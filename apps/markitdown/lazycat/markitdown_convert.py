import io
import os
import re
from pathlib import Path

from markitdown import MarkItDown, StreamInfo


CID_TOKEN_RE = re.compile(r"\(cid:\d+\)")
CID_TOKEN_MIN_COUNT = 5


def plugins_enabled() -> bool:
    return os.getenv("MARKITDOWN_ENABLE_PLUGINS", "false").strip().lower() in (
        "true",
        "1",
        "yes",
    )


def build_converter() -> MarkItDown:
    return MarkItDown(enable_plugins=plugins_enabled())


def is_probably_pdf(*, uri: str | None = None, filename: str | None = None, mimetype: str | None = None) -> bool:
    if mimetype and "pdf" in mimetype.lower():
        return True

    if filename and filename.lower().endswith(".pdf"):
        return True

    if uri:
        lowered = uri.lower()
        if lowered.startswith("data:application/pdf"):
            return True
        if ".pdf" in lowered:
            return True

    return False


def validate_markdown(markdown: str, *, source_label: str) -> str:
    cid_tokens = CID_TOKEN_RE.findall(markdown)
    if len(cid_tokens) >= CID_TOKEN_MIN_COUNT:
        raise ValueError(
            f"{source_label} 的 PDF 文本层无法被当前提取器正确解码，已检测到大量 CID 字形标记。"
            " 这类 PDF 需要 OCR 或更强的文档解析服务，当前结果继续返回只会是乱码。"
        )
    return markdown


def convert_uri(uri: str) -> str:
    result = build_converter().convert_uri(uri)
    if is_probably_pdf(uri=uri):
        return validate_markdown(result.markdown, source_label="该文件")
    return result.markdown


def convert_upload(upload_bytes: bytes, *, filename: str, mimetype: str | None = None) -> str:
    stream_info = StreamInfo(
        filename=filename,
        extension=(Path(filename).suffix or None),
        mimetype=(mimetype or None),
    )
    result = build_converter().convert_stream(io.BytesIO(upload_bytes), stream_info=stream_info)
    if is_probably_pdf(filename=filename, mimetype=mimetype):
        return validate_markdown(result.markdown, source_label=filename)
    return result.markdown
