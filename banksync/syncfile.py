"""Syncfiles: reading, writing, and finding the JSON file that describes a bank of repositories.

A syncfile looks like:

    {
        "configuration": {
            "createdByBanksyncVersion": "0.9.10",
            "requiredBanksyncVersion": "0.9.10",
            "syncfileFormatVersion": "1.0",
            "relativePathToRepositories": "..",
            "clone.syncreponame": "syncrepo"
        },
        "repositories": {
            "repoBird": {"path": "repoBird", "sha": "...", "UnixTimeStamp": "...", ...},
            ...
        }
    }

Older syncfiles have no "configuration" section and consist of just the "repositories" mapping.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import git
from .console import console
from .git import RepoInfo
from .util import BanksyncError, version_less_or_equal

LEGACY_RELATIVE_PATH_TO_REPOSITORIES = ".."


@dataclass
class SyncFile:
    path: Path  # absolute
    data: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> SyncFile:
        path = Path(os.path.abspath(path))
        check_syncfile_and_syncrepo(path)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise BanksyncError(f"failure! could not read the sync file at {path}: {error}") from error
        if not data or not isinstance(data, dict):
            raise BanksyncError(f"failure! no repos where specified in the sync file at {path}.")
        return cls(path, data)

    @property
    def syncrepo(self) -> Path:
        return self.path.parent

    @property
    def is_legacy(self) -> bool:
        return "repositories" not in self.data

    @property
    def configuration(self) -> dict[str, Any]:
        configuration = self.data.get("configuration", {})
        return configuration if isinstance(configuration, dict) else {}

    @property
    def repositories(self) -> dict[str, RepoInfo]:
        repositories: dict[str, RepoInfo] = self.data if self.is_legacy else self.data["repositories"]
        return repositories

    @repositories.setter
    def repositories(self, repositories: dict[str, RepoInfo]) -> None:
        if self.is_legacy:
            self.data = dict(repositories)
        else:
            self.data["repositories"] = repositories

    @property
    def relative_path_to_repositories(self) -> str:
        return str(self.configuration.get("relativePathToRepositories", LEGACY_RELATIVE_PATH_TO_REPOSITORIES))

    def repo_path(self, info: RepoInfo) -> Path:
        """The absolute location of a repository: its path is relative to the syncrepo plus
        relativePathToRepositories, unless it is absolute."""
        path = info["path"]
        if os.path.isabs(path):
            return Path(path)
        return Path(os.path.normpath(os.path.join(self.syncrepo, self.relative_path_to_repositories, path)))

    def write(self) -> None:
        write_syncfile(self.path, self.data)


def write_syncfile(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=4) + "\n")
    console.say(f"Wrote new dictionary of bank sync information to {path}", 3)


# ----- checks -----


def check_syncfile_and_syncrepo(syncfile: Path) -> None:
    if not syncfile.is_file():
        raise BanksyncError(f"failure! could not locate the sync file at {syncfile}.")
    check_syncrepo_dir(syncfile.parent)


def check_syncrepo_dir(syncrepo: Path, existing: bool = True) -> None:
    if not syncrepo.is_dir():
        raise BanksyncError(f"failure! could not locate the syncrepo dir at {syncrepo}.")
    if not git.is_working_tree_root(syncrepo):
        if existing:
            raise BanksyncError(f"failure! {syncrepo} is not a git repository consisting of syncfile revisions.")
        raise BanksyncError(f"failure! {syncrepo} is not a git repository.")


def check_repo(label: str, repo: Path) -> bool:
    """Report and return False if `repo` is missing or is not a git repository."""
    if not repo.is_dir():
        console.failure(f"{label} : there is no repository at {repo}.")
        return False
    if not git.is_working_tree_root(repo):
        console.failure(f"{label} : {repo} is not a git repository.")
        return False
    return True


# ----- finding the syncfile -----


def is_syncfile(path: Path, current_version: str) -> bool:
    """Whether `path` is a JSON syncfile this version of banksync can use.

    Raises BanksyncError for a syncfile that needs a newer version of banksync."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False

    if not isinstance(data, dict):
        return False

    configuration = data.get("configuration")
    if isinstance(configuration, dict) and "requiredBanksyncVersion" in configuration:
        required = str(configuration["requiredBanksyncVersion"])
        if version_less_or_equal(required, current_version):
            return True
        created = configuration.get("createdByBanksyncVersion", "unknown")
        raise BanksyncError(
            f"Warning: The syncfile {path} was created with banksync version {created} and it needs at least banksync"
            f" version {required} to work with this file, but you are running banksync version {current_version}."
            f" Please upgrade your version of banksync to at least version {required} to use this file."
        )

    # An old style syncfile: a mapping from repo names to repo entries.
    return bool(data) and all(isinstance(value, dict) and "UnixTimeStamp" in value for value in data.values())


def find_syncfile_in(directory: Path, current_version: str) -> Path | None:
    """The first syncfile directly inside `directory`, if `directory` is the root of a git repo."""
    if not git.is_working_tree_root(directory):
        return None
    for candidate in sorted(directory.glob("*.json")):
        if is_syncfile(candidate, current_version):
            return candidate
    return None


def find_syncfile_below(directory: Path, current_version: str) -> Path | None:
    """The first syncfile found in an immediate subdirectory of `directory`."""
    try:
        children = sorted(child for child in directory.iterdir() if child.is_dir())
    except OSError:
        return None
    for child in children:
        found = find_syncfile_in(child, current_version)
        if found:
            return found
    return None


def locate_syncfile(syncfile_arg: str | None, current_version: str) -> Path:
    """Find the syncfile to use: the one given with --syncfile, else one in the current directory, else one in a
    sibling directory of the current directory or of any of its parents."""
    if syncfile_arg:
        path = Path(os.path.abspath(syncfile_arg))
        check_syncfile_and_syncrepo(path)
        return path

    cwd = Path.cwd()
    found = find_syncfile_in(cwd, current_version)
    directory = cwd
    while not found:
        found = find_syncfile_below(directory, current_version)
        if found or directory == directory.parent:
            break
        directory = directory.parent

    if not found:
        raise BanksyncError(f"failure! no syncfile found in or above {cwd}.")
    check_syncfile_and_syncrepo(found)
    return found

