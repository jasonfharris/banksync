#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import os.path
import sys
import shutil
import tempfile
import re
import glob
import json
import subprocess
from sysexecute import *
import datetime
import configparser
import textwrap
from urllib.parse import urlsplit



# --------------------------------------------------------------------------------------------------------------------------
# Defines
# --------------------------------------------------------------------------------------------------------------------------

autoNum = -1       # an arbitrary negative number to stand in for 'auto' in a numerical option



# --------------------------------------------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------------------------------------------

def multipleReplace(mapping, text):
    """Replace multiple substrings in 'text' according to the given 'mapping' dictionary."""
    regex = re.compile(f'({"|".join(map(re.escape, mapping.keys()))})') # type: ignore
    return regex.sub(lambda mo: mapping[mo.string[mo.start():mo.end()]], text)

def dateFromTimestamp(ts):
    """Convert a Unix timestamp 'ts' to a formatted date string."""
    return datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')

def isSha1Str(s):
    """Check if the given string 's' is a valid SHA-1 hash."""
    return bool(re.match(r'^[0-9a-fA-F]{40}$', s))

def correctlyQuoteArg(arg):
    """Quote the input 'arg' if it contains whitespace characters."""
    return f'"{arg}"' if re.match(r'.*\s+.*', arg) else arg

def wrapParagraphs(text):
    """Wrap the paragraphs of a given 'text' to fit within an 80-character width."""
    paras = text.split('\n\n')
    wrappedParas = [textwrap.fill(para, 80) for para in paras]
    return "\n\n".join(wrappedParas)

def escapeAnsi(line):
    """Remove ANSI escape codes from the input 'line'."""
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
    return ansi_escape.sub('', line)


def nestedGet(data, keys, default=None):
    """Retrieve a nested value from a dictionary using a list of keys."""
    for key in keys:
        if not (isinstance(data, dict) and key in data):
            return default
        data = data[key]
    return data


def prettyPrintDictionary(d, indent=0, indentStep=4):
    """Pretty print a dictionary as simple keys and values, with support for nested dictionaries."""
    maxKeyLength = 0
    maxValueLength = 0

    for key, value in d.items():
        maxKeyLength = max(maxKeyLength, len(key))
        if isinstance(value, dict):
            maxValueLength = max(maxValueLength, max(len(str(k)) for k in value.keys()))
        else:
            maxValueLength = max(maxValueLength, len(str(value)))

    for key in sorted(d.keys()):
        value = d[key]
        keySpecifier = f">{indent + maxKeyLength}"
        valueSpecifier = f"<{maxValueLength}"
        if isinstance(value, dict):
            print(f"{key:{keySpecifier}} :")
            prettyPrintDictionary(value, indent + indentStep, indentStep)
        else:
            valueStr = str(value)
            print(f"{key:{keySpecifier}} : {valueStr:{valueSpecifier}}")


# --------------------------------------------------------------------------------------------------------------------------
# Version number handling
# --------------------------------------------------------------------------------------------------------------------------

# versionLessOrEqual checks if one version number is less than or equal to another version number, considering
# both major and minor version parts.
def versionLessOrEqual(version1: str, version2: str):
    parts1 = version1.split('.')
    parts2 = version2.split('.')

    # Pad the parts with zeros if one version has more parts than the other
    while len(parts1) < len(parts2):
        parts1.append('0')
    while len(parts2) < len(parts1):
        parts2.append('0')

    for part1, part2 in zip(parts1, parts2):
        if int(part1) < int(part2):
            return True
        elif int(part1) > int(part2):
            return False

    return True  # Both versions are equal


# --------------------------------------------------------------------------------------------------------------------------
# INI Config Handling
# --------------------------------------------------------------------------------------------------------------------------

def isAutomatic(val):
    return val == "auto" or val == autoNum or val is None

def iniParserToOptionDict(parser):
    return {sec: {key: parser[sec][key] for key in parser[sec]} for sec in parser}

def getOptionDictFromIniFile(configFile):
    config = configparser.ConfigParser()
    config.read(configFile)
    return iniParserToOptionDict(config)

