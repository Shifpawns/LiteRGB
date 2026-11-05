import io
import json
import os
import threading
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from tkinter import ttk

from PIL import Image, ImageTk

import theme
from i18n import t as T

API = "https://api.giphy.com/v1/gifs/search"
KEY_URL = "https://developers.giphy.com/dashboard/"
THUMB = 120
COLUMNS = 5


def fetch(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": "LiteRGB"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def search(key, query, limit=25):
    params = urllib.parse.urlencode({"api_key": key, "q": query, "limit": limit, "rating": "pg-13"})
    data = json.loads(fetch(f"{API}?{params}"))
    results = []
    for item in data.get("data", []):
        images = item.get("images", {})
        thumb = images.get("fixed_width_small_still", {}).get("url") or images.get("fixed_width_still", {}).get("url")
        full = images.get("downsized_large", {}).get("url") or images.get("original", {}).get("url")
        if thumb and full:
            results.append((item["id"], thumb, full))
    return results


class GifSearch(tk.Toplevel):
    def __init__(self, app, on_pick):
        super().__init__(app.root)
        self.app = app
        self.on_pick = on_pick
        self.photos = []
        self.title(T("GIF zoeken"))
        self.geometry("700x620")
        if theme.DARK:
            self.configure(bg=theme.BG)
            theme.dark_title_bar(self)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame)
        top.pack(fill="x")
        self.query = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda e: self.run_search())
        ttk.Button(top, text=T("Zoeken"), command=self.run_search).pack(side="left", padx=(8, 0))

        self.key_row = ttk.Frame(frame)
        self.key = tk.StringVar(value=app.config.get("giphy_key", ""))
        ttk.Label(self.key_row, text=T("GIPHY API-sleutel")).pack(side="left")
        ttk.Entry(self.key_row, textvariable=self.key, width=36).pack(side="left", padx=8)
        ttk.Button(self.key_row, text=T("Sleutel aanmaken"), command=lambda: webbrowser.open(KEY_URL)).pack(side="left")
        if not self.key.get():
            self.key_row.pack(fill="x", pady=(8, 0))

        self.status = ttk.Label(frame, foreground=theme.MUTED)
        self.status.pack(anchor="w", pady=6)

        self.grid_frame = ttk.Frame(frame)
        self.grid_frame.pack(fill="both", expand=True)

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x")
        ttk.Label(bottom, text="Powered by GIPHY", foreground=theme.MUTED).pack(side="right")
        ttk.Button(bottom, text=T("API-sleutel"), command=lambda: self.key_row.pack(fill="x", pady=(8, 0),
                                                                                  before=self.status)).pack(side="left")
        if not self.key.get():
            self.status.configure(text=T("Maak een gratis sleutel aan bij GIPHY en plak hem hierboven."))
        entry.focus_set()

    def run_search(self):
        key = self.key.get().strip()
        query = self.query.get().strip()
        if not key:
            self.status.configure(text=T("Vul eerst je GIPHY API-sleutel in."))
            self.key_row.pack(fill="x", pady=(8, 0), before=self.status)
            return
        if not query:
            return
        self.app.config["giphy_key"] = key
        self.app.save()
        self.status.configure(text=T("Zoeken..."))
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.photos = []

        def work():
            try:
                results = search(key, query)
                thumbs = []
                for gif_id, thumb, full in results:
                    try:
                        image = Image.open(io.BytesIO(fetch(thumb))).convert("RGB")
                        image.thumbnail((THUMB, THUMB))
                        thumbs.append((gif_id, image, full))
                    except Exception:
                        pass
                self.after(0, lambda: self.show(thumbs))
            except Exception as error:
                self.after(0, lambda e=error: self.status.configure(text=T("Zoeken mislukt: {error}", error=e)))

        threading.Thread(target=work, daemon=True).start()

    def show(self, thumbs):
        if not thumbs:
            self.status.configure(text=T("Niets gevonden."))
            return
        self.status.configure(text=T("Klik op een GIF om hem te gebruiken."))
        for index, (gif_id, image, full) in enumerate(thumbs):
            photo = ImageTk.PhotoImage(image)
            self.photos.append(photo)
            button = tk.Button(self.grid_frame, image=photo, relief="flat", bd=0, cursor="hand2",
                               bg=theme.BG if theme.DARK else None,
                               command=lambda g=gif_id, u=full: self.pick(g, u))
            button.grid(row=index // COLUMNS, column=index % COLUMNS, padx=3, pady=3)

    def pick(self, gif_id, url):
        self.status.configure(text=T("Downloaden..."))

        def work():
            try:
                folder = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LiteRGB", "gifs")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, f"{gif_id}.gif")
                if not os.path.exists(path):
                    data = fetch(url, 60)
                    with open(path, "wb") as f:
                        f.write(data)
                self.after(0, lambda: self.done(path))
            except Exception as error:
                self.after(0, lambda e=error: self.status.configure(text=T("Downloaden mislukt: {error}", error=e)))

        threading.Thread(target=work, daemon=True).start()

    def done(self, path):
        self.on_pick(path)
        self.destroy()
