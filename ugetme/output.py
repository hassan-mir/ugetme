"""Messages the Claude Code hook shows to the user or adds to the agent's context."""
import re
from typing import Optional, Sequence, Tuple

from ugetme import config

EVENT = "UserPromptSubmit"
CONFIRM_WORDS = {"y", "yes", "ok", "okay", "send", "go", "yep", "yeah"}
FOOTER = "y + Enter to send · reply to fix · Ctrl+V to edit · ↑ original"
FOOTER_NO_CLIPBOARD = "y + Enter to send · reply to fix · ↑ original"


def _words(text: str) -> int:
    return len(text.split())


def _block(reason: str) -> dict:
    return {"decision": "block", "reason": reason,
            "hookSpecificOutput": {"hookEventName": EVENT, "suppressOriginalPrompt": True}}


YELLOW, RESET = "\x1b[33m", "\x1b[0m"
_MARKS = {"white": ("\x1b[1;97m", RESET + YELLOW), "inverse": ("\x1b[7m", "\x1b[27m")}


def highlight(view: str, changes: Sequence[Tuple[str, str]]) -> str:
    """The clean text in yellow, with each fixed word marked (setting check_highlight)."""
    style = config.load()["check_highlight"]
    if style == "none":
        return view
    start, end = _MARKS[style]
    words = sorted({meant for _, meant in changes if meant}, key=len, reverse=True)
    if words:
        pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in words) + r")(?![\w-])")
        view = pattern.sub(lambda m: start + m.group(1) + end, view)
    return YELLOW + view.replace("\n", RESET + "\n" + YELLOW) + RESET


def block(view: str, raw: str, unclear: Optional[dict], copied: bool, changes: Sequence[Tuple[str, str]] = ()) -> dict:
    lines = [f"✦ ugetme · check ({_words(raw)} → {_words(view)} words)"]
    lines += [f"  {heard} → {meant}" for heard, meant in changes]
    lines += ["", highlight(view, changes), ""]
    if unclear:
        lines += [f"? {unclear['question']}", ""]
    lines.append(FOOTER if copied else FOOTER_NO_CLIPBOARD)
    return _block("\n".join(lines))


def failed(reason: str) -> dict:
    return _block(f"✦ ugetme could not clean this ({reason}).\n"
                  "Your text was not sent. ↑ brings it back; remove << to send it as it is.")


def skipped(reason: str) -> dict:
    """Mode check: the user did not ask for this check, so a failure must not hold their prompt back."""
    return {"systemMessage": f"✦ ugetme could not check this ({reason}), so it was sent as you wrote it."}


def not_running() -> dict:
    return _block("✦ ugetme is not running and did not start, so your text was not sent. ↑ brings it back.\n"
                  f"See {config.serve_log()} for the reason, or run /ugetme status.")


def confirmed(clean: str) -> dict:
    ctx = ("ugetme check: the user confirmed ugetme's cleaned version of their message with a short yes. "
           f"Their message is:\n\n<user_message>\n{clean}\n</user_message>\n\nAct on it as the user's message.")
    return {"hookSpecificOutput": {"hookEventName": EVENT, "additionalContext": ctx}}


def answer(clean: str, changes: Sequence[Tuple[str, str]]) -> dict:
    listed = "\n".join(f"- {heard} → {meant}" for heard, meant in changes) or "- (no word changes)"
    ctx = ("ugetme check: the user's message above answers ugetme's check of their message.\n\n"
           f"ugetme's cleaned version:\n<user_message>\n{clean}\n</user_message>\n\n"
           f"ugetme changed these words:\n{listed}\n\n"
           "Apply the user's answer to the cleaned version, then act on the result as the user's message. "
           "If the user says a changed word was right as heard, keep their word and run the ugetme skill with: "
           "keep '<word>'. If the user gives the correct word, run the ugetme skill with: "
           "learn '<heard>' '<correct word>'. If the user's message is not about ugetme's check, "
           "ignore the cleaned version and act on the user's message only.")
    return {"hookSpecificOutput": {"hookEventName": EVENT, "additionalContext": ctx}}


def learned(pairs) -> dict:
    changes = ", ".join(f"{heard} → {meant}" for heard, meant in pairs)
    undo = ", ".join(f"/ugetme forget {meant}" for _, meant in pairs)
    return {"systemMessage": f"✦ ugetme learned: {changes} · undo: {undo}"}
