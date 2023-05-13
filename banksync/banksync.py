#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import os.path
import sys
import argparse
import argcomplete
import json
from collections import OrderedDict
from sysexecute import *
from .banksync_common import *

__version__ = "0.9.10"
__sync_file_version__ = "1.0"

# --------------------------------------------------------------------------------------------------------------------------
# Defines
# --------------------------------------------------------------------------------------------------------------------------

tryOrder = ["sha", "UnixTimeStamp"]
defaultSyncPointBranchName = "syncPoint"



# --------------------------------------------------------------------------------------------------------------------------
# Command and Option setup
# --------------------------------------------------------------------------------------------------------------------------

defaultOptions = {
    'general' : {
        'syncfile' : 'syncfile.json',
        'verbosity' : 2,
        'colorize' : 'yes',
        'seperator' : ' '
    },
    'sync' : {
        'matching' : 'closetimestamp'
    },
    'create_syncrepo' : {
        'syncfilename' : 'syncfile.json',
        'syncreponame' : 'syncrepo'
    }
}

# These can create a syncrepo or syncfile
banksync_creation_commands = ['create_syncfile', 'create_syncrepo', 'clone']

# These commands use an existing syncfile
banksync_operation_commands = ['sync', 'record_repos', 'bisect', 'populate', 'git', 'gitall', 'status']
banksync_commands = banksync_creation_commands + banksync_operation_commands

# List of git commands that are suitable for operating over multiple repositories in the bank collection. (This list may not be exhaustive)
approved_git_commands = ['reset', 'log', 'status', 'branch', 'checkout', 'commit', 'tag', 'diff', 'fetch',
                         'push', 'pull', 'prune', 'gc', 'fsck', 'ls-files', 'ls-remote', 'ls-tree']

bisectSubCommands = ['start', 'bad', 'new', 'good', 'old', 'terms', 'skip', 'reset', 'visualize', 'replay', 'log', 'run']

# This list was culled from `git help -a`
allGitCommands = [
  'add',                       'credential-store',          'index-pack',                'patch-id',                  'shortlog',
  'add--interactive',          'cvsexportcommit',           'init',                      'prune',                     'show',
  'am',                        'cvsimport',                 'init-db',                   'prune-packed',              'show-branch',
  'annotate',                  'cvsserver',                 'instaweb',                  'pull',                      'show-index',
  'apply',                     'daemon',                    'interpret-trailers',        'push',                      'show-ref',
  'archimport',                'describe',                  'log',                       'quiltimport',               'stage',
  'archive',                   'diff',                      'ls-files',                   'read-tree',                 'stash',
  'bisect',                    'diff-files',                 'ls-remote',                 'rebase',                    'status',
  'bisect--helper',            'diff-index',                'ls-tree',                   'receive-pack',              'stripspace',
  'blame',                     'diff-tree',                 'mailinfo',                  'reflog',                     'submodule',
  'branch',                    'difftool',                  'mailsplit',                 'relink',                    'submodule--helper',
  'bundle',                    'difftool--helper',          'merge',                     'remote',                    'svn',
  'cat-file',                   'fast-export',               'merge-base',                'remote-ext',                'symbolic-ref',
  'check-attr',                'fast-import',               'merge-file',                 'remote-fd',                 'tag',
  'check-ignore',              'fetch',                     'merge-index',               'remote-ftp',                'unpack-file',
  'check-mailmap',             'fetch-pack',                'merge-octopus',             'remote-ftps',               'unpack-objects',
  'check-ref-format',          'filter-branch',              'merge-one-file',             'remote-http',               'update-index',
  'checkout',                  'fmt-merge-msg',             'merge-ours',                'remote-https',              'update-ref',
  'checkout-index',            'for-each-ref',              'merge-recursive',           'remote-testsvn',            'update-server-info',
  'cherry',                    'format-patch',              'merge-resolve',             'repack',                    'upload-archive',
  'cherry-pick',               'fsck',                      'merge-subtree',             'replace',                   'upload-pack',
  'citool',                    'fsck-objects',              'merge-tree',                'request-pull',              'var',
  'clean',                     'gc',                        'mergetool',                 'rerere',                    'verify-commit',
  'clone',                     'get-tar-commit-id',         'mktag',                     'reset',                     'verify-pack',
  'column',                    'grep',                      'mktree',                    'rev-list',                  'verify-tag',
  'commit',                    'gui',                       'mv',                        'rev-parse',                 'web--browse',
  'commit-tree',               'gui--askpass',              'name-rev',                  'revert',                    'whatchanged',
  'config',                     'hash-object',               'notes',                     'rm',                        'worktree',
  'count-objects',             'help',                      'p4',                        'send-email',                'write-tree',
  'credential',                'http-backend',              'pack-objects',              'send-pack',
  'credential-cache',          'http-fetch',                'pack-redundant',            'sh-i18n--envsubst',
  'credential-cache--daemon',  'http-push',                 'pack-refs',                 'shell',
]

