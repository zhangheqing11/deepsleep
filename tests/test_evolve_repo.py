import pytest

from engine.evolve.repo import PlaybookRepo
from evolve_support import FIXTURE_INITIAL, make_config


def test_lifecycle(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    repo.init()
    assert repo.current_version() == "v1" and repo.versions() == ["v1"]
    assert repo.log()[0]["author"] == "deepsleep-team"
    v1 = repo.read()
    assert v1 == FIXTURE_INITIAL.read_text(encoding="utf-8")

    version, sha = repo.commit_version(v1 + "新规则\n", "补充一条规则")
    assert (version, repo.current_version(), repo.head()) == ("v2", "v2", sha)
    assert repo.log()[0]["author"] == "deepsleep-agent"
    assert repo.read("v2").endswith("新规则\n") and repo.read("v1") == v1

    repo.rollback("v1")
    assert repo.current_version() == "v1" and repo.read() == v1
    assert repo.versions() == ["v1", "v2"] and len(repo.log()) == 3   # history kept
    assert repo.next_version() == "v3"
    with pytest.raises(ValueError):
        repo.rollback("v7")


def test_init_is_idempotent(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    sha = repo.init()
    assert repo.init() == sha


def test_reset_to_initial(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    repo.init()
    repo.commit_version(repo.read() + "x\n", "x")
    repo.reset_to_initial()
    assert repo.versions() == ["v1"] and repo.current_version() == "v1" and len(repo.log()) == 1


def test_reset_refuses_unrelated_path(tmp_path):
    config = make_config(tmp_path)
    repo = PlaybookRepo(config, path=tmp_path / "important")
    (tmp_path / "important").mkdir()
    with pytest.raises(RuntimeError):
        repo.reset_to_initial()
    assert (tmp_path / "important").exists()


def test_reset_refuses_non_repo_dir_with_same_name(tmp_path):
    config = make_config(tmp_path)
    target = tmp_path / "var" / "playbook-repo"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RuntimeError):
        PlaybookRepo(config).reset_to_initial()
    assert (target / "notes.txt").exists()


def test_legacy_reset_alias(tmp_path):
    repo = PlaybookRepo(make_config(tmp_path))
    repo.init()
    repo.commit_version(repo.read() + "extra\n", "extra")
    assert PlaybookRepo.reset_to_v0 is PlaybookRepo.reset_to_initial
    repo.reset_to_v0()
    assert repo.current_version() == "v1" and repo.versions() == ["v1"]


@pytest.mark.parametrize("use_loader", [False, True])
def test_legacy_path_fallback(tmp_path, use_loader):
    from engine.evolve.config import load_config

    config = make_config(tmp_path)
    config["repo"]["v0_path"] = config["repo"].pop("initial_path")
    if use_loader:
        config = load_config(config)
    repo = PlaybookRepo(config)
    repo.init()
    assert repo.read() == FIXTURE_INITIAL.read_text(encoding="utf-8")


def test_initial_path_takes_precedence(tmp_path):
    from engine.evolve.config import load_config

    config = make_config(tmp_path)
    config["repo"]["v0_path"] = str(tmp_path / "missing.md")
    repo = PlaybookRepo(load_config(config))
    repo.init()
    assert repo.read() == FIXTURE_INITIAL.read_text(encoding="utf-8")
