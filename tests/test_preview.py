"""preview.py 单测：前 N 章正文聚合 + 锁章标记。注入假 parser/engine，不触网。"""

from novel_crawler import preview
from novel_crawler.registry import ParserRegistry


class _FakeParser:
    headers: dict = {}

    def __init__(self, chapters):
        self._chapters = chapters  # [(title, url)]

    def parse_catalog(self, soup, base_url):
        return list(self._chapters)


class _FakeEngine:
    def __init__(self, catalog_html, content_by_url):
        self._html = catalog_html
        self._content = content_by_url

    def cached_fetch(self, url, headers=None):
        return self._html

    def fetch_chapter(self, url, parser):
        return self._content.get(url)


def test_preview_aggregates_first_n_with_content():
    reg = ParserRegistry()
    reg._parsers = {"x.com": _FakeParser([("第1章", "u1"), ("第2章", "u2"), ("第3章", "u3")])}
    eng = _FakeEngine("<html></html>", {"u1": "正文1", "u2": "正文2", "u3": "正文3"})
    out = preview.preview("https://x.com/book/1", 2, eng, reg)
    assert [c["title"] for c in out] == ["第1章", "第2章"]
    assert out[0]["content"] == "正文1"
    assert all(not c["locked"] for c in out)


def test_preview_marks_locked_when_content_empty():
    reg = ParserRegistry()
    reg._parsers = {"x.com": _FakeParser([("第1章", "u1"), ("第2章", "u2")])}
    # u2 正文为空（VIP 锁 / 抓取失败）
    eng = _FakeEngine("<html></html>", {"u1": "正文1", "u2": ""})
    out = preview.preview("https://x.com/book/1", 5, eng, reg)
    assert out[0]["locked"] is False
    assert out[1]["locked"] is True
    assert out[1]["content"] == ""


def test_preview_empty_when_no_catalog():
    reg = ParserRegistry()
    reg._parsers = {"x.com": _FakeParser([])}
    eng = _FakeEngine("<html></html>", {})
    assert preview.preview("https://x.com/book/1", 3, eng, reg) == []
