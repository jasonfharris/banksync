"""The implementations of the bank commands. Each returns True on success and False on failure."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from . import git
from .console import Level, console
from .git import RepoInfo
from .options import Options
from .shell import git as run_git
from .syncfile import (
    SyncFile,
    check_repo,
    check_syncrepo_dir,
    find_syncfile_named_like,
    write_syncfile,
)
from .util import (
    BanksyncError,
    date_from_timestamp,
    is_valid_git_url,
    move_directory,
    padded,
    relative_to_cwd,
    repo_name_from_url,
)
from .version import REQUIRED_BANKSYNC_VERSION, SYNCFILE_FORMAT_VERSION, __version__

DEFAULT_SYNC_POINT_BRANCH = "syncPoint"  # the branch used by --syncBranches when the syncfile records no branch
BISECT_RESTORE_FILE = ".bisectRestore"


def branch_info(branch: str) -> str:
    return f"({console.dim('branch')}: {console.blue(branch)})"


# --------------------------------------------------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------------------------------------------------


def _branch_arguments(info: RepoInfo, repo: Path, sha: str, opts: Options) -> tuple[list[str], str]:
    """The extra `git checkout` arguments that put the recorded branch at `sha`, and a description of the branch.

    The branch is checked out if it already points at `sha`. With --syncBranches yes it is also created if it does not
    exist, and with --syncBranches force it is created or moved to `sha` regardless."""
    branch = info.get("branch", DEFAULT_SYNC_POINT_BRANCH)
    target = git.branch_sha(repo, branch)
    if opts.sync_branches == "force" or (opts.sync_branches == "yes" and not target):
        target = sha
    if branch == "HEAD":  # the repo was recorded with a detached HEAD
        target = None
    arguments = ["-B", branch] if target == sha else []
    return arguments, f" {branch_info(branch)}"


def _checkout(repo: Path, sha: str, branch_arguments: list[str]) -> bool:
    result = run_git("checkout", *branch_arguments, sha, cwd=repo)
    if not result.ok and result.stderr.strip() and not console.shows(Level.COMMAND):
        console.say(console.red("    " + result.stderr.strip().replace("\n", "\n    ")), Level.REPO)
    return result.ok


def _checkout_by_sha(info: RepoInfo, repo: Path, label: str, opts: Options) -> bool:
    sha = info["sha"]
    short = sha[:12]
    if opts.dryrun:
        console.say(f"{label}: would try and check out revision by sha: {short}")
        return True

    branch_arguments, branch_message = _branch_arguments(info, repo, sha, opts)
    console.progress(f">> checking out {sha}{branch_message}...")
    if _checkout(repo, sha, branch_arguments):
        revision = git.revision_number(repo)
        current = branch_info(git.branch_name(repo))
        console.say(f"{console.green(label)}: successfully checked out revision by sha: {short} {current} (revision number {revision})")
        return True
    console.say(f"{label}: failed to check out revision by sha: {sha}{branch_message}", Level.COMMAND)
    return False


def _checkout_by_timestamp(info: RepoInfo, repo: Path, label: str, opts: Options) -> bool:
    if opts.matching not in ("timestamp", "closetimestamp"):
        return False

    timestamp = info["UnixTimeStamp"]
    date = date_from_timestamp(timestamp)
    if opts.dryrun:
        console.say(f"{label}: would try and check out revision by UnixTimeStamp: {timestamp} ({date})")
        return True

    def failed() -> bool:
        console.say(f"{label}: failed to check out revision by UnixTimeStamp: {timestamp} ({date})", Level.COMMAND)
        return False

    shas = git.timestamps_to_shas(repo)
    if not shas:
        return failed()

    if timestamp in shas:
        sha = shas[timestamp]
        branch_arguments, branch_message = _branch_arguments(info, repo, sha, opts)
        console.progress(f">> checking out {timestamp} ({date}){branch_message}...")
        if not _checkout(repo, sha, branch_arguments):
            return failed()
        revision = git.revision_number(repo)
        console.say(f"{console.green(label)}: successfully checked out revision by UnixTimeStamp: {timestamp} ({date}) {sha} (revision number {revision})")
        return True

    if opts.matching == "closetimestamp":
        closest = min(shas, key=lambda candidate: abs(int(candidate) - int(timestamp)))
        sha = shas[closest]
        branch_arguments, branch_message = _branch_arguments(info, repo, sha, opts)
        console.progress(f">> checking out close {timestamp} ({date}){branch_message}...")
        if _checkout(repo, sha, branch_arguments):
            revision = git.revision_number(repo)
            current = branch_info(git.branch_name(repo))
            console.say(f"{console.yellow(label)}: {console.red('warning checking out revision by closest timestamp.')}")
            console.say(f"       requested UnixTimeStamp: {timestamp} ({date}){branch_message}")
            console.say(f"       used      UnixTimeStamp: {closest} ({date_from_timestamp(closest)}) {sha} {current} (revision number {revision})")
            return True
    return failed()


def sync(syncfile: SyncFile, opts: Options) -> bool:
    repos = syncfile.repositories
    all_found = True
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        if not check_repo(label, repo):
            all_found = False
            continue

        found = "sha" in info and _checkout_by_sha(info, repo, label, opts)
        if not found and "UnixTimeStamp" in info:
            found = _checkout_by_timestamp(info, repo, label, opts)
        if not found and not opts.dryrun:
            all_found = False
            console.say(f"{console.red(label)}: failed to check out specified revision by any method.")

    where = relative_to_cwd(syncfile.path)
    if opts.dryrun:
        return True
    if all_found:
        console.success(f"success! all repos checked out to the state given in {where}.")
        return True
    console.failure(f"failure! not all repos checked out to the state given in {where}.")
    return False


# --------------------------------------------------------------------------------------------------------------------
# record_repos
# --------------------------------------------------------------------------------------------------------------------


def record_repos(syncfile: SyncFile, opts: Options) -> bool:
    repos = syncfile.repositories
    recorded = dict(repos)
    any_failures = False
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        if not check_repo(label, repo):
            any_failures = True
            continue

        state = git.current_state(repo, info["path"])
        if state:
            console.say(f"{console.green(label)}: recording bank sync state of {state['sha'][:12]}, {state['date']}.")
        else:
            console.say(console.red(f"{label}: failure! not able to get the status of {name} at {repo}"))
            any_failures = True
        recorded[name] = state or {"path": info["path"]}

    if opts.dryrun:
        return True

    syncfile.repositories = recorded
    syncfile.write()

    where = relative_to_cwd(syncfile.path)
    if any_failures:
        console.failure(f"failure! not all constituent repos had their state recorded to {where}.")
        return False
    console.success(f"success! all constituent repos had their state recorded to {where}.")
    return True


# --------------------------------------------------------------------------------------------------------------------
# create_syncfile and create_syncrepo
# --------------------------------------------------------------------------------------------------------------------


def create_syncfile(syncfile_path: Path, repo_args: Sequence[str], opts: Options) -> bool:
    syncrepo = syncfile_path.parent
    check_syncrepo_dir(syncrepo, existing=False)
    where = relative_to_cwd(syncfile_path)

    infos: dict[str, RepoInfo] = {}
    locations: dict[str, tuple[Path, bool]] = {}  # repo name -> (absolute path, whether it was given as absolute)
    names = [Path(os.path.abspath(arg)).name for arg in repo_args]
    any_failures = False
    for arg in repo_args:
        repo = Path(os.path.abspath(arg))
        name = repo.name
        if not check_repo(name, repo):
            any_failures = True
            continue

        locations[name] = (repo, os.path.isabs(arg))
        state = git.current_state(repo, arg)
        if state:
            console.say(f"{console.green(padded(name, names))}: recording repository state of {state['sha'][:12]}, {state['date']}.")
        else:
            console.say(console.red(f"failure! not able to get the status of {name} at {repo}"))
            any_failures = True
        infos[name] = state or {"path": arg}

    if not infos:
        console.failure(f"failure! syncfile {where} not created.")
        return False

    # The repositories are located relative to the deepest directory containing all the relatively given repos.
    relative_repos = [path for path, was_absolute in locations.values() if not was_absolute]
    if relative_repos:
        root = Path(os.path.commonpath([path.parent for path in relative_repos]))
        offset = os.path.relpath(root, syncrepo)
    else:
        root = Path.cwd()
        offset = "."

    for name, info in infos.items():
        path, was_absolute = locations[name]
        if not was_absolute:
            info["path"] = os.path.relpath(path, root)

    data = {
        "configuration": {
            "createdByBanksyncVersion": __version__,
            "requiredBanksyncVersion": REQUIRED_BANKSYNC_VERSION,
            "syncfileFormatVersion": SYNCFILE_FORMAT_VERSION,
            "relativePathToRepositories": offset,  # from the syncrepo to the directory the repo paths are relative to
            "clone.syncreponame": os.path.relpath(syncrepo, root),  # where `bank clone` puts the syncrepo
        },
        "repositories": infos,
    }

    if opts.dryrun:
        console.say(f"{console.green('Dry run')}: Would create {where} with contents:\n{json.dumps(data, indent=4)}", Level.SUMMARY)
        return True

    write_syncfile(syncfile_path, data)
    if any_failures:
        console.failure(f"failure! not all repos had their state recorded to {where}.")
        return False
    console.success(f"success! all repos had their state recorded to {where}.")
    return True


def create_syncrepo(repo_args: Sequence[str], opts: Options) -> bool:
    syncrepo = Path(os.path.abspath(opts.syncreponame))
    syncfilename = opts.syncfilename
    if not os.path.dirname(syncfilename):
        syncfile_path = syncrepo / syncfilename
    elif Path(os.path.abspath(syncfilename)) == syncrepo:
        syncfile_path = Path(os.path.abspath(syncfilename))
    else:
        raise BanksyncError(f"failure! sync file name: {syncfilename} does not live directly inside {opts.syncreponame}.")

    if syncrepo.is_dir():
        raise BanksyncError(f"failure! The directory {syncrepo} already exists.")

    if opts.dryrun:
        console.say(
            f"The directory {syncrepo} would be created and a git repository would be initialized there."
            f" The file {syncfile_path} would be created and filled.",
            Level.SUMMARY,
        )
        return True

    syncrepo.mkdir(parents=True)
    run_git("init", "--quiet", cwd=syncrepo, check=True)
    return create_syncfile(syncfile_path, repo_args, opts)


# --------------------------------------------------------------------------------------------------------------------
# bisect
# --------------------------------------------------------------------------------------------------------------------


def _write_bisect_restore(syncrepo: Path, restore: dict[str, str]) -> None:
    (syncrepo / BISECT_RESTORE_FILE).write_text(json.dumps(restore, indent=4))


def _read_bisect_restore(syncrepo: Path) -> dict[str, str] | None:
    path = syncrepo / BISECT_RESTORE_FILE
    if not path.exists():
        return None
    restore: dict[str, str] = json.loads(path.read_text()) or {}
    return restore


def bisect(syncfile: SyncFile, subcommand: str, extra_args: Sequence[str], opts: Options) -> bool:
    syncrepo = syncfile.syncrepo
    repos = syncfile.repositories
    before = git.head_sha(syncrepo)
    any_failures = False

    if opts.dryrun:
        console.say("would try exectue the given bisect command on the current sync repo and sync the bank repos to the new state.")
        return True

    if subcommand == "start":
        restore: dict[str, str] = {}
        for name, info in repos.items():
            label = padded(name, repos)
            repo = syncfile.repo_path(info)
            revision = git.branch_or_sha(repo)
            if not revision:
                any_failures = True
                console.say(f"{console.red(label)}: error recoding original branch in {repo}")
                continue
            restore[str(repo)] = revision
            console.say(f"{console.green(label)}: recording repository state of '{revision}' before starting bisect")
        _write_bisect_restore(syncrepo, restore)
        if any_failures:
            console.failure("failure! not all repo states recorded before bisect.")

    run_git("bisect", subcommand, *extra_args, cwd=syncrepo, show=Level.REPO)
    if git.head_sha(syncrepo) != before:
        sync(SyncFile.load(syncfile.path), opts)  # the bisect step checked out a different version of the syncfile

    if subcommand == "reset":
        restore_or_none = _read_bisect_restore(syncrepo)
        if not restore_or_none:
            console.say(console.yellow("We are not in a bisection or bisection record not found."), Level.SUMMARY)
            return True
        for name, info in repos.items():
            label = padded(name, repos)
            repo = syncfile.repo_path(info)
            revision = restore_or_none.get(str(repo))
            if not revision:
                any_failures = True
                console.say(f"{console.red(label)}: error restoring original branch in {repo}")
                continue
            run_git("checkout", revision, cwd=repo)
            console.say(f"{console.green(label)}: restoring repository state to '{revision}' after finishing bisect")
        if any_failures:
            console.failure("failure! not all repo states restored after bisect.")
        (syncrepo / BISECT_RESTORE_FILE).unlink()

    return True


# --------------------------------------------------------------------------------------------------------------------
# clone and populate
# --------------------------------------------------------------------------------------------------------------------


def clone(url: str, name: str | None, opts: Options) -> bool:
    if not is_valid_git_url(url):
        raise BanksyncError(f"failure! {url} appears not to be a URL that works with git clone.")
    destination = Path(os.path.abspath(name or repo_name_from_url(url)))

    destination.mkdir(parents=True, exist_ok=True)
    console.progress(f">> cloning {url}...")
    result = run_git("clone", url, destination.name, cwd=destination.parent, stream=True)
    if not result.ok:
        console.say(f"{console.red(url)}: error cloning repo to {destination}:\n    {result.stderr}")
        return False
    console.say(f"{console.green(url)}: cloned repo to {destination}")

    syncrepo = destination / "syncrepo"

    # The URL is normally that of the syncrepo, so move it down into project/syncrepo.
    if find_syncfile_named_like(destination):
        move_directory(destination, syncrepo)

    syncfile_path = find_syncfile_named_like(syncrepo)
    if not syncfile_path:
        console.say(f"{console.red('failure!')}: no syncfile found at {destination} or {syncrepo}")
        return False

    return populate(SyncFile.load(syncfile_path), opts)


def populate(syncfile: SyncFile, opts: Options) -> bool:
    repos = syncfile.repositories
    any_failures = False
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        url = info.get("cloneURL")
        if not url:
            any_failures = True
            console.say(console.red(f"{label}: there is no cloneURL for this repo"))
            continue
        if opts.dryrun:
            console.say(f"{label}: would clone {url} to {repo}.")
            continue

        repo.parent.mkdir(parents=True, exist_ok=True)
        console.progress(f">> cloning {repo.name}...")
        if run_git("clone", url, repo.name, cwd=repo.parent, stream=True).ok:
            console.say(f"{console.green(label)}: cloned repo to {repo}")
        else:
            any_failures = True
            console.say(f"{console.red(label)}: error cloning repo to {repo}")

    where = relative_to_cwd(syncfile.path)
    if opts.dryrun:
        return True
    if any_failures:
        console.failure(f"failure! not all repos from {where} were populated.")
        return False

    console.success(f"success! all repos from {where} were populated.")
    return sync(syncfile, opts)


# --------------------------------------------------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------------------------------------------------


def status(syncfile: SyncFile, opts: Options) -> bool:
    repos = syncfile.repositories
    any_failures = False
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        if opts.dryrun:
            console.say(f"{label} : would give the status of the repo at {repo}.")
            continue
        if not check_repo(label, repo):
            any_failures = True
            continue

        description = f"{console.dim('branch')}: {console.blue(git.branch_name(repo))}"
        modified = git.modified_count(repo)
        staged = git.staged_count(repo)
        if modified:
            description += f", {console.dim('modified')}: {modified}"
        if staged:
            description += f", {console.dim('staged')}: {staged}"
        console.say(f"{console.green(label)} : {description}", Level.SUMMARY)

    if opts.dryrun:
        return True
    if any_failures:
        console.failure("failure! not all repos reported the status correctly.")
        return False
    console.success("success! all repos status reported.")
    return True


# --------------------------------------------------------------------------------------------------------------------
# git and gitall
# --------------------------------------------------------------------------------------------------------------------

# Git commands that make sense run non-interactively in every repo of a bank. Other commands are allowed but warned
# about. The command line completes these.
APPROVED_GIT_COMMANDS = [
    "reset", "log", "status", "branch", "checkout", "commit", "tag", "diff", "fetch",
    "push", "pull", "prune", "gc", "fsck", "ls-files", "ls-remote", "ls-tree",
]  # fmt: skip


def git_in_each_repo(syncfile: SyncFile, command: str, extra_args: Sequence[str], include_syncrepo: bool, opts: Options) -> bool:
    if command not in APPROVED_GIT_COMMANDS:
        console.say(
            f"{console.yellow('warning')}: the git command `{command}` might not make sense being applied"
            " non-interactively to each repo in the bank. Use at your own discretion.",
            Level.SUMMARY,
        )

    separator = (opts.separator * 40)[:40]
    repos = syncfile.repositories
    directories: list[Path] = []
    any_failures = False
    for name, info in repos.items():
        repo = syncfile.repo_path(info)
        if check_repo(name, repo):
            directories.append(repo)
        else:
            any_failures = True
    if include_syncrepo:
        directories.append(syncfile.syncrepo)

    console.say(separator)
    for directory in directories:
        arguments = git.pull_arguments(directory, extra_args) if command == "pull" else [command, *extra_args]
        run_git(*arguments, cwd=directory, show=Level.REPO, stream=True, dryrun=opts.dryrun)
        console.say(separator)

    where = relative_to_cwd(syncfile.path)
    description = " ".join(["git", command, *extra_args])
    if any_failures:
        console.failure(f"failure! not all repos in {where} present.")
        return False
    console.success(f"all repos in {where} issued git command '{description}'")
    return True
