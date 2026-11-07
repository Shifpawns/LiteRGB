import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

import theme
import updater
from i18n import t as T


class ChangelogWindow(tk.Toplevel):
    def __init__(self, app, current):
        super().__init__(app.root)
        self.title(T("Wat is er nieuw"))
        self.geometry("560x460")
        if theme.DARK:
            self.configure(bg=theme.BG)
            theme.dark_title_bar(self)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        colors = {"bg": theme.FIELD, "fg": theme.TEXT} if theme.DARK else {}
        self.text = tk.Text(frame, wrap="word", relief="flat", padx=10, pady=8, height=10,
                            font=("Segoe UI", 10), highlightthickness=0, **colors)
        scroll = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        bottom = ttk.Frame(frame)
        bottom.pack(side="bottom", fill="x", pady=(10, 0))
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.text.tag_configure("title", font=("Segoe UI", 12, "bold"), spacing1=8, spacing3=4)
        self.text.tag_configure("item", lmargin1=8, lmargin2=22, spacing1=2)
        self.text.insert("end", T("Laden..."))
        self.text.configure(state="disabled")

        ttk.Button(bottom, text=T("Bekijk op GitHub"),
                   command=lambda: webbrowser.open(updater.RELEASES_URL)).pack(side="left")
        ttk.Button(bottom, text=T("Sluiten"), command=self.destroy).pack(side="right")

        self.current = current
        threading.Thread(target=self.load, daemon=True).start()

    def load(self):
        try:
            sections = updater.changes_since(self.current)
            self.after(0, lambda: self.show(sections))
        except Exception as error:
            self.after(0, lambda e=error: self.show_text(T("Kon de wijzigingen niet laden: {error}", error=e)))

    def show_text(self, text):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", text)
        self.text.configure(state="disabled")

    def show(self, sections):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for version, body in sections:
            title = T("Versie {version}", version=version)
            if version == self.current:
                title += "  " + T("(jouw versie)")
            self.text.insert("end", title + "\n", "title")
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    self.text.insert("end", "•  " + line[2:] + "\n", "item")
                elif line:
                    self.text.insert("end", line + "\n", "item")
        self.text.configure(state="disabled")
