
# The `setup_path` function is used to add the parent directory of the test file to `sys.path`. This allows
# you to import modules from the parent directory and its subdirectories in your doctest. By creating a
# separate `test_setup.py` file with the `setup_path` function, you avoid the issue of `__file__` being
# unavailable in doctest.

import sys, os

def setup_path():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def get_test_file_path():
    return os.path.abspath(os.path.dirname(__file__))
