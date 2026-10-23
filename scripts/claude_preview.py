#!/usr/bin/env python3
"""Regenerate docs/media/claude-page.png from the plugin's own OLED renderer.

Each 128x40 frame is exactly what the daemon sends to the keyboard; every
lit pixel is drawn as a square with a thin gap so it reads like an OLED.

    python3 scripts/claude_preview.py
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "bin"))

from PIL import Image, ImageDraw  # noqa: E402

from apex import render  # noqa: E402

FRAMES = (
    ({"state": "working", "detail": "Edit: render.py", "count": 1, "busy": 1}, 0.25),
    ({"state": "waiting", "detail": "Allow Bash?", "count": 1, "busy": 1}, 0.25),
    ({"state": "thinking", "detail": "", "count": 2, "busy": 1}, 0.5),
    ({"state": "idle", "detail": "", "count": 2, "busy": 0}, 0.25),  # eyes open, not mid-blink
)
USAGE = 0.19
RESETS_IN = 3 * 3600 + 32 * 60
SCALE = 4       # screen pixels per OLED pixel
DOT = 3         # lit square inside each cell
PAD = 12        # bezel around each frame
GAP = 16        # space between frames
LIT = (236, 240, 255)
BEZEL = (12, 12, 14)
BACKGROUND = (34, 34, 38)


def oled(frame):
    w, h = frame.size
    out = Image.new("RGB", (w * SCALE + 2 * PAD, h * SCALE + 2 * PAD), BEZEL)
    draw = ImageDraw.Draw(out)
    px = frame.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] > 127:
                x0, y0 = PAD + x * SCALE, PAD + y * SCALE
                draw.rectangle([x0, y0, x0 + DOT - 1, y0 + DOT - 1], fill=LIT)
    return out


def main(path=os.path.join(ROOT, "docs", "media", "claude-page.png")):
    tiles = [oled(render.claude_page(s, USAGE, t, RESETS_IN)) for s, t in FRAMES]
    tw, th = tiles[0].size
    sheet = Image.new("RGB", (2 * tw + 3 * GAP, 2 * th + 3 * GAP), BACKGROUND)
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (GAP + (i % 2) * (tw + GAP), GAP + (i // 2) * (th + GAP)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path, optimize=True)
    print(path)


if __name__ == "__main__":
    main(*sys.argv[1:])
