"""Option handling: defaults, overridden by the user's ~/.bankconfigrc, overridden by the command line.

Options are named `section.key`, e.g. `sync.matching`, matching the `[section]` / `key = value` layout of the INI
style ~/.bankconfigrc file.
"""

from __future__ import annotations

import configparser
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from .util import BanksyncError

type Matching = Literal["shaOnly", "timestamp", "closetimestamp"]
type SyncBranches = Literal["no", "yes", "force"]
type YesNo = Literal["yes", "no"]

MATCHING_VALUES: tuple[Matching, ...] = get_args(Matching.__value__)
SYNC_BRANCHES_VALUES: tuple[SyncBranches, ...] = get_args(SyncBranches.__value__)
COLORIZE_VALUES: tuple[YesNo, ...] = get_args(YesNo.__value__)
VERBOSITY_VALUES = (0, 1, 2, 3, 4)

RC_FILE_NAME = ".bankconfigrc"

DEFAULTS: dict[str, str] = {
    "general.verbosity": "2",  # see console.Level
    "general.colorize": "yes",
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
            colorize=_choice(options, "general.colorize", COLORIZE_VALUES) == "yes",
            dryrun=dryrun,
            separator=options["general.separator"],
            matching=_choice(options, "sync.matching", MATCHING_VALUES),
            sync_branches=_choice(options, "sync.syncbranches", SYNC_BRANCHES_VALUES),
            syncfilename=options["create_syncrepo.syncfilename"],
            syncreponame=options["create_syncrepo.syncreponame"],
        )
