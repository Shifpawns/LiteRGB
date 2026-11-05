from effects import hex_to_rgb
from .base import Device, HidHandle, find_hid, scaled, speed_level

PIDS = {
    0x2001, 0x2002, 0x2006, 0x200D, 0x200F, 0x2009, 0x200E, 0x2010,
    0x2011, 0x2012, 0x2019, 0x201F, 0x2020, 0x2021, 0x2022,
}


MODES = {
    "off": 0x00,
    "static": 0x00,
    "breathing": 0x07,
    "spectrum": 0x02,
    "wave": 0x0B,
    "gradient": 0x01,
}


class NzxtRgbFanController(Device):
    key = "nzxt_rgb_fan"
    name = "NZXT RGB & Fan Controller"

    def __init__(self, info, leds_per_channel):
        super().__init__()
        self.dev = HidHandle(info["path"])
        self.channels = self.read_channel_count()
        self.leds = [min(40, int(n)) for n in leds_per_channel][: self.channels]
        while len(self.leds) < self.channels:
            self.leds.append(40)

        total = sum(self.leds) or 1
        index = 0
        for count in self.leds:
            for _ in range(count):
                self.positions.append(index / total)
                index += 1

    @classmethod
    def detect(cls, config):
        infos = [i for i in find_hid(0x1E71, PIDS) if i["interface_number"] in (-1, 0)]
        leds = config.get("nzxt_leds_per_channel", [40, 40, 40])
        return [cls(infos[0], leds)] if infos else []

    def read_channel_count(self):
        self.dev.drain()
        self.dev.write([0x20, 0x03], 64)
        for _ in range(20):
            packet = self.dev.read(64, 50)
            if len(packet) > 14 and packet[0] == 0x21 and packet[1] == 0x03:
                return max(1, packet[14])
        return 3

    def send(self, colors):
        pos = 0
        for channel, count in enumerate(self.leds):
            grb = []
            for r, g, b in colors[pos:pos + count]:
                grb += [g, r, b]
            pos += count

            packet_number = 0
            while grb:
                chunk, grb = grb[:60], grb[60:]
                self.dev.write([0x22, 0x10 | packet_number, 1 << channel, 0x00] + chunk, 64)
                packet_number += 1

            self.dev.write([0x22, 0xA0, 1 << channel, 0x00, 0x01, 0x00, 0x00, 0x28,
                            0x00, 0x00, 0x80, 0x00, 0x32, 0x00, 0x00, 0x01], 64)
        self.dev.drain()

    def save_to_device(self, effect, colors, brightness):
        kind = effect.get("type", "static")
        color1 = scaled(hex_to_rgb(effect.get("color1", "#ffffff")), brightness)
        color2 = scaled(hex_to_rgb(effect.get("color2", "#ffffff")), brightness)
        if kind == "off":
            color1 = color2 = [0, 0, 0]
        palette = [color1, color2] if kind == "gradient" else [color1]
        grb = []
        for r, g, b in palette:
            grb += [g, r, b]

        for channel in range(self.channels):
            packet = [0x28, 0x03, 1 << channel, 0x28, MODES.get(kind, 0x00),
                      speed_level(effect.get("speed", 1.0), 5), 0x01, 0x00, len(palette), 0x00] + grb
            self.dev.write(packet, 64)
        self.dev.drain()
        self.last_colors = None
        return "opgeslagen"

    def close(self):
        self.dev.close()
