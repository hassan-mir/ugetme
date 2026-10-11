"""Talk to the ugetme service, and start it in the background when it is not running."""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from ugetme import config

REQUEST_MARGIN_S = 15  # on top of timeout_s, the engine's own limit


class ClientError(Exception):
    pass


def _url(path: str) -> str:
    return config.service_url(config.load()["port"], path)


def request(method: str, path: str, body=None, timeout: float = 5.0) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(_url(path), data=data, method=method,
                                 headers={"Authorization": f"Bearer {config.token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise ClientError(f"service answered {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ClientError(f"service not reachable ({e})")


def clean(text: str, ctx: Optional[dict] = None) -> dict:
    return request("POST", "/ugetme/clean", dict(ctx or {}, text=text),
                   timeout=config.load()["timeout_s"] + REQUEST_MARGIN_S)


def health(timeout: float = 0.5) -> Optional[dict]:
    try:
        with urllib.request.urlopen(_url("/health"), timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("ok") else None


def start_detached() -> None:
    home = config.home()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = dict(os.environ)
    env.pop("UGETME_INNER", None)
    package_parent = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = package_parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    kwargs = {"creationflags": 0x00000008 | 0x00000200} if sys.platform == "win32" else {"start_new_session": True}
    fd = os.open(str(config.serve_log()), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as log:
        subprocess.Popen([sys.executable, "-m", "ugetme", "serve"], stdin=subprocess.DEVNULL, stdout=log,
                         stderr=log, env=env, cwd=str(home), close_fds=True, **kwargs)


def stop(wait_s: float = 5.0):
    """Stop the running service: True when it stopped, None when nothing was running, False when it did not stop."""
    info = health()
    if info is None or not isinstance(info.get("pid"), int):
        return None
    try:
        os.kill(info["pid"], signal.SIGTERM)
    except OSError:
        return False
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if health(timeout=0.3) is None:
            return True
        time.sleep(0.1)
    return health(timeout=0.3) is None


def ensure_running(wait_s: float = 10.0) -> bool:
    if health() is not None:
        return True
    start_detached()
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(0.2)
        if health() is not None:
            return True
    return False
