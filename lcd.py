import os
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence

from i18n import t

FORMAT_Q565 = 0x08
FORMAT_RGB565 = 0x06


def to_rgb565(image):
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint16)
    r = rgb[..., 0] >> 3
    g = rgb[..., 1] >> 2
    b = rgb[..., 2] >> 3
    return ((r << 11) | (g << 5) | b).ravel()


def encode_q565(image):
    pixels = to_rgb565(image)
    w, h = image.size

    change = np.empty(len(pixels), dtype=bool)
    change[0] = True
    change[1:] = pixels[1:] != pixels[:-1]
    starts = np.flatnonzero(change)
    lengths = np.diff(np.append(starts, len(pixels)))
    values = pixels[starts]

    extra = lengths - 1
    full = extra // 62
    rest = extra % 62
    sizes = 3 + full + (rest > 0)
    offsets = np.concatenate(([0], np.cumsum(sizes)[:-1]))

    out = np.full(int(sizes.sum()), 0xC0 | 61, dtype=np.uint8)
    out[offsets] = 0xFE
    out[offsets + 1] = values & 0xFF
    out[offsets + 2] = values >> 8
    has_rest = rest > 0
    out[(offsets + 3 + full)[has_rest]] = 0xC0 | (rest[has_rest] - 1)

    return b"q565" + struct.pack("<HH", w, h) + out.tobytes() + b"\xff"


def encode_rgb565(image):
    return to_rgb565(image).astype(">u2").tobytes()


def encode(image, fmt):
    return encode_q565(image) if fmt == FORMAT_Q565 else encode_rgb565(image)


def fit(image, size, rotation, zoom=1.0, dx=0.0, dy=0.0):
    image = image.convert("RGB")
    w, h = image.size
    scale = size / min(w, h) * zoom
    width, height = max(1, round(w * scale)), max(1, round(h * scale))
    image = image.resize((width, height), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    canvas.paste(image, (round((size - width) / 2 + dx * size), round((size - height) / 2 + dy * size)))
    if rotation:
        canvas = canvas.rotate(-rotation)
    return canvas


def load_media(path, size, rotation, fmt, zoom=1.0, dx=0.0, dy=0.0):
    source = Image.open(path)
    frames = []
    for frame in ImageSequence.Iterator(source):
        duration = frame.info.get("duration", source.info.get("duration", 100)) or 100
        image = fit(frame, size, rotation, zoom, dx, dy)
        frames.append((encode(image, fmt), max(20, duration) / 1000))
    return frames


def font(size, bold=False):
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    folders = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"), "/usr/share/fonts/truetype/dejavu"]
    for folder in folders:
        for name in names + ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def sensor_frame(size, rotation, liquid, cpu_temp, cpu_load, accent):
    accent = hex_to_rgb(accent)
    image = Image.new("RGB", (size, size), (8, 10, 14))
    draw = ImageDraw.Draw(image)

    margin = size * 0.06
    width = max(4, int(size * 0.045))
    box = [margin, margin, size - margin, size - margin]
    draw.arc(box, 135, 405, fill=(38, 42, 50), width=width)
    if liquid is not None:
        share = max(0.0, min(1.0, (liquid - 20) / 40))
        if share > 0:
            draw.arc(box, 135, 135 + 270 * share, fill=accent, width=width)

    center = size / 2
    value = f"{liquid:.1f}°" if liquid is not None else "--"
    draw.text((center, center - size * 0.02), value, font=font(int(size * 0.2), True),
              fill=(240, 242, 245), anchor="mm")
    draw.text((center, center - size * 0.2), t("VLOEISTOF"), font=font(int(size * 0.055)),
              fill=accent, anchor="mm")

    parts = []
    if cpu_temp is not None:
        parts.append(f"{cpu_temp:.0f}°")
    if cpu_load is not None:
        parts.append(f"{cpu_load:.0f}%")
    if parts:
        draw.text((center, center + size * 0.18), "CPU  " + "  ·  ".join(parts),
                  font=font(int(size * 0.07)), fill=(170, 176, 186), anchor="mm")

    if rotation:
        image = image.rotate(-rotation)
    return image
