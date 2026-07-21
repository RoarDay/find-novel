"""tracker.py 单测：追更比对 new 计算（首次 None / 持平 0 / 新增 N）。用 tmp db。"""

import pytest

from novel_crawler import config, db, tracker
from novel_crawler.base import SearchResult
from novel_crawler.registry import ParserRegistry


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(tracker, "db", db)  # tracker 用真实 db 模块（指向 tmp 路径）
    db.init_db()
    return db


class _FakeParser:
    headers: dict = {}

    def __init__(self, total):
        self._total = total

    def parse_catalog(self, soup, base_url):
        return [(f"第{i}章", f"u{i}") for i in range(1, self._total + 1)]


class _FakeEngine:
    def cached_fetch(self, url, headers=None):
        return "<html></html>"


def _setup(tmp_db, total):
    tmp_db.create_booklist("待读")
    tmp_db.add_book(SearchResult(title="书A", url="https://x.com/1", source="x.com"))
    tmp_db.add_to_booklist("待读", "https://x.com/1")
    reg = ParserRegistry()
    reg._parsers = {"x.com": _FakeParser(total)}
    return reg, _FakeEngine()


def test_track_first_time_new_is_none(tmp_db):
    reg, eng = _setup(tmp_db, 13)
    r = tracker.track_booklist("待读", eng, reg)
    assert len(r) == 1
    assert r[0]["new"] is None  # 首次无上次快照
    assert r[0]["curr_total"] == 13
    assert r[0]["prev_total"] is None
    assert r[0]["last_chapter"] == "第13章"


def test_track_no_change_new_is_zero(tmp_db):
    reg, eng = _setup(tmp_db, 13)
    tracker.track_booklist("待读", eng, reg)  # 建快照
    r = tracker.track_booklist("待读", eng, reg)  # 第二次，持平
    assert r[0]["new"] == 0
    assert r[0]["prev_total"] == 13


def test_track_detects_new_chapters(tmp_db):
    reg, eng = _setup(tmp_db, 13)
    tracker.track_booklist("待读", eng, reg)
    # 目录增长到 16
    reg._parsers = {"x.com": _FakeParser(16)}
    r = tracker.track_booklist("待读", eng, reg)
    assert r[0]["new"] == 3
    assert r[0]["curr_total"] == 16
    assert r[0]["last_chapter"] == "第16章"


def test_track_empty_booklist(tmp_db):
    reg = ParserRegistry()
    assert tracker.track_booklist("不存在", _FakeEngine(), reg) == []
