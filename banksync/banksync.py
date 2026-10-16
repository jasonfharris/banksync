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

# Commands that create a syncrepo or syncfile, and commands that use an existing syncfile.
CREATION_COMMANDS = ["create_syncfile", "create_syncrepo", "clone"]
OPERATION_COMMANDS = ["sync", "record_repos", "bisect", "populate", "git", "gitall", "status"]

BISECT_SUBCOMMANDS = ["start", "bad", "new", "good", "old", "terms", "skip", "reset", "visualize", "replay", "log", "run"]



# --------------------------------------------------------------------------------------------------------------------
# Help texts
# --------------------------------------------------------------------------------------------------------------------

MAIN_DESCRIPTION = "execute operations across a collection of git repositories."
MAIN_EPILOG = wrap_paragraphs(
    """bank is a command line utility to checkout or create a synchronized state across a collection (a bank) of
repositories, or to perform a git command in each of the repositories in the bank. The information about the
repositories in the bank is specified in a "syncfile". The syncfile lives inside a normal git repo which we call the
"syncrepo".

Using bank allows a more general way to handle sub-repositories / submodules. It is intended to be less brittle than
traditional ways to specify submodules by allowing some looseness / decoupling.

The bank command line utility can also be used to issue a normal git command to every repository specified in the
syncfile through use of `bank git <cmd>` and `bank gitall <cmd>`. Ie to issue the git command <cmd> to every repo in the bank of repos.

All of the options, can be specified in in the syncfile itself or in your ~/.backsyncrc file so they do not
need to be specified each time on the command line. See the documentation for the syncfile for more information."""
)

COMMAND_HELP: dict[str, str] = {
    "sync": "checkout / update the repos given in the syncfile to the states given in the syncfile",
    "record_repos": "alter the contents of the syncfile so that it matches the current revisions of the referenced repositories.",
    "create_syncfile": "create or overwrite the syncfile to contain the current sync states for the passed in repos.",
    "create_syncrepo": "create or overwrite the syncrepo to contain the current sync states for the passed in repos.",
    "clone": "clone the repos specified in the syncfile",
    "populate": "populate the repos specified in the syncfile",
    "status": "reports the status of the repos specified in the syncfile",
    "bisect": "bisect the syncrepo and sync all repos in the bank to the new state of the syncfile",
    "git": "perform the given git command in each repo in the bank",
    "gitall": "perform the given git command in each repo in the bank and additionally in the syncrepo",
}

