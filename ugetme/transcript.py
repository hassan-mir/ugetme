"""Read recent conversation turns and file names from a Claude Code transcript."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

TAIL_BYTES = 2_000_000
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_SKIP = re.compile(
    r"^\s*<(command-name|command-message|command-args|local-command-|bash-input|bash-stdout|bash-stderr|task-notification)",
    re.I,
)
_FILE_KEYS = ("file_path", "notebook_path", "path")


@dataclass
class Turn:
    role: str
    text: str


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _tail_lines(path: Path) -> List[str]:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    return lines[1:] if size > TAIL_BYTES else lines


def _add_files(content, files: List[str]) -> None:
    for block in content:
        if not (isinstance(block, dict) and block.get("type") == "tool_use"):
            continue
        inp = block.get("input") or {}
        for key in _FILE_KEYS:
            value = inp.get(key)
            if isinstance(value, str) and value:
                if value in files:
                    files.remove(value)
                files.append(value)
                break


def read(path) -> Tuple[List[Turn], List[str]]:
    turns: List[Turn] = []
    files: List[str] = []
    if not path:
        return turns, files
    try:
        lines = _tail_lines(Path(path))
    except OSError:
        return turns, files
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("isSidechain") or rec.get("isMeta"):
            continue
        kind = rec.get("type")
        if kind not in ("user", "assistant"):
            continue
        content = (rec.get("message") or {}).get("content")
        if kind == "assistant" and isinstance(content, list):
            _add_files(content, files)
        text = _REMINDER.sub("", _text_of(content)).strip()
        if not text or _SKIP.match(text):
            continue
        if turns and turns[-1].role == kind:
            turns[-1].text += "\n" + text
        else:
            turns.append(Turn(kind, text))
    return turns, files


def recent(turns: List[Turn], n: int) -> List[Turn]:
    if n < 0:
        return list(turns)
    if n == 0:
        return []
    return list(turns[-n:])


def last_reply(turns: List[Turn]) -> Optional[str]:
    for turn in reversed(turns):
        if turn.role == "assistant":
            return turn.text
    return None
