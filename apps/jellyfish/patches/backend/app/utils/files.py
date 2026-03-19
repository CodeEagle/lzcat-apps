from __future__ import annotations

import base64
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.models.studio import FileItem, FileType


async def create_file_from_url_or_b64(
    db: AsyncSession,
    *,
    url: str | None = None,
    b64_data: str | None = None,
    name: str,
    prefix: str = "files",
) -> FileItem:
    payload: bytes
    content_type: str | None = None
    extension = ".bin"

    if url:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
        payload = response.content
        content_type = response.headers.get("content-type", "").split(";")[0] or None
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix
        if suffix:
            extension = suffix
        elif content_type:
            guessed = mimetypes.guess_extension(content_type)
            if guessed:
                extension = guessed
    elif b64_data:
        raw = b64_data
        if "," in raw and raw.startswith("data:"):
            header, raw = raw.split(",", 1)
            content_type = header.split(";", 1)[0].replace("data:", "", 1) or None
        payload = base64.b64decode(raw)
        if content_type:
            guessed = mimetypes.guess_extension(content_type)
            if guessed:
                extension = guessed
    else:
        raise ValueError("Either url or b64_data must be provided")

    file_id = str(uuid.uuid4())
    object_name = f"{file_id}{extension}"
    key = f"{prefix.strip('/').strip()}/{object_name}" if prefix.strip() else object_name
    info = await storage.upload_file(
        key=key,
        data=payload,
        content_type=content_type,
        extra_args={"ACL": "public-read"},
    )

    file_type = FileType.image
    if content_type and content_type.startswith("video/"):
        file_type = FileType.video

    file_obj = FileItem(
        id=file_id,
        type=file_type,
        name=name,
        thumbnail=info.url,
        tags=[],
        storage_key=key,
    )
    db.add(file_obj)
    await db.flush()
    await db.refresh(file_obj)
    return file_obj
