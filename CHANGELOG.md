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