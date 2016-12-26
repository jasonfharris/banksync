## Purpose

The banksync command line tool allows the easy operation of git commands across a "bank" or "collection" or repositories. It allows synchronization to historic configurations across the bank of repos.

## Installation

You can install `banksync` from PyPi with a simple:

```
pip install banksync
```

## Quickstart

A bank is a collection of repos. The collection of repos is specified in a *syncfile*. The syncfile typically lives in *syncrepo*. So let us demonstrate this with a trivial collection of repos. The overall project will be called `animals` and it will contain a repo `repoFish` and a repo `repoBirds`. The project can live anywhere but to make the description easy let us put the project in the users root directory.

So make a directory `animals`:

    cd ~
    mkdir animals
    cd animals

Now clone the demonstration syncrepo for the animals project using standard git:

    git clone https://github.com/testbank/animalsRepoSync.git

This will clone the thin repo which records the syncfile over time. Ie it records the state of the repos in the bank at different times / stages. We now have the hierarchy:

    animals
    └── animalsRepoSync
        ├── bankconfig.ini
        └── syncfile.wl

Now we enter into this directory and we clone the repositories in the bank

    cd animalsRepoSync
    bank clone

The clone command will clone all of the repos specified in the syncfile and we will now have the following layout:

    animals
    ├── animalsRepoSync
    │   ├── bankconfig.ini
    │   └── syncfile.wl
    ├── repoBird
    │   └── Bird.txt
    └── repoFish
        └── Fish.txt

We can now issue commands across the repos in the bank. From the syncrepo we can execute:

    cd ~/animals/animalsRepoSync
    bank git status

Which will execute the status command in each of the repos in the bank. If we want to checkout a previous state across the repos in the project we can do this via (from the syncrepo):

    git checkout master~2
    bank sync

The last two commands just moved the syncrepo two revisions back, and then synchronized the repos in the bank to the sync file at this earlier time. To get all repos back to the master branch revisions you can simply execute:

    bank gitall checkout master

Which will do a `git checkout master` on all the repos in the bank including the sync repo.

## Syncfile

The syncfile specifies which repositories are part of the bank, and what state the repositories should be synchronized to. A typical simple sync file might be the following

    more ~/animals/animalsRepoSync/syncfile.wl

Which yields:

```
<|
    "repoFish" -> <|
        "path" -> "repoFish",
        "sha" -> "a27368bec17373938b1dcf73638945b89b60a9d0",
        "UnixTimeStamp" -> "1480517200",
        "date" -> "30 Nov 2016 - 15:46:40",
        "author" -> "Jason Harris",
        "revisionNumber" -> "3",
        "message" -> "committing salmon",
        "cloneURL" -> "https://github.com/testbank/repoFish.git"
    |>,
    "repoBird" -> <|
        "path" -> "repoBird",
        "sha" -> "6bf9d646b2aa224b64fb86cbddb4d7ab0f2e37d3",
        "UnixTimeStamp" -> "1480517200",
        "date" -> "30 Nov 2016 - 15:46:40",
        "author" -> "Jason Harris",
        "revisionNumber" -> "3",
        "message" -> "committing eagle",
        "cloneURL" -> "https://github.com/testbank/repoBird.git"
    |>
|>
```

The syncfile should lie inside a git repo (the syncrepo). Whenever we want to record a configuration of the repos we simply alter the syncfile by transcribing the current state of the repos into the syncfile using `bank recordRepos` with the appropriate options. We then use `git commit` to record this new state / configuration in the syncrepo.

So let us add some content to repoBird in our example and then commit this change.

    cd  ~/animals/repoBird
    echo "toucan" >> Bird.txt
    git commit -am "committing toucan"

So now we can update the syncfile with the state of the current repos in the bank:

    cd ~/animals/animalsRepoSync/
    bank recordRepos

The contents of our syncfile will now be something like:

