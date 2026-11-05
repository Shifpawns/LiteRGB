import logging
import threading
import time

import effects
from devices.aerox import SteelSeriesAerox9
from devices.ajazz_ak820 import AjazzAK820
from devices.corsair_dram import CorsairDram
from devices.corsair_k95 import CorsairK95Platinum
from devices.dualsense import DualSense
from devices.gigabyte_fusion2 import GigabyteFusion2
from devices.kraken import KrakenElite
from devices.lianli import LianLiSLInfinity
from devices.msi_mystic import MsiMysticLight162
from devices.nzxt_hue2 import NzxtRgbFanController

DRIVERS = [
    KrakenElite,
    NzxtRgbFanController,
    LianLiSLInfinity,
    CorsairK95Platinum,
    SteelSeriesAerox9,
    MsiMysticLight162,
    GigabyteFusion2,
    AjazzAK820,
    DualSense,
    CorsairDram,
]

FPS = 30


class Engine:
    def __init__(self, config, sensors):
        self.config = config
        self.sensors = sensors
        self.devices = {}
        self.errors = {}
        self.running = False
        self.save_request = None

    def start(self):
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()

    def stop(self):
        self.running = False
        time.sleep(0.2)
        for device in list(self.devices.values()):
            try:
                device.close()
            except Exception:
                pass
        self.devices.clear()

    def kraken(self):
        return self.devices.get(KrakenElite.key)

    def effect_for(self, key):
        settings = self.config["devices"].get(key, {})
        if not self.config.get("lights_on", True) or not settings.get("enabled", True):
            return {"type": "off"}
        if settings.get("own_effect") and settings.get("effect"):
            return settings["effect"]
        return self.config["effect"]

    def request_save(self, callback):
        self.save_request = callback

    def save_to_devices(self):
        results = []
        brightness = self.config.get("brightness", 100) if self.config.get("lights_on", True) else 0
        for key, device in list(self.devices.items()):
            effect = effects.with_saturation(self.effect_for(key))
            try:
                result = device.save_to_device(effect, device.last_colors or [], brightness)
            except Exception as error:
                logging.warning("Save failed for %s: %s", device.name, error)
                result = f"mislukt ({error})"
            results.append((device.name, result or "niet mogelijk"))
        return results

    def update_hardware(self, key, device, now):
        brightness = self.config.get("brightness", 100)
        wanted = (repr(self.effect_for(key)), brightness)
        if wanted == device.applied:
            device.pending_since = 0.0
            return
        if not device.pending_since:
            device.pending_since = now
        if now - device.pending_since < 1.0:
            return
        try:
            if device.apply_effect(effects.with_saturation(self.effect_for(key)), brightness) is False:
                device.pending_since = now + 9.0
                return
            device.applied = wanted
            device.pending_since = 0.0
        except Exception as error:
            self.drop(key, error)

    def scan(self):
        for driver in DRIVERS:
            if driver.key in self.devices:
                continue
            try:
                found = driver.detect(self.config)
            except Exception as error:
                self.errors[driver.key] = str(error)
                logging.warning("%s: %s", driver.name, error)
                continue
            for device in found:
                self.devices[driver.key] = device
                self.errors.pop(driver.key, None)
                logging.info("Connected: %s", device.name)
                if isinstance(device, KrakenElite):
                    device.start_lcd(self)

    def drop(self, key, error):
        logging.warning("Lost %s: %s", key, error)
        self.errors[key] = str(error)
        device = self.devices.pop(key, None)
        if device:
            try:
                device.close()
            except Exception:
                pass

    def loop(self):
        self.scan()
        start = time.time()
        last_tick = 0.0
        last_scan = time.time()

        while self.running:
            now = time.time()
            t = now - start

            for key, device in list(self.devices.items()):
                if device.hardware_only:
                    self.update_hardware(key, device, now)
                    continue
                if not device.positions:
                    continue
                colors = effects.render(self.effect_for(key), device.positions, t,
                                        self.config.get("brightness", 100))
                if device.wants_frame(colors, now):
                    try:
                        device.push(colors, now)
                    except Exception as error:
                        self.drop(key, error)

            if self.save_request:
                callback, self.save_request = self.save_request, None
                callback(self.save_to_devices())

            if now - last_tick > 1.0:
                last_tick = now
                for key, device in list(self.devices.items()):
                    try:
                        device.tick(self)
                    except Exception as error:
                        self.drop(key, error)

            if now - last_scan > 5.0:
                last_scan = now
                if len(self.devices) < len(DRIVERS):
                    self.scan()

            time.sleep(max(0.0, 1.0 / FPS - (time.time() - now)))
