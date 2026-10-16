"""Read-only queries about the state of a git repository."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from .shell import git, git_output
from .util import is_sha1

type RepoInfo = dict[str, str]  # one repository's entry in a syncfile


def is_working_tree_root(path: Path) -> bool:
    """Whether `path` is the top level of a git working tree.

    Linked worktrees and submodules have a `.git` file rather than a `.git` directory, so ask git instead of looking
    for `.git`. A directory nested inside a repository is not a root."""
    if not path.is_dir():
        return False
    toplevel = git_output("rev-parse", "--show-toplevel", cwd=path)
    if not toplevel:
        return False
    try:
        return os.path.samefile(toplevel, path)
    except OSError:
        return False


def head_sha(repo: Path) -> str | None:
    sha = git_output("rev-parse", "--verify", "--quiet", "HEAD", cwd=repo)
    return sha if sha and is_sha1(sha) else None


def branch_name(repo: Path) -> str:
    """The checked out branch, or 'HEAD' when the HEAD is detached."""
    return git_output("rev-parse", "--abbrev-ref", "HEAD", cwd=repo) or ""


def branch_or_sha(repo: Path) -> str | None:
    """The checked out branch, or the commit sha when the HEAD is detached. Used to restore a repo after bisecting."""
    return git_output("symbolic-ref", "--quiet", "--short", "HEAD", cwd=repo) or head_sha(repo)


def branch_sha(repo: Path, branch: str) -> str | None:
    """The commit that a local branch points at, or None if the branch does not exist."""
    sha = git_output("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}", cwd=repo)
    return sha if sha and is_sha1(sha) else None


def revision_number(repo: Path) -> str:
    """The number of first-parent commits up to HEAD, as a rough 'revision number'."""
    count = git_output("rev-list", "--count", "--first-parent", "HEAD", cwd=repo)
    return count if count and count.isdigit() else "(unknown)"


def modified_count(repo: Path) -> int:
    output = git_output("ls-files", "--modified", "--exclude-standard", "--directory", cwd=repo)
    return len(output.splitlines()) if output else 0


def staged_count(repo: Path) -> int:
    output = git_output("diff", "--name-only", "--cached", cwd=repo)
    return len(output.splitlines()) if output else 0


def timestamps_to_shas(repo: Path) -> dict[str, str] | None:
    """Map the author timestamp of every commit reachable from any ref to its sha, or None if git fails.

    When several commits share a timestamp the oldest one listed by `git log --all` wins."""
    output = git_output("log", "--all", "--format=%at %H", cwd=repo)
    if output is None:
        return None
    table: dict[str, str] = {}
    for line in output.splitlines():
        timestamp, _, sha = line.partition(" ")
        table[timestamp] = sha
    return table


# ----- remotes -----


def remote_names(repo: Path) -> list[str]:
    output = git_output("remote", cwd=repo)
    return output.split() if output else []


def default_remote(repo: Path) -> str | None:
    """'origin' if the repo has it, otherwise its first remote."""
    remotes = remote_names(repo)
    if "origin" in remotes:
        return "origin"
    return remotes[0] if remotes else None


def clone_url(repo: Path) -> str | None:
    remote = default_remote(repo)
    return git_output("remote", "get-url", remote, cwd=repo) if remote else None


def _has_ref(repo: Path, ref: str) -> bool:
    return git("show-ref", "--verify", "--quiet", ref, cwd=repo, show=4).ok


def default_pull_branch(repo: Path, remote: str) -> str | None:
    """The branch to pull while detached: the remote's HEAD branch, else main or master, if they exist."""
    remote_head = git_output("symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD", cwd=repo)
    prefix = f"{remote}/"
    if remote_head and remote_head.startswith(prefix):
        branch = remote_head.removeprefix(prefix)
        if _has_ref(repo, f"refs/remotes/{remote}/{branch}"):
            return branch
    for branch in ("main", "master"):
        if _has_ref(repo, f"refs/remotes/{remote}/{branch}"):
            return branch
    for branch in ("main", "master"):
        if _has_ref(repo, f"refs/heads/{branch}"):
            return branch
    return None


def pull_arguments(repo: Path, extra_args: Sequence[str]) -> list[str]:
    """The arguments for `git pull` in this repo.

    A bare `git pull` fails on a detached HEAD because there is no branch configuration to consult, which is common
    after a sync or in a fresh worktree. In that case pull the remote's default branch explicitly."""
    if extra_args or branch_name(repo) != "HEAD":
        return ["pull", *extra_args]
    remote = default_remote(repo)
    branch = default_pull_branch(repo, remote) if remote else None
    if remote and branch:
        return ["pull", remote, branch]
    return ["pull"]


# ----- recording -----


def current_state(repo: Path, path: str) -> RepoInfo | None:
    """Describe the commit checked out in `repo` as a syncfile entry, recording `path` as its location.

    Returns None if the repo has no commits or git fails."""
    fields = git_output("log", "-1", "--date=iso", "--format=%H%x00%at%x00%ad%x00%an%x00%B", "HEAD", cwd=repo)
    if not fields:
        return None
    sha, timestamp, date, author, message = fields.split("\x00", 4)
    info: RepoInfo = {
        "path": path,
        "sha": sha,
        "UnixTimeStamp": timestamp,
        "date": date,
        "author": author,
        "branch": branch_name(repo),
        "revisionNumber": revision_number(repo),
        "message": message.strip(),
    }
    url = clone_url(repo)
    if url:
        info["cloneURL"] = url
    return info
