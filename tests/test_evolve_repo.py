import pytest

from engine.evolve.repo import PlaybookRepo
from evolve_support import FIXTURE_V0, make_config


def test_lifecycle(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    repo.init()
    assert repo.current_version() == "v0" and repo.versions() == ["v0"]
    assert repo.log()[0]["author"] == "deepsleep-team"
    v0 = repo.read()
    assert v0 == FIXTURE_V0.read_text(encoding="utf-8")

    version, sha = repo.commit_version(v0 + "新规则\n", "补充一条规则")
    assert (version, repo.current_version(), repo.head()) == ("v1", "v1", sha)
    assert repo.log()[0]["author"] == "deepsleep-agent"
    assert repo.read("v1").endswith("新规则\n") and repo.read("v0") == v0

    repo.rollback("v0")
    assert repo.current_version() == "v0" and repo.read() == v0
    assert repo.versions() == ["v0", "v1"] and len(repo.log()) == 3   # history kept
    assert repo.next_version() == "v2"
    with pytest.raises(ValueError):
        repo.rollback("v7")


def test_init_is_idempotent(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    sha = repo.init()
    assert repo.init() == sha


def test_reset_to_v0(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    repo.init()
    repo.commit_version(repo.read() + "x\n", "x")
    repo.reset_to_v0()
    assert repo.versions() == ["v0"] and repo.current_version() == "v0" and len(repo.log()) == 1


def test_reset_refuses_unrelated_path(tmp_path):
    config = make_config(tmp_path)
    repo = PlaybookRepo(config, path=tmp_path / "important")
    (tmp_path / "important").mkdir()
    with pytest.raises(RuntimeError):
        repo.reset_to_v0()
    assert (tmp_path / "important").exists()


def test_reset_refuses_non_repo_dir_with_same_name(tmp_path):
    config = make_config(tmp_path)
    target = tmp_path / "var" / "playbook-repo"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RuntimeError):
        PlaybookRepo(config).reset_to_v0()
    assert (target / "notes.txt").exists()
