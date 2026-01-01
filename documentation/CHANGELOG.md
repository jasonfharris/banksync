# 0.9.11

Changes made in 0.9.11 can be summarized as follows:

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