def flattenDict(d, parentKeys=[]):
    items = {}
    for k, v in d.items():
        newKeys = parentKeys + [k.lower()]
        if isinstance(v, dict):
            items.update(flattenDict(v, newKeys))
        else:
            items['.'.join(newKeys)] = v
    return items


def mergeOptionDicts(d1,d2):
    """Merge in dict d2 into a copy of d1. Don't overwrite values when the value is 'none'"""
    combined = dict(d1)
    for key, val in d2.items():
        if not isAutomatic(val):
            combined[key] = val
    return combined




# --------------------------------------------------------------------------------------------------------------------------
# Repo Checking
# --------------------------------------------------------------------------------------------------------------------------

def paddedRepoName(repoName, names):
    maxRepoNameLength = 0                     # maxRepoNameLength
    for name in names:
        maxRepoNameLength = max(maxRepoNameLength, len(name))
    return repoName.ljust(maxRepoNameLength)

def checkForRepo(repoString, repoAbsPath):
    if not os.path.isdir(repoAbsPath):
        printWithVars1(f"{repoString} : there is no repository at {repoAbsPath}.", 'red')
        return False
    if not isGitWorkingTreeDir(repoAbsPath):
        printWithVars1(f"{repoString} : {repoAbsPath} is not a git repository.", 'red')
        return False
    return True

def checkForSyncRepoFile(syncFileAbsPath):
    if not os.path.isfile(syncFileAbsPath):
        printWithVars1(f"failure! could not locate the sync file at {syncFileAbsPath}.", 'red')
        sys.exit(1)

def isGitWorkingTreeDir(absPath):
    if not os.path.isdir(absPath):
        return False

    process = subprocess.Popen(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=absPath,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, _ = process.communicate()
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors="replace")

    if process.returncode != 0:
        return False

    return os.path.abspath(stdout.strip()) == os.path.abspath(absPath)


def checkForSyncRepoDir(syncFileAbsPath, existing = True):
    syncRepoAbsPath = os.path.dirname(syncFileAbsPath)
    if not os.path.isdir(syncRepoAbsPath):
        printWithVars1(f"failure! could not locate the syncrepo dir at {syncRepoAbsPath}.", 'red')
        sys.exit(1)

    if not isGitWorkingTreeDir(syncRepoAbsPath):
        if existing:
            printWithVars1(f"failure! {syncRepoAbsPath} is not a git repository consisting of syncfile revisions.", 'red')
        else:
            printWithVars1(f"failure! {syncRepoAbsPath} is not a git repository.", 'red')
        sys.exit(1)

def checkForSyncRepoAndSyncFile(syncFileAbsPath):
    checkForSyncRepoFile(syncFileAbsPath)
    checkForSyncRepoDir(syncFileAbsPath)



# --------------------------------------------------------------------------------------------------------------------------
# Repo Operations
# --------------------------------------------------------------------------------------------------------------------------

def gitCommand(cmdStr, verbosityThreshold=3, **kwargs):
    """Execute a git command and return the result."""
    defaultOpts = {
        'cwd': '.',
        'captureStdOutStdErr': True,
        'permitShowingStdErr': True,
        'permitShowingStdOut': True,
        'ignoreErrors': True,
        'raiseOnFailure': False,
        'verbosity': 3
    }
    opts = merge(defaultOpts,kwargs)
    (code, sout, serr) = execute(cmdStr, verbosityThreshold, **opts)
    res = {'code': code, 'stdout': sout, 'stderr': serr}
    if opts['raiseOnFailure'] and code != 0:
        raise Exception(f"Bad git result {res}")
    return res

def getRevNumber(repoAbsPath):
    """Return the revision number of the repository at the given path."""
    res = gitCommand("git rev-list HEAD --count --first-parent", 4, cwd=repoAbsPath)
    try:
        num = int(res["stdout"].strip())
        return str(num)
    except:
        return "(unknown)"

