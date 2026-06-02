# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Frobozz plays Infocom-era interactive fiction one turn at a time from a stateless CLI, so an LLM agent can play by calling a tool and reading stdout. The tool call *is* the game command — no parser sits between the agent's intent and the z-machine. See `README.md` for the user-facing pitch and command reference.

## Commands

```sh
uv sync                                    # install
uv run frobozz list-games                  # run the CLI in-tree
uv run frobozz start zork1
uv run frobozz do <game-id> "open mailbox"

uv run ruff check src                       # lint (vendor/ is excluded)
uv run ruff format src                      # format
```

There is no test suite yet. The workshop rules reference pre-commit, but no `.pre-commit-config.yaml` is checked in here — don't assume hooks run.

## Architecture

The whole design turns on one idea: **a turn is a process lifetime.** Every `do` constructs a fresh interpreter, restores the head checkpoint, steps exactly one command, captures output, writes a new checkpoint, and exits. Nothing survives between invocations except files on disk. The layers:

- **`cli.py`** — Click command group (`main`). Each subcommand is one stateless turn. `do` is the hot path: load meta → restore head `.sav` → `send_command` → write `turn-NNNN.sav` → update `meta.json`.
- **`game_session.py`** — `GameSession` wraps the vendored xyppy z-machine. Drives `zenv.step()` in a loop until the screen signals it wants input. Also reconstructs status lines and reads score/moves (or the clock, for "time games") straight out of z-machine globals.
- **`screen.py`** — `ProgrammaticScreen` replaces xyppy's terminal screen. Lower window (the story) is captured as a plain text stream; upper window (the status panel) as a positioned character grid. Input comes from a command queue, not stdin.
- **`storage.py`** — on-disk layout, game-id minting, story-file resolution, atomic `meta.json` writes. No game logic.
- **`vendor/xyppy/`** — the z-machine interpreter, vendored unmodified (MIT). Excluded from linting. Don't edit it; all customization lives in our own layer — `screen.py` (I/O) and `game_session.py` (the turn loop and v3 status synthesis) — never the vendored tree.

### Two cross-cutting details that will bite you

**Stepping and the program counter.** xyppy has no "run one command" entry point. `GameSession` busy-loops `zenv.step()` until `ProgrammaticScreen.get_line_of_input` raises `StopIteration` (queue empty → game wants input). At that point the READ instruction has partially executed, so the session **rewinds `env.pc` to `prev_pc`** to re-run it on resume. `restore_state` does the analogous fixup by hand — after a Quetzal restore the PC sits on the SAVE/RESTORE instruction, and the code skips its branch byte(s) for v3 or sets the store var for v4+. This PC bookkeeping is load-bearing; changing the step loop without preserving it will silently corrupt play.

**Status lines differ by z-machine version.** v4+ games paint the upper window themselves, so `ProgrammaticScreen` captures it as a grid and `get_status` returns it. v3 games rely on the host's automatic status line, which xyppy never draws — so `GameSession._v3_status_line` *synthesizes* it from globals (location = global 0; right side = score/moves or clock per Flags 1 bit 1). Two code paths, one feature.

### State on disk

Single XDG root, `$XDG_DATA_HOME/frobozz` (default `~/.local/share/frobozz`): `games/` holds story files, `saves/<game-id>/` holds one playthrough. Checkpoints are **append-only and never overwritten** (`turn-0001.sav`, …). `meta.json` records `head`, `next_turn`, and a per-turn map where each turn stores its `parent`. `rewind` just walks `parent` pointers back and moves `head`; the next `do` branches from there, so the full decision tree persists. The story files referenced by a save are resolved by name through `storage.resolve_story`, so don't rename them out from under active games.
