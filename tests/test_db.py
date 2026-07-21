"""db.py 单测：用 tmp_path fixture 隔离 DB_PATH，测建表 + booklist CRUD + book upsert。"""

import pytest

from novel_crawler import config, db
from novel_crawler.base import SearchResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """每个测试用独立临时 DB 文件。"""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


def _r(url="http://x.com/1", title="t", source="x.com", **kw):
    return SearchResult(title=title, url=url, source=source, **kw)


# ── books ─────────────────────────────────────────────────────────────

def test_add_book_then_get_returns_row(tmp_db):
    r = _r(author="甲", blurb="简介", word_count="10万字")
    bid = tmp_db.add_book(r)
    row = tmp_db.get_book(r.url)
    assert row is not None
    assert row["id"] == bid
    assert row["title"] == "t"
    assert row["author"] == "甲"
    assert row["blurb"] == "简介"
    assert row["word_count"] == "10万字"
    assert row["source"] == "x.com"


def test_add_book_upsert_dedupes_by_url(tmp_db):
    """同 url 二次 add：不新建行，更新字段，返回同 id。"""
    id1 = tmp_db.add_book(_r(title="旧标题", author="旧作者"))
    id2 = tmp_db.add_book(_r(title="新标题", author="新作者"))
    assert id1 == id2
    row = tmp_db.get_book(_r().url)
    assert row["title"] == "新标题"
    assert row["author"] == "新作者"


def test_search_books_matches_title_or_author(tmp_db):
    tmp_db.add_book(_r(url="u1", title="凡人修仙", author="忘语"))
    tmp_db.add_book(_r(url="u2", title="斗破苍穹", author="天蚕土豆"))
    tmp_db.add_book(_r(url="u3", title="凡人修仙传2", author="x"))
    hits = tmp_db.search_books("凡人")
    assert len(hits) == 2
    assert {h["url"] for h in hits} == {"u1", "u3"}


# ── search_history ────────────────────────────────────────────────────

def test_record_search_then_list(tmp_db):
    tmp_db.record_search("凡人修仙", 3)
    tmp_db.record_search("斗破苍穹", 5)
    rows = tmp_db.list_search_history()
    assert len(rows) == 2
    keywords = {r["keyword"] for r in rows}
    assert keywords == {"凡人修仙", "斗破苍穹"}
    # result_count 字段落库
    counts = {r["keyword"]: r["result_count"] for r in rows}
    assert counts["凡人修仙"] == 3


# ── booklists ─────────────────────────────────────────────────────────

def test_create_booklist_duplicate_raises(tmp_db):
    tmp_db.create_booklist("待读")
    with pytest.raises(ValueError):
        tmp_db.create_booklist("待读")


def test_add_to_booklist_requires_existing_book_and_list(tmp_db):
    # 书单不存在
    with pytest.raises(ValueError):
        tmp_db.add_to_booklist("不存在", "http://x.com/1")
    tmp_db.create_booklist("待读")
    # 书不存在
    with pytest.raises(ValueError):
        tmp_db.add_to_booklist("待读", "http://x.com/missing")


def test_booklist_full_crud(tmp_db):
    tmp_db.create_booklist("待读")
    tmp_db.add_book(_r(url="http://x.com/1", title="书A"))
    tmp_db.add_book(_r(url="http://x.com/2", title="书B"))

    tmp_db.add_to_booklist("待读", "http://x.com/1")
    tmp_db.add_to_booklist("待读", "http://x.com/2")
    books = tmp_db.get_booklist_books("待读")
    assert {b["title"] for b in books} == {"书A", "书B"}

    # 重复 add 幂等（不抛错）
    tmp_db.add_to_booklist("待读", "http://x.com/1")
    assert len(tmp_db.get_booklist_books("待读")) == 2

    # remove
    tmp_db.remove_from_booklist("待读", "http://x.com/1")
    books = tmp_db.get_booklist_books("待读")
    assert len(books) == 1
    assert books[0]["title"] == "书B"

    # remove 不存在的 book 静默（幂等）
    tmp_db.remove_from_booklist("待读", "http://x.com/never")
    assert len(tmp_db.get_booklist_books("待读")) == 1


def test_list_booklists_ordered(tmp_db):
    tmp_db.create_booklist("a")
    tmp_db.create_booklist("b")
    names = [b["name"] for b in tmp_db.list_booklists()]
    assert names == ["b", "a"]  # DESC by created_at


# ── book_snapshots（追更）──────────────────────────────────────────────

def test_snapshot_upsert_and_get(tmp_db):
    bid = tmp_db.add_book(_r(url="u1", title="书A"))
    assert tmp_db.get_snapshot(bid) is None
    tmp_db.upsert_snapshot(bid, 100, "第100章")
    row = tmp_db.get_snapshot(bid)
    assert row["chapter_total"] == 100
    assert row["last_chapter_title"] == "第100章"
    # re-upsert 更新
    tmp_db.upsert_snapshot(bid, 130, "第130章")
    row = tmp_db.get_snapshot(bid)
    assert row["chapter_total"] == 130
    assert row["last_chapter_title"] == "第130章"


def test_snapshot_cascades_on_book_delete(tmp_db):
    bid = tmp_db.add_book(_r(url="u1", title="书A"))
    tmp_db.upsert_snapshot(bid, 50, "第50章")
    assert tmp_db.get_snapshot(bid) is not None
    with tmp_db._get_conn() as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (bid,))
    assert tmp_db.get_snapshot(bid) is None  # FK 级联
