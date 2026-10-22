"""Render 128x40 1-bit frames for the Apex OLED."""

from __future__ import annotations

import os
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import devices
from .config import LOGO_PATH
from .oled import OLED_HEIGHT, OLED_WIDTH

FONT_REG = "/usr/share/fonts/noto/NotoSans-Regular.ttf"
FONT_MONO = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"
LOGO_FALLBACK = LOGO_PATH


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


FONT_LG = _font(FONT_MONO, 18)
FONT_MD = _font(FONT_REG, 11)
FONT_SM = _font(FONT_REG, 10)


def blank(color=0):
    return Image.new("L", (OLED_WIDTH, OLED_HEIGHT), color)


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _blit_text(draw, xy, text, font, fill=255):
    # Draw 1-bit glyphs: antialiased edges fall below the OLED threshold and
    # leave gaps in small text.
    draw.fontmode = "1"
    draw.text(xy, text, font=font, fill=fill)


def _scroll_x(text, font, t, speed=28, pad=16):
    dummy = ImageDraw.Draw(blank())
    width = _text_width(dummy, text, font)
    if width <= OLED_WIDTH - 4:
        return 2
    span = width + pad + OLED_WIDTH
    return int(OLED_WIDTH - (t * speed % span))


def clock(_state, now=None):
    now = now or datetime.now()
    im = blank()
    draw = ImageDraw.Draw(im)
    time_s = now.strftime("%H:%M")
    date_s = now.strftime("%a %d %b")
    tw = _text_width(draw, time_s, FONT_LG)
    _blit_text(draw, ((OLED_WIDTH - tw) // 2, -2), time_s, FONT_LG)
    dw = _text_width(draw, date_s, FONT_SM)
    _blit_text(draw, ((OLED_WIDTH - dw) // 2, 24), date_s, FONT_SM)
    return im


def text_page(message, t=0.0, subtitle=""):
    im = blank()
    draw = ImageDraw.Draw(im)
    message = (message or "").strip() or devices.current().short
    x = _scroll_x(message, FONT_MD, t)
    _blit_text(draw, (x, 4 if subtitle else 12), message, FONT_MD)
    if subtitle:
        sx = _scroll_x(subtitle, FONT_SM, t * 0.7)
        _blit_text(draw, (sx, 22), subtitle, FONT_SM)
    return im


def now_playing(title, artist, t=0.0, playing=True):
    mark = ">" if playing else "="
    headline = f"{mark} {title}" if title else "Nothing playing"
    return text_page(headline, t=t, subtitle=artist or "")


def workspace(name, title, t=0.0):
    label = f"WS {name}" if name else "Workspace"
    return text_page(label, t=0, subtitle=title or "")


# 1-bit homage to the Claude Code banner mascot: head with eye notches, arms, legs.
_CLAWD_BODY = (
    "....##########....",
    "....##########....",
    "....#..####..#....",
    "....#..####..#....",
    "##################",
    "##################",
    "..##############..",
    "..##############..",
)
_CLAWD_BLINK_ROW = "....##########...."
_CLAWD_LEGS = (
    ("....#.#....#.#....",) * 3,                                              # standing
    ("....#.#....#.#....", "...#.#....#.#.....", "...#.#....#.#....."),        # step left
    ("....#.#....#.#....", ".....#.#....#.#...", ".....#.#....#.#..."),        # step right
)
_CLAUDE_LABEL = {
    "waiting": "Needs you",
    "working": "Working",
    "thinking": "Thinking",
    "done": "Done",
    "idle": "Idle",
    "none": "No sessions",
}


def _blit_rows(im, rows, x0, y0, scale=2):
    px = im.load()
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != "#":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    xx, yy = x0 + x * scale + dx, y0 + y * scale + dy
                    if 0 <= xx < OLED_WIDTH and 0 <= yy < OLED_HEIGHT:
                        px[xx, yy] = 255


def claude_page(summary, usage=None, t=0.0):
    """Claude Code activity: animated mascot, state, detail, 5-hour usage meter.

    summary is claude.summary(); usage is a 0..1 fraction or None.
    """
    state = summary.get("state", "none")
    tick = int(t * 4)  # 4 animation frames per second
    rows = list(_CLAWD_BODY)
    bob = 0
    legs = _CLAWD_LEGS[0]
    bang = False
    if state in ("idle", "none", "done"):
        if tick % 16 == 0:  # blink every 4 s
            rows[2] = rows[3] = _CLAWD_BLINK_ROW
    elif state == "thinking":
        bob = -1 if (tick // 2) % 2 else 0
    elif state == "working":
        legs = _CLAWD_LEGS[1 + tick % 2]
    elif state == "waiting":
        bob = -2 if tick % 2 else 0
        bang = tick % 4 < 3

    im = blank()
    draw = ImageDraw.Draw(im)
    _blit_rows(im, rows + list(legs), 2, 8 + bob)
    if bang:
        draw.rectangle([40, 4, 41, 11], fill=255)
        draw.rectangle([40, 14, 41, 15], fill=255)

    label = _CLAUDE_LABEL.get(state, state.title())
    if state == "thinking":
        label += "." * (1 + (tick // 2) % 3)
    _blit_text(draw, (46, 1), label, FONT_MD)

    detail = summary.get("detail") or ""
    count = summary.get("count", 0)
    if not detail and count > 1:
        detail = f"{count} sessions" if not summary.get("busy") else f"{summary['busy']} of {count} busy"
    if detail:
        room = OLED_WIDTH - 48
        if _text_width(draw, detail, FONT_SM) > room:
            while detail and _text_width(draw, detail + "…", FONT_SM) > room:
                detail = detail[:-1]
            detail += "…"
        _blit_text(draw, (46, 15), detail, FONT_SM)

    if usage is not None:
        draw.rectangle([46, 35, 125, 38], outline=255)
        fill = int(77 * max(0.0, min(1.0, usage)))
        if fill:
            draw.rectangle([47, 36, 47 + fill - 1, 37], fill=255)
    return im


TEMP_SCALE = (30.0, 100.0)  # °C mapped to an empty..full sparkline


def _sparkline(draw, values, x0, y0, width, height, lo=0.0, hi=1.0):
    """1-px bars, newest on the right, filled from the bottom; baseline always drawn."""
    draw.line([x0, y0 + height - 1, x0 + width - 1, y0 + height - 1], fill=255)
    recent = values[-width:]
    start = x0 + width - len(recent)
    for i, v in enumerate(recent):
        frac = max(0.0, min(1.0, (v - lo) / (hi - lo)))
        bar = int(round(frac * (height - 1)))
        if bar:
            draw.line([start + i, y0 + height - 1 - bar, start + i, y0 + height - 1], fill=255)


def system_page(stats):
    """Three rows: CPU %, memory %, CPU temperature, each with ~75 s of history."""
    im = blank()
    draw = ImageDraw.Draw(im)
    cpu, mem, temp = stats.get("cpu") or [], stats.get("mem") or [], stats.get("temp") or []
    rows = (
        ("CPU", f"{cpu[-1] * 100:.0f}%" if cpu else "–", cpu, 0.0, 1.0),
        ("MEM", f"{mem[-1] * 100:.0f}%" if mem else "–", mem, 0.0, 1.0),
        ("TMP", f"{temp[-1]:.0f}°" if temp else "–", temp, *TEMP_SCALE),
    )
    # Widest label "MEM" is 24 px and widest value "100%" 25 px at FONT_SM:
    # label at 1, value right-aligned to 53, sparkline from 56 (72 px wide).
    spark_x = 56
    for i, (label, value, series, lo, hi) in enumerate(rows):
        y = i * 13
        _blit_text(draw, (1, y), label, FONT_SM)
        vw = _text_width(draw, value, FONT_SM)
        _blit_text(draw, (spark_x - 3 - vw, y), value, FONT_SM)
        _sparkline(draw, series, spark_x, y + 2, OLED_WIDTH - spark_x, 10, lo, hi)
    return im


def _fit(draw, text, font, room):
    if _text_width(draw, text, font) <= room:
        return text
    while text and _text_width(draw, text + "…", font) > room:
        text = text[:-1]
    return text + "…"


def cheatsheet_page(state):
    """Keybinding cheat sheet: modifier set, then the selected key and action."""
    im = blank()
    draw = ImageDraw.Draw(im)
    position = state.get("position", "")
    pw = _text_width(draw, position, FONT_SM)
    _blit_text(draw, (OLED_WIDTH - pw - 1, 3), position, FONT_SM)
    _blit_text(draw, (1, 1), _fit(draw, state.get("label", ""), FONT_MD, OLED_WIDTH - pw - 6), FONT_MD)
    if state.get("key"):
        _blit_text(draw, (1, 15), _fit(draw, state["key"], FONT_SM, OLED_WIDTH - 2), FONT_SM)
        _blit_text(draw, (1, 27), _fit(draw, state.get("description", ""), FONT_SM, OLED_WIDTH - 2), FONT_SM)
    else:
        _blit_text(draw, (1, 15), f"{state.get('count', 0)} keys · scroll", FONT_SM)
        _blit_text(draw, (1, 27), "click: next set", FONT_SM)
    return im


def image_page(path):
    path = os.path.expanduser(path or LOGO_FALLBACK)
    if not os.path.isfile(path):
        return text_page("no image")
    src = Image.open(path).convert("L")
    src = ImageOps.contain(src, (OLED_WIDTH, OLED_HEIGHT), Image.Resampling.LANCZOS)
    im = blank()
    x = (OLED_WIDTH - src.size[0]) // 2
    y = (OLED_HEIGHT - src.size[1]) // 2
    im.paste(src, (x, y))
    # Hard 1-bit so the OLED doesn't look muddy.
    return im.point(lambda p: 255 if p > 110 else 0, mode="L")


def render(page, state):
    """state keys: text, image, title, artist, playing, workspace, window, t."""
    t = state.get("t", time.time())
    if page == "clear":
        return blank()
    if page == "clock":
        return clock(state)
    if page == "now-playing":
        return now_playing(state.get("title", ""), state.get("artist", ""), t, state.get("playing", False))
    if page == "workspace":
        return workspace(state.get("workspace", ""), state.get("window", ""), t)
    if page == "logo":
        return image_page(state.get("image"))
    if page == "system":
        return system_page(state.get("system") or {})
    if page == "cheatsheet":
        return cheatsheet_page(state.get("cheatsheet") or {})
    if page == "claude":
        return claude_page(state.get("claude") or {}, state.get("usage"), t)
    if page == "text":
        return text_page(state.get("text", ""), t)
    return text_page(page)
