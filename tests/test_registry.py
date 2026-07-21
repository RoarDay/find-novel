import pytest

from novel_crawler.registry import ParserRegistry

EXPECTED_SITES = {
    "92yanqing.com",
    "min-yuan.com",
    "zongheng.com",
    "qidian.com",
    "qimao.com",
    "faloo.com",
    "fanqienovel.com",
}


def test_auto_registers_six_sites():
    reg = ParserRegistry()
    assert set(reg.list_supported()) == EXPECTED_SITES


def test_get_parser_matches_subdomain():
    reg = ParserRegistry()
    p = reg.get_parser("https://www.92yanqing.com/book/123")
    assert p.domain == "92yanqing.com"
    p2 = reg.get_parser("https://m.qidian.com/book/1/catalog/")
    assert p2.domain == "qidian.com"


def test_get_by_source_matches_domain():
    reg = ParserRegistry()
    assert reg.get_by_source("m.qidian.com").domain == "qidian.com"
    assert reg.get_by_source("92yanqing.com").domain == "92yanqing.com"


def test_get_parser_unknown_raises():
    reg = ParserRegistry()
    with pytest.raises(ValueError):
        reg.get_parser("https://example.com/x")


def test_search_all_swallows_single_failure():
    """单站 search 抛异常时，其它站照常聚合，不崩。"""
    reg = ParserRegistry()
    p = reg.get_by_source("92yanqing.com")

    def boom(keyword, fetch):
        raise RuntimeError("boom")

    original = p.search
    p.search = boom
    try:
        results = reg.search_all("kw", fetch=lambda *a, **k: "")
        assert isinstance(results, list)
    finally:
        p.search = original


def test_search_all_concurrent_preserves_order_and_isolates_failure():
    """注入 3 个假 parser（a, b-抛异常, c），验证并发后顺序=注册顺序 + b 被隔离。"""
    from novel_crawler.base import SearchResult

    class _Fake:
        def __init__(self, domain, res):
            self.domain = domain
            self._res = res

        def search(self, keyword, fetch):
            if isinstance(self._res, Exception):
                raise self._res
            return self._res

    reg = ParserRegistry()
    reg._parsers = {
        "a.com": _Fake("a.com", [SearchResult(title="a1", url="ua", source="a.com")]),
        "b.com": _Fake("b.com", RuntimeError("b boom")),
        "c.com": _Fake("c.com", [
            SearchResult(title="c1", url="uc1", source="c.com"),
            SearchResult(title="c2", url="uc2", source="c.com"),
        ]),
    }
    results = reg.search_all("kw", fetch=lambda *a, **k: "")
    # b 失败被隔离；顺序 = a 的结果在前，c 的在后
    assert [r.title for r in results] == ["a1", "c1", "c2"]
