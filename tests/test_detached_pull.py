import subprocess

from test_setup import setup_path

setup_path()

from banksync.banksync_common import gitPullCommandForRepo, getBranchName, isGitWorkingTreeDir


def run_git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def make_detached_clone(tmp_path, branch_name):
    source = tmp_path / f"source-{branch_name}"
    remote = tmp_path / f"remote-{branch_name}.git"
    clone = tmp_path / f"clone-{branch_name}"

    source.mkdir()
    run_git(["init"], source)
    run_git(["checkout", "-B", branch_name], source)
    run_git(["config", "user.name", "banksync test"], source)
    run_git(["config", "user.email", "banksync@example.invalid"], source)

    (source / "README.txt").write_text(f"{branch_name}\n")
    run_git(["add", "README.txt"], source)
    run_git(["commit", "-m", f"initial {branch_name}"], source)

    run_git(["clone", "--bare", str(source), str(remote)], tmp_path)
    run_git(["clone", str(remote), str(clone)], tmp_path)
    run_git(["checkout", "--detach", "HEAD"], clone)

    return clone


def test_bare_pull_on_detached_master_uses_explicit_remote_branch(tmp_path):
    clone = make_detached_clone(tmp_path, "master")

    assert getBranchName(str(clone)) == "HEAD"
    assert gitPullCommandForRepo(str(clone), []) == "git pull origin master"


def test_bare_pull_on_detached_main_uses_explicit_remote_branch(tmp_path):
    clone = make_detached_clone(tmp_path, "main")

    assert getBranchName(str(clone)) == "HEAD"
    assert gitPullCommandForRepo(str(clone), []) == "git pull origin main"


def test_explicit_pull_arguments_are_left_unchanged(tmp_path):
    clone = make_detached_clone(tmp_path, "master")

    assert gitPullCommandForRepo(str(clone), ["upstream", "feature"]) == "git pull upstream feature"


def test_nested_directory_inside_repo_is_not_treated_as_repo_root(tmp_path):
    repo = tmp_path / "repo"
    nested = repo / "nested"

    repo.mkdir()
    run_git(["init"], repo)
    nested.mkdir()

    assert isGitWorkingTreeDir(str(repo))
    assert not isGitWorkingTreeDir(str(nested))
