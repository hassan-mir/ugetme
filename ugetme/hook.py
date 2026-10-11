"""Claude Code hook logic: send context, run checks (<< or mode check) through the service, learn from edits.

Never loses a prompt: every path exits 0, and a << prompt is never sent raw."""
import json
import os
import shutil
import sys
from typing import Optional

from ugetme import client, clipboard, config, learn, markers, output, state

REPLY_MAX_WORDS = 15
PASTE_BACK = 0.9
SENSOR_MIN_WORDS = 5
CHECK_MIN_WORDS = 5  # mode check: shorter prompts ("y", "run the tests") go through as they are


def _ctx(event: dict) -> dict:
    return {"cwd": str(event.get("cwd") or ""), "transcript_path": str(event.get("transcript_path") or ""),
            "config_dir": os.environ.get("CLAUDE_CONFIG_DIR", ""), "auth": config.auth_fingerprint(os.environ)}


def session_start(event: dict) -> None:
    if not config.settings_file().exists():
        # No setup yet (plugin-only user): the engine uses this session's login and PATH.
        cfg = config.load()
        cfg["claude_config_dir"] = os.environ.get("CLAUDE_CONFIG_DIR", "")
        cfg["claude_bin"] = shutil.which("claude") or ""
        cfg["env_path"] = os.environ.get("PATH", "")
        config.save(cfg)
    client.ensure_running(wait_s=2.0)


def _service(method: str, path: str, body=None, timeout: float = 0.3) -> Optional[dict]:
    """The service's answer, or None when the service cannot be reached."""
    try:
        return client.request(method, path, body, timeout=timeout)
    except client.ClientError:
        return None


def _learned(output_id: str, sent: str) -> Optional[dict]:
    res = _service("POST", "/ugetme/learn", {"output_id": output_id, "sent": sent}, timeout=2.0)
    pairs = state.pairs(res.get("learned")) if res is not None else []
    return output.learned(pairs) if pairs else None


def _reply(pending: dict, stripped: str, up: bool):
    """The answer to a pending check, or False when the prompt is not an answer."""
    if learn.similarity(stripped, pending["text"]) >= PASTE_BACK:
        return _learned(pending["output_id"], stripped) if up else None
    if stripped == "." or stripped.rstrip(".!").lower() in output.CONFIRM_WORDS:
        return output.confirmed(pending["text"])
    if 0 < len(stripped.split()) < REPLY_MAX_WORDS:
        return output.answer(pending["text"], pending["changes"])
    return False


def _check(marked: str, session: str, ctx: dict, up: bool, asked: bool = True) -> dict:
    """asked: the user typed <<. Without it (mode check), a failure lets the prompt through."""
    report = output.failed if asked else output.skipped
    if not up and not client.ensure_running(wait_s=8.0 if asked else 2.0):
        return output.not_running() if asked else output.skipped("ugetme is not running")
    try:
        res = client.clean(marked, ctx)
    except client.ClientError as e:
        return report(str(e))
    if res.get("failed"):
        return report(res["failed"])
    changes = state.pairs(res.get("changes"))
    state.save_pending(session, res["clean"], changes, res.get("id", ""))
    copied = clipboard.copy(res["clean"])
    return output.block(res.get("view") or res["clean"], marked, res.get("unclear"), copied, changes)


def _sensor(stripped: str) -> Optional[dict]:
    res = _service("GET", "/ugetme/recent")
    if res is None:
        return None
    outputs = res.get("outputs") or []
    best, score = None, 0.0
    for item in outputs:
        s = learn.similarity(stripped, str(item.get("clean") or ""))
        if s > score:
            best, score = item, s
    if best is None or score < learn.MIN_SIMILARITY or stripped == str(best.get("clean") or "").strip():
        return None
    return _learned(str(best.get("id") or ""), stripped)


def prompt(event: dict) -> Optional[dict]:
    if os.environ.get("UGETME_INNER"):
        return None
    text = str(event.get("prompt") or "")
    stripped = text.strip()
    session = str(event.get("session_id") or "default")
    ctx = _ctx(event)
    up = client.health(timeout=0.3) is not None
    if up:
        _service("POST", "/ugetme/context", ctx)
    marked = markers.clean_request(text)
    command = stripped.startswith(("/", "!"))
    pending = None
    if not command:
        pending = state.pop_pending(session)
        if pending is not None and marked is None:
            reply = _reply(pending, stripped, up)
            if reply is not False:
                return reply
    if marked is not None:
        return _check(marked, session, ctx, up)
    if not command and len(stripped.split()) >= CHECK_MIN_WORDS and config.load()["mode"] == "check":
        if pending is not None and learn.similarity(stripped, pending["text"]) >= learn.MIN_SIMILARITY:
            return _learned(pending["output_id"], stripped) if up else None  # the user's edit of the check: send it
        return _check(text, session, ctx, up, asked=False)
    if up and len(stripped.split()) >= SENSOR_MIN_WORDS:
        return _sensor(stripped)
    return None


def run(kind: str) -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    try:
        out = session_start(event) if kind == "session-start" else prompt(event)
    except Exception as e:  # never break the user's prompt
        text = str(event.get("prompt") or "")
        out = output.failed(f"internal error: {type(e).__name__}") if markers.clean_request(text) else None
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0