def getCurrentRevHash(repoAbsPath):
    """Return the current revision hash of the repository at the given path."""
    res = gitCommand("git log HEAD -n 1 --date=iso --format=format:'%H'", 4, cwd=repoAbsPath, verbosity=1)
    if isSha1Str(res['stdout']):
        return res['stdout']
    return '0'*40

def getBranchName(repoAbsPath):
    """Return the current branch name of the repository at the given path."""
    res = gitCommand("git rev-parse --abbrev-ref HEAD", 4, cwd=repoAbsPath, verbosity=1)
    return res['stdout'].strip()

def getRemoteNames(repoAbsPath):
    """Return the configured remote names for the repository at the given path."""
    res = gitCommand("git remote", 4, cwd=repoAbsPath, verbosity=1)
    return [remote.strip() for remote in res['stdout'].splitlines() if remote.strip()]

def getDefaultRemoteName(repoAbsPath):
    """Return origin if configured, otherwise the first configured remote."""
    remotes = getRemoteNames(repoAbsPath)
    if 'origin' in remotes:
        return 'origin'
    return remotes[0] if remotes else None

def getRemoteHeadBranchName(repoAbsPath, remoteName):
    """Return the branch name referenced by refs/remotes/<remoteName>/HEAD."""
    res = gitCommand(f"git symbolic-ref --quiet --short refs/remotes/{remoteName}/HEAD", 4, cwd=repoAbsPath, verbosity=1)
    remoteHead = res['stdout'].strip()
    prefix = f"{remoteName}/"
    if remoteHead.startswith(prefix):
        return remoteHead[len(prefix):]
    return None

def hasLocalBranch(repoAbsPath, branchName):
    """Return whether the repository has a local branch with the given name."""
    res = gitCommand(f"git show-ref --verify --quiet refs/heads/{branchName}", 4, cwd=repoAbsPath, verbosity=1)
    return res['code'] == 0

def hasRemoteBranch(repoAbsPath, remoteName, branchName):
    """Return whether the repository has a remote-tracking branch with the given name."""
    res = gitCommand(f"git show-ref --verify --quiet refs/remotes/{remoteName}/{branchName}", 4, cwd=repoAbsPath, verbosity=1)
    return res['code'] == 0

def getDefaultPullBranch(repoAbsPath, remoteName):
    """Return a default branch suitable for pulling while detached, if one exists."""
    remoteHeadBranch = getRemoteHeadBranchName(repoAbsPath, remoteName)
    if remoteHeadBranch and hasRemoteBranch(repoAbsPath, remoteName, remoteHeadBranch):
        return remoteHeadBranch

    for branchName in ['main', 'master']:
        if hasRemoteBranch(repoAbsPath, remoteName, branchName):
            return branchName

    for branchName in ['main', 'master']:
        if hasLocalBranch(repoAbsPath, branchName):
            return branchName

    return None

def gitPullCommandForRepo(repoAbsPath, remainingArgs):
    """Return the git pull command to run for this repo.

    Bare `git pull` fails in detached HEAD because Git has no branch config to
    consult. In that case, pull from the repository's default main/master
    branch explicitly.
    """
    if remainingArgs:
        return "git pull " + " ".join(remainingArgs)

    if getBranchName(repoAbsPath) != 'HEAD':
        return "git pull"

    remoteName = getDefaultRemoteName(repoAbsPath)
    if not remoteName:
        return "git pull"

    branchName = getDefaultPullBranch(repoAbsPath, remoteName)
    if not branchName:
        return "git pull"

    return f"git pull {remoteName} {branchName}"

def getModifiedCount(repoAbsPath):
    """Return the count of modified files in the repository at the given path."""
    res = gitCommand("git ls-files --modified --exclude-standard --directory", 4, cwd=repoAbsPath, verbosity=1)
    ans = res['stdout'].strip()
    if not ans:
        return 0
    return len(ans.split('\n'))

def getStagedCount(repoAbsPath):
    """Return the count of staged files in the repository at the given path."""
    res = gitCommand("git diff --name-only --cached", 4, cwd=repoAbsPath, verbosity=1)
    ans = res['stdout'].strip()
    if not ans:
        return 0
    return len(ans.split('\n'))

