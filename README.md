## Purpose

`banksync` is a command line tool that simplifies the use of git commands across a "bank" or "collection" of repositories. It enables synchronization of historical configurations throughout the bank of repos.

## Installation

You can install `banksync` from PyPi with a simple:

    pip install banksync

## Quick Start

A bank is a collection of repos defined in a *syncfile*. The syncfile typically resides in a *syncrepo*. In this example, we'll use a project called `animals` containing two repos: `repoFish` and `repoBirds`. The project can be placed anywhere, but for simplicity, we'll put it in the user's root directory.

To quickly clone and populate the example collection of repos, use the following commands:

    cd ~
    bank clone https://github.com/testbank/animalsSyncRepo.git animals

This will git clone the thin syncrepo, which contains the syncfile, and then populate all constituent repos. The resulting structure will be:

    animals
    ├── repoBird
    │   └── Bird.txt
    ├── repoFish
    │   └── Fish.txt
    └── syncrepo
        └── syncfile.json


Let's walk quickly through what is happening

### Step-by-step Walkthrough

Let's break down the quick start process into steps.

1. Create a directory `animals`:

   ```
   cd ~
   sudo rm -r animals
   mkdir animals
   cd animals
   ```

2. Clone the demonstration syncrepo for the animals project using standard git:

   ```
   git clone https://github.com/testbank/animalsSyncRepo.git syncrepo
   ```

   This clones the thin repo, which records the syncfile over time. It tracks the state of the repos in the bank at different times or stages. The resulting hierarchy is:

   ```
   animals
   └── syncrepo
       └── syncfile.json
   ```

3. Populate the repositories in the bank:

   ```
   cd syncrepo
   bank populate
   ```

   The `populate` command clones each of the repos specified in the syncfile, resulting in the following layout:

   ```
   animals
   ├── repoBird
   │   └── Bird.txt
   ├── repoFish
   │   └── Fish.txt
   └── syncrepo
       └── syncfile.json
   ```

### Issuing Commands

We can now issue commands across the repos in the bank. From the root directory we can execute:

    cd ~/animals
    bank git status

Which will execute the status command in each of the repos in the bank. You can issue commands from anywhere
in the project directory. The bank executable will look for a syncrepo in successive parent directories until it
finds a syncrepo and it's syncfile. (If the bank executable doesn't find a syncfile the command will fail.) So

    cd ~/animals/repoBird
    bank git status

will yield the exact same result as before.

If we want to checkout a previous state across the repos in the project we can do this via (from the syncrepo):

    cd ~/animals/syncrepo
    git checkout master~2
    bank sync

The last two commands just moved the syncrepo two revisions back, and then synchronized the repos in the bank to the sync file at this earlier time. To get all repos back to the master branch revisions you can simply execute:

    bank gitall checkout master

Which will do a `git checkout master` on all the repos in the bank including the sync repo.

## Syncfile

The syncfile specifies which repositories are part of the bank, and what state the repositories should be synchronized to. A typical simple sync file might be the following

    more ~/animals/syncrepo/syncfile.json

Which yields:

```
{
   "configuration": {
      "createdByBanksyncVersion": "0.9.10",
      "requiredBanksyncVersion": "0.9.10",
      "syncfileFormatVersion": "1.0",
      "relativePathToRepositories": "..",
      "clone.syncreponame": "syncrepo"
   },
   "repositories": {
      "repoBird" : {
         "path": "repoBird",
         "sha": "6bf9d646b2aa224b64fb86cbddb4d7ab0f2e37d3",
         "UnixTimeStamp": "1480517200",
         "date": "2016-11-30 15:46:40 +0100",
         "author": "Jason Harris",
         "branch": "master",
         "revisionNumber": "3",
         "message": "committing eagle",
         "cloneURL": "https://github.com/testbank/repoBird.git"
      },
      "repoFish": {
         "path": "repoFish",
         "sha": "a27368bec17373938b1dcf73638945b89b60a9d0",
         "UnixTimeStamp": "1480517200",
         "date": "2016-11-30 15:46:40 +0100",
         "author": "Jason Harris",
         "branch": "master",
         "revisionNumber": "3",
         "message": "committing salmon",
         "cloneURL": "https://github.com/testbank/repoFish.git"
      }
   }
}
```

The syncfile should lie inside a git repo (the syncrepo). Whenever we want to record a configuration of the
repos we simply alter the syncfile by transcribing the current state of the repos into the syncfile using
`bank record_repos` with the appropriate options. We then use `git commit` to record this new state /
configuration in the syncrepo (the syncrepo is a normal git repo).

So let us add some content to repoBird in our example and then commit this change.

    cd  ~/animals/repoBird
    echo "toucan" >> Bird.txt
    git commit -am "committing toucan"

So now we can update the syncfile with the state of the current repos in the bank (we can issue bank commands
from anywhere within our project directory):

    bank record_repos

The contents of our syncfile will now be something like:

