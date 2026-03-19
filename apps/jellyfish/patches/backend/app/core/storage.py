"""统一存储封装。

优先使用 S3；未配置 `s3_bucket_name` 时，回退到本地文件系统存储。
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

from anyio import to_thread
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings


@dataclass
class StoredFileInfo:
    key: str
    url: str
    size: int | None = None
    content_type: str | None = None
    etag: str | None = None
    extra: dict[str, Any] | None = None


def _use_s3() -> bool:
    return bool(settings.s3_bucket_name)


def _local_root() -> Path:
    return Path(settings.local_storage_dir).resolve()


def _local_path_for_key(key: str) -> Path:
    return _local_root() / key.lstrip("/")


def _local_public_url(key: str) -> str:
    return f"/local-files/{quote(key.lstrip('/'))}"


def _build_s3_client():
    if not settings.s3_bucket_name:
        raise RuntimeError("S3 未配置：请设置 s3_bucket_name")

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region_name,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=BotoConfig(s3={"addressing_style": "virtual"}),
    )


def _normalize_key(key: str) -> str:
    key = key.lstrip("/")
    base = settings.s3_base_path.strip().strip("/")
    if base:
        return f"{base}/{key}"
    return key


def _build_public_url(key: str) -> str:
    if not _use_s3():
        return _local_public_url(key)

    key = _normalize_key(key)
    if settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
    endpoint = settings.s3_endpoint_url.rstrip("/") if settings.s3_endpoint_url else ""
    if endpoint:
        return f"{endpoint}/{settings.s3_bucket_name}/{key}"
    return f"/{settings.s3_bucket_name}/{key}"


def init_storage() -> None:
    if not _use_s3():
        _local_root().mkdir(parents=True, exist_ok=True)
        return

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if not bucket:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise

    params: dict[str, Any] = {"Bucket": bucket}
    region = settings.s3_region_name
    if region and region != "us-east-1":
        params["CreateBucketConfiguration"] = {"LocationConstraint": region}

    try:
        client.create_bucket(**params)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise

    client.head_bucket(Bucket=bucket)


async def upload_file(
    *,
    key: str,
    data: bytes | BinaryIO,
    content_type: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> StoredFileInfo:
    if not _use_s3():
        path = _local_path_for_key(key)

        def _write() -> int:
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, (bytes, bytearray)):
                payload = bytes(data)
            else:
                payload = data.read()
            path.write_bytes(payload)
            return len(payload)

        size = await to_thread.run_sync(_write)
        return StoredFileInfo(key=key, url=_build_public_url(key), size=size, content_type=content_type)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)
    extra = extra_args.copy() if extra_args else {}
    if content_type and "ContentType" not in extra:
        extra["ContentType"] = content_type

    def _upload():
        if isinstance(data, (bytes, bytearray)):
            return client.put_object(Bucket=bucket, Key=s3_key, Body=data, **extra)
        return client.upload_fileobj(data, bucket, s3_key, ExtraArgs=extra)  # type: ignore[arg-type]

    result = await to_thread.run_sync(_upload)
    etag = result.get("ETag") if isinstance(result, dict) else None
    return StoredFileInfo(key=s3_key, url=_build_public_url(key), etag=etag, content_type=content_type)


async def download_file(*, key: str) -> bytes:
    if not _use_s3():
        path = _local_path_for_key(key)
        return await to_thread.run_sync(path.read_bytes)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)

    def _download() -> bytes:
        obj = client.get_object(Bucket=bucket, Key=s3_key)
        return obj["Body"].read()  # type: ignore[no-any-return]

    return await to_thread.run_sync(_download)


async def get_file_info(*, key: str) -> StoredFileInfo:
    if not _use_s3():
        path = _local_path_for_key(key)

        def _stat() -> StoredFileInfo:
            stat = path.stat()
            return StoredFileInfo(
                key=key,
                url=_build_public_url(key),
                size=stat.st_size,
                extra={"LastModified": stat.st_mtime},
            )

        return await to_thread.run_sync(_stat)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)

    def _head() -> dict[str, Any]:
        return client.head_object(Bucket=bucket, Key=s3_key)  # type: ignore[no-any-return]

    meta = await to_thread.run_sync(_head)
    return StoredFileInfo(
        key=s3_key,
        url=_build_public_url(key),
        size=int(meta.get("ContentLength") or 0),
        content_type=meta.get("ContentType"),
        etag=meta.get("ETag"),
        extra={k: v for k, v in meta.items() if k not in {"ContentLength", "ContentType", "ETag"}},
    )


async def list_files(*, prefix: str = "") -> list[StoredFileInfo]:
    if not _use_s3():
        root = _local_root()
        base = root / prefix.lstrip("/") if prefix else root

        def _list() -> list[StoredFileInfo]:
            if not base.exists():
                return []
            results: list[StoredFileInfo] = []
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                key = str(path.relative_to(root))
                results.append(
                    StoredFileInfo(
                        key=key,
                        url=_build_public_url(key),
                        size=path.stat().st_size,
                    )
                )
            return results

        return await to_thread.run_sync(_list)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    normalized_prefix = _normalize_key(prefix) if prefix else settings.s3_base_path.strip().strip("/")

    def _list() -> list[dict[str, Any]]:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=normalized_prefix or None)
        return resp.get("Contents", [])  # type: ignore[no-any-return]

    contents = await to_thread.run_sync(_list)
    return [
        StoredFileInfo(
            key=item["Key"],
            url=_build_public_url(item["Key"]),
            size=int(item.get("Size") or 0),
            extra={"LastModified": item.get("LastModified"), "StorageClass": item.get("StorageClass")},
        )
        for item in contents
    ]


async def delete_file(*, key: str) -> None:
    if not _use_s3():
        path = _local_path_for_key(key)

        def _delete() -> None:
            if path.exists():
                path.unlink()

        await to_thread.run_sync(_delete)
        return

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)

    def _delete() -> None:
        client.delete_object(Bucket=bucket, Key=s3_key)

    await to_thread.run_sync(_delete)
