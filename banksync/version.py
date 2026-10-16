"""Version numbers for banksync and the syncfile format. pyproject.toml and the release scripts read __version__."""

__version__ = "0.9.10"

# Written into new syncfiles: the format version, and the oldest banksync that can read them. Syncfiles with a
# "configuration" section cannot be read by banksync 0.9.10, so set REQUIRED_BANKSYNC_VERSION to the version of the
# next release when it is cut.
SYNCFILE_FORMAT_VERSION = "1.0"
REQUIRED_BANKSYNC_VERSION = "0.9.10"
