## Purpose

The banksync command line tool allows the easy operation of git commands across a "bank" or "collection" or repositories. It allows synchronization to historic configurations across the bank of repos.

## Installation

You can install `banksync` from PyPi by a simple:

```
pip install banksync
```

## Syncfile

The syncfile specifies which repositories are part of the bank, and what state they should be synchronized to. A typical simple sync file might be the following

```
<|
    "Fishes" -> <|
        "path" -> "repoFish",
        "sha" -> "1404c7dbf83524f152968a0fe93dc588676ce75a",
        "UnixTimeStamp" -> "1479846913",
        "date" -> "Tue Nov 22 21:35:13 2016 +0100",
        "author" -> "Jason Harris",
        "revisionNumber" -> "2",
        "message" -> "committing snapper"
    |>,
    "Birds" -> <|
        "path" -> "repoBird",
        "sha" -> "be06fc47733f518c0fd18bf90b460ef3ab858cb4",
        "UnixTimeStamp" -> "1479846913",
        "date" -> "Tue Nov 22 21:35:13 2016 +0100",
        "author" -> "Jason Harris",
        "revisionNumber" -> "2",
        "message" -> "committing hawk"
    |>
|>
```

(That example is mostly taken from the banksync tests)

Typically the syncfile lies inside a git repo. Whenever we want to record a configuration of the repos we simply alter the syncfile by transcribing the current state of the repos into the syncfile using `bank createSyncPoint` with the appropriate options. We then use `git commit` to record this new state / configuration.

So assume we call the overall project "animals". Then we might have the following layout.

    └── animals
        ├── repoBird
        │   └── Bird.txt
        ├── repoFish
        │   └── Fish.txt
        └── animalsSyncRepo
            └── syncfile.wl

So assume you the developer then make some changes to the repos `repoBird` and `repoFish`. To record this new state you could do:

```
cd animals/animalsSyncRepo
bank createSyncPoint --syncfile syncfile.wl --cwd ..
git commit -am "recording the latest state of the repos in animals."
```

## Bank command line options

The command line tool `bank` has several options which can be specified:

#### --syncfile

The `syncfile` option specifies a syncfile. The syncfile contents specify which repos are part of the bank. The various keys which are recorded if present are:`path`, `sha`, `UnixTimeStamp`, `date`, `author`, `revisionNumber`, `message`, and `cloneURL`. Adding other keys at present will not effect change the behavior of the bank tool so you can add other info as you see fit / want to each of the recorded states in the various repos.

#### --cwd

The cwd option will change the working directory. Using this you can specify the relative path to get to the base of where the path for each of the repos in the bank are. For instance in the layout example of the animals project above, if we are in the directory `animals/animalsSyncRepo` then since the path in the syncfile for "Birds" is just `repoBird` then relative to `animals/animalsSyncRepo` we want the directory ../repoBird. So we would use the option `--cwd ..`

#### --matching

When attempting to sync the constituent repos to the versions specified in the syncfile, how do we determine what to set the versions to? We want some loose coupling in that for instance if someone runs filter branch on a project or they do some rebase very early on in the history then the shas will change on all the revisions in the repository. So instead of finding a commit via a sha we will have to fall back to looking for a matching timestamp for the revision. These are generally fairly unique in a project unless a lot of cherrypicking has gone on. If we don't find that exact timestamp then we could fall back to the closest matching revision to that timestamp. In this way at least we have some hope of getting close to the configuration at the time instead of just giving up. Ie we get to the exact configuration if it is available but if not get as close as we can. The value of the option can be:

- **shaOnly**: if we can't find the exact same revision given by the sha in the syncfile than give up.
- **timestamps**: try matching by sha first but if that fails find the first revision with the same unix timestamp. (This is almost always preserved across repo manipulation)
- **closetimestamps**: try matching by sha first, if that fails try matching by timestamp. and if that fails find the revision with the closest timestamp and match to that.

## Config file

Instead of specifying the `--syncfile` and`—cwd` in each command you can create a `bankconfig.ini` file alongside the syncfile. In the `bankconfig.ini` file you can specify the default syncfile and cwd to use if none is specified. Eg we could add the file `animals/animalsSyncRepo/bankconfig.ini` with the following contents:

```
[Bank]
cwd=..
syncFile=syncfile.wl
```

Then you could commit the options to the bank command and they would be taken from the bankconfig.ini file so the above example would become:

```
cd animals/animalsSyncRepo
bank createSyncPoint
git commit -am "recording the latest state of the repos in animals."
```

You can choose weather to include the `bankconfig.ini` in the SyncRepo history or not. (We choose not to.)

## Commands

The form of a bank command is `bank <cmd> <opts>` where `<cmd>` is one of `sync`, `createSyncPoint`, `generateSyncFile`, `bisect`, or a git command.

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

#### bank createSyncPoint <opts>

`createSyncPoint` is used to transcribe the current state of the repos into the syncfile. Eg:

```
bank createSyncPoint --syncfile syncfile.wl
```

This would alter the contents of the syncfile and change the revisions stored in the syncfile.wl to match the current revisions of the referenced repositories.

#### bank generateSyncFile <opts>

`generateSyncFile` is used to generate an initial syncfile. Eg:

```
bank generateSyncFile --syncfile syncfile.wl repo1 repo2 ... repoN --cwd some/dir
```

This would generate or overwrite the syncfile.wl to contain sync points for the current states of `repo1`, `repo2`, ... `repoN`

#### bank bisect <opts>

You can use `bank bisect` on the SyncRepo to step through historic configurations looking for a configuration which produces some change (typically searching for a regression.) Eg if we have a configuration file in the syncRepo the following might be a typical bisect session

    cd syncRepo
    bank bisect start
    bank bisect good 12e4f5
    bank bisect bad master
    <do build / test>
    bank bisect good 78a6b9
    <do build / test>
    bank bisect bad ae726a
    ...

Basically we are git bisecting on the SyncRepo, and after each time we get a new configuration then `bank sync` will be run. So `bank bisect <arguments>` is basically equivalent to `git bisect arguments; bank sync`

#### Dispatched git commands

We can use `bank` to perform a git command on each repository in the bank. All git commands have the prefix 'git' along with the normal name of the git command. Eg

    bank gitstatus --syncfile syncfile.wl

Well perform a git `status` operation on each of the repositories in the bank and print the results to std out.

## Testing

To run the test suite you need `py.test` installed on your machine. Then after downloading the source code you can simply execute:

```
cd banksync_Package
py.test
```

