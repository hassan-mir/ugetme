"""Private state: one file per Claude Code session for pending checks, and the cleanup log."""
import json
import re
import threading
import time
from pathlib import Path
from typing import Optional

from ugetme import config

PENDING_MAX_AGE = 1800
MAX_SESSIONS = 50
LOG_MAX = 500
LOG_KEEP = 400
LOG_FIELD_CAP = 20000
_LOG_LOCK = threading.Lock()


def _sessions_dir() -> Path:
    return config.home() / "sessions"


def _log_file() -> Path:
    return config.home() / "log.jsonl"


def pairs(value) -> list:
    """The [heard, meant] pairs in `value` as tuples; anything else is dropped."""
    return [tuple(c) for c in value or [] if isinstance(c, list) and len(c) == 2]


def _session_file(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "default")[:80] or "default"
    return _sessions_dir() / f"{safe}.json"


def _read_session(session_id: str) -> dict:
    data = config.read_json(_session_file(session_id))
    return data if isinstance(data, dict) else {}


def _prune() -> None:
    try:
        files = sorted(_sessions_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for old in files[:-MAX_SESSIONS]:
        try:
            old.unlink()
        except OSError:
            pass


def _write_session(session_id: str, data: dict) -> None:
    config.write_json(_session_file(session_id), data)
    _prune()


def save_pending(session_id: str, text: str, changes=(), output_id: str = "") -> None:
    data = _read_session(session_id)
    data["pending"] = {"text": text, "changes": [list(c) for c in changes], "output_id": output_id,
                       "ts": time.time()}
    _write_session(session_id, data)


def pop_pending(session_id: str) -> Optional[dict]:
    data = _read_session(session_id)
    item = data.pop("pending", None)
    if item is None:
        return None
    _write_session(session_id, data)
    if not isinstance(item, dict) or not isinstance(item.get("text"), str):
        return None
    if time.time() - item.get("ts", 0) > PENDING_MAX_AGE:
        return None
    return {"text": item["text"], "changes": pairs(item.get("changes")), "output_id": str(item.get("output_id") or "")}


def _cap(value):
    if isinstance(value, str) and len(value) > LOG_FIELD_CAP:
        return value[:LOG_FIELD_CAP] + " […]"
    return value


def log(entry: dict, enabled: bool = True) -> None:
    if not enabled:
        return
    path = _log_file()
    line = json.dumps({"ts": int(time.time()), **{k: _cap(v) for k, v in entry.items()}}, ensure_ascii=False)
    with _LOG_LOCK:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        lines.append(line)
        if len(lines) > LOG_MAX:
            lines = lines[-LOG_KEEP:]
        config.write_text(path, "\n".join(lines) + "\n")


def read_log(limit: int = 50) -> list:
    try:
        lines = _log_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
