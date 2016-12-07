#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import os.path
import string
import sys
import time
import re
import argparse
import argcomplete
import json
from collections import OrderedDict
from sysexecute import *
from banksync_common import *

__version__ = "0.7.3"


# --------------------------------------------------------------------------------------------------------------------------
# Defines
# --------------------------------------------------------------------------------------------------------------------------

tryOrder = ["sha", "UnixTimeStamp"]
defaultSyncPointBranchName = "syncPoint"



# --------------------------------------------------------------------------------------------------------------------------
# Command and Option setup
# --------------------------------------------------------------------------------------------------------------------------

defaultOptions = {
    'General' : {
        'cwd' : '.',
        'syncfile' : 'syncfile.wl',
        'verbosity' : 2,
        'colorize' : 'yes'
    },
    'sync' : {
        'matching' : 'closetimestamp'
    }
}

sync_commands = ['sync', 'recordRepos', 'createSyncfile', 'bisect', 'clone', 'git', 'gitall']
approved_git_commands = ['reset', 'log', 'status', 'branch', 'checkout', 'commit', 'tag', 'diff', 'fetch',
                         'push', 'pull', 'prune', 'gc', 'fsck', 'ls-files', 'ls-remote', 'ls-tree']

# This list was culled from `git help -a`
allGitCommands = [
  'add',                       'credential-store',          'index-pack',                'patch-id',                  'shortlog',
  'add--interactive',          'cvsexportcommit',           'init',                      'prune',                     'show',
  'am',                        'cvsimport',                 'init-db',                   'prune-packed',              'show-branch',
  'annotate',                  'cvsserver',                 'instaweb',                  'pull',                      'show-index',
  'apply',                     'daemon',                    'interpret-trailers',        'push',                      'show-ref',
  'archimport',                'describe',                  'log',                       'quiltimport',               'stage',
  'archive',                   'diff',                      'ls-files',                  'read-tree',                 'stash',
  'bisect',                    'diff-files',                'ls-remote',                 'rebase',                    'status',
  'bisect--helper',            'diff-index',                'ls-tree',                   'receive-pack',              'stripspace',
  'blame',                     'diff-tree',                 'mailinfo',                  'reflog',                    'submodule',
  'branch',                    'difftool',                  'mailsplit',                 'relink',                    'submodule--helper',
  'bundle',                    'difftool--helper',          'merge',                     'remote',                    'svn',
  'cat-file',                  'fast-export',               'merge-base',                'remote-ext',                'symbolic-ref',
  'check-attr',                'fast-import',               'merge-file',                'remote-fd',                 'tag',
  'check-ignore',              'fetch',                     'merge-index',               'remote-ftp',                'unpack-file',
  'check-mailmap',             'fetch-pack',                'merge-octopus',             'remote-ftps',               'unpack-objects',
  'check-ref-format',          'filter-branch',             'merge-one-file',            'remote-http',               'update-index',
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
  'config',                    'hash-object',               'notes',                     'rm',                        'worktree',
  'count-objects',             'help',                      'p4',                        'send-email',                'write-tree',
  'credential',                'http-backend',              'pack-objects',              'send-pack',
  'credential-cache',          'http-fetch',                'pack-redundant',            'sh-i18n--envsubst',
  'credential-cache--daemon',  'http-push',                 'pack-refs',                 'shell',
]

commands = sync_commands + allGitCommands
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

All of the options, eg the --syncfile option, the --cwd  option, etc., can be specified in a standard ini config file
`bankconfig.ini` so they do not need to be specified each time on the command line. If the bank command uses the config
file than the bank command must be executed from the same directory which contains the bankconfig.ini file. ''')



#  CMD: sync ----------

syncCmdHelp = 'checkout / update the repos given in the syncfile to the states given in the syncfile'
syncCmdDescription = syncCmdHelp
syncCmdEpilog = wrapParagraphs('''Example usage:

  bank sync --syncfile syncfile.wl

