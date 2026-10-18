"""Flat illustrated avatars from an avatar key like "f-40-3" (gender, age, palette). One shape list drives both the SVG
(web) and a Pillow PNG (slides, documents), so the two always match. Deliberately stylised: no skin tones, no realism."""

from __future__ import annotations

import io
from typing import Any

# (background, figure, hair) per palette; hair greys with age
PALETTES = [
    ("#E8F0FE", "#4F6BED", "#2B2F77"), ("#FDECEA", "#E0574F", "#6B2420"), ("#E6F6EC", "#2E9E5B", "#14502D"),
    ("#FFF4E0", "#E59A1F", "#6E4608"), ("#F1E8FB", "#8A56D6", "#43257A"), ("#E3F4F7", "#1C93A8", "#0D4A56"),
]
GREY = "#B8B8C0"


def parse(key: str) -> tuple[str, int, int]:
    try:
        g, age, pal = key.split("-")
        return (g if g in ("f", "m", "n") else "n"), int(age), int(pal) % len(PALETTES)
    except (ValueError, AttributeError):
        return "n", 35, 0


def shapes(key: str) -> list[dict[str, Any]]:
    """Shapes on a 100x100 canvas: {type: circle|ellipse|rect, cx, cy, rx, ry | x,y,w,h,r, fill}."""
    g, age, pal = parse(key)
    bg, fig, hair = PALETTES[pal]
    if age >= 55:
        hair = GREY
    elif age >= 45:
        hair = "#7B7B88"
    out: list[dict[str, Any]] = [{"type": "circle", "cx": 50, "cy": 50, "rx": 50, "ry": 50, "fill": bg}]
    if g == "f":  # long hair behind the head
        out.append({"type": "rect", "x": 27, "y": 24, "w": 46, "h": 46, "r": 20, "fill": hair})
    out.append({"type": "ellipse", "cx": 50, "cy": 104, "rx": 34, "ry": 30, "fill": fig})  # shoulders
    out.append({"type": "rect", "x": 44, "y": 58, "w": 12, "h": 14, "r": 4, "fill": "#F2C9A8"})  # neck
    out.append({"type": "ellipse", "cx": 50, "cy": 45, "rx": 16, "ry": 19, "fill": "#F6D7BC"})  # head (stylised, neutral)
    if g == "m":
        out.append({"type": "rect", "x": 33, "y": 24, "w": 34, "h": 15, "r": 8, "fill": hair})
    elif g == "f":
        out.append({"type": "rect", "x": 32, "y": 24, "w": 36, "h": 13, "r": 8, "fill": hair})
    else:
        out.append({"type": "rect", "x": 34, "y": 25, "w": 32, "h": 11, "r": 6, "fill": hair})
    return out


def svg(key: str, size: int = 96) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}" role="img" aria-label="avatar">',
             '<defs><clipPath id="c"><circle cx="50" cy="50" r="50"/></clipPath></defs><g clip-path="url(#c)">']
    for s in shapes(key):
        if s["type"] == "circle":
            parts.append(f'<circle cx="{s["cx"]}" cy="{s["cy"]}" r="{s["rx"]}" fill="{s["fill"]}"/>')
        elif s["type"] == "ellipse":
            parts.append(f'<ellipse cx="{s["cx"]}" cy="{s["cy"]}" rx="{s["rx"]}" ry="{s["ry"]}" fill="{s["fill"]}"/>')
        else:
            parts.append(f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="{s["r"]}" fill="{s["fill"]}"/>')
    parts.append("</g></svg>")
    return "".join(parts)


def png(key: str, size: int = 256) -> bytes:
    from PIL import Image, ImageDraw
    k = 4  # supersample for smooth edges
    img = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = size * k / 100.0
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * k - 1, size * k - 1), fill=255)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for s in shapes(key):
        if s["type"] in ("circle", "ellipse"):
            ld.ellipse(((s["cx"] - s["rx"]) * f, (s["cy"] - s["ry"]) * f, (s["cx"] + s["rx"]) * f, (s["cy"] + s["ry"]) * f), fill=s["fill"])
        else:
            ld.rounded_rectangle((s["x"] * f, s["y"] * f, (s["x"] + s["w"]) * f, (s["y"] + s["h"]) * f), radius=s["r"] * f, fill=s["fill"])
    img.paste(layer, (0, 0), mask)
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
