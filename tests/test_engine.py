import time
from unittest.mock import MagicMock

from novel_crawler.engine import DownloadEngine


def test_fetch_retries_then_succeeds(monkeypatch):
    """前 2 次 get 抛异常，第 3 次成功 → 返回 200 文本。"""
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    engine = DownloadEngine(delay=(0, 0))

    responses = iter([Exception("e1"), Exception("e2"), _resp("got it")])

    def fake_get(*a, **k):
        v = next(responses)
        if isinstance(v, Exception):
            raise v
        return v

    engine.session.get = fake_get
    assert engine.fetch("http://x", retries=3) == "got it"


def test_fetch_returns_none_after_all_retries_fail(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    engine = DownloadEngine(delay=(0, 0))
    engine.session.get = MagicMock(side_effect=Exception("always"))
    assert engine.fetch("http://x", retries=2) is None


def test_fetch_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    engine = DownloadEngine(delay=(0, 0))
    engine.session.get = MagicMock(return_value=_resp("fail", status=500))
    assert engine.fetch("http://x", retries=1) is None


def test_fetch_apparent_encoding_priority():
    """resp.encoding 应被赋为 apparent_encoding（gbk 优先于 latin-1）。"""
    engine = DownloadEngine(delay=(0, 0))
    r = _resp("内容", apparent="gbk", encoding="latin-1")
    engine.session.get = MagicMock(return_value=r)
    assert engine.fetch("http://x") == "内容"
    assert r.encoding == "gbk"


def test_save_writes_header_and_ordered_chapters(tmp_path):
    engine = DownloadEngine(delay=(0, 0))
    chapters = [("第一章", "u1"), ("第二章", "u2"), ("第三章", "u3")]
    results = {
        1: ("第一章", "c1"),
        2: ("第二章", "c2"),
        3: ("第三章", None),  # ponytail: 失败章节占位
    }
    path = engine.save(
        "书名", "作者", chapters, results,
        filename="out.txt", output_dir=str(tmp_path),
    )
    text = open(path, encoding="utf-8").read()
    assert text.startswith("书名\n作者：作者\n\n")
    assert "[本章内容获取失败]" in text
    # 顺序保留
    assert text.index("第一章") < text.index("第二章") < text.index("第三章")
    assert text.index("c1") < text.index("c2")


def test_download_all_results_indexed_in_order(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    engine = DownloadEngine(delay=(0, 0), max_workers=3)
    chapters = [("一", "u1"), ("二", "u2"), ("三", "u3")]

    def parse_fn(url):
        return f"content-{url}"

    results, failed = engine.download_all(chapters, parse_fn)
    assert failed == []
    assert [results[i][0] for i in (1, 2, 3)] == ["一", "二", "三"]
    assert results[1][1] == "content-u1"
    assert results[3][1] == "content-u3"


def test_download_all_tracks_failed_and_retries(monkeypatch):
    """首次 parse_fn 失败的章节会被记入 failed；重试成功后 results 更新。"""
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    engine = DownloadEngine(delay=(0, 0), max_workers=2)
    chapters = [("一", "u1"), ("二", "u2")]

    calls = {"u2": 0}

    def parse_fn(url):
        if url == "u2":
            calls["u2"] += 1
            return None  # 始终失败，触发重试仍失败
        return "ok"

    results, failed = engine.download_all(chapters, parse_fn)
    assert results[1] == ("一", "ok")
    assert results[2][0] == "二"
    assert any(idx == 2 for idx, _, _ in failed)


def _resp(text="ok", status=200, encoding="utf-8", apparent=None):
    r = MagicMock()
    r.text = text
    r.status_code = status
    r.encoding = encoding
    r.apparent_encoding = apparent or encoding
    return r
