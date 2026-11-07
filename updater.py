import json
import os
import subprocess
import sys
import urllib.request

REPO = "Shifpawns/LiteRGB"
ASSET = "LiteRGB.exe"


def version_tuple(text):
    parts = []
    for piece in text.lstrip("vV").split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def latest_release():
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "LiteRGB-updater"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        release = json.load(response)
    url = next((a["browser_download_url"] for a in release.get("assets", []) if a["name"] == ASSET), None)
    return release.get("tag_name", ""), url, release.get("body", "")


CHANGELOG_URL = f"https://raw.githubusercontent.com/{REPO}/main/CHANGELOG.md"
RELEASES_URL = f"https://github.com/{REPO}/releases"


def changelog():
    request = urllib.request.Request(CHANGELOG_URL, headers={"User-Agent": "LiteRGB-updater"})
    with urllib.request.urlopen(request, timeout=10) as response:
        text = response.read().decode("utf-8")
    sections = []
    for block in text.split("\n## ")[1:]:
        version, _, body = block.partition("\n")
        sections.append((version.strip(), body.strip()))
    return sections


def changes_since(current):
    sections = changelog()
    newer = [s for s in sections if version_tuple(s[0]) > version_tuple(current)]
    return newer or sections[:3]


def check(current):
    tag, url, notes = latest_release()
    if url and version_tuple(tag) > version_tuple(current):
        return tag, url, notes
    return None


def is_frozen():
    return getattr(sys, "frozen", False)


def cleanup_old():
    if not is_frozen():
        return
    old = sys.executable + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass


def install(url):
    exe = sys.executable
    new = exe + ".new"
    old = exe + ".old"
    request = urllib.request.Request(url, headers={"User-Agent": "LiteRGB-updater"})
    with urllib.request.urlopen(request, timeout=60) as response, open(new, "wb") as f:
        while True:
            block = response.read(1 << 16)
            if not block:
                break
            f.write(block)
    if os.path.getsize(new) < 1_000_000:
        os.remove(new)
        raise OSError("download is onvolledig")
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)
    os.replace(new, exe)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_MEI", "_PYI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([exe, "--after-update"], close_fds=True, env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
