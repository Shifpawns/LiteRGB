import io
import json
import os
import threading
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

from PIL import Image, ImageSequence, ImageTk

import theme
from i18n import t as T

API = "https://api.giphy.com/v1/gifs/search"
KEY_URL = "https://developers.giphy.com/dashboard/"
PROXY = "https://gif.vanbommel.org"
THUMB = 120
COLUMNS = 5
MAX_THUMB_FRAMES = 60


def animated_url(still):
    return still.replace("_s.gif", ".gif")


def thumb_frames(url):
    source = Image.open(io.BytesIO(fetch(url)))
    frames = []
    for frame in ImageSequence.Iterator(source):
        image = frame.convert("RGB")
        image.thumbnail((THUMB, THUMB))
        delay = max(40, frame.info.get("duration", source.info.get("duration", 100)) or 100)
        frames.append((image, delay))
        if len(frames) >= MAX_THUMB_FRAMES:
            break
    return frames


def fetch(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": "LiteRGB"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def search_proxy(proxy, query):
    params = urllib.parse.urlencode({"q": query})
    data = json.loads(fetch(f"{proxy.rstrip('/')}/search?{params}"))
    if "error" in data:
        raise OSError(data["error"])
    return [(item["id"], item["thumb"], item["url"]) for item in data.get("data", [])]


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
        self.generation = 0
        self.pool = ThreadPoolExecutor(max_workers=6)
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

        self.status = ttk.Label(frame, foreground=theme.MUTED)
        self.status.pack(anchor="w", pady=6)

        self.grid_frame = ttk.Frame(frame)
        self.grid_frame.pack(fill="both", expand=True)

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x")
        ttk.Label(bottom, text="Powered by GIPHY", foreground=theme.MUTED).pack(side="right")
        ttk.Button(bottom, text=T("API-sleutel"), command=lambda: self.key_row.pack(fill="x", pady=(8, 0),
                                                                                  before=self.status)).pack(side="left")
        entry.focus_set()

    def run_search(self):
        key = self.key.get().strip()
        query = self.query.get().strip()
        if not query:
            return
        if key != self.app.config.get("giphy_key", ""):
            self.app.config["giphy_key"] = key
            self.app.save()
        proxy = self.app.config.get("gif_proxy") or PROXY
        self.status.configure(text=T("Zoeken..."))
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.photos = []
        self.generation += 1
        generation = self.generation

        def work():
            try:
                results = search(key, query) if key else search_proxy(proxy, query)

                def still(result):
                    gif_id, thumb, full = result
                    try:
                        image = Image.open(io.BytesIO(fetch(thumb))).convert("RGB")
                        image.thumbnail((THUMB, THUMB))
                        return gif_id, image, full, thumb
                    except Exception:
                        return None

                with ThreadPoolExecutor(max_workers=8) as stills:
                    thumbs = [t for t in stills.map(still, results) if t]
                self.after(0, lambda: self.show(thumbs, generation))
            except Exception as error:
                self.after(0, lambda e=error: self.status.configure(text=T("Zoeken mislukt: {error}", error=e)))

        threading.Thread(target=work, daemon=True).start()

    def show(self, thumbs, generation):
        if generation != self.generation:
            return
        if not thumbs:
            self.status.configure(text=T("Niets gevonden."))
            return
        self.status.configure(text=T("Klik op een GIF om hem te gebruiken."))
        for index, (gif_id, image, full, still) in enumerate(thumbs):
            photo = ImageTk.PhotoImage(image)
            self.photos.append(photo)
            button = tk.Button(self.grid_frame, image=photo, relief="flat", bd=0, cursor="hand2",
                               bg=theme.BG if theme.DARK else None,
                               command=lambda g=gif_id, u=full: self.pick(g, u))
            button.grid(row=index // COLUMNS, column=index % COLUMNS, padx=3, pady=3)
            self.load_animation(button, animated_url(still), generation)

    def load_animation(self, button, url, generation):
        def work():
            try:
                frames = thumb_frames(url)
            except Exception:
                return
            if len(frames) > 1:
                self.after(0, lambda: self.start_animation(button, frames, generation))

        self.pool.submit(work)

    def start_animation(self, button, frames, generation):
        if generation != self.generation:
            return
        photos = [(ImageTk.PhotoImage(image), delay) for image, delay in frames]
        self.photos.extend(p for p, _ in photos)
        self.animate(button, photos, 0, generation)

    def animate(self, button, photos, index, generation):
        if generation != self.generation:
            return
        photo, delay = photos[index % len(photos)]
        try:
            button.configure(image=photo)
        except tk.TclError:
            return
        self.after(delay, lambda: self.animate(button, photos, index + 1, generation))

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
