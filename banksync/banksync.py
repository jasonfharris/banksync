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

__version__ = "0.7.1"


# --------------------------------------------------------------------------------------------------------------------------
# Defines
# --------------------------------------------------------------------------------------------------------------------------

tryOrder = ["sha", "UnixTimeStamp"]
defaultSyncPointBranchName = "syncPoint"



# --------------------------------------------------------------------------------------------------------------------------
# Parse the arguments
# --------------------------------------------------------------------------------------------------------------------------

sync_commands = ['sync', 'createSyncPoint', 'generateSyncFile', 'bisect', 'clone']
git_commands = ['gitclone', 'gitreset', 'gitlog', 'gitstatus', 'gitbranch', 'gitcheckout', 'gitcommit', 'gitdiff', 'gitfecth', 'gitpush', 'gitpull', 'gitprune', 'gitgc', 'gitfsck']
commands = sync_commands + git_commands
matchingOpts = ['shaOnly', 'timestamp', 'closetimestamp']



mainDescription = 'execute operations across a collection of git repositories.'
bodyDescription = stringWithVars(
'''Utility to checkout or create a synchronized state across a collection of
repositories. This utility works on a syncfile. It is a more general way to
handle sub-repositories / submodules. It is intended to be less brittle than
traditional ways to specify submodules by allowing some looseness / decoupling.

It can also be used to issue a normal git command to every repository specified in the syncfile.
Current git commands allowed are {git_commands} (although adding others is a quick script change)

The options, eg the --syncfile option and the --cwd  option, can be specified in a standard ini
config file `bankconfig.ini` so they do not need to be specified each time on the command line.

Example usage:

  bank sync --syncfile syncfile.wl

This would checkout / update the repos given in the syncfile to the states given in the syncfile.

  bank sync --syncfile syncfile.wl --cwd ../other/dir

This would checkout / update the repos given in the syncfile to the states given in the syncfile
(but the path to the repos are prefixed by the value of cwd).

  bank createSyncPoint --syncfile syncfile.wl

This would alter the revisions stored in the syncfile.wl to match the current revisions of the referenced repositories.

  bank generateSyncFile --syncfile syncfile.wl repo1 repo2 ... repoN

This would generate or overwrite the syncfile.wl to contain sync points for the current states of repo1 repo2 ... repoN

  bank gitstatus --syncfile syncfile.wl

Perform gitstatus and list the results on each of the repositories specified in the syncfile.wl

  bank sync

Use the syncfile specified in the  and list the results on each of the repositories specified in the syncfile.wl
''')

bodyDescription = wrapParagraphs(bodyDescription)

