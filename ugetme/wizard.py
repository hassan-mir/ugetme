"""ugetme setup: one guided run. Every question also has a flag, so tools can run it without a terminal."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from ugetme import autostart, client, config, handy, scan

SAMPLE = "so um can you like check the the login page and uh tell me if the tests pass"
HANDY_MISSING = ("Handy not found. To dictate with Handy: install it (https://handy.computer), open it once, "
                 "quit it, then run: ugetme handy setup")


class Asker:
    def __init__(self, interactive: bool):
        self.interactive = interactive

    def text(self, question: str, default: str) -> str:
        if not self.interactive:
            return default
        answer = input(f"{question} [{default}] ").strip()
        return answer or default

    def yes(self, question: str, default: bool) -> bool:
        if not self.interactive:
            return default
        answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
        return default if not answer else answer.startswith("y")

    def choose(self, question: str, options: List[str]) -> str:
        if not self.interactive:
            return options[0]
        print(question)
        for i, option in enumerate(options, 1):
            print(f"  {i}. {option}")
        answer = input("Number [1] ").strip()
        return options[int(answer) - 1] if answer.isdigit() and 1 <= int(answer) <= len(options) else options[0]


def detect_logins() -> List[str]:
    candidates = []
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        candidates.append(Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser())
    candidates.append(Path.home() / ".claude")
    candidates += sorted(p for p in Path.home().glob(".claude-*") if p.is_dir())
    out, seen = [], set()
    for path in candidates:
        if not path.is_dir() or not any((path / n).exists() for n in (".credentials.json", "settings.json", "projects")):
            continue
        key = config.normalize_config_dir(str(path))
        if key not in seen:
            seen.add(key)
            out.append(str(path))
    return out


def _flag_pair(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    dest = name.replace("-", "_")
    parser.add_argument(f"--{name}", dest=dest, action="store_true", default=None, help=help_text)
    parser.add_argument(f"--no-{name}", dest=dest, action="store_false")


def setup_handy(port: int, token: str, main_hotkey: bool, auto_submit: Optional[bool], interactive: bool) -> str:
    path = handy.find_settings()
    if path is None:
        return HANDY_MISSING
    while handy.is_running():
        if not interactive:
            return "Handy is running, so its settings were not changed. Quit Handy, then run: ugetme handy setup"
        input("Handy is running. Quit it (tray icon → Quit), then press Enter… ")
    try:
        backup = handy.configure(path, port, token, swap_hotkeys=main_hotkey, auto_submit=auto_submit)
    except (ValueError, KeyError, TypeError, AttributeError) as e:  # a damaged settings file
        return (f"✗ ugetme could not read Handy's settings ({type(e).__name__}), so nothing changed. "
                f"Open Handy once, quit it, then run: ugetme handy setup")
    kept = f"backup: {backup.name}" if backup else "your first backup is kept"
    return f"✓ Handy is set up ({kept}). Start Handy again."


def _choose_claude_login(cfg: dict, a: argparse.Namespace, ask: Asker) -> None:
    """The Claude login that cleans, and the other logins whose conversation may be used."""
    logins = detect_logins()
    if a.login is not None:
        chosen = a.login
    elif len(logins) > 1:
        chosen = ask.choose("Which Claude login should clean your text?", logins)
    else:
        chosen = logins[0] if logins else ""
    if chosen and config.normalize_config_dir(chosen) != config.normalize_config_dir(""):
        cfg["claude_config_dir"] = str(Path(chosen).expanduser().resolve())
    else:
        cfg["claude_config_dir"] = ""
    print(f"✓ Engine: claude ({cfg['claude_config_dir'] or '~/.claude'})")
    others = [str(Path(o).expanduser().resolve()) for o in logins
              if config.normalize_config_dir(o) != config.normalize_config_dir(cfg["claude_config_dir"])]
    if a.trust_other_logins is not None:
        cfg["trusted_logins"] = others if a.trust_other_logins else []
    elif others and ask.interactive:
        question = f"Also use the conversation from {', '.join(others)} as context? It is sent to the login above."
        cfg["trusted_logins"] = others if ask.yes(question, False) else []
    else:   # nobody answered: keep the saved list, without the login that now cleans
        engine_login = config.normalize_config_dir(cfg["claude_config_dir"])
        cfg["trusted_logins"] = [t for t in cfg["trusted_logins"] if config.normalize_config_dir(t) != engine_login]
    if cfg["trusted_logins"]:
        print(f"✓ Trusted logins: {', '.join(cfg['trusted_logins'])}")


def _choose_openai(cfg: dict, a: argparse.Namespace, ask: Asker) -> None:
    """The OpenAI-compatible URL, key and model."""
    if not a.engine:
        print("Claude Code (claude) was not found, so ugetme uses an OpenAI-compatible model. "
              "To use Claude Code instead: install it, log in, and run ugetme setup again.")
    o = cfg["openai"]
    o["base_url"] = a.openai_url or ask.text("OpenAI-compatible base URL", o["base_url"] or "http://localhost:11434/v1")
    o["api_key"] = a.openai_key if a.openai_key is not None else ask.text("API key (empty for none)", o["api_key"])
    o["model"] = a.openai_model or ask.text("Model", o["model"] or "llama3")
    print(f"✓ Engine: {o['base_url']} ({o['model']})")


def _test_sample() -> bool:
    """Start the service and clean the sample sentence; True when it worked."""
    if not client.ensure_running():
        print(f"✗ The service did not start; see {config.serve_log()}")
        return False
    started = time.time()
    try:
        res = client.clean(SAMPLE)
    except client.ClientError as e:
        print(f"✗ Test failed: {e}")
        return False
    if res.get("failed"):
        print(f"✗ Test failed: {res['failed']}\n  Fix that, then run: ugetme test")
        return False
    print(f"✓ Test ({time.time() - started:.1f} s): {res.get('clean')}")
    return True


def run(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ugetme setup", description="Set up ugetme.")
    p.add_argument("--yes", action="store_true", help="use defaults and ask nothing")
    p.add_argument("--engine", choices=("claude", "openai"), help="claude (default when claude is on PATH) or an OpenAI-compatible model")
    p.add_argument("--login", help="Claude login folder (CLAUDE_CONFIG_DIR); empty for the default ~/.claude. Without it, --yes uses the first folder that --list-logins shows")
    p.add_argument("--openai-url", help="base URL of the OpenAI-compatible API, for example http://localhost:11434/v1")
    p.add_argument("--openai-key", help="API key for that API (empty for none)")
    p.add_argument("--openai-model", help="model name for that API")
    p.add_argument("--scan-root", action="append", help="folder with your projects; repeat for several folders")
    p.add_argument("--no-scan", action="store_true", help="do not read project names")
    _flag_pair(p, "trust-other-logins", "also use the conversation from your other Claude logins as context (default: no)")
    _flag_pair(p, "autostart", "start the service at login")
    _flag_pair(p, "handy", "set up Handy")
    p.add_argument("--mode", choices=tuple(config.MODES), help="auto (default): Handy's main hotkey cleans; "
                   "check: Claude Code checks every prompt; manual: clean only when you ask")
    _flag_pair(p, "handy-auto-submit", "press Enter after Handy pastes")
    p.add_argument("--no-test", action="store_true", help="do not clean a test sentence at the end")
    p.add_argument("--list-logins", action="store_true", help="print the Claude logins found, as JSON, and stop")
    a = p.parse_args(argv)
    if a.list_logins:
        print(json.dumps(detect_logins()))
        return 0
    ask = Asker(not a.yes and sys.stdin.isatty())
    if not a.yes and not ask.interactive:
        print("No terminal, so setup uses the defaults (see ugetme setup --help).")
    cfg = config.load()

    claude_bin = shutil.which("claude") or cfg["claude_bin"]
    cfg["engine"] = a.engine or ("claude" if claude_bin else "openai")
    cfg["env_path"] = os.environ.get("PATH", "")  # autostarted services get a minimal PATH (node, claude)
    if cfg["engine"] == "claude":
        cfg["claude_bin"] = claude_bin or ""
        _choose_claude_login(cfg, a, ask)
    else:
        _choose_openai(cfg, a, ask)

    if not a.no_scan:
        default = ",".join(cfg["scan_roots"] or scan.default_roots())
        roots = a.scan_root or ask.text("Folders with your projects (comma-separated)", default).split(",")
        cfg["scan_roots"] = [str(Path(r.strip()).expanduser().resolve()) for r in roots if r.strip()]
    if a.mode:
        cfg["mode"] = a.mode
    elif ask.interactive:
        options = [f"{name}: {text}" for name, text in config.MODES.items()]
        cfg["mode"] = ask.choose("How do you want to use ugetme?", options).split(":", 1)[0]
    print(f"✓ Mode: {cfg['mode']} (ugetme mode shows all modes)")
    config.save(cfg)
    token = config.token()
    if cfg["scan_roots"]:
        count = scan.update_profile(cfg["scan_roots"])
        print(f"✓ Found {count} project name" + ("" if count == 1 else "s"))

    if a.autostart if a.autostart is not None else ask.yes("Start ugetme when you log in?", True):
        try:
            print(f"✓ Autostart: {autostart.install()}")
        except (OSError, subprocess.SubprocessError) as e:
            print(f"✗ Autostart failed: {e}. Start the service with: ugetme ensure")

    found = handy.find_settings() is not None
    if a.handy if a.handy is not None else (found and ask.yes("Set up Handy to use ugetme?", True)):
        auto = a.handy_auto_submit if a.handy_auto_submit is not None else ask.yes(
            "Send automatically after the paste (auto-submit Enter)?", False)
        print(setup_handy(cfg["port"], token, cfg["mode"] == "auto", auto, ask.interactive))
    elif not found and a.handy is None:
        print(HANDY_MISSING)

    ok = True if a.no_test else _test_sample()
    if a.no_test:
        print("Run ugetme test to see a cleanup.")
    print("\nIn Claude Code (optional), install the ugetme plugin:\n"
          "  /plugin marketplace add hassan-mir/ugetme\n  /plugin install ugetme@ugetme")
    return 0 if ok else 1
