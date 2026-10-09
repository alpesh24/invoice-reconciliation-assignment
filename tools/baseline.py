"""Review baseline without git.

The orchestrator saves a copy of the project after each approved phase; the reviewer compares the
current project with that copy. Standard library only, works on Windows, macOS and Linux.

    python tools/baseline.py save              # copy the project to .baseline/ (orchestrator only)
    python tools/baseline.py status [PATH...]  # A/M/D list vs .baseline/ (read-only)
    python tools/baseline.py diff [PATH...]    # unified diff vs .baseline/ (read-only)
"""
from __future__ import annotations

import difflib
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / ".baseline"
EXCLUDE_DIRS = {".baseline", ".venv", "venv", "__pycache__", ".pytest_cache", ".git", ".mypy_cache", ".ruff_cache"}
EXCLUDE_FILES = {".env"}
EXCLUDE_PREFIXES = ("data/state",)  # runtime state, rebuilt by `cli run`
EXCLUDE_SUFFIXES = (".pyc",)


def _excluded(rel: Path) -> bool:
    parts = rel.parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if rel.name in EXCLUDE_FILES or rel.name.endswith(EXCLUDE_SUFFIXES):
        return True
    posix = rel.as_posix()
    return any(posix == p or posix.startswith(p + "/") for p in EXCLUDE_PREFIXES)


def _files(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not _excluded(p.relative_to(root))
    }


def _in_scope(rel: str, scopes: list[str]) -> bool:
    if not scopes:
        return True
    return any(rel == s.rstrip("/") or rel.startswith(s.rstrip("/") + "/") for s in scopes)


def _changes(scopes: list[str]) -> list[tuple[str, str]]:
    cur, old = _files(ROOT), _files(BASE)
    out = []
    for rel in sorted(cur | old):
        if not _in_scope(rel, scopes):
            continue
        if rel not in old:
            out.append(("A", rel))
        elif rel not in cur:
            out.append(("D", rel))
        elif not filecmp.cmp(ROOT / rel, BASE / rel, shallow=False):
            out.append(("M", rel))
    return out


def _read_lines(path: Path) -> list[str] | None:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None  # binary


def save() -> None:
    if BASE.exists():
        shutil.rmtree(BASE)
    for rel in sorted(_files(ROOT)):
        dst = BASE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    print(f"baseline saved: {len(_files(BASE))} files in {BASE.name}/")


def status(scopes: list[str]) -> None:
    if not BASE.exists():
        print("no baseline yet (run: python tools/baseline.py save)")
        sys.exit(2)
    for code, rel in _changes(scopes):
        print(f"{code} {rel}")


def diff(scopes: list[str]) -> None:
    if not BASE.exists():
        print("no baseline yet (run: python tools/baseline.py save)")
        sys.exit(2)
    for code, rel in _changes(scopes):
        old, new = _read_lines(BASE / rel), _read_lines(ROOT / rel)
        if old is None or new is None:
            print(f"Binary file {rel} {'added' if code == 'A' else 'deleted' if code == 'D' else 'differs'}")
            continue
        sys.stdout.writelines(
            difflib.unified_diff(old, new, fromfile=f"baseline/{rel}", tofile=f"current/{rel}")
        )
        if (old and not old[-1].endswith("\n")) or (new and not new[-1].endswith("\n")):
            print()


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in {"save", "status", "diff"}:
        print(__doc__)
        sys.exit(1)
    cmd, scopes = argv[0], argv[1:]
    if cmd == "save":
        save()
    elif cmd == "status":
        status(scopes)
    else:
        diff(scopes)


if __name__ == "__main__":
    main(sys.argv[1:])
