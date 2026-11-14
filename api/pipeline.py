"""Console "one-click full pipeline": progress aggregation and the demo child-process launcher.

The HTTP service never calls a model. ``POST /demo/launch`` starts ``python -m engine.demo all ...``
in the repo root; ``GET /demo/pipeline`` reads only files under ``var/`` (see PIPELINE_API.md).
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from api.auth import current_user
from api.errors import APIError
from api.file_store import ID_PATTERN, VISITOR_PATTERN, FileStore
from api.run_models import ErrorResponse
from engine.file_lock import file_lock

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_TAIL_LINES = 20

# Fixed on the server (competition rule: nothing may be tuned live). ``step_s`` are default
# step durations used for ETAs until the same experiment has measured a step of that kind.
PRESETS = {
    "live": {"label": "现场模式", "generations": 1, "effort": "low",
             "description": "运行 1 → 学习 1 代 → 运行 2 与对照",
             "step_s": {"run": 60, "generation": 240, "practice": 60, "final": 100}},
    "full": {"label": "完整模式", "generations": 3, "effort": "high",
             "description": "运行 1 → 学习 3 代（含自我练习）→ 运行 2 与对照",
             "step_s": {"run": 60, "generation": 400, "practice": 60, "final": 100}},
}
MOCK_STEP_S = {"run": 5, "generation": 15, "practice": 5, "final": 5}
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|SHA256", re.IGNORECASE)
RUN_LABELS = {"run1": "运行 1", "run2": "运行 2", "control": "对照"}


def preset_expected_s(preset: dict) -> int:
    s, n = preset["step_s"], preset["generations"]
    return s["run"] + n * s["generation"] + (n - 1) * s["practice"] + s["final"]


def _parse(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _seconds(start, end) -> float | None:
    start, end = _parse(start), _parse(end)
    return None if start is None or end is None else round(max((end - start).total_seconds(), 0.0), 1)


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def _mean(values) -> float | None:
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(sum(values) / len(values), 4) if values else None


def _valid_id(value) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(ID_PATTERN, value)) and value not in {".", ".."}


# --------------------------------------------------------------------------------------------
# Launcher
# --------------------------------------------------------------------------------------------

class Launcher:
    """Owns at most one ``engine.demo`` child process started by this service process."""

    def __init__(self, enabled: bool, data_root: Path):
        self.enabled = enabled
        self.root = Path(data_root).resolve()
        self.log_path = self.root / "var/demo/launcher.log"
        self.lock_path = self.root / "var/demo/.lock"
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self.preset: str | None = None
        self.mock = False
        self.started_at: str | None = None
        self.stopped = False
        self._eid: str | None = None
        # Experiments whose child (started by this service process) has exited: id -> error text.
        # Lets GET /demo/pipeline report them as failed even after a later launch truncated the log.
        self.ended: dict[str, str] = {}

    # -- state ---------------------------------------------------------------------------
    def state(self) -> str:
        if self._proc is None:
            return "idle"
        return "running" if self._proc.poll() is None else "exited"

    def exit_code(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def log_lines(self, limit: int = LOG_TAIL_LINES) -> list[str]:
        if not self.enabled:
            return []
        try:
            with self.log_path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(size - 64 * 1024, 0))
                text = stream.read().decode("utf-8", errors="replace")
        except OSError:
            return []
        return [_redact(line) for line in text.splitlines()[-limit:]]

    def experiment_id(self) -> str | None:
        """The experiment id the current/last child printed (``experiment_id=...``, near the top)."""
        if self._proc is None or not self.enabled:
            return None
        if self._eid is None:
            try:
                with self.log_path.open("rb") as stream:
                    head = stream.read(16 * 1024).decode("utf-8", errors="replace")
            except OSError:
                return None
            match = re.search(r"^experiment_id=(\S+)", head, re.MULTILINE)
            self._eid = match[1] if match else None
        return self._eid

    def exit_message(self) -> str:
        return "已手动停止" if self.stopped else f"子进程已退出（退出码 {self.exit_code()}），实验未完成"

    def abandoned(self, experiment_id: str) -> str | None:
        """Error text if *experiment_id* belongs to a child of ours that is no longer running."""
        if self.state() == "exited" and self.experiment_id() == experiment_id:
            return self.exit_message()
        if self.state() == "running" and self.experiment_id() == experiment_id:
            return None
        return self.ended.get(experiment_id)

    def view(self) -> dict:
        state = self.state()
        return {
            "enabled": self.enabled,
            "state": state,
            "pid": self._proc.pid if self._proc is not None else None,
            "preset": self.preset,
            "mock": self.mock,
            "started_at": self.started_at,
            "exit_code": self.exit_code(),
            "stopped": self.stopped,
            "presets": [{"key": key, "label": p["label"], "generations": p["generations"],
                         "description": p["description"], "expected_s": preset_expected_s(p)}
                        for key, p in PRESETS.items()],
            "log_tail": self.log_lines(),
        }

    # -- actions -------------------------------------------------------------------------
    def _lock_busy(self) -> bool:
        try:
            with file_lock(self.lock_path, blocking=False):
                return False
        except BlockingIOError:
            return True
        except OSError:
            return False  # cannot probe; engine.demo still refuses a second command itself

    def launch(self, preset_key: str, mock: bool) -> dict:
        if not self.enabled:
            raise APIError(403, "LAUNCH_DISABLED", "服务端未开启一键全链路（API_DEMO_LAUNCH=1）；请在终端执行 make demo-run1。")
        preset = PRESETS.get(preset_key)
        if preset is None:
            raise APIError(422, "VALIDATION_ERROR", "未知的启动预设。")
        with self._lock:
            if self.state() == "running" or self._lock_busy():
                raise APIError(409, "ALREADY_RUNNING", "已有 demo 命令在运行。")
            previous = self.experiment_id()
            if previous:  # remember before the new child truncates the log
                self.ended[previous] = self.exit_message()
            command = [sys.executable, "-m", "engine.demo", "all", "--reset",
                       "--generations", str(preset["generations"]), "--visitor-renderer", "template"]
            if mock:
                command.append("--mock")
            env = dict(os.environ)
            env.update(REFLECTOR_REASONING_EFFORT=preset["effort"], PYTHONUNBUFFERED="1",
                       PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            if os.name == "nt":
                group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                         | getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            else:
                group = {"start_new_session": True}
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("wb") as log:  # the child keeps its own handle
                proc = subprocess.Popen(command, cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, **group)
            self._proc, self.preset, self.mock, self.stopped, self._eid = proc, preset_key, bool(mock), False, None
            self.started_at = _iso(_now())
            return {"pid": proc.pid, "preset": preset_key, "mock": bool(mock)}

    def stop(self) -> dict:
        if not self.enabled:
            raise APIError(403, "LAUNCH_DISABLED", "服务端未开启一键全链路（API_DEMO_LAUNCH=1）。")
        with self._lock:
            if self.state() != "running":
                raise APIError(409, "NOT_RUNNING", "没有在运行的 demo 子进程。")
            proc = self._proc
            self.stopped = True
            kill_tree(proc)
            return {"stopped": True}


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the child and everything it spawned (it runs in its own group/session)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)  # start_new_session: pgid == pid
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _redact(line: str) -> str:
    """Belt and braces: never echo a secret-looking environment value from the child log."""
    for name, value in os.environ.items():
        if SECRET_NAME.search(name) and len(value) >= 8 and value in line:
            line = line.replace(value, "***")
    return line


# --------------------------------------------------------------------------------------------
# Aggregator
# --------------------------------------------------------------------------------------------

class PipelineView:
    """Builds the ``GET /demo/pipeline`` document from files under ``var/``. Never writes."""

    def __init__(self, store: FileStore):
        self.store = store
        self._final_counts: dict[str, tuple[int, int]] = {}  # finished batches never change

    # -- file helpers ----------------------------------------------------------------------
    def _json(self, *parts) -> dict | None:
        try:
            return self.store._json(*parts, optional=True)
        except (APIError, OSError, ValueError, TypeError):
            return None

    def _report(self, run_id) -> dict | None:
        return self._json("var/runs", run_id, "run_report.json") if _valid_id(run_id) else None

    def _counts(self, run_id, final: bool) -> tuple[int, int]:
        if not _valid_id(run_id):
            return 0, 0
        if run_id in self._final_counts:
            return self._final_counts[run_id]
        completed = failed = 0
        try:
            folder = self.store._path("var/runs", run_id, "sessions")
            files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        except (APIError, OSError):
            files = []
        for path in files:
            if path.is_symlink() or not re.fullmatch(VISITOR_PATTERN, path.stem):
                continue
            doc = self._json("var/runs", run_id, "sessions", path.name)
            if doc is None:
                continue
            if doc.get("status") == "error":
                failed += 1
            else:
                completed += 1
        if final:
            self._final_counts[run_id] = (completed, failed)
        return completed, failed

    # -- pieces ------------------------------------------------------------------------------
    @staticmethod
    def _batch_label(b: dict) -> str:
        role = b.get("role")
        if role in RUN_LABELS:
            return RUN_LABELS[role]
        if role == "practice":
            return f"练习（{b.get('version')}）"
        replicate = b.get("replicate") or 1
        candidate = b.get("candidate")
        if not candidate:
            return f"基线 · 第 {replicate} 次"
        number = re.sub(r"^c", "", str(candidate))
        return f"候选 {number} · 第 {replicate} 次"

    def _batch(self, b: dict) -> dict:
        state = b.get("state") if b.get("state") in ("running", "done", "failed") else "running"
        completed, failed = self._counts(b.get("run_id"), final=state != "running")
        report = self._report(b.get("run_id"))
        isi = ((report or {}).get("metrics") or {}).get("isi_response_rate")
        duration = _seconds(b.get("started_at"), b.get("finished_at"))
        if duration is None and report is not None and isinstance(report.get("duration_s"), (int, float)):
            duration = round(float(report["duration_s"]), 1)
        total = b.get("total")
        if total is None and report is not None:
            total = report.get("n_visitors")
        return {"run_id": b.get("run_id"), "role": b.get("role"), "label": self._batch_label(b),
                "version": b.get("version"), "split": b.get("split"), "total": total,
                "completed": completed, "failed": failed, "state": state,
                "started_at": b.get("started_at"), "finished_at": b.get("finished_at"), "duration_s": duration,
                "isi_response_rate": isi, "generation": b.get("generation"), "candidate": b.get("candidate"),
                "replicate": b.get("replicate") or 1}

    def _coarse_progress(self, manifest: dict, options: dict) -> dict:
        """Old experiments without progress.json: rebuild a progress-like dict from the manifest."""
        batches = []

        def add(role, entry, split):
            if not isinstance(entry, dict) or entry.get("state") in (None, "pending"):
                return
            batches.append({"run_id": entry.get("run_id"), "role": role, "version": entry.get("playbook_version"),
                            "split": split, "total": None, "state": entry.get("state"),
                            "started_at": None, "finished_at": None, "generation": None, "candidate": None,
                            "replicate": 1})

        add("run1", manifest.get("run1"), "A")
        evolution = manifest.get("evolution") or {}
        ids = evolution.get("generations") or (
            [evolution["evolution_id"]] if evolution.get("evolution_id") and evolution.get("state") != "pending"
            else [])
        generations = []
        for index, eid in enumerate(ids, start=1):
            status = self._json("var/evolve", eid, "status.json") if _valid_id(eid) else None
            phase = (status or {}).get("phase")
            state = "done" if phase == "done" else "failed" if phase == "failed" else (
                "running" if status else evolution.get("state", "pending"))
            if state == "pending":
                continue
            generations.append({"index": index, "evolution_id": eid,
                                "from_version": (status or {}).get("from_version"), "state": state,
                                "started_at": None, "finished_at": (status or {}).get("updated_at")
                                if state in ("done", "failed") else None,
                                "outcome": (status or {}).get("outcome"), "to_version": (status or {}).get("to_version")})
        for number, item in enumerate(manifest.get("practice") or [], start=1):
            add("practice", item, "A")
            if batches and batches[-1]["role"] == "practice":
                batches[-1]["generation"] = number
        add("run2", manifest.get("run2"), "B")
        add("control", manifest.get("control"), "B")
        return {"generations_planned": options.get("generations") or max(len(ids), 1),
                "mock": options.get("mock"), "batches": batches, "generations": generations, "started_at": None}

    def _generation(self, entry: dict, batches: list[dict], previous: dict | None) -> dict:
        eid = entry.get("evolution_id")
        status = (self._json("var/evolve", eid, "status.json") if _valid_id(eid) else None) or {}
        finished = entry.get("state") != "running" or status.get("phase") in ("done", "failed")
        evolution = (self._json("var/evolve", eid, "evolution.json") if _valid_id(eid) and finished else None) or {}
        raw_states = (status.get("validation") or {}).get("candidates") or {}
        ids = list(dict.fromkeys([*raw_states, *(b["candidate"] for b in batches if b["candidate"])]))
        if not ids and entry.get("state") == "running":
            ids = ["c1", "c2", "c3"]
        passed = {c.get("id"): c.get("passed") for c in evolution.get("candidates") or []}
        candidates = []
        for cid in ids:
            own = [b for b in batches if b["candidate"] == cid]
            raw = raw_states.get(cid)
            if any(b["state"] == "running" for b in own) or raw == "running":
                state = "running"
            elif raw in ("done", "error", "blocked", "empty") or (own and finished):
                state = "done"
            else:
                state = "pending"
            candidates.append({"id": cid, "state": state, "status": raw,
                               "isi": _mean(b["isi_response_rate"] for b in own if b["state"] == "done"),
                               "passed": passed.get(cid) if evolution else None})
        baseline_isi = _mean(b["isi_response_rate"] for b in batches if not b["candidate"] and b["state"] == "done")
        if baseline_isi is None:
            baseline_isi = (evolution.get("baseline_val_metrics") or {}).get("isi_response_rate")
        if baseline_isi is None and (status.get("validation") or {}).get("baseline") == "skipped" and previous:
            chosen = previous.get("chosen")
            baseline_isi = next((c["isi"] for c in previous["candidates"] if c["id"] == chosen), None)
        phase = status.get("phase") or {"done": "done", "failed": "failed"}.get(entry.get("state"))
        return {"index": entry.get("index"), "evolution_id": eid,
                "from_version": entry.get("from_version") or status.get("from_version"),
                "phase": phase, "reflector": status.get("reflector"),
                "baseline_state": (status.get("validation") or {}).get("baseline"),
                "baseline_isi": baseline_isi, "candidates": candidates,
                "outcome": status.get("outcome") or entry.get("outcome"),
                "to_version": status.get("to_version") or entry.get("to_version"),
                "chosen": status.get("chosen")}

    @staticmethod
    def _aggregate(states: list[str]) -> str:
        if any(s == "running" for s in states):
            return "running"
        if any(s == "failed" for s in states):
            return "failed"
        return "done"

    def _result(self, manifest: dict) -> dict:
        out = {}
        for key in ("run1", "control", "run2"):
            report = self._report((manifest.get(key) or {}).get("run_id"))
            metrics = (report or {}).get("metrics") or {}
            out[key] = None if report is None else {
                "isi_response_rate": metrics.get("isi_response_rate"),
                "referral_recall": metrics.get("referral_recall"),
                "referral_precision": metrics.get("referral_precision"),
                "n": report.get("n_visitors"), "playbook_version": report.get("playbook_version")}
        isi = [(out[k] or {}).get("isi_response_rate") for k in ("run2", "control")]
        out["delta_pp"] = (round((isi[0] - isi[1]) * 100, 2)
                           if all(isinstance(v, (int, float)) for v in isi) else None)
        return out

    def _started_at(self, eid: str, manifest: dict) -> str | None:
        for name in ("cohorts.json", "options.json"):
            try:
                path = self.store._path("var/demo", eid, name)
                return _iso(datetime.fromtimestamp(path.stat().st_mtime).astimezone())
            except (APIError, OSError):
                continue
        return manifest.get("updated_at")

    # -- main ---------------------------------------------------------------------------------
    def build(self, launcher: Launcher, now: datetime | None = None) -> dict:
        now = now or _now()
        manifest = self._json("var/demo/experiment.json")
        eid = (manifest or {}).get("experiment_id")
        if manifest is None or not _valid_id(eid):
            return {"available": False, "launcher": launcher.view()}
        options = self._json("var/demo", eid, "options.json") or {}
        progress = self._json("var/demo", eid, "progress.json")
        detailed = progress is not None and progress.get("experiment_id") == eid
        if not detailed:
            progress = self._coarse_progress(manifest, options)

        stage = manifest.get("stage")
        state = "done" if stage == "done" else "failed" if stage == "failed" else "running"
        error = manifest.get("error")
        abandoned = launcher.abandoned(eid) if state == "running" else None
        if abandoned:  # our child exited (or was stopped) but the manifest never reached a final stage
            state, error = "failed", abandoned
        terminal = state != "running"
        mock = progress.get("mock")
        mock = options.get("mock") if mock is None else mock
        planned = progress.get("generations_planned") or options.get("generations") or 1
        planned = max(int(planned), len(progress.get("generations") or []))
        preset = PRESETS.get(launcher.preset) if launcher.experiment_id() == eid else None
        preset = preset or PRESETS["live" if planned == 1 else "full"]
        defaults = MOCK_STEP_S if mock else preset["step_s"]

        batches = [self._batch(b) for b in progress.get("batches") or [] if isinstance(b, dict)]
        if terminal:
            for b in batches:
                if b["state"] == "running":
                    b["state"] = "failed"
        generations = {g.get("index"): g for g in progress.get("generations") or [] if isinstance(g, dict)}
        evolution_state = (manifest.get("evolution") or {}).get("state")
        learning_over = terminal or evolution_state in ("done", "failed")

        steps: list[dict] = []

        def run_step(key, kind, label, detail, own, fallback_state):
            state_ = self._aggregate([b["state"] for b in own]) if own else fallback_state
            starts = [b["started_at"] for b in own if b["started_at"]]
            ends = [b["finished_at"] for b in own if b["finished_at"]]
            steps.append({"key": key, "kind": kind, "label": label, "detail": detail, "state": state_,
                          "started_at": min(starts, key=lambda v: _parse(v) or now) if starts else None,
                          "finished_at": max(ends, key=lambda v: _parse(v) or now)
                          if ends and state_ in ("done", "failed") else None,
                          "batches": own, "generation": None})

        manifest_state = lambda key: {"pending": "pending", "running": "running", "done": "done",
                                      "failed": "failed"}.get((manifest.get(key) or {}).get("state"), "pending")
        run_step("run1", "run", "运行 1", "用初始 playbook（v1）跑 A 组来访",
                 [b for b in batches if b["role"] == "run1"], manifest_state("run1"))
        previous = None
        for index in range(1, planned + 1):
            entry = generations.get(index)
            own = [b for b in batches if b["role"] == "validation" and b["generation"] == index]
            generation = self._generation(entry, own, previous) if entry else None
            if entry:
                gstate = entry.get("state") if entry.get("state") in ("running", "done", "failed") else "running"
            else:
                gstate = "skipped" if learning_over else "pending"
            if terminal and gstate == "running":
                gstate = "failed"
            steps.append({"key": f"gen{index}", "kind": "generation", "label": f"学习 · 第 {index} 代",
                          "detail": "反思运行结果，提出 3 份候选，在验证集 C 上过门禁", "state": gstate,
                          "started_at": (entry or {}).get("started_at"),
                          "finished_at": (entry or {}).get("finished_at") if gstate in ("done", "failed") else None,
                          "batches": own, "generation": generation})
            previous = generation
            if planned > 1 and index < planned:
                own = [b for b in batches if b["role"] == "practice" and b["generation"] == index]
                if own:
                    fallback = None
                elif (entry and entry.get("state") == "done" and entry.get("outcome") != "committed") \
                        or index + 1 in generations or learning_over:
                    fallback = "skipped"
                else:
                    fallback = "pending"
                version = (entry or {}).get("to_version") or "新版本"
                run_step(f"practice{index}", "practice", f"自我练习 · 第 {index} 代后",
                         f"用刚采纳的 {version} 重跑 A 组，供下一代反思", own, fallback)
        pair = [manifest_state("run2"), manifest_state("control")]
        final_fallback = "pending" if pair == ["pending", "pending"] else (
            "running" if "pending" in pair else self._aggregate(pair))
        run_step("final", "final", "运行 2 与对照", "学习后的版本与 v1 并行跑 B 组来访",
                 [b for b in batches if b["role"] in ("run2", "control")], final_fallback)

        if terminal:
            for step in steps:
                if step["state"] == "pending":
                    step["state"] = "skipped"
                elif step["state"] == "running":
                    step["state"] = "failed"
        self._estimate(steps, defaults, now)

        started_at = progress.get("started_at") or self._started_at(eid, manifest)
        updated = [v for v in (manifest.get("updated_at"), progress.get("updated_at")) if _parse(v)]
        updated_at = max(updated, key=_parse) if updated else None
        finished_at = None
        if terminal:  # the final manifest save stamps updated_at; a killed child leaves the last write
            finished_at = manifest.get("updated_at") if stage in ("done", "failed") else updated_at
        end = _parse(finished_at) if terminal else now
        start = _parse(started_at)
        elapsed = round(max((end - start).total_seconds(), 0.0), 1) if start and end else None
        eta = None
        if not terminal:
            eta = int(sum(s["eta_s"] or 0 for s in steps if s["state"] == "running")
                      + sum(s["expected_s"] or 0 for s in steps if s["state"] == "pending"))

        from_version = (manifest.get("run1") or {}).get("playbook_version")
        current = (manifest.get("run2") or {}).get("playbook_version")
        if not current:
            committed = [g.get("to_version") for _, g in sorted(generations.items())
                         if g.get("outcome") == "committed" and g.get("to_version")]
            current = committed[-1] if committed else from_version
        return {
            "available": True, "experiment_id": eid, "mode": "mock" if mock else "real",
            "state": state, "error": error, "stage": stage, "progress_available": detailed,
            "started_at": started_at, "updated_at": updated_at, "finished_at": finished_at,
            "elapsed_s": elapsed, "eta_s": eta, "generations_planned": planned,
            "playbook": {"from_version": from_version, "current_version": current},
            "steps": steps, "result": self._result(manifest), "launcher": launcher.view(),
        }

    @staticmethod
    def _estimate(steps: list[dict], defaults: dict, now: datetime) -> None:
        measured: dict[str, list[float]] = {}
        for step in steps:
            if step["state"] == "done":
                duration = _seconds(step["started_at"], step["finished_at"])
                if duration is not None:
                    measured.setdefault(step["kind"], []).append(duration)
        run_like = measured.get("run")
        for step in steps:
            kind = step["kind"]
            samples = measured.get(kind) or (run_like if kind in ("practice", "final") else None)
            expected = int(round(sum(samples) / len(samples))) if samples else defaults[kind]
            elapsed = None
            start = _parse(step["started_at"])
            if step["state"] == "running" and start is not None:
                elapsed = round(max((now - start).total_seconds(), 0.0), 1)
            elif step["state"] in ("done", "failed"):
                elapsed = _seconds(step["started_at"], step["finished_at"])
            eta = None
            if step["state"] == "running":
                remaining = expected - (elapsed or 0)
                total = sum(b["total"] or 0 for b in step["batches"])
                finished = sum(b["completed"] + b["failed"] for b in step["batches"])
                if kind != "generation" and total and finished and elapsed:
                    remaining = elapsed * (total - finished) / finished  # session-rate estimate
                eta = int(round(max(remaining, 0)))
            step.update(elapsed_s=elapsed, expected_s=expected, eta_s=eta)


# --------------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------------

class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: Annotated[str, Field(min_length=1, max_length=32)]
    mock: bool = False


router = APIRouter(prefix="/api/v1/demo", tags=["全链路演示"],
                   responses={s: {"model": ErrorResponse} for s in (403, 409, 422, 501)})


def _files_only(request: Request) -> None:
    if request.app.state.settings.data_source != "files":
        raise APIError(501, "RUNS_VIA_CLI", "Mock 数据源不支持一键全链路；真实运行请在操作员终端执行 make demo-run1。")


@router.get("/pipeline")
def pipeline(request: Request) -> dict:
    current_user(request)
    launcher: Launcher = request.app.state.launcher
    view: PipelineView | None = request.app.state.pipeline
    if view is None:
        return {"available": False, "launcher": launcher.view()}
    return view.build(launcher)


@router.post("/launch", status_code=202)
def launch(body: LaunchRequest, request: Request) -> dict:
    current_user(request)
    _files_only(request)
    return request.app.state.launcher.launch(body.preset, body.mock)


@router.post("/stop")
def stop(request: Request) -> dict:
    current_user(request)
    _files_only(request)
    return request.app.state.launcher.stop()
