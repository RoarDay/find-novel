import pytest

from novel_crawler.registry import ParserRegistry

EXPECTED_SITES = {
    "92yanqing.com",
    "min-yuan.com",
    "zongheng.com",
    "qidian.com",
    "qimao.com",
    "faloo.com",
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
