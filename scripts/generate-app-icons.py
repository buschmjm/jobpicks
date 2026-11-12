#!/usr/bin/env python3
"""Generate JobPicks launcher icons from brand colors (deck stack + amber accent)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCES = REPO_ROOT / "resources"
STORE_LISTING = REPO_ROOT / "docs" / "store-listing"


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (250, 250, 249, 255))
    draw = ImageDraw.Draw(img)
    scale = size / 48.0

    def rect(x: int, y: int, w: int, h: int, fill: str, outline: str | None = None, width: int = 1) -> None:
        box = [x * scale, y * scale, (x + w) * scale, (y + h) * scale]
        draw.rounded_rectangle(box, radius=4 * scale, fill=fill, outline=outline, width=max(1, int(width * scale)))

    rect(8, 10, 28, 20, "#fafaf9", "#e7e5e4")
    rect(12, 16, 28, 20, "#ffffff", "#292524", 2)
    rect(16, 22, 28, 20, "#f5f5f4", "#e7e5e4")
    draw.line(
        [(16 * scale, 28 * scale), (36 * scale, 28 * scale)],
        fill="#b45309",
        width=max(2, int(2 * scale)),
    )
    draw.line(
        [(16 * scale, 33 * scale), (30 * scale, 33 * scale)],
        fill="#a8a29e",
        width=max(1, int(1.5 * scale)),
    )
    return img


def main() -> None:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    STORE_LISTING.mkdir(parents=True, exist_ok=True)

    for size, path in (
        (1024, RESOURCES / "icon.png"),
        (512, STORE_LISTING / "icon-512.png"),
        (192, RESOURCES / "icon-192.png"),
    ):
        draw_icon(size).save(path, format="PNG")
        print(f"Wrote {path} ({size}x{size})")


if __name__ == "__main__":
    main()
