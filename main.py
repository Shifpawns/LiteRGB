import ctypes
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import psutil

import config as cfg
import updater
import effects
from engine import Engine
from sensors import Sensors

APP = "LiteRGB"
VERSION = "1.8"
CONFLICTS = {
    "SignalRgb.exe": "SignalRGB",
    "NZXT CAM.exe": "NZXT CAM",
    "iCUE.exe": "Corsair iCUE",
    "SteelSeriesGG.exe": "SteelSeries GG",
    "SteelSeriesEngine.exe": "SteelSeries Engine",
    "L-Connect 3.exe": "L-Connect",
    "MSI Center.exe": "MSI Center",
    "LightKeeperService.exe": "MSI Mystic Light",
    "OpenRGB.exe": "OpenRGB",
}


def base_folder():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" "{os.path.abspath(__file__)}" --tray'


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            winreg.QueryValueEx(key, APP)
            return True
    except OSError:
        pass
    result = subprocess.run(["schtasks", "/Query", "/TN", APP], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.returncode == 0


def set_autostart(enabled):
    import winreg
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, APP)
        except OSError:
            pass
        if enabled and not is_admin():
            winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, launch_command())
    subprocess.run(["schtasks", "/Delete", "/TN", APP, "/F"], capture_output=True, creationflags=flags)
    if enabled and is_admin():
        subprocess.run(["schtasks", "/Create", "/TN", APP, "/TR", launch_command(), "/SC", "ONLOGON",
                        "/RL", "HIGHEST", "/F"], capture_output=True, creationflags=flags)


def running_conflicts():
    names = set()
    for process in psutil.process_iter(["name"]):
        name = process.info.get("name") or ""
        if name in CONFLICTS:
            names.add(CONFLICTS[name])
    return sorted(names)


class ColorButton(tk.Button):
    def __init__(self, parent, on_change):
        super().__init__(parent, width=6, relief="groove", command=self.pick)
        self.on_change = on_change
        self.value = "#ffffff"

    def set(self, value):
        self.value = value
        self.configure(bg=value, activebackground=value)

    def pick(self):
        result = colorchooser.askcolor(self.value, parent=self)
        if result and result[1]:
            self.set(result[1])
            self.on_change()


