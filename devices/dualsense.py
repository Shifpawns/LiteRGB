import zlib

from .base import Device, HidHandle, find_hid

PIDS = {0x0CE6, 0x0DF2}


class DualSense(Device):
    key = "sony_dualsense"
    name = "PS5 DualSense"
    refresh_seconds = 5.0

    def __init__(self, info):
        super().__init__()
        self.dev = HidHandle(info["path"])
        self.bluetooth = info["interface_number"] == -1
        self.positions = [0.5]

    @classmethod
    def detect(cls, config):
        infos = find_hid(0x054C, PIDS)
        return [cls(infos[0])] if infos else []

    def send(self, colors):
        r, g, b = colors[0]
        if self.bluetooth:
            buf = [0] * 79
            buf[0:5] = [0xA2, 0x31, 0x02, 0x0F, 0x55]
            buf[41] = 0xFF
            buf[44] = 0x02
            buf[45] = 0x00
            buf[46] = 0x20
            buf[47:50] = [r, g, b]
            crc = zlib.crc32(bytes(buf[:75]))
            packet = buf[1:75] + list(crc.to_bytes(4, "little"))
            self.dev.write(packet, 78)
        else:
            packet = [0] * 48
            packet[0:3] = [0x02, 0x0F, 0x55]
            packet[39] = 0xFF
            packet[43] = 0x00
            packet[44] = 0x20
            packet[45:48] = [r, g, b]
            self.dev.write(packet, 48)

    def close(self):
        self.dev.close()