```
<|
    "repoFish" -> <|
        "path" -> "repoFish",
        "sha" -> "a27368bec17373938b1dcf73638945b89b60a9d0",
        "UnixTimeStamp" -> "1480517200",
        "date" -> "30 Nov 2016 - 15:46:40",
        "author" -> "Jason Harris",
        "revisionNumber" -> "3",
        "message" -> "committing salmon",
        "cloneURL" -> "https://github.com/testbank/repoFish.git"
    |>,
    "repoBird" -> <|
        "path" -> "repoBird",
        "sha" -> "c8fb05947c5161e484104d99f427ec082fb4e85b",
        "UnixTimeStamp" -> "1480519159",
        "date" -> "30 Nov 2016 - 16:19:19",
        "author" -> "Jason Harris",
        "revisionNumber" -> "4",
        "message" -> "committing toucan",
        "cloneURL" -> "https://github.com/testbank/repoBird.git"
    |>
|>
```

(Note the sha, timestamps, and other data about the state of the repo `repoBird` has changed.)

So we could now record this new overall state of the repos in the bank via simply committing the file syncfile in the syncrepo.

    git commit -am "recording the latest state of the repos in animals."

## Locations

How does the bank command know where to put the `repoBird` and `repoFish`? How does it know which syncfile to use, etc. Well in the syncrepo there is the file `bankconfig.ini`. This is a standard preferences file but in this example it has two important options: `cwd=..` and `syncfile=syncfile.wl`.

The cwd (ChangeWorkingDirectory) option specifies that the repo commands should be executed one level up from our current working directory. So since we are currently at `~/animals/animalsRepoSync` that means that the repos paths will start from `~/animals/`

The second option just tells us what the name of the syncfile is. We could have called it `earthanimals.wl` if we wanted to.

## Bank command line options

The command line tool `bank` has several options which can be specified:

#### --syncfile <path>

The `syncfile` option specifies a syncfile. The syncfile contents specify which repos are part of the bank. The various keys which are recorded if present are:`path`, `sha`, `UnixTimeStamp`, `date`, `author`, `revisionNumber`, `message`, and `cloneURL`. Adding other keys at present will not effect or change the behavior of the bank tool so you can add other info as you see fit / want to each of the recorded states in the various repos.

#### --cwd <path>

The cwd option will change the working directory. Using this you can specify the relative path to get to the base of where the path for each of the repos in the bank are. For instance in the layout example of the animals project above, if we are in the directory `animals/animalsSyncRepo` then since the path in the syncfile for "Birds" is just `repoBird` then relative to `animals/animalsSyncRepo` we want the directory `../repoBird`. So we would use the option `--cwd ..`

#### --dryrun

If this option is specified then `banksync` will report what it *would* do but it doesn't actually do anything.

#### --colorize <bool>

You can specify if color is not to be used in output if for instance you want the logs to be parsed in jenkins or other devops tools. (The default is `True`, i.e. colorize the output of the bank command)

#### --verbosity <num>

You can specify how much information banksync reports. This integer should be between 0, 1, 2, 3, or 4. The higher the number the more verbose is the reporting. The default is 2.

#### --matching <type>

When attempting to sync the constituent repos to the versions specified in the syncfile, how do we determine what to set the versions to? We want some loose coupling in that for instance if someone runs filter branch on a project or they do some rebase very early on in the history then the shas will change on all the revisions in the repository. So instead of finding a commit via a sha we will have to fall back to looking for a matching timestamp for the revision. These are generally fairly unique in a project unless a lot of cherrypicking has gone on. If we don't find that exact timestamp then we could fall back to the closest matching revision to that timestamp. In this way at least we have some hope of getting close to the configuration at the time instead of just giving up. Ie we get to the exact configuration if it is available but if not get as close as we can. The value of the option can be:

