import ctypes
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

import psutil

import config as cfg
import power
import theme
import i18n
from i18n import t as T
import lcd as lcd_render
import updater
import autostart
import effects
from engine import Engine
from sensors import Sensors

APP = "LiteRGB"
PREVIEW = 220
AJAZZ_PREVIEW = 192
VERSION = "1.27"
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


def asset(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def system_language():
    try:
        return "nl" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x13 else "en"
    except Exception:
        return "nl"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def running_conflicts():
    names = set()
    for process in psutil.process_iter(["name"]):
        name = process.info.get("name") or ""
        if name in CONFLICTS:
            names.add(CONFLICTS[name])
    return sorted(names)


def value_slider(parent, var, start, end, text, command, length=200):
    frame = ttk.Frame(parent)
    ttk.Scale(frame, from_=start, to=end, variable=var, length=length, command=lambda v: command()).pack(side="left")
    label = ttk.Label(frame, width=6, anchor="e")
    label.pack(side="left", padx=(6, 0))

    def update(*args):
        try:
            label.configure(text=text(float(var.get())))
        except (tk.TclError, ValueError):
            pass

    var.trace_add("write", update)
    update()
    return frame


HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def parse_hex(text):
    match = HEX.match(text.strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.lower()


class ColorButton(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.on_change = on_change
        self.value = "#ffffff"
        self.swatch = tk.Button(self, width=4, relief="groove", command=self.pick)
        self.swatch.pack(side="left")
        self.text = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.text, width=8)
        self.entry.pack(side="left", padx=(4, 8))
        self.entry.bind("<Return>", self.typed)
        self.entry.bind("<FocusOut>", self.typed)

    def set(self, value):
        self.value = value
        self.swatch.configure(bg=value, activebackground=value)
        self.text.set(value.upper())

    def typed(self, event=None):
        value = parse_hex(self.text.get())
        if value is None:
            self.text.set(self.value.upper())
            return
        if value != self.value:
            self.set(value)
            self.on_change()
        else:
            self.text.set(value.upper())

    def pick(self):
        result = colorchooser.askcolor(self.value, parent=self)
        if result and result[1]:
            self.set(result[1])
            self.on_change()


class App:
    def __init__(self, start_hidden):
        self.config = cfg.load()
        if not self.config.get("language"):
            self.config["language"] = system_language()
        i18n.LANG = self.config["language"]
        self.sensors = Sensors(os.path.join(base_folder(), "lib"))
        self.engine = Engine(self.config, self.sensors)
        self.selected = None
        self.save_results = None
        self.update_info = None
        self.loading = False
        self.tray = None
        try:
            self.autostart_mode = autostart.refresh(__file__)
        except Exception as error:
            logging.warning("Autostart check failed: %s", error)
            self.autostart_mode = "off"
        logging.info("Autostart: %s", self.autostart_mode)

        self.root = tk.Tk()
        theme.apply(self.root, self.config.get("theme", "system"))
        self.root.title(f"{APP} {VERSION}")
        try:
            self.root.iconbitmap(asset("icon.ico"))
        except tk.TclError:
            pass
        self.root.geometry("920x520")
        self.root.minsize(900, 500)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.protocol("WM_SAVE_YOURSELF", self.on_shutdown)

        notebook = ttk.Notebook(self.root)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.build_lighting(notebook)
        self.build_lcd(notebook)
        self.build_ajazz(notebook)
        self.build_profiles(notebook)
        self.build_settings(notebook)

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=6)
        self.status = ttk.Label(bar, anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        self.lights_var = tk.BooleanVar(value=self.config["lights_on"])
        ttk.Checkbutton(bar, text=T("Alle RGB aan"), variable=self.lights_var,
                        command=self.apply_brightness).pack(side="right")

        self.engine.start()
        self.start_tray()
        self.load_selection()
        self.poll()
        updater.cleanup_old()
        if updater.is_frozen():
            self.root.after(3000, lambda: self.check_updates(silent=True))

        conflicts = running_conflicts()
        if conflicts:
            messagebox.showwarning(APP, T("Sluit deze programma's, anders vechten ze om je apparaten:") + "\n\n"
                                   + "\n".join(conflicts))
        power.watch(self.on_sleep, self.on_resume, self.on_shutdown)
        if start_hidden or self.config.get("start_minimized", False):
            self.root.withdraw()

    def on_sleep(self):
        if self.config.get("leds_off_on_sleep", True):
            self.leds_off()

    def on_shutdown(self):
        self.leds_off()

    def leds_off(self):
        if self.engine.paused:
            return
        logging.info("Turning LEDs off")
        self.engine.blackout()
        logging.info("LEDs off")

    def on_resume(self):
        if self.engine.paused:
            logging.info("Resumed from sleep")
            self.engine.resume()

    def on_close(self):
        if self.config.get("close_to_tray", True) and self.tray:
            self.hide()
        else:
            self.quit()

    def save(self):
        cfg.save(self.config)

    def build_lighting(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text=T("Verlichting"))

        left = ttk.Frame(tab)
        left.pack(side="left", fill="y")
        ttk.Label(left, text=T("Apparaten")).pack(anchor="w")
        self.device_list = tk.Listbox(left, width=34, exportselection=False, activestyle="none")
        theme.style_listbox(self.device_list)
        self.device_list.pack(fill="y", expand=True, pady=(4, 0))
        self.device_list.bind("<<ListboxSelect>>", lambda e: self.load_selection())

        right = ttk.Frame(tab, padding=(16, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        self.title = ttk.Label(right, font=("Segoe UI", 11, "bold"))
        self.title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.enabled_var = tk.BooleanVar(value=True)
        self.own_var = tk.BooleanVar(value=False)
        self.enabled_check = ttk.Checkbutton(right, text=T("Verlichting van dit apparaat aan"),
                                             variable=self.enabled_var,
                                             command=lambda: self.apply_effect(auto_own=False))
        self.own_check = ttk.Checkbutton(right, text=T("Eigen effect (niet synchroon)"), variable=self.own_var,
                                         command=lambda: self.apply_effect(auto_own=False))
        self.enabled_check.grid(row=1, column=0, columnspan=3, sticky="w")
        self.own_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(right, text=T("Effect")).grid(row=3, column=0, sticky="w", pady=4)
        self.effect_var = tk.StringVar()
        self.effect_box = ttk.Combobox(right, textvariable=self.effect_var, state="readonly",
                                       values=[T(v) for v in effects.EFFECTS.values()], width=20)
        self.effect_box.grid(row=3, column=1, columnspan=2, sticky="w")
        self.effect_box.bind("<<ComboboxSelected>>", lambda e: self.apply_effect())

        self.colors_label = ttk.Label(right, text=T("Kleuren"))
        self.colors_label.grid(row=4, column=0, sticky="w", pady=4)
        self.color1 = ColorButton(right, self.apply_effect)
        self.color2 = ColorButton(right, self.apply_effect)
        self.color1.grid(row=4, column=1, sticky="w")
        self.color2.grid(row=4, column=2, sticky="w")

        self.speed_label = ttk.Label(right, text=T("Snelheid"))
        self.speed_label.grid(row=5, column=0, sticky="w", pady=4)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_frame = value_slider(right, self.speed_var, 0.1, 4.0, lambda v: f"{v:.1f}×", self.apply_effect)
        self.speed_frame.grid(row=5, column=1, columnspan=2, sticky="w")

        ttk.Label(right, text=T("Verzadiging")).grid(row=6, column=0, sticky="w", pady=4)
        self.saturation_var = tk.IntVar(value=100)
        value_slider(right, self.saturation_var, 0, 100, lambda v: f"{v:.0f}%", self.apply_effect).grid(
            row=6, column=1, columnspan=2, sticky="w")

        ttk.Separator(right).grid(row=7, column=0, columnspan=3, sticky="ew", pady=12)

        ttk.Label(right, text=T("Helderheid (alles)")).grid(row=8, column=0, sticky="w")
        self.brightness_var = tk.IntVar(value=self.config["brightness"])
        value_slider(right, self.brightness_var, 0, 100, lambda v: f"{v:.0f}%", self.apply_brightness).grid(
            row=8, column=1, columnspan=2, sticky="w")

        self.save_button = ttk.Button(right, text=T("Opslaan in apparaten"), command=self.save_to_devices)
        self.save_button.grid(row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def update_controls(self):
        kind = self.selected_kind()
        colors = kind in ("static", "breathing", "gradient")
        animated = kind not in ("off", "static")
        for widget, visible in ((self.colors_label, colors), (self.color1, colors),
                                (self.color2, kind == "gradient"),
                                (self.speed_label, animated), (self.speed_frame, animated)):
            if visible:
                widget.grid()
            else:
                widget.grid_remove()
        self.colors_label.configure(text=T("Kleuren") if kind == "gradient" else T("Kleur"))

    def selected_kind(self):
        return next((k for k, v in effects.EFFECTS.items() if T(v) == self.effect_var.get()), "static")

    def build_lcd(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text=T("Kraken LCD"))
        self.lcd_tab = tab
        lcd = self.config["lcd"]

        self.lcd_mode = tk.StringVar(value=lcd["mode"])
        modes = [(T("Sensoren (vloeistof + CPU)"), "sensors"), (T("Afbeelding / GIF"), "image"),
                 (T("Standaard NZXT-scherm"), "liquid")]
        for row, (text, value) in enumerate(modes):
            ttk.Radiobutton(tab, text=text, value=value, variable=self.lcd_mode,
                            command=self.apply_lcd).grid(row=row, column=0, columnspan=3, sticky="w")

        ttk.Label(tab, text=T("Bestand")).grid(row=3, column=0, sticky="w", pady=(12, 4))
        self.image_var = tk.StringVar(value=lcd["image"])
        ttk.Entry(tab, textvariable=self.image_var, width=26, state="readonly").grid(row=3, column=1, sticky="w")
        file_buttons = ttk.Frame(tab)
        file_buttons.grid(row=3, column=2, padx=6, sticky="w")
        ttk.Button(file_buttons, text=T("Kies..."), command=self.pick_image).pack(side="left")
        ttk.Button(file_buttons, text=T("GIF zoeken..."), command=lambda: self.open_gif_search(self.use_lcd_gif)).pack(
            side="left", padx=(6, 0))

        ttk.Label(tab, text=T("Helderheid")).grid(row=4, column=0, sticky="w", pady=4)
        self.lcd_brightness = tk.IntVar(value=lcd["brightness"])
        value_slider(tab, self.lcd_brightness, 0, 100, lambda v: f"{v:.0f}%", self.apply_lcd, 180).grid(
            row=4, column=1, columnspan=2, sticky="w")

        ttk.Label(tab, text=T("Draaien")).grid(row=5, column=0, sticky="w", pady=4)
        self.rotation_var = tk.StringVar(value=str(lcd["rotation"]))
        rotation = ttk.Combobox(tab, textvariable=self.rotation_var, values=["0", "90", "180", "270"],
                                state="readonly", width=6)
        rotation.grid(row=5, column=1, sticky="w")
        rotation.bind("<<ComboboxSelected>>", lambda e: self.apply_lcd())

        ttk.Label(tab, text=T("Accentkleur")).grid(row=6, column=0, sticky="w", pady=4)
        self.accent = ColorButton(tab, self.apply_lcd)
        self.accent.set(lcd["accent"])
        self.accent.grid(row=6, column=1, sticky="w")

        ttk.Label(tab, text=T("Beeldformaat")).grid(row=7, column=0, sticky="w", pady=4)
        self.format_var = tk.StringVar(value=lcd["format"])
        fmt = ttk.Combobox(tab, textvariable=self.format_var, values=["q565", "rgb565"],
                           state="readonly", width=8)
        fmt.grid(row=7, column=1, sticky="w")
        fmt.bind("<<ComboboxSelected>>", lambda e: self.apply_lcd())
        ttk.Label(tab, text=T("Blijft het scherm zwart? Probeer rgb565."), foreground=theme.MUTED).grid(
            row=8, column=1, columnspan=2, sticky="w")

        overlay_row = ttk.Frame(tab)
        overlay_row.grid(row=9, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.overlay_var = tk.BooleanVar(value=lcd.get("overlay_sensors", False))
        ttk.Checkbutton(overlay_row, text=T("Sensoren over afbeelding/GIF tonen"), variable=self.overlay_var,
                        command=self.apply_lcd).pack(side="left")
        positions = {"bottom": T("Onder"), "top": T("Boven")}
        self.overlay_position = tk.StringVar(value=positions.get(lcd.get("overlay_position", "bottom")))
        position_box = ttk.Combobox(overlay_row, textvariable=self.overlay_position, values=list(positions.values()),
                                    state="readonly", width=7)
        position_box.pack(side="left", padx=8)
        position_box.bind("<<ComboboxSelected>>", lambda e: self.apply_lcd())
        self.overlay_positions = positions

        self.cpu_label = ttk.Label(tab, foreground=theme.MUTED, wraplength=430, justify="left")
        self.cpu_label.grid(row=10, column=0, columnspan=3, sticky="w", pady=(12, 0))

        side = ttk.Frame(tab, padding=(20, 0, 0, 0))
        side.grid(row=0, column=3, rowspan=11, sticky="n")
        self.preview = tk.Canvas(side, width=PREVIEW, height=PREVIEW, highlightthickness=0, bg="#0b0d10",
                                 cursor="fleur")
        self.preview.pack()
        self.preview.bind("<ButtonPress-1>", self.preview_press)
        self.preview.bind("<B1-Motion>", self.preview_drag)
        self.preview.bind("<ButtonRelease-1>", lambda e: self.apply_lcd())
        self.preview.bind("<MouseWheel>", self.preview_wheel)
        self.preview.bind("<Button-4>", lambda e: self.preview_wheel(e, 1))
        self.preview.bind("<Button-5>", lambda e: self.preview_wheel(e, -1))
        ttk.Label(side, text=T("Sleep om te verschuiven,\nscroll om te zoomen"), justify="center", foreground=theme.MUTED).pack(pady=(6, 4))
        zoom_row = ttk.Frame(side)
        zoom_row.pack()
        ttk.Label(zoom_row, text=T("Zoom")).pack(side="left")
        self.zoom_var = tk.DoubleVar(value=lcd.get("zoom", 1.0))
        value_slider(zoom_row, self.zoom_var, 0.3, 4.0, lambda v: f"{v:.1f}×", self.preview_changed, 130).pack(
            side="left", padx=6)
        ttk.Button(side, text=T("Reset"), command=self.reset_view).pack(pady=6)
        self.offset_x = lcd.get("offset_x", 0.0)
        self.offset_y = lcd.get("offset_y", 0.0)
        self.preview_source = (None, None)
        self.preview_photo = None
        self.preview_job = None
        self.draw_preview()

    def preview_frame(self):
        path = self.image_var.get()
        if self.preview_source[0] != path:
            try:
                self.preview_source = (path, Image.open(path).convert("RGB") if path else None)
            except OSError:
                self.preview_source = (path, None)
        return self.preview_source[1]

    def draw_preview(self):
        rotation = 0
        mode = self.lcd_mode.get()
        frame = self.preview_frame()
        if mode == "image" and frame is not None:
            image = lcd_render.fit(frame, PREVIEW, rotation, self.zoom_var.get(), self.offset_x, self.offset_y)
            if self.overlay_var.get():
                overlay = lcd_render.sensor_overlay(PREVIEW, 31.4, self.sensors.cpu_temp, self.sensors.cpu_load,
                                                    self.accent.value, self.overlay_position_code())
                image = lcd_render.compose(image, overlay, 0)
        elif mode == "sensors":
            image = lcd_render.sensor_frame(PREVIEW, rotation, 31.4, self.sensors.cpu_temp,
                                            self.sensors.cpu_load, self.accent.value)
        else:
            image = Image.new("RGB", (PREVIEW, PREVIEW), (11, 13, 16))
        mask = Image.new("L", (PREVIEW, PREVIEW), 70)
        ImageDraw.Draw(mask).ellipse([0, 0, PREVIEW - 1, PREVIEW - 1], fill=255)
        image = Image.composite(image, Image.new("RGB", image.size, (0, 0, 0)), mask)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview.delete("all")
        self.preview.create_image(0, 0, anchor="nw", image=self.preview_photo)

    def preview_press(self, event):
        self.drag_start = (event.x, event.y, self.offset_x, self.offset_y)

    def preview_drag(self, event):
        x, y, ox, oy = self.drag_start
        dx, dy = (event.x - x) / PREVIEW, (event.y - y) / PREVIEW
        self.offset_x = max(-2.0, min(2.0, ox + dx))
        self.offset_y = max(-2.0, min(2.0, oy + dy))
        self.draw_preview()

    def preview_wheel(self, event, direction=None):
        step = direction if direction is not None else (1 if event.delta > 0 else -1)
        self.zoom_var.set(max(0.3, min(4.0, self.zoom_var.get() * (1.1 if step > 0 else 1 / 1.1))))
        self.preview_changed()

    def preview_changed(self):
        self.draw_preview()
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        self.preview_job = self.root.after(500, self.apply_lcd)

    def reset_view(self):
        self.zoom_var.set(1.0)
        self.offset_x = self.offset_y = 0.0
        self.draw_preview()
        self.apply_lcd()

    def build_ajazz(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text=T("Ajazz-scherm"))
        self.ajazz_tab = tab
        ttk.Label(tab, text=T("Ajazz-uitleg"),
                  justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self.ajazz_image = tk.StringVar(value=self.config.get("ajazz_image", ""))
        ttk.Entry(tab, textvariable=self.ajazz_image, width=34, state="readonly").grid(row=1, column=0, sticky="w")
        ajazz_buttons = ttk.Frame(tab)
        ajazz_buttons.grid(row=1, column=1, padx=6, sticky="w")
        ttk.Button(ajazz_buttons, text=T("Kies..."), command=self.pick_ajazz_image).pack(side="left")
        ttk.Button(ajazz_buttons, text=T("GIF zoeken..."),
                   command=lambda: self.open_gif_search(self.use_ajazz_gif)).pack(side="left", padx=(6, 0))

        preview_side = ttk.Frame(tab, padding=(20, 0, 0, 0))
        preview_side.grid(row=0, column=3, rowspan=6, sticky="n")
        self.ajazz_preview = tk.Canvas(preview_side, width=AJAZZ_PREVIEW, height=AJAZZ_PREVIEW,
                                       highlightthickness=0, bg="#0b0d10")
        self.ajazz_preview.pack()
        ttk.Label(preview_side, text=T("Voorbeeld op het toetsenbord"), foreground=theme.MUTED).pack(pady=(6, 0))
        self.ajazz_frames = []
        self.ajazz_frame_index = 0
        self.ajazz_animation = None
        self.load_ajazz_preview()
        self.ajazz_button = ttk.Button(tab, text=T("Naar toetsenbord sturen"), command=self.upload_ajazz)
        self.ajazz_button.grid(row=2, column=0, sticky="w", pady=10)
        self.ajazz_status = ttk.Label(tab, foreground=theme.MUTED, wraplength=520, justify="left")
        self.ajazz_status.grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Label(tab, text=T("Maximaal 30 frames. Fn + Delete wisselt op het toetsenbord tussen klok en afbeelding."),
                  foreground=theme.MUTED).grid(row=4, column=0, columnspan=3, sticky="w", pady=(16, 0))

    def pick_ajazz_image(self):
        path = filedialog.askopenfilename(filetypes=[(T("Afbeeldingen"), "*.png *.jpg *.jpeg *.gif *.webp *.bmp")])
        if path:
            self.use_ajazz_gif(path)

    def use_ajazz_gif(self, path):
        self.ajazz_image.set(path)
        self.config["ajazz_image"] = path
        self.save()
        self.load_ajazz_preview()

    def use_lcd_gif(self, path):
        self.image_var.set(path)
        self.lcd_mode.set("image")
        self.apply_lcd()

    def open_gif_search(self, on_pick):
        from gif_search import GifSearch
        GifSearch(self, on_pick)

    def load_ajazz_preview(self):
        from devices import ajazz_tft
        if self.ajazz_animation:
            self.root.after_cancel(self.ajazz_animation)
            self.ajazz_animation = None
        self.ajazz_preview.delete("all")
        self.ajazz_frames = []
        path = self.ajazz_image.get()
        if not path or not os.path.exists(path):
            return
        try:
            for image, delay in ajazz_tft.preview_frames(path):
                image = image.resize((AJAZZ_PREVIEW, AJAZZ_PREVIEW), Image.NEAREST)
                self.ajazz_frames.append((ImageTk.PhotoImage(image), delay))
        except Exception as error:
            logging.warning("Ajazz preview failed: %s", error)
            return
        self.ajazz_frame_index = 0
        self.animate_ajazz()

    def animate_ajazz(self):
        if not self.ajazz_frames:
            return
        photo, delay = self.ajazz_frames[self.ajazz_frame_index % len(self.ajazz_frames)]
        self.ajazz_preview.delete("all")
        self.ajazz_preview.create_image(0, 0, anchor="nw", image=photo)
        self.ajazz_frame_index += 1
        if len(self.ajazz_frames) > 1:
            self.ajazz_animation = self.root.after(delay, self.animate_ajazz)

    def upload_ajazz(self):
        path = self.ajazz_image.get()
        if not path or not os.path.exists(path):
            self.ajazz_status.configure(text=T("Kies eerst een afbeelding."))
            return
        self.ajazz_button.state(["disabled"])
        self.ajazz_status.configure(text=T("Bezig met versturen..."))

        def work():
            from devices import ajazz_tft
            try:
                message = ajazz_tft.upload(path)
            except Exception as error:
                logging.warning("Ajazz screen upload failed: %s", error)
                message = T("Mislukt: {error}", error=error)
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
        notebook.add(tab, text=T("Profielen"))

        self.profile_list = tk.Listbox(tab, width=30, height=12, exportselection=False)
        theme.style_listbox(self.profile_list)
        self.profile_list.grid(row=0, column=0, rowspan=8, sticky="ns")

        ttk.Label(tab, text=T("Nieuw profiel")).grid(row=0, column=1, padx=12, sticky="w")
        self.profile_name = tk.StringVar()
        ttk.Entry(tab, textvariable=self.profile_name, width=26).grid(row=1, column=1, padx=12, sticky="w")
        ttk.Button(tab, text=T("Opslaan als nieuw"), command=self.save_profile).grid(
            row=2, column=1, padx=12, pady=(4, 16), sticky="ew")

        ttk.Label(tab, text=T("Geselecteerd profiel")).grid(row=3, column=1, padx=12, sticky="w")
        ttk.Button(tab, text=T("Laden"), command=self.load_profile).grid(row=4, column=1, padx=12, pady=2, sticky="ew")
        ttk.Button(tab, text=T("Bijwerken met huidige instellingen"), command=self.update_profile).grid(
            row=5, column=1, padx=12, pady=2, sticky="ew")
        ttk.Button(tab, text=T("Verwijderen"), command=self.delete_profile).grid(
            row=6, column=1, padx=12, pady=2, sticky="ew")
        self.refresh_profiles()

    def build_settings(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text=T("Instellingen"))

        current = self.autostart_mode
        start_row = ttk.Frame(tab)
        start_row.grid(row=0, column=0, sticky="w")
        self.autostart_var = tk.BooleanVar(value=current != "off")
        ttk.Checkbutton(start_row, text=T("Starten met Windows"), variable=self.autostart_var,
                        command=self.change_autostart).pack(side="left")
        self.autostart_admin_var = tk.BooleanVar(value=current == "admin")
        self.autostart_admin_check = ttk.Checkbutton(
            start_row, text=T("Als administrator, zonder UAC-melding"), variable=self.autostart_admin_var,
            command=self.change_autostart)
        self.autostart_admin_check.pack(side="left", padx=(16, 0))
        if current == "off":
            self.autostart_admin_check.state(["disabled"])
        self.minimized_var = tk.BooleanVar(value=self.config.get("start_minimized", False))
        ttk.Checkbutton(tab, text=T("Geminimaliseerd starten (alleen in systeemvak)"), variable=self.minimized_var,
                        command=lambda: self.set_option("start_minimized", self.minimized_var.get())).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        self.close_tray_var = tk.BooleanVar(value=self.config.get("close_to_tray", True))
        ttk.Checkbutton(tab, text=T("Bij sluiten naar systeemvak (anders afsluiten)"), variable=self.close_tray_var,
                        command=lambda: self.set_option("close_to_tray", self.close_tray_var.get())).grid(
            row=2, column=0, sticky="w", pady=(4, 0))
        self.sleep_var = tk.BooleanVar(value=self.config.get("leds_off_on_sleep", True))
        ttk.Checkbutton(tab, text=T("Leds uit bij slaapstand"), variable=self.sleep_var,
                        command=lambda: self.set_option("leds_off_on_sleep", self.sleep_var.get())).grid(
            row=3, column=0, sticky="w", pady=(4, 0))
        note = T("Draait als administrator.") if is_admin() else \
            T("Niet als administrator: CPU-temperatuur en RAM werken alleen als administrator.")
        ttk.Label(tab, text=note, foreground=theme.MUTED).grid(row=4, column=0, sticky="w", pady=(8, 12))

        buttons = ttk.Frame(tab)
        buttons.grid(row=5, column=0, sticky="w")
        ttk.Button(buttons, text=T("Apparaten opnieuw zoeken"), command=self.rescan).pack(side="left")
        ttk.Button(buttons, text=T("Logbestand openen"), command=lambda: os.startfile(LOG_PATH)).pack(
            side="left", padx=8)

        ttk.Separator(tab).grid(row=6, column=0, sticky="ew", pady=12)
        version_row = ttk.Frame(tab)
        version_row.grid(row=7, column=0, sticky="w")
        ttk.Label(version_row, text=T("Versie {version}", version=VERSION)).pack(side="left")
        self.update_button = ttk.Button(version_row, text=T("Zoeken naar updates"), command=self.check_updates)
        self.update_button.pack(side="left", padx=12)
        ttk.Button(version_row, text=T("Wat is er nieuw"), command=self.show_changelog).pack(side="left")
        self.update_status = ttk.Label(tab, foreground=theme.MUTED, wraplength=560, justify="left")
        self.update_status.grid(row=8, column=0, sticky="w", pady=(4, 0))
        self.update_info = None
        self.update_result = None

        language_row = ttk.Frame(tab)
        language_row.grid(row=9, column=0, sticky="w", pady=(16, 0))
        ttk.Label(language_row, text="Language" if i18n.LANG == "en" else "Taal / Language", width=16).pack(side="left")
        names = {"nl": "Nederlands", "en": "English"}
        self.language_var = tk.StringVar(value=names.get(self.config["language"], "Nederlands"))
        language = ttk.Combobox(language_row, textvariable=self.language_var, values=list(names.values()),
                                state="readonly", width=12)
        language.pack(side="left")
        language.bind("<<ComboboxSelected>>", lambda e: self.change_language(
            next(k for k, v in names.items() if v == self.language_var.get())))

        theme_row = ttk.Frame(tab)
        theme_row.grid(row=10, column=0, sticky="w", pady=(8, 0))
        ttk.Label(theme_row, text=T("Thema"), width=16).pack(side="left")
        themes = {"system": T("Systeem"), "light": T("Licht"), "dark": T("Donker")}
        self.theme_var = tk.StringVar(value=themes.get(self.config.get("theme", "system")))
        theme_box = ttk.Combobox(theme_row, textvariable=self.theme_var, values=list(themes.values()),
                                 state="readonly", width=12)
        theme_box.pack(side="left")
        theme_box.bind("<<ComboboxSelected>>", lambda e: self.change_theme(
            next(k for k, v in themes.items() if v == self.theme_var.get())))

    def set_option(self, key, value):
        self.config[key] = value
        self.save()

    def change_language(self, code):
        if code == self.config.get("language"):
            return
        self.config["language"] = code
        self.save()
        i18n.LANG = code
        if messagebox.askyesno(APP, T("Herstart LiteRGB om de taal te wijzigen.") + "\n\n" +
                               ("Nu herstarten?" if code == "nl" else "Restart now?")):
            self.restart()

    def change_theme(self, choice):
        if choice == self.config.get("theme", "system"):
            return
        self.config["theme"] = choice
        self.save()
        if messagebox.askyesno(APP, T("LiteRGB herstarten om het thema toe te passen?")):
            self.restart()

    def restart(self):
        self.save()
        self.engine.stop()
        if self.tray:
            self.tray.stop()
        command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("_MEI", "_PYI"))}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen(command + ["--after-update"], env=env, close_fds=True)
        self.root.destroy()

    def change_autostart(self):
        wanted = "off"
        if self.autostart_var.get():
            wanted = "admin" if self.autostart_admin_var.get() else "normal"
        self.autostart_admin_check.state(["!disabled"] if wanted != "off" else ["disabled"])
        try:
            if autostart.needs_elevation(wanted):
                if not autostart.apply_elevated(wanted, __file__):
                    self.sync_autostart_checks()
                    return
                self.root.after(1500, lambda: self.wait_for_autostart(wanted, 10))
                return
            autostart.apply(wanted, __file__)
        except Exception as error:
            logging.warning("Autostart failed: %s", error)
            messagebox.showerror(APP, T("Mislukt: {error}", error=error))
        self.sync_autostart_checks()

    def wait_for_autostart(self, wanted, tries):
        if autostart.mode() != wanted and tries > 0:
            self.root.after(1000, lambda: self.wait_for_autostart(wanted, tries - 1))
            return
        self.sync_autostart_checks()

    def sync_autostart_checks(self):
        current = autostart.mode()
        self.autostart_mode = current
        self.autostart_var.set(current != "off")
        if current != "off":
            self.autostart_admin_var.set(current == "admin")
        self.autostart_admin_check.state(["!disabled"] if current != "off" else ["disabled"])

    def check_updates(self, silent=False):
        if self.update_info:
            return self.install_update()
        self.update_button.state(["disabled"])
        if not silent:
            self.update_status.configure(text=T("Zoeken..."))

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
                self.update_status.configure(text=T("Kon niet zoeken naar updates: {error}", error=value))
        elif value is None:
            if not silent:
                self.update_status.configure(text=T("Je hebt de nieuwste versie."))
        else:
            tag, url, notes = value
            self.update_info = (tag, url)
            self.update_button.configure(text=T("Bijwerken naar {tag}", tag=tag))
            self.update_status.configure(text=T("Versie {tag} is beschikbaar.", tag=tag))

    def show_changelog(self):
        from changelog_view import ChangelogWindow
        ChangelogWindow(self, VERSION)

    def install_update(self):
        tag, url = self.update_info
        if not updater.is_frozen():
            self.update_status.configure(text=T("Bijwerken werkt alleen in LiteRGB.exe. "
                                                "Download de nieuwe versie van GitHub."))
            return
        self.update_button.state(["disabled"])
        self.update_status.configure(text=T("{tag} downloaden...", tag=tag))

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
            self.update_status.configure(text=T("Bijwerken mislukt: {error}", error=value))

    def device_keys(self):
        return [None] + [k for k, d in self.engine.devices.items() if d.positions or d.hardware_only]

    def show_tab(self, tab, visible):
        if visible:
            self.notebook.add(tab)
        elif self.notebook.tab(tab, "state") != "hidden":
            self.notebook.hide(tab)

    def refresh_status(self):
        self.show_tab(self.lcd_tab, "nzxt_kraken" in self.engine.devices)
        self.show_tab(self.ajazz_tab, "ajazz_ak820" in self.engine.devices)
        keys = self.device_keys()
        names = [T("Alle apparaten (sync)")] + [self.device_label(k) for k in keys[1:]]
        if list(self.device_list.get(0, "end")) != names:
            current = self.selected
            self.device_list.delete(0, "end")
            for name in names:
                self.device_list.insert("end", name)
            index = keys.index(current) if current in keys else 0
            self.device_list.selection_set(index)

        if hasattr(self, "cpu_label"):
            self.cpu_label.configure(text=self.cpu_text())

        count = len(self.engine.devices)
        text = T("{count} apparaten verbonden", count=count)
        if self.engine.errors:
            text += f"  ·  {T('fouten')}: {', '.join(self.engine.errors)}"
        if self.update_info:
            text += "  ·  " + T("update {tag} beschikbaar (Instellingen)", tag=self.update_info[0])
        self.status.configure(text=text)

    def device_label(self, key):
        settings = self.config["devices"].get(key, {})
        name = self.engine.devices[key].name
        if not settings.get("enabled", True):
            return f"{name}  ·  {T('uit')}"
        if settings.get("own_effect"):
            return f"{name}  ·  {T('eigen effect')}"
        return name

    def cpu_text(self):
        status = self.sensors.status
        if status == "active":
            return T("CPU-temperatuur: actief")
        if status == "waiting":
            return T("CPU-temperatuur: wordt gestart...")
        if status == "missing_lib":
            return T("CPU-temperatuur: LibreHardwareMonitor ontbreekt in deze versie.")
        if status == "missing_pythonnet":
            return T("CPU-temperatuur: pythonnet ontbreekt ({error}).", error=self.sensors.error)
        if status == "no_value":
            if not is_admin():
                return T("CPU-temperatuur: start LiteRGB als administrator.")
            return T("CPU-temperatuur: geen waarde. Installeer de PawnIO-driver via pawnio.eu en herstart.")
        return T("CPU-temperatuur: fout: {error}", error=self.sensors.error)

    def poll(self):
        self.refresh_status()
        if self.save_results is not None:
            results, self.save_results = self.save_results, None
            self.save_button.state(["!disabled"])
            lines = [f"{name}: {T(result)}" for name, result in results]
            messagebox.showinfo(APP, "\n".join(lines) or T("Geen apparaten gevonden"))
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
            self.title.configure(text=T("Alle apparaten"))
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

        self.effect_var.set(T(effects.EFFECTS.get(effect.get("type"), "Statisch")))
        self.color1.set(effect.get("color1", "#00a2ff"))
        self.color2.set(effect.get("color2", "#ff0080"))
        self.speed_var.set(effect.get("speed", 1.0))
        self.saturation_var.set(effect.get("saturation", 100))
        self.update_controls()
        self.loading = False

    def apply_effect(self, auto_own=True):
        if self.loading:
            return
        self.update_controls()
        kind = self.selected_kind()
        effect = {"type": kind, "color1": self.color1.value, "color2": self.color2.value,
                  "speed": round(self.speed_var.get(), 2), "saturation": int(self.saturation_var.get())}
        settings = self.current_settings()
        if settings is None:
            self.config["effect"] = effect
        else:
            if auto_own and not self.own_var.get():
                self.own_var.set(True)
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
        path = filedialog.askopenfilename(filetypes=[(T("Afbeeldingen"), "*.png *.jpg *.jpeg *.gif *.webp *.bmp")])
        if path:
            self.image_var.set(path)
            self.lcd_mode.set("image")
            self.apply_lcd()

    def overlay_position_code(self):
        return next((k for k, v in self.overlay_positions.items() if v == self.overlay_position.get()), "bottom")

    def apply_lcd(self):
        lcd = self.config["lcd"]
        lcd["mode"] = self.lcd_mode.get()
        lcd["image"] = self.image_var.get()
        lcd["brightness"] = int(self.lcd_brightness.get())
        lcd["rotation"] = int(self.rotation_var.get())
        lcd["accent"] = self.accent.value
        lcd["format"] = self.format_var.get()
        lcd["zoom"] = round(self.zoom_var.get(), 3)
        lcd["offset_x"] = round(self.offset_x, 3)
        lcd["offset_y"] = round(self.offset_y, 3)
        lcd["overlay_sensors"] = self.overlay_var.get()
        lcd["overlay_position"] = self.overlay_position_code()
        self.save()
        self.draw_preview()

    def refresh_profiles(self):
        self.profile_list.delete(0, "end")
        for name in sorted(self.config["profiles"]):
            self.profile_list.insert("end", name)
        self.update_tray_menu()

    def selected_profile(self):
        selection = self.profile_list.curselection()
        return self.profile_list.get(selection[0]) if selection else None

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            messagebox.showinfo(APP, T("Vul eerst een naam in voor het nieuwe profiel."))
            return
        if name in self.config["profiles"] and not messagebox.askyesno(
                APP, T("Profiel '{name}' bestaat al. Overschrijven?", name=name)):
            return
        cfg.save_profile(self.config, name)
        self.save()
        self.profile_name.set("")
        self.refresh_profiles()

    def update_profile(self):
        name = self.selected_profile()
        if not name:
            messagebox.showinfo(APP, T("Selecteer eerst een profiel in de lijst."))
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
        self.zoom_var.set(lcd.get("zoom", 1.0))
        self.offset_x = lcd.get("offset_x", 0.0)
        self.offset_y = lcd.get("offset_y", 0.0)
        self.overlay_var.set(lcd.get("overlay_sensors", False))
        self.overlay_position.set(self.overlay_positions.get(lcd.get("overlay_position", "bottom")))
        self.draw_preview()
        self.load_selection()

    def delete_profile(self):
        name = self.selected_profile()
        if name:
            self.config["profiles"].pop(name, None)
            self.save()
            self.refresh_profiles()

    def save_to_devices(self):
        if not messagebox.askyesno(APP, T("Opslaan-uitleg")):
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
            from PIL import Image
        except Exception as error:
            logging.warning("Tray icon unavailable: %s", error)
            return
        try:
            image = Image.open(asset("icon.png")).resize((64, 64), Image.LANCZOS)
        except OSError:
            image = Image.new("RGBA", (64, 64), (0, 162, 255, 255))
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
                     for text, mode in [(T("Sensoren"), "sensors"), (T("Afbeelding / GIF"), "image"),
                                        (T("Standaard NZXT"), "liquid")]]
        return pystray.Menu(
            item(T("Openen"), lambda: later(0, self.show), default=True),
            item(T("Verlichting aan"), lambda: later(0, self.toggle_lights),
                 checked=lambda i: self.config.get("lights_on", True)),
            item(T("Profielen"), pystray.Menu(*profiles) if profiles else pystray.Menu(item(T("(geen)"), None, enabled=False))),
            item(T("Kraken LCD"), pystray.Menu(*lcd_modes)),
            pystray.Menu.SEPARATOR,
            item(T("Afsluiten"), lambda: later(0, self.quit)),
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


def selftest(path):
    sensors = Sensors(os.path.join(base_folder(), "lib"), start=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{sensors.status} {sensors.error}\n")


def main():
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
        return
    os.makedirs(cfg.FOLDER, exist_ok=True)
    if "--launch-task" in sys.argv and not is_admin() and autostart.launch_task():
        return
    if "--set-autostart" in sys.argv:
        logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
        try:
            autostart.apply(sys.argv[sys.argv.index("--set-autostart") + 1], __file__)
        except Exception as error:
            logging.warning("Autostart failed: %s", error)
        return
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

    logging.info("LiteRGB %s started from %s%s, admin: %s", VERSION, base_folder(),
                 " (autostart)" if "--autostart" in sys.argv else "", is_admin())
    App("--tray" in sys.argv).run()


if __name__ == "__main__":
    main()
