"""Start the service at login: launchd (macOS), systemd --user (Linux), the Startup folder (Windows, WSL)."""
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List
from xml.sax.saxutils import escape

from ugetme import config

LABEL = "com.ugetme.serve"
UNIT = "ugetme.service"
_LAUNCHER = (Path(__file__).resolve().parents[1] / "bin" / "ugetme")
_STARTUP = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")  # inside %APPDATA%


def kind() -> str:
    override = os.environ.get("UGETME_PLATFORM")
    if override:
        return override
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    if config.is_wsl():
        return "wsl"
    return "linux" if shutil.which("systemctl") else "xdg"  # xdg: a desktop autostart entry, without systemd


def _in_plugin_cache(path: str) -> bool:
    p = path.replace("\\", "/")
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").replace("\\", "/")
    return "/plugins/cache/" in p or bool(root and p.startswith(root))


def stable_launcher() -> Path:
    """A copy of the package and its launcher in ~/.ugetme/app, which plugin updates cannot remove."""
    app = config.home() / "app"
    package = app / "ugetme"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(Path(__file__).resolve().parent, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    launcher = app / "bin" / "ugetme"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(_LAUNCHER.read_text(encoding="utf-8"), encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def serve_command() -> List[str]:
    installed = shutil.which("ugetme")
    if installed and not _in_plugin_cache(installed):
        return [installed, "serve"]
    return [sys.executable, str(stable_launcher()), "serve"]


def _run(cmd: List[str]) -> None:
    if os.environ.get("UGETME_AUTOSTART_DRY"):
        return
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _windows_startup_dir(k: str) -> Path:
    override = os.environ.get("UGETME_STARTUP_DIR")
    if override:
        return Path(override)
    if k == "windows":
        return Path(os.environ["APPDATA"]).joinpath(*_STARTUP)
    if not shutil.which("cmd.exe"):
        raise OSError("cmd.exe is not on PATH, so ugetme cannot find the Windows Startup folder (is WSL interop off?)")
    appdata = subprocess.run(["cmd.exe", "/c", "echo %APPDATA%"], capture_output=True, text=True, timeout=10).stdout.strip()
    unix = subprocess.run(["wslpath", "-u", appdata], capture_output=True, text=True, timeout=10).stdout.strip()
    return Path(unix).joinpath(*_STARTUP)


def target(k: str = None) -> Path:
    k = k or kind()
    override = os.environ.get("UGETME_AUTOSTART_DIR")
    if k == "macos":
        return Path(override or Path.home() / "Library" / "LaunchAgents") / f"{LABEL}.plist"
    if k == "linux":
        return Path(override or Path.home() / ".config" / "systemd" / "user") / UNIT
    if k == "xdg":
        config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(override or Path(config_home) / "autostart") / "ugetme.desktop"
    return _windows_startup_dir(k) / "ugetme.vbs"


def _vbs(arg: str) -> str:
    return '""' + arg.replace('"', "") + '""'


def content(k: str, cmd: List[str]) -> str:
    if k == "macos":
        args = "".join(f"\n    <string>{escape(a)}</string>" for a in cmd)
        log = escape(str(config.serve_log()))
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                f'<plist version="1.0">\n<dict>\n  <key>Label</key>\n  <string>{LABEL}</string>\n'
                f'  <key>ProgramArguments</key>\n  <array>{args}\n  </array>\n'
                '  <key>RunAtLoad</key>\n  <true/>\n'
                f'  <key>StandardOutPath</key>\n  <string>{log}</string>\n'
                f'  <key>StandardErrorPath</key>\n  <string>{log}</string>\n</dict>\n</plist>\n')
    if k == "linux":
        return ("[Unit]\nDescription=ugetme text cleanup service\n\n"
                f"[Service]\nExecStart={shlex.join(cmd)}\nRestart=on-failure\n\n"
                "[Install]\nWantedBy=default.target\n")
    if k == "xdg":
        return ("[Desktop Entry]\nType=Application\nName=ugetme\nComment=ugetme text cleanup service\n"
                f"Exec={' '.join(_desktop_quote(a) for a in cmd)}\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n")
    if k == "wsl":
        distro = os.environ.get("WSL_DISTRO_NAME", "")
        line = "wsl.exe" + (f" -d {_vbs(distro)}" if distro else "") + " -- " + " ".join(_vbs(a) for a in cmd)
    else:
        pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
        args = [pythonw] + cmd[1:] if cmd and cmd[0] == sys.executable else [pythonw, "-m", "ugetme", "serve"]
        line = " ".join(_vbs(a) for a in args)
    return f'CreateObject("WScript.Shell").Run "{line}", 0, False\r\n'


def _desktop_quote(arg: str) -> str:
    """Quote one Exec argument as the Desktop Entry spec asks."""
    if arg and not any(c in arg for c in ' \t"\'\\><~|&;$*?#()`'):
        return arg
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'


def install() -> Path:
    k = kind()
    path = target(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content(k, serve_command()).encode("utf-8"))  # keeps \r\n; write_text(newline=) needs 3.10
    if k == "macos":
        _run(["launchctl", "load", "-w", str(path)])
    elif k == "linux":
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", UNIT])
    return path


def installed() -> bool:
    try:
        return target().exists()
    except (OSError, subprocess.SubprocessError, KeyError):
        return False


def remove() -> bool:
    k = kind()
    path = target(k)
    if not path.exists():
        return False
    if k == "macos":
        _run(["launchctl", "unload", "-w", str(path)])
    elif k == "linux":
        _run(["systemctl", "--user", "disable", "--now", UNIT])
    path.unlink()
    return True
