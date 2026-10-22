"""Apex OLED (128x40) via HID feature reports on the control interface."""

from __future__ import annotations

import fcntl
import os

from PIL import Image

from . import devices

OLED_WIDTH = 128
OLED_HEIGHT = 40
OLED_REPORT_ID = 0x61
# Gen 3: 00 1F 81 + 640 bytes + pad. 0x81 is the live framebuffer; never use
# 0x83, which persists the image in the keyboard's own memory.
GEN3_HEADER = bytes([0x00, 0x1F, 0x81])
GEN3_REPORT_LENGTH = 644

_IOC_WRITE = 1
_IOC_READ = 2


def _ioc(direction, type_, nr, size):
    return (direction << 30) | (size << 16) | (ord(type_) << 8) | nr


def hidios_feature(length):
    return _ioc(_IOC_WRITE | _IOC_READ, "H", 0x06, length)


def find_oled_hidraw():
    _profile, path = devices.detect()
    return path


def _mono(image: Image.Image):
    im = image.convert("L")
    if im.size != (OLED_WIDTH, OLED_HEIGHT):
        im = im.resize((OLED_WIDTH, OLED_HEIGHT), Image.Resampling.LANCZOS)
    return im.load()


def image_to_report(image: Image.Image) -> bytes:
    """Apex 7: row-major, MSB-first."""
    pix = _mono(image)
    bits = []
    for y in range(OLED_HEIGHT):
        for x in range(OLED_WIDTH):
            bits.append(1 if pix[x, y] > 127 else 0)
    payload = [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    return bytes([OLED_REPORT_ID, *payload, 0x00])


def image_to_gen3_report(image: Image.Image) -> bytes:
    """Gen 3: five 128-byte pages; byte page*128+x holds (x, page*8..+7), bit 0 on top."""
    pix = _mono(image)
    out = bytearray(GEN3_REPORT_LENGTH)
    out[:3] = GEN3_HEADER
    for page in range(OLED_HEIGHT // 8):
        for x in range(OLED_WIDTH):
            byte = 0
            for bit in range(8):
                if pix[x, page * 8 + bit] > 127:
                    byte |= 1 << bit
            out[3 + page * OLED_WIDTH + x] = byte
    return bytes(out)


def send_report(data: bytes, hidraw=None):
    path = hidraw or find_oled_hidraw()
    if not path:
        raise FileNotFoundError("Apex OLED hidraw (control interface) not found")
    buf = bytearray(data)
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.ioctl(fd, hidios_feature(len(buf)), buf, True)
    finally:
        os.close(fd)
    return path


def send_image(image: Image.Image, hidraw=None):
    profile, path = devices.detect()
    if profile and profile.oled == "gen3":
        return send_report(image_to_gen3_report(image), hidraw=hidraw or path)
    return send_report(image_to_report(image), hidraw=hidraw or path)


def send_file(path, hidraw=None):
    return send_image(Image.open(path), hidraw=hidraw)


def clear(hidraw=None):
    return send_image(Image.new("L", (OLED_WIDTH, OLED_HEIGHT), 0), hidraw=hidraw)
