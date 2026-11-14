import multiprocessing
import os
from pathlib import Path
import stat
import sys
import time

import pytest

from engine.file_lock import file_lock


def _hold_lock(path, ready, release):
    with file_lock(path):
        ready.set()
        release.wait(5)


def test_file_lock_releases_after_exception(tmp_path):
    path = tmp_path / "demo.lock"
    with pytest.raises(RuntimeError):
        with file_lock(path, blocking=False):
            raise RuntimeError("boom")
    with file_lock(path, blocking=False):
        pass


def test_file_lock_rejects_second_process_and_reacquires(tmp_path):
    path = tmp_path / "demo.lock"
    ready = multiprocessing.Event()
    release = multiprocessing.Event()
    process = multiprocessing.Process(target=_hold_lock, args=(path, ready, release))
    process.start()
    try:
        assert ready.wait(5)
        with pytest.raises(BlockingIOError):
            with file_lock(path, blocking=False):
                pass
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
    assert process.exitcode == 0
    with file_lock(path, blocking=False):
        pass


def test_windows_imports_do_not_require_fcntl():
    import engine.demo  # noqa: F401
    import engine.integ_trial  # noqa: F401


def test_request_budget_uses_sidecar_and_enforces_limit(tmp_path):
    from engine.integ_trial import RequestBudget, RequestBudgetExceeded

    path = tmp_path / "budget.log"
    budget = RequestBudget(path, 2)
    budget.reserve()
    budget.reserve()
    with pytest.raises(RequestBudgetExceeded):
        budget.reserve()
    assert path.with_name("budget.log.lock").exists()


def test_git_output_decode_handles_utf8_and_replacement():
    from engine.evolve.repo import _decode_git_output

    assert _decode_git_output("提交信息") == "提交信息"
    assert _decode_git_output("提交信息".encode("utf-8")) == "提交信息"
    assert "�" in _decode_git_output(b"broken\xff")


def test_reset_handles_readonly_git_file(tmp_path):
    from engine.evolve.repo import PlaybookRepo
    from evolve_support import make_config

    repo = PlaybookRepo(make_config(tmp_path))
    try:
        repo.init()
    except RuntimeError as exc:
        if "cannot lock ref" in str(exc):
            pytest.skip("managed temporary directory does not permit nested Git refs")
        raise
    readonly = repo.path / ".git" / "objects" / "readonly.pack"
    readonly.write_bytes(b"placeholder")
    readonly.chmod(stat.S_IREAD)
    repo.reset_to_initial()
    assert repo.current_version() == "v1"
