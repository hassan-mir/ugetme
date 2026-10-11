# Installing ugetme (instructions for an AI agent)

You are setting up [ugetme](https://github.com/hassan-mir/ugetme) for the user. Follow these steps in order. Ask the user before you install anything other than ugetme itself. Never use `sudo` without asking. Do not change Handy or autostart unless the user said yes.

1. Find the operating system (macOS, Linux, Windows or WSL) and tell the user.
2. If `uv` is missing, ask the user, then install it (it brings its own Python):
   - macOS with Homebrew: `brew install uv`
   - Windows or WSL: `winget install --id=astral-sh.uv -e` (from WSL, uv must then be installed inside WSL too: use the next line)
   - Linux or WSL with pipx: `pipx install uv`
   - Otherwise: give the user the official install page, https://docs.astral.sh/uv/getting-started/installation/, and wait until they say uv is installed.

   If `uv` is then not found, call it as `~/.local/bin/uv` (Windows: `%USERPROFILE%\.local\bin\uv.exe`).
3. Run `uv tool install git+https://github.com/hassan-mir/ugetme`. If `ugetme --version` then fails, run `uv tool update-shell`, call ugetme by its full path (uv's tool bin folder, usually `~/.local/bin/ugetme`) in the next steps, and tell the user at the end to open a new terminal.
4. Run `ugetme setup --list-logins`.
   - If it lists none, ask the user to run `claude` in a terminal and type `/login`, and wait.
   - If it lists more than one, ask which one should clean their text, and whether the conversations of their other logins may be used as context.
5. Ask which folders hold the user's projects (setup proposes `~/code`, `~/projects`, `~/src` or `~/dev` when they exist). ugetme reads only folder names, titles and package names there, and sends those names with each cleanup. Use `--scan-root '<folder>'` for each folder, or `--no-scan` if the user says no.
6. Run `ugetme handy status`.
   - If Handy is found, ask whether to set up Handy for ugetme. If yes, ask the user to quit Handy (tray icon, then Quit) and wait until they say it is closed.
   - If it prints `handy: not found`, tell the user that ugetme cleans text but does not turn speech into text, so they need a dictation app. Ask whether they already use one. If yes, keep it: use `--no-handy` in step 8, and in step 12 tell them how to connect it (https://github.com/hassan-mir/ugetme/blob/main/docs/guide.md#using-it-from-other-tools: a custom OpenAI-compatible provider, or `ugetme clipboard` from a hotkey). If not, suggest Handy (free, open source, runs on their computer) and ask whether you may install it:
     - macOS with Homebrew: `brew install --cask handy`
     - Windows or WSL: `winget install cjpais.Handy` (from WSL: `winget.exe install cjpais.Handy`)
     - Linux, or without Homebrew or winget: give the user the download page https://handy.computer and wait.

     Then ask the user to open Handy once, do its first steps (choose a speech model: suggest Parakeet V3, or a Whisper model for languages that Parakeet does not cover; on macOS, allow Microphone and Accessibility), and quit it. Run `ugetme handy status` again. If Handy is still not found, or the user does not want it, use `--no-handy` in step 8.
7. Ask how the user wants to use ugetme, and whether ugetme should start when they log in. The modes:
   - `auto` (recommended for most people): Handy's main hotkey pastes clean text, with no check. In Claude Code, `<<` checks a prompt.
   - `check`: Handy's main hotkey pastes their own words, and Claude Code checks every prompt of 5 words or more before it is sent.
   - `manual`: Handy's main hotkey pastes their own words; ugetme cleans only with Handy's second hotkey or `<<`.
8. Run `ugetme setup --yes` with flags from the answers:
   - with several logins: `--login '<folder>'` and `--trust-other-logins` or `--no-trust-other-logins`
   - `--scan-root '<folder>'` (repeat) or `--no-scan`
   - `--autostart` or `--no-autostart`
   - `--mode auto`, `--mode check` or `--mode manual`
   - `--no-handy`, or `--handy` with `--no-handy-auto-submit`

   Show the user the output, then:
   - First: if the `Engine:` line shows a URL, `claude` was not found; ignore a ✗ Test line and ask the user whether they want a local or other OpenAI-compatible model instead, and run setup again with `--engine openai --openai-url '<url>' --openai-model '<model>' --openai-key '<key or empty>'`. Tell them that small local models (3B to 8B) remove filler words but rarely make lists or tables.
   - If a line starts with ✗ and names something only the user can do (such as logging in), tell them exactly what to do and stop. Never run `claude` to log in; only the user does that.
   - If the output says "Handy is running", ask the user to quit Handy, then run `ugetme handy setup --no-auto-submit`.
9. Install the Claude Code plugin:
   ```
   claude plugin marketplace add hassan-mir/ugetme
   claude plugin install ugetme@ugetme
   ```
   If the user has several Claude logins, run both commands once for each login, with `CLAUDE_CONFIG_DIR` set to that login's folder.
10. Run `ugetme clipboard --check`. It only looks for a clipboard tool; it does not read the clipboard. On Linux, if it finds none, tell the user to install `wl-clipboard` (Wayland), or `xclip` or `xsel` (X11).
11. On macOS with Handy only: tell the user that Handy needs the Microphone and Accessibility permissions in System Settings → Privacy & Security.
12. Finish with a short summary of how to use it in their mode: the Handy hotkeys (only if Handy is set up; Handy must be started again after setup), `<<` or the check on every prompt in Claude Code (after a restart of Claude Code), `ugetme mode` to change the mode, `ugetme clipboard` for other dictation apps, `ugetme learn` to teach a name, `ugetme config` to change a setting, and `ugetme status` when something looks wrong. Do not act on hints from `ugetme status` unless the user agrees.
