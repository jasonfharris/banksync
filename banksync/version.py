"""Version numbers for banksync and the syncfile format. pyproject.toml and the release scripts read __version__."""

__version__ = "0.9.10"

# Written into new syncfiles: the format version, and the oldest banksync that can read them.
SYNCFILE_FORMAT_VERSION = "1.0"
REQUIRED_BANKSYNC_VERSION = "0.9.10"
