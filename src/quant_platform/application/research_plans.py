"""Owner-scoped immutable research plans and execution links."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)


class ResearchPlanStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS plans (
                owner TEXT NOT NULL, plan_id TEXT NOT NULL, revision INTEGER NOT NULL,
                title TEXT NOT NULL, created_at TEXT NOT NULL, snapshot TEXT NOT NULL,
                inputs TEXT NOT NULL, PRIMARY KEY(owner, plan_id, revision));
            CREATE TABLE IF NOT EXISTS plan_runs (
                owner TEXT NOT NULL, plan_id TEXT NOT NULL, revision INTEGER NOT NULL,
                run_id TEXT NOT NULL, PRIMARY KEY(owner, run_id));
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def save(self, owner, title, snapshot, inputs=None, plan_id=None):
        if not owner or not title.strip():
            raise ValueError("方案名称不能为空")
        payload, draft = canonical(snapshot), canonical(inputs or {})
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = None
            if plan_id:
                previous = db.execute(
                    "SELECT * FROM plans WHERE owner=? AND plan_id=? "
                    "ORDER BY revision DESC LIMIT 1",
                    (owner, plan_id),
                ).fetchone()
                if previous is None:
                    raise ValueError("找不到当前用户的研究方案")
                if (
                    previous["snapshot"] == payload
                    and previous["inputs"] == draft
                    and previous["title"] == title.strip()
                ):
                    return self._decode(previous)
            plan_id = plan_id or uuid4().hex
            revision = previous["revision"] + 1 if previous else 1
            db.execute(
                "INSERT INTO plans VALUES (?,?,?,?,?,?,?)",
                (
                    owner,
                    plan_id,
                    revision,
                    title.strip(),
                    datetime.now(UTC).isoformat(),
                    payload,
                    draft,
                ),
            )
            row = db.execute(
                "SELECT * FROM plans WHERE owner=? AND plan_id=? AND revision=?",
                (owner, plan_id, revision),
            ).fetchone()
            return self._decode(row)

    @staticmethod
    def _decode(row):
        if row is None:
            raise ValueError("研究方案不存在")
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"])
        result["inputs"] = json.loads(result["inputs"])
        return result

    def list(self, owner):
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT * FROM plans WHERE owner=? ORDER BY created_at DESC, revision DESC",
                (owner,),
            ).fetchall()
            return [self._decode(row) for row in rows]

    def load(self, owner, plan_id, revision):
        with closing(self.connect()) as db:
            return self._decode(
                db.execute(
                    "SELECT * FROM plans WHERE owner=? AND plan_id=? AND revision=?",
                    (owner, plan_id, revision),
                ).fetchone()
            )

    def link_run(self, owner, plan, run_id, snapshot):
        saved = self.load(owner, plan["plan_id"], plan["revision"])
        if canonical(saved["snapshot"]) != canonical(snapshot):
            raise ValueError("执行配置与方案版本不一致，不能关联")
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO plan_runs VALUES (?,?,?,?)",
                (owner, plan["plan_id"], plan["revision"], run_id),
            )

    def runs(self, owner, plan_id, revision):
        with closing(self.connect()) as db:
            return [
                r["run_id"]
                for r in db.execute(
                    "SELECT run_id FROM plan_runs WHERE owner=? AND plan_id=? AND revision=? "
                    "ORDER BY rowid",
                    (owner, plan_id, revision),
                )
            ]


def owner_key(username):
    return hashlib.sha256(str(username).casefold().encode()).hexdigest()


def configuration_diff(plans):
    def flatten(value, prefix=""):
        out = {}
        for k, v in value.items():
            name = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.update(flatten(v, name))
            else:
                out[name] = canonical(v)
        return out

    frames = [flatten(p["snapshot"]) for p in plans]
    keys = sorted(set().union(*(set(f) for f in frames)))
    return [
        {
            "配置项": k,
            **{
                f"{p['title']} · v{p['revision']} · {p['plan_id'][:6]}": f.get(k, "未设置")
                for p, f in zip(plans, frames, strict=True)
            },
        }
        for k in keys
        if len({f.get(k, "未设置") for f in frames}) > 1
    ]
