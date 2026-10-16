#!/usr/bin/env bash

set -euo pipefail

# Build and upload banksync to the real PyPI repository.
#
# Requirements:
#   - ~/.pypirc contains a [pypi] entry, or Twine credentials are supplied via
#     environment variables / interactive prompt.
#   - banksync/version.py has a new __version__; PyPI will reject reused versions.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

cd "${REPO_ROOT}"

VERSION="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path

for line in Path("banksync/version.py").read_text().splitlines():
    if line.startswith("__version__"):
        print(line.split("=", 1)[1].strip().strip("\"'"))
        break
else:
    raise SystemExit("Could not find __version__ in banksync/version.py")
PY
)"

echo "Preparing banksync ${VERSION} for PyPI"

"${PYTHON_BIN}" -m pip install --upgrade build twine

rm -rf banksync.egg-info build dist

"${PYTHON_BIN}" -m build
"${PYTHON_BIN}" -m twine check dist/*
"${PYTHON_BIN}" -m twine upload --repository pypi dist/*

cat <<EOF

Uploaded banksync ${VERSION} to PyPI.

Verify from a clean environment with:
  ${PYTHON_BIN} -m pip install --upgrade banksync==${VERSION}
  bank --version

This script does not uninstall or replace the current editable install.
EOF