COMMAND_EPILOG: dict[str, str] = {
    "sync": """Example usage:

  bank sync

This would find the "prevaling" syncfile.json and checkout / update the repos specified in the syncfile to the states given
in the syncfile and list the results of the sync on each repo in the bank.

  bank sync --syncfile some/dir/syncfile.json

This would checkout / update the repos given in the syncfile.json located at some/dir to the states given
in the syncfile.json.

  bank sync --syncBranches yes

Sync the repos in the bank to the "prevaling" syncfile.json and sync the branches specified in the
syncfile to the commits specified in the syncfile. This is useful if you want to change the branches to
their state specified in the syncfile. If a branch for a child repo given in the syncfile already exists in the
child repo, then don't move the branch. If the branch does not exist in the child repo, then create the branch
and point it to the commit specified in the syncfile.

  bank sync --syncBranches force

If the force option is used, then this acts like `--syncBranches yes` however the branch will be created or
moved to the committ given in the syncfile even if the branch already exists in the child repo and is pointing
to a different commit. (Be aware of course that this will move the local branches in the child repos to the commits
specified in the syncfile and as such commits could be lost if there are no other references to them.)
""",
    "record_repos": """Example usage:

  bank record_repos --syncfile syncfile.json

This would alter the contents of syncfile.json so that it matches the current revisions of the referenced repositories.
""",
    "create_syncfile": """Example usage:

  bank create_syncfile --syncfile syncrepo/syncfile.json repo1 repo2 ... repoN

This would create or overwrite the syncfile.json to record the current states of repo1 repo2 ... repoN. Alternatively you could execute

  bank create_syncfile --syncfile syncfile.json path1/to/repo1 path2/to/repo2 ... path3/to/repoN
""",
    "create_syncrepo": """Example usage:

  bank create_syncrepo repo1 repo2 ... repoN

This would create and initilize a git repository called syncrepo and inside there it would create the syncfile.json
to record the current states of the repo1 repo2 ... repoN which are located at this level. repo1, repo2, etc
are the names or paths to the repositories to track in the bank collection.

  bank create_syncrepo --syncrepo <syncreponame> repo1 repo2 ... repoN

This would create the syncrepo as the above command, but the repo would be called syncreponame.

  bank create_syncrepo --syncrepo some/path/syncreponame repo1 repo2 ... repoN

  This would create the syncrepo as the above command, but the repo would be called syncreponame and located
  at some/path relative to the current directory.

  bank create_syncrepo --syncrepo some/path/syncreponame --syncfilename devCollection.json repo1 repo2 ...
  repoN

  This would create the syncrepo as the above command, but the syncfile would be named devCollection.json and located
  at some/path/syncreponame/devCollection.json relative to the current directory.
""",
    "clone": """Example usage:

  bank clone https://github.com/myProject/syncrepo.git myProject

This would create the folder myProject and clone the syncrepo into myProject, and then populate each of the constituent repositories specified in the syncfile.
""",
    "populate": """Example usage:

  bank populate --syncfile syncfile.json

This would perform a git clone for each of the repositories specified in the syncfile.
""",
    "status": """Example usage:

  bank status --syncfile syncfile.json

This would report the status of each of the repositories specified in the syncfile.
""",
    "bisect": """Example usage:

  bank bisect --syncfile syncfile.json reset

This would pass the reset to the bisection of the sync-repo.
""",
    "git": """Example usage:

  bank git status --syncfile syncfile.json

Perform git status and list the results on each of the repositories specified in the syncfile.json

  bank git tag release_1.7.0.1

Use the prevailing syncfile and apply the command `git tag release_1.7.0.1` to each of the
repos in the bank.
""",
    "gitall": f"""The common git commands which make sense have been "approved" are
{commands.APPROVED_GIT_COMMANDS}. (Actually any git command can be used but so far only those common git
commands have been "approved" as making sense in the setting of banksync. Some other git commands definitely do not make
sense such as `git rebase --interactive` since the bank command is not interactive. Command completion on the command
line only works for the common commands.

Example usage:

  bank gitall status --syncfile syncfile.json

Perform git status and list the results on each of the repositories specified in the syncfile.json
and in addition to the actual repo containing the sync file (the syncrepo)

  bank gitall tag release_1.7.0.1

Use the prevailing syncfile and apply the command `git tag release_1.7.0.1` to each of the
repos in the bank and in addition to the actual repo containing the sync file (the syncrepo).
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
    syncfile_options.add_argument("--syncfile", metavar="SYNCFILE", help="the path to the syncfile")

    common_options = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common_options.add_argument(
        "--verbosity",
        metavar="NUM",
        type=int,
        choices=VERBOSITY_VALUES,
        help="Specify the level of reported feedback / detail. Acceptable values: 1 (minimal feedback), 2 (some feedback) , 3 (detailed feedback), or 4 (full feedback)",
    )
    common_options.add_argument("--colorize", metavar="BOOL", choices=COLORIZE_VALUES, help=f"Colorize the output: {list(COLORIZE_VALUES)}")
    common_options.add_argument("--dryrun", action="store_true", help="Print what would happen instead of performing the command")

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
        help="Show the version number of the banksync tool and exit",
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
    sync.add_argument("--matching", metavar="MATCH", choices=MATCHING_VALUES, help=f'specify how we can recognize a revision "match": {list(MATCHING_VALUES)}')
    sync.add_argument("--syncBranches", metavar="BRANCHES", choices=SYNC_BRANCHES_VALUES, help=f"Sync branches as well: {list(SYNC_BRANCHES_VALUES)}")

    add_command("record_repos")

    create_syncfile = add_command("create_syncfile")
    create_syncfile.add_argument("repos", metavar="reponame", nargs="+", help="the repos to be included in the bank")

    create_syncrepo = add_command("create_syncrepo", [common_options])
    create_syncrepo.add_argument("repos", metavar="reponame", nargs="+", help="the repos to be included in the bank")
    create_syncrepo.add_argument("--syncfilename", metavar="NAME", help="specify the name and extension of the syncfile")
    create_syncrepo.add_argument("--syncreponame", metavar="NAME", help="specify the name of the syncrepo")

    clone = add_command("clone", [common_options])
    clone.add_argument("url", metavar="URL", help="the URL of the sync repo")
    clone.add_argument("name", metavar="NAME", nargs="?", help="the optional name for the repo")

    add_command("populate")
    add_command("status")

    bisect = add_command("bisect")
    bisect.add_argument("bisectcmd", metavar="BISECTCMD", nargs="?", default="log", choices=BISECT_SUBCOMMANDS, help=f"the bisect subcommand one of {BISECT_SUBCOMMANDS}.")

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
