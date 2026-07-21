"""SQLite 持久化：books / search_history / booklists / booklist_items。

stdlib sqlite3，单文件（`config.DB_PATH`），短连接（每次操作 connect/commit/close，
避免跨线程共享——engine 是 ThreadPoolExecutor 多线程的）。参数化查询防注入。
schema `CREATE TABLE IF NOT EXISTS` 幂等，无需迁移工具。
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from novel_crawler import config
from novel_crawler.base import SearchResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    author      TEXT,
    blurb       TEXT,
    word_count  TEXT,
    url         TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS search_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword       TEXT    NOT NULL,
    result_count  INTEGER NOT NULL,
    searched_at   TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS booklists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS booklist_items (
    booklist_id  INTEGER NOT NULL,
    book_id      INTEGER NOT NULL,
    added_at     TEXT    NOT NULL,
    PRIMARY KEY (booklist_id, book_id),
    FOREIGN KEY (booklist_id) REFERENCES booklists(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id)     REFERENCES books(id)     ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS book_snapshots (
    book_id            INTEGER PRIMARY KEY,
    chapter_total      INTEGER NOT NULL,
    last_chapter_title TEXT,
    checked_at         TEXT    NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);
"""


def _connect() -> sqlite3.Connection:
    parent = os.path.dirname(config.DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _get_conn() -> Iterator[sqlite3.Connection]:
    """短连接：建表（IF NOT EXISTS）→ yield → commit/rollback → close。"""
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """显式建表（幂等；repo 函数自动调，正常无需手动调）。"""
    with _get_conn():
        pass


# ── books ──────────────────────────────────────────────────────────────

def add_book(r: SearchResult) -> int:
    """upsert by url（ON CONFLICT 更新非主键字段），返回 book id。"""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO books(source, title, author, blurb, word_count, url, created_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET "
            "source=excluded.source, title=excluded.title, author=excluded.author, "
            "blurb=excluded.blurb, word_count=excluded.word_count",
            (r.source, r.title, r.author, r.blurb, r.word_count, r.url, now),
        )
        row = conn.execute("SELECT id FROM books WHERE url = ?", (r.url,)).fetchone()
        return int(row["id"])


def get_book(url: str) -> sqlite3.Row | None:
    with _get_conn() as conn:
        return conn.execute("SELECT * FROM books WHERE url = ?", (url,)).fetchone()


def search_books(keyword: str) -> list[sqlite3.Row]:
    like = f"%{keyword}%"
    with _get_conn() as conn:
        return conn.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? "
            "ORDER BY created_at DESC",
            (like, like),
        ).fetchall()


def list_all_books() -> list[sqlite3.Row]:
    """books 全表（去重/聚合用）。"""
    with _get_conn() as conn:
        return conn.execute("SELECT * FROM books ORDER BY created_at DESC").fetchall()


# ── search_history ────────────────────────────────────────────────────

def record_search(keyword: str, n: int) -> None:
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO search_history(keyword, result_count, searched_at) "
            "VALUES(?,?,?)",
            (keyword, n, now),
        )


def list_search_history(limit: int = 50) -> list[sqlite3.Row]:
    with _get_conn() as conn:
        return conn.execute(
            "SELECT * FROM search_history ORDER BY searched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


# ── booklists ─────────────────────────────────────────────────────────

def create_booklist(name: str) -> int:
    """重名抛 ValueError（UNIQUE 约束）。"""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO booklists(name, created_at) VALUES(?,?)",
                (name, now),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"书单 '{name}' 已存在") from e
        row = conn.execute(
            "SELECT id FROM booklists WHERE name = ?", (name,)
        ).fetchone()
        return int(row["id"])


def list_booklists() -> list[sqlite3.Row]:
    with _get_conn() as conn:
        return conn.execute(
            "SELECT * FROM booklists ORDER BY created_at DESC"
        ).fetchall()


def add_to_booklist(name: str, url: str) -> None:
    """书单或 book 不存在抛 ValueError；重复加幂等（不报错）。"""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        bl = conn.execute(
            "SELECT id FROM booklists WHERE name = ?", (name,)
        ).fetchone()
        if bl is None:
            raise ValueError(f"书单 '{name}' 不存在")
        book = conn.execute(
            "SELECT id FROM books WHERE url = ?", (url,)
        ).fetchone()
        if book is None:
            raise ValueError(f"书 '{url}' 不在 books 表，先 add_book")
        try:
            conn.execute(
                "INSERT INTO booklist_items(booklist_id, book_id, added_at) "
                "VALUES(?,?,?)",
                (bl["id"], book["id"], now),
            )
        except sqlite3.IntegrityError:
            pass  # 已在书单，幂等


def remove_from_booklist(name: str, url: str) -> None:
    """书单不存在抛 ValueError；book 不在书单静默（幂等）。"""
    with _get_conn() as conn:
        bl = conn.execute(
            "SELECT id FROM booklists WHERE name = ?", (name,)
        ).fetchone()
        if bl is None:
            raise ValueError(f"书单 '{name}' 不存在")
        book = conn.execute(
            "SELECT id FROM books WHERE url = ?", (url,)
        ).fetchone()
        if book is None:
            return
        conn.execute(
            "DELETE FROM booklist_items WHERE booklist_id = ? AND book_id = ?",
            (bl["id"], book["id"]),
        )


def get_booklist_books(name: str) -> list[sqlite3.Row]:
    with _get_conn() as conn:
        return conn.execute(
            "SELECT b.* FROM books b "
            "JOIN booklist_items bi ON bi.book_id = b.id "
            "JOIN booklists bl ON bl.id = bi.booklist_id "
            "WHERE bl.name = ? ORDER BY bi.added_at DESC",
            (name,),
        ).fetchall()


# ── book_snapshots（追更）──────────────────────────────────────────────

def upsert_snapshot(book_id: int, chapter_total: int, last_chapter_title: str) -> None:
    """upsert 最新目录快照（按 book_id 单行）。"""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO book_snapshots(book_id, chapter_total, last_chapter_title, checked_at) "
            "VALUES(?,?,?,?) "
            "ON CONFLICT(book_id) DO UPDATE SET "
            "chapter_total=excluded.chapter_total, "
            "last_chapter_title=excluded.last_chapter_title, checked_at=excluded.checked_at",
            (book_id, chapter_total, last_chapter_title, now),
        )


def get_snapshot(book_id: int) -> sqlite3.Row | None:
    with _get_conn() as conn:
        return conn.execute(
            "SELECT * FROM book_snapshots WHERE book_id = ?", (book_id,)
        ).fetchone()


# ── 协同推荐（书单共现）──────────────────────────────────────────────

def recommend_for(url: str, limit: int = 10) -> list[sqlite3.Row]:
    """「读过 X 也读 Y」：该书所在书单里的其它书，按共现次数降序。
    该书不在任何书单 / url 不在 books 表 → []。每行含 books.* + co(共现次数)。"""
    with _get_conn() as conn:
        return conn.execute(
            "SELECT b.*, COUNT(*) AS co "
            "FROM booklist_items bi1 "
            "JOIN booklist_items bi2 ON bi2.booklist_id = bi1.booklist_id "
            "JOIN books b ON b.id = bi2.book_id "
            "WHERE bi1.book_id = (SELECT id FROM books WHERE url = ?) "
            "AND bi2.book_id != bi1.book_id "
            "GROUP BY b.id "
            "ORDER BY co DESC, b.title "
            "LIMIT ?",
            (url, limit),
        ).fetchall()
