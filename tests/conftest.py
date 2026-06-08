import shutil
from pathlib import Path

import pytest


TEST_SCRATCH_PATHS = (
    "repoFish",
    "repoBird",
    "repoSyncFile",
    "repoBob",
    "zoosyncrepo",
    "animals",
    "animalsrepo",
    "testFido",
    "foo",
)


@pytest.fixture(autouse=True)
def cleanup_test_scratch_paths():
    repo_root = Path(__file__).resolve().parent.parent
    preexisting_paths = {}
    for path in (repo_root / relative_path for relative_path in TEST_SCRATCH_PATHS):
        if path.exists():
            stat = path.stat()
            preexisting_paths[path] = (stat.st_dev, stat.st_ino)

    try:
        yield
    finally:
        for relative_path in TEST_SCRATCH_PATHS:
            path = repo_root / relative_path
            if not path.exists():
                continue

            stat = path.stat()
            if preexisting_paths.get(path) == (stat.st_dev, stat.st_ino):
                continue

            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
