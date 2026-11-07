import os
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageSequence

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


GPU_COLOR = (120, 220, 120)
CPU_COLOR = (255, 140, 60)
WHITE = (245, 247, 250, 255)
DIM = (215, 220, 228, 255)
TRACK = (20, 22, 28, 200)


def temp(value, digits=0):
    return f"{value:.{digits}f}°" if value is not None else "--"


def detail_lines(values):
    lines = []
    for name in ("cpu", "gpu"):
        parts = []
        if values.get(f"{name}_temp") is not None:
            parts.append(temp(values[f"{name}_temp"]))
        if values.get(f"{name}_load") is not None:
            parts.append(f"{values[f'{name}_load']:.0f}%")
        if parts and (name == "cpu" or values.get("gpu_temp") is not None):
            lines.append(name.upper() + "  " + "  ·  ".join(parts))
    return lines


def columns(values, accent):
    result = [(t("VLOEISTOF"), temp(values.get("liquid"), 1), accent)]
    if values.get("cpu_temp") is not None or values.get("cpu_load") is not None:
        result.append(("CPU", temp(values.get("cpu_temp")), CPU_COLOR))
    if values.get("gpu_temp") is not None:
        result.append(("GPU", temp(values.get("gpu_temp")), GPU_COLOR))
    return result


def share(value, low, high):
    if value is None:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def draw_gauge(draw, size, values, accent, background):
    margin = size * 0.06
    width = max(4, int(size * 0.045))
    box = [margin, margin, size - margin, size - margin]
    draw.arc(box, 135, 405, fill=background, width=width)
    part = share(values.get("liquid"), 20, 60)
    if part > 0:
        draw.arc(box, 135, 135 + 270 * part, fill=accent, width=width)

    lines = detail_lines(values)
    center = size / 2
    lift = size * 0.04 if len(lines) > 1 else 0
    draw.text((center, center - size * 0.02 - lift), temp(values.get("liquid"), 1), font=font(int(size * 0.2), True),
              fill=WHITE, anchor="mm")
    draw.text((center, center - size * 0.2 - lift), t("VLOEISTOF"), font=font(int(size * 0.055)),
              fill=accent, anchor="mm")
    small = font(int(size * 0.062 if len(lines) > 1 else size * 0.07))
    for i, line in enumerate(lines):
        draw.text((center, center + size * 0.16 - lift + i * size * 0.085), line, font=small, fill=DIM, anchor="mm")


def sensor_frame(size, rotation, values, accent):
    accent = hex_to_rgb(accent)
    image = Image.new("RGB", (size, size), (8, 10, 14))
    draw_gauge(ImageDraw.Draw(image), size, values, accent, (38, 42, 50))
    if rotation:
        image = image.rotate(-rotation)
    return image


def load_frames(path, size, zoom=1.0, dx=0.0, dy=0.0):
    source = Image.open(path)
    frames = []
    for frame in ImageSequence.Iterator(source):
        duration = frame.info.get("duration", source.info.get("duration", 100)) or 100
        frames.append((fit(frame, size, 0, zoom, dx, dy), max(20, duration) / 1000))
    return frames


