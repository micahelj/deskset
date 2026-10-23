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


def _countdown(seconds):
    """3h 05m / 42m / <1m"""
    mins = int(seconds // 60)
    if mins < 1:
        return "<1m"
    h, m = divmod(mins, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def claude_page(summary, usage=None, t=0.0, resets_in=None):
    """Claude Code activity: animated mascot, state, detail, 5-hour usage meter.

    summary is claude.summary(); usage is a 0..1 fraction or None; resets_in is
    seconds until the 5-hour window refreshes, or None.
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
        right = 125
        if resets_in is not None:
            left = _countdown(resets_in)
            right = 125 - _text_width(draw, left, FONT_SM) - 4
            _blit_text(draw, (right + 4, 29), left, FONT_SM)
        draw.rectangle([46, 35, right, 38], outline=255)
        fill = int((right - 48) * max(0.0, min(1.0, usage)))
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


def _stat_rows(rows):
    """Three label | value | sparkline rows. Columns fit the widest label and a
    "100%" value, so values never touch labels (CPU page: sparkline from x=56)."""
    im = blank()
    draw = ImageDraw.Draw(im)
    label_w = max(_text_width(draw, r[0], FONT_SM) for r in rows)
    value_w = _text_width(draw, "100%", FONT_SM)
    spark_x = 1 + label_w + 3 + value_w + 3
    for i, (label, value, series, lo, hi) in enumerate(rows):
        y = i * 13
        _blit_text(draw, (1, y), label, FONT_SM)
        vw = _text_width(draw, value, FONT_SM)
        _blit_text(draw, (spark_x - 3 - vw, y), value, FONT_SM)
        _sparkline(draw, series, spark_x, y + 2, OLED_WIDTH - spark_x, 10, lo, hi)
    return im


def _pct(series):
    return f"{series[-1] * 100:.0f}%" if series else "–"


def _deg(series):
    return f"{series[-1]:.0f}°" if series else "–"


def system_page(stats):
    """CPU %, memory %, CPU temperature, each with ~72 s of history."""
    cpu, mem, temp = stats.get("cpu") or [], stats.get("mem") or [], stats.get("temp") or []
    return _stat_rows((
        ("CPU", _pct(cpu), cpu, 0.0, 1.0),
        ("MEM", _pct(mem), mem, 0.0, 1.0),
        ("TMP", _deg(temp), temp, *TEMP_SCALE),
    ))


def gpu_page(stats):
    """GPU load, video memory and GPU temperature; a note when there is none or it sleeps."""
    if not stats.get("present"):
        return text_page("No NVIDIA GPU")
    if stats.get("asleep"):
        return text_page("GPU asleep", subtitle=stats.get("name") or "not polled, saves power")
    util, vram, temp = stats.get("util") or [], stats.get("vram") or [], stats.get("temp") or []
    return _stat_rows((
        ("GPU", _pct(util), util, 0.0, 1.0),
        ("VRAM", _pct(vram), vram, 0.0, 1.0),
        ("TMP", _deg(temp), temp, *TEMP_SCALE),
    ))


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
    if page == "toast":
        return text_page(state.get("title", ""), 0, subtitle=state.get("subtitle", ""))
    if page == "gpu":
        return gpu_page(state.get("gpu") or {})
    if page == "system":
        return system_page(state.get("system") or {})
    if page == "cheatsheet":
        return cheatsheet_page(state.get("cheatsheet") or {})
    if page == "claude":
        return claude_page(state.get("claude") or {}, state.get("usage"), t, state.get("resets_in"))
    if page == "text":
        return text_page(state.get("text", ""), t)
    return text_page(page)
