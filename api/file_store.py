"""Read-only view of engine artifacts. Never initialize a repo or write under var/."""

from datetime import datetime, timezone
from difflib import unified_diff
from functools import wraps
from pathlib import Path
import json
import re

from api.errors import APIError
from api.run_models import RunState
from contracts.validate import load_validators, read_json, validate_document
from engine.evolve.config import load_config
from engine.evolve.evidence import run_evidence
from engine.evolve.repo import PlaybookRepo

ID_PATTERN = r"^[A-Za-z0-9._-]{1,80}$"
VISITOR_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
VERSION_PATTERN = r"^v[0-9]{1,4}$"


def identifier(value: str, pattern: str = ID_PATTERN) -> str:
    if not re.fullmatch(pattern, value) or value in {".", ".."}:
        raise APIError(422, "VALIDATION_ERROR", "请求标识不合法。")
    return value


def read_errors(method):
    """Turn corrupt, disappearing or unreadable artifacts into a safe HTTP error."""
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, RuntimeError):
            raise APIError(404, "DATA_UNAVAILABLE", "产物暂不可读取，请稍后重试。") from None
    return guarded


def timestamp(value) -> float:
    if not value:
        return 0
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def execution_mode(document: dict) -> str:
    return "mock" if document.get("models", {}).get("agent", "").startswith("mock") else "real"


class FileStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.validators = load_validators()

    def _path(self, *parts: str) -> Path:
        path = self.root
        for part in parts:
            for component in Path(part).parts:
                if component in {"..", "/"}:
                    raise APIError(404, "NOT_FOUND", "资源不存在。")
                path = path / component
                # Reject even in-root symlinks: an allowed filename must not alias .env.
                if path.is_symlink():
                    raise APIError(404, "NOT_FOUND", "资源不存在。")
        if not path.resolve().is_relative_to(self.root):
            raise APIError(404, "NOT_FOUND", "资源不存在。")
        return path

    def _json(self, *parts: str, optional=False, schema=None) -> dict | None:
        path = self._path(*parts)
        try:
            data = read_json(path)
        except FileNotFoundError:
            if optional:
                return None
            raise APIError(404, "NOT_FOUND", "产物不存在。") from None
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        json.dumps(data, allow_nan=False)  # Also reject numeric overflow such as 1e999.
        if schema and validate_document(data, schema, self.validators, {}):
            raise ValueError("Invalid contract document")
        return data

    def _directories(self, area: str) -> list[str]:
        parent = self._path("var", area)
        if not parent.exists():
            return []
        return sorted(p.name for p in parent.iterdir() if p.is_dir() and not p.is_symlink()
                      and re.fullmatch(ID_PATTERN, p.name))

    @read_errors
    def experiment(self) -> dict:
        data = self._json("var/demo/experiment.json", optional=True)
        return data if data is not None else {"available": False}

    def _plan(self, run_id: str) -> dict:
        experiment = self.experiment()
        for role in ("run1", "run2", "control"):
            entry = experiment.get(role)
            if isinstance(entry, dict) and entry.get("run_id") == run_id:
                return {"role": role, "label": {"run1": "运行 1", "run2": "运行 2", "control": "对照"}[role],
                        **entry}
        return {}

    def _session_docs(self, run_id: str) -> dict:
        parent = self._path("var/runs", run_id, "sessions")
        if not parent.exists():
            return {}
        return {p.stem: self.session(run_id, p.stem) for p in sorted(parent.glob("*.json"))
                if re.fullmatch(VISITOR_PATTERN, p.stem) and not p.is_symlink()}

    def _run(self, run_id: str) -> tuple[dict | None, dict, dict]:
        identifier(run_id)
        directory = self._path("var/runs", run_id)
        report = self._json("var/runs", run_id, "run_report.json", optional=True, schema="run_report")
        sessions = self._session_docs(run_id)
        summary = self._json("var/runs", run_id, "summary.json", optional=True) or {}
        if report is None and not self._path("var/runs", run_id, "sessions").is_dir() and not summary:
            raise APIError(404, "NOT_FOUND", "运行不存在。")
        if report is not None and report["run_id"] != run_id:
            raise ValueError("Mismatched run")
        plan = self._plan(run_id)
        source = report or next(iter(sessions.values()), {})
        meta = {key: (report or {}).get(key, plan.get(key)) for key in
                ("label", "role", "playbook_version", "split", "duration_s", "metrics")}
        meta["playbook_version"] = meta["playbook_version"] or source.get("playbook_version")
        total = plan.get("n_visitors", summary.get("attempted", (report or {}).get("n_visitors")))
        if total is not None and (type(total) is not int or total < len(sessions)):
            raise ValueError("Invalid planned total")
        meta.update(run_id=run_id, n_visitors=total,
                    created_at=(report or {}).get("created_at") or plan.get("created_at")
                    or datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc).isoformat(),
                    status="completed" if report is not None else "running",
                    execution_mode=execution_mode(source))
        return report, sessions, meta

    @read_errors
    def runs(self, limit=50) -> dict:
        items = []
        for run_id in self._directories("runs"):
            try:
                meta = self.run_item(run_id)
                items.append(meta)
            except APIError:
                continue  # One unfinished/corrupt directory must not hide all runs.
        return {"items": sorted(items, key=lambda i: timestamp(i["created_at"]), reverse=True)[:limit]}

    @read_errors
    def run_item(self, run_id: str) -> dict:
        meta = self._run(run_id)[2]
        timestamp(meta["created_at"])
        return meta

    @read_errors
    def state(self, run_id: str) -> dict:
        report, sessions, meta = self._run(run_id)
        data = {"run_id": run_id, "status": "succeeded" if report is not None else "running",
                "execution_mode": meta["execution_mode"], "split": meta["split"],
                "playbook_version": meta["playbook_version"],
                "progress": {"total": meta["n_visitors"],
                             "completed": sum(s["status"] != "error" for s in sessions.values()),
                             "failed": sum(s["status"] == "error" for s in sessions.values())},
                "elapsed_ms": int((meta["duration_s"] or 0) * 1000),
                "report_available": report is not None, "error": None}
        return RunState.model_validate(data).model_dump()

    @read_errors
    def report(self, run_id: str) -> dict:
        report, _, _ = self._run(run_id)
        if report is None:
            raise APIError(404, "NOT_READY", "运行报告尚未生成。")
        return report

    @read_errors
    def sessions(self, run_id: str) -> dict:
        report, sessions, _ = self._run(run_id)
        ids = sorted(set(sessions) | {row["visitor_id"] for row in (report or {}).get("per_visitor", [])})
        return {"items": [{"visitor_id": vid,
                           "status": ("failed" if sessions[vid]["status"] == "error" else "succeeded")
                           if vid in sessions else ("succeeded" if report else "running"),
                           "session_available": vid in sessions,
                           "session_status": sessions[vid]["status"] if vid in sessions else None}
                          for vid in ids]}

    @read_errors
    def session(self, run_id: str, visitor_id: str) -> dict:
        identifier(run_id)
        identifier(visitor_id, VISITOR_PATTERN)
        data = self._json("var/runs", run_id, "sessions", visitor_id + ".json", schema="session")
        if data["run_id"] != run_id or data["visitor_id"] != visitor_id:
            raise ValueError("Mismatched session")
        return data

    @read_errors
    def evidence(self, run_id: str) -> dict:
        report, sessions, _ = self._run(run_id)
        traces = {vid: self._json("var/runs", run_id, "trace", identifier(vid, VISITOR_PATTERN) + ".json",
                                  optional=True) or {}
                  for vid in set(sessions) | {r["visitor_id"] for r in (report or {}).get("per_visitor", [])}}
        if report is None:
            return {"available": False}
        evidence = run_evidence(report["per_visitor"], sessions, traces, {})
        if not evidence["summary"]["n_with_path_probs"]:
            return {"available": False}
        return {**evidence, "contract": False}

    @read_errors
    def evolutions(self, limit=20) -> dict:
        items = []
        for eid in self._directories("evolve"):
            try:
                items.append(self.evolution_item(eid))
            except APIError:
                continue
        return {"items": sorted(items, key=lambda i: timestamp(i["created_at"]), reverse=True)[:limit]}

    @read_errors
    def evolution_item(self, evolution_id: str) -> dict:
        identifier(evolution_id)
        doc = self._json("var/evolve", evolution_id, "evolution.json", optional=True, schema="evolution")
        status = self._json("var/evolve", evolution_id, "status.json", optional=True) or {}
        if doc is None and not status:
            raise APIError(404, "NOT_FOUND", "进化记录不存在。")
        source = doc or status
        if source.get("evolution_id") != evolution_id:
            raise ValueError("Mismatched evolution")
        created = source.get("created_at") or status.get("updated_at")
        timestamp(created)
        return {"evolution_id": evolution_id, "created_at": created,
                **{k: source.get(k) for k in ("from_version", "to_version", "source_run_id", "chosen")},
                "outcome": doc["outcome"] if doc else None,
                "phase": status.get("phase", "done" if doc else None)}

    @read_errors
    def evolution(self, evolution_id: str) -> dict:
        identifier(evolution_id)
        doc = self._json("var/evolve", evolution_id, "evolution.json", optional=True, schema="evolution")
        if doc is not None:
            if doc["evolution_id"] != evolution_id:
                raise ValueError("Mismatched evolution")
            return doc
        if self._json("var/evolve", evolution_id, "status.json", optional=True) is not None:
            raise APIError(404, "NOT_READY", "进化仍在进行，最终产物尚未生成。")
        raise APIError(404, "NOT_FOUND", "进化记录不存在。")

    @read_errors
    def evolution_status(self, evolution_id: str) -> dict:
        return self._json("var/evolve", identifier(evolution_id), "status.json")

    @read_errors
    def insights(self, evolution_id: str) -> dict:
        return self._json("var/evolve", identifier(evolution_id), "insights.json")

    def _repo(self) -> PlaybookRepo:
        path = self._path("var/playbook-repo")
        self._path("var/playbook-repo/.git")
        repo = PlaybookRepo(load_config(), path=path)
        if not repo.exists():
            raise APIError(404, "NOT_FOUND", "Playbook 版本库尚不存在。")
        return repo

    @read_errors
    def versions(self) -> dict:
        repo = self._repo()
        head = repo.head()
        items = []
        for version in repo.versions():
            if not re.fullmatch(VERSION_PATTERN, version):
                continue
            sha, author, committed, message = repo._git(
                "show", "-s", "--format=%H%x1f%an%x1f%cI%x1f%s", "refs/tags/" + version,
                "--").split("\x1f", 3)
            items.append(dict(version=version, sha=sha, author=author, message=message,
                              committed_at=committed, is_head=sha == head))
        return {"items": items}

    @read_errors
    def playbook(self, version: str) -> dict:
        identifier(version, VERSION_PATTERN)
        repo = self._repo()
        if version not in repo.versions():
            raise APIError(404, "NOT_FOUND", "Playbook 版本不存在。")
        return {"version": version, "text": repo.read("refs/tags/" + version)}

    @read_errors
    def diff(self, from_version: str, to_version: str) -> dict:
        before, after = self.playbook(from_version), self.playbook(to_version)
        return {"from": from_version, "to": to_version,
                "diff": "".join(unified_diff(before["text"].splitlines(keepends=True),
                                             after["text"].splitlines(keepends=True),
                                             fromfile=from_version + "/playbook.md",
                                             tofile=to_version + "/playbook.md"))}
