"""The << marker, and protection of pasted code and logs (they never go to the model)."""
import re
from typing import List, Optional, Tuple

CLEAN = "<<"
PLACEHOLDER = "⟦ugetme:{}⟧"

_PLACEHOLDER_RE = re.compile(r"⟦ugetme:(\d+)⟧")
_FENCE = re.compile(r"```.*?```", re.S)
_HEREDOC = re.compile(r"^<<-?\s*['\"]?[A-Za-z_]{2,}['\"]?\s*\n")
_CODE_LINE = re.compile(
    r"^(\s{4}|\t)"
    r"|[{};]\s*$"
    r"|^\s*(at |File \"|Traceback|\$ |#include|def |class |import |from \S+ import |const |let |function |[A-Za-z]+Error:)"
    # log lines: timestamps, levels, compiler and package-manager output, file:line prefixes
    r"|^\s*\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"
    r"|^\s*\[?\d{2}:\d{2}:\d{2}"
    r"|^\s*\[?(ERROR|WARN|WARNING|INFO|DEBUG|FATAL|TRACE)\b"
    r"|^\s*(Exception|Caused by)\b"
    r"|^\s*(error|warning|note|fatal)(\[\w+\])?:"
    r"|^\s*-->"
    r"|^\s*npm (ERR!|WARN)"
    r"|^(E {2,}|FAILED |PASSED )"
    r"|^\s*[\w./\\-]+\.\w+:\d+(:\d+)?\b"
)


def strip_marker(text: str) -> Tuple[bool, str]:
    s = text.strip()
    if _HEREDOC.match(s):
        return False, s
    triple = CLEAN + CLEAN[0]
    if s.startswith(CLEAN) and not s.startswith(triple):
        return True, s[len(CLEAN):].strip()
    if s.endswith(CLEAN) and not s.endswith(triple):
        return True, s[: -len(CLEAN)].strip()
    return False, s


def clean_request(prompt: str) -> Optional[str]:
    """The text to clean when a prompt starts or ends with <<; None otherwise."""
    s = prompt.strip()
    if not s or s.startswith(("/", "!")):
        return None
    hit, rest = strip_marker(s)
    return rest if hit and rest else None


def protect(text: str) -> Tuple[str, List[str]]:
    """Replace fenced blocks and runs of 2+ code-like lines with placeholders."""
    blocks: List[str] = []

    def keep(block: str) -> str:
        blocks.append(block)
        return PLACEHOLDER.format(len(blocks))

    text = _FENCE.sub(lambda m: keep(m.group(0)), text)
    out: List[str] = []
    run: List[str] = []

    def flush() -> None:
        if len(run) >= 2:
            out.append(keep("\n".join(run)))
        else:
            out.extend(run)
        run.clear()

    for line in text.split("\n"):
        if _CODE_LINE.search(line) and not _PLACEHOLDER_RE.search(line):
            run.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out), blocks


def _label(block: str) -> str:
    lines = block.count("\n") + 1
    return f"[pasted block: {lines} lines]" if lines > 3 else block


def restore(text: str, blocks: List[str], short: bool = False) -> str:
    """Put blocks back. Unknown placeholders go away; dropped blocks go at the end."""
    show = _label if short else (lambda b: b)
    used = set()

    def put(m) -> str:
        i = int(m.group(1))
        if 1 <= i <= len(blocks) and i not in used:
            used.add(i)
            return show(blocks[i - 1])
        return ""

    out = _PLACEHOLDER_RE.sub(put, text)
    missing = [show(b) for i, b in enumerate(blocks, 1) if i not in used]
    return "\n\n".join([out.rstrip()] + missing) if missing else out
