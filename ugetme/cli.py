"""The ugetme command."""
import difflib
import json
import os
import subprocess
import sys
import time

from ugetme import __version__, autostart, client, clipboard, config, handy, hook, scan, server, state, vocab, wizard

USAGE = """usage: ugetme <command>

  setup                       guided setup (engine, projects, mode, autostart, Handy)
  serve                       run the service in this terminal
  status                      show the service, engine, mode, context, vocabulary, autostart and Handy
  config [key [value]]        show all settings, or show or change one
  mode [auto|check|manual]    how ugetme works with Handy and Claude Code (no value: show the modes)
  clean <text>                clean text (or stdin) and print it
  clipboard [--check]         clean the text on the clipboard, in place (for a hotkey); --check only finds the tool
  learn "<heard>" "<meant>"   teach a name, for example: learn "cloud code" "Claude Code"
  keep <word>                 never change this word
  forget <term>               remove a term or keep word
  style <note>                add a style note
  review [--list|--wrong N,M] review recent word fixes
  scan [folder ...]           read project names again
  tidy                        merge duplicate vocabulary entries
  trust [folder]              use the conversation from another Claude login as context (no folder: list)
  untrust <folder>            stop using that login's conversation
  handy setup|undo|status     Handy settings
  autostart on|off|status     start the service at login
  ensure                      start the service in the background if needed
  stop                        stop the running service
  restart                     stop and start the service (after an update)
  test                        clean one sample sentence
  --version                   print the version
"""
COMMANDS = ("setup", "serve", "status", "config", "mode", "clean", "clipboard", "learn", "keep", "forget", "style", "review", "scan",
            "tidy", "trust", "untrust", "handy", "autostart", "ensure", "stop", "restart", "test")


def _unquote(text: str) -> str:
    return text.strip().strip("'\"")


def _pair(args):
    text = " ".join(args)
    for sep in ("→", "->", "=>"):
        if sep in text:
            heard, meant = map(_unquote, text.split(sep, 1))
            break
    else:
        heard, meant = map(_unquote, args) if len(args) == 2 else ("", "")
    if not heard or not meant:
        raise SystemExit("usage: ugetme learn <heard> <meant>")
    return heard, meant


def cmd_learn(args):
    heard, meant = _pair(args)
    with vocab.edit() as v:
        vocab.add_confirmed(v, heard, meant)
    print(f'ugetme learned: "{heard}" → {meant}')


def cmd_keep(args):
    word = _unquote(" ".join(args))
    if not word:
        raise SystemExit("usage: ugetme keep <word>")
    with vocab.edit() as v:
        vocab.keep(v, word)
    print(f"ugetme keeps: {word}")


def cmd_forget(args):
    term = _unquote(" ".join(args))
    with vocab.edit() as v:
        removed = vocab.forget(v, term) if term else None
        if not removed:
            raise SystemExit(f"ugetme does not know: {term}")
    print(f"ugetme forgot: {removed}")


def cmd_style(args):
    note = _unquote(" ".join(args))
    if not note:
        raise SystemExit("usage: ugetme style <note>")
    with vocab.edit() as v:
        if note not in v.style:
            v.style.append(note)
    print(f"ugetme style: {note}")


def cmd_tidy(args):
    with vocab.edit() as v:
        vocab.tidy(v)
    print(f"vocabulary tidied: {len(v.terms)} terms, {len(v.style)} style notes, {len(v.keep)} keep words")


def _review_items():
    items = []
    for entry in reversed(state.read_log(200)):
        for heard, meant in entry.get("changes") or []:
            items.append({"heard": heard, "meant": meant, "clean": str(entry.get("clean") or "")[:200]})
            if len(items) == 20:
                break
        if len(items) == 20:
            break
    return [dict(n=i, **item) for i, item in enumerate(items, 1)]


def cmd_review(args):
    items = _review_items()
    if "--list" in args:
        print(json.dumps(items, ensure_ascii=False))
        return
    if "--wrong" in args:
        chosen = args[args.index("--wrong") + 1] if len(args) > args.index("--wrong") + 1 else ""
    else:
        if not items:
            print("No word fixes yet.")
            return
        for item in items:
            print(f"{item['n']:>2}. {item['heard']} → {item['meant']}   ({item['clean'][:60]})")
        if not sys.stdin.isatty():
            print("\nTo mark wrong fixes, run: ugetme review --wrong 1,3")
            return
        chosen = input("Numbers of wrong fixes (comma-separated, empty for none): ")
    numbers = {int(n) for n in chosen.replace(" ", "").split(",") if n.isdigit()}
    kept = [item["heard"] for item in items if item["n"] in numbers]
    with vocab.edit() as v:
        for word in kept:
            vocab.keep(v, word)
    print("ugetme keeps: " + ", ".join(kept) if kept else "No changes.")


