"""On-disk storage for Frobozz playthroughs.

Single XDG-style root: ``$XDG_DATA_HOME/frobozz`` (default ``~/.local/share/frobozz``),
holding both the story files (``games/``) and every playthrough's checkpoints
(``saves/<game_id>/``). rsync the root and the whole world moves.

Checkpoints are append-only and monotonically numbered (``turn-0001.sav``, ...);
a turn is never overwritten or deleted, so rewinding keeps the full decision
tree. ``meta.json`` tracks the head turn, the next free number, and each turn's
parent plus breadcrumbs (command, score, last line of output).
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

STORY_SUFFIXES = {".z1", ".z2", ".z3", ".z4", ".z5", ".z6", ".z7", ".z8"}


def _xdg_data() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


FROBOZZ_HOME = _xdg_data() / "frobozz"
GAMES_DIR = FROBOZZ_HOME / "games"
SAVES_DIR = FROBOZZ_HOME / "saves"


def ensure_dirs() -> None:
    """Create the root tree on first run. (On a laptop the parent always exists,
    so create-on-first-use is correct here — unlike a mounted-volume server.)"""
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    SAVES_DIR.mkdir(parents=True, exist_ok=True)


# --- story files -----------------------------------------------------------


def list_story_files() -> list[Path]:
    if not GAMES_DIR.exists():
        return []
    return sorted(p for p in GAMES_DIR.iterdir() if p.suffix.lower() in STORY_SUFFIXES)


def resolve_story(name: str) -> Path:
    """Find a story file in GAMES_DIR by filename, stem, or unambiguous prefix
    (case-insensitive). Raises FileNotFoundError if missing or ambiguous."""
    stories = list_story_files()
    name_l = name.lower()
    for p in stories:
        if p.name.lower() == name_l or p.stem.lower() == name_l:
            return p
    matches = [
        p
        for p in stories
        if p.name.lower().startswith(name_l) or p.stem.lower().startswith(name_l)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise FileNotFoundError(f"'{name}' is ambiguous: {names}")
    raise FileNotFoundError(f"no story file matching '{name}' in {GAMES_DIR}")


# --- playthrough paths -----------------------------------------------------


def mint_game_id(story_path: Path) -> str:
    slug = re.split(r"[^a-z0-9]+", story_path.stem.lower())[0] or "game"
    return f"{slug}-{secrets.token_hex(3)}"


def game_dir(game_id: str) -> Path:
    return SAVES_DIR / game_id


def save_path(game_id: str, turn: int) -> Path:
    return game_dir(game_id) / f"turn-{turn:04d}.sav"


def meta_path(game_id: str) -> Path:
    return game_dir(game_id) / "meta.json"


# --- meta.json -------------------------------------------------------------


def load_meta(game_id: str) -> dict[str, Any]:
    p = meta_path(game_id)
    if not p.exists():
        raise FileNotFoundError(f"no active game '{game_id}'")
    return json.loads(p.read_text())


def save_meta(game_id: str, meta: dict[str, Any]) -> None:
    """Atomic write: temp file in the same dir, then os.replace."""
    p = meta_path(game_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.parent / (p.name + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2))
    os.replace(tmp, p)


def list_active() -> list[dict[str, Any]]:
    if not SAVES_DIR.exists():
        return []
    rows: list[dict[str, Any]] = []
    for d in sorted(SAVES_DIR.iterdir()):
        mp = d / "meta.json"
        if not mp.exists():
            continue
        try:
            rows.append(json.loads(mp.read_text()))
        except json.JSONDecodeError:
            continue
    return rows


# --- small helpers ---------------------------------------------------------


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def summarize(output: str) -> str:
    """Rough breadcrumb for `list-active-games`: last non-empty line, truncated."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return (lines[-1] if lines else "")[:70]
