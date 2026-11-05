import logging
import os
import sys
import time

from effects import hex_to_rgb
from .base import Device, speed_level
from .smbus import open_dram_buses

MODELS = [
    ("Corsair Vengeance RGB Pro DDR4", {0x0100, 0x0101}, 10, False),
    ("Corsair Dominator Platinum RGB DDR4", {0x0200, 0x0201}, 12, True),
    ("Corsair Vengeance RGB Pro SL DDR4", {0x0300, 0x0301}, 10, False),
    ("Corsair Vengeance RGB RS DDR4", {0x0400, 0x0401}, 6, False),
    ("Corsair Dominator Platinum RGB DDR5", {0x0600, 0x0601}, 12, True),
    ("Corsair Dominator Titanium RGB DDR5", {0x0800, 0x0801, 0x0810, 0x0811}, 12, True),
    ("Corsair Vengeance RGB DDR5", {0x0700, 0x0701, 0x0900, 0x0901, 0x0910, 0x0911}, 10, False),
    ("Corsair Vengeance Shugo Series DDR5", {0x0A00, 0x0A01, 0x0A10, 0x0A11}, 10, False),
    ("Corsair Vengeance RGB RS DDR5", {0x0B00, 0x0B01}, 6, False),
]

ADDRESSES = list(range(0x58, 0x60)) + list(range(0x18, 0x20))

EFFECTS = {
    "off": (0x10, False),
    "static": (0x10, False),
    "breathing": (0x01, False),
    "spectrum": (0x00, True),
    "wave": (0x03, True),
    "gradient": (0x04, False),
}


def crc8(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def lib_folder():
    candidates = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")]
    if getattr(sys, "frozen", False):
        candidates = [os.path.join(getattr(sys, "_MEIPASS", ""), "lib"),
                      os.path.join(os.path.dirname(sys.executable), "lib")]
    for folder in candidates:
        if os.path.isdir(os.path.join(folder, "pawnio")):
            return folder
    return candidates[0]


class Stick:
    def __init__(self, bus, addr):
        self.bus = bus
        self.addr = addr
        self.name = "Corsair DRAM"
        self.leds = 10
        self.reverse = False
        self.protocol = 0
        self.read_info()

    def read_info(self):
        self.bus.write_byte(self.addr, 0x61, 0x00)
        self.bus.write_byte(self.addr, 0x21, 0x00)
        info = [self.bus.read_byte(self.addr, 0x40) for _ in range(32)]
        pid = (info[3] << 8) | info[2]
        self.protocol = info[28]
        for name, pids, leds, reverse in MODELS:
            if pid in pids:
                self.name, self.leds, self.reverse = name, leds, reverse

    def wait_ready(self):
        for _ in range(5):
            if not self.bus.read_byte(self.addr, 0x30) & 0x08:
                return
            time.sleep(0.01)

    def write_buffer(self, buffer_id, data):
        self.bus.write_byte(self.addr, 0x0B, 0x00)
        self.bus.write_byte(self.addr, 0x21, 0x00)
        for value in data:
            self.bus.write_byte(self.addr, 0x20, value)
        if self.bus.read_byte(self.addr, 0x42) == crc8(data):
            self.bus.write_byte(self.addr, 0x82, buffer_id)
            self.wait_ready()

    def set_colors(self, colors):
        if self.reverse:
            colors = colors[::-1]
        if self.protocol >= 4:
            packet = [self.leds]
            for r, g, b in colors:
                packet += [r, g, b]
            packet.append(crc8(packet))
            self.bus.write_block(self.addr, 0x31, packet[:32])
            if len(packet) > 32:
                self.bus.write_block(self.addr, 0x32, packet[32:])
        else:
            data = []
            for r, g, b in colors:
                data += [r, g, b, 0xFF]
            self.write_buffer(2, data)

    def set_effect(self, mode, speed, random, direction, brightness, color1, color2):
        data = [mode, speed, 0 if random else 1, direction, *color1, brightness, *color2, brightness] + [0] * 8
        self.write_buffer(1, data)


class CorsairDram(Device):
    key = "corsair_dram"
    name = "Corsair RGB RAM"
    max_fps = 15
    scanned = False

    def __init__(self, sticks):
        super().__init__()
        self.sticks = sticks
        self.name = sticks[0].name
        total = sum(s.leds for s in sticks)
        self.positions = [i / max(1, total - 1) for i in range(total)]

    @classmethod
    def detect(cls, config):
        if cls.scanned or not config.get("ram_support", True) or sys.platform != "win32":
            return []
        cls.scanned = True
        sticks = []
        for bus in open_dram_buses(lib_folder()):
            for addr in ADDRESSES:
                try:
                    if bus.read_byte(addr, 0x43) in (0x1A, 0x1B, 0x1C) and \
                            bus.read_byte(addr, 0x44) in (0x01, 0x03, 0x04):
                        sticks.append(Stick(bus, addr))
                except OSError:
                    pass
                time.sleep(0.01)
        if sticks:
            logging.info("Found %d Corsair RAM sticks", len(sticks))
        return [cls(sticks)] if sticks else []

    def send(self, colors):
        pos = 0
        for stick in self.sticks:
            stick.set_colors(colors[pos:pos + stick.leds])
            pos += stick.leds

    def save_to_device(self, effect, colors, brightness):
        kind = effect.get("type", "static")
        mode, random = EFFECTS.get(kind, EFFECTS["static"])
        color1 = (0, 0, 0) if kind == "off" else hex_to_rgb(effect.get("color1", "#ffffff"))
        color2 = color1 if kind in ("static", "breathing", "off") else hex_to_rgb(effect.get("color2", "#ffffff"))
        speed = speed_level(effect.get("speed", 1.0), 3)
        level = int(brightness * 255 / 100)
        for stick in self.sticks:
            stick.set_effect(mode, speed, random, 1, level, color1, color2)
        self.last_colors = None
        return "opgeslagen"
