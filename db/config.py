"""Connection configuration — parse DATABASE_URL into engine + params.

Examples:
  sqlite:///data/askterritory.db                 (relative file — default)
  sqlite:////absolute/path/askterritory.db       (absolute file)
  postgresql://user:pass@localhost:5432/askterritory
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse, unquote

DEFAULT_URL = "sqlite:///data/askterritory.db"


@dataclass
class DbConfig:
    engine: str                 # "sqlite" | "postgresql"
    url: str
    sqlite_path: str | None = None
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    dbname: str | None = None


def load_config(url: str | None = None) -> DbConfig:
    url = url or os.environ.get("DATABASE_URL", DEFAULT_URL)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme.startswith("sqlite"):
        # sqlite:///rel/path  -> path is parsed.path without leading slash for relative
        path = url.split("sqlite://", 1)[1]
        path = path.lstrip("/") if path.startswith("///") is False else path
        # normalise: 'sqlite:///data/x.db' -> 'data/x.db'; 'sqlite:////abs' -> '/abs'
        raw = url[len("sqlite://"):]
        if raw.startswith("///"):          # 4 slashes total -> absolute
            path = raw[2:]                  # keep leading '/'
        else:                               # 3 slashes -> relative
            path = raw.lstrip("/")
        return DbConfig(engine="sqlite", url=url, sqlite_path=path)

    if scheme in ("postgresql", "postgres"):
        return DbConfig(
            engine="postgresql", url=url,
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=unquote(parsed.username) if parsed.username else os.environ.get("USER"),
            password=unquote(parsed.password) if parsed.password else None,
            dbname=(parsed.path or "/askterritory").lstrip("/"),
        )

    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme!r}")
