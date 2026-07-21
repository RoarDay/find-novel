"""请求缓存（opt-in）：短期避免重复抓搜索/详情页等**元数据**。

章节正文下载**不**缓存（大且一次性，由调用方不传 cache=True 保证）。
sqlite 表 `fetch_cache(key, body, fetched_at)`，复用 `config.DB_PATH`，
`CREATE TABLE IF NOT EXISTS` 幂等。短连接，与 db.py 同模式。
"""

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from novel_crawler import config


def _connect() -> sqlite3.Connection:
    parent = os.path.dirname(config.DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fetch_cache ("
        "  key        TEXT PRIMARY KEY,"
        "  body       TEXT NOT NULL,"
        "  fetched_at TEXT NOT NULL"
        ")"
    )
    return conn


@contextmanager
def _get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def make_key(
    method: str, url: str, data: dict | None, headers: dict | None
) -> str:
    """(method, url, data, headers) → 稳定摘要 key。headers 排序保证稳定。"""
    h = headers or {}
    raw = f"{method.upper()}|{url}|{data!r}|{sorted(h.items())!r}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get(key: str, ttl: int = config.CACHE_TTL) -> str | None:
    """命中且未过期返回 body，否则 None。"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT body, fetched_at FROM fetch_cache WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    try:
        age = (datetime.now() - datetime.fromisoformat(row["fetched_at"])).total_seconds()
    except ValueError:
        return None
    if age > ttl:
        return None
    return row["body"]


def set(key: str, body: str) -> None:
    """写回（upsert）。空 body 不写。"""
    if not body:
        return
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO fetch_cache(key, body, fetched_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET body=excluded.body, fetched_at=excluded.fetched_at",
            (key, body, now),
        )