def getShaForBranchName(repoAbsPath: str, branchName: str):
    """Return the SHA-1 hash for the given branch name in the repository at the given path or None if not found."""
    res = gitCommand(f"git rev-parse {branchName}", 4, cwd=repoAbsPath, verbosity=1)
    ans = res['stdout'].strip()
    return ans if isSha1Str(ans) else None


# --------------------------------------------------------------------------------------------------------------------------
# URL helpers
# --------------------------------------------------------------------------------------------------------------------------

def getUniqueDirName(baseDirName):
    """Generate a unique directory name by appending an incremented number to the base name."""
    i = 1
    newDirName = baseDirName
    while os.path.exists(newDirName):
        newDirName = f"{baseDirName}_{i}"
        i += 1
    return newDirName


def getRepoNameFromUrl(url):
    """Extract the repository name from a given URL."""
    urlParts = urlsplit(url)
    repoNameWithExt = os.path.basename(urlParts.path)
    repoName, ext = os.path.splitext(repoNameWithExt)

    # Remove sync_repo, syncRepo, or SyncRepo from the repo name
    repoName = re.sub(r"(?:_?sync_repo|_?syncRepo|_?SyncRepo)$", "", repoName)

    # Get the last component in the path with an ASCII char in it
    pathParts = re.split(r'[/]+', repoName)
    for item in reversed(pathParts):
        if any(char.isascii() and char.isalnum() for char in item):
            return item.strip('_')

    return getUniqueDirName('WrapperProject')


def isValidGitUrl(url):
    """Check if the given 'url' has a valid Git URL format or is a local file path."""
    gitUrlPattern = re.compile(
        r"(?:(?:https?|git|ssh|rsync)://|(?:(?:(?:[^@]+@)?[^:/]+)[:]))"  # Protocol or user@host
        r"(?:[^/]+/)+"  # At least one-level of subdirectories
        r"[^/]+(?:\.git)?$"  # Repository name, with an optional .git extension
    )

    return gitUrlPattern.match(url) or os.path.exists(url)



# --------------------------------------------------------------------------------------------------------------------------
# path operations
# --------------------------------------------------------------------------------------------------------------------------

def isFilenameWithoutPath(filename):
    return not bool(os.path.dirname(filename))

def moveDirectory(srcDir, destDir):
    """Move a directory to a new location, using a temporary directory to avoid issues with moving into a subdirectory."""
    if not os.path.exists(srcDir):
        raise ValueError(f"Source directory {srcDir} does not exist")

    if os.path.exists(destDir):
        raise ValueError(f"Destination directory {destDir} already exists")

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tempDir:
        # Move the source directory to the temporary directory
        tempSrcDir = os.path.join(tempDir, os.path.basename(srcDir))
        shutil.move(srcDir, tempSrcDir)

        # Move the temporary source directory to the destination directory
        shutil.move(tempSrcDir, destDir)


def getSyncFileInDir(srcDir):
   pattern = os.path.join(srcDir, 'syncfile.*')
   matching_files = glob.glob(pattern)

   if matching_files:
      return matching_files[0]
   return None  # Or set a default value if necessary


# --------------------------------------------------------------------------------------------------------------------------
# bank bisect helpers
# --------------------------------------------------------------------------------------------------------------------------

# Given the current branch is say "bobby" then return "bobby", or else if we are in a detached head
# state then return something like "39b2f210afb38cb43dc6387cb7096ad4aa70cc3a"

def getCurrentBranchOrHash(repoAbsPath):
    try:
        res = gitCommand("git branch", 3, cwd=repoAbsPath, verbosity=1, ignoreErrors=False)
        m = re.search(r'^\* \(HEAD detached at.*', res["stdout"], re.MULTILINE)
        if m:
            return getCurrentRevHash(repoAbsPath)
        m = re.search(r'^\* (.*)$', res["stdout"], re.MULTILINE)
        if m:
            return m.group(1)
    except:
        pass
    raise Exception("Invalid Branch")



# --------------------------------------------------------------------------------------------------------------------------
# Dictionary Operations
# --------------------------------------------------------------------------------------------------------------------------