def parseArguments():
    parser = argparse.ArgumentParser(description=mainDescription, epilog=bodyDescription, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", metavar="ACTION", nargs='?', help=stringWithVars("perform one of {sync_commands} on a syncfile, or one of {git_commands} on all the repos in the bank."), choices=commands, default='gitstatus')
    parser.add_argument("--syncfile", metavar="SYNCFILE", help="the path to the syncfile", default='Automatic')
    parser.add_argument("--cwd", metavar="CWD", help="prefix / change the working directory for the repos in the sync file", default="Automatic")
    parser.add_argument("--matching", metavar="MATCH", help=stringWithVars('specify how we can recognize a revision "match": {matchingOpts}'), choices=matchingOpts, default="Automatic")
    parser.add_argument("--verbosity", metavar="NUM", help="Specify the level of feedback detail for the install", type=int, default=AutomaticNum)
    parser.add_argument('--dryRun',dest='dryRun',action='store_true', help="Print what would happen instead of executing the deploy")
    parser.add_argument('--version',dest='version',action='store_true', help="Show the version number of the banksync tool")
    parser.set_defaults(dryrun=False)
    parser.set_defaults(version=False)
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
    remainingArgs = [correctlyQuoteArg(arg) for arg in remainingArgs]
    if args.version:
        printVersionAndExit()
    
    return args, remainingArgs





# --------------------------------------------------------------------------------------------------------------------------
# command "sync"
# --------------------------------------------------------------------------------------------------------------------------

def commandSync():
    checkForSyncRepo(syncFilePath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    allFound = True

    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        repoString = paddedRepoName(repoName,syncDict)
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
# command "createSyncPoint"
# --------------------------------------------------------------------------------------------------------------------------

def commandSyncCreateSyncPoint():
    checkForSyncRepo(syncFilePath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    newSyncDict = OrderedDict(syncDict)
    anyFailures = False
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        repoString = paddedRepoName(repoName,syncDict)
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
# command "generateSyncFile"
# --------------------------------------------------------------------------------------------------------------------------

def commandGenerateSyncFile():
    checkForSyncRepoDir(syncFilePath, existing = False)
    newSyncDict = OrderedDict()
    anyFailures = False
    for repo in remainingArgs:
        absRepoPath = getAbsRepoPath(repo, cwd)
        repoName = os.path.basename(absRepoPath)
        if not checkForRepo(repoName, absRepoPath):
            anyFailures = True
            continue
        (worked, newRepoInfo) = dictFromCurrentRepoState(repo, cwd=cwd, verbosity=verbosity)
        if worked:
            shortHash = newRepoInfo["sha"][0:12]
            date = newRepoInfo["date"]
            printWithVars2("{repoName}: recording repository state of {shortHash}, {date}.")
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
    bisectCmd = "git bisect " + " ".join(remainingArgs)
    res = gitCommand(bisectCmd, 2, cwd=syncRepoPath, verbosity=verbosity);
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
        repoString = paddedRepoName(repoName,syncDict)
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

def distributeGitCommand(command):
    cmd = command[3:]
    gitCmd = "git " + command[3:] + " " + " ".join(remainingArgs)
    gitCmd = gitCmd.strip()
    checkForSyncRepoDir(syncFilePath)
    syncDict = loadSyncFileAsDict(syncFilePath)
    anyFailures = False
    for repoName in syncDict:
        repoInfo = syncDict[repoName]
        absRepoPath = getAbsRepoPath(repoInfo["path"], cwd)
        if not checkForRepo(repoName, absRepoPath):
            anyFailures = True
            continue
        res = gitCommand(gitCmd, 2, cwd=absRepoPath, verbosity=verbosity);
    if anyFailures:
        printWithVars1("failure! not all constituent repos present.", 'red')
        sys.exit(1)
    else:
        printWithVars1("all constituent repos issued git command '{gitCmd}'", 'green')



# --------------------------------------------------------------------------------------------------------------------------
# dispatch command
# --------------------------------------------------------------------------------------------------------------------------

def dispatchCommand(command):
    #from pudb import set_trace; set_trace()
    if command == "sync":
        commandSync()
    if command == "clone":
        commandClone()
    if command == "createSyncPoint":
        commandSyncCreateSyncPoint()
    if command == "generateSyncFile":
        commandGenerateSyncFile()
    if command == "bisect":
        commandBisect()
    if command in git_commands:
        distributeGitCommand(command)



# --------------------------------------------------------------------------------------------------------------------------
# Extract and clean the argument parameters
# --------------------------------------------------------------------------------------------------------------------------

def main():
    global remainingArgs, syncFilePath, syncRepoPath, cwd, matching, verbosity
    args, remainingArgs = parseArguments()

    # Get the config file path
    if args.cwd != "Automatic":
        configFile = os.path.abspath(os.path.join(args.cwd, 'bankconfig.ini'))
    else:
        configFile = os.path.abspath('bankconfig.ini')

    command = args.command
    syncFilePath = getSetting(args.syncfile, configFile, 'syncfile', 'syncfile.wl')
    syncRepoPath = os.path.dirname(os.path.abspath(syncFilePath))
    cwd = getSetting(args.cwd, configFile, 'cwd', '.')
    matching = getSetting(args.matching, configFile, 'matching', 'closetimestamp')
    verbosity= getSetting(args.verbosity, configFile, 'verbosity', 2)
    set_defaults('verbosity', verbosity)
    set_defaults('dryRun', args.dryRun)

    dispatchCommand(command)


if __name__ == '__main__':
    main()