"""Adversarial launch-time source provenance tests."""

import subprocess

import pytest

from mineocclude.prospective.source_provenance import (
    CriticalSource,
    ProvenanceViolation,
    sha256_file,
    verify_sources,
)


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "controller.py").write_bytes(b"print('run')\n")
    _git(tmp_path, "add", "controller.py")
    _git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def _head(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.decode().strip()


def _source(repo, path="controller.py"):
    return CriticalSource(path, sha256_file(repo / path))


def test_correct_tracked_file_sha_and_commit_verify(repo):
    receipt = verify_sources(repo, [_source(repo)], expected_head=_head(repo))
    assert receipt.verified
    assert receipt.sources[0]["tree_matches_pin"]
    assert receipt.sources[0]["index_matches_tree"]
    assert receipt.sources[0]["working_tree_matches_tree"]
    assert receipt.sources[0]["tree_mode"] == "100644"
    assert receipt.sources[0]["index_mode_matches_tree"]
    assert receipt.sources[0]["working_tree_mode_matches_tree"]
    receipt.require_verified()


def test_index_only_executable_bit_change_fails(repo):
    pinned = _source(repo)
    _git(repo, "update-index", "--chmod=+x", "controller.py")
    receipt = verify_sources(repo, [pinned], expected_head=_head(repo))
    assert not receipt.verified
    assert receipt.sources[0]["index_mode"] == "100755"
    assert not receipt.sources[0]["index_mode_matches_tree"]
    assert any("staging index mode" in issue for issue in receipt.violations)


def test_worktree_only_executable_bit_change_fails(repo):
    pinned = _source(repo)
    _git(repo, "config", "core.filemode", "true")
    (repo / "controller.py").chmod(0o755)
    receipt = verify_sources(repo, [pinned], expected_head=_head(repo))
    assert not receipt.verified
    assert receipt.sources[0]["working_tree_mode"] == "100755"
    assert not receipt.sources[0]["working_tree_mode_matches_tree"]
    assert any("working-tree mode" in issue for issue in receipt.violations)


def test_file_only_staged_and_absent_from_expected_head_fails(repo):
    (repo / "staged_only.py").write_text("x = 1\n")
    _git(repo, "add", "staged_only.py")
    receipt = verify_sources(repo, [_source(repo, "staged_only.py")], expected_head=_head(repo))
    assert not receipt.verified
    assert any("missing from expected commit" in issue for issue in receipt.violations)


def test_staged_modification_with_clean_working_tree_fails(repo):
    original = (repo / "controller.py").read_bytes()
    (repo / "controller.py").write_bytes(b"print('staged edit')\n")
    _git(repo, "add", "controller.py")
    (repo / "controller.py").write_bytes(original)
    receipt = verify_sources(repo, [CriticalSource("controller.py", sha256_file(repo / "controller.py"))], expected_head=_head(repo))
    assert not receipt.verified
    assert any("staging index differs" in issue for issue in receipt.violations)


def test_unstaged_modification_fails(repo):
    pinned = _source(repo)
    (repo / "controller.py").write_text("print('unstaged edit')\n")
    receipt = verify_sources(repo, [pinned], expected_head=_head(repo))
    assert not receipt.verified
    assert any("working-tree bytes differ" in issue for issue in receipt.violations)


@pytest.mark.parametrize("staged", [False, True])
def test_deletion_fails(repo, staged):
    pinned = _source(repo)
    (repo / "controller.py").unlink()
    if staged:
        _git(repo, "add", "-u")
    receipt = verify_sources(repo, [pinned], expected_head=_head(repo))
    assert not receipt.verified
    assert any("missing from working tree" in issue for issue in receipt.violations)


def test_renamed_or_moved_critical_file_fails(repo):
    pinned = _source(repo)
    _git(repo, "mv", "controller.py", "moved.py")
    receipt = verify_sources(repo, [pinned], expected_head=_head(repo))
    assert not receipt.verified
    assert any("absent or deleted in staging index" in issue for issue in receipt.violations)


def test_wrong_expected_commit_fails(repo):
    original = _head(repo)
    (repo / "controller.py").write_text("print('second')\n")
    _git(repo, "add", "controller.py")
    _git(repo, "commit", "-qm", "second")
    receipt = verify_sources(repo, [CriticalSource("controller.py", "0" * 64)], expected_head=original)
    assert not receipt.verified
    assert any("HEAD" in issue for issue in receipt.violations)


def test_wrong_sha_fails(repo):
    receipt = verify_sources(
        repo,
        [CriticalSource("controller.py", "0" * 64)],
        expected_head=_head(repo),
    )
    assert not receipt.verified
    assert any("pinned" in issue for issue in receipt.violations)


def test_missing_expected_commit_and_path_fail(repo):
    receipt = verify_sources(
        repo,
        [CriticalSource("absent.py", "0" * 64)],
        expected_head="0" * 40,
    )
    assert not receipt.verified
    assert any("missing or invalid" in issue for issue in receipt.violations)
    with pytest.raises(ProvenanceViolation):
        receipt.require_verified()


def test_empty_source_enumeration_fails(repo):
    assert not verify_sources(repo, [], expected_head=_head(repo)).verified


def test_receipt_does_not_upgrade_historical_provenance(repo):
    receipt = verify_sources(repo, [_source(repo)], expected_head=_head(repo)).to_dict()
    assert receipt["does_not_repair_historical_p3_provenance"] is True
    assert receipt["expected_commit"] == _head(repo)
