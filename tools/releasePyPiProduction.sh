#!/bin/bash

pip uninstall banksync
python setup.py sdist upload -r pypi
sleep 3
pip install banksync