#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""The `bank` command line: argument parsing, option resolution, and dispatch to the commands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import argcomplete

from . import commands
from .console import console
from .options import COLORIZE_VALUES, MATCHING_VALUES, SYNC_BRANCHES_VALUES, VERBOSITY_VALUES, Options, syncfile_layer, user_rc_layer
from .shell import CommandFailed
from .syncfile import SyncFile, locate_syncfile
from .util import BanksyncError, wrap_paragraphs
from .version import __version__

BISECT_SUBCOMMANDS = ["start", "bad", "new", "good", "old", "terms", "skip", "reset", "visualize", "replay", "log", "run"]



# --------------------------------------------------------------------------------------------------------------------
# Help texts
# --------------------------------------------------------------------------------------------------------------------

MAIN_DESCRIPTION = "synchronize, record, bisect and run git commands across a bank (collection) of git repositories."
MAIN_EPILOG = wrap_paragraphs(
    """bank checks out or records a synchronized state across a collection (a bank) of repositories, or performs a git
command in each of the repositories in the bank. The repositories and their states are given in a "syncfile", a JSON
file that lives inside a normal git repo called the "syncrepo", so that each commit of the syncrepo records a
configuration of the whole bank.

bank is a looser alternative to git submodules: when a recorded commit no longer exists, for example after a rebase,
the repository can be matched by the commit's timestamp instead.

Commands that use a syncfile find it with --syncfile, or else look in the current directory, and then in the
subdirectories of the current directory and of each of its parent directories.

Options can also be set in ~/.bankconfigrc (an INI file with [general] and [sync] sections) or in the
"configuration" section of the syncfile (keys such as "sync.matching"). The command line wins over the syncfile,
which wins over ~/.bankconfigrc. Run `bank <command> --help` for the options of a command."""
)

COMMAND_HELP: dict[str, str] = {
    "sync": "check out the revisions given in the syncfile in each repo of the bank",
    "record_repos": "record the revisions currently checked out in the repos of the bank in the syncfile",
    "create_syncfile": "create or overwrite a syncfile recording the current revisions of the given repos",
    "create_syncrepo": "create a syncrepo and a syncfile in it recording the current revisions of the given repos",
    "clone": "clone a syncrepo and then populate the bank it describes",
    "populate": "clone the repos given in the syncfile that are not present yet, then sync",
    "status": "report the branch and the modified and staged file counts of each repo in the bank",
    "bisect": "git bisect the syncrepo, syncing the bank to the syncfile at each step",
    "git": "perform a git command in each repo of the bank",
    "gitall": "perform a git command in each repo of the bank and in the syncrepo",
}

