"""End to end tests that drive `bank` against real git repositories in a scratch directory."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
    assert "failure! syncfile repoBob/syncfile.json not created." in output
    assert not ws.path("repoBob/syncfile.json").exists()  # an incomplete syncfile is never written

    output = ws.bank("create_syncrepo", "--syncreponame", "repoBob", "repoFish", "repoBird", ok=False)
    assert "already exists" in output

    # A failed create_syncrepo removes the syncrepo it created, so it can be rerun once the repos are fixed.
    ws.bank("create_syncrepo", "--syncreponame", "zoosyncrepo", "repoFish", "repoBird", ok=False)
    assert not ws.path("zoosyncrepo").exists()


def test_create_syncfile_rejects_two_repos_with_the_same_name(workspace: Workspace) -> None:
    ws = workspace
    ws.init_repo("syncrepo")
    for repo in ("one/repoFish", "two/repoFish"):
        ws.init_repo(repo)
        ws.commit(repo, "Fish.txt", "trout", BASE_TIMESTAMP)
    output = ws.bank("create_syncfile", "--syncfile", "syncrepo/syncfile.json", "one/repoFish", "two/repoFish", ok=False)
    assert "are both named repoFish" in output
    assert not ws.path("syncrepo/syncfile.json").exists()


def test_bisect_keeps_its_state_out_of_the_syncrepo_working_tree(animals: Animals) -> None:
    ws = animals.ws
    sp1, _, sp3 = animals.sync_points
    animals.bank("explicit", "bisect", "start")
    animals.bank("explicit", "bisect", "good", sp1)
    animals.bank("explicit", "bisect", "bad", sp3)
    assert ws.git("repoSyncFile", "status", "--porcelain") == ""
    assert ws.path("repoSyncFile/.git/banksync-bisect-restore.json").is_file()

    animals.bank("explicit", "bisect", "reset")
    assert not ws.path("repoSyncFile/.git/banksync-bisect-restore.json").exists()


def test_bisect_reset_reports_repos_it_could_not_restore(animals: Animals) -> None:
    ws = animals.ws
    sp1, _, sp3 = animals.sync_points
    animals.bank("explicit", "bisect", "start")
    animals.bank("explicit", "bisect", "good", sp1)
    animals.bank("explicit", "bisect", "bad", sp3)

    # A local change that conflicts with the original branch stops repoFish from being restored.
    (ws.path("repoFish") / "Fish.txt").write_text("local change\n")
    output = animals.bank("explicit", "bisect", "reset", ok=False)
    assert "repoFish: failed to restore repository state to 'master'" in output
    assert "failure! not all repo states restored after bisect." in output
    assert ws.branch("repoBird") == "master"


def test_bisect_run_syncs_the_bank_before_each_step(animals: Animals) -> None:
    ws = animals.ws
    sp1, sp2, sp3 = animals.sync_points
    animals.bank("explicit", "bisect", "start", sp3, sp1)

    # The step command runs in the syncrepo; it fails ("bad") once repoFish contains salmon.
    output = animals.bank("explicit", "bisect", "run", "sh", "-c", "! grep -q salmon ../repoFish/Fish.txt")
    assert f"{sp3} is the first bad commit" in output

    animals.bank("explicit", "bisect", "reset")
    assert animals.heads() == animals.at(3)


def test_bisect_run_needs_a_command(animals: Animals) -> None:
    animals.bank("explicit", "bisect", "start")
    output = animals.bank("explicit", "bisect", "run", ok=False)
    assert "needs a command to run" in output


def test_record_repos_keeps_keys_banksync_does_not_write(animals: Animals) -> None:
    ws = animals.ws
    syncfile = ws.read_json(SYNCFILE)
    syncfile["repositories"]["repoFish"]["notes"] = "pinned for the 2.0 release"
    ws.write_json(SYNCFILE, syncfile)

    ws.commit("repoFish", "Fish.txt", "pike", BASE_TIMESTAMP + 300)
    animals.bank("explicit", "record_repos")
    fish = ws.read_json(SYNCFILE)["repositories"]["repoFish"]
    assert fish["notes"] == "pinned for the 2.0 release"
    assert fish["sha"] == ws.head("repoFish")


def test_git_accepts_any_git_command_and_passes_options_and_double_dash_through(animals: Animals) -> None:
    ws = animals.ws
    # `--color` is not taken as an abbreviation of bank's --colorize.
    output = animals.bank("explicit", "git", "log", "-1", "--color=never", "--format=%s")
    assert "committing salmon" in output and "committing eagle" in output

    # Everything after `--` reaches git as written: here a pathspec rather than a revision.
    output = animals.bank("explicit", "git", "log", "--format=%s", "--", "Fish.txt", "--colorize", "no")
    assert "committing trout" in output

    # Commands outside the approved list run, with a warning.
    output = animals.bank("explicit", "git", "count-objects")
    assert "might not make sense" in output
    animals.bank("explicit", "git", "switch", "--quiet", "--detach", "HEAD~1")
    assert animals.heads() == animals.at(2)


def test_create_syncrepo_accepts_a_syncfilename_path_inside_the_syncrepo(animals: Animals) -> None:
    ws = animals.ws
    ws.bank(
        "create_syncrepo",
        "--syncreponame", "some/path/zoo",
        "--syncfilename", "some/path/zoo/devCollection.json",
        "repoFish", "repoBird",
    )  # fmt: skip
    assert ws.path("some/path/zoo/devCollection.json").is_file()

    output = ws.bank("create_syncrepo", "--syncreponame", "other", "--syncfilename", "some/devCollection.json", "repoFish", ok=False)
    assert "does not live directly inside other" in output


def test_populate_skips_repos_that_are_already_present(workspace: Workspace) -> None:
    ws = workspace
    fish, bird = make_bank_with_remotes(ws, "repoFish", "repoBird")
    ws.bank("create_syncrepo", "repoFish", "repoBird")
    shutil.rmtree(ws.path("repoBird"))

    output = ws.bank("populate", cwd="syncrepo")
    assert "repoFish: already present at" in output
    assert "repoBird: cloned repo to" in output
    assert (ws.head("repoFish"), ws.head("repoBird")) == (fish, bird)


def test_clone_uses_the_syncreponame_and_syncfile_name_recorded_in_the_syncfile(workspace: Workspace) -> None:
    ws = workspace
    fish, bird = make_bank_with_remotes(ws, "original/repoFish", "original/repoBird")
    ws.bank("create_syncrepo", "--syncreponame", "control", "--syncfilename", "earthanimals.json", "repoFish", "repoBird", cwd="original")
    ws.git("original/control", "add", "earthanimals.json")
    ws.git("original/control", "commit", "--quiet", "-m", "initial")
    remote = ws.make_bare_remote("original/control", "animalsSyncRepo.git")

    ws.path("work").mkdir()
    ws.bank("clone", str(remote), "zoo", cwd="work")
    assert ws.path("work/zoo/control/earthanimals.json").is_file()
    assert (ws.head("work/zoo/repoFish"), ws.head("work/zoo/repoBird")) == (fish, bird)

    output = ws.bank("clone", str(remote), "zoo", cwd="work", ok=False)
    assert "already exists and is not an empty directory" in output


def test_options_layer_rc_file_then_syncfile_then_command_line(animals: Animals) -> None:
    ws = animals.ws
    animals.checkout_syncrepo(animals.sync_points[0])
    syncfile = ws.read_json(SYNCFILE)
    for info in syncfile["repositories"].values():
        del info["sha"]  # leave only the timestamps, so the matching option decides whether the sync succeeds
    ws.write_json(SYNCFILE, syncfile)

    rc_file = Path(os.environ["HOME"]) / ".bankconfigrc"
    rc_file.write_text("[sync]\nmatching = shaOnly\n")
    output = animals.bank("explicit", "sync", ok=False)
    assert "failed to check out specified revision by any method" in output

    syncfile["configuration"]["sync.matching"] = "timestamp"  # the syncfile overrides ~/.bankconfigrc
    ws.write_json(SYNCFILE, syncfile)
    animals.bank("explicit", "sync")
    assert animals.heads() == animals.at(1)

    syncfile["configuration"]["sync.matching"] = "shaOnly"
    ws.write_json(SYNCFILE, syncfile)
    animals.bank("explicit", "sync", "--matching", "timestamp")  # the command line overrides the syncfile

    syncfile["configuration"]["sync.matching"] = "sometimes"
    ws.write_json(SYNCFILE, syncfile)
    output = animals.bank("explicit", "sync", ok=False)
    assert "invalid value 'sometimes' for option sync.matching" in output


def test_output_is_only_colored_on_request_when_not_on_a_terminal(animals: Animals) -> None:
    def raw_output(*args: str) -> str:
        result = subprocess.run([sys.executable, "-m", "banksync", "status", "--syncfile", SYNCFILE, *args], cwd=animals.ws.root, capture_output=True, text=True)
        return result.stdout

    assert "\x1b[" not in raw_output()
    assert "\x1b[" in raw_output("--colorize", "yes")


def test_syncfiles_that_need_a_newer_banksync_are_refused(animals: Animals) -> None:
    ws = animals.ws
    syncfile = ws.read_json(SYNCFILE)
    syncfile["configuration"]["requiredBanksyncVersion"] = "99.0"
    ws.write_json(SYNCFILE, syncfile)
    for style in ("explicit", "syncrepo"):
        output = animals.bank(style, "status", ok=False)
        assert "needs at least banksync version 99.0" in output


@pytest.mark.network
def test_quick_start_clone_from_github(workspace: Workspace) -> None:
    """The README Quick Start: clone the public animals example bank."""
    workspace.bank("clone", "https://github.com/testbank/animalsSyncRepo.git", "animals")
    assert workspace.head("animals/repoFish") == "a27368bec17373938b1dcf73638945b89b60a9d0"
    assert workspace.head("animals/repoBird") == "6bf9d646b2aa224b64fb86cbddb4d7ab0f2e37d3"

