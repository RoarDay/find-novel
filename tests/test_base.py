from novel_crawler.base import BaseParser, SearchResult


class _MinParser(BaseParser):
    """ ponytail: 最小 BaseParser 子类，验证默认行为。domain 用类属性覆盖抽象 property。 """
    domain = "example.com"

    def parse_catalog(self, soup, base_url):
        return [(a.get_text(strip=True), a.get("href", "")) for a in soup.select("a.chapter")]

    def parse_content(self, soup):
        return ""


def test_search_result_defaults():
    r = SearchResult(title="t", url="u", source="s")
    assert r.title == "t" and r.url == "u" and r.source == "s"
    assert r.author == ""
    assert r.blurb == ""
    assert r.word_count == ""


def _noop_fetch(*a, **k):
    return ""


def test_base_default_methods_return_empty():
    p = _MinParser()
    fetch = _noop_fetch
    assert p.search("kw", fetch) == []
    assert p.get_blurb("u", fetch) == ""
    assert p.get_rank("r", fetch) == []
    assert p.get_category("c", fetch) == []
    assert p.get_similar("u", fetch) == []


def test_get_chapter_titles_uses_parse_catalog_and_limit():
    p = _MinParser()
    html = """
    <html><body>
      <a class="chapter" href="/c1">第一章</a>
      <a class="chapter" href="/c2">第二章</a>
      <a class="chapter" href="/c3">第三章</a>
    </body></html>
    """
    seen = {}

    def fake_fetch(url, headers=None):
        seen["url"] = url
        seen["headers"] = headers
        return html

    titles = p.get_chapter_titles("http://example.com/book/1", fake_fetch, limit=2)
    assert titles == ["第一章", "第二章"]
    assert seen["url"] == "http://example.com/book/1"
    assert seen["headers"] == p.headers


def test_get_chapter_titles_empty_when_fetch_returns_none():
    p = _MinParser()
    assert p.get_chapter_titles("http://example.com/x", lambda *a, **k: None) == []
