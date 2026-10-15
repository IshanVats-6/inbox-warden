"""SQLite storage: mailboxes, the label taxonomy, settings, and run history."""

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS mailboxes (
    email TEXT PRIMARY KEY,
    auth TEXT NOT NULL,                 -- 'oauth' | 'demo'
    refresh_token TEXT,                 -- encrypted, oauth only
    mode TEXT NOT NULL DEFAULT 'clean', -- 'clean' | 'label_only' | 'paused'
    min_age_hours INTEGER NOT NULL DEFAULT 0,
    added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS labels (
    path TEXT PRIMARY KEY,              -- 'Clients/Acme Corp'
    description TEXT NOT NULL DEFAULT '',
    disposition TEXT NOT NULL,          -- 'inbox' | 'archive' | 'archive_unread'
    origin TEXT NOT NULL,               -- 'core' | 'agent' | 'user'
    emails INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL,
    trigger TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    stats TEXT NOT NULL DEFAULT '{}',
    error TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    run_id INTEGER NOT NULL,
    mailbox TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    label TEXT NOT NULL,
    action TEXT NOT NULL,
    attention INTEGER NOT NULL,
    new_label INTEGER NOT NULL,
    reason TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS decisions_run ON decisions(run_id);
"""

_lock = threading.Lock()


def _path():
    os.makedirs(settings.data_dir, exist_ok=True)
    path = os.path.join(settings.data_dir, "mailhub.db")
    legacy = os.path.join(settings.data_dir, "warden.db")  # installs from before the rename keep their data
    if not os.path.exists(path) and os.path.exists(legacy):
        os.rename(legacy, path)
    return path


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(_path())
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def get(key, default=None):
    with conn() as c:
        row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def put(key, value):
    with conn() as c:
        c.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value)))


def rows(sql, *args):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def execute(sql, *args):
    with conn() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def now():
    return time.time()
