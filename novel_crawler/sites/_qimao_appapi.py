"""七猫 App API：完整目录（签名）+ 全本下载（zip + AES）。

签名 2026-07-21 实测有效（research/sign.md）。
- **核心（签名 + chapter-list 完整目录）零新依赖**（stdlib hashlib）。
- 全本下载的 AES 懒加载 pycryptodome（缺失给清晰错误，不破坏核心/目录功能）。

下划线前缀：registry 不当 parser 加载；QimaoParser 委托本模块。
"""

import base64
import hashlib
import io
import json
import re
import zipfile

SIGN_KEY = "d3dGiJc651gSQ8w1"  # 公共常量（dart 源码硬编码）
AES_KEY = bytes.fromhex("32343263636238323330643730396531")  # 16 字节

API_CHAPTER_LIST = "https://api-ks.wtzw.com/api/v1/chapter/chapter-list"
API_DOWNLOAD = "https://api-bc.wtzw.com/api/v1/book/download"

# app-version 池（api_client.dart:15-19，2026 实测仍接受）
VERSION_LIST = [
    73720, 73700, 73620, 73600, 73500, 73420, 73400,
    73328, 73325, 73320, 73300, 73220, 73200, 73100,
    73000, 72900, 72820, 72800, 70720, 62010, 62112,
]

_ZIP_URL_RE = re.compile(r"https?://[^\s\"']+\.zip")


def qimao_sign(params: dict, key: str = SIGN_KEY) -> str:
    """按 key 字典序拼 `k=v`（紧挨，无 &，不 url-encode）+ 末尾 signKey → md5 hex。"""
    sign_str = "".join(f"{k}={params[k]}" for k in sorted(params)) + key
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def qimao_headers(version: int | None = None) -> dict:
    """App API 必填头；头部整体再签一次。version=None 随机抽。"""
    import random

    ver = version if version is not None else random.choice(VERSION_LIST)
    h = {
        "AUTHORIZATION": "",
        "app-version": str(ver),
        "application-id": "com.****.reader",  # 字面量就是 4 个星号
        "channel": "unknown",
        "net-env": "1",
        "platform": "android",
        "qm-params": "",
        "reg": "0",
    }
    h["sign"] = qimao_sign(h)
    return h


def _signed_query(params: dict) -> str:
    """计算 sign 并拼成 querystring（值原样 urlencode-free，sign 决定最后一项）。"""
    sign = qimao_sign(params)
    return "&".join(f"{k}={params[k]}" for k in sorted(params)) + f"&sign={sign}"


def get_full_catalog(book_id: str | int, fetch=None) -> list[tuple[str, str]]:
    """完整目录：chapter-list API → `data.chapter_lists` 按 chapter_sort 升序。

    fetch: text-fetcher(url, headers=...) -> str | None。默认模块内 requests。
    """
    params = {"chapter_ver": "0", "id": str(book_id)}
    url = f"{API_CHAPTER_LIST}?{_signed_query(params)}"
    html = (fetch or _default_fetch)(url, headers=qimao_headers())
    if not html:
        return []
    try:
        resp = json.loads(html)
    except ValueError:
        return []
    items = (resp.get("data") or {}).get("chapter_lists") or []
    items = sorted(items, key=lambda c: int(c.get("chapter_sort", 0) or 0))
    return [(c.get("title", ""), str(c.get("id", ""))) for c in items if c.get("id")]


def _decrypt_chapter(b64_body: str | bytes) -> str:
    """章节正文：base64 解码 → [IV(16), 密文] → AES-CBC → PKCS7 unpad → utf-8。"""
    from Crypto.Cipher import AES  # 懒加载：仅全本下载需要

    raw = base64.b64decode(b64_body)
    iv, payload = raw[:16], raw[16:]
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    dec = cipher.decrypt(payload)
    pad = dec[-1]  # PKCS7
    return dec[:-pad].decode("utf-8")


def _decrypt_zip(zip_bytes: bytes) -> dict[str, str]:
    """zip 内每个 `{chapter_id}.txt`（base64）→ AES 解密 → {chapter_id: text}。"""
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.endswith(".txt"):
                continue
            chapter_id = name[:-4].rsplit("/", 1)[-1]
            try:
                out[chapter_id] = _decrypt_chapter(zf.read(name))
            except Exception:  # noqa: BLE001
                continue  # 单章失败不拖垮整本
    return out


def _find_zip_url(text: str) -> str:
    """defensive：从 download API 响应里找 .zip 直链（字段名变体兼容）。"""
    m = _ZIP_URL_RE.search(text or "")
    return m.group(0) if m else ""


def download_full_content(
    book_id: str | int,
    fetch=None,
    bytes_fetcher=None,
) -> dict[str, str]:
    """全本下载：download API → zip 直链 → 解压 → 每章 AES 解密 → {chapter_id: text}。

    fetch/bytes_fetcher 可注入（测试）；默认模块内 requests。zip 必须 bytes，故独立
    bytes_fetcher（engine.fetch 只返回 text）。
    """
    params = {"id": str(book_id), "source": "1", "type": "2", "is_vip": "1"}
    url = f"{API_DOWNLOAD}?{_signed_query(params)}"
    resp_text = (fetch or _default_fetch)(url, headers=qimao_headers())
    zip_url = _find_zip_url(resp_text or "")
    if not zip_url:
        return {}
    zip_bytes = (bytes_fetcher or _default_fetch_bytes)(zip_url)
    if not zip_bytes:
        return {}
    return _decrypt_zip(zip_bytes)


# ── 模块内默认 HTTP（独立于 engine；__main__ 烟测 + CLI 全本下载用）─────────

def _default_fetch(url: str, headers: dict | None = None) -> str | None:
    import requests

    try:
        r = requests.get(url, headers=headers or {}, timeout=20)
        return r.text if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _default_fetch_bytes(url: str, headers: dict | None = None) -> bytes:
    import requests

    try:
        r = requests.get(url, headers=headers or {}, timeout=60)
        return r.content if r.status_code == 200 else b""
    except Exception:  # noqa: BLE001
        return b""


if __name__ == "__main__":
    # ponytail: 真连网烟测；断网/签名失效时跳过
    try:
        cat = get_full_catalog("1860026")
        assert len(cat) > 100, f"catalog too short: {len(cat)}"
        print(f"catalog OK: {len(cat)} chapters, ch1 = {cat[0]}")
    except Exception as e:  # noqa: BLE001
        print("SKIP catalog (网络/签名):", e)