matchingOptionValues = ['shaOnly', 'timestamp', 'closetimestamp']
colorizeOptionValues = ['yes', 'no']


# --------------------------------------------------------------------------------------------------------------------------
# Set up argument parsing
# --------------------------------------------------------------------------------------------------------------------------

mainDescription = 'execute operations across a collection of git repositories.'
mainEpilog = wrapParagraphs(
'''bank is a command line utility to checkout or create a synchronized state across a collection (a bank) of
repositories, or to perform a git command in each of the repositories in the bank. The information about the
repositories in the bank is specified in a "syncfile". The syncfile lives inside a normal git repo which we call the
"syncrepo".

Using bank allows a more general way to handle sub-repositories / submodules. It is intended to be less brittle than
traditional ways to specify submodules by allowing some looseness / decoupling.

The bank command line utility can also be used to issue a normal git command to every repository specified in the
syncfile through use of `bank git <cmd>` and `bank gitall <cmd>`. Ie to issue the git command <cmd> to every repo in the bank of repos.

All of the options, can be specified in in the syncfile itself or in your ~/.backsyncrc file so they do not
need to be specified each time on the command line. See the documentation for the syncfile for more information.''')

cmdHelp = {}
cmdDescription = {}
cmdEpilog = {}

#  CMD: sync ----------

cmdHelp['sync'] = 'checkout / update the repos given in the syncfile to the states given in the syncfile'
cmdDescription['sync'] = cmdHelp['sync']
cmdEpilog ['sync']= wrapParagraphs(
    '''Example usage:

  bank sync --syncfile syncfile.json

This would checkout / update the repos given in the syncfile.json to the states given
in the syncfile.json.

  bank sync --syncfile some/dir/syncfile.json

This would checkout / update the repos given in the syncfile.json located at some/dir to the states given
in the syncfile.json.

  bank sync

Use the syncfile in the current syncrepo directory and list the results of the sync on each repo in the bank.
''')


#  CMD: record_repos ----------

cmdHelp['record_repos'] = 'alter the contents of the syncfile so that it matches the current revisions of the referenced repositories.'
cmdDescription['record_repos'] = cmdHelp['record_repos']
cmdEpilog ['record_repos']= wrapParagraphs('''Example usage:

  bank record_repos --syncfile syncfile.json

This would alter the contents of syncfile.json so that it matches the current revisions of the referenced repositories.
''')


#  CMD: create_syncfile ----------

cmdHelp['create_syncfile'] = 'create or overwrite the syncfile to contain the current sync states for the passed in repos.'
cmdDescription['create_syncfile'] = cmdHelp['create_syncfile']
cmdEpilog ['create_syncfile']= wrapParagraphs('''Example usage:

  bank create_syncfile --syncfile syncrepo/syncfile.json repo1 repo2 ... repoN

This would create or overwrite the syncfile.json to record the current states of repo1 repo2 ... repoN. Alternatively you could execute

  bank create_syncfile --syncfile syncfile.json path1/to/repo1 path2/to/repo2 ... path3/to/repoN

''')


#  CMD: create_syncrepo ----------

cmdHelp['create_syncrepo'] = 'create or overwrite the syncrepo to contain the current sync states for the passed in repos.'
cmdDescription['create_syncrepo'] = cmdHelp['create_syncrepo']
cmdEpilog ['create_syncrepo']= wrapParagraphs('''Example usage:

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

''')

#  CMD: clone ----------

cmdHelp['clone'] = 'clone the repos specified in the syncfile'
cmdDescription['clone'] = cmdHelp['clone']
cmdEpilog ['clone']= wrapParagraphs('''Example usage:

  bank clone https://github.com/myProject/syncrepo.git myProject

This would create the folder myProject and clone the syncrepo into myProject, and then populate each of the constituent repositories specified in the syncfile.
''')


#  CMD: populate ----------

cmdHelp['populate'] = 'populate the repos specified in the syncfile'
cmdDescription['populate'] = cmdHelp['populate']
cmdEpilog ['populate']= wrapParagraphs('''Example usage:

  bank populate --syncfile syncfile.json

This would perform a git clone for each of the repositories specified in the syncfile.
''')


#  CMD: status ----------

cmdHelp['status'] = 'reports the status of the repos specified in the syncfile'
cmdDescription['status'] = cmdHelp['status']
cmdEpilog ['status']= wrapParagraphs('''Example usage:

  bank status --syncfile syncfile.json

This would report the status of each of the repositories specified in the syncfile.
''')

#  CMD: bisect ----------

cmdHelp['bisect'] = 'bisect the syncrepo and sync all repos in the bank to the new state of the syncfile'
cmdDescription['bisect'] = cmdHelp['bisect']
cmdEpilog ['bisect']= wrapParagraphs('''Example usage:

  bank bisect --syncfile syncfile.json reset

This would pass the reset to the bisection of the sync-repo.
''')


#  CMD: git ----------

