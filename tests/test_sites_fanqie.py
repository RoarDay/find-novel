"""fanqie.py 离线单测：__INITIAL_STATE__ 抽取 / PUA 解密 / VIP 锁检测 / book_list 解析。
不触网（线上端到端见 fanqie.py __main__ 烟测，单 session 未验证）。"""

import json

from bs4 import BeautifulSoup

from novel_crawler.sites import fanqie
from novel_crawler.sites._fanqie_font_map import FONT_MAP
from novel_crawler.sites.fanqie import FanqieParser

_PAGE_HTML = """
<html><head>
<script>window.__INITIAL_STATE__={"page":{
  "bookName":"测试书","author":"作者甲","abstract":"这是一段简介",
  "wordNumber":3201,"category":undefined,
  "chapterListWithVolume":[
    [{"itemId":"111","title":"第1章 开端"},{"itemId":"222","title":"第2章 发展"}]
  ]
}};</script>
</head><body></body></html>
"""


def test_decode_pua_known_mapping():
    items = list(FONT_MAP.items())[:6]
    pua_text = "".join(chr(int(cp)) for cp, _ in items)
    expected = "".join(ch for _, ch in items)
    assert fanqie._decode_pua(pua_text) == expected


def test_decode_pua_leaves_non_pua_untouched():
    assert fanqie._decode_pua("普通汉字abc") == "普通汉字abc"


def test_extract_state_normalizes_undefined():
    state = fanqie._extract_state(_PAGE_HTML)
    page = state["page"]
    assert page["bookName"] == "测试书"
    assert page["category"] is None  # undefined→null
    assert page["wordNumber"] == 3201


def test_parse_catalog_from_inline_state():
    soup = BeautifulSoup(_PAGE_HTML, "lxml")
    chapters = FanqieParser().parse_catalog(soup, "https://fanqienovel.com/page/123")
    assert [t for t, _ in chapters] == ["第1章 开端", "第2章 发展"]
    assert chapters[0][1] == "https://fanqienovel.com/reader/111"
    assert chapters[1][1] == "https://fanqienovel.com/reader/222"


def test_parse_content_locked_chapter_returns_empty():
    # 含 VIP 标记 + 仅 1 段 → 锁章，返回空
    html = (
        '<html><body><div class="muye-reader-content noselect">'
        "<p>本章 VIP 内容需下载番茄小说</p>"
        '</div><div>下载番茄 阅读全文 SVIP</div></body></html>'
    )
    soup = BeautifulSoup(html, "lxml")
    assert FanqieParser().parse_content(soup) == ""


def test_parse_content_decodes_pua_paragraphs():
    items = list(FONT_MAP.items())[:5]
    pua_para = "".join(chr(int(cp)) for cp, _ in items)
    decoded_para = "".join(ch for _, ch in items)
    # 3 段以上 + 无锁标记 → 正常解密
    html = (
        '<html><body><div class="muye-reader-content noselect">'
        f"<p>{pua_para}</p><p>{pua_para}</p><p>{pua_para}</p>"
        "</div></body></html>"
    )
    soup = BeautifulSoup(html, "lxml")
    out = FanqieParser().parse_content(soup)
    assert out.count(decoded_para) == 3


def test_fetch_book_list_parses_recommend_json():
    p = FanqieParser()
    resp = {"code": 0, "data": {"book_list": [
        {"bookId": "1", "bookName": "书A", "author": "甲", "abstract": "简介A", "wordNumber": 100},
        {"bookId": "2", "bookName": "书B", "author": "乙", "abstract": "简介B"},
    ]}}
    captured = {}

    def fake_fetch(url, headers=None):
        captured["url"] = url
        return json.dumps(resp)

    results = p.get_category("male", fake_fetch)
    assert "recommend/list" in captured["url"]
    assert "gender=0" in captured["url"]
    assert [r.title for r in results] == ["书A", "书B"]
    assert results[0].blurb == "简介A"
    assert results[0].word_count == "100"
    assert results[1].url.endswith("/page/2")


def test_search_returns_empty():
    assert FanqieParser().search("任意", lambda *a, **k: "") == []
