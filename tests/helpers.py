import atexit
import io
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

FAKE = str(Path(__file__).with_name("fake_claude.py"))
_CLEARED_PREFIXES = ("UGETME_", "FAKE_CLAUDE_", "ANTHROPIC_", "CLAUDE")
_CLEARED = ("WSL_DISTRO_NAME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "APPDATA")

# Bound but never listening: a connection is refused at once, and no other program can take the port.
_CLOSED = socket.socket()
_CLOSED.bind(("127.0.0.1", 0))
atexit.register(_CLOSED.close)
CLOSED_PORT = _CLOSED.getsockname()[1]


def write_jsonl(records, broken: bool = False) -> str:
    """A temporary JSONL file with these records (and a broken last line when asked). The caller deletes it."""
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
        if broken:
            f.write("{broken line\n")
    return f.name


def free_port() -> int:
    """A free port for a service in another process (a service in this process binds port 0)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TempHomeTest(unittest.TestCase):
    """Each test gets its own UGETME_HOME and HOME, the fake engine, no clipboard, no terminal, and no
    real autostart, Handy or service. The whole environment comes back after the test."""

    closed_port = True  # the default port refuses connections, so no test reaches a real service

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.handy_file = self.home / "handy" / "settings_store.json"
        stdin_patch = mock.patch("sys.stdin", io.StringIO(""))  # a question must never wait for a key
        stdin_patch.start()
        self.addCleanup(stdin_patch.stop)
        env_patch = mock.patch.dict(os.environ)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        for key in [k for k in os.environ if k.startswith(_CLEARED_PREFIXES) or k in _CLEARED]:
            del os.environ[key]
        os.environ.update({
            "HOME": str(self.home), "UGETME_HOME": str(self.home), "UGETME_CLAUDE_BIN": FAKE,
            "UGETME_NO_CLIPBOARD": "1", "UGETME_PLATFORM": "linux", "UGETME_AUTOSTART_DRY": "1",
            "UGETME_AUTOSTART_DIR": str(self.home / "auto"), "UGETME_HANDY_RUNNING": "0",
            "UGETME_HANDY_SETTINGS": str(self.handy_file)})
        if self.closed_port:
            from ugetme import config
            port_patch = mock.patch.dict(config.DEFAULTS, port=CLOSED_PORT)
            port_patch.start()
            self.addCleanup(port_patch.stop)

    def set_config(self, **values) -> dict:
        from ugetme import config
        cfg = config.load()
        cfg.update(values)
        config.save(cfg)
        return config.load()

    def fake_output(self, clean: str, changes=(), unclear=None) -> None:
        """What the fake engine answers: the clean text, the (heard, meant) changes and the unclear point."""
        os.environ["FAKE_CLAUDE_OUT"] = json.dumps(
            {"clean": clean, "changes": [{"heard": h, "meant": m} for h, m in changes], "unclear": unclear})

    def handy_settings(self) -> dict:
        return json.loads(self.handy_file.read_text())["settings"]

    def fake_log(self) -> Path:
        path = self.home / "fake.log"
        os.environ["FAKE_CLAUDE_LOG"] = str(path)
        return path

    def fake_calls(self, path: Path) -> list:
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class ServerTest(TempHomeTest):
    """Runs a real ugetme service in a thread, on a port the system picks."""

    def setUp(self):
        super().setUp()
        from ugetme import server
        self.httpd, self.service = server.make_server({}, port=0)
        self.addCleanup(self.httpd.server_close)
        self.cfg = self.set_config(port=self.httpd.server_address[1])
        thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.cfg['port']}"

    def call(self, method, path, body=None, auth=True, raw=False):
        from ugetme import config
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {config.token()}"
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode()
                return r.status, text if raw else json.loads(text)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
