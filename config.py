import copy
import json
import os

FOLDER = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LiteRGB")
PATH = os.path.join(FOLDER, "config.json")

DEFAULTS = {
    "language": "",
    "theme": "system",
    "lights_on": True,
    "brightness": 100,
    "effect": {"type": "wave", "color1": "#00a2ff", "color2": "#ff0080", "speed": 1.0},
    "devices": {},
    "lcd": {
        "mode": "sensors",
        "image": "",
        "brightness": 80,
        "rotation": 0,
        "accent": "#00a2ff",
        "format": "q565",
        "zoom": 1.0,
        "offset_x": 0.0,
        "offset_y": 0.0,
    },
    "lianli_fans_per_channel": [4, 4, 4, 4],
    "nzxt_leds_per_channel": [40, 40, 40],
    "gigabyte_argb_leds": [32, 32, 32],
    "ram_support": True,
    "profiles": {},
}

PROFILE_KEYS = ["lights_on", "brightness", "effect", "devices", "lcd"]


def merge(defaults, saved):
    result = copy.deepcopy(defaults)
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict) and key not in ("devices", "profiles"):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def save(config):
    os.makedirs(FOLDER, exist_ok=True)
    temp = PATH + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.replace(temp, PATH)


def save_profile(config, name):
    config["profiles"][name] = copy.deepcopy({k: config[k] for k in PROFILE_KEYS})


def load_profile(config, name):
    profile = config["profiles"].get(name)
    if profile:
        for key in PROFILE_KEYS:
            if key in profile:
                config[key] = copy.deepcopy(profile[key])
