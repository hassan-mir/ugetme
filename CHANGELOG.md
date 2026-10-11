# Changelog

## 0.4.1

- The service starts without a reverse DNS lookup, which could hang for seconds on macOS.
- Cleanups start `claude` without MCP servers: about 3 seconds, with no slow spikes.
- A message with a greeting and a sign-off gets them on their own lines; its separate points become bullets.
- The `/ugetme` skill pre-approves only everyday ugetme commands; Claude Code asks before setup, trust, Handy changes and autostart changes.
- A plugin icon. INSTALL.md installs uv with a package manager instead of a download-and-run script.

## 0.4.0

First public version.

- Three modes, chosen in setup and changed with `ugetme mode`: `auto` (Handy's main hotkey pastes clean text), `check` (Claude Code checks every prompt before it is sent) and `manual` (clean only when you ask). The Handy hotkey moves with the mode.
- A local service on `127.0.0.1:7337` with an OpenAI-compatible endpoint, so Handy and other tools get clean text before they paste.
- Engines: `claude -p` with your own login, or any OpenAI-compatible model.
- Formatting: steps become a numbered list, separate items a bullet list, comparisons a Markdown table, and a message with a greeting and a sign-off gets them on their own lines.
- Context: your word list and project names, plus your recent Claude Code conversation.
- Learning: from your edits in Claude Code (not from your raw words sent again), from `learn` and `keep`, and from `review`.
- A Claude Code plugin: context, learning, `<<` checks and the `/ugetme` skill.
- `ugetme setup`: engine and login, project names, autostart (macOS, Linux, Windows, WSL) and Handy (with a backup and `undo`).
- The check shows the clean text in yellow with each fixed word in bold white (`check_highlight` setting).
- `ugetme clipboard` cleans the clipboard in place, so any dictation (also Win+H or macOS Dictation) can use ugetme from a hotkey.
- Several Claude logins: `ugetme trust` lets the conversation of your other logins be used as context.
- `ugetme config` shows and changes every setting, with validation.
- `ugetme restart`, and `ugetme status` warns when the running service is another version.
- Spelling out a word after you say it ("slow, S-L-O-W") fixes how it is written; the letters are dropped.
- Pasted code and logs are held back from the AI and come back unchanged; any failure returns your own words.