class App:
    def __init__(self, start_hidden):
        self.config = cfg.load()
        self.sensors = Sensors(os.path.join(base_folder(), "lib"))
        self.engine = Engine(self.config, self.sensors)
        self.selected = None
        self.save_results = None
        self.update_info = None
        self.loading = False
        self.tray = None

        self.root = tk.Tk()
        self.root.title(f"{APP} {VERSION}")
        self.root.geometry("640x460")
        self.root.minsize(600, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.build_lighting(notebook)
        self.build_lcd(notebook)
        self.build_ajazz(notebook)
        self.build_profiles(notebook)
        self.build_settings(notebook)

        self.status = ttk.Label(self.root, anchor="w")
        self.status.pack(fill="x", padx=10, pady=6)

        self.engine.start()
        self.start_tray()
        self.load_selection()
        self.poll()
        updater.cleanup_old()
        if updater.is_frozen():
            self.root.after(3000, lambda: self.check_updates(silent=True))

        conflicts = running_conflicts()
        if conflicts:
            messagebox.showwarning(APP, "Sluit deze programma's, anders vechten ze om je apparaten:\n\n"
                                   + "\n".join(conflicts))
        if start_hidden:
            self.root.withdraw()

    def save(self):
        cfg.save(self.config)

    def build_lighting(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Verlichting")

        left = ttk.Frame(tab)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Apparaten").pack(anchor="w")
        self.device_list = tk.Listbox(left, width=28, exportselection=False, activestyle="none")
        self.device_list.pack(fill="y", expand=True, pady=(4, 0))
        self.device_list.bind("<<ListboxSelect>>", lambda e: self.load_selection())

        right = ttk.Frame(tab, padding=(16, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        self.title = ttk.Label(right, font=("Segoe UI", 11, "bold"))
        self.title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.enabled_var = tk.BooleanVar(value=True)
        self.own_var = tk.BooleanVar(value=False)
        self.enabled_check = ttk.Checkbutton(right, text="Ingeschakeld", variable=self.enabled_var,
                                             command=self.apply_effect)
        self.own_check = ttk.Checkbutton(right, text="Eigen effect (niet synchroon)", variable=self.own_var,
                                         command=self.apply_effect)
        self.enabled_check.grid(row=1, column=0, columnspan=3, sticky="w")
        self.own_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(right, text="Effect").grid(row=3, column=0, sticky="w", pady=4)
        self.effect_var = tk.StringVar()
        self.effect_box = ttk.Combobox(right, textvariable=self.effect_var, state="readonly",
                                       values=list(effects.EFFECTS.values()), width=20)
        self.effect_box.grid(row=3, column=1, columnspan=2, sticky="w")
        self.effect_box.bind("<<ComboboxSelected>>", lambda e: self.apply_effect())

        ttk.Label(right, text="Kleuren").grid(row=4, column=0, sticky="w", pady=4)
        self.color1 = ColorButton(right, self.apply_effect)
        self.color2 = ColorButton(right, self.apply_effect)
        self.color1.grid(row=4, column=1, sticky="w")
        self.color2.grid(row=4, column=2, sticky="w")

        ttk.Label(right, text="Snelheid").grid(row=5, column=0, sticky="w", pady=4)
        self.speed_var = tk.DoubleVar(value=1.0)
        ttk.Scale(right, from_=0.1, to=4.0, variable=self.speed_var, length=200,
                  command=lambda v: self.apply_effect()).grid(row=5, column=1, columnspan=2, sticky="w")

        ttk.Separator(right).grid(row=6, column=0, columnspan=3, sticky="ew", pady=12)

        ttk.Label(right, text="Helderheid (alles)").grid(row=7, column=0, sticky="w")
        self.brightness_var = tk.IntVar(value=self.config["brightness"])
        ttk.Scale(right, from_=0, to=100, variable=self.brightness_var, length=200,
                  command=lambda v: self.apply_brightness()).grid(row=7, column=1, columnspan=2, sticky="w")

        self.lights_var = tk.BooleanVar(value=self.config["lights_on"])
        ttk.Checkbutton(right, text="Verlichting aan", variable=self.lights_var,
                        command=self.apply_brightness).grid(row=8, column=0, columnspan=3, sticky="w", pady=8)

        self.save_button = ttk.Button(right, text="Opslaan in apparaten", command=self.save_to_devices)
        self.save_button.grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def build_lcd(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Kraken LCD")
        lcd = self.config["lcd"]

        self.lcd_mode = tk.StringVar(value=lcd["mode"])
        modes = [("Sensoren (vloeistof + CPU)", "sensors"), ("Afbeelding / GIF", "image"),
                 ("Standaard NZXT-scherm", "liquid")]
        for row, (text, value) in enumerate(modes):
            ttk.Radiobutton(tab, text=text, value=value, variable=self.lcd_mode,
                            command=self.apply_lcd).grid(row=row, column=0, columnspan=3, sticky="w")

        ttk.Label(tab, text="Bestand").grid(row=3, column=0, sticky="w", pady=(12, 4))
        self.image_var = tk.StringVar(value=lcd["image"])
        ttk.Entry(tab, textvariable=self.image_var, width=42, state="readonly").grid(row=3, column=1, sticky="w")
        ttk.Button(tab, text="Kies...", command=self.pick_image).grid(row=3, column=2, padx=6)

        ttk.Label(tab, text="Helderheid").grid(row=4, column=0, sticky="w", pady=4)
        self.lcd_brightness = tk.IntVar(value=lcd["brightness"])
        ttk.Scale(tab, from_=0, to=100, variable=self.lcd_brightness, length=200,
                  command=lambda v: self.apply_lcd()).grid(row=4, column=1, sticky="w")

        ttk.Label(tab, text="Draaien").grid(row=5, column=0, sticky="w", pady=4)
        self.rotation_var = tk.StringVar(value=str(lcd["rotation"]))
        rotation = ttk.Combobox(tab, textvariable=self.rotation_var, values=["0", "90", "180", "270"],
                                state="readonly", width=6)
        rotation.grid(row=5, column=1, sticky="w")
        rotation.bind("<<ComboboxSelected>>", lambda e: self.apply_lcd())

        ttk.Label(tab, text="Accentkleur").grid(row=6, column=0, sticky="w", pady=4)
        self.accent = ColorButton(tab, self.apply_lcd)
        self.accent.set(lcd["accent"])
        self.accent.grid(row=6, column=1, sticky="w")

        ttk.Label(tab, text="Beeldformaat").grid(row=7, column=0, sticky="w", pady=4)
        self.format_var = tk.StringVar(value=lcd["format"])
        fmt = ttk.Combobox(tab, textvariable=self.format_var, values=["q565", "rgb565"],
                           state="readonly", width=8)
        fmt.grid(row=7, column=1, sticky="w")
        fmt.bind("<<ComboboxSelected>>", lambda e: self.apply_lcd())
        ttk.Label(tab, text="Blijft het scherm zwart? Probeer rgb565.", foreground="#777").grid(
            row=8, column=1, columnspan=2, sticky="w")

        cpu_note = "CPU-temperatuur: actief" if self.sensors.computer else \
            "CPU-temperatuur: niet beschikbaar (zie README)"
        ttk.Label(tab, text=cpu_note, foreground="#777").grid(row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def build_ajazz(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Ajazz-scherm")
        ttk.Label(tab, text="Afbeelding of GIF naar het schermpje van de Ajazz AK820 Pro sturen.\n"
                            "Werkt alleen via de USB-kabel, niet via de 2.4 GHz-ontvanger.\n"
                            "Het beeld wordt in het toetsenbord opgeslagen, je hoeft dit maar één keer te doen.",
                  justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self.ajazz_image = tk.StringVar(value=self.config.get("ajazz_image", ""))
        ttk.Entry(tab, textvariable=self.ajazz_image, width=42, state="readonly").grid(row=1, column=0, sticky="w")
        ttk.Button(tab, text="Kies...", command=self.pick_ajazz_image).grid(row=1, column=1, padx=6)
        self.ajazz_button = ttk.Button(tab, text="Naar toetsenbord sturen", command=self.upload_ajazz)
        self.ajazz_button.grid(row=2, column=0, sticky="w", pady=10)
        self.ajazz_status = ttk.Label(tab, foreground="#777", wraplength=520, justify="left")
        self.ajazz_status.grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Label(tab, text="Maximaal 30 frames. Fn + Delete wisselt op het toetsenbord tussen klok en afbeelding.",
                  foreground="#777").grid(row=4, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def pick_ajazz_image(self):
        path = filedialog.askopenfilename(filetypes=[("Afbeeldingen", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")])
        if path:
            self.ajazz_image.set(path)
            self.config["ajazz_image"] = path
            self.save()

    def upload_ajazz(self):
        path = self.ajazz_image.get()
        if not path or not os.path.exists(path):
            self.ajazz_status.configure(text="Kies eerst een afbeelding.")
            return
        self.ajazz_button.state(["disabled"])
        self.ajazz_status.configure(text="Bezig met versturen...")

        def work():
            from devices import ajazz_tft
            try:
                message = ajazz_tft.upload(path)
            except Exception as error:
                logging.warning("Ajazz screen upload failed: %s", error)
                message = f"Mislukt: {error}"
            self.ajazz_result = message

        self.ajazz_result = None
        threading.Thread(target=work, daemon=True).start()
        self.root.after(300, self.check_ajazz)

    def check_ajazz(self):
        if self.ajazz_result is None:
            self.root.after(300, self.check_ajazz)
            return
        self.ajazz_status.configure(text=self.ajazz_result)
        self.ajazz_button.state(["!disabled"])

    def build_profiles(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Profielen")

        self.profile_list = tk.Listbox(tab, width=30, height=12, exportselection=False)
        self.profile_list.grid(row=0, column=0, rowspan=5, sticky="ns")
        self.profile_name = tk.StringVar()
        ttk.Entry(tab, textvariable=self.profile_name, width=24).grid(row=0, column=1, padx=10, sticky="w")
        ttk.Button(tab, text="Huidige opslaan", command=self.save_profile).grid(row=1, column=1, padx=10, sticky="ew")
        ttk.Button(tab, text="Laden", command=self.load_profile).grid(row=2, column=1, padx=10, sticky="ew")
        ttk.Button(tab, text="Verwijderen", command=self.delete_profile).grid(row=3, column=1, padx=10, sticky="ew")
        self.refresh_profiles()

    def build_settings(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Instellingen")
        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(tab, text="Starten met Windows", variable=self.autostart_var,
                        command=lambda: set_autostart(self.autostart_var.get())).grid(row=0, column=0, sticky="w")
        note = "Draait als administrator: autostart met CPU-temperatuur." if is_admin() else \
            "Niet als administrator: CPU-temperatuur werkt alleen als administrator."
        ttk.Label(tab, text=note, foreground="#777").grid(row=1, column=0, sticky="w", pady=(4, 12))
        ttk.Button(tab, text="Apparaten opnieuw zoeken", command=self.rescan).grid(row=2, column=0, sticky="w")
        ttk.Button(tab, text="Logbestand openen", command=lambda: os.startfile(LOG_PATH)).grid(
            row=3, column=0, sticky="w", pady=6)

        ttk.Separator(tab).grid(row=4, column=0, sticky="ew", pady=12)
        ttk.Label(tab, text=f"Versie {VERSION}").grid(row=5, column=0, sticky="w")
        self.update_button = ttk.Button(tab, text="Zoeken naar updates", command=self.check_updates)
        self.update_button.grid(row=6, column=0, sticky="w", pady=6)
        self.update_status = ttk.Label(tab, foreground="#777", wraplength=520, justify="left")
        self.update_status.grid(row=7, column=0, sticky="w")
        self.update_info = None
        self.update_result = None

    def check_updates(self, silent=False):
        if self.update_info:
            return self.install_update()
        self.update_button.state(["disabled"])
        if not silent:
            self.update_status.configure(text="Zoeken...")

        def work():
            try:
                self.update_result = ("ok", updater.check(VERSION))
            except Exception as error:
                self.update_result = ("error", str(error))

        self.update_result = None
        threading.Thread(target=work, daemon=True).start()
        self.root.after(300, lambda: self.finish_check(silent))

    def finish_check(self, silent):
        if self.update_result is None:
            self.root.after(300, lambda: self.finish_check(silent))
            return
        self.update_button.state(["!disabled"])
        state, value = self.update_result
        if state == "error":
            if not silent:
                self.update_status.configure(text=f"Kon niet zoeken naar updates: {value}")
        elif value is None:
            if not silent:
                self.update_status.configure(text="Je hebt de nieuwste versie.")
        else:
            tag, url, notes = value
            self.update_info = (tag, url)
            self.update_button.configure(text=f"Bijwerken naar {tag}")
            self.update_status.configure(text=notes.strip()[:400] or f"Versie {tag} is beschikbaar.")

    def install_update(self):
        tag, url = self.update_info
        if not updater.is_frozen():
            self.update_status.configure(text="Bijwerken werkt alleen in LiteRGB.exe. "
                                              "Download de nieuwe versie van GitHub.")
            return
        self.update_button.state(["disabled"])
        self.update_status.configure(text=f"{tag} downloaden...")

        def work():
            try:
                updater.install(url)
                self.update_result = ("installed", tag)
            except Exception as error:
                self.update_result = ("error", str(error))

        self.update_result = None
        threading.Thread(target=work, daemon=True).start()
        self.root.after(300, self.finish_install)

    def finish_install(self):
        if self.update_result is None:
            self.root.after(300, self.finish_install)
            return
        state, value = self.update_result
        if state == "installed":
            self.quit()
        else:
            self.update_button.state(["!disabled"])
            self.update_status.configure(text=f"Bijwerken mislukt: {value}")

    def device_keys(self):
        return [None] + [k for k, d in self.engine.devices.items() if d.positions or d.hardware_only]

    def refresh_status(self):
        keys = self.device_keys()
        names = ["Alle apparaten (sync)"] + [self.engine.devices[k].name for k in keys[1:]]
        if list(self.device_list.get(0, "end")) != names:
            current = self.selected
            self.device_list.delete(0, "end")
            for name in names:
                self.device_list.insert("end", name)
            index = keys.index(current) if current in keys else 0
            self.device_list.selection_set(index)

        count = len(self.engine.devices)
        text = f"{count} apparaten verbonden"
        if self.engine.errors:
            text += f"  ·  fouten: {', '.join(self.engine.errors)}"
        if self.update_info:
            text += f"  ·  update {self.update_info[0]} beschikbaar (Instellingen)"
        self.status.configure(text=text)

    def poll(self):
        self.refresh_status()
        if self.save_results is not None:
            results, self.save_results = self.save_results, None
            self.save_button.state(["!disabled"])
            lines = [f"{name}: {result}" for name, result in results]
            messagebox.showinfo(APP, "\n".join(lines) or "Geen apparaten gevonden")
        self.root.after(1000, self.poll)

    def current_settings(self):
        if self.selected is None:
            return None
        return self.config["devices"].setdefault(self.selected, {})

    def load_selection(self):
        selection = self.device_list.curselection()
        keys = self.device_keys()
        self.selected = keys[selection[0]] if selection and selection[0] < len(keys) else None

        self.loading = True
        settings = self.current_settings()
        if settings is None:
            self.title.configure(text="Alle apparaten")
            self.enabled_check.state(["disabled"])
            self.own_check.state(["disabled"])
            effect = self.config["effect"]
        else:
            self.title.configure(text=self.engine.devices[self.selected].name)
            self.enabled_check.state(["!disabled"])
            self.own_check.state(["!disabled"])
            self.enabled_var.set(settings.get("enabled", True))
            self.own_var.set(settings.get("own_effect", False))
            effect = settings.get("effect") or dict(self.config["effect"])

        self.effect_var.set(effects.EFFECTS.get(effect.get("type"), "Statisch"))
        self.color1.set(effect.get("color1", "#00a2ff"))
        self.color2.set(effect.get("color2", "#ff0080"))
        self.speed_var.set(effect.get("speed", 1.0))
        self.loading = False

    def apply_effect(self):
        if self.loading:
            return
        kind = next((k for k, v in effects.EFFECTS.items() if v == self.effect_var.get()), "static")
        effect = {"type": kind, "color1": self.color1.value, "color2": self.color2.value,
                  "speed": round(self.speed_var.get(), 2)}
        settings = self.current_settings()
        if settings is None:
            self.config["effect"] = effect
        else:
            settings["enabled"] = self.enabled_var.get()
            settings["own_effect"] = self.own_var.get()
            if settings["own_effect"]:
                settings["effect"] = effect
        self.save()

    def apply_brightness(self):
        self.config["brightness"] = int(self.brightness_var.get())
        self.config["lights_on"] = self.lights_var.get()
        self.save()

    def pick_image(self):
        path = filedialog.askopenfilename(filetypes=[("Afbeeldingen", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")])
        if path:
            self.image_var.set(path)
            self.lcd_mode.set("image")
            self.apply_lcd()

    def apply_lcd(self):
        lcd = self.config["lcd"]
        lcd["mode"] = self.lcd_mode.get()
        lcd["image"] = self.image_var.get()
        lcd["brightness"] = int(self.lcd_brightness.get())
        lcd["rotation"] = int(self.rotation_var.get())
        lcd["accent"] = self.accent.value
        lcd["format"] = self.format_var.get()
        self.save()

    def refresh_profiles(self):
        self.profile_list.delete(0, "end")
        for name in sorted(self.config["profiles"]):
            self.profile_list.insert("end", name)
        self.update_tray_menu()

    def selected_profile(self):
        selection = self.profile_list.curselection()
        return self.profile_list.get(selection[0]) if selection else None

    def save_profile(self):
        name = self.profile_name.get().strip() or self.selected_profile()
        if not name:
            return
        cfg.save_profile(self.config, name)
        self.save()
        self.refresh_profiles()

    def load_profile(self, name=None):
        name = name or self.selected_profile()
        if not name:
            return
        cfg.load_profile(self.config, name)
        self.save()
        self.brightness_var.set(self.config["brightness"])
        self.lights_var.set(self.config["lights_on"])
        lcd = self.config["lcd"]
        self.lcd_mode.set(lcd["mode"])
        self.image_var.set(lcd["image"])
        self.lcd_brightness.set(lcd["brightness"])
        self.rotation_var.set(str(lcd["rotation"]))
        self.accent.set(lcd["accent"])
        self.format_var.set(lcd["format"])
        self.load_selection()

    def delete_profile(self):
        name = self.selected_profile()
        if name:
            self.config["profiles"].pop(name, None)
            self.save()
            self.refresh_profiles()

    def save_to_devices(self):
        if not messagebox.askyesno(APP, "Huidige verlichting opslaan in de apparaten zelf?\n\n"
                                   "Ze vallen dan terug op deze instelling als LiteRGB niet draait, "
                                   "met de ingebouwde effecten van elk apparaat. Doe dit niet te vaak, "
                                   "het geheugen van apparaten slijt van veel schrijfacties."):
            return
        self.save_button.state(["disabled"])
        self.engine.request_save(lambda results: setattr(self, "save_results", results))

    def rescan(self):
        threading.Thread(target=self.engine.scan, daemon=True).start()

    def set_lcd_mode(self, mode):
        self.lcd_mode.set(mode)
        self.apply_lcd()

    def toggle_lights(self):
        self.lights_var.set(not self.lights_var.get())
        self.apply_brightness()

    def start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception as error:
            logging.warning("Tray icon unavailable: %s", error)
            return
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for i, color in enumerate([(255, 60, 60), (60, 220, 90), (60, 140, 255)]):
            draw.ellipse([6 + i * 14, 6 + i * 14, 34 + i * 14, 34 + i * 14], fill=color)
        self.tray = pystray.Icon(APP, image, APP, self.tray_menu())
        self.tray.run_detached()

    def tray_menu(self):
        import pystray
        item = pystray.MenuItem
        later = self.root.after
        profiles = [item(name, (lambda n: lambda: later(0, self.load_profile, n))(name))
                    for name in sorted(self.config["profiles"])]
        lcd_modes = [item(text, (lambda m: lambda: later(0, self.set_lcd_mode, m))(mode),
                          checked=(lambda m: lambda i: self.config["lcd"]["mode"] == m)(mode), radio=True)
                     for text, mode in [("Sensoren", "sensors"), ("Afbeelding / GIF", "image"),
                                        ("Standaard NZXT", "liquid")]]
        return pystray.Menu(
            item("Openen", lambda: later(0, self.show), default=True),
            item("Verlichting aan", lambda: later(0, self.toggle_lights),
                 checked=lambda i: self.config.get("lights_on", True)),
            item("Profielen", pystray.Menu(*profiles) if profiles else pystray.Menu(item("(geen)", None, enabled=False))),
            item("Kraken LCD", pystray.Menu(*lcd_modes)),
            pystray.Menu.SEPARATOR,
            item("Afsluiten", lambda: later(0, self.quit)),
        )

    def update_tray_menu(self):
        if self.tray:
            self.tray.menu = self.tray_menu()
            self.tray.update_menu()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def quit(self):
        self.save()
        self.engine.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


LOG_PATH = os.path.join(cfg.FOLDER, "litergb.log")


def main():
    os.makedirs(cfg.FOLDER, exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    attempts = 40 if "--after-update" in sys.argv else 1
    for attempt in range(attempts):
        try:
            lock.bind(("127.0.0.1", 47613))
            break
        except OSError:
            if attempt == attempts - 1:
                return
            time.sleep(0.25)

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    logging.info("LiteRGB %s started from %s", VERSION, base_folder())
    App("--tray" in sys.argv).run()


if __name__ == "__main__":
    main()
