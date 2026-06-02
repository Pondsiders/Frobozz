"""
Custom Screen implementation for programmatic control of Z-machine I/O.

This replaces xyppy's terminal-based screen with one that:
- Captures the lower window (the scrolling story) as a clean text stream
- Captures the upper window (the fixed status panel) as a positioned grid
- Reads input from a command queue
- Raises StopIteration when waiting for input

The z-machine has two screen regions. The *lower window* (window 0) is the
scrolling narrative; we keep it as a plain text stream because that reads far
better than a fixed-width character grid. The *upper window* (window 1) is a
fixed, cursor-addressed panel pinned to the top — score/moves in Zork, the
Mode/Time/Location/Date display in A Mind Forever Voyaging. Games paint it by
switching `env.current_window` to 1, positioning `env.cursor[1]`, and writing
characters at coordinates. We model it as a real grid so it comes out laid out,
not smeared into the prose. See vendor/xyppy/vterm.py for the terminal version.
"""


class ProgrammaticScreen:
    """Screen implementation for xyppy that enables programmatic control."""

    def __init__(self, env):
        """
        Args:
            env: The xyppy Env object (required by xyppy's screen interface)
        """
        self.env = env
        self.output_buffer = []  # lower window: the scrolling story stream
        self.upper_rows = []  # upper window: list of rows, each a list of chars
        self.command_queue = []
        self.waiting_for_input = False
        self.commands_dispensed = 0  # Track commands given out this turn

    def queue_command(self, command: str):
        """Queue a command for the game to process."""
        self.command_queue.append(command)
        self.waiting_for_input = False

    def get_output(self) -> str:
        """
        Get accumulated lower-window (story) output and clear that buffer.
        The upper-window grid is intentionally NOT cleared here — the status
        panel is persistent and updated in place across turns, like a real one.
        """
        result = "".join(self.output_buffer)
        self.output_buffer.clear()
        result = result.rstrip("\n>")
        result = result.rstrip()
        return result

    def get_status(self) -> str:
        """Render the upper-window grid (the status panel) as text, trimming
        trailing whitespace per line and blank lines top and bottom. Returns ''
        when the game draws no panel."""
        lines = ["".join(row).rstrip() for row in self.upper_rows]
        while lines and not lines[-1]:
            lines.pop()
        while lines and not lines[0]:
            lines.pop(0)
        return "\n".join(lines)

    def write(self, text: str):
        """Capture output, routed by the current window."""
        if self.env.current_window == 1:
            self._write_upper(text)
        else:
            self.output_buffer.append(text)

    def _write_upper(self, text: str):
        """Place characters into the upper-window grid at env.cursor[1],
        advancing the cursor as the real screen does."""
        env = self.env
        width = env.hdr.screen_width_units
        height = env.hdr.screen_height_units
        row, col = env.cursor[1]
        for ch in text:
            if ch == "\n":
                row, col = row + 1, 0
                continue
            if 0 <= row < height and 0 <= col < width:
                self._ensure_rows(row, width)
                self.upper_rows[row][col] = ch
                col += 1
                if col >= width:
                    row, col = row + 1, 0
        env.cursor[1] = (row, col)

    def _ensure_rows(self, row: int, width: int):
        while len(self.upper_rows) <= row:
            self.upper_rows.append([" "] * width)

    def get_line_of_input(self, prompt: str = "", prefilled: str = "") -> str:
        """
        Called by the game when it needs a line of input. Instead of blocking on
        stdin, pulls from the command queue; raises StopIteration when empty so
        the session yields control back to the caller.
        """
        if prompt:
            self.write(prompt)

        if not self.command_queue:
            self.waiting_for_input = True
            raise StopIteration("Waiting for input")

        command = self.command_queue.pop(0)
        self.waiting_for_input = False
        self.commands_dispensed += 1
        return command

    # --- window-management interface ---------------------------------------
    # The opcodes (set_window/set_cursor/split_window/erase_window) mutate env
    # state and call back here. We render no physical terminal, so most of these
    # are no-ops; blank_top_win clears the status grid for real.

    def blank_top_win(self):
        """Clear the upper-window (status) grid."""
        width = self.env.hdr.screen_width_units
        self.upper_rows = [[" "] * width for _ in range(self.env.top_window_height)]

    def finish_wrapping(self):
        """No-op: we capture text directly and don't buffer for word-wrap."""
        pass

    def blank_bottom_win(self):
        """No-op: we accumulate the story stream per turn rather than clearing a
        physical lower window — better to keep everything that happened."""
        pass

    def scroll_top_line_only(self):
        """No-op: upper-window scrolling has no meaning for a text capture."""
        pass

    def getch_or_esc_seq(self) -> str:
        """Auto-advance single-keypress gates ("press any key" screens, [MORE]
        prompts) so intros flow straight through to the next command prompt
        instead of blocking. A space satisfies essentially all such gates."""
        return " "

    def flush(self):
        """No-op for programmatic control."""
        pass

    def first_draw(self):
        """No-op for programmatic control."""
        pass

    def update_seen_lines(self):
        """No-op for programmatic control."""
        pass

    def msg(self, text: str):
        """Display a message (used by Quetzal for error messages). We route it
        to the story buffer so it gets captured."""
        self.output_buffer.append(text)
