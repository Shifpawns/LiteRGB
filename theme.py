import ctypes
from tkinter import ttk

MUTED = "#777777"
DARK = False

BG = "#1e1f22"
PANEL = "#26282c"
FIELD = "#313338"
BORDER = "#3a3d43"
TEXT = "#e3e5e8"
DIM = "#8b9096"
ACCENT = "#3d8bfd"


def system_prefers_dark():
    try:
        import winreg
        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def resolve(choice):
    if choice == "dark":
        return True
    if choice == "light":
        return False
    return system_prefers_dark()


def dark_title_bar(root):
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def apply(root, choice):
    global DARK, MUTED
    DARK = resolve(choice)
    if not DARK:
        MUTED = "#777777"
        return

    MUTED = DIM
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)

    style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER,
                    lightcolor=PANEL, darkcolor=PANEL, troughcolor=FIELD, focuscolor=ACCENT,
                    selectbackground=ACCENT, selectforeground="#ffffff", insertcolor=TEXT)
    style.map(".", foreground=[("disabled", DIM)])
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TNotebook", background=BG, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=PANEL, foreground=DIM, padding=(10, 4), bordercolor=BORDER)
    style.map("TNotebook.Tab", background=[("selected", FIELD)], foreground=[("selected", TEXT)])
    style.configure("TButton", background=FIELD, foreground=TEXT, bordercolor=BORDER, padding=(10, 4))
    style.map("TButton", background=[("active", BORDER), ("disabled", PANEL)])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=BG, foreground=TEXT, indicatorbackground=FIELD,
                        indicatorforeground=TEXT)
        style.map(name, background=[("active", BG)], indicatorbackground=[("selected", ACCENT)])
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT, arrowcolor=TEXT)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])
    style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT)
    style.map("TEntry", fieldbackground=[("readonly", FIELD)])
    style.configure("Horizontal.TScale", background=ACCENT, troughcolor=FIELD, bordercolor=BORDER)
    style.configure("TSeparator", background=BORDER)

    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    dark_title_bar(root)


def style_listbox(listbox):
    if DARK:
        listbox.configure(bg=PANEL, fg=TEXT, selectbackground=ACCENT, selectforeground="#ffffff",
                          highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER, relief="flat")
