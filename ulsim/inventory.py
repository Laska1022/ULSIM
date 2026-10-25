"""Controller-local inventory and crash-resumable installation journal."""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STAGES = {
    "planned": {"approved"}, "approved": {"preparing", "failed"},
    "preparing": {"installing", "bootloader", "rebooting", "failed"},
    "installing": {"bootloader", "rebooting", "failed"},
    "bootloader": {"rebooting", "failed"},
    "rebooting": {"reconnecting", "failed"},
    "reconnecting": {"configuring", "failed"},
    "configuring": {"verifying", "failed"},
    "verifying": {"complete", "failed"}, "complete": set(),
    "failed": {"reconnecting"},
}


def state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("XDG_STATE_HOME")
    return Path(base or Path.home() / ".local" / "state") / "ulsim"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Inventory:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory) if directory else state_dir()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.directory / "inventory.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
              stage TEXT NOT NULL, data TEXT NOT NULL, updated TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (job_id TEXT, stage TEXT, at TEXT, detail TEXT);
        """)
        self.db.commit()

    def save_device(self, device: dict) -> dict:
        if not device.get("device_id"):
            raise ValueError("Device identity is required")
        old = self.get_device(device["device_id"], required=False) or {}
        old.update(device)
        self.db.execute("INSERT OR REPLACE INTO devices VALUES (?,?)", (old["device_id"], json.dumps(old)))
        self.db.commit()
        return old

    def get_device(self, selector: str | None, required=True) -> dict | None:
        devices = self.devices()
        matches = [d for d in devices if selector in (d["device_id"], d.get("name"), d.get("hostname"))] if selector else devices
        if len(matches) == 1:
            return matches[0]
        if not required:
            return None
        raise ValueError("Select a unique device using --device; use 'ulsim devices' to list known devices")

    def devices(self) -> list[dict]:
        return [json.loads(row[0]) for row in self.db.execute("SELECT data FROM devices ORDER BY id")]

    def new_job(self, plan: dict) -> dict:
        existing = self.job(plan["plan_id"])
        if existing:
            return existing
        self.db.execute("INSERT INTO jobs VALUES (?,?,?,?,?)", (plan["plan_id"], plan["device_id"], "planned", json.dumps({"plan": plan}), now()))
        self.db.commit()
        return self.job(plan["plan_id"])

    def job(self, job_id: str) -> dict | None:
        row = self.db.execute("SELECT id,device_id,stage,data,updated FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        return dict(job_id=row[0], device_id=row[1], stage=row[2], **json.loads(row[3]), updated=row[4])

    def transition(self, job_id: str, stage: str, detail: dict | None = None) -> dict:
        job = self.job(job_id)
        if not job:
            raise ValueError("Unknown job")
        if stage != job["stage"] and stage not in STAGES[job["stage"]]:
            raise ValueError(f"Invalid installation transition: {job['stage']} -> {stage}")
        data = {"plan": job["plan"], "detail": detail or {}}
        with self.db:
            self.db.execute("UPDATE jobs SET stage=?,data=?,updated=? WHERE id=?", (stage,json.dumps(data),now(),job_id))
            self.db.execute("INSERT INTO events VALUES (?,?,?,?)", (job_id,stage,now(),json.dumps(detail or {})))
        return self.job(job_id)