def cmd_scan(args):
    cfg = config.load()
    roots = args or cfg["scan_roots"] or scan.default_roots()
    if args:
        cfg["scan_roots"] = list(args)
        config.save(cfg)
    count = scan.update_profile(roots)
    print(f"ugetme found {count} project name" + ("" if count == 1 else "s"))


def _save_trusted(cfg: dict, trusted: list) -> None:
    cfg["trusted_logins"] = trusted
    config.save(cfg)


def cmd_trust(args):
    cfg = config.load()
    trusted = config.trusted_logins(cfg)
    engine_login = config.normalize_config_dir(cfg["claude_config_dir"])
    for folder in args:
        path = config.normalize_config_dir(folder)
        if path == engine_login:
            raise SystemExit(f"{path} is the login that cleans your text; it needs no trust")
        if not os.path.isdir(path):
            print(f"note: {path} does not exist yet")
        if path not in trusted:
            trusted.append(path)
    if args:
        _save_trusted(cfg, trusted)
    print("trusted logins: " + (", ".join(trusted) or "none"))


def cmd_untrust(args):
    if len(args) != 1:
        raise SystemExit("usage: ugetme untrust <folder>")
    cfg = config.load()
    path = config.normalize_config_dir(args[0])
    trusted = config.trusted_logins(cfg)
    if path not in trusted:
        raise SystemExit(f"{path} is not trusted")
    trusted.remove(path)
    _save_trusted(cfg, trusted)
    print("trusted logins: " + (", ".join(trusted) or "none"))


CONFIG_LISTS = {"trusted_logins": "use ugetme trust / ugetme untrust", "scan_roots": "use ugetme scan <folder> ...",
                "engine_env": "edit ~/.ugetme/config.json"}
_ON, _OFF = config.TRUE_WORDS, ("0", "false", "off", "no")


def _flat(cfg: dict) -> dict:
    out = {}
    for key, value in cfg.items():
        if key in config.NESTED and isinstance(value, dict):
            out.update({f"{key}.{k}": v for k, v in value.items()})
        else:
            out[key] = value
    return out


def _tilde(path: str) -> str:
    """A path in the home folder as ~/..., so pasted output does not show the user name."""
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if home not in ("", "~") and (path == home or path.startswith(home + os.sep)) else path


def _show(key: str, value) -> str:
    if key == "openai.api_key":
        return "(set)" if value else "(empty)"
    if key == "env_path" and value:   # a whole PATH: its folders can show user names (also Windows ones under WSL)
        return f"({len([p for p in str(value).split(os.pathsep) if p])} folders)"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return ", ".join(value) or "(none)"
    if isinstance(value, dict):
        return str({k: _tilde(v) if isinstance(v, str) else v for k, v in value.items()})
    return "(empty)" if value == "" else _tilde(str(value))


def _parse_value(key: str, raw: str, current):
    """`raw` as the type of the current value: on/off for a switch, a whole number for a number."""
    if isinstance(current, bool):
        if raw.lower() not in _ON + _OFF:
            raise SystemExit(f"{key} must be on or off")
        return raw.lower() in _ON
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            raise SystemExit(f"{key} must be a whole number")
    return raw


