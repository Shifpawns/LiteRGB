import logging
import os
import sys
import threading
import time

import psutil


def library_folders(lib_folder):
    folders = [lib_folder, os.path.join(lib_folder, "lhm")]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        folders.append(os.path.join(bundled, "lib", "lhm"))
    return folders


class Sensors:
    def __init__(self, lib_folder, start=True):
        self.cpu_load = None
        self.cpu_temp = None
        self.computer = None
        self.cpu_hardware = []
        self.status = "missing_lib"
        self.error = ""
        self.load_lhm(lib_folder)
        psutil.cpu_percent(None)
        if start:
            threading.Thread(target=self.loop, daemon=True).start()

    def load_lhm(self, lib_folder):
        dll = next((os.path.join(f, "LibreHardwareMonitorLib.dll") for f in library_folders(lib_folder)
                    if os.path.exists(os.path.join(f, "LibreHardwareMonitorLib.dll"))), None)
        if dll is None:
            return
        try:
            import clr
        except Exception as error:
            self.status, self.error = "missing_pythonnet", str(error)
            return
        try:
            sys.path.append(os.path.dirname(dll))
            clr.AddReference(dll)
            from LibreHardwareMonitor.Hardware import Computer, HardwareType
            computer = Computer()
            computer.IsCpuEnabled = True
            computer.Open()
            self.cpu_hardware = [h for h in computer.Hardware if h.HardwareType == HardwareType.Cpu]
            self.computer = computer
            self.status = "waiting"
        except Exception as error:
            self.status, self.error = "error", str(error)
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
                    self.status = "active" if self.cpu_temp is not None else "no_value"
                except Exception as error:
                    self.cpu_temp = None
                    self.status, self.error = "error", str(error)
            time.sleep(1)