This would checkout / update the repos given in the syncfile.wl to the states given
in the syncfile.wl.

  bank sync --syncfile syncfile.wl --cwd ../other/dir

This would checkout / update the repos given in the syncfile.wl to the states given
in the syncfile.wl (but the path to the repos are prefixed by the value of cwd).

  bank sync

Use the syncfile specified in the file bankconfig.ini and list the results of the sync
on each repo in the bank.
''')


#  CMD: recordRepos ----------

recordReposCmdHelp = 'alter the contents of the syncfile so that it matches the current revisions of the referenced repositories.'
recordReposCmdDescription = recordReposCmdHelp
recordReposCmdEpilog = wrapParagraphs('''Example usage:

  bank recordRepos --syncfile syncfile.wl

This would alter the contents of syncfile.wl so that it matches the current revisions of the referenced repositories.
''')


#  CMD: createSyncfile ----------

createSyncfileCmdHelp = 'create or overwrite the syncfile to contain the current sync states for the passed in repos.'
createSyncfileCmdDescription = createSyncfileCmdHelp
createSyncfileCmdEpilog = wrapParagraphs('''Example usage:

  bank createSyncfile --syncfile syncfile.wl --cwd .. repo1 repo2 ... repoN

This would create or overwrite the syncfile.wl to record the current states of repo1 repo2 ... repoN which are located
one directory level up.
''')


#  CMD: clone ----------

cloneCmdHelp = 'clone the repos specified in the syncfile'
cloneCmdDescription = cloneCmdHelp
cloneCmdEpilog = wrapParagraphs('''Example usage:

  bank clone --syncfile syncfile.wl

This would perform a git clone for each of the repositories specified in the syncfile
''')


#  CMD: bisect ----------

bisectCmdHelp = 'bisect the syncrepo and sync all repos in the bank to the new state of the syncfile'
bisectCmdDescription = cloneCmdHelp
bisectCmdEpilog = wrapParagraphs('''Example usage:

  bank bisect --syncfile syncfile.wl reset

This would pass the reset to the bisection of the sync-repo.
''')


#  CMD: git ----------

gitCmdHelp = 'perform the given git command in each repo in the bank'
gitCmdDescription = gitCmdHelp
gitCmdEpilog = wrapParagraphs('''Example usage:

  bank git status --syncfile syncfile.wl 

Perform git status and list the results on each of the repositories specified in the syncfile.wl

  bank git tag release_1.7.0.1

Use the syncfile specified in the file bankconfig.ini and apply the command `git tag release_1.7.0.1` to each of the
repos in the bank.
''')


#  CMD: gitall ----------

gitallCmdHelp = 'perform the given git command in each repo in the bank and additionally in the syncrepo'
gitallCmdDescription = gitallCmdHelp
gitallCmdEpilog = wrapParagraphs('''