def writeBisectRestoreToJson(syncRepoAbsPath, restoreDict):
    newFileContents = json.dumps(restoreDict, indent=4)
    bisectRestoreAbsPath = os.path.join(syncRepoAbsPath, '.bisectRestore')
    with open(bisectRestoreAbsPath, 'w') as f:
        f.write(newFileContents)

def loadBisectRestoreFromJson(syncFileAbsPath):
    syncRepoAbsPath = os.path.dirname(syncFileAbsPath)
    bisectRestoreAbsPath = os.path.join(syncRepoAbsPath, '.bisectRestore')
    if not os.path.exists(bisectRestoreAbsPath):
        return None
    with open(bisectRestoreAbsPath) as f:
        jsonTxt = f.read()
        restoreDict = json.loads(jsonTxt)
        return restoreDict if restoreDict else {}

def removeBisectRestoreFile(syncRepoAbsPath):
    bisectRestoreAbsPath = os.path.join(syncRepoAbsPath, '.bisectRestore')
    os.remove(bisectRestoreAbsPath)

def loadSyncFileAsDict(syncFilePath):
    syncFileAbsPath = os.path.abspath(syncFilePath)
    checkForSyncRepoAndSyncFile(syncFileAbsPath)
    with open(syncFileAbsPath) as f:
        jsonTxt = f.read()
        syncInfo = json.loads(jsonTxt)
        if not syncInfo:
            printWithVars1(f"failure! no repos where specified in the sync file at {syncFileAbsPath}.", 'red')
            sys.exit(1)
        return syncInfo

def repositories(syncInfo: dict):
    return syncInfo['repositories'] if 'repositories' in syncInfo else syncInfo # backwards compatibility 

def relativePathToRepositories(syncInfo):
    if 'configuration' in syncInfo:
        if 'relativePathToRepositories' in syncInfo['configuration']:
            return syncInfo['configuration']['relativePathToRepositories']
    return ".." # backwards compatibility

def writeDictToSyncFile(syncFilePath, dict):
    newFileContents = json.dumps(dict, indent=4)
    path = os.path.abspath(syncFilePath)
    with open(path, 'w') as f:
        f.write(newFileContents)
    printWithVars3(f"Wrote new dictionary of bank sync information to {path}")


def dictFromCurrentRepoState(repoPath, repoAbsPath, **kwargs):
    opts = merge({'verbosity': 3, 'raiseOnFailure': True}, kwargs)
    opts['cwd'] = repoAbsPath
    newRepoInfo = {'path': repoPath}
    succeeded = True
    try:
        res = gitCommand("git log HEAD -n 1 --date=iso --format=format:'\"sha\" : \"%H\",%n\"UnixTimeStamp\" : \"%at\",%n\"date\" : \"%ad\",%n\"author\" : \"%an\"'", **opts)
        props = json.loads('{'+res["stdout"]+'}')
        newRepoInfo.update(props)

        res = gitCommand("git rev-parse --abbrev-ref HEAD", **opts)
        newRepoInfo["branch"] = res["stdout"].strip()

        res = gitCommand("git rev-list HEAD --count --first-parent", **opts)
        newRepoInfo["revisionNumber"] = res["stdout"].strip()

        res = gitCommand("git log HEAD -n 1 --format=format:\"%B\"", **opts)
        sanitizedMessage = res["stdout"].strip().replace("\"","'").replace("\n","\\n")
        newRepoInfo["message"] = sanitizedMessage

        res = gitCommand("git remote --verbose", **opts)
        cloneURL = ''
        if not cloneURL:
            m = re.search(r'origin\s*(\S+) \(fetch\)', res["stdout"])
            if m:
                cloneURL = m.group(1)
        if not cloneURL:
            m = re.search(r'(\w+)\s*(\S+) \(fetch\)', res["stdout"])
            if m:
                cloneURL = m.group(1)
        if cloneURL:
            newRepoInfo["cloneURL"] = cloneURL.strip()
    except:
        succeeded = False

    return (succeeded, newRepoInfo)
