#!/usr/bin/env python3
"""Generate sample profile screenshots for trust-layer testing."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).parent / "samples"
OUT.mkdir(parents=True, exist_ok=True)


def make_natural_profile():
    img = Image.new("RGB", (400, 600), color=(240, 235, 230))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 380, 280], fill=(180, 160, 140))
    d.text((30, 300), "Emma, 27", fill=(30, 30, 30))
    d.text((30, 330), "Portland, OR", fill=(80, 80, 80))
    d.text((30, 370), "Bio: Weekend farmer market regular.", fill=(30, 30, 30))
    d.text((30, 400), "Love hiking and cooking from scratch.", fill=(30, 30, 30))
    img.save(OUT / "natural_profile.jpg")
    print(f"Wrote {OUT / 'natural_profile.jpg'}")


def make_filtered_profile():
    img = Image.new("RGB", (400, 600), color=(255, 240, 250))
    d = ImageDraw.Draw(img)
    d.ellipse([80, 40, 320, 280], fill=(255, 220, 200))
    d.text((30, 300), "Jessica, 24", fill=(30, 30, 30))
    d.text((30, 330), "Miami, FL", fill=(80, 80, 80))
    d.text((30, 370), "Bio: Love to laugh! Partner in crime.", fill=(30, 30, 30))
    d.text((30, 400), "Here for a good time not a long time", fill=(30, 30, 30))
    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    img = img.filter(ImageFilter.SMOOTH_MORE)
    img.save(OUT / "filtered_generic_profile.jpg")
    print(f"Wrote {OUT / 'filtered_generic_profile.jpg'}")


def make_ai_style_profile():
    img = Image.new("RGB", (400, 600), color=(20, 20, 35))
    d = ImageDraw.Draw(img)
    d.ellipse([100, 50, 300, 250], fill=(255, 245, 240))
    d.ellipse([140, 120, 170, 150], fill=(100, 180, 255))
    d.ellipse([230, 120, 260, 150], fill=(100, 180, 255))
    d.arc([150, 170, 250, 210], 20, 160, fill=(200, 100, 100), width=3)
    d.text((30, 300), "Model_99, 22", fill=(200, 200, 220))
    d.text((30, 340), "Bio: Perfect in every way.", fill=(200, 200, 220))
    img.save(OUT / "ai_suspect_profile.jpg")
    print(f"Wrote {OUT / 'ai_suspect_profile.jpg'}")


if __name__ == "__main__":
    make_natural_profile()
    make_filtered_profile()
    make_ai_style_profile()