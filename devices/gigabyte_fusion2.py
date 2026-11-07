import struct

from effects import hex_to_rgb
from .base import Device, HidHandle, find_hid, pause, speed_level

REPORT_ID = 0xCC
PIDS = {0x5711, 0x5702, 0x8297, 0x8950}

SINGLE_LEDS = [2, 4]
HEADERS = [
    (5, 0x58, 0x01),
    (6, 0x59, 0x02),
    (7, 0x62, 0x08),
]

EFFECTS = {
    "off": 1,
    "static": 1,
    "breathing": 2,
    "spectrum": 4,
    "wave": 4,
    "gradient": 2,
}

DEFAULT_ORDER = (1, 0, 2)


def count_enum(count):
    for limit, value in ((32, 0), (64, 1), (256, 2), (512, 3)):
        if count <= limit:
            return value
    return 4


def byte_order(value):
    b = value & 0xFF
    g = (value >> 8) & 0xFF
    r = (value >> 16) & 0xFF
    if value >> 24 or len({r, g, b}) != 3 or max(r, g, b) > 2:
        return DEFAULT_ORDER
    return r, g, b


class GigabyteFusion2(Device):
    key = "gigabyte_fusion2"
    name = "Gigabyte RGB Fusion"

    def __init__(self, info, header_leds):
        super().__init__()
        self.pid = info["product_id"]
        self.dev = HidHandle(info["path"])
        self.leds = [max(0, int(n)) for n in header_leds][:3]
        while len(self.leds) < 3:
            self.leds.append(0)
        self.orders = [DEFAULT_ORDER] * 3
        self.direct = False

        self.read_info()
        self.reset()
        self.cc(0x34, (count_enum(self.leds[1]) << 4) | count_enum(self.leds[0]), count_enum(self.leds[2]))

        total = len(SINGLE_LEDS) + sum(self.leds)
        self.positions = [i / max(1, total - 1) for i in range(total)]

    @classmethod
    def detect(cls, config):
        infos = find_hid(0x048D, PIDS, usage_page=0xFF89, usage=0xCC)
        leds = config.get("gigabyte_argb_leds", [32, 32, 32])
        return [cls(infos[0], leds)] if infos else []

    def cc(self, a, b=0, c=0):
        self.dev.send_feature([REPORT_ID, a, b, c], 64)

    def read_info(self):
        self.cc(0x60)
        report = self.dev.get_feature(REPORT_ID, 64)
        if len(report) < 64:
            return
        flags = report[11]
        strip0, strip1 = struct.unpack_from("<II", bytes(report), 44)
        self.orders[0] = byte_order(strip0)
        self.orders[1] = byte_order(strip1)
        if flags & 0x02:
            self.cc(0x48, 0)
        if self.pid == 0x5711:
            self.cc(0x61)
            extra = self.dev.get_feature(REPORT_ID, 64)
            if len(extra) >= 20:
                self.orders[2] = byte_order(struct.unpack_from("<I", bytes(extra), 4)[0])

    def reset(self):
        for reg in range(0x20, 0x28):
            self.cc(reg)
        if self.pid == 0x5711:
            for reg in range(0x90, 0x93):
                self.cc(reg)
        self.cc(0x28, 0xFF, 0x07 if self.pid == 0x5711 else 0x00)
        self.cc(0x31, 0)

    def effect_packet(self, led, mode, color, speed=0, brightness=255):
        packet = [0] * 64
        packet[0] = REPORT_ID
        packet[1] = 0x20 + led
        packet[2:6] = list(struct.pack("<I", 1 << led))
        packet[11] = mode
        packet[12] = brightness
        r, g, b = color
        packet[14:18] = [b, g, r, 0]
        if mode == 2:
            period = 400 + speed * 100 if speed <= 6 else 1000 + (speed - 6) * 200
            packet[22:28] = list(struct.pack("<HHH", period, period, 200))
        elif mode == 4:
            period = speed * 100 + 300 + (1300 * (speed - 8) if speed > 8 else 0)
            packet[22:26] = list(struct.pack("<HH", period, period - 200))
            packet[30] = 7
        self.dev.send_feature(packet, 64)
        return 1 << led

    def apply(self, mask):
        self.dev.send_feature([REPORT_ID, 0x28] + list(struct.pack("<II", mask, 0)), 64)

    def strip(self, header, order, colors):
        offset = 0
        while colors:
            chunk, colors = colors[:19], colors[19:]
            packet = [0] * 64
            packet[0] = REPORT_ID
            packet[1] = header
            packet[2:4] = list(struct.pack("<H", offset))
            packet[4] = len(chunk) * 3
            for i, (r, g, b) in enumerate(chunk):
                base = 5 + i * 3
                packet[base + order[0]] = r
                packet[base + order[1]] = g
                packet[base + order[2]] = b
            offset += len(chunk) * 3
            self.dev.send_feature(packet, 64)

    def set_direct(self, enabled):
        mask = 0
        for (_, _, bit), count in zip(HEADERS, self.leds):
            if count:
                mask |= bit
        self.cc(0x32, mask if enabled else 0)
        pause(50)
        self.direct = enabled

    def send(self, colors):
        if not self.direct:
            self.set_direct(True)
        mask = 0
        for led, color in zip(SINGLE_LEDS, colors):
            mask |= self.effect_packet(led, 1, color)
        pos = len(SINGLE_LEDS)
        for (_, header, _), count, order in zip(HEADERS, self.leds, self.orders):
            if count:
                self.strip(header, order, colors[pos:pos + count])
            pos += count
        self.apply(mask)

    def save_to_device(self, effect, colors, brightness):
        kind = effect.get("type", "static")
        mode = EFFECTS.get(kind, 1)
        color = (0, 0, 0) if kind == "off" else hex_to_rgb(effect.get("color1", "#ffffff"))
        speed = 9 - speed_level(effect.get("speed", 1.0), 10)
        level = int(brightness * 255 / 100)

        self.set_direct(False)
        mask = 0
        for led in SINGLE_LEDS + [h[0] for h, n in zip(HEADERS, self.leds) if n]:
            mask |= self.effect_packet(led, mode, color, speed, level)
        self.apply(mask)
        pause(20)
        self.cc(0x47, 1)
        pause(20)
        self.cc(0x5E, 0)
        pause(50)
        self.last_colors = None
        return "opgeslagen"

    def blackout(self):
        self.save_to_device({"type": "off"}, None, 0)

    def close(self):
        self.dev.close()
