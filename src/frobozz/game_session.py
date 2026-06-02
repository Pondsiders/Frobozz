"""
GameSession: Clean interface for running Z-machine games programmatically.

This module provides a high-level API for:
- Loading Z-machine story files
- Running games turn-by-turn
- Controlling randomness for reproducibility
- Managing game state
"""

import random
import sys
from pathlib import Path

# Add vendored xyppy to path
vendor_path = Path(__file__).parent / "vendor"
sys.path.insert(0, str(vendor_path))

from xyppy import zenv, ops, quetzal, ops_impl  # noqa: E402

from .screen import ProgrammaticScreen  # noqa: E402


class GameSession:
    """
    High-level interface for programmatic Z-machine control.

    Example usage:
        session = GameSession("games/zork1.z5", random_seed=0)
        output = session.start()
        print(output)

        while not session.is_finished():
            command = get_next_command()
            output = session.send_command(command)
            print(output)
    """

    def __init__(self, story_path: str, random_seed: int = 0):
        """
        Initialize a game session.

        Args:
            story_path: Path to the Z-machine story file (.z3, .z5, etc.)
            random_seed: Random seed for deterministic behavior (default: 0)
        """
        # Set random seed for deterministic behavior
        random.seed(random_seed)

        # Load story file
        with open(story_path, "rb") as f:
            story_data = f.read()

        # Create a minimal args object (xyppy expects this)
        class Args:
            no_slow_scroll = True

        # Create environment
        self.env = zenv.Env(story_data, Args())

        # Replace the screen with our programmatic version
        self.screen = ProgrammaticScreen(self.env)
        self.env.screen = self.screen

        # Setup opcodes
        ops.setup_opcodes(self.env)

        self._started = False
        self._finished = False
        self._turn_count = 0

    def start(self) -> str:
        """
        Start the game and return initial output.

        Returns:
            The game's initial text (intro, location description, etc.)

        Raises:
            RuntimeError: If the game has already been started
        """
        if self._started:
            raise RuntimeError("Game already started")

        self._started = True

        # Run until the screen signals it's waiting for input
        try:
            while not self.screen.waiting_for_input:
                prev_pc = self.env.pc  # Save PC before step
                zenv.step(self.env)
            return self.screen.get_output()
        except StopIteration:
            # Restore PC so the READ instruction will be re-executed
            # when we resume (instead of being skipped)
            if self.screen.waiting_for_input:
                self.env.pc = prev_pc
            return self.screen.get_output()

    def send_command(self, command: str) -> str:
        """
        Send a command to the game and return the resulting output.

        Args:
            command: The command string (e.g., "open mailbox", "north")

        Returns:
            The game's response to the command

        Raises:
            RuntimeError: If the game hasn't been started yet
        """
        if not self._started:
            raise RuntimeError("Game not started - call start() first")

        if self._finished:
            raise RuntimeError("Game has finished")

        # Queue the command and reset the counter
        self.screen.queue_command(command)
        self.screen.commands_dispensed = 0
        self._turn_count += 1

        # Resume execution until StopIteration (command processed) or SystemExit (game quit)
        try:
            while True:
                prev_pc = self.env.pc  # Save PC before step
                zenv.step(self.env)
        except StopIteration:
            # Restore PC so the READ instruction will be re-executed
            # when we resume (instead of being skipped)
            if self.screen.waiting_for_input:
                self.env.pc = prev_pc
            return self.screen.get_output()
        except SystemExit:
            # Game has quit
            self._finished = True
            return self.screen.get_output()

    def get_status(self) -> str:
        """Return the status line: the upper-window panel for v4+ games (the
        score bar in Zork-era v4, the date/mode display in AMFV), or — for v3
        games, whose status line xyppy's show_status opcode never draws — the
        classic v3 bar synthesized from game state. Returns '' if there's none."""
        panel = self.screen.get_status()
        if panel:
            return panel
        if self.env.hdr.version <= 3:
            return self._v3_status_line()
        return ""

    def _v3_status_line(self) -> str:
        """Synthesize the classic v3 status bar from the z-machine globals:
        location is the object in global 0; the right side is score/moves for a
        "score game" or the clock for a "time game" (Flags 1, bit 1)."""
        env = self.env
        loc_obj = ops_impl.get_var(env, 0x10, pop_stack=False)  # global 0
        if not loc_obj:
            return ""
        location = ops_impl.get_obj_str(env, loc_obj).strip()

        if env.hdr.flags1 & 0x02:  # time game
            hours = ops_impl.get_var(env, 0x11, pop_stack=False)
            minutes = ops_impl.get_var(env, 0x12, pop_stack=False)
            ampm = "am" if hours < 12 else "pm"
            h12 = hours % 12 or 12
            right = f"Time: {h12}:{minutes:02d} {ampm}"
        else:  # score game
            score = ops_impl.to_signed_word(
                ops_impl.get_var(env, 0x11, pop_stack=False)
            )
            moves = ops_impl.get_var(env, 0x12, pop_stack=False)
            right = f"Score: {score}   Moves: {moves}"

        width = env.hdr.screen_width_units
        left = " " + location
        right = right + " "
        pad = max(1, width - len(left) - len(right))
        return left + " " * pad + right

    def is_finished(self) -> bool:
        """
        Check if the game has finished (quit/died).

        Returns:
            True if the game is over, False otherwise
        """
        return self._finished

    def get_turn_count(self) -> int:
        """
        Get the number of commands sent so far.

        Returns:
            The turn count (number of times send_command() was called)
        """
        return self._turn_count

    @property
    def memory(self):
        """
        Direct access to Z-machine memory (for advanced use cases).

        Returns:
            The memory array from the xyppy environment
        """
        return self.env.mem

    @property
    def program_counter(self) -> int:
        """
        Current program counter value (for debugging/analysis).

        Returns:
            The current PC value
        """
        return self.env.pc

    def save_state(self, save_path: str) -> bool:
        """
        Save the current game state to a Quetzal save file.

        This creates a standard Z-machine save file that can be restored
        later to resume from this exact point in the game.

        Args:
            save_path: Path to save the state file (.sav extension will be added if missing)

        Returns:
            True if save succeeded, False otherwise
        """
        return quetzal.write(self.env, save_path)

    def restore_state(self, save_path: str) -> bool:
        """
        Restore game state from a Quetzal save file.

        This loads a previously saved state, allowing you to resume from
        that exact point in the game. After restoring, the game will be
        in the "started" state and ready to accept commands.

        Args:
            save_path: Path to the save file to restore

        Returns:
            True if restore succeeded, False otherwise

        Raises:
            RuntimeError: If called after the game has been started
        """
        if self._started:
            raise RuntimeError("Cannot restore state after game has started")

        success = quetzal.load_to_env(self.env, save_path)
        if success:
            self._started = True

            # quetzal.load_to_env() calls env.reset(), which re-initializes
            # the environment and replaces our screen. Re-attach our screen.
            self.env.screen = self.screen

            # After restore, PC points at the SAVE instruction.
            # We need to skip past it and set the return value.
            # This matches how xyppy's interactive restore works.
            if self.env.hdr.version < 4:
                # Z3: Move past the SAVE instruction's branch byte(s)
                # Branch format bit 6 determines if it's 1 or 2 bytes
                self.env.pc += 1 if self.env.mem[self.env.pc] & 64 else 2
                self.env.last_pc_branch_var = self.env.pc
            else:
                # Z4+: Set the store variable to 2 (restore success), then skip past it
                store_var = self.env.mem[self.env.pc]
                ops_impl.set_var(self.env, store_var, 2)
                self.env.pc += 1
                self.env.last_pc_store_var = self.env.pc

            # Reset screen state after restore
            self.screen.output_buffer.clear()
            self.screen.command_queue.clear()
            self.screen.waiting_for_input = True
            self.screen.commands_dispensed = 0
        return success

    def get_score(self) -> dict[str, int | str]:
        """
        Get the current score or time from the game.

        In Z-machine Version 3 games, bit 1 of Flags 1 (header byte 0x01)
        determines the game type:
        - Bit 1 clear (0): SCORE game - globals hold score and moves
        - Bit 1 set (1): TIME game - globals hold hours and minutes

        For SCORE games:
        - Global variable 1 (var 17): Current score
        - Global variable 2 (var 18): Number of moves/turns

        For TIME games:
        - Global variable 1 (var 17): Hours (24-hour format)
        - Global variable 2 (var 18): Minutes

        Returns:
            Dictionary with keys:
            - 'type': 'score' or 'time'
            - 'score': int (for score games)
            - 'moves': int (for score games)
            - 'time': str formatted as "H:MM am/pm" (for time games)

        Raises:
            RuntimeError: If the game hasn't been started yet
        """
        if not self._started:
            raise RuntimeError("Game not started - call start() first")

        # Check Flags 1 bit 1 to determine game type (Version 3 only)
        flags1 = self.env.mem[0x01]
        is_time_game = (flags1 & 0x02) != 0

        if is_time_game:
            # TIME game - read hours and minutes
            hours = ops_impl.get_var(self.env, 17, pop_stack=False)
            minutes = ops_impl.get_var(self.env, 18, pop_stack=False)

            # Convert 24-hour to 12-hour format with am/pm
            am_pm = "am" if hours < 12 else "pm"
            display_hour = hours % 12
            if display_hour == 0:
                display_hour = 12

            time_str = f"{display_hour}:{minutes:02d} {am_pm}"

            return {"type": "time", "time": time_str}
        else:
            # SCORE game - read score and moves
            score = ops_impl.get_var(self.env, 17, pop_stack=False)
            moves = ops_impl.get_var(self.env, 18, pop_stack=False)

            # Convert to signed 16-bit integers
            if score >= 0x8000:
                score = score - 0x10000
            if moves >= 0x8000:
                moves = moves - 0x10000

            return {"type": "score", "score": score, "moves": moves}
