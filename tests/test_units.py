"""Unit tests for banksync's helper modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from banksync import git
from banksync.console import Console, Level
from banksync.options import Options, flatten, merge, read_rc_file, syncfile_layer
from banksync.shell import CommandFailed, describe, run
from banksync.util import BanksyncError, repo_name_from_url, version_less_or_equal
from conftest import BASE_TIMESTAMP, Workspace


# ----- util -----


@pytest.mark.parametrize(
    ("version1", "version2", "expected"),
    [
        ("1.2.3", "1.2.3", True),
        ("1.2.3", "2.2.3", True),
        ("2.2.3", "1.2.3", False),
        ("2.2.3.4", "2.2.3", False),
        ("2.2.3", "2.2.3.4", True),
        ("2.2.3.0", "2.2.3", True),
        ("2.2.3", "2.2.3.0", True),
        ("1.2", "2.0.0", True),
        ("2", "3", True),
        ("0.9.10", "0.9.9", False),
    ],
)
def test_version_less_or_equal(version1: str, version2: str, expected: bool) -> None:
    assert version_less_or_equal(version1, version2) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://example.com/project_Foo_sync_repo.git", "project_Foo"),
        ("https://example.com/project_name_sync_repo.git", "project_name"),
        ("http://example.com/projectNameSyncRepo.git", "projectName"),
        ("https://example.com/someProjectRepo.git", "someProjectRepo"),
        ("https://github.com/testbank/animalsSyncRepo.git", "animals"),
        ("git@github.com:testbank/animalsSyncRepo.git", "animals"),
        ("https://example.com/project_boo/sync_repo.git", "WrapperProject"),
        ("https://example.com/syncRepo.git", "WrapperProject"),
    ],
)
def test_repo_name_from_url(url: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert repo_name_from_url(url) == expected


# ----- options -----


def test_flatten_and_merge_layers() -> None:
    rc = flatten({"sec1": {"key1": "value1", "Key2": "value2"}, "sec2": {"keyA": "valueA"}})
    assert rc == {"sec1.key1": "value1", "sec1.key2": "value2", "sec2.keya": "valueA"}
    assert merge(rc, {"sec1.key2": "fish"}, {"sec2.keya": "bird"}) == {
        "sec1.key1": "value1",
        "sec1.key2": "fish",
        "sec2.keya": "bird",
    }


def test_rc_file_options_are_validated(tmp_path: Path) -> None:
    rc = tmp_path / "bankconfigrc"
    rc.write_text("[general]\nverbosity = 3\ncolorize = no\n\n[sync]\nmatching = shaOnly\n")
    options = Options.resolve(read_rc_file(rc))
    assert (options.verbosity, options.colorize, options.matching) == (3, False, "shaOnly")

    with pytest.raises(BanksyncError, match="invalid value 'sometimes' for option sync.matching"):
        Options.resolve({"sync.matching": "sometimes"})
    with pytest.raises(BanksyncError, match="general.verbosity"):
        Options.resolve({"general.verbosity": "7"})


def test_syncfile_configuration_only_supplies_general_and_sync_options() -> None:
    configuration = {
        "relativePathToRepositories": "..",
        "clone.syncreponame": "syncrepo",
        "sync.matching": "timestamp",
        "sync.syncBranches": "yes",
        "general.verbosity": 3,
        "create_syncrepo.syncreponame": "elsewhere",
    }
    assert syncfile_layer(configuration) == {"sync.matching": "timestamp", "sync.syncbranches": "yes", "general.verbosity": "3"}


def test_colorize_auto_follows_the_terminal_and_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert Options.resolve().colorize
    assert not Options.resolve({"general.colorize": "no"}).colorize

    monkeypatch.setenv("NO_COLOR", "1")
    assert not Options.resolve().colorize
    assert Options.resolve({"general.colorize": "yes"}).colorize

    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert not Options.resolve().colorize


# ----- console -----


def test_console_respects_verbosity_and_colorize(capsys: pytest.CaptureFixture[str]) -> None:
    console = Console(verbosity=Level.SUMMARY, colorize=False)
    console.say("per repo detail")
    console.success("all done")
    assert capsys.readouterr().out == "all done\n"

    console.colorize = True
    assert console.red("x") == "\033[31mx\033[0m"


# ----- shell -----


def test_run_passes_arguments_through_untouched(tmp_path: Path) -> None:
    argument = "a {brace} 'quote' \"double\" $HOME *.json HEAD@{0}"
    result = run("printf", "%s", argument, cwd=tmp_path)
    assert result.ok
    assert result.stdout == argument


def test_run_reports_failures(tmp_path: Path) -> None:
    result = run("git", "rev-parse", "--verify", "no-such-ref", cwd=tmp_path)
    assert not result.ok
    with pytest.raises(CommandFailed, match="git rev-parse --verify no-such-ref"):
        run("git", "rev-parse", "--verify", "no-such-ref", cwd=tmp_path, check=True)


def test_dryrun_does_not_run_the_command(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    assert run("touch", marker, cwd=tmp_path, dryrun=True).ok
    assert not marker.exists()


def test_describe_shows_the_directory_when_it_is_not_the_current_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "repo").mkdir()
    monkeypatch.chdir(tmp_path)
    assert describe(("git", "commit", "-m", "two words")) == "$ git commit -m 'two words'"
    assert describe(("git", "status"), tmp_path / "repo") == "(repo) $ git status"


# ----- git queries -----


def test_current_state_records_the_checked_out_commit(workspace: Workspace) -> None:
    ws = workspace
    ws.init_repo("repo")
    ws.commit("repo", "file.txt", "first", BASE_TIMESTAMP)
    ws.git("repo", "commit", "--quiet", "--allow-empty", "-m", 'Subject with "quotes"\n\nBody line {braces}')
    ws.git("repo", "remote", "add", "upstream", "https://example.com/repo.git")

    state = git.current_state(ws.path("repo"), "repo")
    assert state is not None
    assert state["sha"] == ws.head("repo")
    assert state["branch"] == "master"
    assert state["revisionNumber"] == "2"
    assert state["message"] == 'Subject with "quotes"\n\nBody line {braces}'
    assert state["cloneURL"] == "https://example.com/repo.git"  # the only remote, even though it is not origin


def test_current_state_of_a_repo_without_commits_is_none(workspace: Workspace) -> None:
    workspace.init_repo("empty")
    assert git.current_state(workspace.path("empty"), "empty") is None


def test_nested_directory_inside_repo_is_not_treated_as_repo_root(workspace: Workspace) -> None:
    repo = workspace.init_repo("repo")
    (repo / "nested").mkdir()
    assert git.is_working_tree_root(repo)
    assert not git.is_working_tree_root(repo / "nested")


def test_linked_worktree_is_a_repo_root(workspace: Workspace) -> None:
    ws = workspace
    ws.init_repo("repo")
    ws.commit("repo", "file.txt", "first", BASE_TIMESTAMP)
    ws.git("repo", "worktree", "add", "--quiet", "--detach", str(ws.path("linked")))
    assert (ws.path("linked") / ".git").is_file()
    assert git.is_working_tree_root(ws.path("linked"))


def make_detached_clone(ws: Workspace, branch: str) -> Path:
    ws.init_repo("source")
    ws.git("source", "checkout", "--quiet", "-B", branch)
    ws.commit("source", "README.txt", branch, BASE_TIMESTAMP)
    ws.git(".", "clone", "--quiet", "--bare", "source", "remote.git")
    ws.git(".", "clone", "--quiet", "remote.git", "clone")
    ws.git("clone", "checkout", "--quiet", "--detach", "HEAD")
    return ws.path("clone")


@pytest.mark.parametrize("branch", ["master", "main"])
def test_bare_pull_on_a_detached_head_pulls_the_remote_default_branch(workspace: Workspace, branch: str) -> None:
    clone = make_detached_clone(workspace, branch)
    assert git.branch_name(clone) == "HEAD"
    assert git.pull_arguments(clone, []) == ["pull", "origin", branch]


def test_explicit_pull_arguments_are_left_unchanged(workspace: Workspace) -> None:
    clone = make_detached_clone(workspace, "master")
    assert git.pull_arguments(clone, ["upstream", "feature"]) == ["pull", "upstream", "feature"]
