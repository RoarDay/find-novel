"""web.py 单测：渲染函数输出含预期内容 + html 转义。不启服务器。"""

from novel_crawler import web


def _row(**kw):
    return kw


def test_render_index_has_nav():
    out = web.render_index()
    assert "novel-crawler" in out
    assert "/booklists" in out and "/history" in out


def test_render_booklists_empty_and_filled():
    assert "暂无书单" in web.render_booklists([])
    out = web.render_booklists([_row(name="待读", created_at="2026-07-21T10:00:00")])
    assert "待读" in out
    assert "/booklist?name=" in out


def test_render_booklist_shows_books_and_escapes():
    books = [
        _row(title="书<script>A", url="http://x.com/1", source="x.com", author="甲"),
        _row(title="书B", url="http://x.com/2", source="y.com", author=""),
    ]
    out = web.render_booklist("待读", books)
    assert "书&lt;script&gt;A" in out  # 转义，防 XSS
    assert "<script>A" not in out
    assert "书B" in out


def test_render_history():
    row = _row(keyword="凡人修仙", result_count=5, searched_at="2026-07-21T10:00:00")
    out = web.render_history([row])
    assert "凡人修仙" in out and "5 条" in out


def test_render_recommend_empty_and_filled():
    url = "http://x.com/1"
    book = _row(title="书A", url=url, source="x.com", author="")
    empty = web.render_recommend(url, [], book)
    assert "无推荐" in empty
    recs = [_row(title="书B", source="y.com", author="", co=2)]
    out = web.render_recommend(url, recs, book)
    assert "书B" in out and "2 次共现" in out


def test_render_books_tag():
    out = web.render_books([_row(title="书A", url="u1", source="qidian.com", author="")])
    assert "qidian.com" in out and "/recommend?url=" in out
