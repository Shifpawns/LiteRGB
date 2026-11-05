import logging
import os
import threading
import time

import lcd
from .base import Device, HidHandle, find_hid

RESOLUTIONS = {0x300C: 640, 0x300E: 240, 0x3014: 240}
BULK_HEADER = [0x12, 0xFA, 0x01, 0xE8, 0xAB, 0xCD, 0xEF, 0x98, 0x76, 0x54, 0x32, 0x10]



class KrakenElite(Device):
    key = "nzxt_kraken"
    name = "NZXT Kraken Elite"

    def __init__(self, info):
        super().__init__()
        self.pid = info["product_id"]
        self.size = RESOLUTIONS[self.pid]
        self.dev = HidHandle(info["path"])
        self.lock = threading.Lock()
        self.status = {}
        self.bulk = None
        self.lcd_thread = None
        self.running = False
        self.brightness = None
        self.orientation = 0
        self.in_liquid_mode = False
        self.media_key = None
        self.media = []
        self.media_index = 0
        self.next_frame = 0.0

        with self.lock:
            self.dev.drain()
            self.dev.write([0x70, 0x02, 0x01, 0xB8, 0x01], 64)
            self.dev.write([0x70, 0x01], 64)

    @classmethod
    def detect(cls, config):
        infos = find_hid(0x1E71, set(RESOLUTIONS))
        infos.sort(key=lambda i: i["interface_number"] != 1)
        return [cls(infos[0])] if infos else []

    def parse(self, packet):
        if len(packet) > 25 and packet[0] == 0x75:
            liquid = packet[15] + packet[16] / 10
            if packet[15] != 0xFF:
                self.status["liquid"] = liquid
            self.status["pump_rpm"] = packet[18] << 8 | packet[17]
            self.status["pump_duty"] = packet[19]
            self.status["fan_rpm"] = packet[24] << 8 | packet[23]
            self.status["fan_duty"] = packet[25]
        elif len(packet) > 0x1A and packet[0] == 0x31 and packet[1] == 0x01:
            self.brightness = packet[0x18]
            self.orientation = packet[0x1A]

    def read_until(self, first, second, timeout=0.2):
        end = time.time() + timeout
        while time.time() < end:
            packet = self.dev.read(64, 20)
            if not packet:
                continue
            self.parse(packet)
            if packet[0] == first and (second is None or packet[1] == second):
                return packet
        return None

    def tick(self, engine):
        with self.lock:
            self.dev.write([0x74, 0x01], 64)
            self.read_until(0x75, None)

    def set_lcd_brightness(self, value):
        with self.lock:
            self.dev.write([0x30, 0x01], 64)
            self.read_until(0x31, 0x01)
            self.dev.write([0x30, 0x02, 0x01, int(value), 0x00, 0x00, 0x01, self.orientation], 64)
            self.brightness = int(value)

    def liquid_mode(self):
        with self.lock:
            self.dev.write([0x38, 0x01, 0x02, 0x00], 64)
            self.read_until(0x39, None, 0.1)
        self.in_liquid_mode = True

    def open_bulk(self):
        import usb.core
        import usb.util
        try:
            import libusb_package
            backend = libusb_package.get_libusb1_backend()
        except ImportError:
            backend = None

        device = usb.core.find(idVendor=0x1E71, idProduct=self.pid, backend=backend)
        if device is None:
            raise OSError("Kraken bulk interface not found")
        config = device.get_active_configuration()
        for interface in config:
            for endpoint in interface:
                if endpoint.bEndpointAddress == 0x02:
                    usb.util.claim_interface(device, interface.bInterfaceNumber)
                    self.bulk = device
                    return
        raise OSError("Kraken bulk endpoint 0x02 not found")

    def push_frame(self, data, fmt):
        if self.bulk is None:
            self.open_bulk()
        with self.lock:
            self.dev.drain()
            self.dev.write([0x36, 0x01, 0x00, 0x01, fmt], 64)
            self.read_until(0x37, 0x01, 0.05)
            try:
                header = BULK_HEADER + [fmt, 0x00, 0x00, 0x00] + list(len(data).to_bytes(4, "little"))
                self.bulk.write(0x02, bytes(header), 1000)
                self.bulk.write(0x02, data, 3000)
            finally:
                self.dev.write([0x36, 0x02], 64)
                self.read_until(0x37, 0x02, 0.05)
        self.in_liquid_mode = False

    def start_lcd(self, engine):
        self.running = True
        self.lcd_thread = threading.Thread(target=self.lcd_loop, args=(engine,), daemon=True)
        self.lcd_thread.start()

    def lcd_loop(self, engine):
        with self.lock:
            self.dev.drain()
            self.dev.write([0x36, 0x03], 64)
            self.read_until(0x37, 0x03, 0.1)

        while self.running:
            try:
                self.lcd_step(engine)
            except Exception as error:
                logging.warning("Kraken LCD: %s", error)
                self.bulk = None
                time.sleep(3)

    def lcd_step(self, engine):
        settings = engine.config["lcd"]
        if settings.get("brightness") != self.brightness:
            self.set_lcd_brightness(settings.get("brightness", 80))

        mode = settings.get("mode", "sensors")
        fmt = lcd.FORMAT_RGB565 if settings.get("format") == "rgb565" else lcd.FORMAT_Q565
        rotation = int(settings.get("rotation", 0))

        if mode == "liquid":
            if not self.in_liquid_mode:
                self.liquid_mode()
            time.sleep(0.3)
            return

        if mode == "image" and settings.get("image") and os.path.exists(settings["image"]):
            key = (settings["image"], rotation, fmt)
            if key != self.media_key:
                self.media = lcd.load_media(settings["image"], self.size, rotation, fmt)
                self.media_key = key
                self.media_index = 0
            data, duration = self.media[self.media_index % len(self.media)]
            if len(self.media) == 1:
                duration = 2.0
            self.media_index += 1
            self.wait_and_push(data, fmt, duration)
            return

        sensors = engine.sensors
        image = lcd.sensor_frame(self.size, rotation, self.status.get("liquid"),
                                 sensors.cpu_temp, sensors.cpu_load, settings.get("accent", "#00a2ff"))
        self.wait_and_push(lcd.encode(image, fmt), fmt, 1.0)

    def wait_and_push(self, data, fmt, duration):
        delay = self.next_frame - time.time()
        if delay > 0:
            time.sleep(min(delay, 2.0))
        self.next_frame = time.time() + duration
        self.push_frame(data, fmt)

    def close(self):
        self.running = False
        if self.lcd_thread:
            self.lcd_thread.join(timeout=3)
        try:
            self.liquid_mode()
        except Exception:
            pass
        if self.bulk is not None:
            try:
                import usb.util
                usb.util.dispose_resources(self.bulk)
            except Exception:
                pass
        self.dev.close()
