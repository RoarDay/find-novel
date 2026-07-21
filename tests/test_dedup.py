"""dedup.py 单测：跨站去重分组 + 元数据聚合。row 用 dict 模拟 sqlite3.Row（按键取值）。"""

from novel_crawler.dedup import group_books, normalize


def _row(title, source, url, author="", blurb="", word_count=""):
    return {
        "title": title, "source": source, "url": url,
        "author": author, "blurb": blurb, "word_count": word_count,
    }


def test_normalize_tolerates_punctuation_and_space():
    assert normalize("凡人修仙！", "忘 语") == normalize("凡人修仙", "忘语")
    assert normalize("Book One", "X") == ("bookone", "x")


def test_group_merges_same_book_across_sources():
    rows = [
        _row("凡人修仙", "qidian.com", "u1", author="忘语", blurb="短", word_count="100万"),
        _row("凡人修仙！", "zongheng.com", "u2", author="忘 语",
             blurb="更长的简介", word_count="2089021"),
        _row("斗破苍穹", "qidian.com", "u3", author="天蚕土豆", word_count="500万"),
    ]
    groups = group_books(rows)
    # 多源组排在前
    top = groups[0]
    assert top["title"] == "凡人修仙"
    assert top["sources"] == ["qidian.com", "zongheng.com"]
    assert top["urls"] == ["u1", "u2"]
    assert top["blurb"] == "更长的简介"  # 取最长
    assert top["word_count"] == "2089021"  # 100万=1_000_000 < 2089021，取大
    # 孤立书独立成组
    titles = [g["title"] for g in groups]
    assert "斗破苍穹" in titles


def test_group_word_count_wan_unit_parsed():
    rows = [
        _row("书X", "a.com", "u1", word_count="767.59万字"),
        _row("书X", "b.com", "u2", word_count="100000"),  # 10万 < 767.59万
    ]
    g = group_books(rows)[0]
    assert g["word_count"] == "767.59万字"  # 取大


def test_group_order_by_sources_desc():
    rows = [
        _row("A", "a.com", "u1"),
        _row("A", "b.com", "u2"),
        _row("B", "a.com", "u3"),
    ]
    groups = group_books(rows)
    # A 双源在前，B 单源在后
    assert [g["title"] for g in groups] == ["A", "B"]


def test_group_empty():
    assert group_books([]) == []
