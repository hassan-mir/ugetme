"""Read project names from folders the user chose: folder names, H1 titles and package names only."""
import re
from pathlib import Path
from typing import List

from ugetme import config, vocab

SKIP = {"node_modules", "venv", ".venv", "dist", "build", "target", "__pycache__"}
LIMIT = 200
_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$")
_PYPROJECT_NAME = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']', re.M)


def default_roots() -> List[str]:
    return [str(p) for p in (Path.home() / n for n in ("code", "projects", "src", "dev")) if p.is_dir()]


def _titles(path: Path) -> List[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:200]
    except OSError:
        return []
    out = []
    in_code = False
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code  # "# ..." inside a code block is a shell comment, not a title
            continue
        m = None if in_code else _H1.match(line)
        if m:
            title = re.sub(r"[`*_\[\]]", "", m.group(1)).strip()
            if title:
                out.append(title)
            if len(out) == 2:
                break
    return out


def _package_names(folder: Path) -> List[str]:
    names = []
    data = config.read_json(folder / "package.json")
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        names.append(data["name"])
    try:
        text = (folder / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        text = ""
    if "[project]" in text:
        m = _PYPROJECT_NAME.search(text.split("[project]", 1)[1].split("\n[", 1)[0])
        if m:
            names.append(m.group(1))
    return names


def scan(roots, limit: int = LIMIT) -> List[str]:
    found: List[str] = []
    for root in roots:
        base = Path(root).expanduser()
        try:
            children = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP)
        except OSError:
            continue
        for child in children:
            found.append(child.name)
            for doc in ("CLAUDE.md", "README.md"):
                found += _titles(child / doc)
            found += _package_names(child)
    return vocab.unique([name for name in found if name and len(name) <= 60])[:limit]


def update_profile(roots) -> int:
    names = scan(roots)
    with vocab.edit() as v:
        v.projects = names
    return len(names)