COMMAND_EPILOG: dict[str, str] = {
    "sync": """For each repo, sync checks out the recorded sha, or if that fails (depending on --matching) the commit with the
recorded timestamp, or the commit with the closest timestamp.

  bank sync

Sync the bank to the syncfile that bank finds from the current directory.

  bank sync --syncfile some/dir/syncfile.json

Sync the bank described by some/dir/syncfile.json.

  bank sync --matching shaOnly

Only accept the exact recorded commits.

  bank sync --syncBranches yes

Also create each recorded branch at the recorded commit if the branch does not exist yet. (By default the recorded
branch is checked out if it already points at the recorded commit, and otherwise the commit is checked out with a
detached HEAD.)

  bank sync --syncBranches force

Create or move each recorded branch to the recorded commit, even if it points at a different commit. Be aware that
this can leave commits on those branches unreferenced.
""",
    "record_repos": """Example usage:

  bank record_repos

Update the syncfile so that it records the commits currently checked out in the repos of the bank, then commit the
syncfile in the syncrepo to record this configuration. Keys that bank does not write itself are kept.
""",
    "create_syncfile": """Example usage:

  bank create_syncfile --syncfile syncrepo/syncfile.json repo1 repo2 ... repoN

Create or overwrite syncrepo/syncfile.json to record the current states of repo1 repo2 ... repoN. The directory
holding the syncfile must already be the top of a git repo (use create_syncrepo to create both). The repos may be
given as relative or absolute paths, e.g.

  bank create_syncfile --syncfile syncfile.json path1/to/repo1 path2/to/repo2 /abs/path/to/repoN

No syncfile is written if the state of any repo cannot be recorded.
""",
    "create_syncrepo": """Example usage:

  bank create_syncrepo repo1 repo2 ... repoN

Create the directory syncrepo, initialize a git repository there, and create syncrepo/syncfile.json recording the
current states of repo1 repo2 ... repoN, given as names or paths.

  bank create_syncrepo --syncreponame some/path/controlrepo repo1 repo2 ... repoN

Create the syncrepo at some/path/controlrepo instead.

  bank create_syncrepo --syncreponame some/path/controlrepo --syncfilename devCollection.json repo1 repo2

Name the syncfile devCollection.json. (--syncfilename some/path/controlrepo/devCollection.json is equivalent.)

The syncrepo directory must not exist yet. The syncfile is not committed.
""",
    "clone": """Example usage:

  bank clone https://github.com/myProject/myProjectSyncRepo.git myProject

Create the directory myProject, clone the syncrepo into myProject/syncrepo (or the directory named by the
syncfile's clone.syncreponame), and populate the bank: clone each repo given in the syncfile and sync it. Without
a name the directory is named after the URL, here myProject.
""",
    "populate": """Example usage:

  bank populate

Clone each repo in the syncfile that is not present yet from its cloneURL, and then sync the bank. Repos that are
already present are left as they are, so populate can be rerun.
""",
    "status": """Example usage:

  bank status

Report the branch of each repo in the bank and how many files are modified or staged.
""",
    "bisect": f"""BISECTCMD is one of {BISECT_SUBCOMMANDS}; other arguments are passed on to git bisect.
Whenever a step checks out a different version of the syncfile the bank is synced to it. `start` records the branch
of each repo and `reset` restores it. Example usage:

  bank bisect start
  bank bisect good 12e4f5
  bank bisect bad master
  <build and test, then mark the step with bank bisect good / bank bisect bad>
  bank bisect reset

  bank bisect run sh -c 'cd .. && make test'

Sync the bank and then run the command in the syncrepo at each step. The command's exit status marks the step good
(0), bad (1-127 except 125) or skipped (125), as for git bisect run. Steps that cannot be synced are skipped.
""",
    "git": f"""Example usage:

  bank git status
  bank git tag release_1.7.0.1
  bank git log --oneline -3 -- src/

Any git command can be used. Commands other than {", ".join(commands.APPROVED_GIT_COMMANDS)} produce a warning, since
some (such as rebase --interactive) make no sense run non-interactively in every repo. Arguments are passed to git
as given, and everything after `--` is passed on without being interpreted by bank.
""",
    "gitall": """Like `bank git`, but also performs the command in the syncrepo. Example usage:

  bank gitall checkout master
  bank gitall fetch --prune
""",
}


# --------------------------------------------------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------------------------------------------------


def complete_git_command(**_: object) -> list[str]:
    """Shell completion for the git command of `bank git` / `bank gitall`."""
    return commands.APPROVED_GIT_COMMANDS


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False everywhere: otherwise `bank git log --color` would be taken as an abbreviation of --colorize.
    syncfile_options = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    syncfile_options.add_argument("--syncfile", metavar="SYNCFILE", help="the path to the syncfile (by default it is found from the current directory)")

    common_options = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common_options.add_argument(
        "--verbosity",
        metavar="NUM",
        type=int,
        choices=VERBOSITY_VALUES,
        help="how much to report: 0 (only errors), 1 (the overall result), 2 (a line per repo, the default), 3 (also the git commands run), 4 (also git queries)",
    )
    common_options.add_argument("--colorize", metavar="WHEN", choices=COLORIZE_VALUES, help="color the output: auto (on a terminal unless NO_COLOR is set, the default), yes or no")
    common_options.add_argument("--dryrun", action="store_true", help="print what would happen instead of performing the command")

    parser = argparse.ArgumentParser(
        prog="bank",
        description=MAIN_DESCRIPTION,
        epilog=MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"banksync {__version__}. Author: Jason F Harris.\nhttps://github.com/jasonfharris/banksync",
        help="show the version number of banksync and exit",
    )
    subparsers = parser.add_subparsers(title="commands", dest="command", metavar="", required=True)

    def add_command(name: str, parents: Sequence[argparse.ArgumentParser] = (syncfile_options, common_options)) -> argparse.ArgumentParser:
        return subparsers.add_parser(
            name,
            help=COMMAND_HELP[name],
            description=COMMAND_HELP[name],
            epilog=wrap_paragraphs(COMMAND_EPILOG[name]),
            parents=list(parents),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            allow_abbrev=False,
        )

    sync = add_command("sync")
    sync.add_argument("--matching", metavar="MATCH", choices=MATCHING_VALUES, help="how to find each recorded revision: shaOnly, timestamp (sha, then the same timestamp) or closetimestamp (sha, same timestamp, then the closest timestamp; the default)")
    sync.add_argument("--syncBranches", metavar="WHEN", choices=SYNC_BRANCHES_VALUES, help="whether to create (yes) or create and move (force) the recorded branches to the recorded commits: no (the default), yes or force")

    add_command("record_repos")

    create_syncfile = add_command("create_syncfile")
    create_syncfile.add_argument("repos", metavar="reponame", nargs="+", help="the repos to be included in the bank")

    create_syncrepo = add_command("create_syncrepo", [common_options])
    create_syncrepo.add_argument("repos", metavar="reponame", nargs="+", help="the repos to be included in the bank")
    create_syncrepo.add_argument("--syncfilename", metavar="NAME", help="the file name of the syncfile (default syncfile.json)")
    create_syncrepo.add_argument("--syncreponame", metavar="PATH", help="the name or path of the syncrepo to create (default syncrepo)")

    clone = add_command("clone", [common_options])
    clone.add_argument("url", metavar="URL", help="the URL of the syncrepo")
    clone.add_argument("name", metavar="NAME", nargs="?", help="the directory to create for the bank (default: derived from the URL)")

    add_command("populate")
    add_command("status")

    bisect = add_command("bisect")
    bisect.add_argument("bisectcmd", metavar="BISECTCMD", nargs="?", default="log", choices=BISECT_SUBCOMMANDS, help="the git bisect subcommand (default log)")

    for name, where in [("git", "on all the repos in the bank"), ("gitall", "on all the repos in the bank including the syncrepo")]:
        git_command = add_command(name)
        gitcmd = git_command.add_argument("gitcmd", metavar="GITCMD", nargs="?", default="status", help=f"the git command to perform {where}, e.g. one of {commands.APPROVED_GIT_COMMANDS}.")
        gitcmd.completer = complete_git_command  # type: ignore[attr-defined]

    return parser