def cmd_config(args):
    cfg = config.load()
    flat = _flat(cfg)
    if not args:
        for key, value in flat.items():
            choices = config.CHOICES.get(key) or (("on", "off") if isinstance(value, bool) else None)
            print(f"{key} = {_show(key, value)}" + (f"  ({', '.join(choices)})" if choices else ""))
        print(f"\nChange one: ugetme config <key> <value>   (file: {_tilde(str(config.settings_file()))})")
        return
    key = args[0]
    if key not in flat:
        guess = difflib.get_close_matches(key, list(flat), n=1)
        raise SystemExit(f"ugetme: no setting '{key}'." + (f" Did you mean {guess[0]}?" if guess else ""))
    if len(args) == 1:
        print(_show(key, flat[key]))
        return
    if key == "mode":
        return cmd_mode(args[1:])  # a mode also moves the Handy hotkey
    if key in CONFIG_LISTS:
        raise SystemExit(f"{key} cannot be set here: {CONFIG_LISTS[key]}")
    raw, current = " ".join(args[1:]), flat[key]
    value = _parse_value(key, raw, current)
    if key in config.CHOICES and value not in config.CHOICES[key]:
        raise SystemExit(f"{key} must be one of: {', '.join(config.CHOICES[key])}")
    if key == "port" and value != current:
        client.stop()   # the running service listens on the old port; stop it before the change
    if "." in key:
        group, sub = key.split(".", 1)
        cfg[group][sub] = value
    else:
        cfg[key] = value
    if _flat(config.normalize(cfg))[key] != value:   # check before saving, so a refused value never reaches the file
        raise SystemExit(f"{key} = {raw} was not accepted; it stays {_show(key, current)}")
    config.save(cfg)
    stored = _flat(config.load())[key]
    print(f"{key} = {_show(key, stored)}")
    if key == "port":
        print("The old service is stopped. Now run: ugetme ensure, then ugetme handy setup (if you use Handy).")


def cmd_mode(args):
    cfg = config.load()
    if not args:
        for name, text in config.MODES.items():
            print(f"{name}{' (now)' if name == cfg['mode'] else ''}: {text}")
        print("\nChange it: ugetme mode auto|check|manual")
        return
    mode = args[0]
    if mode not in config.MODES:
        raise SystemExit(f"ugetme: no mode '{mode}'. Choose one of: {', '.join(config.MODES)}")
    cfg["mode"] = mode
    config.save(cfg)
    print(f"mode = {mode}: {config.MODES[mode]}")
    path = handy.find_settings()
    if path and handy.is_set_up(path):
        print(wizard.setup_handy(cfg["port"], config.token(), mode == "auto", None, sys.stdin.isatty()))


def _describe_service(health) -> str:
    if not health:
        return "not running"
    text = f"running (pid {health.get('pid')}) · version {health.get('version')}"
    if health.get("version") != __version__:
        text += f" (this command is {__version__}; run: ugetme restart)"
    return text


def cmd_status(args):
    cfg = config.load()
    health = client.health()
    v = vocab.load(vocab.user_file())
    engine = (f"claude · login: {_tilde(cfg['claude_config_dir']) or '~/.claude (default)'} · model {cfg['model']}"
              if cfg["engine"] == "claude"
              else f"openai · {cfg['openai']['base_url'] or '(no URL)'} · {cfg['openai']['model']}")
    print("\n".join([
        f"ugetme {__version__}",
        f"service: {_describe_service(health)} · {config.service_url(cfg['port'], '/v1')}",
        f"engine: {engine}",
        f"mode: {cfg['mode']} · {config.MODES[cfg['mode']]}",
        f"context: {cfg['context']} · live context "
        + (f"for {cfg['live_context_minutes']} min" if cfg["live_context_minutes"] else "with no time limit")
        + (f" · trusted logins: {', '.join(_tilde(d) for d in cfg['trusted_logins'])}" if cfg["trusted_logins"] else ""),
        f"vocabulary: {len(v.terms)} terms, {len(v.keep)} keep, {len(v.style)} style, {len(v.projects)} projects",
        f"autostart: {'on' if autostart.installed() else 'off'}",
        f"handy: {handy.describe(port=cfg['port'])}",
        f"files: {_tilde(str(config.home()))}",   # home paths as ~, so pasted output shows no user name
    ]))


def _running() -> bool:
    if client.ensure_running():
        return True
    print(f"ugetme is not running; see {config.serve_log()}")
    return False


def _clean_and_print(text: str) -> int:
    if not text.strip():
        raise SystemExit("usage: ugetme clean <text>")
    if not _running():
        return 1
    started = time.time()
    res = client.clean(text)
    print(res.get("clean", ""))
    if res.get("failed"):
        print(f"(cleanup failed, so this is your text as it was: {res['failed']})", file=sys.stderr)
        return 1
    for heard, meant in res.get("changes") or []:
        print(f"  {heard} → {meant}", file=sys.stderr)
    print(f"({time.time() - started:.1f} s)", file=sys.stderr)
    return 0


