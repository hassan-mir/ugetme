"""Find name corrections between ugetme's text and what the user sent."""
import difflib
import re
from typing import List, Optional, Tuple

MIN_SIMILARITY = 0.6
SOUND_ALIKE = 0.5
_PUNCT = ".,;:!?\"'()[]`*"
_NAMEY = re.compile(r"[A-Z0-9_\-./]")


def _words(text: str) -> List[str]:
    return [w.strip(_PUNCT) for w in text.split() if w.strip(_PUNCT)]


def similarity(a: str, b: str) -> float:
    wa = [w.lower() for w in _words(a)]
    wb = [w.lower() for w in _words(b)]
    if not wa and not wb:
        return 1.0
    return difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).ratio()


def _sounds_alike(heard: str, meant: str) -> bool:
    a, b = heard.lower().replace(" ", ""), meant.lower().replace(" ", "")
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio() >= SOUND_ALIKE


def _is_name_fix(heard: str, meant: str, signal: str) -> bool:
    """A misheard name, not a change of content (postgres → MySQL, 5 → 3, It → This).

    `signal` is `meant` without the capitals that only start a sentence."""
    if heard == meant or not _NAMEY.search(signal):
        return False
    if heard.replace(" ", "").isdigit() or meant.replace(" ", "").isdigit():
        return False
    return _sounds_alike(heard, meant)


def replacements(pending: str, sent: str) -> Optional[List[Tuple[str, str]]]:
    if similarity(pending, sent) < MIN_SIMILARITY:
        return None
    a, b = _words(pending), _words(sent)
    raw_b = [w for w in sent.split() if w.strip(_PUNCT)]
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or not (1 <= i2 - i1 <= 4 and 1 <= j2 - j1 <= 4):
            continue
        heard, meant = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        signal = " ".join(b[k][1:] if k == 0 or raw_b[k - 1][-1:] in ".!?:" else b[k] for k in range(j1, j2))
        if _is_name_fix(heard, meant, signal):
            pairs.append((heard, meant))
    return pairs
