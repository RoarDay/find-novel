"""_qimao_appapi 单测：签名 / headers / chapter-list 解析 / AES 往返 / zip 解密。
不触网（线上端到端见 _qimao_appapi __main__ 烟测，单 session 未验证）。"""

import base64
import io
import json
import zipfile

import pytest

from novel_crawler.sites import _qimao_appapi as api

SIGN_REF = "708093a4ab465a2108c1cfaf1635e383"  # {id:1860026, chapter_ver:0}


# ── 签名 ──────────────────────────────────────────────────────────────

def test_sign_matches_reference():
    assert api.qimao_sign({"id": "1860026", "chapter_ver": "0"}) == SIGN_REF


def test_sign_order_independent():
    a = api.qimao_sign({"id": "1860026", "chapter_ver": "0"})
    b = api.qimao_sign({"chapter_ver": "0", "id": "1860026"})
    assert a == b


def test_sign_kv_concat_no_urlencode():
    """值含空格/& 也不 url-encode：签名用原始字符串紧挨拼接。"""
    import hashlib

    params = {"a": "x y", "b": "1&2"}
    expected = hashlib.md5(("a=x yb=1&2" + api.SIGN_KEY).encode("utf-8")).hexdigest()
    assert api.qimao_sign(params) == expected


def test_signed_query_appends_sign_last():
    q = api._signed_query({"chapter_ver": "0", "id": "1860026"})
    assert q.endswith("&sign=" + SIGN_REF)
    assert "id=1860026" in q and "chapter_ver=0" in q


# ── headers ───────────────────────────────────────────────────────────

def test_headers_contain_required_and_sign():
    h = api.qimao_headers(version=73720)
    assert h["app-version"] == "73720"
    assert h["application-id"] == "com.****.reader"
    assert h["platform"] == "android"
    assert "sign" in h and h["sign"]


# ── chapter-list 解析 ─────────────────────────────────────────────────

def test_get_full_catalog_parses_and_sorts():
    resp = {"data": {"chapter_lists": [
        {"id": "21", "title": "第3章", "chapter_sort": 3},
        {"id": "11", "title": "第1章", "chapter_sort": 1},
        {"id": "12", "title": "第2章", "chapter_sort": 2},
    ]}}
    captured = {}

    def fake_fetch(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return json.dumps(resp)

    cat = api.get_full_catalog("1860026", fake_fetch)
    assert [t for t, _ in cat] == ["第1章", "第2章", "第3章"]  # 按 chapter_sort 升序
    assert [cid for _, cid in cat] == ["11", "12", "21"]
    assert "chapter-list" in captured["url"]
    assert "sign=" in captured["url"]


def test_get_full_catalog_empty_on_bad_response():
    assert api.get_full_catalog("x", lambda url, headers=None: None) == []
    assert api.get_full_catalog("x", lambda url, headers=None: "not json") == []
    assert api.get_full_catalog("x", lambda url, headers=None: "{}") == []


# ── AES 解密（pycryptodome）────────────────────────────────────────────

def _make_chapter_b64(plaintext: str, iv: bytes = b"0123456789abcdef") -> str:
    """用 AES_KEY 加密 plaintext → base64(IV + 密文)，模拟七猫章节文件。"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    cipher = AES.new(api.AES_KEY, AES.MODE_CBC, iv)
    enc = cipher.encrypt(pad(plaintext.encode("utf-8"), 16))
    return base64.b64encode(iv + enc).decode()


def test_decrypt_chapter_roundtrip():
    try:
        from Crypto.Cipher import AES  # noqa: F401
    except ImportError:
        pytest.skip("pycryptodome 未安装")
    plain = "卫渊看着远方的山，心中波澜不惊。第一章节测试内容。"
    assert api._decrypt_chapter(_make_chapter_b64(plain)) == plain


def test_decrypt_zip_roundtrip():
    try:
        from Crypto.Cipher import AES  # noqa: F401
    except ImportError:
        pytest.skip("pycryptodome 未安装")
    chapters = {"17231076120001": "第一章内容", "17231076120002": "第二章内容"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for cid, txt in chapters.items():
            zf.writestr(f"book_download/01/{cid}.txt", _make_chapter_b64(txt))
    out = api._decrypt_zip(buf.getvalue())
    assert out == chapters


def test_find_zip_url_defensive():
    assert api._find_zip_url('{"data":{"url":"https://cdn.x.com/a.zip"}}') == \
        "https://cdn.x.com/a.zip"
    assert api._find_zip_url("no zip here") == ""
