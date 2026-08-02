#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event database layer for the financial news system.

Stores collected news events, analysis results, and market snapshots
in a single SQLite database for historical tracking and comparison.
"""
import os
import sqlite3
import hashlib
import threading
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finance.db")
_WRITE_LOCK = threading.Lock()
_MASTER_CONN = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT UNIQUE,
    source TEXT,
    title TEXT,
    link TEXT,
    published TEXT,
    fetched_at TEXT,
    summary TEXT,
    language TEXT,
    category TEXT,
    severity INTEGER DEFAULT 0,
    sentiment TEXT,
    related_tickers TEXT,
    impact_notes TEXT,
    status TEXT DEFAULT 'new',
    is_duplicate INTEGER DEFAULT 0,
    is_noise INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT,
    scope TEXT,
    batch_size INTEGER,
    prompt_version TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    name TEXT,
    price REAL,
    change_pct REAL,
    currency TEXT,
    source TEXT,
    captured_at TEXT,
    UNIQUE(symbol, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_events_published ON events(published);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _event_guid(source, title, link):
    raw = f"{source}|{title.strip()[:120]}|{link}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _master_conn():
    """Persistent connection for writes (single-threaded via lock)."""
    global _MASTER_CONN
    if _MASTER_CONN is None:
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _MASTER_CONN = conn
    return _MASTER_CONN


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def insert_event(source, title, link, published, summary, language):
    """Insert an event. Returns 'inserted' or 'existing'. Call commit() to persist."""
    with _WRITE_LOCK:
        conn = _master_conn()
        try:
            cur = conn.execute(
                """SELECT id FROM events WHERE guid=?""",
                (_event_guid(source, title, link),),
            )
            if cur.fetchone():
                return "existing"
            conn.execute(
                """INSERT INTO events
                   (guid, source, title, link, published, fetched_at, summary, language)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    _event_guid(source, title, link),
                    source,
                    title,
                    link,
                    published,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    summary,
                    language,
                ),
            )
            return "inserted"
        finally:
            pass


def commit():
    """Persist all pending inserts."""
    global _MASTER_CONN
    with _WRITE_LOCK:
        if _MASTER_CONN is not None:
            _MASTER_CONN.commit()


def reset_noise_flags():
    """Clear all noise/duplicate flags (for re-filtering)."""
    with _WRITE_LOCK:
        conn = _master_conn()
        conn.execute("UPDATE events SET is_noise=0, is_duplicate=0")


def mark_noise(ids):
    with _WRITE_LOCK:
        conn = _master_conn()
        conn.execute(
            "UPDATE events SET is_noise=1 WHERE id IN ({})".format(
                ",".join("?" * len(ids))
            ),
            ids,
        )


def mark_duplicate(ids):
    with _WRITE_LOCK:
        conn = _master_conn()
        conn.execute(
            "UPDATE events SET is_duplicate=1 WHERE id IN ({})".format(
                ",".join("?" * len(ids))
            ),
            ids,
        )


def update_analysis(eid, category, severity, sentiment, related_tickers, impact_notes):
    with _WRITE_LOCK:
        conn = _master_conn()
        conn.execute(
            """UPDATE events SET category=?, severity=?, sentiment=?,
               related_tickers=?, impact_notes=?, status='analyzed' WHERE id=?""",
            (category, severity, sentiment, related_tickers, impact_notes, eid),
        )


def unanalyzed(limit=200, language=None):
    """Events that passed noise filter but have not been analyzed."""
    conn = connect()
    try:
        sql = (
            "SELECT * FROM events WHERE is_noise=0 AND is_duplicate=0 "
            "AND status='new'"
        )
        params = []
        if language:
            sql += " AND language=?"
            params.append(language)
        sql += " ORDER BY published DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def recent_events(limit=50, severity_min=0, category=None):
    conn = connect()
    try:
        sql = (
            "SELECT * FROM events WHERE is_noise=0 AND is_duplicate=0 "
            "AND severity>=?"
        )
        params = [severity_min]
        if category:
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY published DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_market_snapshot(symbol, name, price, change_pct, currency, source):
    with _WRITE_LOCK:
        conn = _master_conn()
        captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """INSERT OR REPLACE INTO market_snapshots
               (symbol, name, price, change_pct, currency, source, captured_at)
               VALUES (?,?,?,?,?,?,?)""",
            (symbol, name, price, change_pct, currency, source, captured),
        )


def latest_market_snapshot(symbol):
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT * FROM market_snapshots WHERE symbol=?
               ORDER BY captured_at DESC LIMIT 1""",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows][0] if rows else None
    finally:
        conn.close()


def stats():
    conn = connect()
    try:
        row = conn.execute(
            """SELECT
                (SELECT COUNT(*) FROM events) AS total,
                (SELECT COUNT(*) FROM events WHERE is_noise=0 AND is_duplicate=0) AS kept,
                (SELECT COUNT(*) FROM events WHERE status='analyzed') AS analyzed,
                (SELECT COUNT(*) FROM events WHERE severity>=2) AS important,
                (SELECT COUNT(*) FROM market_snapshots) AS snapshots
            """
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def event_trend(days=7):
    """Per-day event counts for the last N days. Returns list of (date, important, total)."""
    conn = connect()
    try:
        sql = """
            SELECT substr(published, 1, 10) AS d,
                   SUM(CASE WHEN severity >= 2 THEN 1 ELSE 0 END) AS imp,
                   COUNT(*) AS total
            FROM events
            WHERE is_noise=0 AND is_duplicate=0
            GROUP BY d ORDER BY d DESC LIMIT ?
        """
        rows = conn.execute(sql, (days,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
