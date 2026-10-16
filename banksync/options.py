"""Option handling. Each option is resolved from these layers, where later layers win:

1. the defaults below
2. the user's ~/.bankconfigrc, an INI file with `[section]` headers and `key = value` lines
3. the "configuration" section of the syncfile, with keys such as "sync.matching" (general and sync options only)
4. the command line

Options are named `section.key`, e.g. `sync.matching` or `general.verbosity`. Keys are case insensitive.
"""

from __future__ import annotations

import configparser
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from .util import BanksyncError

type Matching = Literal["shaOnly", "timestamp", "closetimestamp"]
type SyncBranches = Literal["no", "yes", "force"]
type Colorize = Literal["auto", "yes", "no"]

MATCHING_VALUES: tuple[Matching, ...] = get_args(Matching.__value__)
SYNC_BRANCHES_VALUES: tuple[SyncBranches, ...] = get_args(SyncBranches.__value__)
COLORIZE_VALUES: tuple[Colorize, ...] = get_args(Colorize.__value__)
VERBOSITY_VALUES = (0, 1, 2, 3, 4)

RC_FILE_NAME = ".bankconfigrc"

# The option sections that a syncfile's "configuration" section may set. (create_syncrepo options would be
# meaningless there, since the syncfile already exists.)
SYNCFILE_OPTION_SECTIONS = ("general", "sync")

DEFAULTS: dict[str, str] = {
    "general.verbosity": "2",  # see console.Level
    "general.colorize": "auto",  # color the output when it goes to a terminal and NO_COLOR is not set
    "general.separator": " ",  # the character repeated to separate the output of `bank git` for each repo
    "sync.matching": "closetimestamp",
    "sync.syncbranches": "no",
    "create_syncrepo.syncfilename": "syncfile.json",
    "create_syncrepo.syncreponame": "syncrepo",
}

type OptionLayer = Mapping[str, str]


def flatten(nested: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten {'sync': {'matching': 'timestamp'}} to {'sync.matching': 'timestamp'}, lower-casing the keys."""
    flat: dict[str, str] = {}
    for key, value in nested.items():
        name = f"{prefix}{key.lower()}"
        if isinstance(value, Mapping):
            flat.update(flatten(value, f"{name}."))
        else:
            flat[name] = str(value)
    return flat


def read_rc_file(path: Path) -> dict[str, str]:
    """Read an INI style options file into flat `section.key` options."""
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except configparser.Error as error:
        raise BanksyncError(f"failure! could not read the options in {path}: {error}") from error
    return flatten({section: dict(parser[section]) for section in parser.sections()})


def user_rc_layer() -> dict[str, str]:
    path = Path.home() / RC_FILE_NAME
    return read_rc_file(path) if path.is_file() else {}


def syncfile_layer(configuration: Mapping[str, Any]) -> dict[str, str]:
    """The options set in a syncfile's "configuration" section, e.g. {"sync.matching": "timestamp"}.

    Other entries there, such as relativePathToRepositories or clone.syncreponame, are not options and are ignored."""
    return {
        name: value
        for name, value in flatten(configuration).items()
        if name in DEFAULTS and name.split(".")[0] in SYNCFILE_OPTION_SECTIONS
    }


def merge(*layers: OptionLayer) -> dict[str, str]:
    """Merge option layers; later layers win."""
    merged: dict[str, str] = {}
    for layer in layers:
        merged.update(layer)
    return merged


def _choice[T: str](options: Mapping[str, str], name: str, choices: tuple[T, ...]) -> T:
    value = options[name]
    for choice in choices:
        if value.lower() == choice.lower():
            return choice
    raise BanksyncError(f"failure! invalid value '{value}' for option {name}; expected one of: {', '.join(choices)}")


def _colorize(options: Mapping[str, str]) -> bool:
    value = options["general.colorize"]
    value = {"true": "yes", "false": "no"}.get(value.lower(), value)
    match _choice({"general.colorize": value}, "general.colorize", COLORIZE_VALUES):
        case "yes":
            return True
        case "no":
            return False
        case "auto":
            return terminal_wants_color()


def terminal_wants_color() -> bool:
    """Whether to color output by default: only on a terminal, and never if NO_COLOR is set (see no-color.org)."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def _verbosity(options: Mapping[str, str]) -> int:
    value = options["general.verbosity"]
    if not value.isdigit() or int(value) not in VERBOSITY_VALUES:
        raise BanksyncError(f"failure! invalid value '{value}' for option general.verbosity; expected 0 to 4")
    return int(value)


@dataclass(frozen=True)
class Options:
    verbosity: int
    colorize: bool
    dryrun: bool
    separator: str
    matching: Matching
    sync_branches: SyncBranches
    syncfilename: str
    syncreponame: str

    @classmethod
    def resolve(cls, *layers: OptionLayer, dryrun: bool = False) -> Options:
        """Combine the defaults with the given layers (later layers win) and validate the result."""
        options = merge(DEFAULTS, *layers)
        return cls(
            verbosity=_verbosity(options),
            colorize=_colorize(options),
            dryrun=dryrun,
            separator=options["general.separator"],
            matching=_choice(options, "sync.matching", MATCHING_VALUES),
            sync_branches=_choice(options, "sync.syncbranches", SYNC_BRANCHES_VALUES),
            syncfilename=options["create_syncrepo.syncfilename"],
            syncreponame=options["create_syncrepo.syncreponame"],
        )