```

{
   "configuration": {
      "createdByBanksyncVersion": "0.9.10",
      "requiredBanksyncVersion": "0.9.10",
      "syncfileFormatVersion": "1.0",
      "relativePathToRepositories": "..",
      "clone.syncreponame": "syncrepo"
   },
   "repositories": {
      "repoBird" : {
         "path" : "repoBird",
         "sha" : "c8fb05947c5161e484104d99f427ec082fb4e85b",
         "UnixTimeStamp" : "1480519159",
         "date" : "2016-11-30 - 16:19:19",
         "author" : "Jason Harris",
         "revisionNumber" : "4",
         "message" : "committing toucan",
         "cloneURL" : "https://github.com/testbank/repoBird.git"
      },
      "repoFish": {
         "path": "repoFish",
         "sha": "a27368bec17373938b1dcf73638945b89b60a9d0",
         "UnixTimeStamp": "1480517200",
         "date": "2016-11-30 15:46:40 +0100",
         "author": "Jason Harris",
         "branch": "master",
         "revisionNumber": "3",
         "message": "committing salmon",
         "cloneURL": "https://github.com/testbank/repoFish.git"
      }
   }
}
```

(Note the sha, timestamps, and other data about the state of the repo `repoBird` has changed.)

So we could now record this new overall state of the repos in the bank via simply committing the file syncfile in the syncrepo.

    git commit -am "recording the latest state of the repos in animals."

## Locations

How does the bank command determine the locations for `repoBird` and `repoFish`, as well as the appropriate
syncfile to use? The paths are stored in the syncfile itself (along with other information). So all the paths
are relative to the syncfile.

The `relativePathToRepositories` configuration option indicates the relative path where repo commands should be executed. In this case, it is one level above our current working directory. Given that the syncfile is located in `~/animals/syncrepo`, this means that the repo paths will originate from `~/animals/`. For example, the path for "Birds" in the syncfile is simply `repoBird`. Relative to `animals/syncrepo`, and considering the `relativePathToRepositories` of `..`, we can determine the repo path for "birds". This is calculated as `animals/syncrepo` + `..` + `repoBird`, resulting in `animals/repoBird`, which is the storage location for the "Birds" repo.

Note if we wanted to we could have used a different name for the syncrepo and indeed a different name for the
syncfile. We could have called the syncfile `earthanimals.json` if we wanted to.

## Bank command line options

The command line tool `bank` has several options which can be specified:

#### --syncfile <path>

The `syncfile` option specifies a syncfile. The syncfile contents specify which repos are part of the bank.
The various keys which are recorded if present are:`path`, `sha`, `UnixTimeStamp`, `date`, `author`,
`revisionNumber`, `message`, `branch`, and `cloneURL`. Adding other keys at present will not effect or change
the behavior of the bank tool so you can add other info as you see fit / want to each of the recorded states
in the various repos.

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

## Options in the sync file

The sync file itself contains a 'configuration' section where you can specify prevailing options. So the above example would become:

## Commands

The form of a bank command is `bank <cmd> <opts>` where `<cmd>` is one of `sync`, `record_repos`, `create_syncfile`, `bisect`, `populate`,  `git` or `gitall` 

#### bank sync <opts>

`sync` will update / checkout the revisions specified in the syncfile for each of the repos specified in the bank.

    bank sync --syncfile syncfile.json

This would checkout / update the repos given in the syncfile `syncfile.json` to the states given in the syncfile. It each repo it tries to checkout the version first by the given sha, and then it falls back to the given timestamp, and then it falls back to the closest timestamp. (This fallback behavior can be controlled by the `--matching` option.)

    bank sync --syncfile other/dir/syncfile.json

This would checkout / update the repos given in the specified syncfile to the states given in the syncfile.
(The repos are relative to the syncfile.)

#### bank record_repos <opts>

`record_repos` is used to transcribe the current state of the repos into the syncfile. Eg:

    bank record_repos --syncfile syncfile.json

This would alter the contents of the syncfile and change the revisions stored in the syncfile.json to match the current revisions of the referenced repositories.

#### bank create_syncfile <opts>

`create_syncfile` is used to generate an initial syncfile. Eg:

    bank create_syncfile --syncfile syncfile.json repo1 repo2 ... repoN --cwd some/dir

This would generate or overwrite the syncfile.json to contain sync points for the current states of `repo1`, `repo2`, ... `repoN`

#### bank create_syncrepo <opts>

`create_syncrepo` is used to generate the syncrepo directory, initialize a git repository there, and create the syncfile. Basically it creates all the working parts of a syncrepo. Eg:

    bank create_syncrepo repo1 repo2 ... repoN

This would create the directory `syncrepo` and fill it with a `syncfile.json`. The syncfile would contain the latest states of the `repo1`, `repo2`, ... `repoN`. 

    bank create_syncrepo --syncreponame controlrepo --syncfilename felipe.json repo1 repo2 ... repoN

Would create and initialize a syncrepo called `controlrepo` and inside that a syncfile called `felipe.json`.

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

    bank git status --syncfile syncfile.json

Will perform a `git status` operation on each of the repositories in the bank and print the results to stdout.

If you use `gitall` instead of `git` command, then the git command will also be run in the syncrepo.

    bank gitall status --syncfile syncfile.json

Will perform a `git status` operation on each of the repositories in the bank and print the results to stdout.

## Testing

To run the test suite you need `py.test` installed on your machine. Then after downloading the source code you can simply execute:

    cd banksync_Package
    py.test

