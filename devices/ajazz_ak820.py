import logging

from effects import hex_to_rgb
from .base import Device, HidHandle, find_hid, pause, speed_level

MODES = {
    "off": (0x00, 0, 0),
    "static": (0x01, 0, 0),
    "breathing": (0x07, 0, 0),
    "spectrum": (0x08, 1, 0),
    "wave": (0x10, 1, 3),
    "gradient": (0x0B, 0, 3),
}


class AjazzAK820(Device):
    key = "ajazz_ak820"
    name = "Ajazz AK820 Pro"
    hardware_only = True
    static_mode = None

    def __init__(self, info, kind):
        super().__init__()
        self.dev = HidHandle(info["path"])
        self.kind = kind

    @classmethod
    def detect(cls, config):
        cls.static_mode = config.get("ajazz_static_mode")
        dongle = find_hid(0x0C45, {0xFDFD}, usage_page=0xFF60)
        infos = []
        for info in find_hid(0x0C45, {0x8009, 0x800A}):
            name = (info.get("product_string") or "").upper()
            if info["product_id"] == 0x800A and "AK820" not in name:
                continue
            infos.append(info)
        pages = {i["usage_page"] for i in infos}
        if 0xFF13 in pages and 0xFF67 not in pages:
            control = [i for i in infos if i["usage_page"] == 0xFF13]
            return [cls(control[0], "legacy")]
        control = [i for i in infos if i["usage_page"] == 0xFF68]
        if control:
            return [cls(control[0], "web")]
        return [cls(dongle[0], "dongle")] if dongle else []

    def apply_effect(self, effect, brightness):
        kind = effect.get("type", "static")
        mode, color_mode, direction = MODES.get(kind, MODES["static"])
        r, g, b = hex_to_rgb(effect.get("color1", "#ffffff"))
        sr, sg, sb = hex_to_rgb(effect.get("color2", "#000000"))
        level = round(brightness / 20)
        speed = speed_level(effect.get("speed", 1.0), 6)

        if kind == "static":
            speed = 0
            if self.static_mode is not None:
                mode, speed = self.static_mode
            kind = "custom"
        return self.send_raw(kind, mode, (r, g, b), (sr, sg, sb), color_mode, level, speed, direction)

    def send_raw(self, kind, mode, color, color2, color_mode, level, speed, direction):
        logging.info("AK820 %s: effect %02X speed %d brightness %d", self.kind, mode, speed, level)
        if self.kind == "legacy":
            self.apply_legacy(kind, mode, color, color_mode, level, speed, direction)
            return True
        if self.kind == "dongle":
            return self.apply_dongle(kind, mode, color, color_mode, level, speed, direction)
        payload = [mode, *color, 0xFF, *color2, color_mode, level, speed, direction, 0, 0, 0xAA, 0x55]
        self.dev.write([0x00, 0xAA, 0x23, len(payload), 0x00, 0x00, 0x00, 0x01, 0x00] + payload, 65)
        self.dev.read(64, 200)
        return True

    def apply_dongle(self, kind, mode, color, color_mode, level, speed, direction):
        data = [mode, *color, 0, 0, 0, 0, 1 if color_mode else 0, level, speed, direction, 0, 0, 0xAA, 0x55]
        frame = [0x05, len(data), 0x00] + data
        frame += [0] * (31 - len(frame))
        frame.append(sum(frame) & 0xFF)

        for _ in range(3):
            self.dev.write([0x00] + frame, 33)
            pause(5)
            for _ in range(20):
                reply = self.dev.read(64, 10)
                if reply and list(reply[:3]) == frame[:3]:
                    return True
        logging.info("AK820 receiver did not answer, keyboard may be asleep")
        return False

    def exchange(self, packet):
        pause(35)
        self.dev.send_feature([0x00] + packet, 65)
        pause(50)
        reply = self.dev.get_feature(0x00, 65)
        return reply[1:] if len(reply) == 65 else reply

    def command(self, command, sub=0, flag=0):
        packet = [0] * 64
        packet[0:3] = [0x04, command, sub]
        packet[8] = flag
        return packet

    def ack(self, reply, command):
        if len(reply) < 4 or reply[0] != 0x04 or reply[1] != command or reply[3] != 0x01:
            raise OSError(f"AK820 rejected command {command:02x}")

    def apply_legacy(self, kind, mode, color, color_mode, level, speed, direction):
        if kind == "off":
            mode, level, speed = 0x02, 0, 0

        data = [0] * 64
        data[0] = mode
        data[1:4] = list(color)
        data[8] = 1 if color_mode else 0
        data[9] = level
        data[10] = speed
        data[11] = direction
        data[14:16] = [0x55, 0xAA]

        try:
            for _ in range(10):
                reply = self.exchange(self.command(0x18, 0, 1))
                if any(reply) and reply[:4] != [4, 0x18, 0, 0xFF]:
                    break
                pause(300)
            self.ack(reply, 0x18)
            self.ack(self.exchange(self.command(0x13, 0, 1)), 0x13)
            self.exchange(data)
            self.ack(self.exchange(self.command(0x02, 0, 0)), 0x02)
        finally:
            try:
                self.exchange(self.command(0xF0, 0, 1))
            except Exception as error:
                logging.warning("AK820 finish failed: %s", error)

    def save_to_device(self, effect, colors, brightness):
        if self.apply_effect(effect, brightness) is False:
            return "toetsenbord slaapt, druk op een toets en probeer opnieuw"
        return "opgeslagen"

    def close(self):
        self.dev.close()
