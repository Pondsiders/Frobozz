# Frobozz

**Interactive fiction for agents.** A minimal command-line tool for playing
Infocom-era text adventures from inside a stateless, tool-calling harness —
one turn at a time, with the whole game living on disk between calls.

## Why this exists

An LLM agent lives in a turn-based, stateless world: each tool call is
independent, and no process survives from one call to the next. Interactive
fiction is *also* turn-based — you type one command, the game answers, repeat.
The two fit together almost suspiciously well.

Frobozz is the bridge. Every invocation loads a saved game, runs a single
command, prints the result to stdout, and writes a fresh checkpoint. There's no
daemon, no session protocol, no special runtime — just a CLI that happens to
hold an entire world in a save file. An agent plays the way it does anything
else: it calls a command and reads the output.

The neat part is what *doesn't* need to exist. There's no parser to translate
the agent's intent into a game command, because the tool call **is** the
command. The agent reasons in natural language, emits one verb-phrase, and the
z-machine answers. Function calling turns out to be the parser interactive
fiction always wanted.

## Install

Frobozz is a [uv](https://docs.astral.sh/uv/) tool. Python 3.12+.

Run it ad hoc, straight from GitHub:

```sh
uvx --from git+https://github.com/Pondsiders/Frobozz frobozz list-games
```

Or install it so `frobozz` is on your PATH:

```sh
uv tool install git+https://github.com/Pondsiders/Frobozz
frobozz list-games
```

## Game files

Frobozz ships **no** game files — bring your own. Drop standard z-machine story
files (`.z3`, `.z4`, `.z5`, … any of `.z1`–`.z8`) into the games directory:

```
~/.local/share/frobozz/games/
```

(That's `$XDG_DATA_HOME/frobozz/games/` if you've set `XDG_DATA_HOME`.) The
directory is created on first run. For example:

```
~/.local/share/frobozz/games/
    zork1-r88-s840726.z3
    amfv-r77-s850814.z4
```

A note on obtaining story files: Microsoft released the source for **Zork I, II,
and III** under the MIT License in 2025, so those are free and clear. Most other
Infocom titles remain copyrighted (and widely archived); play the ones you own.

## Playing

```sh
# What's installed?
frobozz list-games

# Begin a playthrough. Prints the opening and a game id you'll reuse.
frobozz start zork1
#  West of House                                    Score: 0   Moves: 0
#
#  West of House
#  You are standing in an open field west of a white house, with a
#  boarded front door. There is a small mailbox here.
#
#  — game id: zork1-3f9a2c —

# Take a turn. Quote multi-word commands.
frobozz do zork1-3f9a2c "open mailbox"

# look / inventory / restart are just commands:
frobozz do zork1-3f9a2c "look"

# Made a mistake (or got eaten by a grue)? Step back. Nothing is lost.
frobozz rewind zork1-3f9a2c -n 1

# Resume any game in progress:
frobozz list-active-games
```

### Commands

| command | what it does |
|---|---|
| `list-games` | list available story files |
| `start <game>` | begin a new playthrough; prints the opening and a new game id |
| `do <game-id> <command>` | send one command; prints the game's response |
| `rewind <game-id> [-n N]` | move the game's head back N turns (default 1) |
| `list-active-games` | list playthroughs in progress, with turn, score, and last line |

## How state works

Each playthrough is one directory under a single root, holding **append-only,
numbered checkpoints** plus a small metadata file:

```
~/.local/share/frobozz/
    games/
        zork1-r88-s840726.z3
    saves/
        zork1-3f9a2c/
            meta.json
            turn-0001.sav
            turn-0002.sav
            ...
```

A turn is never overwritten or deleted. Each checkpoint records its parent, so
`rewind` doesn't discard the future — it just moves a pointer back, and the next
command branches from there. The entire decision tree stays on disk. Because
it's one root, you can `rsync ~/.local/share/frobozz` to move or share every
game, every playthrough, and every road not taken in a single shot.

## Status lines

Frobozz reconstructs the game's status line, whichever way the game draws it:

- **v4+ games** (e.g. *A Mind Forever Voyaging*) paint a positioned upper-window
  panel — mode, time, location, date — and Frobozz renders it laid out, where it
  belongs, instead of smeared into the prose.
- **v3 games** (*Zork*, *Cutthroats*, *Wishbringer*, the mysteries) use the old
  automatic status line, which Frobozz synthesizes from game state: location on
  the left, score and moves (or the clock, for time games) on the right.

## Under the hood

The z-machine interpreter is [xyppy](https://github.com/theinternetftw/xyppy),
vendored into the source tree (`src/frobozz/vendor/xyppy/`, MIT) so the tool
stands entirely alone. Frobozz replaces xyppy's terminal screen with a
programmatic one that captures the scrolling story as a clean text stream and
the status panel as a positioned grid. Each `do` is stateless: construct the
interpreter, restore the latest checkpoint, step exactly one command, capture
the output, write the next checkpoint, tear down.

## Name

The **Frobozz Magic Tool Company** is, per Infocom canon, the firm responsible
for manufacturing everything in Zork's Great Underground Empire. It seemed only
right.

## License

Frobozz is released under the MIT License. The vendored xyppy interpreter is
also MIT (see `src/frobozz/vendor/xyppy/LICENSE`). Story files are yours, and
are not included.
