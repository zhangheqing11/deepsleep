"""Independent local git repo for agent-written playbook versions (var/playbook-repo).

Layout: ``playbook.md`` + ``VERSION``. Each generation is one commit authored by the
agent and tagged ``vN``; v1 is copied from the team repo and authored by the team.
``rollback`` makes a new commit restoring an old version (history is kept);
``reset_to_initial`` deletes and re-creates the repo for a clean demo.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import shutil
import subprocess

from .config import resolve

_TAG = re.compile(r"^v(\d+)$")


def _decode_git_output(value: bytes | str) -> str:
    """Decode Git output consistently across Windows code pages."""
    if isinstance(value, str):
        return value
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        encoding = "mbcs" if os.name == "nt" else "latin-1"
        return value.decode(encoding, errors="replace")


class PlaybookRepo:
    def __init__(self, config: dict, path: str | Path | None = None):
        self.config = config["repo"]
        self.path = resolve(path or self.config["path"])
        self.file = self.path / self.config["file_name"]

    # -- git plumbing ---------------------------------------------------------------
    def _git(self, *args: str, author: str = "agent") -> str:
        name = self.config[f"{author}_name"]
        email = self.config[f"{author}_email"]
        env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
               "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        cmd = ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
               "-c", "i18n.logOutputEncoding=utf-8",
               "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main", *args]
        result = subprocess.run(cmd, cwd=self.path, env=env, capture_output=True)
        stdout = _decode_git_output(result.stdout)
        stderr = _decode_git_output(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} 失败: {stderr.strip()}")
        return stdout.strip()

    def exists(self) -> bool:
        return (self.path / ".git").is_dir()

    def _commit(self, text: str, version: str, message: str, author: str, tag: bool) -> str:
        self.file.write_text(text, encoding="utf-8")
        (self.path / "VERSION").write_text(version + "\n", encoding="utf-8")
        self._git("add", self.config["file_name"], "VERSION", author=author)
        self._git("commit", "-q", "--allow-empty", "-m", message, author=author)
        if tag:
            self._git("tag", version, author=author)
        return self._git("rev-parse", "HEAD")

    # -- lifecycle ------------------------------------------------------------------
    def init(self, initial_text: str | None = None) -> str:
        """Create the repo with v1 if it does not exist; return HEAD sha."""
        if self.exists():
            return self._git("rev-parse", "HEAD")
        if initial_text is None:
            # Compatibility with configs supplied directly by older callers.
            initial_path = self.config["initial_path"] if "initial_path" in self.config else self.config["v0_path"]
            initial_text = resolve(initial_path).read_text(encoding="utf-8")
        self.path.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q")
        return self._commit(initial_text, "v1", "v1: 团队手写初始版本", author="team", tag=True)

    def reset_to_initial(self, initial_text: str | None = None) -> str:
        """One-click demo reset: wipe the repo and re-create it at v1."""
        configured = resolve(self.config["path"]).resolve()
        target = self.path.resolve()
        ours = self.exists() and (self.path / "VERSION").is_file()
        if target != configured or self.path.name != configured.name or (self.path.exists() and not ours):
            raise RuntimeError(f"拒绝删除非 playbook 版本库路径: {self.path}")
        if self.path.exists():
            def remove_readonly(func, path, _exc_info):
                # Git may leave object/pack files read-only on Windows.
                # Restrict the retry to the path reported by rmtree.
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                func(path)

            shutil.rmtree(self.path, onerror=remove_readonly)
        return self.init(initial_text)

    # Compatibility alias for unmerged callers; resets to initial v1.
    reset_to_v0 = reset_to_initial

    # -- queries --------------------------------------------------------------------
    def current_version(self) -> str:
        return (self.path / "VERSION").read_text(encoding="utf-8").strip()

    def read(self, version: str | None = None) -> str:
        if version is None:
            return self.file.read_text(encoding="utf-8")
        return self._git("show", f"{version}:{self.config['file_name']}") + "\n"

    def versions(self) -> list[str]:
        tags = [t for t in self._git("tag", "--list").splitlines() if _TAG.match(t)]
        return sorted(tags, key=lambda t: int(_TAG.match(t).group(1)))

    def next_version(self) -> str:
        numbers = [int(_TAG.match(t).group(1)) for t in self.versions()]
        return f"v{max(numbers, default=1) + 1}"

    def head(self) -> str:
        return self._git("rev-parse", "HEAD")

    def log(self) -> list[dict]:
        out = self._git("log", "--format=%H%x1f%an%x1f%aI%x1f%s")
        return [dict(zip(("sha", "author", "date", "message"), line.split("\x1f"))) for line in out.splitlines()]

    # -- writes ---------------------------------------------------------------------
    def commit_version(self, text: str, message: str) -> tuple[str, str]:
        """Commit a new agent generation; returns (version, sha)."""
        version = self.next_version()
        sha = self._commit(text, version, f"{version}: {message}", author="agent", tag=True)
        return version, sha

    def rollback(self, version: str) -> str:
        """Restore an earlier version as a new commit (no history rewrite); returns sha."""
        if version not in self.versions():
            raise ValueError(f"不存在的版本: {version}")
        return self._commit(self.read(version), version, f"rollback: 回到 {version}", author="agent", tag=False)
