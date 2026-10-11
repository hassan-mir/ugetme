"""Settings for ugetme: load, save, presets, the service token and atomic private writes."""
import hashlib
import json
import os
import platform
import secrets
import sys
import tempfile
import time
from pathlib import Path

PRESETS = {
    "none": {"turns": 0, "last_reply": False, "file_names": False, "project_outline": False},
    "light": {"turns": 2, "last_reply": True, "file_names": False, "project_outline": False},
    "balanced": {"turns": 6, "last_reply": True, "file_names": True, "project_outline": True},
    "full": {"turns": -1, "last_reply": True, "file_names": True, "project_outline": True},
}

DEFAULTS = {
    "engine": "claude",
    "mode": "auto",
    "port": 7337,
    "model": "sonnet",
    "effort": "low",
    "timeout_s": 45,
    "claude_bin": "",
    "claude_config_dir": "",
    "trusted_logins": [],
    "engine_env": {},
    "env_path": "",
    "openai": {"base_url": "", "api_key": "", "model": ""},
    "context": "balanced",
    "custom": dict(PRESETS["balanced"]),
    "live_context_minutes": 0,  # 0: no limit
    "check_highlight": "white",
    "scan_roots": [],
    "log": True,
}

MODES = {
    "auto": "Handy's main hotkey pastes clean text. In Claude Code, add << to check a prompt.",
    "check": "Handy's main hotkey pastes your own words. Claude Code checks every prompt of 5 words or more.",
    "manual": "Handy's main hotkey pastes your own words. ugetme cleans only with Handy's second hotkey or <<.",
}

CHOICES = {"engine": ("claude", "openai"), "mode": tuple(MODES), "context": tuple(PRESETS) + ("custom",),
           "check_highlight": ("white", "inverse", "none")}
MAX_TIMEOUT_S = 80
NESTED = ("custom", "openai")
TRUE_WORDS = ("1", "true", "on", "yes")
HOST = "127.0.0.1"  # not "localhost": it can resolve to ::1 first
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW: no console pops up


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def service_url(port: int, path: str = "") -> str:
    return f"http://{HOST}:{port}{path}"


def home() -> Path:
    return Path(os.environ.get("UGETME_HOME") or Path.home() / ".ugetme")


def settings_file() -> Path:
    return home() / "config.json"


def serve_log() -> Path:
    return home() / "serve.log"


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUE_WORDS
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_int(value, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return default
    return value


def load() -> dict:
    return normalize(read_json(settings_file(), {}))


def normalize(user) -> dict:
    """The settings as ugetme uses them: defaults, plus the valid values from `user`."""
    cfg = json.loads(json.dumps(DEFAULTS))
    if not isinstance(user, dict):
        user = {}
    for key, value in user.items():
        if key in NESTED:
            if isinstance(value, dict):
                cfg[key].update({k: v for k, v in value.items() if k in cfg[key]})
        elif key in cfg:
            cfg[key] = value
    for key, allowed in CHOICES.items():
        if cfg[key] not in allowed:
            cfg[key] = DEFAULTS[key]
    for key in ("port", "timeout_s", "live_context_minutes"):
        cfg[key] = _as_int(cfg[key], DEFAULTS[key])
    if not 0 < cfg["port"] < 65536:
        cfg["port"] = DEFAULTS["port"]
    cfg["timeout_s"] = min(cfg["timeout_s"] or DEFAULTS["timeout_s"], MAX_TIMEOUT_S)
    cfg["log"] = _as_bool(cfg["log"], True)
    if isinstance(cfg["engine_env"], dict):
        cfg["engine_env"] = {k: v for k, v in cfg["engine_env"].items() if isinstance(k, str) and isinstance(v, str)}
    else:
        cfg["engine_env"] = {}
    for key in ("model", "effort", "claude_bin", "claude_config_dir", "env_path"):
        if not isinstance(cfg[key], str):
            cfg[key] = DEFAULTS[key]
    if not cfg["model"]:
        cfg["model"] = DEFAULTS["model"]
    for key in ("base_url", "api_key", "model"):
        if not isinstance(cfg["openai"][key], str):
            cfg["openai"][key] = ""
    for key in ("scan_roots", "trusted_logins"):
        if not isinstance(cfg[key], list):
            cfg[key] = []
        cfg[key] = [r for r in cfg[key] if isinstance(r, str) and r]
    return cfg


def save(cfg: dict) -> None:
    write_json(settings_file(), cfg)


def write_text(path, text: str) -> None:
    """Atomic write. The file ends up with mode 0600, because mkstemp creates it so."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path, default=None):
    """The JSON in `path`, or `default` when the file is missing or is not JSON."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def token() -> str:
    """The service token. Created once, exclusively, so two services starting together agree on it."""
    path = home() / "token"
    for _ in range(20):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if value:
            return value
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            time.sleep(0.05)  # another process is writing it
            continue
        value = secrets.token_urlsafe(24)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
        return value
    raise OSError(f"cannot read or create {path}")


CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL",
                   "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")


def auth_fingerprint(env) -> str:
    """A short hash of the credential variables that pick a Claude account; empty when there are none."""
    parts = [f"{k}={env[k]}" for k in CREDENTIAL_VARS if env.get(k)]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16] if parts else ""


def context_settings(cfg: dict) -> dict:
    if cfg["context"] == "custom":
        return dict(cfg["custom"])
    return dict(PRESETS[cfg["context"]])


def normalize_config_dir(value: str) -> str:
    """One comparable form of a Claude login folder; empty means the default ~/.claude."""
    path = Path(value).expanduser() if value else Path.home() / ".claude"
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def trusted_logins(cfg: dict) -> list:
    """The trusted login folders in normal form, each once."""
    return list(dict.fromkeys(normalize_config_dir(folder) for folder in cfg["trusted_logins"]))
