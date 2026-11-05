import logging
import os
import threading
import time

import psutil


class Sensors:
    def __init__(self, lib_folder):
        self.cpu_load = None
        self.cpu_temp = None
        self.computer = None
        self.cpu_hardware = []
        self.load_lhm(os.path.join(lib_folder, "LibreHardwareMonitorLib.dll"))
        psutil.cpu_percent(None)
        threading.Thread(target=self.loop, daemon=True).start()

    def load_lhm(self, dll):
        if not os.path.exists(dll):
            return
        try:
            import clr
            clr.AddReference(dll)
            from LibreHardwareMonitor.Hardware import Computer, HardwareType
            computer = Computer()
            computer.IsCpuEnabled = True
            computer.Open()
            self.cpu_hardware = [h for h in computer.Hardware if h.HardwareType == HardwareType.Cpu]
            self.computer = computer
        except Exception as error:
            logging.warning("LibreHardwareMonitor not available: %s", error)

    def read_cpu_temp(self):
        best = None
        for hardware in self.cpu_hardware:
            hardware.Update()
            for sensor in hardware.Sensors:
                if str(sensor.SensorType) != "Temperature" or sensor.Value is None:
                    continue
                name = str(sensor.Name)
                if "Package" in name or "Tctl" in name or "Tdie" in name:
                    return float(sensor.Value)
                if best is None or float(sensor.Value) > best:
                    best = float(sensor.Value)
        return best

    def loop(self):
        while True:
            self.cpu_load = psutil.cpu_percent(None)
            if self.computer is not None:
                try:
                    self.cpu_temp = self.read_cpu_temp()
                except Exception:
                    self.cpu_temp = None
            time.sleep(1)