- **shaOnly**: if we can't find the exact same revision given by the sha in the syncfile than give up.
- **timestamps**: try matching by sha first but if that fails find the first revision with the same unix timestamp. (This is almost always preserved across repo manipulation)
- **closetimestamps**: try matching by sha first, if that fails try matching by timestamp. and if that fails find the revision with the closest timestamp and match to that.

## Config file

Instead of specifying the `--syncfile` and`—cwd` in each command you can create a `bankconfig.ini` file alongside the syncfile. In the `bankconfig.ini` file you can specify the default syncfile and cwd to use if none is specified. Eg we could add the file `animals/animalsSyncRepo/bankconfig.ini` with the following contents:

```
[General]
cwd=..
syncFile=syncfile.wl
```

Then you could omit the options to the bank command and they would be taken from the bankconfig.ini file so the above example would become:

```
cd animals/animalsSyncRepo
bank recordRepos
git commit -am "recording the latest state of the repos in animals."
```

You can choose weather to include the `bankconfig.ini` in the syncrepo history or not. (We choose to in this example but other teams may leave this to the individual developers.)

## Commands

The form of a bank command is `bank <cmd> <opts>` where `<cmd>` is one of `sync`, `recordRepos`, `createSyncfile`, `bisect`, `clone`,  `git` or `gitall` 

#### bank sync <opts>

`sync` will update / checkout the revisions specified in the syncfile for each of the repos specified in the bank.

```
bank sync --syncfile syncfile.wl
```

This would checkout / update the repos given in the syncfile `syncfile.wl` to the states given in the syncfile. It each repo it tries to checkout the version first by the given sha, and then it falls back to the given timestamp, and then it falls back to the closest timestamp. (This fallback behavior can be controlled by the `--matching` option.)

```
bank sync --syncfile syncfile.wl --cwd ../other/dir
```

This would checkout / update the repos given in the syncfile to the states given in the syncfile
(but the path to each repo in the bank will be prefixed by the value of the `--cwd` option `../other/dir`).

#### bank recordRepos <opts>

`recordRepos` is used to transcribe the current state of the repos into the syncfile. Eg:

```
bank recordRepos --syncfile syncfile.wl
```

This would alter the contents of the syncfile and change the revisions stored in the syncfile.wl to match the current revisions of the referenced repositories.

#### bank createSyncfile <opts>

`createSyncfile` is used to generate an initial syncfile. Eg:

```
bank createSyncfile --syncfile syncfile.wl repo1 repo2 ... repoN --cwd some/dir
```

This would generate or overwrite the syncfile.wl to contain sync points for the current states of `repo1`, `repo2`, ... `repoN`

#### bank bisect <opts>

You can use `bank bisect` on the syncrepo to step through historic configurations looking for a configuration which produces some change. (Typically we are searching for a regression.) Eg if we have a configuration file in the syncrepo the following might be a typical bisect session:

    cd SomeSyncRepo
    bank bisect start
    bank bisect good 12e4f5
    bank bisect bad master
    <do build / test>
    bank bisect good 78a6b9
    <do build / test>
    bank bisect bad ae726a
    ...

Basically we are git bisecting on the syncrepo, and after each bisect step we get a new configuration, then `bank sync` will be run to synchronize the repositories in the bank to their state at the time that iteration of the syncfile was recorded . So `bank bisect <arguments>` is basically equivalent to `git bisect <arguments>; bank sync`

#### Dispatching git commands

We can use `bank` to perform a git command on each repository in the bank. All git commands have the prefix 'git' along with the normal name of the git command. Eg

    bank git status --syncfile syncfile.wl

Will perform a `git status` operation on each of the repositories in the bank and print the results to stdout.

If you use `gitall` instead of `git` command, then the git command will also be run in the syncrepo.

    bank gitall status --syncfile syncfile.wl

Will perform a `git status` operation on each of the repositories in the bank and print the results to stdout.

## Testing

To run the test suite you need `py.test` installed on your machine. Then after downloading the source code you can simply execute:

```
cd banksync_Package
py.test
```
