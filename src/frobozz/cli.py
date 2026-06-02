"""Frobozz CLI.

Turn-by-turn z-machine play. Each invocation loads the head checkpoint for a
game, steps one command, prints the game's output, and writes a new
(append-only, numbered) checkpoint. State lives on disk under a single XDG root
(see storage.py).
"""

from __future__ import annotations

from typing import Any

import click

from . import storage
from .game_session import GameSession


def _save_checkpoint(sess: GameSession, game_id: str, turn: int) -> None:
    if not sess.save_state(str(storage.save_path(game_id, turn))):
        raise click.ClickException(
            f"failed to write checkpoint turn-{turn:04d} for {game_id}"
        )


def _turn_record(
    sess: GameSession, parent: int | None, command: str | None, output: str
) -> dict[str, Any]:
    return {
        "parent": parent,
        "command": command,
        "score": sess.get_score(),
        "status": sess.get_status(),
        "summary": storage.summarize(output),
        "ended": sess.is_finished(),
    }


def _echo_turn(status: str, body: str) -> None:
    """Print a turn: the status panel (if the game draws one) as a header,
    then a blank line, then the narrative."""
    if status:
        click.echo(status)
        click.echo()
    click.echo(body.rstrip())


@click.group()
@click.version_option()
def main() -> None:
    """Play interactive fiction, one turn at a time."""


@main.command("list-games")
def list_games() -> None:
    """List available story files."""
    storage.ensure_dirs()
    stories = storage.list_story_files()
    if not stories:
        click.echo(f"No games in {storage.GAMES_DIR}")
        return
    for p in stories:
        click.echo(p.name)


@main.command("start")
@click.argument("game")
def start(game: str) -> None:
    """Start a new playthrough of GAME; print the opening and the new game id."""
    storage.ensure_dirs()
    try:
        story = storage.resolve_story(game)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    game_id = storage.mint_game_id(story)
    storage.game_dir(game_id).mkdir(parents=True, exist_ok=True)

    sess = GameSession(str(story), random_seed=0)
    opening = sess.start()
    _save_checkpoint(sess, game_id, 1)

    meta: dict[str, Any] = {
        "story": story.name,
        "game_id": game_id,
        "created_at": storage.now_iso(),
        "head": 1,
        "next_turn": 2,
        "turns": {"1": _turn_record(sess, parent=None, command=None, output=opening)},
    }
    storage.save_meta(game_id, meta)

    _echo_turn(sess.get_status(), opening)
    click.echo(f"\n— game id: {game_id} —")


@main.command("do")
@click.argument("game_id")
@click.argument("command")
def do(game_id: str, command: str) -> None:
    """Send COMMAND to GAME_ID and print the result. Quote multi-word commands."""
    try:
        meta = storage.load_meta(game_id)
        story = storage.resolve_story(meta["story"])
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    head: int = meta["head"]
    sess = GameSession(str(story), random_seed=0)
    if not sess.restore_state(str(storage.save_path(game_id, head))):
        raise click.ClickException(
            f"failed to restore checkpoint turn-{head:04d} for {game_id}"
        )

    output = sess.send_command(command)

    new_turn: int = meta["next_turn"]
    _save_checkpoint(sess, game_id, new_turn)
    meta["turns"][str(new_turn)] = _turn_record(
        sess, parent=head, command=command, output=output
    )
    meta["head"] = new_turn
    meta["next_turn"] = new_turn + 1
    storage.save_meta(game_id, meta)

    _echo_turn(sess.get_status(), output)


@main.command("rewind")
@click.argument("game_id")
@click.option("-n", "turns", default=1, show_default=True, help="Turns to rewind.")
def rewind(game_id: str, turns: int) -> None:
    """Move GAME_ID's head back TURNS turns. Older checkpoints are kept; the next
    `do` branches from here, so nothing is ever lost."""
    try:
        meta = storage.load_meta(game_id)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e

    head: int = meta["head"]
    for _ in range(turns):
        parent = meta["turns"][str(head)]["parent"]
        if parent is None:
            break
        head = parent
    meta["head"] = head
    storage.save_meta(game_id, meta)

    rec = meta["turns"][str(head)]
    click.echo(f"[rewound to turn {head}: {rec['summary'] or 'start'}]")
    click.echo(f"do {game_id} look   # to re-orient")


@main.command("list-active-games")
def list_active_games() -> None:
    """List in-progress playthroughs: id, story, head turn, score, last line."""
    storage.ensure_dirs()
    rows = storage.list_active()
    if not rows:
        click.echo(f"No active games in {storage.SAVES_DIR}")
        return
    for m in rows:
        head = m.get("head")
        rec = m.get("turns", {}).get(str(head), {})
        score = rec.get("score", {})
        sc = (
            score.get("score", score.get("time", "?"))
            if isinstance(score, dict)
            else "?"
        )
        moves = score.get("moves", "?") if isinstance(score, dict) else "?"
        click.echo(
            f"{m.get('game_id', '?'):<18} {m.get('story', '?'):<28} "
            f"turn {head}  score {sc}  moves {moves}  — {rec.get('summary', '')}"
        )


if __name__ == "__main__":
    main()
