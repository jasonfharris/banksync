#!/bin/bash

# https://packaging.python.org/tutorials/packaging-projects/

# cd to /Development/Python/sysexecute_Package
# it is important the script is run from there.

pip3 uninstall banksync
python3 setup.py sdist bdist_wheel

#python3 -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*
# Enter the TestPyPI user: jasonfh
# Enter the TestPyPI pass: **************

# The following uses the information in ~/.pypirc
python3 -m twine upload --repository pypi dist/*


sleep 5

# install the package locally from TestPyPI:
pip3 install banksync