"""A thin DB-API wrapper that works for both SQLite and PostgreSQL.

All app/migration SQL is written with '?' placeholders; this layer rewrites them
to '%s' for PostgreSQL. SQLite needs nothing extra; PostgreSQL needs `psycopg`
(install: pip install "psycopg[binary]").
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import DbConfig, load_config


class Database:
    def __init__(self, url: str | None = None):
        self.cfg: DbConfig = load_config(url)
        self.conn = None

    # --- lifecycle ---------------------------------------------------------

    def connect(self) -> "Database":
        if self.cfg.engine == "sqlite":
            import sqlite3
            Path(self.cfg.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False: the threaded web server serialises access
            # with a lock, so sharing one connection across threads is safe.
            self.conn = sqlite3.connect(self.cfg.sqlite_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            # WAL lets a background writer (auto-refresh) and readers run
            # concurrently without "database is locked"; busy_timeout waits briefly.
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=5000")
        else:  # postgresql
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as e:
                raise RuntimeError(
                    "PostgreSQL selected but `psycopg` is not installed.\n"
                    "  pip install \"psycopg[binary]\"") from e
            # dict_row so rows support r["col"] access like sqlite3.Row
            self.conn = psycopg.connect(
                host=self.cfg.host, port=self.cfg.port, user=self.cfg.user,
                password=self.cfg.password, dbname=self.cfg.dbname, row_factory=dict_row)
        return self

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def commit(self) -> None:
        self.conn.commit()

    # --- placeholder handling ---------------------------------------------

    def _q(self, sql: str) -> str:
        return sql if self.cfg.engine == "sqlite" else sql.replace("?", "%s")

    # --- execution helpers -------------------------------------------------

    def execute(self, sql: str, params: tuple = ()):  # returns a cursor
        cur = self.conn.cursor()
        cur.execute(self._q(sql), params)
        return cur

    def executemany(self, sql: str, rows) -> None:
        cur = self.conn.cursor()
        cur.executemany(self._q(sql), rows)

    def fetchall(self, sql: str, params: tuple = ()):
        return self.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: tuple = ()):
        return self.execute(sql, params).fetchone()

    def run_script(self, sql: str) -> None:
        """Run a multi-statement SQL script (migrations)."""
        if self.cfg.engine == "sqlite":
            self.conn.executescript(sql)
        else:
            for stmt in (s.strip() for s in sql.split(";")):
                if stmt:
                    self.conn.cursor().execute(stmt)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        if self.conn:
            if exc[0] is None:
                self.commit()
            self.close()


def describe() -> str:
    cfg = load_config()
    if cfg.engine == "sqlite":
        return f"SQLite file: {cfg.sqlite_path}"
    return f"PostgreSQL: {cfg.user}@{cfg.host}:{cfg.port}/{cfg.dbname}"
