"""Terminal output for banksync: messages gated by verbosity, with optional ANSI colors."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Level(IntEnum):
    """The verbosity at which a message is shown. A message is printed when `--verbosity` is at least its level."""

    SUMMARY = 1  # the overall success or failure of a command
    REPO = 2  # one line per repository (the default verbosity)
    COMMAND = 3  # git commands that change a repository, together with their output
    QUERY = 4  # read-only git queries, together with their output


class Color(StrEnum):
    RED = "31"
    GREEN = "32"
    YELLOW = "33"
    BLUE = "34"
    DIM = "2"  # dimmed rather than grey, since grey can be indistinguishable from black text


@dataclass
class Console:
    verbosity: int = Level.REPO
    colorize: bool = True
    _progress_shown: bool = False

    # ----- colors -----

    def paint(self, text: str, color: Color) -> str:
        return f"\033[{color}m{text}\033[0m" if self.colorize else text

    def red(self, text: str) -> str:
        return self.paint(text, Color.RED)

    def green(self, text: str) -> str:
        return self.paint(text, Color.GREEN)

    def yellow(self, text: str) -> str:
        return self.paint(text, Color.YELLOW)

    def blue(self, text: str) -> str:
        return self.paint(text, Color.BLUE)

    def dim(self, text: str) -> str:
        return self.paint(text, Color.DIM)

    # ----- output -----

    def shows(self, level: int) -> bool:
        return self.verbosity >= level

    def say(self, message: str, level: int = Level.REPO) -> None:
        """Print a message if the verbosity is at least `level`."""
        if self.shows(level):
            self._clear_progress()
            print(message, flush=True)

    def success(self, message: str, level: int = Level.SUMMARY) -> None:
        self.say(self.green(message), level)

    def failure(self, message: str, level: int = Level.SUMMARY) -> None:
        self.say(self.red(message), level)

    def progress(self, message: str) -> None:
        """Show a transient status line on a terminal. The next message printed replaces it."""
        if self.shows(Level.REPO) and sys.stdout.isatty():
            self._clear_progress()
            print(message, end="", flush=True)
            self._progress_shown = True

    def _clear_progress(self) -> None:
        if self._progress_shown:
            print("\r\033[K", end="")
            self._progress_shown = False


# The console used by all of banksync. `main` configures its verbosity and colorize settings.
console = Console()
