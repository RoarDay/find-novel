from bs4 import BeautifulSoup

from novel_crawler.sites.faloo import FalooParser
from novel_crawler.sites.min_yuan import MinYuanParser
from novel_crawler.sites.qidian import QidianParser
from novel_crawler.sites.qimao import QimaoParser
from novel_crawler.sites.yanqing92 import Yanqing92Parser
from novel_crawler.sites.zongheng import ZonghengParser

# ---------- yanqing92 ----------

def test_yanqing92_parse_catalog(fixture_html):
    soup = BeautifulSoup(fixture_html("yanqing92_catalog"), "lxml")
    chapters = Yanqing92Parser().parse_catalog(soup, "https://www.92yanqing.com/book/1/")
    assert chapters == [
        ("第一章 开端", "https://www.92yanqing.com/book/1/ch1.html"),
        ("第二章 发展", "https://www.92yanqing.com/book/1/ch2.html"),
    ]


def test_yanqing92_parse_content(fixture_html):
    soup = BeautifulSoup(fixture_html("yanqing92_content"), "lxml")
    text = Yanqing92Parser().parse_content(soup)
    assert "正文段落一" in text
    assert "正文段落二" in text


# ---------- min_yuan ----------

def test_min_yuan_parse_catalog(fixture_html):
    soup = BeautifulSoup(fixture_html("min_yuan_catalog"), "lxml")
    chapters = MinYuanParser().parse_catalog(soup, "https://www.min-yuan.com/book/2/")
    assert chapters == [
        ("第一章 起始", "https://www.min-yuan.com/book/2/c1.html"),
        ("第二章 延续", "https://www.min-yuan.com/book/2/c2.html"),
    ]


def test_min_yuan_parse_content(fixture_html):
    soup = BeautifulSoup(fixture_html("min_yuan_content"), "lxml")
    text = MinYuanParser().parse_content(soup)
    assert "小原正文段落一" in text
    assert "小原正文段落二" in text


# ---------- zongheng ----------

def test_zongheng_parse_catalog(fixture_html):
    soup = BeautifulSoup(fixture_html("zongheng_catalog"), "lxml")
    chapters = ZonghengParser().parse_catalog(soup, "https://book.zongheng.com/showchapter/1.html")
    assert chapters == [
        ("第一章 入门", "https://book.zongheng.com/chapter/1.html"),
        ("第二章 进阶", "https://book.zongheng.com/chapter/2.html"),
    ]


def test_zongheng_parse_content(fixture_html):
    soup = BeautifulSoup(fixture_html("zongheng_content"), "lxml")
    text = ZonghengParser().parse_content(soup)
    assert "纵横正文段落一" in text
    assert "纵横正文段落二" in text


# ---------- qidian ----------

def test_qidian_parse_catalog(fixture_html):
    soup = BeautifulSoup(fixture_html("qidian_catalog"), "lxml")
    chapters = QidianParser().parse_catalog(soup, "https://m.qidian.com/book/12345/catalog/")
    assert chapters == [
        ("第一章 启程", "https://m.qidian.com/chapter/12345/1001/"),
        ("第二章 抵达", "https://m.qidian.com/chapter/12345/1002/"),
    ]


def test_qidian_parse_content(fixture_html):
    soup = BeautifulSoup(fixture_html("qidian_content"), "lxml")
    text = QidianParser().parse_content(soup)
    assert "起点正文段落一" in text


def test_qidian_parse_content_locked_returns_empty():
    """VIP 锁章（含 lock-mask class）应返回空。"""
    html = '<html><body><main class="content lock-mask"><p>看不见</p></main></body></html>'
    soup = BeautifulSoup(html, "lxml")
    assert QidianParser().parse_content(soup) == ""


# ---------- qimao ----------

def test_qimao_parse_catalog(fixture_html):
    soup = BeautifulSoup(fixture_html("qimao_catalog"), "lxml")
    chapters = QimaoParser().parse_catalog(soup, "https://www.qimao.com/shuku/1860026/")
    assert chapters == [("最新章：终章标题", "https://www.qimao.com/shuku/1860026-12/")]


def test_qimao_parse_content_filters_short_lines(fixture_html):
    soup = BeautifulSoup(fixture_html("qimao_content"), "lxml")
    text = QimaoParser().parse_content(soup)
    assert "第一段" in text
    assert "第二段" in text
    assert "短句" not in text  # <20 字被过滤


# ---------- faloo ----------

def test_faloo_parse_catalog(fixture_html):
    soup = BeautifulSoup(fixture_html("faloo_catalog"), "lxml")
    chapters = FalooParser().parse_catalog(soup, "https://b.faloo.com/12345.html")
    assert chapters == [
        ("第一章 序章", "https://b.faloo.com/12345_1.html"),
        ("第二章 正篇", "https://b.faloo.com/12345_2.html"),
    ]


def test_faloo_parse_content(fixture_html):
    soup = BeautifulSoup(fixture_html("faloo_content"), "lxml")
    text = FalooParser().parse_content(soup)
    assert "飞卢正文段落一" in text
    assert "飞卢正文段落二" in text
