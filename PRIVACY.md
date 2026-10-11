# Privacy

ugetme runs on your computer. It has no account, no server of its own, no telemetry and no analytics. The people who make ugetme never receive your text or any data about you.

## Where your text goes

ugetme sends the text you dictate (or a Claude Code prompt you mark with `<<`, or every prompt in mode `check`) to **the engine you chose**, together with the context that helps it clean:

- **Claude Code (the default).** ugetme runs your installed Claude Code (`claude -p`) with your own login. Anthropic's terms and privacy policy, and your Claude plan's usage limits, apply.
- **An OpenAI-compatible model.** If you set one up, the text goes to the address you configured: for example OpenAI, or a local model such as Ollama, where it stays on your computer.

The context is:

- your word list, style notes and the project names from the folders you chose in setup;
- parts of your current Claude Code conversation (recent turns, Claude's last reply and the names of files it used), only from the Claude logins you allowed;
- the names of the files and folders at the top of your current project folder (names only, not their contents).

`ugetme config context` sets how much of the conversation and the project goes with each cleanup: `none`, `light`, `balanced` (the default), `full` or `custom`.

## What ugetme reads on your computer

- The text that your dictation app or Claude Code passes to it.
- Your Claude Code conversation files, for the context above.
- In the project folders you chose: folder names, project titles and package names only.
- In your current project folder: the names of the top-level files and folders.
- Handy's settings file, when you ask setup to configure Handy.

ugetme never reads or sends your Claude credentials. To check that a conversation belongs to the same Claude account before it uses it as context, it compares a one-way hash of the account settings, on your computer only.

## What ugetme stores

Everything is in `~/.ugetme` (or `UGETME_HOME`), readable only by you:

- `config.json` (your settings), `vocab.md` (your words and style notes) and `token` (a random key that only your local service and its clients use);
- `log.jsonl`: recent cleanups with your raw and clean text (400 to 500 events). Turn it off with `ugetme config log off`;
- `sessions/`: the last check of each Claude Code session, which expires after 30 minutes;
- `serve.log`, `handy.json` and, for autostart, `app/`.

When setup configures Handy, it saves a backup of Handy's settings next to them.

## How to remove everything

- `ugetme handy undo` restores Handy's settings, and `ugetme autostart off` removes autostart.
- `uv tool uninstall ugetme` (or `pipx uninstall ugetme`) removes the program, and `/plugin uninstall ugetme` removes the Claude Code plugin.
- Delete `~/.ugetme` to remove your settings, words and logs.

## Questions

Ask in [Discussions](https://github.com/hassan-mir/ugetme/discussions), or report a security problem as [SECURITY.md](SECURITY.md) describes.
