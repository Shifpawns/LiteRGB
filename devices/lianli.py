from .base import Device, HidHandle, find_hid, pause

INNER = 8
OUTER = 12


class LianLiSLInfinity(Device):
    key = "lianli_sl_infinity"
    name = "Lian Li Uni Hub SL Infinity"
    max_fps = 20

    def __init__(self, info, fans_per_channel):
        super().__init__()
        self.dev = HidHandle(info["path"])
        self.fans = [max(0, min(4, int(n))) for n in fans_per_channel][:4]
        while len(self.fans) < 4:
            self.fans.append(0)

        total = sum(self.fans) or 1
        index = 0
        for count in self.fans:
            for _ in range(count):
                for led in range(INNER + OUTER):
                    self.positions.append((index + led / (INNER + OUTER)) / total)
                index += 1

        self.dev.send_feature([0xE0, 0x10, 0x61, 0x00], 6)

    @classmethod
    def detect(cls, config):
        fans = config.get("lianli_fans_per_channel", [4, 4, 4, 4])
        infos = find_hid(0x0CF2, {0xA102, 0xA100}, interface=1)
        return [cls(infos[0], fans)] if infos else []

    def send(self, colors):
        pos = 0
        for channel, count in enumerate(self.fans):
            if count == 0:
                continue
            inner = []
            outer = []
            for _ in range(count):
                fan = colors[pos:pos + INNER + OUTER]
                pos += INNER + OUTER
                for r, g, b in fan[:INNER]:
                    inner += [r, b, g]
                for r, g, b in fan[INNER:]:
                    outer += [r, b, g]

            self.dev.write([0xE0, 0x30 | (channel * 2)] + inner, 353)
            pause(1)
            self.dev.write([0xE0, 0x30 | (channel * 2 + 1)] + outer, 353)
            pause(1)
            self.dev.send_feature([0xE0, 0x10 | (channel * 2), 0x01, 0x02], 6)
            pause(1)
            self.dev.send_feature([0xE0, 0x10 | (channel * 2 + 1), 0x01, 0x02], 6)
            pause(1)

    def close(self):
        self.dev.close()
