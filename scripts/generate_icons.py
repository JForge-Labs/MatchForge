#!/usr/bin/env python3
"""Generate PNG icons and OG card from MatchForge brand assets."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

BG = (15, 17, 23)
ACCENT_A = (149, 136, 245)
ACCENT_B = (124, 108, 240)
GREEN = (74, 222, 128)


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_logo(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    radius = max(8, size // 4)
    _rounded_rect(draw, (pad, pad, size - pad, size - pad), radius, BG)

    # Gradient-ish M via layered fills
    m_w = int(size * 0.55)
    m_h = int(size * 0.42)
    m_x = (size - m_w) // 2
    m_y = int(size * 0.30)
    leg = max(2, size // 14)
    mid = m_x + m_w // 2
    draw.rectangle((m_x, m_y, m_x + leg, m_y + m_h), fill=ACCENT_B)
    draw.rectangle((m_x + m_w - leg, m_y, m_x + m_w, m_y + m_h), fill=ACCENT_A)
    draw.polygon(
        [
            (m_x + leg, m_y + m_h * 0.35),
            (mid, m_y),
            (m_x + m_w - leg, m_y + m_h * 0.35),
            (m_x + m_w - leg, m_y + m_h),
            (mid, m_y + m_h * 0.55),
            (m_x + leg, m_y + m_h),
        ],
        fill=ACCENT_B,
    )

    dot_r = max(3, size // 13)
    dot_cx = size - pad - dot_r - 2
    dot_cy = pad + dot_r + 2
    draw.ellipse(
        (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
        fill=GREEN,
    )
    return img


def draw_og_card() -> Image.Image:
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    logo = draw_logo(180)
    img.paste(logo, (80, (h - 180) // 2), logo)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        brand_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
    except OSError:
        title_font = ImageFont.load_default()
        sub_font = title_font
        brand_font = title_font

    draw.text((300, 200), "MatchForge vetting summary", fill=(232, 234, 237), font=title_font)
    draw.text(
        (300, 290),
        "AI trust vetting on a dating profile",
        fill=ACCENT_A,
        font=sub_font,
    )
    draw.text(
        (300, 360),
        "Privacy-first match intelligence",
        fill=(154, 160, 176),
        font=sub_font,
    )
    draw.text((300, 480), "MatchForge", fill=ACCENT_B, font=brand_font)
    return img


def main() -> None:
    for size, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        draw_logo(size).convert("RGB").save(OUT / name, format="PNG", optimize=True)
        print(f"Wrote {OUT / name}")

    draw_og_card().save(OUT / "og-card.png", format="PNG", optimize=True)
    print(f"Wrote {OUT / 'og-card.png'}")


if __name__ == "__main__":
    main()