def draw_columns(draw, size, items, top, height, width):
    left = (size - width) / 2
    draw.rounded_rectangle([left, top, left + width, top + height], radius=height * 0.4, fill=(8, 10, 14, 185))
    label = font(int(size * 0.035), True)
    value = font(int(size * (0.07 if len(items) > 2 else 0.075)), True)
    step = width / len(items)
    for i, (name, text, color) in enumerate(items):
        x = left + step * (i + 0.5)
        draw.text((x, top + height * 0.28), name, font=label, fill=color + (255,), anchor="mm")
        draw.text((x, top + height * 0.65), text, font=value, fill=WHITE, anchor="mm")
        if i:
            line_x = left + step * i
            draw.line([line_x, top + height * 0.22, line_x, top + height * 0.78], fill=(255, 255, 255, 60),
                      width=max(1, size // 320))


def bar_overlay(size, values, accent, position):
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    items = columns(values, accent)
    width = size * (0.36 + 0.14 * len(items))
    height = size * 0.17
    top = size * 0.12 if position == "top" else size * 0.71
    draw_columns(ImageDraw.Draw(overlay), size, items, top, height, width)
    return overlay


def radial_shade(size, radius, alpha):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([size / 2 - radius, size / 2 - radius, size / 2 + radius, size / 2 + radius],
                                 fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.06))
    shade = Image.new("RGBA", (size, size), (6, 8, 12, 0))
    shade.putalpha(mask)
    return shade


def gauge_overlay(size, values, accent):
    overlay = radial_shade(size, size * 0.36, 170)
    draw_gauge(ImageDraw.Draw(overlay), size, values, accent + (255,), TRACK)
    return overlay


def dual_overlay(size, values, accent):
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    margin = size * 0.05
    width = max(4, int(size * 0.04))
    box = [margin, margin, size - margin, size - margin]
    draw.arc(box, 100, 260, fill=TRACK, width=width)
    draw.arc(box, 280, 440, fill=TRACK, width=width)
    left = share(values.get("liquid"), 20, 60)
    if left:
        draw.arc(box, 100, 100 + 160 * left, fill=accent + (255,), width=width)
    right_value, right_color = values.get("cpu_temp"), CPU_COLOR
    if values.get("gpu_temp") is not None and right_value is None:
        right_value, right_color = values.get("gpu_temp"), GPU_COLOR
    right = share(right_value, 20, 100)
    if right:
        draw.arc(box, 440 - 160 * right, 440, fill=right_color + (255,), width=width)

    items = columns(values, accent)
    if len(items) > 1:
        items[0] = (items[0][0], temp(values.get("liquid")), items[0][2])
    draw_columns(draw, size, items, size * 0.68, size * 0.2, size * (0.3 + 0.15 * len(items)))
    return overlay


def minimal_overlay(size, values, accent, position):
    fade = Image.new("L", (1, 256))
    for y in range(256):
        fade.putpixel((0, y), int(235 * min(1, max(0, (y - 110) / 100)) ** 1.2))
    fade = fade.resize((size, size))
    if position == "top":
        fade = fade.transpose(Image.FLIP_TOP_BOTTOM)
    overlay = Image.new("RGBA", (size, size), (4, 5, 8, 0))
    overlay.putalpha(fade)
    draw = ImageDraw.Draw(overlay)
    center = size / 2
    y = size * 0.24 if position == "top" else size * 0.76
    draw.text((center, y), temp(values.get("liquid"), 1), font=font(int(size * 0.12), True), fill=WHITE,
              anchor="mm", stroke_width=max(1, size // 200), stroke_fill=(0, 0, 0, 120))
    parts = [f"{name} {text}" for name, text, _ in columns(values, accent)[1:]]
    if values.get("gpu_temp") is None and values.get("cpu_load") is not None and parts:
        parts[0] += f"  {values['cpu_load']:.0f}%"
    if parts:
        offset = -size * 0.1 if position == "top" else size * 0.095
        draw.text((center, y + offset), "   ".join(parts), font=font(int(size * 0.05), True),
                  fill=accent + (255,), anchor="mm")
    return overlay


STYLES = ["bar", "gauge", "dual", "minimal"]


def sensor_overlay(size, values, accent, style="bar", position="bottom"):
    accent = hex_to_rgb(accent)
    if style == "gauge":
        return gauge_overlay(size, values, accent)
    if style == "dual":
        return dual_overlay(size, values, accent)
    if style == "minimal":
        return minimal_overlay(size, values, accent, position)
    return bar_overlay(size, values, accent, position)


def compose(frame, overlay, rotation):
    image = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
    return image.rotate(-rotation) if rotation else image
