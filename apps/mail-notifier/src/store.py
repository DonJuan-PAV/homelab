"""
Memory of the notifier: a small SQLite database (one file, no server).

It records every email it has seen, so:
  - each important email is counted only once, even after a restart;
  - the dashboard can show how many important emails arrived, per mailbox.
Only counts ever leave this file, never subjects or senders.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from models import Email

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    email_key     TEXT PRIMARY KEY,   -- account + provider ID
    account       TEXT NOT NULL,
    subject       TEXT,
    sender        TEXT,
    important     INTEGER NOT NULL,   -- 1 = counted, 0 = skipped as noise
    skip_reason   TEXT,
    seen_day      TEXT NOT NULL,      -- local date, for "today" counts
    seen_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _now() -> datetime:
    return datetime.now().astimezone()  # local time, with time zone


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._db() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        """Open the database, save changes when done, and always close it."""
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def is_seen(self, email: Email) -> bool:
        with self._db() as conn:
            return conn.execute(
                "SELECT 1 FROM seen WHERE email_key = ?", (email.key,)).fetchone() is not None

    def mark_seen(self, email: Email, important: bool, skip_reason: str | None = None) -> None:
        now = _now()
        with self._db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen VALUES (?,?,?,?,?,?,?,?)",
                (email.key, email.account, email.subject, email.sender, int(important),
                 skip_reason, now.date().isoformat(), now.isoformat(timespec="seconds")),
            )

    def set_meta(self, key: str, value: str) -> None:
        with self._db() as conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def get_meta(self, key: str) -> str | None:
        with self._db() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def stats(self, accounts: list[str]) -> dict:
        """
        Numbers for the dashboard, for example:
          {"today": 3, "total": 41, "outlook_today": 2, "gmail_today": 1,
           "outlook_total": 30, "gmail_total": 11, "last_check": "..."}
        Every listed account appears, even with 0, so the widget never shows blanks.
        """
        today = _now().date().isoformat()
        with self._db() as conn:
            rows = conn.execute(
                "SELECT account, COUNT(*), SUM(seen_day = ?) FROM seen "
                "WHERE important = 1 GROUP BY account", (today,)).fetchall()

        result = {"today": 0, "total": 0}
        for account in accounts:
            result[f"{account}_today"] = 0
            result[f"{account}_total"] = 0
        for account, total, today_count in rows:
            result[f"{account}_today"] = today_count or 0
            result[f"{account}_total"] = total
            result["today"] += today_count or 0
            result["total"] += total
        result["last_check"] = self.get_meta("last_check")
        return result
