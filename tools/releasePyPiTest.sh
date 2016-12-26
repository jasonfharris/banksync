#!/bin/bash

pip uninstall banksync
python setup.py sdist upload -r pypitest
sleep 3
pip install -i https://testpypi.python.org/pypi banksync