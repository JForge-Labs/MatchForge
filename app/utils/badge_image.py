"""Render the shareable X-verification badge PNG (OG card) with Pillow."""
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
BG = (15, 17, 23)
SURFACE = (26, 29, 39)
BORDER = (42, 47, 61)
TEXT = (232, 234, 237)
MUTED = (154, 160, 176)
ACCENT = (124, 108, 240)
GREEN = (74, 222, 128)
YELLOW = (250, 204, 21)
RED = (248, 113, 113)

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _score_color(score: float | None) -> tuple[int, int, int]:
    if score is None:
        return MUTED
    if score >= 70:
        return GREEN
    if score >= 40:
        return YELLOW
    return RED


def render_verify_badge(
    *,
    handle: str,
    score: float | None,
    verdict: str,
    summary: str = "",
) -> bytes:
    """Return a 1200x630 PNG badge for the public verification report."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Card surface
    draw.rounded_rectangle(
        (60, 60, WIDTH - 60, HEIGHT - 60), radius=28, fill=SURFACE, outline=BORDER, width=2
    )

    # Header
    draw.text((110, 110), "MatchForge", font=_font(44), fill=ACCENT)
    draw.text((110, 168), "X-VERIFIED DATING INTELLIGENCE", font=_font(22), fill=MUTED)

    # Handle
    draw.text((110, 250), f"@{handle}", font=_font(64), fill=TEXT)

    # Verdict pill
    verdict_label = verdict.replace("_", " ").title()
    pill_font = _font(28)
    pill_w = draw.textlength(verdict_label, font=pill_font) + 48
    draw.rounded_rectangle(
        (110, 350, 110 + pill_w, 406), radius=28, outline=_score_color(score), width=2
    )
    draw.text((134, 362), verdict_label, font=pill_font, fill=_score_color(score))

    # Score block (right side)
    if score is not None:
        score_text = f"{score:.0f}"
        score_font = _font(160)
        sw = draw.textlength(score_text, font=score_font)
        draw.text((WIDTH - 170 - sw, 200), score_text, font=score_font, fill=_score_color(score))
        draw.text((WIDTH - 320, 380), "X SOCIAL PROOF / 100", font=_font(22), fill=MUTED)

    # Summary
    if summary:
        words = summary.split()
        lines: list[str] = []
        current = ""
        body_font = _font(26)
        for word in words:
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=body_font) > WIDTH - 260:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        y = 440
        for line in lines[:2]:
            draw.text((110, y), line, font=body_font, fill=TEXT)
            y += 36

    # Footer
    draw.text(
        (110, HEIGHT - 110),
        "Powered by the X API + Grok agentic search · public data only",
        font=_font(20),
        fill=MUTED,
    )

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
