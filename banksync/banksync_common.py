#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import os.path
import sys
import shutil
import tempfile
import re
import glob
import json
from collections import OrderedDict
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
    regex = re.compile("(%s)" % "|".join(map(re.escape, mapping.keys())))
    return regex.sub(lambda mo: mapping[mo.string[mo.start():mo.end()]], text)

def dateFromTimestamp(ts):
    """Convert a Unix timestamp 'ts' to a formatted date string."""
    return datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')

def isSha1Str(s):
    """Check if the given string 's' is a valid SHA-1 hash."""
    return True if re.match(r'^[0-9a-fA-F]{40}$', s) else False

def correctlyQuoteArg(arg):
    """Quote the input 'arg' if it contains whitespace characters."""
    m = re.match(r'.*\s+.*', arg)
    if m:
        return '"{}"'.format(arg)
    return arg

def wrapParagraphs(text):
    """Wrap the paragraphs of a given 'text' to fit within an 80-character width."""
    paras = text.split('\n\n')
    wrappedParas = [textwrap.fill(para, 80) for para in paras]
    return "\n\n".join(wrappedParas)

def escapeAnsi(line):
    """Remove ANSI escape codes from the input 'line'."""
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
    return ansi_escape.sub('', line)



# --------------------------------------------------------------------------------------------------------------------------
# INI Config Handling
# --------------------------------------------------------------------------------------------------------------------------

def isAutomatic(val):
    return val == "auto" or val == autoNum or val is None

def iniParserToOptionDict(parser):
    d = {}
    for sec in parser:
        secd = {}
        for key in parser[sec]:
            secd[key]= parser[sec][key]
        d[sec] = secd
    return d

def getOptionDictFromIniFile(configFile):
    config = configparser.ConfigParser()
    config.read(configFile)
    return iniParserToOptionDict(config)

def mergeOptionDicts(d1,d2):
    """Merge in ini d2 into a copy of d1. Don't overwrite values when the value is 'none'"""
    combined = dict(d1)
    for sec in d2:
        for key in d2[sec]:
            val = d2[sec][key]
            if not isAutomatic(val):
                if sec in combined:
                    combined[sec][key] = val
                else:
                    combined[sec] = {key:val}
    return combined




# --------------------------------------------------------------------------------------------------------------------------
# Repo Checking
# --------------------------------------------------------------------------------------------------------------------------

def getAbsRepoPath(path, cwd = "."):
    if cwd == ".":
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(cwd, path))

def paddedRepoName(repoName, names):
    maxRepoNameLength = 0                     # maxRepoNameLength
    for name in names:
        maxRepoNameLength = max(maxRepoNameLength, len(name))
    return repoName.ljust(maxRepoNameLength)

def checkForRepo(repoString, absRepoPath):
    if not os.path.isdir(absRepoPath):
        printWithVars1("{repoString} : there is no repository at {absRepoPath}.", 'red')
        return False
    if not os.path.isdir(os.path.join(absRepoPath,".git")):
        printWithVars1("{repoString} : {absRepoPath} is not a git repository.", 'red')
        return False
    return True

def checkForSyncRepoFile(syncFilePath):
    if not os.path.isfile(syncFilePath):
        absSyncFilePath = os.path.abspath(syncFilePath)
        printWithVars1("failure! could not locate the sync file at {absSyncFilePath}.", 'red')
        sys.exit(1)

def checkForSyncRepoDir(syncRepoPath, existing = True):
    absSyncRepoPath = os.path.abspath(syncRepoPath)

    if not os.path.isdir(absSyncRepoPath):
        printWithVars1("failure! could not locate the syncrepo dir at {absSyncRepoPath}.", 'red')
        sys.exit(1)

    if not os.path.isdir(os.path.join(absSyncRepoPath,".git")):
        if existing:
            printWithVars1("failure! {absSyncRepoPath} is not a git repository consisting of syncfile revisions.", 'red')
        else:
            printWithVars1("failure! {absSyncRepoPath} is not a git repository.", 'red')        
        sys.exit(1)

def checkForSyncRepo(syncFilePath):
    absSyncFilePath = os.path.abspath(syncFilePath)
    absSyncRepoPath = os.path.dirname(absSyncFilePath)
    checkForSyncRepoFile(absSyncFilePath)
    checkForSyncRepoDir(absSyncRepoPath)



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

def getRevNumber(absRepoPath):
    """Return the revision number of the repository at the given path."""
    res = gitCommand("git rev-list HEAD --count --first-parent", 4, cwd=absRepoPath)
    try:
        num = int(res["stdout"].strip())
        return str(num)
    except:
        return "(unknown)"

def getCurrentRevHash(absRepoPath):
    """Return the current revision hash of the repository at the given path."""
    res = gitCommand("git log HEAD -n 1 --date=iso --format=format:'%H'", 4, cwd=absRepoPath, verbosity=1)
    if isSha1Str(res['stdout']):
        return res['stdout']
    return '0'*40

