"""cache.py 单测：用 tmp_path 隔离 DB_PATH。测 key 稳定 + get/set 往返 + TTL 过期。"""

import time
from unittest.mock import MagicMock

from novel_crawler import cache, config
from novel_crawler.engine import DownloadEngine


def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "c.db"))


def _resp(text="b"):
    r = MagicMock()
    r.text = text
    r.status_code = 200
    r.encoding = "utf-8"
    r.apparent_encoding = "utf-8"
    return r


def test_make_key_stable_and_sensitive(monkeypatch, tmp_path):
    _use_tmp_db(tmp_path, monkeypatch)
    k1 = cache.make_key("GET", "http://x", None, None)
    k2 = cache.make_key("get", "http://x", None, None)  # 方法大小写不敏感
    k3 = cache.make_key("GET", "http://y", None, None)
    k4 = cache.make_key("GET", "http://x", {"a": 1}, None)
    assert k1 == k2
    assert k1 != k3
    assert k1 != k4


def test_get_set_roundtrip(monkeypatch, tmp_path):
    _use_tmp_db(tmp_path, monkeypatch)
    k = cache.make_key("GET", "http://x", None, None)
    assert cache.get(k) is None
    cache.set(k, "body")
    assert cache.get(k) == "body"
    cache.set(k, "body2")  # upsert
    assert cache.get(k) == "body2"


def test_set_empty_is_noop(monkeypatch, tmp_path):
    _use_tmp_db(tmp_path, monkeypatch)
    k = cache.make_key("GET", "http://x", None, None)
    cache.set(k, "")
    assert cache.get(k) is None


def test_get_expired_returns_none(monkeypatch, tmp_path):
    _use_tmp_db(tmp_path, monkeypatch)
    k = cache.make_key("GET", "http://x", None, None)
    cache.set(k, "body")
    assert cache.get(k, ttl=0) is None  # TTL=0 立即过期


def test_engine_cached_fetch_hits_cache_second_call(monkeypatch, tmp_path):
    """cache=True：第二次同请求不触网，直接返回缓存 body。"""
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    engine = DownloadEngine(delay=(0, 0))
    calls = {"n": 0}

    def fake_get(url, headers=None, timeout=15):
        calls["n"] += 1
        return _resp("live-body")

    engine.session.get = fake_get
    assert engine.fetch("http://x", cache=True, retries=1) == "live-body"
    assert calls["n"] == 1
    # 第二次命中缓存，不应再触网
    assert engine.fetch("http://x", cache=True, retries=1) == "live-body"
    assert calls["n"] == 1


def test_engine_cached_fetch_wrapper(monkeypatch, tmp_path):
    """engine.cached_fetch 等价于 fetch(cache=True)。"""
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    engine = DownloadEngine(delay=(0, 0))
    engine.session.get = lambda *a, **k: _resp("b")
    assert engine.cached_fetch("http://y", retries=1) == "b"
