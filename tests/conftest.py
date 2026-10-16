"""Shared fixtures for the banksync test suite.

Every test runs in its own temporary directory with an isolated HOME and git configuration, and drives the real
command line through `python -m banksync`, so tests neither touch the checkout nor depend on the network.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# A fixed base time for commits, so timestamp matching does not depend on sleeping between commits.
BASE_TIMESTAMP = 1_700_000_000


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("BANKSYNC_NETWORK_TESTS") == "1":
        return
    skip_network = pytest.mark.skip(reason="needs github.com; set BANKSYNC_NETWORK_TESTS=1 to run")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    home = tmp_path_factory.mktemp("home")
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(
        "[user]\n"
        "\tname = Banksync Test\n"
        "\temail = banksync@example.invalid\n"
        "[init]\n"
        "\tdefaultBranch = master\n"
        "[advice]\n"
        "\tdetachedHead = false\n"
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)
    # Run the code in this checkout even if a different banksync is installed.
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(PACKAGE_ROOT), os.environ.get("PYTHONPATH")])))
    yield


class Workspace:
    """A scratch directory with helpers to build git repos and run `bank` commands in it."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, relative: str | Path) -> Path:
        return self.root / relative

    # ----- bank -----

    def bank(self, *args: str, cwd: str | Path = ".", ok: bool = True) -> str:
        """Run `bank <args>` and return its combined stdout and stderr, without ANSI color codes.

        With ok=True the command must succeed; with ok=False it must fail."""
        result = subprocess.run(
            [sys.executable, "-m", "banksync", *args],
            cwd=self.root / cwd,
            capture_output=True,
            text=True,
        )
        output = ANSI_ESCAPE.sub("", result.stdout + result.stderr)
        if ok and result.returncode != 0:
            raise AssertionError(f"bank {' '.join(args)} failed with exit code {result.returncode}:\n{output}")
        if not ok and result.returncode == 0:
            raise AssertionError(f"bank {' '.join(args)} unexpectedly succeeded:\n{output}")
        return output

    # ----- git -----

    def git(self, repo: str | Path, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root / repo,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} in {repo} failed:\n{result.stdout}{result.stderr}")
        return result.stdout.strip()

    def head(self, repo: str | Path) -> str:
        return self.git(repo, "rev-parse", "HEAD")

    def branch(self, repo: str | Path) -> str:
        return self.git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    def init_repo(self, repo: str | Path) -> Path:
        path = self.path(repo)
        path.mkdir(parents=True, exist_ok=True)
        self.git(repo, "init", "--quiet")
        return path

    def commit(self, repo: str | Path, filename: str, line: str, timestamp: int) -> str:
        """Append a line to a file and commit it with the given author and committer time. Return the new sha."""
        with open(self.path(repo) / filename, "a") as f:
            f.write(line + "\n")
        self.git(repo, "add", filename)
        date = f"@{timestamp} +0000"
        self.git(repo, "commit", "--quiet", "-m", f"committing {line}", env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})
        return self.head(repo)

    def make_bare_remote(self, repo: str | Path, remote_name: str) -> Path:
        """Create a bare clone of a repo under remotes/ and register it as that repo's origin."""
        remote = self.path("remotes") / remote_name
        remote.parent.mkdir(exist_ok=True)
        self.git(".", "clone", "--quiet", "--bare", str(self.path(repo)), str(remote))
        self.git(repo, "remote", "add", "origin", str(remote))
        return remote

    # ----- syncfiles -----

    def read_json(self, relative: str | Path) -> Any:
        return json.loads(self.path(relative).read_text())

    def write_json(self, relative: str | Path, data: Any) -> None:
        self.path(relative).write_text(json.dumps(data, indent=4))


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)