NO_CLIPBOARD = "No clipboard tool found. Install wl-clipboard, xclip or xsel (on WSL, powershell.exe must be on PATH)."


def cmd_clipboard(args) -> int:
    if "--check" in args:
        found = clipboard.tool()
        print(f"clipboard tool: {found}" if found else NO_CLIPBOARD)
        return 0 if found else 1
    text = clipboard.paste()
    if text is None:
        print(NO_CLIPBOARD)
        return 1
    if not text.strip():
        print("The clipboard has no text.")
        return 1
    if not _running():
        return 1
    res = client.clean(text)
    if res.get("failed") or not res.get("clean"):
        print(f"Cleanup failed ({res.get('failed') or 'no text'}); the clipboard is unchanged.")
        return 1
    if not clipboard.copy(res["clean"]):
        print("Could not write the clipboard.")
        return 1
    print(res["clean"])
    return 0


def cmd_handy(args):
    action = args[0] if args else "status"
    path = handy.find_settings()
    if action == "status":
        print(f"handy: {handy.describe(port=config.load()['port'])}" + (f" · {path}" if path else ""))
    elif action == "undo":
        restored = handy.undo(path) if path else None
        print(f"Restored {restored.name}" if restored else "No ugetme backup found.")
    elif action == "setup":
        cfg = config.load()
        interactive = sys.stdin.isatty()
        ask = wizard.Asker(interactive)
        main_hotkey = cfg["mode"] == "auto"  # only mode auto puts ugetme on the main hotkey
        auto = "--auto-submit" in args or ("--no-auto-submit" not in args and ask.yes("Send automatically after the paste?", False))
        print(wizard.setup_handy(cfg["port"], config.token(), main_hotkey, auto, interactive))
    else:
        raise SystemExit("usage: ugetme handy setup|undo|status")


def cmd_autostart(args):
    action = args[0] if args else "status"
    if action == "on":
        try:
            path = autostart.install()
        except (OSError, subprocess.SubprocessError) as e:
            raise SystemExit(f"Autostart failed: {e}")
        print(f"Autostart on: {path}")
    elif action == "off":
        print("Autostart off." if autostart.remove() else "Autostart was not on.")
    elif action == "status":
        print("autostart: " + ("on" if autostart.installed() else "off"))
    else:
        raise SystemExit("usage: ugetme autostart on|off|status")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    command, args = argv[0], argv[1:]
    if command == "--version":
        print(__version__)
        return 0
    if command != "setup" and ("-h" in args or "--help" in args):
        print(USAGE)
        return 0
    simple = {"learn": cmd_learn, "keep": cmd_keep, "forget": cmd_forget, "style": cmd_style, "tidy": cmd_tidy,
              "review": cmd_review, "scan": cmd_scan, "trust": cmd_trust, "untrust": cmd_untrust, "config": cmd_config, "status": cmd_status, "handy": cmd_handy,
              "autostart": cmd_autostart, "mode": cmd_mode}
    try:
        if command in simple:
            simple[command](args)
            return 0
        if command == "serve":
            return server.serve()
        if command == "setup":
            return wizard.run(args)
        if command == "stop":
            stopped = client.stop()
            print({True: "ugetme stopped", None: "ugetme was not running", False: "ugetme did not stop"}[stopped])
            return 1 if stopped is False else 0
        if command in ("restart", "ensure"):
            if command == "restart" and client.stop() is False:
                print("ugetme did not stop")
                return 1
            ok = client.ensure_running()
            done = f"ugetme restarted ({__version__})" if command == "restart" else "ugetme is running"
            print(done if ok else f"ugetme did not start; see {config.serve_log()}")
            return 0 if ok else 1
        if command == "clean":
            return _clean_and_print(" ".join(args) if args else sys.stdin.read())
        if command == "clipboard":
            return cmd_clipboard(args)
        if command == "test":
            return _clean_and_print(wizard.SAMPLE)
        if command == "hook" and args and args[0] in ("prompt", "session-start"):
            return hook.run(args[0])
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code)
            return 1
        raise
    except client.ClientError as e:
        print(f"ugetme: {e}")
        return 1
    guess = difflib.get_close_matches(command, COMMANDS, n=1)
    print(f"ugetme: unknown command '{command}'." + (f" Did you mean {guess[0]}?" if guess else "") + "\n")
    print(USAGE)
    return 2
