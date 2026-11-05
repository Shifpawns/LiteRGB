from effects import hex_to_rgb
from .base import Device, HidHandle, find_hid, pause, speed_level

KEYS = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 17, 18, 20, 21, 24, 25, 26, 27, 28, 29, 30,
    31, 32, 33, 36, 37, 38, 39, 40, 42, 43, 44, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 60, 61,
    62, 63, 64, 66, 67, 68, 69, 72, 73, 74, 75, 76, 78, 79, 80, 81, 84, 85, 86, 87, 88, 89, 90,
    91, 92, 93, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 108, 109, 110, 111, 112, 113, 115,
    116, 117, 120, 121, 122, 123, 124, 126, 127, 128, 129, 132, 133, 134, 135, 136, 137, 139,
    140, 141, 16, 114, 10, 22, 34, 46, 58, 70, 125, 144, 145, 146, 158, 160, 147, 148, 149, 150,
    151, 152, 153, 154, 155, 159, 162, 161, 156, 157,
]

NA = None
MATRIX = [
    [NA, NA, NA, 119, 107, 8, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, NA, 16, NA, NA, NA],
    [113, 0, NA, 10, 18, 28, 36, NA, 46, 55, 64, 74, NA, 84, 93, 102, 6, 15, 24, 33, 26, 35, 44, 53],
    [114, 1, 11, 19, 29, 37, 47, 56, 65, 75, 85, 94, NA, 103, 7, 25, NA, 42, 51, 60, 62, 72, 82, 91],
    [115, 2, NA, 12, 20, 30, 38, NA, 48, 57, 66, 76, 86, 95, 104, 70, 80, 34, 43, 52, 9, 17, 27, 100],
    [116, 3, NA, 13, 21, 31, 39, NA, 49, 58, 67, 77, 87, 96, 105, 98, 112, NA, NA, NA, 45, 54, 63, NA],
    [117, 4, 111, 22, 32, 40, 50, NA, 59, NA, 68, 78, 88, 97, 106, 61, NA, NA, 81, NA, 73, 83, 92, 109],
    [118, 5, 14, 23, NA, NA, NA, NA, 41, NA, NA, NA, NA, 69, 79, 89, 71, 90, 99, 108, 101, NA, 110, NA],
]

SKIP_ANSI = [0x31, 0x3F, 0x41, 0x42, 0x51, 0x53, 0x55, 0x6F, 0x7E, 0x7F, 0x80, 0x81]
SKIP_ISO = [0x3F, 0x41, 0x42, 0x50, 0x53, 0x55, 0x6F, 0x78, 0x7E, 0x7F, 0x80, 0x81]

HW_MODES = {
    "off": (0x00, 3),
    "static": (0x00, 3),
    "breathing": (0x01, 3),
    "spectrum": (0x00, 1),
    "wave": (0x03, 0),
    "gradient": (0x04, 3),
}

KEY_COUNT = 120
BAR_COUNT = 19


class CorsairK95Platinum(Device):
    key = "corsair_k95_platinum"
    name = "Corsair K95 RGB Platinum"

    def __init__(self, info):
        super().__init__()
        self.dev = HidHandle(info["path"])

        columns = {}
        for row in MATRIX:
            for x, index in enumerate(row):
                if index is not None:
                    columns[index] = x
        self.positions = [columns[i] / 23 for i in range(KEY_COUNT)]
        self.positions += [i / (BAR_COUNT - 1) for i in range(BAR_COUNT)]

        self.iso = self.read_layout() == 0x01
        self.software_mode()

    @classmethod
    def detect(cls, config):
        infos = find_hid(0x1B1C, {0x1B2D, 0x1B82}, interface=1, usage_page=0xFFC2)
        return [cls(infos[0])] if infos else []

    def read_layout(self):
        for _ in range(5):
            self.dev.write([0x00, 0x0E, 0x01], 65)
            packet = self.dev.read(65, 500)
            if len(packet) > 0x17 and packet[0x14] == 0xC0:
                return packet[0x17]
        return 0x00

    def software_mode(self):
        self.dev.write([0x00, 0x07, 0x04, 0x02], 65)
        self.dev.write([0x00, 0x07, 0x05, 0x02, 0x00, 0x03], 65)
        self.dev.write([0x00, 0x07, 0x05, 0x08, 0x00, 0x01], 65)

        skipped = SKIP_ISO if self.iso else SKIP_ANSI
        identifier = 0
        for _ in range(4):
            packet = [0x00, 0x07, 0x40, 0x1E, 0x00]
            for _ in range(30):
                while identifier in skipped:
                    identifier += 1
                packet += [identifier, 0xC0]
                identifier += 1
            self.dev.write(packet, 65)

    def send(self, colors):
        red = [0] * 168
        green = [0] * 168
        blue = [0] * 168
        for i, (r, g, b) in enumerate(colors[: len(KEYS)]):
            red[KEYS[i]] = r
            green[KEYS[i]] = g
            blue[KEYS[i]] = b

        for channel, values in ((1, red), (2, green), (3, blue)):
            self.dev.write([0x00, 0x7F, 0x01, 60, 0x00] + values[0:60], 65)
            self.dev.write([0x00, 0x7F, 0x02, 60, 0x00] + values[60:120], 65)
            self.dev.write([0x00, 0x7F, 0x03, 48, 0x00] + values[120:168], 65)
            self.dev.write([0x00, 0x07, 0x28, channel, 0x03, 2 if channel == 3 else 1], 65)
        pause(1)

    def save_to_device(self, effect, colors, brightness):
        kind = effect.get("type", "static")
        mode, color_mode = HW_MODES.get(kind, (0x00, 3))
        color1 = list(hex_to_rgb(effect.get("color1", "#ffffff")))
        color2 = list(hex_to_rgb(effect.get("color2", "#ffffff")))
        if kind == "off":
            color1 = color2 = [0, 0, 0]
        elif kind in ("static", "breathing"):
            color2 = color1

        speed = 1 + speed_level(effect.get("speed", 1.0), 3)
        direction = 1 if kind in ("wave", "gradient") else 0
        level = round(brightness / 100 * 3)

        self.dev.write([0x00, 0x07, 0x05, 0x02, 0x00, level], 65)
        self.dev.write([0x00, 0x07, 0x17, 0x05, 0x00] + list(b"lght_00.d"), 65)
        packet = [0x00, 0x7F, 0x01, 0x0D, 0x00, mode, speed, color_mode, direction]
        if color_mode == 3:
            packet += color1 + [0xFF] + color2 + [0xFF]
        self.dev.write(packet, 65)
        self.dev.write([0x00, 0x07, 0x17, 0x09], 65)
        self.dev.write([0x00, 0x07, 0x17, 0x08], 65)
        pause(50)
        self.software_mode()
        self.last_colors = None
        return "opgeslagen (experimenteel)"

    def close(self):
        try:
            self.dev.write([0x00, 0x07, 0x04, 0x01], 65)
        except Exception:
            pass
        self.dev.close()
