"""Run external commands the way a shell script would, but without a shell in between.

Each argument is passed to the program exactly as given. Nothing is re-interpreted: no quoting, globbing, or
`{name}` substitution, so commit messages, paths, and revisions such as `HEAD@{1}` arrive intact.

    git("checkout", "--quiet", sha, cwd=repo)                        # run; returns a Result
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)  # stdout, or None on failure
    if not git("show-ref", "--verify", "--quiet", ref, cwd=repo).ok:
        ...

The command line and its output are printed when the verbosity is at least `show` (by default Level.COMMAND).
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import TypedDict, Unpack

from .console import Level, console

type Arg = str | os.PathLike[str]


@dataclass(frozen=True)
class Result:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandFailed(Exception):
    def __init__(self, result: Result) -> None:
        detail = result.stderr.strip() or result.stdout.strip()
        super().__init__(f"`{shlex.join(result.args)}` failed with exit code {result.returncode}: {detail}")
        self.result = result


class RunOptions(TypedDict, total=False):
    cwd: Arg
    show: int
    stream: bool
    dryrun: bool
    check: bool


def describe(args: tuple[str, ...], cwd: Arg = ".") -> str:
    """Render a command like a shell prompt line, prefixed with its directory when that is not the current one."""
    command = shlex.join(args)
    directory = os.fspath(cwd)
    if os.path.abspath(directory) == os.getcwd():
        return f"$ {command}"
    return f"({os.path.relpath(directory)}) $ {command}"


def run(
    *args: Arg,
    cwd: Arg = ".",
    show: int = Level.COMMAND,
    stream: bool = False,
    dryrun: bool = False,
    check: bool = False,
) -> Result:
    """Run a command and return its Result.

    cwd:    the directory to run the command in.
    show:   the verbosity at which the command line and its output are printed.
    stream: connect the command straight to the terminal (when shown) instead of capturing its output. Use this for
            commands whose output is the point, such as `bank git log`, or which report progress, such as clone.
    dryrun: print the command that would run instead of running it, and return a successful Result.
    check:  raise CommandFailed if the command exits with a non-zero status.
    """
    argv = tuple(os.fspath(arg) for arg in args)
    if dryrun:
        console.say(f"would run: {describe(argv, cwd)}", Level.REPO)
        return Result(argv, 0)

    shown = console.shows(show)
    if shown:
        console.say(console.dim(describe(argv, cwd)), show)

    if stream and shown:
        completed = subprocess.run(argv, cwd=cwd)
        result = Result(argv, completed.returncode)
    else:
        captured = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, errors="replace")
        result = Result(argv, captured.returncode, captured.stdout, captured.stderr)
        if shown:
            if result.stdout.strip():
                console.say(result.stdout.rstrip(), show)
            if result.stderr.strip():
                console.say(console.red(result.stderr.rstrip()), show)

    if check and not result.ok:
        raise CommandFailed(result)
    return result


def git(*args: Arg, **options: Unpack[RunOptions]) -> Result:
    """Run `git <args>`. Takes the same keyword options as `run`."""
    return run("git", *args, **options)


def git_output(*args: Arg, cwd: Arg = ".") -> str | None:
    """Run a read-only git query and return its stripped stdout, or None if git fails."""
    result = git(*args, cwd=cwd, show=Level.QUERY)
    return result.stdout.strip() if result.ok else None
