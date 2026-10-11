"""Build the text that the cleanup model reads."""
from pathlib import Path
from typing import List, Tuple

from ugetme import transcript
from ugetme.scan import SKIP
from ugetme.transcript import Turn

TURN_CAP = 2000
TOTAL_CAP = 40000
OUTLINE_LIMIT = 40
FILES_LIMIT = 30


def project_outline(cwd) -> str:
    p = Path(cwd)
    try:
        names = sorted(
            n.name + ("/" if n.is_dir() else "")
            for n in p.iterdir()
            if not n.name.startswith(".") and n.name not in SKIP
        )
    except OSError:
        return ""
    return f"{p.name}: " + ", ".join(names[:OUTLINE_LIMIT])


def _cap(text: str) -> str:
    if len(text) <= TURN_CAP:
        return text
    half = TURN_CAP // 2
    return text[:half] + " […] " + text[-half:]


def build_input(raw: str, vocab_text: str, turns: List[Turn], files: List[str], outline: str) -> str:
    parts = []
    if vocab_text.strip():
        parts.append(f"<vocabulary>\n{vocab_text.strip()}\n</vocabulary>")
    if outline:
        parts.append(f"<project>\n{outline}\n</project>")
    if files:
        parts.append("<recent_files>\n" + "\n".join(files[-FILES_LIMIT:]) + "\n</recent_files>")
    tail = f"<raw_prompt>\n{raw}\n</raw_prompt>"
    convo = [f"[{t.role}]: {_cap(t.text)}" for t in turns]
    fixed = sum(len(p) for p in parts) + len(tail)
    while convo and fixed + sum(len(c) + 2 for c in convo) > TOTAL_CAP:
        convo.pop(0)
    if convo:
        parts.append("<conversation>\n" + "\n\n".join(convo) + "\n</conversation>")
    parts.append(tail)
    return "\n\n".join(parts)


def gather(settings: dict, transcript_path, cwd: str) -> Tuple[List[Turn], List[str], str]:
    wants_transcript = settings["turns"] != 0 or settings["last_reply"] or settings["file_names"]
    turns, files = transcript.read(transcript_path) if wants_transcript else ([], [])
    chosen = transcript.recent(turns, settings["turns"])
    if settings["last_reply"] and not any(t.role == "assistant" for t in chosen):
        reply = transcript.last_reply(turns)
        if reply:
            chosen = [Turn("assistant", reply)] + chosen
    files = files if settings["file_names"] else []
    outline = project_outline(cwd) if settings["project_outline"] and cwd else ""
    return chosen, files, outline
