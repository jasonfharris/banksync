# 0.9.11 (26 Nov 2026)

The first release since 0.9.10. Syncfiles written by 0.9.11 have a `configuration` section, which banksync 0.9.10
cannot read, so they are stamped `"requiredBanksyncVersion": "0.9.11"`.

Requirements and packaging:

- Python 3.12 or later. Packaging is in pyproject.toml; setup.py, setup.cfg and the bin/ launcher scripts are gone, and
  `bank` / `banksync` are console-script entry points. `python -m banksync` runs a checkout without installing it.
- The sysexecute dependency is removed. Commands run through banksync/shell.py, which passes arguments to git without a
  shell or format-string substitution, so arguments such as `HEAD@{0}`, `@{u}`, quotes and spaces reach git unchanged.
- The license is MIT throughout: documentation/LICENSE.txt now contains the MIT License (it held BSD-3-Clause text
  while the package metadata said MIT) and is included in the built distributions.
- The code is split into typed modules (console, shell, git, syncfile, options, commands) and is `mypy --strict` clean.

Behaviour:

- Options can be set in the syncfile's `configuration` section (`"sync.matching": "timestamp"`, ...) and in
  `~/.bankconfigrc`, which was never actually read before. Command line > syncfile > ~/.bankconfigrc > defaults.
- `--colorize` takes `auto` (the new default: color only on a terminal and when NO_COLOR is unset), `yes` or `no`.
- `bank clone` honours `clone.syncreponame` and finds syncfiles with any name. `bank populate` skips repos that are
  already present, so it can be rerun.
- `bank bisect run <cmd>` syncs the bank before running the command at each step. `bisect reset` reports repos it could
  not restore and exits 1. The bisect state is kept in the syncrepo's .git directory instead of a `.bisectRestore` file.
- `bank git` accepts any git command (with a warning outside the common ones), passes `--` and anything after it
  through, and no longer mistakes git options such as `--color` for abbreviations of bank's own options.
- `create_syncfile` does not write incomplete syncfiles and rejects two repos with the same name. `create_syncrepo`
  accepts `--syncfilename path/inside/the/syncrepo.json` and cleans up after a failure.
- `record_repos` keeps keys it does not write itself, records commit messages verbatim, and records the URL of the
  first remote when there is no origin (it used to record the remote's name).
- Syncfiles given with `--syncfile` are checked against `requiredBanksyncVersion` too.
- `bank sync --syncBranches no|yes|force`, support for git worktrees as repos and syncrepos, and `bank git pull` on a
  detached HEAD pulling the remote's default branch.

Documentation:

- The README and `--help` texts describe the current behaviour: correct `--matching` and `--colorize` values, the
  `status`, `clone` and `create_syncrepo` commands, option files, syncfile keys, and how the syncfile is found.

Testing:

- The doctests are replaced by a pytest suite that works in temporary directories with local remotes and fixed commit
  dates, so it neither touches the checkout nor needs the network (except one opt-in test).


Earlier changes in 0.9.11, made before the rewrite above:

Code files:

- Include the branch in the information we record for each repo in the syncfile.
- Respect the 'colorize' option throughout BankSync.
- Pass `syncFileAbsPath` as a parameter and localize other global variables.
- Enable handling of `bank_sync` commands from anywhere within the project.
- Introduce some utilities for handling version numbers.
- Implement handling for some (or all) repository paths being absolute rather than relative.
- Document the configuration options for the syncfile.
- Move the default options to the section handling options.
- Deprecate `OrderedDict` since in Python 3.7 it has become the standard.
- For most commands, print the syncfile name or path upon success or failure to provide more context.
- Transition to using a `syncInfo` object read from `syncFileAbsPath`.
- In `bisect`, handle cases where a bisection state is not present.
- Remove 'bankconfig.ini' from both the documentation and the test files.
- Store the configuration in the syncfile, particularly the path from the syncrepo to the project root.
- Use dictionaries to store the descriptions for command help.
- Make the offset between the syncfile and the repositories consistent. Remove the `--cwd` option from the command line interface.
- In the series of changes, work towards basing things on the path `syncFileAbsPath`.
- Refactor the way commands are dispatched to create a more uniform dispatch mechanism.
- Rename the variable `absRepoPath` to `repoAbsPath` in both files to improve consistency and clarity.

Testing:

1. Test paths which are outside the root and also absolute paths.


# 0.9.10

Fix documentation mistake

# 0.9.9

Changes made in 0.9.9 can be summarized as follows:

Documentation:

1. Improved the description of `banksync`.
2. Expanded the Quick Start section.
3. Added a step-by-step walkthrough.
4. Changed the syncfile extension from `.wl` to `.json`, and standardized on `.json` files.
5. Replaced camel case command names with snake case.
6. Made minor formatting and wording changes for better readability and clarity.

Code files:

1. Removed unused imports and added new ones.
2. Updated keys in the `defaultOptions` dictionary.
3. Added new subcommands `clone` and `populate` with corresponding code for `commandClone()` and `commandPopulate()`.
4. Updated help text and usage examples for subcommands.
5. Updated the argument parsing code.
6. Updated the resolved option handling to consolidate on a flattened configuration dictionary `_config`.
7. Removed global variables in favour of one consolidated `_config` dictionary.
8. Changed a number of function signatures in response to now having this unified `_config` available.
9. Updated variable assignments and replaced variables in string formatting with f-strings.
10. Updated warning and failure messages.
11. Updated the `dispatchCommand` function to use a dictionary mapping command names to functions.
12. Updated the `getResolvedOptions` function to use `flattenDict`.
13. Renamed and updated several functions, added new helper functions, and removed the `syncFileType` function.
14. Updated the `loadSyncFileAsDict` function.

Testing:

1. Updated a number of the tests so they are more robust around determining the path they are on.

