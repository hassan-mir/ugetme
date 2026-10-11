"""Read and write the system clipboard (macOS, Linux, Windows, WSL)."""
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

from ugetme.config import NO_WINDOW, is_wsl as _is_wsl

_PS = ("[Console]::InputEncoding=[Text.Encoding]::UTF8; "
       "Set-Clipboard -Value ([Console]::In.ReadToEnd())")
_PS_READ = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"


def candidates() -> list:
    if sys.platform == "darwin":
        return [["pbcopy"]]
    if sys.platform == "win32":
        return [["powershell.exe", "-NoProfile", "-Command", _PS]]
    cands = []
    if _is_wsl():
        cands.append(["powershell.exe", "-NoProfile", "-Command", _PS])
    if os.environ.get("WAYLAND_DISPLAY"):
        cands.append(["wl-copy"])
    cands += [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    return cands


TOTAL_TIMEOUT_S = 5


def _run_first(cmds: list, **kwargs) -> Optional[subprocess.CompletedProcess]:
    """The result of the first tool that is on PATH and succeeds, or None."""
    deadline = time.monotonic() + TOTAL_TIMEOUT_S  # all tools together, so the hook stays inside its time limit
    for cmd in cmds:
        remaining = deadline - time.monotonic()
        if remaining <= 0.2:
            break
        if not shutil.which(cmd[0]):
            continue
        try:
            result = subprocess.run(cmd, stderr=subprocess.DEVNULL, timeout=remaining, **kwargs, **NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return result
    return None


def copy(text: str) -> bool:
    if os.environ.get("UGETME_NO_CLIPBOARD"):
        return False
    return _run_first(candidates(), input=text.encode("utf-8"), stdout=subprocess.DEVNULL) is not None


def read_candidates() -> list:
    if sys.platform == "darwin":
        return [["pbpaste"]]
    if sys.platform == "win32" or _is_wsl():
        return [["powershell.exe", "-NoProfile", "-Command", _PS_READ]]
    cands = []
    if os.environ.get("WAYLAND_DISPLAY"):
        cands.append(["wl-paste", "--no-newline", "--type", "text"])
    return cands + [["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]]


def tool() -> Optional[str]:
    """The clipboard tool ugetme would use, without reading the clipboard."""
    return next((cmd[0] for cmd in read_candidates() if shutil.which(cmd[0])), None)


def paste() -> Optional[str]:
    """The text on the clipboard ("" when it has none), or None when no tool can read it."""
    result = _run_first(read_candidates(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    return None if result is None else result.stdout.decode("utf-8", "replace").rstrip("\r\n")
