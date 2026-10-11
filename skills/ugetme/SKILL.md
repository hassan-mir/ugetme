---
name: ugetme
description: 'Runs the ugetme CLI (the local service that cleans dictated text). This skill should be used for /ugetme (status, setup, mode, config, review, test, learn, keep, forget, style, tidy, scan, clean, trust, untrust, ensure, stop, restart, handy, autostart), when the user asks ugetme to learn or keep a word, and when ugetme check context says "run the ugetme skill with: learn ..." or "keep ...".'
argument-hint: "[status | setup | mode [auto|check|manual] | config [key [value]] | review | test | clean <text> | ensure | stop | restart | learn <heard> <meant> | keep <word> | forget <term> | style <note> | tidy | scan | trust <folder> | untrust <folder> | handy status|undo|setup | autostart on|off | or teach a word: nimbis means Nimbus]"
allowed-tools: Bash(ugetme *), Bash(python3 *bin/ugetme*), Bash(python *bin/ugetme*)
---

# ugetme

ugetme is a local service that cleans dictated text. Handy and other tools send text to it; in Claude Code, a prompt that starts or ends with `<<` (in mode `check`, every prompt of 5 words or more) goes through it and comes back for a check.

Run every command through the CLI:

    ugetme <command> [args]

If `ugetme` is not found, use `python3 "${CLAUDE_PLUGIN_ROOT}/bin/ugetme" <command> [args]` (or `python` if `python3` is missing).

Show the output of the last command to the user in a code block, as printed. Do not show the JSON from `review --list` or `setup --list-logins`; use it to make your questions.

Rules for every call:
- Put each value in single quotes: `learn 'nimbis' 'Nimbus'`. For a single quote inside a value, write `'\''`.
- Do not put a value in double quotes, backticks, `$(...)` or `$'...'`. The shell runs what is inside them.
- Write one command on one line. Do not add `;`, `&&`, `|`, `>`, `<` or `->`. The permission rule and the CLI expect one plain call.
- The CLI output is the confirmation. Do not read, search for or check the ugetme files.
- Never run `serve`: it does not stop. To start the service, run `ensure`.

## Direct commands

Run these with the same words:

- `status`, `tidy`, `test`, `ensure`, `stop`, `restart`, `review --list`, `config`, `trust` (with no folder, it only lists)
- `config '<key>'` shows one setting; `config '<key>' '<value>'` changes it (for example `config 'model' 'opus'`)
- `scan`, or `scan '<folder>' '<folder>'`
- `keep '<word>'`, `forget '<term>'`, `style '<note>'`, `clean '<text>'`, `untrust '<folder>'`
- `trust '<folder>'` sends that login's conversation to another account. Run it only when the user asked for it in their own message, and ask with your question tool to confirm the folder first.
- `learn '<heard>' '<meant>'` (also when the user types `fix <heard> -> <meant>`)
- `mode` shows the modes; `mode '<auto|check|manual>'` changes the mode and moves the Handy hotkey. If its output says Handy is running, ask the user to quit Handy, then run `mode '<mode>'` again.
- `handy status`, `handy undo`, `autostart on`, `autostart off`, `autostart status`
- For `handy setup`, do step 5 of `setup` below.

With no arguments, run `status`.

## Teaching words

Any text after `/ugetme` that is not a command above teaches a word, for example `/ugetme nimbis means Nimbus` or `/ugetme you keep writing nimbis and nimbos, I mean Nimbus`. Run one `learn` call for each wrong form: `learn 'nimbis' 'Nimbus'`, then `learn 'nimbos' 'Nimbus'`. If the user says a word is right as it is, run `keep '<word>'`. If you cannot tell the wrong form from the right term, ask one question.

## `review`

Run `review --list`. If it prints `[]`, say there is nothing to review. If it has 16 fixes or fewer, ask with your question tool which fixes were wrong (multi-select, 4 options per question, label `n. heard → meant`). If it has more, show a numbered list and ask the user to type the numbers. If the user picks none, stop. Otherwise run `review --wrong '<numbers, comma-separated>'`.

## `setup`

1. Run `setup --list-logins`. It prints a JSON list of Claude login folders. If it has more than one, ask with your question tool: "Which Claude login should clean your text?" (one option per folder, in list order, 4 at most), and "Also use the conversation from your other logins as context? It goes to the chosen login's account." (yes/no).
2. Ask with your question tool: "Which folders hold your projects? ugetme sends their folder names with each cleanup." (multi-select: `~/code`, `~/projects`, `~/src`, `~/dev`; the user can type another folder or pick none).
3. Run `handy status`. Ask with your question tool: "Start ugetme when you log in?" (yes/no). If the output is not `handy: not found`, also ask "Set up Handy to use ugetme?" (yes/no). Ask "How do you want to use ugetme?" with these options: "Clean automatically (auto)": Handy's main hotkey pastes clean text, `<<` checks a prompt in Claude Code; "Always check in Claude Code (check)": Handy's main hotkey pastes your own words, and Claude Code checks every prompt before it is sent; "Only when I ask (manual)": ugetme cleans only with Handy's second hotkey or `<<`.
4. Run `setup --yes` with `--login '<chosen folder>'` and `--trust-other-logins` or `--no-trust-other-logins` (only when there were several), `--scan-root '<folder>'` for each chosen folder (repeat) or `--no-scan`, `--autostart` or `--no-autostart`, `--mode '<auto|check|manual>'`, `--handy` or `--no-handy`, and `--no-handy-auto-submit` (the user reads the text before sending it). If the output shows an `Engine:` line with a URL, tell the user that ugetme did not find Claude Code, and that `ugetme setup` in a terminal lets them choose another model.
5. If the output says "Handy is running", ask with your question tool: "Quit Handy (tray icon, then Quit). Is Handy closed?" (Done / Skip). On Done, run `handy setup --no-auto-submit`. It uses the hotkeys of the chosen mode. If it says "Handy is running" again, tell the user to run `ugetme handy setup` later, and stop.

## After a ugetme check

When ugetme's context tells you to run `learn` or `keep` after the user answered, run exactly that with single-quoted values, then continue with the user's request.
