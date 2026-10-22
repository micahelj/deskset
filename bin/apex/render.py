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
FONT_SM = _font(FONT_REG, 9)


def blank(color=0):
    return Image.new("L", (OLED_WIDTH, OLED_HEIGHT), color)


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _blit_text(draw, xy, text, font, fill=255):
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
    if page == "text":
        return text_page(state.get("text", ""), t)
    return text_page(page)
