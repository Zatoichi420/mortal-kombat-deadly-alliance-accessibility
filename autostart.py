"""Register / remove the talking-menu daemon as a per-user background service.

Works the same whether this is the downloaded single-file binary (PyInstaller,
`sys.frozen`) or a plain `python menu_reader.py` checkout. No admin rights,
no extra dependencies - it drives the OS's own per-user service manager:

    macOS    launchd LaunchAgent   ~/Library/LaunchAgents/<LABEL>.plist
    Linux    systemd --user unit   ~/.config/systemd/user/<SERVICE>.service
    Windows  Scheduled Task        run at logon, hidden, via a .vbs shim

Called from menu_reader.py's --install / --uninstall / --status.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

LABEL = "com.orlando.mkda-menu-reader"   # macOS
SERVICE = "mkda-menu-reader"             # Linux unit / Windows task name
DESCRIPTION = "MK: Deadly Alliance talking-menu daemon"
APP_DIR_NAME = "mkda-talking-menu"


class AutostartError(RuntimeError):
    pass


def _app_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / APP_DIR_NAME


def _target_argv() -> list[str]:
    """The command the background service should run.

    Frozen (the downloaded binary): copy it into a stable per-user directory
    first, so moving or deleting the download doesn't break autostart - this is
    what the shell/PowerShell installers do too. From a source checkout: run the
    script in place, which is what a contributor wants.
    """
    if getattr(sys, "frozen", False):
        app = _app_dir()
        app.mkdir(parents=True, exist_ok=True)
        dst = app / Path(sys.executable).name
        if os.path.realpath(sys.executable) != os.path.realpath(dst):
            shutil.copy2(sys.executable, dst)
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return [os.path.realpath(dst)]
    return [os.path.realpath(sys.executable), os.path.realpath(sys.argv[0])]


# ---------------------------------------------------------------- macOS

def _macos_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _macos_log() -> Path:
    return Path.home() / "Library" / "Logs" / f"{SERVICE}.log"


def _macos_install() -> str:
    log = _macos_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "Label": LABEL,
        "ProgramArguments": _target_argv(),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    path = _macos_plist()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        plistlib.dump(doc, fh)

    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True)
    res = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise AutostartError(res.stderr.strip() or "launchctl bootstrap failed")
    # keep RetroArch's command port responsive when it's not the focused app
    subprocess.run(["defaults", "write", "org.libretro.RetroArch",
                    "NSAppSleepDisabled", "-bool", "YES"], capture_output=True)
    return f"LaunchAgent installed: {path}\nlog: {log}"


def _macos_uninstall() -> str:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True)
    _macos_plist().unlink(missing_ok=True)
    return "LaunchAgent removed."


def _macos_status() -> str:
    if not _macos_plist().exists():
        return "not installed"
    uid = os.getuid()
    res = subprocess.run(["launchctl", "print", f"gui/{uid}/{LABEL}"],
                         capture_output=True, text=True)
    for line in res.stdout.splitlines():
        if "state = " in line or "pid = " in line:
            return "installed; " + line.strip()
    return "installed (not currently loaded)"


# ---------------------------------------------------------------- Linux

def _linux_unit() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "systemd" / "user" / f"{SERVICE}.service"


def _linux_install() -> str:
    exec_start = " ".join(shlex.quote(a) for a in _target_argv())
    unit = (
        "[Unit]\n"
        f"Description={DESCRIPTION}\n"
        "After=graphical-session.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_start}\n"
        "Restart=always\n"
        "RestartSec=3\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    path = _linux_unit()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    res = subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise AutostartError(res.stderr.strip() or "systemctl enable failed")
    return (f"systemd --user unit installed: {path}\n"
            f"log: journalctl --user -u {SERVICE} -f")


def _linux_uninstall() -> str:
    subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE],
                   capture_output=True)
    _linux_unit().unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    return "systemd --user unit removed."


def _linux_status() -> str:
    if not _linux_unit().exists():
        return "not installed"
    res = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                         capture_output=True, text=True)
    return f"installed; {res.stdout.strip() or 'unknown'}"


# ---------------------------------------------------------------- Windows

def _windows_vbs_body(argv: list[str], log: Path) -> str:
    """A hidden `cmd /c "<exe>" "<args>" >> "<log>" 2>&1` line for wscript.
    VBScript doubles every embedded quote; the leading empty pair keeps cmd
    from stripping the real quotes. This mirrors install/windows/install.ps1."""
    body = 'cmd /c """"' + argv[0] + '""'
    for extra in argv[1:]:
        body += ' ""' + extra + '""'
    body += ' >> ""' + str(log) + '"" 2>&1""'
    return ('Dim sh: Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.Run "{body}", 0, False\r\n')


def _windows_install() -> str:
    work = _app_dir()
    work.mkdir(parents=True, exist_ok=True)
    log = work / "menu_reader.log"
    vbs = work / "run.vbs"
    vbs.write_text(_windows_vbs_body(_target_argv(), log), encoding="ascii")

    res = subprocess.run(
        ["schtasks", "/Create", "/TN", SERVICE, "/TR", f'wscript.exe "{vbs}"',
         "/SC", "ONLOGON", "/RL", "LIMITED", "/F"],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise AutostartError(res.stdout.strip() or res.stderr.strip()
                             or "schtasks /Create failed")
    subprocess.run(["schtasks", "/Run", "/TN", SERVICE], capture_output=True)
    return f"Scheduled Task '{SERVICE}' installed (runs at logon).\nlog: {log}"


def _windows_uninstall() -> str:
    subprocess.run(["schtasks", "/End", "/TN", SERVICE], capture_output=True)
    subprocess.run(["schtasks", "/Delete", "/TN", SERVICE, "/F"],
                   capture_output=True)
    work = _app_dir()
    for name in ("run.vbs",):
        (work / name).unlink(missing_ok=True)
    return "Scheduled Task removed."


def _windows_status() -> str:
    res = subprocess.run(["schtasks", "/Query", "/TN", SERVICE],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return "not installed"
    return "installed; " + res.stdout.strip().splitlines()[-1]


# ---------------------------------------------------------------- dispatch

def _platform_funcs():
    if sys.platform == "darwin":
        return _macos_install, _macos_uninstall, _macos_status
    if sys.platform.startswith("linux"):
        return _linux_install, _linux_uninstall, _linux_status
    if os.name == "nt":
        return _windows_install, _windows_uninstall, _windows_status
    raise AutostartError(f"autostart isn't supported on {sys.platform!r} - "
                         "run the daemon by hand when you play instead.")


def install() -> str:
    return _platform_funcs()[0]()


def uninstall() -> str:
    return _platform_funcs()[1]()


def status() -> str:
    return _platform_funcs()[2]()
