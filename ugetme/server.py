"""The ugetme service: an OpenAI-compatible endpoint plus small ugetme endpoints, on 127.0.0.1 only."""
import errno
import hmac
import json
import os
import re
import socket
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from ugetme import __version__, clean, config, learn, state, vocab

MAX_BODY = 4 * 1024 * 1024
RECENT = 20
RECENT_PROTECT_S = 600
_TRANSCRIPT = re.compile(r"<transcript>\s*(.*?)\s*</transcript>", re.S | re.I)


class PortInUse(Exception):
    pass


def extract_text(messages) -> str:
    """The last user message; only the <transcript> inside when a client prompt wraps it."""
    for message in reversed(messages if isinstance(messages, list) else []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        if not isinstance(content, str):
            return ""
        m = _TRANSCRIPT.search(content)
        return (m.group(1) if m else content).strip()
    return ""


def _context(payload: dict) -> dict:
    return {"cwd": str(payload.get("cwd") or ""), "transcript_path": str(payload.get("transcript_path") or "")}


def _completion_id() -> str:
    return "chatcmpl-ugetme-" + uuid.uuid4().hex[:12]


def completion(text: str, model: str) -> dict:
    return {"id": _completion_id(), "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


def completion_stream(text: str, model: str) -> bytes:
    chunk = {"id": _completion_id(), "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}
    return ("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\ndata: [DONE]\n\n").encode("utf-8")


class Service:
    def __init__(self):
        self.lock = threading.Lock()
        self.live: Optional[dict] = None
        self.recent = deque(maxlen=RECENT)

    @property
    def cfg(self) -> dict:
        """Read for every request, so setup changes apply without a restart."""
        return config.load()

    @property
    def token(self) -> str:
        return config.token()

    def accepts_login(self, payload: dict) -> bool:
        cfg = self.cfg
        if cfg["engine"] != "claude":
            return True
        session = config.normalize_config_dir(str(payload.get("config_dir") or ""))
        if session == config.normalize_config_dir(cfg["claude_config_dir"]):
            return str(payload.get("auth") or "") == config.auth_fingerprint(cfg["engine_env"])
        # a login the user trusts: its conversation may reach the engine's account
        return session in config.trusted_logins(cfg)

    def set_live(self, payload: dict) -> bool:
        if not self.accepts_login(payload):
            return False
        with self.lock:
            self.live = dict(_context(payload), ts=time.time())
        return True

    def live_context(self) -> Optional[dict]:
        with self.lock:
            live = self.live
        limit = self.cfg["live_context_minutes"]
        if live and (not limit or time.time() - live["ts"] <= limit * 60):
            return live
        return None

    def recent_changes(self) -> list:
        cutoff = time.time() - RECENT_PROTECT_S
        with self.lock:
            return [c for item in self.recent if item["ts"] >= cutoff for c in item["changes"]]

    def clean(self, text: str, ctx: Optional[dict]) -> clean.Cleaned:
        cfg = self.cfg
        try:
            result = clean.clean_text(text, cfg, ctx, self.recent_changes())
        except Exception as e:  # any surprise: the client still gets the raw text
            reason = f"internal error: {type(e).__name__}: {e}"
            try:
                state.log({"event": "failed", "reason": reason, "raw": text}, cfg["log"])
            except Exception:
                pass
            return clean.Cleaned("", text, text, failed=reason)
        if not result.failed:
            with self.lock:
                self.recent.append({"id": result.id, "raw": text, "clean": result.clean, "changes": result.changes,
                                    "ts": time.time()})
        return result

    def recent_outputs(self) -> list:
        with self.lock:
            return [{"id": i["id"], "clean": i["clean"], "ts": i["ts"]} for i in self.recent]

    def learn(self, payload: dict) -> list:
        with self.lock:
            output = next((i for i in self.recent if i["id"] == payload.get("output_id")), None)
        sent = str(payload.get("sent") or "")
        if output is None or learn.similarity(sent, output["raw"]) > learn.similarity(sent, output["clean"]):
            return []  # the user sent their own words again, not an edit of the clean text
        pairs = learn.replacements(output["clean"], sent) or []
        with vocab.edit() as v:
            for heard, meant in pairs:
                vocab.add_confirmed(v, heard, meant)
        return pairs


class Handler(BaseHTTPRequestHandler):
    server_version = "ugetme/" + __version__
    protocol_version = "HTTP/1.1"
    service: Service = None

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body, content_type: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if content_type == "text/event-stream":
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        return hmac.compare_digest(header.encode("utf-8"), f"Bearer {self.service.token}".encode("utf-8"))

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def do_OPTIONS(self):
        self._send(403, {"error": "not allowed"})

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "version": __version__, "pid": os.getpid()})
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/v1/models":
            return self._send(200, {"object": "list", "data": [{"id": "ugetme", "object": "model", "owned_by": "ugetme"}]})
        if self.path == "/ugetme/recent":
            return self._send(200, {"outputs": self.service.recent_outputs()})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        body = self._body()
        if not isinstance(body, dict):
            return self._send(400, {"error": "bad json"})
        if self.path == "/v1/chat/completions":
            return self._chat(body)
        if self.path == "/ugetme/clean":
            return self._clean(body)
        if self.path == "/ugetme/context":
            return self._send(200, {"accepted": self.service.set_live(body)})
        if self.path == "/ugetme/learn":
            return self._send(200, {"learned": [list(p) for p in self.service.learn(body)]})
        self._send(404, {"error": "not found"})

    def _chat(self, body: dict) -> None:
        text = extract_text(body.get("messages"))
        model = str(body.get("model") or "ugetme")
        cleaned = self.service.clean(text, self.service.live_context()).clean if text else ""
        if body.get("stream"):
            return self._send(200, completion_stream(cleaned, model), "text/event-stream")
        self._send(200, completion(cleaned, model))

    def _clean(self, body: dict) -> None:
        text = str(body.get("text") or "")
        wants = (body.get("cwd") or body.get("transcript_path")) and self.service.accepts_login(body)
        r = self.service.clean(text, _context(body) if wants else None)
        self._send(200, {"id": r.id, "clean": r.clean, "view": r.view, "changes": [list(c) for c in r.changes],
                         "unclear": r.unclear, "secs": r.secs, "failed": r.failed})


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler):
        # On Windows SO_REUSEADDR lets a second service bind the same port; ask for exclusive use there.
        self.allow_reuse_address = sys.platform != "win32"
        super().__init__(address, handler)

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(cfg: dict, port: Optional[int] = None):
    service = Service()
    handler = type("BoundHandler", (Handler,), {"service": service})
    try:
        httpd = _Server((config.HOST, cfg["port"] if port is None else port), handler)
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, 10048):
            raise PortInUse(f"port {cfg['port'] if port is None else port} is in use")
        raise
    return httpd, service


def _rescan(cfg: dict) -> None:
    if not cfg["scan_roots"]:
        return
    try:
        from ugetme import scan
        scan.update_profile(cfg["scan_roots"])
    except Exception:
        pass


def serve() -> int:
    cfg = config.load()
    try:
        httpd, _ = make_server(cfg)
    except PortInUse:
        print(f"ugetme is already running on port {cfg['port']}")
        return 0
    config.token()  # make the token file now, so clients can read it
    threading.Thread(target=_rescan, args=(cfg,), daemon=True).start()
    print(f"ugetme {__version__} listening on {config.service_url(cfg['port'])}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
