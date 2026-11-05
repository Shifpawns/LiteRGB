from effects import hex_to_rgb
from .base import Device, HidHandle, find_hid, pause, scaled

PIDS = {0x1858, 0x185A, 0x1876}
WIRED = {0x185A}


class SteelSeriesAerox9(Device):
    key = "steelseries_aerox9"
    name = "SteelSeries Aerox 9"
    max_fps = 15
    refresh_seconds = 5.0

    def __init__(self, infos):
        super().__init__()
        self.handles = [HidHandle(info["path"]) for info in infos]
        self.wireless = [info["product_id"] not in WIRED for info in infos]
        self.positions = [0.0, 0.5, 1.0]

    @classmethod
    def detect(cls, config):
        infos = find_hid(0x1038, PIDS, interface=3, usage_page=0xFFC0, usage=0x0001)
        return [cls(infos)] if infos else []

    def send(self, colors):
        for handle in self.handles:
            for zone, (r, g, b) in enumerate(colors[:3]):
                handle.write([0x00, 0x61, 0x01, zone, r, g, b], 65)
                handle.read(65, 20)

    def save_to_device(self, effect, colors, brightness):
        kind = effect.get("type", "static")
        if kind == "static":
            colors = [scaled(hex_to_rgb(effect.get("color1", "#ffffff")), brightness)] * 3
        elif kind == "off":
            colors = [[0, 0, 0]] * 3

        for handle, wireless in zip(self.handles, self.wireless):
            flag = 0x40 if wireless else 0x00
            if kind in ("spectrum", "wave"):
                handle.write([0x00, 0x22 | flag, 0xFF], 65)
            else:
                for zone, (r, g, b) in enumerate(colors[:3]):
                    handle.write([0x00, 0x21 | flag, 0x01, zone, r, g, b], 65)
                    handle.read(65, 50)
            handle.read(65, 50)
            pause(50)
            handle.write([0x00, 0x11 | flag, 0x00], 65)
            handle.read(65, 200)
        self.last_colors = None
        return "opgeslagen"

    def close(self):
        for handle in self.handles:
            handle.close()
