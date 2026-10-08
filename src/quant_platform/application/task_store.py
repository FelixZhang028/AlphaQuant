"""Durable local task state and events, shared by HTTP and detached processes."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from quant_platform.core.diagnostics import redact

TERMINAL = {"SUCCESS", "PARTIAL", "FAILED", "CANCELLED", "INTERRUPTED"}


def now():
    return datetime.now(UTC).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class TaskConflict(ValueError):
    pass


class TaskMissing(ValueError):
    pass


class TaskStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                    input TEXT NOT NULL, private TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE, retry_of TEXT, pid INTEGER,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    started_at TEXT, finished_at TEXT, cancel_requested INTEGER DEFAULT 0,
                    progress TEXT NOT NULL, error TEXT, result_available INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, event TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS task_events ON events(task_id, seq);
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=15)) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn

    def get(self, identifier, *, private=False):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise TaskMissing("任务不存在")
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise TaskMissing("任务不存在")
        result = dict(row)
        for key in ("input", "private", "progress", "error"):
            result[key] = json.loads(result[key]) if result[key] is not None else None
        result["cancel_requested"] = bool(result["cancel_requested"])
        result["result_available"] = bool(result["result_available"])
        if not private:
            for key in ("input", "private", "fingerprint", "idempotency_key", "pid"):
                result.pop(key)
        return result

    def submit(self, kind, inputs, private, *, key=None, retry_of=None):
        fingerprint = hashlib.sha256(canonical([kind, inputs, retry_of]).encode()).hexdigest()
        identifier = uuid4().hex
        timestamp = now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if key is not None:
                previous = conn.execute(
                    "SELECT id,fingerprint FROM tasks WHERE idempotency_key=?", (key,)
                ).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise TaskConflict("同一幂等键不能提交不同参数")
                    return self.get(previous["id"]), False
            count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('SUCCESS','PARTIAL',"
                "'FAILED','CANCELLED','INTERRUPTED')"
            ).fetchone()[0]
            if count >= 20:
                raise TaskConflict("队列已满，请等待当前任务完成")
            conn.execute(
                "INSERT INTO tasks (id,kind,status,input,private,fingerprint,idempotency_key,"
                "retry_of,created_at,updated_at,progress) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    kind,
                    "QUEUED",
                    canonical(inputs),
                    canonical(private),
                    fingerprint,
                    key,
                    retry_of,
                    timestamp,
                    timestamp,
                    canonical({"stage": "queued", "completed": 0, "total": None}),
                ),
            )
        self.directory(identifier).mkdir(exist_ok=True)
        self.event(identifier, {"stage": "queued", "message": "任务已入队"})
        return self.get(identifier), True

    def directory(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise TaskMissing("任务不存在")
        path = (self.root / identifier).resolve()
        if path.parent != self.root:
            raise TaskMissing("任务不存在")
        return path

    def list(self, status=None, kind=None, offset=0, limit=50):
        where, args = [], []
        for key, value in (("status", status), ("kind", kind)):
            if value:
                where.append(f"{key}=?")
                args.append(value)
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM tasks" + clause, args).fetchone()[0]
            rows = conn.execute(
                "SELECT id FROM tasks" + clause + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return {
            "items": [self.get(row["id"]) for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def pending(self):
        with self.connect() as conn:
            return [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM tasks WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')"
                )
            ]

    def launched(self, identifier, pid):
        with self.connect() as conn:
            conn.execute(
                "UPDATE tasks SET pid=?,updated_at=? WHERE id=? AND status='QUEUED'",
                (pid, now(), identifier),
            )

    def claim(self, identifier):
        with self.connect() as conn:
            result = conn.execute(
                "UPDATE tasks SET status='RUNNING',started_at=?,updated_at=? "
                "WHERE id=? AND status='QUEUED' AND cancel_requested=0",
                (now(), now(), identifier),
            )
        return result.rowcount == 1

    def progress(self, identifier, stage, completed, total):
        value = {"stage": stage, "completed": completed, "total": total}
        with self.connect() as conn:
            conn.execute(
                "UPDATE tasks SET progress=?,updated_at=? WHERE id=? "
                "AND status IN ('RUNNING','CANCEL_REQUESTED')",
                (canonical(value), now(), identifier),
            )
        self.event(identifier, value)

    def event(self, identifier, value):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events(task_id,created_at,event) VALUES(?,?,?)",
                (identifier, now(), canonical(redact(value))),
            )

    def events(self, identifier, after=0, limit=200):
        self.get(identifier)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE task_id=? AND seq>? ORDER BY seq LIMIT ?",
                (identifier, after, limit),
            ).fetchall()
        return [
            {"seq": row["seq"], "created_at": row["created_at"], **json.loads(row["event"])}
            for row in rows
        ]

    def cancel(self, identifier):
        self.get(identifier)
        with self.connect() as conn:
            conn.execute(
                "UPDATE tasks SET cancel_requested=1,updated_at=?,"
                "status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,"
                "finished_at=CASE WHEN status='QUEUED' THEN ? ELSE finished_at END "
                "WHERE id=? AND status IN ('QUEUED','RUNNING')",
                (now(), now(), identifier),
            )
        return self.get(identifier)

    def finish(self, identifier, status, error=None, result=None):
        if status not in TERMINAL:
            raise ValueError("无效任务终态")
        if result is not None:
            path = self.directory(identifier) / "result.json"
            temp = path.with_suffix(".tmp")
            temp.write_text(canonical(redact(result)), encoding="utf-8")
            temp.replace(path)
        with self.connect() as conn:
            conn.execute(
                "UPDATE tasks SET status=?,error=?,result_available=?,updated_at=?,"
                "finished_at=?,progress=CASE WHEN ? IN ('SUCCESS','PARTIAL') THEN ? "
                "ELSE progress END WHERE id=? AND status NOT IN "
                "('SUCCESS','PARTIAL','FAILED','CANCELLED','INTERRUPTED')",
                (
                    status,
                    canonical(redact(error)) if error else None,
                    result is not None,
                    now(),
                    now(),
                    status,
                    canonical({"stage": "finished", "completed": 1, "total": 1}),
                    identifier,
                ),
            )
        self.event(identifier, {"stage": status.lower(), "message": status, "error": error})

    def result(self, identifier):
        item = self.get(identifier)
        if not item["result_available"]:
            raise TaskConflict("任务尚无可读取的结果")
        return json.loads((self.directory(identifier) / "result.json").read_text(encoding="utf-8"))
