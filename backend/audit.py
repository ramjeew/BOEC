import aiosqlite
import os
import json
from datetime import datetime
import hashlib

DB_PATH = "storage/audit.db"

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                timestamp TEXT,
                event_type TEXT,
                data TEXT,
                prev_hash TEXT,
                hash TEXT
            )
        """)
        await db.commit()

async def log_event(job_id: str, event_type: str, data: dict) -> str:
    """
    Logs an event to the hash-chained SQLite audit database.
    Guarantees tamper-evident audit trail for SANAS TR-18 / ISO/IEC 17025 compliance.
    """
    await init_db()
    prev_hash = "GENESIS_HASH_BOEC_2026"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                prev_hash = row[0]

        timestamp = datetime.now().isoformat()
        payload = f"{job_id}:{timestamp}:{event_type}:{json.dumps(data, sort_keys=True)}:{prev_hash}"
        curr_hash = hashlib.sha256(payload.encode()).hexdigest()

        await db.execute(
            "INSERT INTO audit_log (job_id, timestamp, event_type, data, prev_hash, hash) VALUES (?,?,?,?,?,?)",
            (job_id, timestamp, event_type, json.dumps(data), prev_hash, curr_hash)
        )
        await db.commit()
        return curr_hash

async def get_audit_trail(limit: int = 100):
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, job_id, timestamp, event_type, data, prev_hash, hash FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "job_id": r[1],
                    "timestamp": r[2],
                    "event": r[3],
                    "data": json.loads(r[4]) if r[4] else {},
                    "prev_hash": r[5],
                    "hash": r[6]
                }
                for r in rows
            ]
