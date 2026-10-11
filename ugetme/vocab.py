"""Vocabulary file: terms, style notes, keep words and scanned project names."""
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional

from ugetme import config

_ENTRY = re.compile(r"^- (?P<term>.+?)(?: \(heard: (?P<heard>[^)]*)\))?\s*$")
_LISTS = ("style", "keep", "projects")


@dataclass
class Entry:
    term: str
    heard: List[str] = field(default_factory=list)


@dataclass
class Vocab:
    terms: List[Entry] = field(default_factory=list)
    style: List[str] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)


def _parse_entry(line: str) -> Optional[Entry]:
    m = _ENTRY.match(line)
    if not m:
        return None
    heard = [h.strip().strip('"') for h in (m.group("heard") or "").split(",")]
    return Entry(m.group("term").strip(), [h for h in heard if h])


def _section(name: str) -> Optional[str]:
    for key in ("terms",) + _LISTS:
        if name.startswith(key[:4]):
            return key
    return None


def parse(text: str) -> Vocab:
    v = Vocab()
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# "):
            section = _section(line[2:].strip().lower())
            continue
        if section is None or not line.startswith("- "):
            continue
        if section == "terms":
            entry = _parse_entry(line)
            if entry:
                v.terms.append(entry)
        else:
            getattr(v, section).append(line[2:].strip())
    return v


def _render_entry(e: Entry) -> str:
    s = f"- {e.term}"
    if e.heard:
        s += " (heard: " + ", ".join(f'"{h}"' for h in e.heard) + ")"
    return s


def render(v: Vocab) -> str:
    out = ["# Terms"] + [_render_entry(e) for e in v.terms]
    out += ["", "# Style"] + [f"- {s}" for s in v.style]
    out += ["", "# Keep"] + [f"- {k}" for k in v.keep]
    out += ["", "# Projects (auto)"] + [f"- {p}" for p in v.projects]
    return "\n".join(out) + "\n"


def load(path) -> Vocab:
    try:
        return parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return Vocab()


def save(path, v: Vocab) -> None:
    config.write_text(Path(path), render(v))


def user_file() -> Path:
    return config.home() / "vocab.md"


@contextmanager
def edit() -> Iterator[Vocab]:
    """Load the user's vocabulary for a change; save it when the block ends without an error."""
    v = load(user_file())
    yield v
    save(user_file(), v)


def _find(entries: List[Entry], term: str) -> Optional[Entry]:
    for e in entries:
        if e.term.lower() == term.lower():
            return e
    return None


def _add_heard(e: Entry, heard: str) -> None:
    if heard and heard.lower() != e.term.lower() and heard.lower() not in (h.lower() for h in e.heard):
        e.heard.append(heard)


def unique(words: List[str]) -> List[str]:
    """The words in order, each once; case does not matter."""
    seen, out = set(), []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def merged(user: Vocab, project: Vocab) -> Vocab:
    result = Vocab(
        terms=[Entry(e.term, list(e.heard)) for e in project.terms],
        style=unique(user.style + project.style),
        keep=unique(user.keep + project.keep),
        projects=unique(user.projects + project.projects),
    )
    for e in user.terms:
        if _find(result.terms, e.term) is None:
            result.terms.append(Entry(e.term, list(e.heard)))
    return result


def add_confirmed(v: Vocab, heard: str, meant: str) -> None:
    entry = _find(v.terms, meant)
    if entry is None:
        entry = Entry(meant)
        v.terms.append(entry)
    _add_heard(entry, heard)
    v.keep = [k for k in v.keep if k.lower() != heard.lower()]


def keep(v: Vocab, word: str) -> None:
    for e in v.terms:
        e.heard = [h for h in e.heard if h.lower() != word.lower()]
    v.keep = unique(v.keep + [word])


def forget(v: Vocab, term: str) -> Optional[str]:
    """Remove a term (found by its name or by a way it was heard) or a keep word; return what was removed."""
    entry = _find(v.terms, term) or next((e for e in v.terms if term.lower() in (h.lower() for h in e.heard)), None)
    if entry is not None:
        v.terms.remove(entry)
        return entry.term
    kept = [k for k in v.keep if k.lower() != term.lower()]
    if len(kept) == len(v.keep):
        return None
    v.keep = kept
    return term


def tidy(v: Vocab) -> None:
    merged_terms: List[Entry] = []
    for e in v.terms:
        existing = _find(merged_terms, e.term)
        if existing is None:
            merged_terms.append(Entry(e.term, list(e.heard)))
        else:
            for h in e.heard:
                _add_heard(existing, h)
    v.terms = merged_terms
    v.style = list(dict.fromkeys(v.style))
    v.keep = unique(v.keep)
    v.projects = unique(v.projects)
