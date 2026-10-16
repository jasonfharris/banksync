"""Small helpers with no knowledge of git or syncfiles."""

from __future__ import annotations

import datetime
import os
import re
import shutil
import tempfile
import textwrap
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit


class BanksyncError(Exception):
    """An error that ends the current command. `main` prints the message and exits with status 1."""


def date_from_timestamp(timestamp: str | int) -> str:
    """Format a Unix timestamp as a local date and time, e.g. '2016-11-30 15:46:40'."""
    return datetime.datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")


def is_sha1(text: str) -> bool:
    return re.fullmatch(r"[0-9a-fA-F]{40}", text) is not None


def wrap_paragraphs(text: str, width: int = 80) -> str:
    """Wrap each paragraph (separated by blank lines) of `text` to `width` columns."""
    return "\n\n".join(textwrap.fill(paragraph, width) for paragraph in text.split("\n\n"))


def padded(name: str, names: Iterable[str]) -> str:
    """Pad `name` to the length of the longest of `names`, so that per-repo output lines up."""
    return name.ljust(max((len(n) for n in names), default=0))


def relative_to_cwd(path: str | os.PathLike[str]) -> str:
    return os.path.relpath(path, os.getcwd())


def version_less_or_equal(version1: str, version2: str) -> bool:
    """Compare dotted numeric versions, treating missing trailing parts as 0: '2.2.3' <= '2.2.3.0' <= '2.2.4'."""
    parts1 = [int(part) for part in version1.split(".")]
    parts2 = [int(part) for part in version2.split(".")]
    length = max(len(parts1), len(parts2))
    parts1 += [0] * (length - len(parts1))
    parts2 += [0] * (length - len(parts2))
    return parts1 <= parts2


def unique_dir_name(base: str) -> str:
    """Return `base`, or `base_1`, `base_2`, ... whichever does not exist yet."""
    name, counter = base, 1
    while os.path.exists(name):
        name = f"{base}_{counter}"
        counter += 1
    return name


def repo_name_from_url(url: str) -> str:
    """Derive a project directory name from a syncrepo URL: '.../animalsSyncRepo.git' -> 'animals'."""
    name, _ = os.path.splitext(os.path.basename(urlsplit(url).path))
    name = re.sub(r"(?:_?sync_repo|_?syncRepo|_?SyncRepo)$", "", name)
    if any(char.isascii() and char.isalnum() for char in name):
        return name.strip("_")
    return unique_dir_name("WrapperProject")


_GIT_URL = re.compile(
    r"(?:(?:https?|git|ssh|rsync)://|(?:(?:[^@]+@)?[^:/]+:))"  # a protocol, or user@host: for scp-like syntax
    r"(?:[^/]+/)+"  # at least one directory
    r"[^/]+(?:\.git)?$"  # the repository name, optionally ending in .git
)


def is_valid_git_url(url: str) -> bool:
    """Whether `url` looks like something `git clone` accepts: a URL, scp-like address, or existing local path."""
    return _GIT_URL.match(url) is not None or os.path.exists(url)


def move_directory(source: Path, destination: Path) -> None:
    """Move a directory, even into a subdirectory of itself (e.g. `project` to `project/syncrepo`)."""
    if not source.exists():
        raise ValueError(f"Source directory {source} does not exist")
    if destination.exists():
        raise ValueError(f"Destination directory {destination} already exists")
    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir) / source.name
        shutil.move(source, staging)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(staging, destination)
