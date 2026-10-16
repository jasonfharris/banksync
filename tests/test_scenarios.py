"""End to end tests that drive `bank` against real git repositories in a scratch directory."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from conftest import BASE_TIMESTAMP, Workspace

SYNCFILE = "repoSyncFile/syncfile.json"


@dataclass
class Animals:
    """Two repos, repoFish and repoBird, whose states are recorded at three sync points in repoSyncFile/syncfile.json.

    Commits for sync point N are made at BASE_TIMESTAMP + 100 * (N - 1)."""

    ws: Workspace
    fish: list[str] = field(default_factory=list)  # trout, snapper, salmon
    bird: list[str] = field(default_factory=list)  # sparrow, hawk, eagle
    sync_points: list[str] = field(default_factory=list)

    def bank(self, style: str, *args: str, ok: bool = True) -> str:
        """Run a bank command that operates on the animals syncfile, locating it in the given style."""
        match style:
            case "explicit":
                return self.ws.bank(*args, "--syncfile", SYNCFILE, ok=ok)
            case "syncrepo":
                return self.ws.bank(*args, cwd="repoSyncFile", ok=ok)
            case "childrepo":
                return self.ws.bank(*args, cwd="repoFish", ok=ok)
        raise ValueError(style)

    def heads(self) -> tuple[str, str]:
        return self.ws.head("repoFish"), self.ws.head("repoBird")

    def at(self, sync_point: int) -> tuple[str, str]:
        """The expected (fish, bird) heads at sync point 1, 2 or 3."""
        return self.fish[sync_point - 1], self.bird[sync_point - 1]

    def checkout_syncrepo(self, ref: str) -> None:
        self.ws.git("repoSyncFile", "checkout", "--quiet", ref)

    def commit_syncfile(self, message: str) -> str:
        self.ws.git("repoSyncFile", "add", "syncfile.json")
        self.ws.git("repoSyncFile", "commit", "--quiet", "-m", message)
        return self.ws.head("repoSyncFile")


@pytest.fixture
def animals(workspace: Workspace) -> Animals:
    ws = workspace
    animals = Animals(ws)
    for repo in ("repoFish", "repoBird", "repoSyncFile"):
        ws.init_repo(repo)

    for index, (fish, bird) in enumerate([("trout", "sparrow"), ("snapper", "hawk"), ("salmon", "eagle")]):
        timestamp = BASE_TIMESTAMP + 100 * index
        animals.fish.append(ws.commit("repoFish", "Fish.txt", fish, timestamp))
        animals.bird.append(ws.commit("repoBird", "Bird.txt", bird, timestamp))
        if index == 0:
            ws.bank("create_syncfile", "--syncfile", SYNCFILE, "repoFish", "repoBird")
        else:
            ws.bank("record_repos", "--syncfile", SYNCFILE)
        animals.sync_points.append(animals.commit_syncfile(f"syncPoint{index + 1}"))

    assert len(set(animals.fish + animals.bird)) == 6
    return animals


# Each style locates the syncfile differently: given explicitly, found in the current directory, or found by
# searching the sibling directories of each parent directory.
styles = pytest.mark.parametrize("style", ["explicit", "syncrepo", "childrepo"])


@styles
def test_sync_moves_repos_to_each_sync_point(animals: Animals, style: str) -> None:
    for number, sync_point in enumerate(animals.sync_points, start=1):
        animals.checkout_syncrepo(sync_point)
        output = animals.bank(style, "sync")
        assert animals.heads() == animals.at(number)
        assert "success! all repos checked out to the state given in" in output

    animals.checkout_syncrepo("master")
    animals.bank(style, "sync")
    assert animals.heads() == animals.at(3)


def test_create_syncrepo_records_a_new_bank_that_can_be_synced(animals: Animals) -> None:
    ws = animals.ws
    animals.checkout_syncrepo(animals.sync_points[0])
    animals.bank("explicit", "sync")

    ws.bank("create_syncrepo", "--syncreponame", "zoosyncrepo", "--syncfilename", "joekeeper.json", "repoFish", "repoBird")
    ws.git("zoosyncrepo", "add", "joekeeper.json")
    ws.git("zoosyncrepo", "commit", "--quiet", "-m", "initial")
    zoo_initial = ws.head("zoosyncrepo")

    ws.bank("git", "checkout", "master", cwd="zoosyncrepo")
    ws.bank("record_repos", cwd="zoosyncrepo")
    ws.git("zoosyncrepo", "commit", "--quiet", "-am", "final")
    zoo_final = ws.head("zoosyncrepo")

    ws.git("zoosyncrepo", "checkout", "--quiet", zoo_initial)
    ws.bank("sync", "--syncfile", "zoosyncrepo/joekeeper.json")
    assert animals.heads() == animals.at(1)

    ws.git("zoosyncrepo", "checkout", "--quiet", zoo_final)
    ws.bank("sync", cwd="zoosyncrepo")
    assert animals.heads() == animals.at(3)


@styles
def test_bisect_syncs_the_bank_at_each_step_and_reset_restores_branches(animals: Animals, style: str) -> None:
    ws = animals.ws
    sp1, sp2, sp3 = animals.sync_points
    animals.bank(style, "gitall", "checkout", "master")

    animals.bank(style, "bisect", "start")
    animals.bank(style, "bisect", "good", sp1)
    animals.bank(style, "bisect", "bad", sp3)
    assert ws.head("repoSyncFile") == sp2
    assert animals.heads() == animals.at(2)

    output = animals.bank(style, "bisect", "good", sp2)
    assert f"{sp3} is the first bad commit" in output
    assert ws.head("repoSyncFile") == sp2
    assert animals.heads() == animals.at(2)

    animals.bank(style, "bisect", "reset")
    assert ws.head("repoSyncFile") == sp3
    assert animals.heads() == animals.at(3)
    assert ws.branch("repoFish") == ws.branch("repoBird") == "master"


@styles
def test_sync_falls_back_to_exact_and_then_closest_timestamps(animals: Animals, style: str) -> None:
    ws = animals.ws
    syncfile_path = "repoSyncFile/syncfile.json"
    animals.bank(style, "sync")

    # Without shas the exact timestamps of sync point 1 are used.
    animals.checkout_syncrepo(animals.sync_points[0])
    syncfile = ws.read_json(syncfile_path)
    for info in syncfile["repositories"].values():
        del info["sha"]
    ws.write_json(syncfile_path, syncfile)
    animals.bank(style, "sync")
    assert animals.heads() == animals.at(1)

    # Shift the sync point 2 timestamps by a second so that only the closest timestamp matches.
    ws.git("repoSyncFile", "reset", "--quiet", "--hard")
    animals.checkout_syncrepo(animals.sync_points[1])
    syncfile = ws.read_json(syncfile_path)
    for info in syncfile["repositories"].values():
        del info["sha"]
        info["UnixTimeStamp"] = str(int(info["UnixTimeStamp"]) + 1)
    ws.write_json(syncfile_path, syncfile)

    output = animals.bank(style, "sync", "--matching", "timestamp", ok=False)
    assert "failure! not all repos checked out to the state given in" in output
    assert animals.heads() == animals.at(1)

    animals.bank(style, "sync", "--matching", "shaOnly", ok=False)
    assert animals.heads() == animals.at(1)

    animals.bank(style, "sync", "--matching", "closetimestamp")
    assert animals.heads() == animals.at(2)


@styles
def test_git_runs_in_each_repo_and_gitall_also_in_the_syncrepo(animals: Animals, style: str) -> None:
    ws = animals.ws
    sp1, _, sp3 = animals.sync_points
    animals.checkout_syncrepo(sp1)
    animals.bank(style, "sync")
    assert animals.heads() == animals.at(1)

    animals.bank(style, "git", "checkout", "master")
    assert animals.heads() == animals.at(3)
    assert ws.head("repoSyncFile") == sp1

    animals.bank(style, "gitall", "checkout", "master")
    assert ws.head("repoSyncFile") == sp3


def test_git_arguments_with_spaces_braces_and_quotes_reach_git_unchanged(animals: Animals) -> None:
    ws = animals.ws
    # Under sysexecute, `{0}` was treated as a format field and the command failed with "unbound variables".
    output = animals.bank("explicit", "git", "log", "-1", "--format=%H", "HEAD@{0}")
    assert animals.fish[2] in output and animals.bird[2] in output

    message = 'a "quoted" {braced} message'
    animals.bank("explicit", "git", "commit", "--allow-empty", "-m", message)
    assert ws.git("repoFish", "log", "-1", "--format=%s") == message
    assert ws.git("repoBird", "log", "-1", "--format=%s") == message


def test_status_reports_branch_and_modified_and_staged_counts(animals: Animals) -> None:
    ws = animals.ws
    (ws.path("repoFish") / "Fish.txt").write_text("changed\n")
    (ws.path("repoBird") / "Bird.txt").write_text("changed\n")
    ws.git("repoBird", "add", "Bird.txt")

    output = animals.bank("explicit", "status", "--colorize", "no")
    assert "repoFish : branch: master, modified: 1" in output
    assert "repoBird : branch: master, staged: 1" in output


def test_create_syncfile_from_inside_the_syncrepo_records_paths_relative_to_the_bank(animals: Animals) -> None:
    ws = animals.ws
    ws.init_repo("otherSyncRepo")
    ws.bank("create_syncfile", "../repoFish", "../repoBird", cwd="otherSyncRepo")

    syncfile = ws.read_json("otherSyncRepo/syncfile.json")
    assert syncfile["configuration"]["relativePathToRepositories"] == ".."
    assert syncfile["configuration"]["clone.syncreponame"] == "otherSyncRepo"
    fish = syncfile["repositories"]["repoFish"]
    assert fish["path"] == "repoFish"
    assert fish["sha"] == animals.fish[2]
    assert fish["UnixTimeStamp"] == str(BASE_TIMESTAMP + 200)
    assert fish["branch"] == "master"
    assert fish["revisionNumber"] == "3"
    assert fish["message"] == "committing salmon"


def make_bank_with_remotes(ws: Workspace, fish_path: str, bird_path: str) -> tuple[str, str]:
    """Create fish and bird repos at the given paths, each with a bare origin remote. Return their heads."""
    for repo, filename, line in [(fish_path, "Fish.txt", "trout"), (bird_path, "Bird.txt", "sparrow")]:
        ws.init_repo(repo)
        ws.commit(repo, filename, line, BASE_TIMESTAMP)
        ws.make_bare_remote(repo, Path(repo).name + ".git")
    return ws.head(fish_path), ws.head(bird_path)


def test_populate_clones_the_repos_given_in_the_syncfile(workspace: Workspace) -> None:
    ws = workspace
    fish, bird = make_bank_with_remotes(ws, "repoFish", "repoBird")
    ws.bank("create_syncrepo", "--syncreponame", "zoosyncrepo", "--syncfilename", "joekeeper.json", "repoFish", "repoBird")
    ws.git("zoosyncrepo", "add", "joekeeper.json")
    ws.git("zoosyncrepo", "commit", "--quiet", "-m", "initial")

    for repo in ("repoFish", "repoBird"):
        shutil.rmtree(ws.path(repo))

    output = ws.bank("populate", cwd="zoosyncrepo")
    assert "success! all repos from joekeeper.json were populated." in output
    assert (ws.head("repoFish"), ws.head("repoBird")) == (fish, bird)


def test_populate_handles_nested_syncrepos_and_repos_in_subdirectories(workspace: Workspace) -> None:
    ws = workspace
    fish, bird = make_bank_with_remotes(ws, "repoFish", "animals/repoBird")
    ws.path("foo/bar").mkdir(parents=True)
    ws.bank("create_syncrepo", "--syncreponame", "foo/bar/zoosyncrepo", "--syncfilename", "joekeeper.json", "repoFish", "animals/repoBird")

    syncfile = ws.read_json("foo/bar/zoosyncrepo/joekeeper.json")
    assert syncfile["configuration"]["relativePathToRepositories"] == "../../.."
    assert syncfile["configuration"]["clone.syncreponame"] == "foo/bar/zoosyncrepo"
    assert syncfile["repositories"]["repoBird"]["path"] == "animals/repoBird"

    shutil.rmtree(ws.path("repoFish"))
    shutil.rmtree(ws.path("animals"))
    ws.bank("populate", "--syncfile", "foo/bar/zoosyncrepo/joekeeper.json")
    assert (ws.head("repoFish"), ws.head("animals/repoBird")) == (fish, bird)


def test_absolute_repo_paths_are_stored_absolute(workspace: Workspace) -> None:
    ws = workspace
    make_bank_with_remotes(ws, "repoFish", "elsewhere/repoBird")
    bird_abs = str(ws.path("elsewhere/repoBird"))
    ws.bank("create_syncrepo", "repoFish", bird_abs)

    syncfile = ws.read_json("syncrepo/syncfile.json")
    assert syncfile["repositories"]["repoBird"]["path"] == bird_abs
    assert syncfile["repositories"]["repoFish"]["path"] == "repoFish"
    assert syncfile["configuration"]["relativePathToRepositories"] == ".."


def test_clone_clones_the_syncrepo_and_populates_the_bank(workspace: Workspace) -> None:
    ws = workspace
    fish, bird = make_bank_with_remotes(ws, "original/repoFish", "original/repoBird")
    ws.bank("create_syncrepo", "repoFish", "repoBird", cwd="original")
    ws.git("original/syncrepo", "add", "syncfile.json")
    ws.git("original/syncrepo", "commit", "--quiet", "-m", "initial")
    remote = ws.make_bare_remote("original/syncrepo", "animalsSyncRepo.git")

    ws.path("work").mkdir()
    ws.bank("clone", str(remote), cwd="work")

    assert (ws.path("work/animals/syncrepo/syncfile.json")).is_file()
    assert (ws.head("work/animals/repoFish"), ws.head("work/animals/repoBird")) == (fish, bird)


def test_create_syncfile_reports_missing_syncrepos_and_repos(workspace: Workspace) -> None:
    ws = workspace
    args = ("create_syncfile", "--syncfile", "repoBob/syncfile.json", "repoFish", "repoBird")

    output = ws.bank(*args, ok=False)
    assert "failure! could not locate the syncrepo dir at" in output

    ws.path("repoBob").mkdir()
    output = ws.bank(*args, ok=False)
    assert "repoBob is not a git repository" in output

    ws.init_repo("repoBob")
    output = ws.bank(*args, ok=False)
    assert "there is no repository at" in output
    assert "failure! syncfile repoBob/syncfile.json not created." in output

    ws.path("repoFish").mkdir()
    ws.path("repoBird").mkdir()
    output = ws.bank(*args, ok=False)
    assert "repoFish is not a git repository" in output
    assert "failure! syncfile repoBob/syncfile.json not created." in output

    ws.init_repo("repoFish")  # a repository without any commits
    output = ws.bank(*args, ok=False)
    assert "not able to get the status of repoFish" in output
    assert "failure! not all repos had their state recorded to repoBob/syncfile.json" in output

    output = ws.bank("create_syncrepo", "--syncreponame", "repoBob", "repoFish", "repoBird", ok=False)
    assert "already exists" in output


@pytest.mark.network
def test_quick_start_clone_from_github(workspace: Workspace) -> None:
    """The README Quick Start: clone the public animals example bank."""
    workspace.bank("clone", "https://github.com/testbank/animalsSyncRepo.git", "animals")
    assert workspace.head("animals/repoFish") == "a27368bec17373938b1dcf73638945b89b60a9d0"
    assert workspace.head("animals/repoBird") == "6bf9d646b2aa224b64fb86cbddb4d7ab0f2e37d3"

