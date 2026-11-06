import ctypes
import logging
import os
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

APP = "LiteRGB"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def program(script):
    if getattr(sys, "frozen", False):
        return sys.executable, []
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return pythonw, [os.path.abspath(script)]


def command_line(script, extra=()):
    exe, args = program(script)
    return subprocess.list2cmdline([exe] + args + ["--autostart", *extra])


def schtasks(*args):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=NO_WINDOW)


def task_exists():
    return schtasks("/Query", "/TN", APP).returncode == 0


def run_key_value():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, APP)[0]
    except OSError:
        return None


def old_logon_task():
    result = schtasks("/Query", "/TN", APP, "/XML")
    return result.returncode == 0 and "LogonTrigger" in result.stdout


def disabled_in_windows():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP)
            return bool(value) and value[0] & 1 == 1
    except OSError:
        return False


def mode():
    value = run_key_value()
    if not value or disabled_in_windows():
        return "off"
    return "admin" if "--launch-task" in value else "normal"


def remove_run_key():
    import winreg
    for path in (RUN_KEY, APPROVED_KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP)
        except OSError:
            pass


def write_run_key(script, admin):
    import winreg
    command = command_line(script, ["--launch-task"] if admin else [])
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, command)


def task_xml(script):
    exe, args = program(script)
    user = f'{os.environ.get("USERDOMAIN", "")}\\{os.environ.get("USERNAME", "")}'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(exe)}</Command>
      <Arguments>{escape(subprocess.list2cmdline(args + ["--autostart"]))}</Arguments>
      <WorkingDirectory>{escape(os.path.dirname(exe))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def write_task(script):
    path = os.path.join(tempfile.gettempdir(), "litergb_task.xml")
    with open(path, "w", encoding="utf-16") as f:
        f.write(task_xml(script))
    try:
        result = schtasks("/Create", "/TN", APP, "/XML", path, "/F")
    finally:
        os.remove(path)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or result.stdout.strip())


def apply(wanted, script):
    remove_run_key()
    if wanted != "admin" and is_admin() and task_exists():
        schtasks("/Delete", "/TN", APP, "/F")
    if wanted == "admin":
        write_task(script)
    if wanted != "off":
        write_run_key(script, wanted == "admin")
    logging.info("Autostart set to %s", wanted)


def needs_elevation(wanted):
    return not is_admin() and (wanted == "admin" or old_logon_task())


def apply_elevated(wanted, script):
    exe, args = program(script)
    params = subprocess.list2cmdline(args + ["--set-autostart", wanted])
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0)
    return result > 32


def refresh(script):
    current = mode()
    try:
        if current == "admin" and is_admin():
            write_task(script)
        if current != "off":
            write_run_key(script, current == "admin")
    except Exception as error:
        logging.warning("Autostart refresh failed: %s", error)
    return current


def launch_task():
    return schtasks("/Run", "/TN", APP).returncode == 0
