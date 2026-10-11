"""The one cleanup path used by every client: protect code and logs, add context, run the engine, log."""
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ugetme import config, context, engine, markers, state, vocab

CORRECTION = re.compile(r"\b(no|nope|wrong|not|right|correct|meant|said|leave|keep|undo)\b", re.I)


@dataclass
class Cleaned:
    id: str
    clean: str
    view: str
    changes: List[Tuple[str, str]] = field(default_factory=list)
    unclear: Optional[dict] = None
    secs: float = 0.0
    failed: str = ""


def load_vocab(cwd: str) -> vocab.Vocab:
    v = vocab.load(vocab.user_file())
    if cwd:
        project = Path(cwd) / ".claude" / "ugetme.md"
        if project.exists():
            v = vocab.merged(v, vocab.load(project))
    return v


def clean_text(raw: str, cfg: dict, ctx: Optional[dict] = None, recent_changes=()) -> Cleaned:
    ctx = ctx or {}
    cwd = ctx.get("cwd") or ""
    masked, blocks = markers.protect(raw)
    v = load_vocab(cwd)
    if CORRECTION.search(raw):  # the user may be correcting a recent change: do not fight them
        lowered = raw.lower()
        for heard, _meant in recent_changes:
            if heard.lower() in lowered:
                vocab.keep(v, heard)
    if ctx:
        turns, files, outline = context.gather(config.context_settings(cfg), ctx.get("transcript_path"), cwd)
    else:
        turns, files, outline = [], [], ""
    text = context.build_input(masked, vocab.render(v), turns, files, outline)
    output_id = uuid.uuid4().hex[:12]
    started = time.time()
    try:
        result = engine.run(text, cfg)
    except engine.CleanupError as e:
        secs = round(time.time() - started, 1)
        state.log({"event": "failed", "id": output_id, "reason": str(e), "raw": raw, "secs": secs}, cfg["log"])
        return Cleaned(output_id, raw, raw, secs=secs, failed=str(e))
    secs = round(time.time() - started, 1)
    clean = markers.restore(result.clean, blocks)
    view = markers.restore(result.clean, blocks, short=True)
    state.log({"event": "cleaned", "id": output_id, "raw": raw, "clean": clean,
               "changes": [list(c) for c in result.changes], "unclear": result.unclear, "secs": secs}, cfg["log"])
    return Cleaned(output_id, clean, view, list(result.changes), result.unclear, secs)
