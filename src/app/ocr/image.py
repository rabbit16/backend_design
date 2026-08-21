from __future__ import annotations

import base64

from src.app.core.exceptions import AppError

ALLOWED_IMAGE_MIME = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})

_EXT_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

_SOURCE_LABELS = {
    "camera": "相机拍摄",
    "album": "相册选择",
}


def source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source)


def sniff_image_mime(
    data: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"

    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared in ALLOWED_IMAGE_MIME:
        return declared
    if declared == "image/jpg":
        return "image/jpeg"

    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _EXT_MIME:
            return _EXT_MIME[ext]

    if declared.startswith("image/"):
        raise AppError(
            "暂不支持该图片格式，请上传 jpg / png / webp / gif",
            code="unsupported_image_type",
            status_code=400,
        )
    return "image/jpeg"


def validate_image_bytes(data: bytes, *, max_bytes: int) -> None:
    if not data:
        raise AppError("图片不能为空", code="empty_file", status_code=400)
    if len(data) > max_bytes:
        raise AppError(
            f"图片过大（上限 {max_bytes} 字节）",
            code="image_too_large",
            status_code=400,
        )


def to_data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
