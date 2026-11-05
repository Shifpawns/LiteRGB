import time

import hid


def find_hid(vid, pids, interface=None, usage_page=None, usage=None):
    found = []
    for info in hid.enumerate(vid, 0):
        if info["product_id"] not in pids:
            continue
        if interface is not None and info["interface_number"] != interface:
            continue
        if usage_page is not None and info["usage_page"] != usage_page:
            continue
        if usage is not None and info["usage"] != usage:
            continue
        found.append(info)
    return found


class HidHandle:
    def __init__(self, path):
        self.h = hid.device()
        self.h.open_path(path)

    def write(self, data, size):
        buf = list(data) + [0] * (size - len(data))
        if self.h.write(buf) < 0:
            raise OSError("HID write failed")

    def read(self, size, timeout_ms):
        return self.h.read(size, timeout_ms)

    def drain(self):
        while self.h.read(64, 1):
            pass

    def send_feature(self, data, size):
        buf = list(data) + [0] * (size - len(data))
        if self.h.send_feature_report(buf) < 0:
            raise OSError("HID feature report failed")

    def get_feature(self, report_id, size):
        return self.h.get_feature_report(report_id, size)

    def get_input(self, report_id, size):
        return self.h.get_input_report(report_id, size)

    def close(self):
        try:
            self.h.close()
        except Exception:
            pass


class Device:
    key = ""
    name = ""
    max_fps = 30
    hardware_only = False
    refresh_seconds = 2.0

    def __init__(self):
        self.positions = []
        self.last_colors = None
        self.last_send = 0.0
        self.applied = None
        self.pending_since = 0.0

    @classmethod
    def detect(cls):
        return []

    def wants_frame(self, colors, now):
        if now - self.last_send < 1.0 / self.max_fps:
            return False
        if colors == self.last_colors and now - self.last_send < self.refresh_seconds:
            return False
        return True

    def push(self, colors, now):
        self.send(colors)
        self.last_colors = colors
        self.last_send = now

    def send(self, colors):
        pass

    def tick(self, engine):
        pass

    def save_to_device(self, effect, colors, brightness):
        return None

    def apply_effect(self, effect, brightness):
        pass

    def close(self):
        pass


def speed_level(speed, levels):
    share = (float(speed) - 0.1) / 3.9
    return max(0, min(levels - 1, round(share * (levels - 1))))


def scaled(color, brightness):
    return [int(c * brightness / 100) for c in color]


def pause(ms):
    time.sleep(ms / 1000)
