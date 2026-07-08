"""Validate user-uploaded images before charging tokens or calling vision models."""
from io import BytesIO

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.utils import image as _image  # noqa: F401 — registers the HEIC opener

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_BATCH = 10


def _reject(status: int, error: str, message: str) -> HTTPException:
    return HTTPException(
        status, detail={"error": error, "message": f"{message} No tokens were charged."}
    )


async def read_validated_image(upload: UploadFile) -> bytes:
    """Read an upload with a size cap and verify it decodes as an image.

    Returns b"" for empty parts (callers already skip those). Raises a
    user-readable HTTPException for oversized or non-image files.
    """
    name = upload.filename or "file"
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if not data:
        return b""
    if len(data) > MAX_IMAGE_BYTES:
        raise _reject(
            413,
            "image_too_large",
            f"'{name}' is over 10 MB — please upload a smaller screenshot.",
        )
    try:
        with Image.open(BytesIO(data)) as img:
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise _reject(
            422,
            "invalid_image",
            f"'{name}' isn't a supported image — upload a PNG, JPG, WebP, or HEIC screenshot.",
        )
    return data