def getBranchName(absRepoPath):
    """Return the current branch name of the repository at the given path."""
    res = gitCommand("git rev-parse --abbrev-ref HEAD", 4, cwd=absRepoPath, verbosity=1)
    return res['stdout'].strip()

def getModifiedCount(absRepoPath):
    """Return the count of modified files in the repository at the given path."""
    res = gitCommand("git ls-files --modified --exclude-standard --directory", 4, cwd=absRepoPath, verbosity=1)
    ans = res['stdout'].strip()
    if not ans:
        return 0
    return len(ans.split('\n'))

def getStagedCount(absRepoPath):
    """Return the count of staged files in the repository at the given path."""
    res = gitCommand("git diff --name-only --cached", 4, cwd=absRepoPath, verbosity=1)
    ans = res['stdout'].strip()
    if not ans:
        return 0
    return len(ans.split('\n'))



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

def getCurrentBranchOrHash(absRepoPath):
    try:
        res = gitCommand("git branch", 3, cwd=absRepoPath, verbosity=1, ignoreErrors=False)
        restore = None
        m = re.search(r'^\* \(HEAD detached at.*', res["stdout"], re.MULTILINE)
        if m:
            return getCurrentRevHash(absRepoPath)
        m = re.search(r'^\* (.*)$', res["stdout"], re.MULTILINE)
        if m:
            return m.group(1)
    except:
        pass
    raise Exception("Invalid Branch")



# --------------------------------------------------------------------------------------------------------------------------
# Dictionary Operations
# --------------------------------------------------------------------------------------------------------------------------

def syncFileType(syncFilePath):
    ext = os.path.splitext(syncFilePath)[-1][1:]
    if ext in ['json','wl']:
        return ext
    return 'json'

def writeBisectRestoreToJson(syncRepoPath, restoreDict):
    newFileContents = json.dumps(restoreDict, indent=4)
    absSyncRepoPath = os.path.abspath(syncRepoPath)
    absBisectRestorePath = os.path.join(absSyncRepoPath, '.bisectRestore')
    with open(absBisectRestorePath, 'w') as f:
        f.write(newFileContents)

def loadBisectRestoreFromJson(syncRepoPath):
    checkForSyncRepoDir(syncRepoPath)
    absSyncRepoPath = os.path.abspath(syncRepoPath)
    absBisectRestorePath = os.path.join(absSyncRepoPath, '.bisectRestore')
    with open(absBisectRestorePath) as f:
        jsonTxt = f.read()
        restoreDict = json.loads(jsonTxt, object_pairs_hook=OrderedDict)
        return restoreDict if restoreDict else OrderedDict()

def removeBisectRestoreFile(syncRepoPath):
    absSyncRepoPath = os.path.abspath(syncRepoPath)
    absBisectRestorePath = os.path.join(absSyncRepoPath, '.bisectRestore')
    os.remove(absBisectRestorePath)

def loadSyncFileAsDict(syncFilePath):
    absSyncFilePath = os.path.abspath(syncFilePath)
    checkForSyncRepo(absSyncFilePath)
    with open(absSyncFilePath) as f:
        txt = f.read()
        if syncFileType(absSyncFilePath) == 'wl':
            replacements = {
                '<|':'{',
                '|>':'}',
                '{' :'[',
                '}' :']',
                '->' :':'
            }
            jsonTxt = multipleReplace(replacements,txt)
        else:
            jsonTxt = txt
        syncDict = json.loads(jsonTxt, object_pairs_hook=OrderedDict)
        if not syncDict:
            printWithVars1("failure! no repos where specified in the sync file at {absSyncFilePath}.", 'red')
            sys.exit(1)
        return syncDict

def writeDictToSyncFile(syncFilePath, dict):
    if syncFileType(syncFilePath) == 'wl':
        newFileContents = json.dumps(dict, indent=4, separators=(',', ' -> ')).replace("{","<|").replace("}","|>")
    else:
        newFileContents = json.dumps(dict, indent=4)    
    path = os.path.abspath(syncFilePath)
    with open(path, 'w') as f:
        f.write(newFileContents)
    printWithVars3("Wrote new dictionary of bank sync information to {path}")


def dictFromCurrentRepoState(path, **kwargs):
    opts = merge({'cwd':".", 'verbosity': 3, 'raiseOnFailure': True}, kwargs)
    absRepoPath = getAbsRepoPath(path, opts['cwd'])
    opts['cwd'] = absRepoPath
    newRepoInfo = OrderedDict()
    newRepoInfo["path"] = path
    succeeded = True
    try:
        res = gitCommand("git log HEAD -n 1 --date=iso --format=format:'\"sha\" : \"%H\",%n\"UnixTimeStamp\" : \"%at\",%n\"date\" : \"%ad\",%n\"author\" : \"%an\"'", **opts)
        props = json.loads('{'+res["stdout"]+'}', object_pairs_hook=OrderedDict)
        newRepoInfo.update(props)

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

