"""Find and change Handy's settings file so its AI post-processing uses ugetme."""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from ugetme import config
from ugetme.config import is_wsl as _is_wsl

APP_DIR = "com.pais.handy"
NAME = "settings_store.json"
PROMPT = {"id": "ugetme", "name": "ugetme", "prompt": "${output}"}
CUSTOM = {"id": "custom", "label": "Custom", "models_endpoint": "/models"}
PROVIDER_ID = CUSTOM["id"]
PROMPT_ID = PROMPT["id"]
MODEL = "ugetme"


def candidate_paths() -> List[Path]:
    override = os.environ.get("UGETME_HANDY_SETTINGS")
    if override:
        return [Path(override)]
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / APP_DIR / NAME]
    if sys.platform == "win32":
        return [Path(os.environ.get("APPDATA", "")) / APP_DIR / NAME]
    paths = []
    if _is_wsl():
        paths += [Path(p) for p in sorted(glob.glob(f"/mnt/c/Users/*/AppData/Roaming/{APP_DIR}/{NAME}"))]
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    paths += [data / APP_DIR / NAME, Path.home() / ".config" / APP_DIR / NAME]
    return paths


def find_settings() -> Optional[Path]:
    for path in candidate_paths():
        if path.is_file():
            return path
    return None


def is_running() -> bool:
    override = os.environ.get("UGETME_HANDY_RUNNING")
    if override is not None:
        return override == "1"
    try:
        if sys.platform == "win32" or _is_wsl():
            out = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq handy.exe", "/NH"], capture_output=True,
                                 text=True, timeout=10).stdout
            return "handy.exe" in out.lower()
        for name in ("Handy", "handy"):
            if shutil.which("pgrep") and subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=5).returncode == 0:
                return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    return False


def _load(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Handy's settings are not a JSON object")
    return data, (data["settings"] if isinstance(data.get("settings"), dict) else data)


def _state_path() -> Path:
    return config.home() / "handy.json"


def _swapped() -> bool:
    data = config.read_json(_state_path())
    return bool(data.get("swapped")) if isinstance(data, dict) else False


def _set_swapped(value: bool) -> None:
    config.write_json(_state_path(), {"swapped": value})


def _base_url(port: int) -> str:
    return config.service_url(port, "/v1")


def _custom(providers) -> Optional[dict]:
    if not isinstance(providers, list):
        return None
    return next((p for p in providers if isinstance(p, dict) and p.get("id") == PROVIDER_ID), None)


def _hotkeys(s: dict):
    """Handy's plain hotkey and its post-processing hotkey."""
    bindings = s.get("bindings") if isinstance(s.get("bindings"), dict) else {}
    return tuple(b if isinstance(b, dict) else None
                 for b in (bindings.get("transcribe"), bindings.get("transcribe_with_post_process")))


def _set_up(s: dict) -> bool:
    return bool(s.get("post_process_enabled") and s.get("post_process_provider_id") == PROVIDER_ID
                and s.get("post_process_selected_prompt_id") == PROMPT_ID)


def is_set_up(path: Path) -> bool:
    try:
        return _set_up(_load(Path(path))[1])
    except (OSError, ValueError, KeyError):
        return False


def _point_at_ugetme(s: dict, port: int, token: str) -> None:
    """Make ugetme Handy's post-processing provider, with its own prompt."""
    providers = s.setdefault("post_process_providers", [])
    custom = _custom(providers)
    if custom is None:
        custom = dict(CUSTOM)
        providers.append(custom)
    custom["base_url"] = _base_url(port)
    custom["allow_base_url_edit"] = True
    custom["supports_structured_output"] = False  # ugetme answers plain text, not Handy's JSON schema
    s["post_process_provider_id"] = PROVIDER_ID
    s.setdefault("post_process_models", {})[PROVIDER_ID] = MODEL
    s.setdefault("post_process_api_keys", {})[PROVIDER_ID] = token
    s["post_process_prompts"] = [p for p in s.get("post_process_prompts", []) if not (isinstance(p, dict) and p.get("id") == PROMPT_ID)]
    s["post_process_prompts"].append(dict(PROMPT))
    s["post_process_selected_prompt_id"] = PROMPT_ID
    s["post_process_enabled"] = True


def _swap_hotkeys(s: dict, swapped: bool) -> None:
    """Exchange the plain and the post-processing hotkeys, and record the new state."""
    a, b = _hotkeys(s)
    if isinstance(a, dict) and isinstance(b, dict):
        a["current_binding"], b["current_binding"] = b.get("current_binding"), a.get("current_binding")
        _set_swapped(swapped)


def configure(path: Path, port: int, token: str, swap_hotkeys: Optional[bool] = None,
              auto_submit: Optional[bool] = None) -> Optional[Path]:
    """Point Handy at ugetme. The backup is taken only from settings that are not set up yet, so undo
    always returns to the user's own settings. swap_hotkeys True puts ugetme on the main hotkey, False
    puts it back on the second one, None leaves the hotkeys as they are."""
    path = Path(path)
    data, s = _load(path)
    backup = None
    if not _set_up(s):
        backup = path.with_name(f"{NAME}.ugetme-backup-{time.strftime('%Y%m%d-%H%M%S')}-{len(backups(path)):03d}")
        shutil.copy2(path, backup)
        _set_swapped(False)
    _point_at_ugetme(s, port, token)
    if swap_hotkeys is not None and swap_hotkeys != _swapped():
        _swap_hotkeys(s, swap_hotkeys)
    if auto_submit is not None:
        s["auto_submit"] = bool(auto_submit)
        if auto_submit:
            s["auto_submit_key"] = "enter"
    config.write_json(path, data)
    return backup


def backups(path: Path) -> List[Path]:
    return sorted(Path(path).parent.glob(f"{NAME}.ugetme-backup-*"))


def undo(path: Path) -> Optional[Path]:
    found = backups(path)
    if not found:
        return None
    shutil.copy2(found[-1], path)
    _set_swapped(False)
    return found[-1]


def describe(port: Optional[int] = None) -> str:
    path = find_settings()
    if path is None:
        return "not found"
    try:
        _, s = _load(Path(path))
    except (OSError, ValueError, KeyError):
        return "found, unreadable"
    custom = _custom(s.get("post_process_providers")) or {}
    url = custom.get("base_url") if isinstance(custom.get("base_url"), str) else "?"
    if _set_up(s):
        plain, clean = ((b or {}).get("current_binding") for b in _hotkeys(s))
        expected = _base_url(port) if port else None
        if expected and url == f"http://localhost:{port}/v1":
            expected = url  # a URL written with localhost also reaches ugetme
        if expected and url != expected:
            return (f"set up, but Handy points to port {url.rsplit(':', 1)[-1].split('/')[0]} "
                    f"and ugetme uses {port}. Quit Handy and run: ugetme handy setup")
        if plain and plain == clean:
            return (f"set up, but both Handy hotkeys are {plain}, so Handy runs plain transcription. "
                    "Give Transcribe a different key in Handy's settings.")
        return f"set up ({url}) · ugetme hotkey: {clean or '?'}"
    return "found, not set up for ugetme"