cmdHelp['git'] = 'perform the given git command in each repo in the bank'
cmdDescription['git'] = cmdHelp['git']
cmdEpilog ['git']= wrapParagraphs('''Example usage:

  bank git status --syncfile syncfile.json

Perform git status and list the results on each of the repositories specified in the syncfile.json

  bank git tag release_1.7.0.1

Use the prevailing syncfile and apply the command `git tag release_1.7.0.1` to each of the
repos in the bank.
''')


#  CMD: gitall ----------

cmdHelp['gitall'] = 'perform the given git command in each repo in the bank and additionally in the syncrepo'
cmdDescription['gitall'] = cmdHelp['gitall']
cmdEpilog ['gitall']= wrapParagraphs('''

The common git commands which make sense have been "approved" are
{approved_git_commands}. (Actually any git command can be used but so far only those common git
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
''')

def parseArguments():

    pathOps_parser = argparse.ArgumentParser(add_help=False)
    pathOps_parser.add_argument("--syncfile", metavar="SYNCFILE", help="the path to the syncfile", default='auto')

    commonOpts_parser = argparse.ArgumentParser(add_help=False)
    commonOpts_parser.add_argument("--verbosity", metavar="NUM", help="Specify the level of reported feedback / detail. Acceptable values: 1 (minimal feedback), 2 (some feedback) , 3 (detailed feedback), or 4 (full feedback)", type=int, default=autoNum)
    commonOpts_parser.add_argument('--colorize', metavar='BOOL', help=f"Colorize the output: {colorizeOptionValues}", choices=colorizeOptionValues, default='auto')
    commonOpts_parser.add_argument('--dryrun', dest='dryrun', action='store_true', help="Print what would happen instead of performing the command")
    commonOpts_parser.set_defaults(dryrun=False)

    parser = argparse.ArgumentParser(description=mainDescription, epilog=mainEpilog, formatter_class=argparse.RawDescriptionHelpFormatter, prog='bank')
    parser.add_argument('--version', dest='version', action='store_true', help="Show the version number of the banksync tool and exit")
    parser.set_defaults(version=False)

    subparsers = parser.add_subparsers(title='commands', dest='command', metavar = '')
    def addSubparser(name, parent_parsers=[pathOps_parser, commonOpts_parser]):
        return subparsers.add_parser(name, help=cmdHelp.get(name, ""), description=cmdDescription.get(name, ""), epilog=cmdEpilog.get(name, ""), parents = parent_parsers, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser_syncCmd = addSubparser('sync')
    parser_syncCmd.add_argument("--matching", metavar="MATCH", help=f'specify how we can recognize a revision "match": {matchingOptionValues}', choices=matchingOptionValues, default='auto')

    parser_record_reposCmd = addSubparser('record_repos')

    parser_create_syncfileCmd = addSubparser('create_syncfile')
    parser_create_syncfileCmd.add_argument("repos", metavar="reponame", help='the repos to be included in the bank', nargs="+")

    parser_create_syncrepoCmd = addSubparser('create_syncrepo', [commonOpts_parser])
    parser_create_syncrepoCmd.add_argument("repos", metavar="reponame", help='the repos to be included in the bank', nargs="+")
    parser_create_syncrepoCmd.add_argument("--syncfilename", metavar="NAME", help='specify the name and extension of the syncfile', default='auto')
    parser_create_syncrepoCmd.add_argument("--syncreponame", metavar="NAME", help='specify the name of the syncrepo', default='auto')

    parser_cloneCmd = addSubparser('clone', [commonOpts_parser])
    parser_cloneCmd.add_argument("url", metavar="URL", help='the URL of the sync repo')
    parser_cloneCmd.add_argument("name", metavar="NAME", help='the optional name for the repo', default=None, nargs='?')

    parser_populateCmd = addSubparser('populate')

    parser_statusCmd = addSubparser('status')

    parser_bisectCmd = addSubparser('bisect')
    parser_bisectCmd.add_argument("bisectcmd", metavar="BISECTCMD", nargs='?', help=f"the bisect subcommand one of {bisectSubCommands}.", choices=bisectSubCommands, default='log')

    parser_gitCmd = addSubparser('git')
    parser_gitCmd.add_argument("gitcmd", metavar="GITCMD", nargs='?', help=f"perform one of {approved_git_commands} on all the repos in the bank.", choices=allGitCommands, default='status')

    parser_gitallCmd = addSubparser('gitall')
    parser_gitallCmd.add_argument("gitcmd", metavar="GITCMD", nargs='?', help=f"perform one of {approved_git_commands} on all the repos in the bank including the syncrepo.", choices=allGitCommands, default='status')

    argcomplete.autocomplete(parser)

    def printVersionAndExit():
        printWithVars1(f"banksync {__version__}. Author: Jason F Harris.\nhttps://github.com/jasonfharris/banksync")
        sys.exit(0)

    if len(sys.argv)==1:
        parser.print_help()
        sys.exit(1)

    if len(sys.argv)==2 and sys.argv[1] == '--version':
        printVersionAndExit()

    args, remaining_args = parser.parse_known_args()
    command = args.command

    if command not in banksync_commands:
        printWithVars1(f"unknown command: {command}", 'red')
        sys.exit(1)

    remaining_args = [correctlyQuoteArg(arg) for arg in remaining_args]
    if args.version:
        printVersionAndExit()

    return args, remaining_args



# --------------------------------------------------------------------------------------------------------------------------
# internal utilities
# --------------------------------------------------------------------------------------------------------------------------


def _green(text):
    return colored(text, 'green')
def _red(text):
    return colored(text, 'red')
def _yellow(text):
    return colored(text, 'yellow')

# def _green(text):
#     if not colorize:
#         return colored(text, 'green')
# def _red(text):
#     if not colorize:
#         return colored(text, 'red')
# def _yellow(text):
#     if not colorize:
#         return colored(text, 'yellow')


# --------------------------------------------------------------------------------------------------------------------------
# command "sync"
# --------------------------------------------------------------------------------------------------------------------------

def commandSync():
    matching = _config['sync.matching']
    checkForSyncRepo(syncFileAbsPath)
    syncDict = loadSyncFileAsDict(syncFileAbsPath)
    allFound = True

    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        offset = _config['relativePathToRepositories']
        repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
        repoString = paddedRepoName(repoName, list(syncDict.keys()))
        if not checkForRepo(repoString, repoAbsPath):
            allFound = False
            continue

        found = False
        for method in tryOrder:
            if found:
                break

            if (method == "sha") and ("sha" in repoInfo):
                sha = repoInfo["sha"]
                shortHash = sha[0:12]
                if dryrun:
                    printWithVars2(f"{repoString}: would try and check out revision by {method}: {shortHash}", dryrun=False)
                    break

                print(f"\r>> checking out {sha}...", end='', flush=True)
                res = gitCommand(f"git checkout -B {defaultSyncPointBranchName} {sha}", 3, cwd=repoAbsPath, verbosity=verbosity)
                if res["code"] == 0:
                    revNum = getRevNumber(repoAbsPath)
                    printWithVars2(f"\r{_green(repoString)}: successfully checked out revision by {method}: {shortHash} (revision number {revNum})")
                    found = True
                    break
                printWithVars3(f"\r{repoString}: failed to check out revision by {method}: {sha}")

            if (method == "UnixTimeStamp") and ("UnixTimeStamp" in repoInfo):
                if (matching == 'timestamp') or (matching == 'closetimestamp'):
                    ts = repoInfo["UnixTimeStamp"]
                    date = dateFromTimestamp(ts)
                    if dryrun:
                        printWithVars2(f"{repoString}: would try and check out revision by {method}: {ts} ({date})", dryrun=False)
                        break

                    res = gitCommand("git log --all --format=format:'\"%at\" : \"%H\",'", 4, cwd=repoAbsPath, raiseOnFailure=True, verbosity=verbosity, permitShowingStdOut=False, permitShowingStdErr=False)
                    if res["code"] == 0:
                        timestampsToShas = json.loads('{'+res["stdout"][0:-1]+'}')
                        if (ts in timestampsToShas):
                            if (matching == 'timestamp') or (matching == 'closetimestamp'):
                                sha = timestampsToShas[ts]
                                branch=defaultSyncPointBranchName
                                print(f"\r>> checking out {ts} ({date})...", end='', flush=True)
                                res = gitCommand(f"git checkout -B {branch} {sha}", 3, cwd=repoAbsPath, verbosity=verbosity)
                                if res["code"] == 0:
                                    revNum = getRevNumber(repoAbsPath)
                                    printWithVars2(f"{_green(repoString)}: successfully checked out revision by {method}: {ts} ({date}) {sha} (revision number {revNum})")
                                    found = True
                                    break
                        else:
                            if matching == 'closetimestamp':
                                closestTimestamp = min(timestampsToShas, key=lambda x:abs(int(x)-int(ts)))
                                closestDate = dateFromTimestamp(closestTimestamp)
                                sha = timestampsToShas[closestTimestamp]
                                branch=defaultSyncPointBranchName
                                print(f"\r>> checking out close {ts} ({date})...", end='', flush=True)
                                res = gitCommand(f"git checkout -B {branch} {sha}", 3, cwd=repoAbsPath, verbosity=verbosity)
                                if res["code"] == 0:
                                    revNum = getRevNumber(repoAbsPath)
                                    printWithVars2(f"\r{_yellow(repoString)}: warning checking out revision by closest timestamp.", "red")
                                    printWithVars2(f"       requested {method}: {ts} ({date})")
                                    printWithVars2(f"       used      {method}: {closestTimestamp} ({closestDate}) {sha} (revision number {revNum})")
                                    found = True
                                    break

                    printWithVars3(f"\r{repoString}: failed to check out revision by {method}: {ts} {date}")

        if not found and not dryrun:
            allFound = False
            printWithVars2(f"{_red(repoString)}: failed to check out specified revision by any method.")
    if dryrun:
        pass
    elif allFound:
        print(colored("success! all repos checked out to the specified sync state.", 'green'))
    else:
        print(colored("failure! not all repos checked out to the specified sync state.", 'red'))
        sys.exit(1)



# --------------------------------------------------------------------------------------------------------------------------
# command "record_repos"
# --------------------------------------------------------------------------------------------------------------------------

def commandRecordRepos():
    checkForSyncRepo(syncFileAbsPath)
    syncDict = loadSyncFileAsDict(syncFileAbsPath)
    newSyncDict = OrderedDict(syncDict)
    anyFailures = False
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        offset = _config['relativePathToRepositories']
        repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
        repoString = paddedRepoName(repoName, list(syncDict.keys()))
        if not checkForRepo(repoString, repoAbsPath):
            anyFailures = True
            continue

        root = os.path.join(syncRepoAbsPath, offset)
        (worked, newRepoInfo) = dictFromCurrentRepoState(repoAbsPath, root, verbosity=verbosity, dryrun=False)
        if worked:
            shortHash = newRepoInfo["sha"][0:12]
            date = newRepoInfo["date"]
            printWithVars2(f"{_green(repoString)}: recording bank sync state of {shortHash}, {date}.")
        else:
            printWithVars2(f"{_red(repoString)}: failure! not able to get the status of {repoName} at {repoAbsPath}", 'red')
            anyFailures = True
        newSyncDict[repoName] = newRepoInfo

    if dryrun:
        sys.exit(0)

    writeDictToSyncFile(syncFileAbsPath, newSyncDict)

    if anyFailures:
        printWithVars1("failure! not all constituent repos had their state recorded.", 'red')
        sys.exit(1)
    else:
        printWithVars1("success! all constituent repos had their state recorded.", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# command "create_syncfile"
# --------------------------------------------------------------------------------------------------------------------------

def commandCreateSyncfile():
    repoNames = _config['args.repos']
    checkForSyncRepoDir(syncRepoAbsPath, existing = False)

    # Assemble the dictionary of repo Information for each repo
    dictOfRepoInfo = OrderedDict()
    repoAbsPaths = {}
    anyFailures = False
    for repo in repoNames:
        offset = _config['relativePathToRepositories']
        repoAbsPath = os.path.normpath(os.path.join(syncRepoAbsPath, offset, repo))
        repoName = os.path.basename(repoAbsPath)
        repoAbsPaths[repoName] = repoAbsPath
        repoString = paddedRepoName(repoName, repoNames)
        if not checkForRepo(repoName, repoAbsPath):
            anyFailures = True
            continue

        root = os.path.join(syncRepoAbsPath, offset)
        (worked, newRepoInfo) = dictFromCurrentRepoState(repoAbsPath, root, verbosity=verbosity, dryrun=False)
        if worked:
            shortHash = newRepoInfo["sha"][0:12]
            date = newRepoInfo["date"]
            printWithVars2(f"{_green(repoString)}: recording repository state of {shortHash}, {date}.")
        else:
            printWithVars2(f"failure! not able to get the status of {repoName} at {repoAbsPath}", 'red')
            anyFailures = True
        dictOfRepoInfo[repoName] = newRepoInfo

    # Find the common root path for the repos and what that is relative to the syncRepoAbsPath to get the
    # computed offset and adjust the path's accordingly.
    commonPathPrefix = os.path.dirname(os.path.commonprefix(list(repoAbsPaths.values())))
    offset = os.path.relpath(commonPathPrefix, syncRepoAbsPath)
    root = os.path.join(syncRepoAbsPath, offset)

    for repoName in dictOfRepoInfo:
        repoInfo = dictOfRepoInfo[repoName]
        repoAbsPath = repoAbsPaths[repoName]
        repoInfo["path"] = os.path.relpath(repoAbsPath, root)

    # Assemble The combined information with configuration and repositories
    configurationDict = OrderedDict()
    configurationDict["createdByBanksyncVersion"] = __version__
    configurationDict["syncfileFormatVersion"] = __sync_file_version__
    configurationDict["cwd"] = offset
    configurationDict["syncreponameForClone"] = os.path.relpath(syncRepoAbsPath, root)
    newSyncDict = OrderedDict()
    newSyncDict["configuration"] = configurationDict
    newSyncDict["repositories"] = dictOfRepoInfo

    if dryrun:
        sys.exit(0)

    writeDictToSyncFile(syncFileAbsPath, newSyncDict)

    if anyFailures:
        printWithVars1("failure! not all constituent repos had their state recorded.",'red',)
        sys.exit(1)
    else:
        printWithVars1("success! all constituent repos had their state recorded.", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# command "create_syncrepo"
# --------------------------------------------------------------------------------------------------------------------------

def commandCreateSyncrepo():
    global syncRepoAbsPath, syncFileAbsPath
    syncfilename = _config['create_syncrepo.syncfilename']
    syncreponame = _config['create_syncrepo.syncreponame']

    syncRepoAbsPath = os.path.abspath(syncreponame)
    if isFilenameWithoutPath(syncfilename):
        syncFileAbsPath = os.path.join(syncRepoAbsPath, syncfilename)
    elif os.path.abspath(syncfilename) == syncRepoAbsPath:
        syncFileAbsPath = os.path.abspath(syncfilename)
    else:
        printWithVars1(f"failure! sync file name: {syncfilename} does not live directly inside {syncreponame}.", 'red')
        sys.exit(1)

    if os.path.isdir(syncRepoAbsPath):
        printWithVars1(f"failure! The directory {syncRepoAbsPath} already exists.", 'red')
        sys.exit(1)

    if dryrun:
        printWithVars1(f"The directory {syncRepoAbsPath} would be created and a git repository would be initilized there. The file {syncFileAbsPath} would be created and filled.")
        sys.exit(0)

    os.makedirs(syncRepoAbsPath)
    execute2("git init", cwd=syncRepoAbsPath)

    commandCreateSyncfile()



# --------------------------------------------------------------------------------------------------------------------------
# command "bisect"
# --------------------------------------------------------------------------------------------------------------------------

def commandBisect():
    command = _config['args.bisectcmd']
    remainingArgs = _config['remaining_args']
    checkForSyncRepo(syncFileAbsPath)
    syncDict = loadSyncFileAsDict(syncFileAbsPath)
    currentRev = getCurrentRevHash(syncRepoAbsPath)
    anyFailures = False

    if dryrun:
        printWithVars2("would try exectue the given bisect command on the current sync repo and sync the bank repos to the new state.")
        sys.exit(0)

    if command == 'start':
        restoreDict = OrderedDict()
        for repoName in syncDict:
            repoInfo = syncDict[repoName]
            offset = _config['relativePathToRepositories']
            repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
            repoString = paddedRepoName(repoName, list(syncDict.keys()))
            try:
                rev = getCurrentBranchOrHash(repoAbsPath)
                restoreDict[repoAbsPath] = rev
                printWithVars2(f"{_green(repoString)}: recording repository state of '{rev}' before starting bisect")
            except:
                anyFailures = True
                printWithVars2(f"{_red(repoString)}: error recoding original branch in {repoAbsPath}")
                continue
        writeBisectRestoreToJson(syncRepoAbsPath, restoreDict)
        if anyFailures:
            print(colored("failure! not all repo states recorded before bisect.", 'red'))

    bisectCmd = f"git bisect {command} " + " ".join(remainingArgs)
    res = gitCommand(bisectCmd, 2, cwd=syncRepoAbsPath, verbosity=verbosity);
    newRev = getCurrentRevHash(syncRepoAbsPath)
    if newRev != currentRev:
        commandSync()

    if command == 'reset':
        restoreDict = loadBisectRestoreFromJson(syncRepoAbsPath)
        if not restoreDict:
            print(colored("We are not in a bisection or bisection record not found.", 'yellow'))
            sys.exit(0)
        for repoName in syncDict:
            repoInfo = syncDict[repoName]
            offset = _config['relativePathToRepositories']
            repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
            repoString = paddedRepoName(repoName, list(syncDict.keys()))
            try:
                rev = restoreDict[repoAbsPath] if (repoAbsPath in restoreDict) else None
                if not rev:
                    raise Exception("Restore changesete not found")
                res = gitCommand("git checkout {rev}", 3, cwd=repoAbsPath, verbosity=verbosity)
                printWithVars2(f"{_green(repoString)}: restoring repository state to '{rev}' after finishing bisect")
            except:
                anyFailures = True
                printWithVars2(f"{_red(repoString)}: error restoring original branch in {repoAbsPath}")
                continue
        if anyFailures:
            print(colored("failure! not all repo states restored after bisect.", 'red'))
        removeBisectRestoreFile(syncRepoAbsPath)



# --------------------------------------------------------------------------------------------------------------------------
# command "clone"
# --------------------------------------------------------------------------------------------------------------------------

def commandClone():
    global syncFileAbsPath, syncRepoAbsPath, cwd
    cloneURL = _config['args.url']
    if not isValidGitUrl(cloneURL):
        print(colored("failure! {cloneURL} appears not to be a URL that works with git clone.", 'red'))
        sys.exit(1)
    destName = _config['args.name']
    destName = destName if (destName is not None) else getRepoNameFromUrl(cloneURL)
    destNameAbsPath = os.path.abspath(destName)

    execute3("mkdir -p {destNameAbsPath}")
    opts = {'captureStdOutStdErr':False, 'verbosity':verbosity, 'cwd': os.path.dirname(destNameAbsPath)}
    print(f"\r>> cloning {cloneURL}...", end='', flush=True)
    res = gitCommand("git clone {cloneURL} {destName}", 3, **opts)
    if res['code'] != 0:
        anyFailures = True
        printWithVars2(f"\r{_red(cloneURL)}: error cloning repo to {destNameAbsPath}: {res['stderr']}")
        sys.exit(1)

    printWithVars2(f"\r{_green(cloneURL)}: cloned repo to {destNameAbsPath}")

    syncRepoAbsPath = os.path.join(destNameAbsPath, 'syncrepo')

    # If we have just cloned a sync repo (the typical case) then move the contents into the sync repo directory
    if getSyncFileInDir(destNameAbsPath):
        moveDirectory(destNameAbsPath, syncRepoAbsPath)

    syncFileAbsPath = getSyncFileInDir(syncRepoAbsPath)
    if not syncFileAbsPath:
            anyFailures = True
            printWithVars2(f"{_red('failure!') }: no syncfile found at {destNameAbsPath} or {syncRepoAbsPath}")
            sys.exit(1)

    _config['relativePathToRepositories'] = ".." #XXX needs work
    commandPopulate()



# --------------------------------------------------------------------------------------------------------------------------
# command "populate"
# --------------------------------------------------------------------------------------------------------------------------

def commandPopulate():
    checkForSyncRepo(syncFileAbsPath)
    syncDict = loadSyncFileAsDict(syncFileAbsPath)
    anyFailures = False

    opts = {'captureStdOutStdErr':False, 'verbosity':verbosity}
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        offset = _config['relativePathToRepositories']
        repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
        repoString = paddedRepoName(repoName, list(syncDict.keys()))
        if "cloneURL" not in repoInfo:
            anyFailures = True
            printWithVars2(f"{repoString}: there is no cloneURL for this repo", "red")
            continue
        cloneURL = repoInfo["cloneURL"]
        name    = os.path.basename(repoAbsPath)
        dirname = os.path.dirname(repoAbsPath)
        if dryrun:
            printWithVars2(f"{repoString}: would clone {cloneURL} to {repoAbsPath}.", dryrun=False)
            continue

        opts['cwd'] = dirname
        execute3(f"mkdir -p {dirname}")
        print(f"\r>> cloning {name}...", end='', flush=True)
        res = gitCommand(f"git clone {cloneURL} {name}", 3, **opts)
        if res['code'] == 0:
            printWithVars2(f"\r{_green(repoString)}: cloned repo to {repoAbsPath}")
        else:
            anyFailures = True
            printWithVars2(f"\r{_red(repoString)}: error cloning repo to {repoAbsPath}")

    if dryrun:
        sys.exit(0)
    if anyFailures:
        print(colored("failure! not all repos populated.", 'red'))
        sys.exit(1)

    print(colored("success! all repos populated.", 'green'))
    commandSync()


# --------------------------------------------------------------------------------------------------------------------------
# command "status"
# --------------------------------------------------------------------------------------------------------------------------

def commandStatus():
    checkForSyncRepo(syncFileAbsPath)
    syncDict = loadSyncFileAsDict(syncFileAbsPath)
    anyFailures = False

    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        offset = _config['relativePathToRepositories']
        repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
        repoString = paddedRepoName(repoName, list(syncDict.keys()))
        if dryrun:
            printWithVars2(f"{repoString} : would give the status of the repo at {repoAbsPath}.", dryrun=False)
            continue

        if not checkForRepo(repoString, repoAbsPath):
            allFound = False
            anyFailures = True
            continue

        modifiedCount = getModifiedCount(repoAbsPath)
        stagedCount = getStagedCount(repoAbsPath)
        branchName = getBranchName(repoAbsPath)

        # This is actually dimmed not grey since grey appears like black text for me
        def greyText(txt):
            return '\033[2m'+txt+"\033[00m"

        description = f"{greyText('branch')}: {colored(branchName,'blue')}".strip()
        description = description.strip()

        if modifiedCount > 0:
            description = f"{description}, {greyText('modified')}: {modifiedCount}".strip()
        if stagedCount > 0:
            description = f"{description}, {greyText('staged')}: {stagedCount}".strip()
        print(f"{_green(repoString)} : {description}")

    if dryrun:
        sys.exit(0)
    if anyFailures:
        print(colored("failure! not all repos reported the status correctly.", 'red'))
        sys.exit(1)

    print(colored("success! all repos status reported.", 'green'))




# --------------------------------------------------------------------------------------------------------------------------
# a git command
# --------------------------------------------------------------------------------------------------------------------------

def distributeGitCommand():

    command = _config['args.gitcmd']
    includeSyncRepo = (_config['args.command'] == 'gitall')
    remainingArgs = _config['remaining_args']

    if command not in approved_git_commands:
        printWithVars1(f"{_yellow('warning')}: the git command `{command}` might not make sense being applied non-interactively to each repo in the bank. Use at your own discretion.")
    if command not in allGitCommands:
        printWithVars1(f"failure! unknown git command `{command}`", 'red')

    gitCmd = f"git {command} " + " ".join(remainingArgs)
    gitCmd = gitCmd.strip()
    gitRepoSeperatorString = (_config['general.seperator']*40)[0:40]
    checkForSyncRepoDir(syncRepoAbsPath)
    syncDict = loadSyncFileAsDict(syncFileAbsPath)
    anyFailures = False
    opts = {'captureStdOutStdErr':False, 'verbosity':verbosity}
    printWithVars2(gitRepoSeperatorString, dryrun=False)
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        offset = _config['relativePathToRepositories']
        repoAbsPath = os.path.join(syncRepoAbsPath, offset, repoInfo["path"])
        if not checkForRepo(repoName, repoAbsPath):
            anyFailures = True
            continue
        opts['cwd'] = repoAbsPath
        gitCommand(gitCmd, 2, **opts);
        printWithVars2(gitRepoSeperatorString, dryrun=False)
    if includeSyncRepo:
        opts['cwd'] = syncRepoAbsPath
        gitCommand(gitCmd, 2, **opts);
        printWithVars2(gitRepoSeperatorString, dryrun=False)

    if anyFailures:
        printWithVars1("failure! not all constituent repos present.", 'red')
        sys.exit(1)
    else:
        printWithVars1(f"all constituent repos issued git command '{gitCmd}'", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# dispatch command
# --------------------------------------------------------------------------------------------------------------------------

def dispatchCommand():
    command_map = {
        "sync": commandSync,
        "clone": commandClone,
        "populate": commandPopulate,
        "status": commandStatus,
        "record_repos": commandRecordRepos,
        "create_syncfile": commandCreateSyncfile,
        "create_syncrepo": commandCreateSyncrepo,
        "bisect": commandBisect,
        "git": distributeGitCommand,
        "gitall": distributeGitCommand,
    }

    command = _config['args.command']
    if command in command_map:
        command_map[command]()
    else:
        printWithVars1(f"failure! unkown command {command}.", 'red')
        sys.exit(1)


# --------------------------------------------------------------------------------------------------------------------------
# Extract and clean the argument parameters
# --------------------------------------------------------------------------------------------------------------------------

def determinePaths(bankOptions):
    """determine syncFileAbsPath and syncRepoAbsPath"""
    command = bankOptions['args.command']

    if command in ['clone', 'create_syncrepo']:
        return None, None

    syncFileAbsPath = os.path.abspath(bankOptions['general.syncfile'])
    syncRepoAbsPath = os.path.dirname(syncFileAbsPath)

    if command == 'create_syncfile':
        return syncFileAbsPath, syncRepoAbsPath

    passedInName = getattr(bankOptions, 'args.syncfile', 'auto')
    if (passedInName == 'auto') or (os.path.abspath(passedInName) != syncFileAbsPath):
        path = os.path.join(syncRepoAbsPath, "*.json")
        jsonFiles = glob.glob(path)
        if not jsonFiles:
            print(colored(f"failure! could not locate the syncfile in {syncRepoAbsPath}.", 'red'))
            sys.exit(1)
        syncFileAbsPath = jsonFiles[0]

    return syncFileAbsPath, syncRepoAbsPath



def getResolvedOptions(args, remaining_args):

    bankOptions = flattenDict(dict(defaultOptions))
    if os.path.isfile('~/.bankconfigrc'):
        newOptions = flattenDict(getOptionDictFromIniFile('~/.bankconfigrc'))
        bankOptions = mergeOptionDicts(bankOptions, newOptions)

    passedInOptions = {
        'general' : {
            'syncfile' : getattr(args, 'syncfile', 'auto'),
            'verbosity' : getattr(args, 'verbosity', autoNum),
            'colorize' :  getattr(args, 'colorize', 'auto'),
            'seperator' : getattr(args, 'seperator', 'auto'),
        },
        'sync' : {
            'matching' : getattr(args, 'matching', 'auto')
        },
        'create_syncrepo' : {
            'syncfilename' : getattr(args, 'syncfilename', 'auto'),
            'syncreponame' : getattr(args, 'syncreponame', 'auto')
        }
    }

    bankOptions = mergeOptionDicts(bankOptions, flattenDict(passedInOptions))

    # normalize non-string options
    bankOptions['general.verbosity'] = int(bankOptions['general.verbosity'])
    bankOptions['general.colorize'] = bankOptions['general.colorize'].lower() in ['yes','true']

    argsOptions = flattenDict({'args' : vars(args)})
    bankOptions['args'] = vars(args)
    bankOptions['remaining_args'] = remaining_args
    bankOptions = flattenDict(bankOptions)
    
    return bankOptions


def main():
    global syncFileAbsPath, syncRepoAbsPath, verbosity, dryrun, _config
    args, remaining_args = parseArguments()

    _config = getResolvedOptions(args, remaining_args)
    syncFileAbsPath, syncRepoAbsPath = determinePaths(_config)

    _config['relativePathToRepositories'] = ".." # This is the path from the syncFile to the Repositories location
    verbosity = _config['general.verbosity']
    colorize = _config['general.colorize']
    dryrun = _config['args.dryrun']
    set_execute_defaults('verbosity', verbosity)
    set_execute_defaults('dryrun', dryrun)
    set_execute_defaults('colorize', colorize)

    dispatchCommand()


if __name__ == '__main__':
    main()