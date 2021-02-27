#!/bin/bash

# https://packaging.python.org/tutorials/packaging-projects/

# cd to /Development/Python/banksync_Package
# it is important the script is run from there.

pip3 uninstall banksync

rm -r banksync.egg-info 2> /dev/null
rm -r build 2> /dev/null
rm -r dist 2> /dev/null

python3 -m build

#python3 -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*
# Enter the TestPyPI user: jasonfh
# Enter the TestPyPI pass: **************

# The following uses the information in ~/.pypirc
python3 -m twine upload --repository testpypi dist/*


sleep 5

# install the package locally from TestPyPI:
pip3 install -i https://test.pypi.org/simple/ banksync