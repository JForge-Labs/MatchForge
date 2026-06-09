"""Image normalization helpers (EXIF orientation, RGB conversion)."""
from io import BytesIO

from PIL import Image, ImageOps


def open_normalized(image_bytes: bytes) -> Image.Image:
    """Open image bytes and apply EXIF orientation so pixels match display intent."""
    img = Image.open(BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def save_jpeg(image_bytes: bytes, path, *, quality: int = 90) -> None:
    """Normalize orientation and persist as JPEG."""
    img = open_normalized(image_bytes)
    img.save(path, format="JPEG", quality=quality)