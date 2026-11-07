import logging

from effects import hex_to_rgb
from .base import Device, HidHandle, find_hid, speed_level

REPORT_SIZE = 162

MODES = {
    "off": (1, False),
    "static": (1, False),
    "breathing": (2, False),
    "spectrum": (22, True),
    "wave": (26, True),
    "gradient": (23, False),
}

ZONES = [
    ("onboard", [41, 51]),
    ("jrgb1", [1]),
    ("jrainbow1", [11]),
    ("jrgb2", [151]),
]


class MsiMysticLight162(Device):
    key = "msi_mystic_light"
    name = "MSI Mystic Light"
    max_fps = 10
    refresh_seconds = 10.0

    def __init__(self, handle, data):
        super().__init__()
        self.dev = handle
        self.data = list(data[:REPORT_SIZE])
        self.positions = [i / (len(ZONES) - 1) for i in range(len(ZONES))]

    @classmethod
    def detect(cls, config):
        for info in find_hid(0x1462, range(0x10000), usage_page=0x0001, usage=0x0000):
            try:
                handle = HidHandle(info["path"])
                data = handle.get_feature(0x52, 200)
            except Exception:
                continue
            if len(data) in (REPORT_SIZE, REPORT_SIZE + 1):
                return [cls(handle, data)]
            logging.info("MSI board found but report length %d is not supported", len(data))
            handle.close()
        return []

    def send(self, colors):
        for (_, offsets), (r, g, b) in zip(ZONES, colors):
            for offset in offsets:
                self.data[offset] = 1
                self.data[offset + 1:offset + 4] = [r, g, b]
                self.data[offset + 4] = 10 << 2
                self.data[offset + 8] = (self.data[offset + 8] | 0x80) & ~0x01
                self.data[offset + 9] = 0
        self.data[0] = 0x52
        self.data[REPORT_SIZE - 1] = 0
        self.dev.send_feature(self.data, REPORT_SIZE)

    def save_to_device(self, effect, colors, brightness):
        kind = effect.get("type", "static")
        mode, rainbow = MODES.get(kind, (1, False))
        color = [0, 0, 0] if kind == "off" else hex_to_rgb(effect.get("color1", "#ffffff"))
        speed = speed_level(effect.get("speed", 1.0), 3)
        level = round(brightness / 10)

        data = list(self.data)
        for _, offsets in ZONES:
            for offset in offsets[:1] if mode > 4 else offsets:
                flags = (level << 2) | speed
                color_flags = data[offset + 8] & ~0x81
                if not rainbow:
                    color_flags |= 0x80
                if mode > 4:
                    flags |= 0x80
                    color_flags |= 0x01
                data[offset] = mode
                data[offset + 1:offset + 4] = list(color)
                data[offset + 4] = flags
                data[offset + 5:offset + 8] = list(color)
                data[offset + 8] = color_flags
                data[offset + 9] = 0
        data[0] = 0x52
        data[REPORT_SIZE - 1] = 1
        self.dev.send_feature(data, REPORT_SIZE)
        self.last_colors = None
        return "opgeslagen"

    def blackout(self):
        self.save_to_device({"type": "off"}, None, 0)

    def close(self):
        self.dev.close()