The common git commands which make sense have been "approved" are
{approved_git_commands}. (Actually any git command can be used but so far only those common git
commands have been "approved" as making sense in the setting of banksync. Some other git commands definitely do not make
sense such as `git rebase --interactive` since the bank command is not interactive. Command completion on the command
line only works for the common commands.

Example usage:

  bank gitall status --syncfile syncfile.wl 

Perform git status and list the results on each of the repositories specified in the syncfile.wl
and in addition to the actual repo containing the sync file (the syncrepo)

  bank gitall tag release_1.7.0.1

Use the syncfile specified in the file bankconfig.ini and apply the command `git tag release_1.7.0.1` to each of the
repos in the bank and in addition to the actual repo containing the sync file (the syncrepo).
''')

def parseArguments():

    parent_parser = argparse.ArgumentParser(add_help=False)                                 
    parent_parser.add_argument("--syncfile", metavar="SYNCFILE", help="the path to the syncfile", default='auto')
    parent_parser.add_argument("--cwd", metavar="CWD", help="prefix / change the working directory for the repos in the sync file", default='auto')
    parent_parser.add_argument("--verbosity", metavar="NUM", help="Specify the level of reported feedback / detail. Acceptable values: 1 (minimal feedback), 2 (some feedback) , 3 (detailed feedback), or 4 (full feedback)", type=int, default=autoNum)
    parent_parser.add_argument('--colorize', metavar='BOOL', help=stringWithVars("Colorize the output: {colorizeOptionValues}"), choices=colorizeOptionValues, default='auto')
    parent_parser.add_argument('--dryrun', dest='dryrun', action='store_true', help="Print what would happen instead of performing the command")
    parent_parser.set_defaults(dryrun=False)

    parser = argparse.ArgumentParser(description=mainDescription, epilog=mainEpilog, formatter_class=argparse.RawDescriptionHelpFormatter, prog='bank')
    parser.add_argument('--version', dest='version', action='store_true', help="Show the version number of the banksync tool and exit")
    parser.set_defaults(version=False)

    subparsers = parser.add_subparsers(title='commands', dest='subparser_name', metavar = '')
    def addSubparser(name):
        return subparsers.add_parser(name, help=eval(name+'CmdHelp'), description=eval(name+'CmdDescription'), epilog=eval(name+'CmdEpilog'), parents = [parent_parser], formatter_class=argparse.RawDescriptionHelpFormatter)
        
    parser_syncCmd = addSubparser('sync')
    parser_syncCmd.add_argument("--matching", metavar="MATCH", help=stringWithVars('specify how we can recognize a revision "match": {matchingOptionValues}'), choices=matchingOptionValues, default='auto')
    parser_recordReposCmd = addSubparser('recordRepos')
    parser_createSyncfileCmd = addSubparser('createSyncfile')
    parser_cloneCmd = addSubparser('clone')
    parser_bisectCmd = addSubparser('bisect')
    parser_gitCmd = addSubparser('git')
    parser_gitCmd.add_argument("gitcmd", metavar="GITCMD", nargs='?', help=stringWithVars("perform one of {approved_git_commands} on all the repos in the bank."), choices=allGitCommands, default='status')
    parser_gitallCmd = addSubparser('gitall')
    parser_gitallCmd.add_argument("gitcmd", metavar="GITCMD", nargs='?', help=stringWithVars("perform one of {approved_git_commands} on all the repos in the bank including the syncrepo."), choices=allGitCommands, default='status')

    argcomplete.autocomplete(parser)

    def printVersionAndExit():
        printWithVars1("banksync {__version__}. Author: Jason F Harris.\nhttps://github.com/jasonfharris/banksync")
        sys.exit(0)

    if len(sys.argv)==1:
        parser.print_help()
        sys.exit(1)

    if len(sys.argv)==2 and sys.argv[1] == '--version':
        printVersionAndExit()

    args, remainingArgs = parser.parse_known_args()
    command = args.subparser_name

    if (not command in commands) and (not command in allGitCommands):
        printWithVars1("unknown command: {command}", 'red')
        sys.exit(1)

    remainingArgs = [correctlyQuoteArg(arg) for arg in remainingArgs]
    if args.version:
        printVersionAndExit()
    
    return args, remainingArgs





# --------------------------------------------------------------------------------------------------------------------------
# command "sync"
# --------------------------------------------------------------------------------------------------------------------------

def commandSync():
    matching = resolvedOpts['sync']['matching']
    checkForSyncRepo(syncFilePath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    allFound = True

    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        repoString = paddedRepoName(repoName, syncDict.keys())
        greenRepoString  = colored(repoString, 'green')
        redRepoString    = colored(repoString, 'red')
        yellowRepoString = colored(repoString, 'yellow')
        if not checkForRepo(repoString, absRepoPath):
            allFound = False
            continue
    
        found = False
        for method in tryOrder:
            if found:
                break

            if (method == "sha") and ("sha" in repoInfo):
                hash = repoInfo["sha"]
                res = gitCommand("git checkout -B {defaultSyncPointBranchName} {hash}", 3, cwd=absRepoPath, verbosity=verbosity)
                if res["code"] == 0:
                    revNum = getRevNumber(hash, absRepoPath)
                    shortHash = hash[0:12]
                    printWithVars2("{greenRepoString}: successfully checked out revision by {method}: {shortHash} (revision number {revNum})")
                    found = True
                    break
                printWithVars3("{repoString}: failed to check out revision by {method}: {hash}")

            if (method == "UnixTimeStamp") and ("UnixTimeStamp" in repoInfo):
                if (matching == 'timestamp') or (matching == 'closetimestamp'):
                    ts = repoInfo["UnixTimeStamp"]
                    date = dateFromTimeStamp(ts)
                    res = gitCommand("git log --all --format=format:'\"%at\" : \"%H\",'", 4, cwd=absRepoPath, raiseOnFailure=True, verbosity=verbosity, permitShowingStdOut=False, permitShowingStdErr=False)
                    shaHash = 0
                    if res["code"] == 0:
                        timestampsToShas = json.loads('{'+res["stdout"][0:-1]+'}')
                        if (ts in timestampsToShas):
                            if (matching == 'timestamp') or (matching == 'closetimestamp'):
                                hash = timestampsToShas[ts]
                                branch=defaultSyncPointBranchName
                                res = gitCommand("git checkout -B {branch} {hash}", 3, cwd=absRepoPath, verbosity=verbosity)
                                if res["code"] == 0:
                                    revNum = getRevNumber(hash, absRepoPath)
                                    printWithVars2("{greenRepoString}: successfully checked out revision by {method}: {ts} ({date}) {hash} (revision number {revNum})")
                                    found = True
                                    break
                        else:
                            if matching == 'closetimestamp':
                                closestTimestamp = min(timestampsToShas, key=lambda x:abs(int(x)-int(ts)))
                                closestDate = dateFromTimeStamp(closestTimestamp)
                                hash = timestampsToShas[closestTimestamp]
                                branch=defaultSyncPointBranchName
                                res = gitCommand("git checkout -B {branch} {hash}", 3, cwd=absRepoPath, verbosity=verbosity)
                                if res["code"] == 0:
                                    revNum = getRevNumber(hash, absRepoPath)
                                    printWithVars2("{yellowRepoString}: warning checking out revision by closest timestamp.", "red")
                                    printWithVars2("       requested {method}: {ts} ({date})")
                                    printWithVars2("       used      {method}: {closestTimestamp} ({closestDate}) {hash} (revision number {revNum})")
                                    found = True
                                    break

                    printWithVars3("{repoString}: failed to check out revision by {method}: {ts} {date}")

        if not found:
            allFound = False
            printWithVars2("{redRepoString}: failed to check out specified revision by any method.")
    if allFound:
        print colored("success! all repos checked out to the specified sync state.", 'green')
    else:
        print colored("failure! not all repos checked out to the specified sync state.", 'red')
        sys.exit(1)



# --------------------------------------------------------------------------------------------------------------------------
# command "recordRepos"
# --------------------------------------------------------------------------------------------------------------------------

def commandRecordRepos():
    checkForSyncRepo(syncFilePath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    newSyncDict = OrderedDict(syncDict)
    anyFailures = False
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        repoString = paddedRepoName(repoName, syncDict.keys())
        greenRepoString = colored(repoString, 'green')
        redRepoString   = colored(repoString, 'red')
        if not checkForRepo(repoString, absRepoPath):
            anyFailures = True
            continue
        (worked, newRepoInfo) = dictFromCurrentRepoState(repoInfo["path"], cwd=cwd, verbosity=verbosity)
        if worked:
            shortHash = newRepoInfo["sha"][0:12]
            date = newRepoInfo["date"]
            printWithVars2("{greenRepoString}: recording bank sync state of {shortHash}, {date}.")
        else:
            printWithVars2("{redRepoString}: failure! not able to get the status of {repoName} at {absRepoPath}", 'red')
            anyFailures = True
        newSyncDict[repoName] = newRepoInfo
    
    writeDictToSyncFile(syncFilePath, newSyncDict)

    if anyFailures:
        printWithVars1("failure! not all constituent repos had their state recorded.", 'red')
        sys.exit(1)
    else:
        printWithVars1("success! all constituent repos had their state recorded.", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# command "createSyncfile"
# --------------------------------------------------------------------------------------------------------------------------

def commandCreateSyncfile():
    checkForSyncRepoDir(syncRepoPath, existing = False)
    newSyncDict = OrderedDict()
    anyFailures = False
    repoNames = remainingArgs
    for repo in repoNames:
        absRepoPath = getAbsRepoPath(repo, cwd)
        repoName = os.path.basename(absRepoPath)
        repoString = paddedRepoName(repoName, repoNames)
        greenRepoString = colored(repoString, 'green')
        if not checkForRepo(repoName, absRepoPath):
            anyFailures = True
            continue
        (worked, newRepoInfo) = dictFromCurrentRepoState(repo, cwd=cwd, verbosity=verbosity)
        if worked:
            shortHash = newRepoInfo["sha"][0:12]
            date = newRepoInfo["date"]
            printWithVars2("{greenRepoString}: recording repository state of {shortHash}, {date}.")
        else:
            printWithVars2("failure! not able to get the status of {repoName} at {absRepoPath}", 'red')
            anyFailures = True
        newSyncDict[repoName] = newRepoInfo

    writeDictToSyncFile(syncFilePath, newSyncDict)

    if anyFailures:
        printWithVars1("failure! not all constituent repos had their state recorded.", 'red')
        sys.exit(1)
    else:
        printWithVars1("success! all constituent repos had their state recorded.", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# command "bisect"
# --------------------------------------------------------------------------------------------------------------------------

def commandBisect():
    currentRev = getCurrentRevHash(syncRepoPath)
    bisectCmd = "git bisect " + " ".join(remainingArgs)
    res = gitCommand(bisectCmd, 2, cwd=syncRepoPath, verbosity=verbosity);
    newRev = getCurrentRevHash(syncRepoPath)
    if newRev != currentRev:
        commandSync()



# --------------------------------------------------------------------------------------------------------------------------
# command "clone"
# --------------------------------------------------------------------------------------------------------------------------

def commandClone():
    checkForSyncRepo(syncFilePath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    anyFailures = False

    opts = {'captureStdOutStdErr':False, 'verbosity':verbosity}
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        repoString = paddedRepoName(repoName, syncDict.keys())
        greenRepoString = colored(repoString, 'green')
        redRepoString   = colored(repoString, 'red')
        if not "cloneURL" in repoInfo:
            anyFailures = True
            printWithVars2("{repoString}: there is no cloneURL for this repo", "red")
            continue   
        cloneURL = repoInfo["cloneURL"]
        name = os.path.basename(absRepoPath)
        dir  = os.path.dirname(absRepoPath)
        opts['cwd'] = dir
        execute3("mkdir -p {dir}")
        res = gitCommand("git clone {cloneURL} {name}", 3, **opts)
        if res['code'] == 0:
            printWithVars2("{greenRepoString}: cloned repo to {absRepoPath}")
        else:
            anyFailures = True
            printWithVars2("{redRepoString}: error cloning repo to {absRepoPath}")

    if anyFailures:
        print colored("failure! not all repos cloned.", 'red')
        sys.exit(1)

    print colored("success! all repos cloned.", 'green')
    commandSync()



# --------------------------------------------------------------------------------------------------------------------------
# a git command
# --------------------------------------------------------------------------------------------------------------------------

def distributeGitCommand(command, includeSyncRepo=False):
    if not command in approved_git_commands:
        yellowWarning = colored("warning", 'yellow')
        printWithVars1("{yellowWarning}: the git command `{command}` might not make sense being applied non-interactively to each repo in the bank. Use at your own discretion.")
    if not command in allGitCommands:
        printWithVars1("failure! unknown git command `{command}`", 'red')

    gitCmd = "git " + command + " " + " ".join(remainingArgs)
    gitCmd = gitCmd.strip()
    checkForSyncRepoDir(syncRepoPath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    anyFailures = False
    opts = {'captureStdOutStdErr':False, 'verbosity':verbosity}
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        if not checkForRepo(repoName, absRepoPath):
            anyFailures = True
            continue
        opts['cwd'] = absRepoPath
        gitCommand(gitCmd, 2, **opts);
    if includeSyncRepo:
        opts['cwd'] = syncRepoPath
        gitCommand(gitCmd, 2, **opts);

    if anyFailures:
        printWithVars1("failure! not all constituent repos present.", 'red')
        sys.exit(1)
    else:
        printWithVars1("all constituent repos issued git command '{gitCmd}'", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# dispatch command
# --------------------------------------------------------------------------------------------------------------------------

def dispatchCommand(command):
    if command == "sync":
        commandSync()
    if command == "clone":
        commandClone()
    if command == "recordRepos":
        commandRecordRepos()
    if command == "createSyncfile":
        commandCreateSyncfile()
    if command == "bisect":
        commandBisect()
    if command == "git":
        distributeGitCommand(args.gitcmd, False)
    if command == "gitall":
        distributeGitCommand(args.gitcmd, True)



# --------------------------------------------------------------------------------------------------------------------------
# Extract and clean the argument parameters
# --------------------------------------------------------------------------------------------------------------------------

def getResolvedOptions(args):
    
    bankOptions = dict(defaultOptions)
    if os.path.isfile('~/.bankconfigrc'):
        newOptions = getOptionDictFromIniFile('~/.bankconfigrc')
        bankOptions = mergeOptionDicts(bankOptions, newOptions)

    # Get the config file path
    if getattr(args, 'cwd', 'auto') != 'auto':
        configFile = os.path.abspath(os.path.join(args.cwd, 'bankconfig.ini'))
    else:
        configFile = os.path.abspath('bankconfig.ini')    
    if os.path.isfile(configFile):
        newOptions = getOptionDictFromIniFile(configFile)
        bankOptions = mergeOptionDicts(bankOptions, newOptions)

    passedInOptions = {
        'General' : {
            'cwd' : getattr(args, 'cwd', 'auto'),
            'syncfile' : getattr(args, 'syncfile', 'auto'),
            'verbosity' : getattr(args, 'verbosity', autoNum),
            'colorize' :  getattr(args, 'colorize', 'auto'),
        },
        'sync' : {
            'matching' : getattr(args, 'matching', 'auto')
        }
    }
    
    bankOptions = mergeOptionDicts(bankOptions, passedInOptions)
    
    # normalize non-string options
    bankOptions['General']['verbosity'] = int(bankOptions['General']['verbosity'])
    bankOptions['General']['colorize'] = True if (bankOptions['General']['colorize'].lower() in ['yes','true']) else False

    return bankOptions


def main():
    global args, remainingArgs, syncFilePath, syncRepoPath, cwd, verbosity, resolvedOpts
    args, remainingArgs = parseArguments()

    command = args.subparser_name
    resolvedOpts = getResolvedOptions(args)
    cwd = resolvedOpts['General']['cwd']
    verbosity = resolvedOpts['General']['verbosity']
    colorize = resolvedOpts['General']['colorize']
    syncFilePath = resolvedOpts['General']['syncfile']
    syncRepoPath = os.path.dirname(os.path.abspath(syncFilePath))
    set_defaults('verbosity', verbosity)
    set_defaults('dryrun', args.dryrun)
    set_defaults('colorize', colorize)
    
    dispatchCommand(command)


if __name__ == '__main__':
    main()