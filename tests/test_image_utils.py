#!/usr/bin/env python3
"""Image orientation normalization tests."""
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.image import open_normalized, save_jpeg


def test_exif_orientation_is_applied_before_save(tmp_path):
    img = Image.new("RGB", (120, 80), color="red")
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=img.getexif())
    exif = img.getexif()
    exif[274] = 6  # rotate 90 CW
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    raw = buf.getvalue()

    normalized = open_normalized(raw)
    assert normalized.size == (80, 120)

    out = tmp_path / "out.jpg"
    save_jpeg(raw, out)
    saved = Image.open(out)
    assert saved.size == (80, 120)