def parse_arguments(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    """Parse the command line. Arguments bank does not recognize are passed on to git by `bank git` / `bank bisect`.

    Everything from a `--` onwards is passed on unparsed, including the `--` itself, so that for example
    `bank git checkout -- file.txt` and `bank git log -- path` reach git as written."""
    parser = build_parser()
    argcomplete.autocomplete(parser)
    if not argv:
        parser.print_help()
        sys.exit(1)
    argv = list(argv)
    split = argv.index("--") if "--" in argv else len(argv)
    args, extra_args = parser.parse_known_args(argv[:split])
    return args, extra_args + argv[split:]


def command_line_layer(args: argparse.Namespace) -> dict[str, str]:
    """The options given on the command line, as `section.key` option values."""
    names = {
        "verbosity": "general.verbosity",
        "colorize": "general.colorize",
        "matching": "sync.matching",
        "syncBranches": "sync.syncbranches",
        "syncfilename": "create_syncrepo.syncfilename",
        "syncreponame": "create_syncrepo.syncreponame",
    }
    return {option: str(value) for attribute, option in names.items() if (value := getattr(args, attribute, None)) is not None}


# --------------------------------------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------------------------------------


def configure(opts: Options) -> Options:
    console.verbosity = opts.verbosity
    console.colorize = opts.colorize
    return opts


def run_command(args: argparse.Namespace, extra_args: list[str]) -> bool:
    """Resolve the options and run the command. Returns whether it succeeded."""
    command: str = args.command
    rc_layer = user_rc_layer()
    cli_layer = command_line_layer(args)

    def options_for(syncfile: SyncFile) -> Options:
        """The options for a command that works on `syncfile`, including those set in its configuration section."""
        return configure(Options.resolve(rc_layer, syncfile_layer(syncfile.configuration), cli_layer, dryrun=args.dryrun))

    opts = configure(Options.resolve(rc_layer, cli_layer, dryrun=args.dryrun))
    match command:
        case "create_syncfile":
            return commands.create_syncfile(Path(args.syncfile or "syncfile.json").absolute(), args.repos, opts)
        case "create_syncrepo":
            return commands.create_syncrepo(args.repos, opts)
        case "clone":
            return commands.clone(args.url, args.name, opts, options_for)

    syncfile = SyncFile.load(locate_syncfile(args.syncfile, __version__))
    opts = options_for(syncfile)
    match command:
        case "sync":
            return commands.sync(syncfile, opts)
        case "record_repos":
            return commands.record_repos(syncfile, opts)
        case "populate":
            return commands.populate(syncfile, opts)
        case "status":
            return commands.status(syncfile, opts)
        case "bisect":
            return commands.bisect(syncfile, args.bisectcmd, extra_args, opts)
        case "git" | "gitall":
            return commands.git_in_each_repo(syncfile, args.gitcmd, extra_args, command == "gitall", opts)
    raise BanksyncError(f"failure! unknown command {command}.")


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_args = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        return 0 if run_command(args, extra_args) else 1
    except (BanksyncError, CommandFailed) as error:
        console.say(console.red(str(error)), 0)
        return 1
    except FileNotFoundError as error:
        if error.filename == "git":
            console.say(console.red("failure! git was not found; banksync needs git on the PATH."), 0)
            return 1
        raise
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
