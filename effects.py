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

    scale = brightness / 100
    return [(int(r * scale), int(g * scale), int(b * scale)) for r, g, b in colors]
