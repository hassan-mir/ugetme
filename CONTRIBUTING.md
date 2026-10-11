# Contributing to ugetme

Thank you for helping. ugetme is small on purpose: Python 3.9+, the standard library only, and no runtime dependencies.

## Run the tests

```sh
python3 -m unittest discover -s tests
```

The tests need no network and no Claude login: `tests/fake_claude.py` stands in for the `claude` command, and each test runs with its own temporary `UGETME_HOME` and `HOME`, so no test touches your settings, Handy, autostart, clipboard or running service. A full run takes a few seconds.

To try your change for real:

```sh
uv tool install --reinstall .
ugetme restart
ugetme test
```

Claude Code keeps its own copy of the plugin and updates it only when the version changes. When you change the plugin (`hooks/`, `skills/`, `bin/` or code the hooks run), raise the version in `ugetme/__init__.py`, `pyproject.toml` and both files in `.claude-plugin/`, then run `/plugin marketplace update ugetme` and `/plugin update ugetme@ugetme`.

## How the code is organized

| File | Job |
|---|---|
| `ugetme/server.py` | The HTTP service: `/v1/chat/completions` (OpenAI format) and the `/ugetme/*` endpoints |
| `ugetme/clean.py` | The one cleanup path every client uses |
| `ugetme/engine.py` | The cleanup prompt, and the `claude -p` and OpenAI-compatible engines |
| `ugetme/markers.py` | The `<<` marker, and holding back code and logs |
| `ugetme/context.py`, `ugetme/transcript.py` | Context from a Claude Code session |
| `ugetme/vocab.py`, `ugetme/learn.py`, `ugetme/scan.py` | The word list, learning from edits, project names |
| `ugetme/hook.py`, `ugetme/output.py` | The Claude Code hooks and the messages they show |
| `ugetme/client.py` | Talking to the service, and starting it |
| `ugetme/wizard.py`, `ugetme/handy.py`, `ugetme/autostart.py` | Setup, Handy settings, start at login |
| `ugetme/cli.py` | The `ugetme` command |
| `ugetme/config.py` | Settings, the service token, and private atomic writes |
| `ugetme/state.py` | Pending checks for each session, and the cleanup log |
| `ugetme/clipboard.py` | Reading and writing the clipboard (macOS, Linux, Windows, WSL) |
| `.claude-plugin/`, `hooks/`, `skills/`, `bin/` | The Claude Code plugin |

## Rules the code keeps

- **Never lose the user's words.** Any failure returns the raw text; the Claude Code hook always exits 0 and never sends a `<<` prompt raw.
- **Local and private.** The service binds `127.0.0.1`, needs a token, and writes user data with owner-only permissions.
- **One cleanup path.** New ways in call the service; they do not clean text themselves.
- **Test first.** Add a failing test, then the fix.

## Examples in code and docs

Use invented names (Nimbus, Orbit) in tests, docs and prompts, never names from a real person's projects.
