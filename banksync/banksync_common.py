#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import os.path
import string
import sys
import time
import re
import json
from collections import OrderedDict
from sysexecute import *
import datetime
import configparser
import textwrap



# --------------------------------------------------------------------------------------------------------------------------
# Defines
# --------------------------------------------------------------------------------------------------------------------------

autoNum = -1       # an arbitrary negative number to stand in for 'auto' in a numerical option



# --------------------------------------------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------------------------------------------

def multiple_replace(dict, text):
  # Create a regular expression  from the dictionary keys
  regex = re.compile("(%s)" % "|".join(map(re.escape, dict.keys())))

  # For each match, look-up corresponding value in dictionary
  return regex.sub(lambda mo: dict[mo.string[mo.start():mo.end()]], text) 

def dateFromTimeStamp(ts):
    return datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')

def isSha1Str(s):
    return True if re.match( r'^[0-9a-fA-F]{40}$', s) else False

def correctlyQuoteArg(arg):
    """quote any string that has white space in it"""
    m = re.match('.*\s+.*', arg)
    if m:
        return '"{}"'.format(arg)
    return arg

def wrapParagraphs(str):
    paras = str.split('\n\n')
    wrappedParas = [textwrap.fill(para, 80) for para in paras]
    return "\n\n".join(wrappedParas)

def escape_ansi(line):
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
    return repoName.ljust(maxRepoNameLength+1)

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

def gitCommand(cmdStr, verbosityThreshold = 3, **kwargs):
    opts = merge({'cwd':'.', 'captureStdOutStdErr':True, 'permitShowingStdErr':True, 'permitShowingStdOut':True, 'ignoreErrors':True, 'raiseOnFailure': False, 'verbosity': 3}, kwargs)
    ( code, sout, serr) = execute(cmdStr, verbosityThreshold, **opts)
    res = {'code':code, 'stdout':sout, 'stderr':serr }
    if opts['raiseOnFailure'] and code != 0:
        raise Exception(stringWithVars("Bad git result {res}"))
    return res

def getRevNumber(sha, absRepoPath):
    res = gitCommand("git rev-list HEAD --count --first-parent", 4, cwd=absRepoPath)
    try:
        num = int(res["stdout"].strip())
        return str(num)
    except:
        return "(unknown)"



# --------------------------------------------------------------------------------------------------------------------------
# Dictionary Operations
# --------------------------------------------------------------------------------------------------------------------------

def loadSyncFileAsDict(syncFilePath):
    absSyncFilePath = os.path.abspath(syncFilePath)
    checkForSyncRepo(absSyncFilePath)
    with open(absSyncFilePath) as f:
        txt = f.read()
        replacements = {
            '<|':'{',
            '|>':'}',
            '{' :'[',
            '}' :']',
            '->' :':'
        }
        jsonTxt = multiple_replace(replacements,txt)
        syncDict = json.loads(jsonTxt, object_pairs_hook=OrderedDict)
        if not syncDict:
            printWithVars1("failure! no repos where specified in the sync file at {absSyncFilePath}.", 'red')
            sys.exit(1)
        return syncDict

def writeDictToSyncFile(syncFilePath, dict):
    newFileContents = json.dumps(dict, indent=4, separators=(',', ' -> ')).replace("{","<|").replace("}","|>")
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
            m = re.match('origin\s*(\S+) \(fetch\)', res["stdout"])
            if m:
                cloneURL = m.group(1)
        if not cloneURL:
            m = re.match('(\w+)\s*(\S+) \(fetch\)', res["stdout"])
            if m:
                cloneURL = m.group(1)
        if cloneURL:
            newRepoInfo["cloneURL"] = cloneURL.strip()
    except:
        succeeded = False
    
    return (succeeded, newRepoInfo)

