from __future__ import annotations

import json
from pathlib import Path
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    digest TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    batch_digest TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    snapshot TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self):
        return sqlite3.connect(self.path)

    def record(self, digest: str, run_id: str, result: dict) -> dict:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO runs VALUES (?, ?, ?)",
                (digest, run_id, json.dumps(result, ensure_ascii=False, sort_keys=True)),
            )
            row = db.execute("SELECT run_id, result FROM runs WHERE digest=?", (digest,)).fetchone()
        return {"run_id": row[0], "result": json.loads(row[1])}

    def record_approval(self, batch_digest: str, run_id: str, snapshot: dict) -> dict:
        """同一批次签批重试只留一份档，返回首次留档的编号。"""
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO approvals VALUES (?, ?, ?)",
                (batch_digest, run_id, payload),
            )
            row = db.execute(
                "SELECT run_id, snapshot FROM approvals WHERE batch_digest=?", (batch_digest,)
            ).fetchone()
        return {"run_id": row[0], "snapshot": json.loads(row[1])}

    def approval(self, batch_digest: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT run_id, snapshot FROM approvals WHERE batch_digest=?", (batch_digest,)
            ).fetchone()
        if row is None:
            return None
        return {"run_id": row[0], "snapshot": json.loads(row[1])}

    def approvals(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT run_id, batch_digest, snapshot FROM approvals ORDER BY run_id"
            ).fetchall()
        return [
            {"run_id": row[0], "batch_digest": row[1], "snapshot": json.loads(row[2])}
            for row in rows
        ]

    def count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def approval_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def all(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT run_id, digest, result FROM runs ORDER BY run_id").fetchall()
        return [{"run_id": r[0], "digest": r[1], "result": json.loads(r[2])} for r in rows]
