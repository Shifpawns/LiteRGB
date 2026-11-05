import colorsys
import math

EFFECTS = {
    "off": "Uit",
    "static": "Statisch",
    "breathing": "Ademen",
    "spectrum": "Kleurcyclus",
    "wave": "Regenboog golf",
    "gradient": "Verloop",
}


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def hue(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, 1.0)
    return r * 255, g * 255, b * 255


def saturate(color, saturation):
    gray = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    return tuple(gray + (c - gray) * saturation for c in color)


def saturate_hex(value, saturation):
    r, g, b = saturate(hex_to_rgb(value), saturation)
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def with_saturation(effect):
    saturation = effect.get("saturation", 100) / 100
    if saturation >= 1:
        return effect
    effect = dict(effect)
    for key in ("color1", "color2"):
        if key in effect:
            effect[key] = saturate_hex(effect[key], saturation)
    return effect


def mix(a, b, amount):
    return tuple(x + (y - x) * amount for x, y in zip(a, b))


def render(effect, positions, t, brightness):
    kind = effect.get("type", "static")
    speed = float(effect.get("speed", 1.0))
    color1 = hex_to_rgb(effect.get("color1", "#00a2ff"))
    color2 = hex_to_rgb(effect.get("color2", "#ff0080"))

    if kind == "off":
        colors = [(0, 0, 0)] * len(positions)
    elif kind == "static":
        colors = [color1] * len(positions)
    elif kind == "breathing":
        level = 0.5 - 0.5 * math.cos(t * speed * math.pi * 0.5)
        colors = [mix((0, 0, 0), color1, level)] * len(positions)
    elif kind == "spectrum":
        colors = [hue(t * speed * 0.05)] * len(positions)
    elif kind == "wave":
        colors = [hue(x - t * speed * 0.2) for x in positions]
    else:
        colors = [mix(color1, color2, 0.5 + 0.5 * math.sin((x - t * speed * 0.2) * math.tau))
                  for x in positions]

    saturation = effect.get("saturation", 100) / 100
    if saturation < 1:
        colors = [saturate(c, saturation) for c in colors]

    scale = brightness / 100
    return [(int(r * scale), int(g * scale), int(b * scale)) for r, g, b in colors]
