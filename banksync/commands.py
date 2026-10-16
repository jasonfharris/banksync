"""The implementations of the bank commands. Each returns True on success and False on failure."""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from . import git
from .console import Level, console
from .git import RepoInfo
from .options import Options
from .shell import git as run_git
from .shell import git_output
from .syncfile import (
    SyncFile,
    check_repo,
    check_syncrepo_dir,
    find_syncfile_below,
    find_syncfile_in,
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


def branch_info(branch: str) -> str:
    if branch == "HEAD":
        return f"({console.dim('detached HEAD')})"
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
    """Record the commit each repository has checked out in the syncfile. Keys that banksync does not write itself
    (notes and the like) are kept."""
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
        if not state:
            console.say(console.red(f"{label}: failure! not able to get the status of {name} at {repo}"))
            any_failures = True
            continue
        console.say(f"{console.green(label)}: recording bank sync state of {state['sha'][:12]}, {state['date']}.")
        recorded[name] = {**info, **state}

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
    """Write a new syncfile recording the commit each of the given repositories has checked out.

    The syncfile is only written if the state of every repository could be recorded."""
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

        if name in locations:
            raise BanksyncError(
                f"failure! {locations[name][0]} and {repo} are both named {name}; the repos in a bank need distinct names."
            )
        locations[name] = (repo, os.path.isabs(arg))
        state = git.current_state(repo, arg)
        if not state:
            console.say(console.red(f"failure! not able to get the status of {name} at {repo}"))
            any_failures = True
            continue
        console.say(f"{console.green(padded(name, names))}: recording repository state of {state['sha'][:12]}, {state['date']}.")
        infos[name] = state

    if any_failures or not infos:
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
    console.success(f"success! all repos had their state recorded to {where}.")
    return True


def create_syncrepo(repo_args: Sequence[str], opts: Options) -> bool:
    """Create the syncrepo directory, initialize a git repository there, and create the syncfile inside it."""
    syncrepo = Path(os.path.abspath(opts.syncreponame))
    syncfilename = opts.syncfilename
    if not os.path.dirname(syncfilename):
        syncfile_path = syncrepo / syncfilename
    elif Path(os.path.abspath(syncfilename)).parent == syncrepo:
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
    if create_syncfile(syncfile_path, repo_args, opts):
        return True
    shutil.rmtree(syncrepo)  # remove the empty syncrepo again, so the command can simply be rerun
    return False


# --------------------------------------------------------------------------------------------------------------------
# bisect
# --------------------------------------------------------------------------------------------------------------------

BISECT_RESTORE_NAME = "banksync-bisect-restore.json"
LEGACY_BISECT_RESTORE_FILE = ".bisectRestore"  # where banksync 0.9.10 kept it, in the syncrepo's working tree


def _bisect_restore_paths(syncrepo: Path) -> list[Path]:
    """Where the revisions to restore after bisecting are kept: inside the syncrepo's git directory, so that the file
    does not show up as an untracked file, followed by the location older versions of banksync used."""
    git_path = git_output("rev-parse", "--git-path", BISECT_RESTORE_NAME, cwd=syncrepo)
    current = syncrepo / git_path if git_path else syncrepo / ".git" / BISECT_RESTORE_NAME
    return [current, syncrepo / LEGACY_BISECT_RESTORE_FILE]


def _record_revisions_before_bisect(syncfile: SyncFile) -> bool:
    repos = syncfile.repositories
    restore: dict[str, str] = {}
    ok = True
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        revision = git.branch_or_sha(repo) if check_repo(label, repo) else None
        if not revision:
            ok = False
            console.say(f"{console.red(label)}: error recording the original branch in {repo}")
            continue
        restore[str(repo)] = revision
        console.say(f"{console.green(label)}: recording repository state of '{revision}' before starting bisect")
    _bisect_restore_paths(syncfile.syncrepo)[0].write_text(json.dumps(restore, indent=4) + "\n")
    if not ok:
        console.failure("failure! not all repo states recorded before bisect.")
    return ok


def _restore_revisions_after_bisect(syncfile: SyncFile) -> bool:
    paths = [path for path in _bisect_restore_paths(syncfile.syncrepo) if path.is_file()]
    if not paths:
        console.say(console.yellow("We are not in a bisection or bisection record not found."), Level.SUMMARY)
        return True
    restore: dict[str, str] = json.loads(paths[0].read_text()) or {}

    repos = syncfile.repositories
    ok = True
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        revision = restore.get(str(repo))
        if not revision or not check_repo(label, repo):
            ok = False
            console.say(f"{console.red(label)}: error restoring the original branch in {repo}: no recorded state")
        elif _checkout(repo, revision, []):
            console.say(f"{console.green(label)}: restoring repository state to '{revision}' after finishing bisect")
        else:
            ok = False
            console.say(f"{console.red(label)}: failed to restore repository state to '{revision}' after finishing bisect")
    for path in paths:
        path.unlink()
    if not ok:
        console.failure("failure! not all repo states restored after bisect.")
    return ok


def _bisect_run_arguments(syncfile: SyncFile, extra_args: Sequence[str], opts: Options) -> list[str]:
    """`git bisect run` arguments that sync the bank before running the user's command at each step.

    git runs the script in the syncrepo after checking out each step. The script syncs the bank to the syncfile it
    checked out, exiting with 125 (which tells git to skip the step) if that fails, and then runs the command."""
    command = list(extra_args[1:] if extra_args[:1] == ["--"] else extra_args)
    if not command:
        raise BanksyncError("failure! `bank bisect run` needs a command to run, e.g. `bank bisect run make test`.")
    script = '"$0" -m banksync sync --syncfile "$1" --verbosity "$2" --colorize "$3" || exit 125; shift 3; exec "$@"'
    colorize = "yes" if opts.colorize else "no"
    step_verbosity = str(min(opts.verbosity, Level.SUMMARY))
    return ["bisect", "run", "sh", "-c", script, sys.executable, str(syncfile.path), step_verbosity, colorize, *command]


def bisect(syncfile: SyncFile, subcommand: str, extra_args: Sequence[str], opts: Options) -> bool:
    """Run `git bisect <subcommand>` in the syncrepo, and sync the bank whenever that checks out another syncfile.

    `start` records the branch or commit of each repo, and `reset` restores them."""
    syncrepo = syncfile.syncrepo
    if opts.dryrun:
        console.say(f"would run `git bisect {subcommand}` in {relative_to_cwd(syncrepo)} and sync the bank to the syncfile it checks out.")
        return True

    ok = _record_revisions_before_bisect(syncfile) if subcommand == "start" else True

    before = git.head_sha(syncrepo)
    if subcommand == "run":
        arguments = _bisect_run_arguments(syncfile, extra_args, opts)
    else:
        arguments = ["bisect", subcommand, *extra_args]
    ok = run_git(*arguments, cwd=syncrepo, show=Level.REPO, stream=True).ok and ok

    if git.head_sha(syncrepo) != before:
        ok = sync(SyncFile.load(syncfile.path), opts) and ok  # the bisect step checked out a different syncfile

    if subcommand == "reset":
        ok = _restore_revisions_after_bisect(syncfile) and ok
    return ok


# --------------------------------------------------------------------------------------------------------------------
# clone and populate
# --------------------------------------------------------------------------------------------------------------------

DEFAULT_SYNCREPO_NAME = "syncrepo"


def _clone_syncreponame(syncfile_path: Path) -> str:
    """The directory name the syncfile asks the syncrepo to be cloned into (`clone.syncreponame`), if it is a safe
    relative path inside the project, else 'syncrepo'."""
    try:
        name = json.loads(syncfile_path.read_text()).get("configuration", {}).get("clone.syncreponame")
    except (OSError, ValueError, AttributeError):
        name = None
    if not isinstance(name, str) or not name or os.path.isabs(name) or ".." in Path(name).parts or name == ".":
        return DEFAULT_SYNCREPO_NAME
    return name


def clone(url: str, name: str | None, opts: Options) -> bool:
    """Clone a syncrepo into <name>/<clone.syncreponame> and then populate the bank around it."""
    if not is_valid_git_url(url):
        raise BanksyncError(f"failure! {url} appears not to be a URL that works with git clone.")
    destination = Path(os.path.abspath(name or repo_name_from_url(url)))
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise BanksyncError(f"failure! {destination} already exists and is not an empty directory.")

    if opts.dryrun:
        console.say(f"would clone {url} to {destination} and then populate the repositories given in its syncfile.")
        return True

    destination.mkdir(parents=True, exist_ok=True)
    console.progress(f">> cloning {url}...")
    result = run_git("clone", url, destination.name, cwd=destination.parent, stream=True)
    if not result.ok:
        console.say(f"{console.red(url)}: error cloning repo to {destination}:\n    {result.stderr.strip()}")
        return False
    console.say(f"{console.green(url)}: cloned repo to {destination}")

    # The URL is normally that of the syncrepo itself, so move it down into the project directory. (Otherwise the URL
    # is that of a project which contains the syncrepo.)
    cloned_syncfile = find_syncfile_in(destination, __version__)
    if cloned_syncfile:
        syncrepo = destination / _clone_syncreponame(cloned_syncfile)
        move_directory(destination, syncrepo)
        syncfile_path: Path | None = syncrepo / cloned_syncfile.name
    else:
        syncfile_path = find_syncfile_below(destination, __version__)

    if not syncfile_path:
        console.failure(f"failure! no syncfile found in {destination} or the directories inside it.")
        return False
    return populate(SyncFile.load(syncfile_path), opts)


def populate(syncfile: SyncFile, opts: Options) -> bool:
    """Clone each repository in the syncfile that is not present yet, then sync the bank."""
    repos = syncfile.repositories
    any_failures = False
    for name, info in repos.items():
        label = padded(name, repos)
        repo = syncfile.repo_path(info)
        if git.is_working_tree_root(repo):
            console.say(f"{console.green(label)}: already present at {repo}")
            continue
        if repo.exists() and (not repo.is_dir() or any(repo.iterdir())):
            any_failures = True
            console.say(f"{console.red(label)}: {repo} already exists but is not a git repository")
            continue
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
    "status", "log", "show", "diff", "branch", "tag", "checkout", "switch", "restore", "reset", "commit", "stash",
    "fetch", "pull", "push", "remote", "describe", "rev-parse", "grep", "prune", "gc", "fsck", "ls-files",
    "ls-remote", "ls-tree",
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
