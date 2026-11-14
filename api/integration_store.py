"""Small single-process SQLite result store; never automatically reruns work."""
import json
from pathlib import Path
import sqlite3
from threading import RLock
from time import time

class IdempotencyConflict(Exception):
    pass

class CapacityExceeded(Exception):
    pass

def _dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)

class IntegrationStore:
    def __init__(self, path: Path, max_runs=100):
        if type(max_runs) is not int or max_runs < 1:
            raise ValueError("max_runs must be a positive integer")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.max_runs, self._lock = max_runs, RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, visitors TEXT NOT NULL, report TEXT); CREATE TABLE IF NOT EXISTS sessions (run_id TEXT REFERENCES runs(id), visitor_id TEXT, session TEXT, trace TEXT, PRIMARY KEY(run_id,visitor_id));")

    def create(self, key, fingerprint, state, visitors):
        with self._lock, self._db:
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute("SELECT fingerprint,state FROM runs WHERE key=?", (key,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise IdempotencyConflict(key)
                return json.loads(row[1]), False
            if self._db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] >= self.max_runs:
                raise CapacityExceeded()
            self._db.execute("INSERT INTO runs(id,key,fingerprint,state,visitors) VALUES(?,?,?,?,?)",
                             (state["run_id"], key, fingerprint, _dump(state), _dump(visitors)))
            return json.loads(_dump(state)), True

    def state(self, run_id):
        with self._lock:
            row = self._db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return json.loads(row[0])

    def update(self, state):
        with self._lock, self._db:
            cursor = self._db.execute("UPDATE runs SET state=? WHERE id=?", (_dump(state), state["run_id"]))
            if not cursor.rowcount:
                raise KeyError(state["run_id"])

    def save_session(self, run_id, visitor_id, session, trace, *, state=None):
        with self._lock, self._db:
            stored = self.state(run_id)
            if visitor_id not in stored["visitor_status"]:
                raise KeyError(visitor_id)
            if state is not None and state["run_id"] != run_id:
                raise ValueError("State belongs to another run.")
            if session is not None and (session.get("run_id") != run_id or session.get("visitor_id") != visitor_id):
                raise ValueError("Session does not belong to this run and visitor.")
            self._db.execute("INSERT INTO sessions(run_id,visitor_id,session,trace) VALUES(?,?,?,?) ON CONFLICT(run_id,visitor_id) DO UPDATE SET session=excluded.session,trace=excluded.trace",
                (run_id, visitor_id, _dump(session) if session is not None else None, _dump(trace)))
            if state is not None:
                self._db.execute("UPDATE runs SET state=? WHERE id=?", (_dump(state), run_id))

    def session(self, run_id, visitor_id):
        with self._lock:
            self.state(run_id)
            row = self._db.execute("SELECT session FROM sessions WHERE run_id=? AND visitor_id=?", (run_id, visitor_id)).fetchone()
            if not row or row[0] is None:
                raise KeyError(visitor_id)
            return json.loads(row[0])

    def sessions(self, run_id):
        with self._lock:
            self.state(run_id)
            return {v: json.loads(s) for v,s in self._db.execute("SELECT visitor_id,session FROM sessions WHERE run_id=? AND session IS NOT NULL", (run_id,))}

    def save_report(self, run_id, report, *, state=None):
        if report.get("run_id") != run_id:
            raise ValueError("Report belongs to another run.")
        if state is not None and state["run_id"] != run_id:
            raise ValueError("State belongs to another run.")
        with self._lock, self._db:
            self.state(run_id)
            self._db.execute("UPDATE runs SET report=? WHERE id=?", (_dump(report), run_id))
            if state is not None:
                self._db.execute("UPDATE runs SET state=? WHERE id=?", (_dump(state), run_id))

    def report(self, run_id):
        with self._lock:
            row = self._db.execute("SELECT report FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return json.loads(row[0]) if row[0] else None

    def recover_interrupted(self):
        count = 0
        with self._lock, self._db:
            rows = list(self._db.execute("SELECT id,state FROM runs"))
            for run_id, raw in rows:
                state = json.loads(raw)
                if state["status"] not in ("queued", "running"):
                    continue
                statuses = state["visitor_status"]
                saved = self.sessions(run_id)
                for visitor_id, status in statuses.items():
                    # Recover old split commits conservatively from validated stored sessions.
                    session = saved.get(visitor_id)
                    if session and session["status"] in ("completed", "crisis_exit"):
                        statuses[visitor_id] = "succeeded"
                    else:
                        statuses[visitor_id] = "failed"
                now = time()
                state.update(status="failed", finished_at=now, report_available=False,
                    elapsed_ms=max(0, int((now-state["created_at"])*1000)),
                    error={"code": "RUN_INTERRUPTED", "message": "服务重启，未完成任务已终止；不会自动重跑。"})
                state["progress"] = {"total": len(statuses), "completed": list(statuses.values()).count("succeeded"),
                                     "failed": list(statuses.values()).count("failed")}
                self._db.execute("UPDATE runs SET state=?,report=NULL WHERE id=?", (_dump(state), run_id))
                count += 1
        return count

    def close(self):
        with self._lock:
            self._db.close()
