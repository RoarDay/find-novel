"""diagnose.py 单测：health_check 分类 ok/EMPTY/ERR + 无 sample_url 跳过。注入假 parser。"""

from novel_crawler import diagnose
from novel_crawler.registry import ParserRegistry


class _FakeParser:
    def __init__(self, domain, sample_url=None, blurb="", catalog=None, titles=None,
                 raise_on=None):
        self.domain = domain
        self.sample_url = sample_url
        self.headers = {}
        self._blurb = blurb
        self._catalog = catalog
        self._titles = titles
        self._raise_on = raise_on or set()

    def get_blurb(self, url, fetch):
        if "blurb" in self._raise_on:
            raise RuntimeError("boom")
        return self._blurb

    def parse_catalog(self, soup, base_url):
        if "catalog" in self._raise_on:
            raise ValueError("parse boom")
        return self._catalog or []

    def get_chapter_titles(self, url, fetch, limit=3):
        if "chapters" in self._raise_on:
            raise KeyError("titles boom")
        return self._titles or []


class _FakeFetch:
    def __call__(self, url, headers=None):
        return "<html></html>"


def _reg(*parsers):
    reg = ParserRegistry()
    reg._parsers = {p.domain: p for p in parsers}
    return reg


def test_ok_when_all_methods_return_content():
    reg = _reg(_FakeParser("a.com", "http://a/1",
                           blurb="简介", catalog=[("第1章", "u")], titles=["第1章"]))
    rep = diagnose.health_check(reg, _FakeFetch())
    e = rep["a.com"]
    assert e["blurb"] == "ok" and e["catalog"] == "ok" and e["chapters"] == "ok"


def test_empty_flags_selector_failure():
    reg = _reg(_FakeParser("a.com", "http://a/1",
                           blurb="", catalog=[], titles=[]))
    e = diagnose.health_check(reg, _FakeFetch())["a.com"]
    assert e["blurb"] == "EMPTY"
    assert e["catalog"] == "EMPTY"
    assert e["chapters"] == "EMPTY"


def test_err_captures_exception_type():
    reg = _reg(_FakeParser("a.com", "http://a/1", raise_on={"catalog", "chapters"}))
    e = diagnose.health_check(reg, _FakeFetch())["a.com"]
    assert e["catalog"] == "ERR:ValueError"
    assert e["chapters"] == "ERR:KeyError"


def test_skips_parser_without_sample_url():
    reg = _reg(_FakeParser("a.com", "http://a/1"), _FakeParser("b.com"))  # b 无 sample_url
    rep = diagnose.health_check(reg, _FakeFetch())
    assert "a.com" in rep and "b.com" not in rep


def test_samples_override():
    reg = _reg(_FakeParser("a.com"))  # 无内置 sample_url
    rep = diagnose.health_check(reg, _FakeFetch(), samples={"a.com": "http://a/x"})
    assert "a.com" in rep
    assert rep["a.com"]["url"] == "http://a/x"


def test_format_report_highlights_failure():
    reg = _reg(_FakeParser("a.com", "http://a/1", catalog=[]))
    rep = diagnose.health_check(reg, _FakeFetch())
    out = diagnose.format_report(rep)
    assert "⚠" in out
