"""番茄小说 (fanqienovel.com) 解析器。

裸 requests 可拿：书页详情（内联 __INITIAL_STATE__）/ 章节正文（PUA 字体解密）/
推荐榜 + 最近更新（全字段 JSON）。**搜索不实现**（web XHR /api/author/search 被
ByteDance secsdk 锁成 0 字节 body，APP API 签名墙；超 BaseParser 范围）。
推荐池缺口用分类/排行（自带 abstract）补足。

线上已验证 2026-07-21：blurb / recommend(9本) / 目录 / 正文 PUA 解密（2410字）全通。
逆向依据见 docs/research/fanqie-probe.md。
"""

import json
import re

from bs4 import BeautifulSoup

from novel_crawler.base import BaseParser, SearchResult
from novel_crawler.log import get_logger

from ._fanqie_font_map import FONT_MAP

log = get_logger("fanqie")

DOMAIN = "fanqienovel.com"
BASE = "https://fanqienovel.com"
# 桌面 Chrome UA 即过反爬（probe.md §7）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

_PUA_RANGE = range(0xE000, 0xF900)  # U+E000..U+F8FF 私用区
# VIP 锁章仅给 ~2 段预览；免费章 60+ 段。<p> 数是可靠锁信号
# （「下载番茄/阅读全文/本章字数」等标记全站页脚都有，不能作锁判据）
_LOCK_PARAGRAPH_THRESHOLD = 2


def _decode_pua(text: str) -> str:
    """PUA 码点 → 真实字符（FONT_MAP 362 条）。未命中保留原字符。
    解码后 PUA 残留 >5% 告警字表过期。"""
    decoded = "".join(FONT_MAP.get(str(ord(c)), c) for c in text)
    pua_remain = sum(1 for c in decoded if ord(c) in _PUA_RANGE)
    if decoded and pua_remain > len(decoded) * 0.05:
        log.warning("fanqie font_map 可能过期：%d/%d PUA 未解", pua_remain, len(decoded))
    return decoded


def _extract_state(html: str) -> dict:
    """从 `__INITIAL_STATE__={...}` 抽整个 state 对象。
    brace-match（字符串感知，限 `</script>` 内）+ `undefined→null` 归一化。失败返回 {}。"""
    idx = html.find("__INITIAL_STATE__")
    if idx < 0:
        return {}
    start = html.find("{", idx)
    if start < 0:
        return {}
    end_bound = html.find("</script>", start)
    scan_end = len(html) if end_bound < 0 else end_bound
    depth = 0
    in_str = False
    quote = ""
    i = start
    end = -1
    while i < scan_end:
        ch = html[i]
        if in_str:
            if ch == "\\":
                i += 2  # 跳过转义下一字符，避免 \" 误判关串
                continue
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    if end < 0:
        return {}
    try:
        return json.loads(re.sub(r"\bundefined\b", "null", html[start:end]))
    except ValueError:
        return {}


def _page_from_soup(soup: BeautifulSoup) -> dict:
    """优先取 script 原文（避免整页 str(soup) 重序列化），兜底 str(soup)。"""
    for s in soup.find_all("script"):
        txt = s.get_text() or ""
        if "__INITIAL_STATE__" in txt:
            return _extract_state(txt).get("page", {}) or {}
    return _extract_state(str(soup)).get("page", {}) or {}


def _flatten_chapters(page: dict) -> list[tuple[str, str]]:
    """page.chapterListWithVolume（分卷二维）展平 → [(title, /reader/{itemId})]。"""
    out: list[tuple[str, str]] = []
    for vol in page.get("chapterListWithVolume") or []:
        for ch in vol or []:
            item_id = ch.get("itemId")
            if item_id:
                out.append((ch.get("title", ""), f"{BASE}/reader/{item_id}"))
    return out


def _book_list(resp: dict) -> list[dict]:
    """defensive：recommend→data.list、category→data.book_list、裸 data:[...] 都兼容。"""
    data = (resp or {}).get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("book_list") or data.get("list") or []
    return []


def _book_to_result(b: dict) -> SearchResult:
    bid = b.get("bookId") or b.get("id")
    wc = b.get("wordNumber")
    return SearchResult(
        title=b.get("bookName") or b.get("title") or "",
        url=f"{BASE}/page/{bid}" if bid else "",
        source=DOMAIN,
        author=b.get("author", ""),
        blurb=b.get("abstract") or b.get("description") or "",
        word_count=str(wc) if wc not in (None, "") else "",
    )


class FanqieParser(BaseParser):
    """番茄小说解析器。目录从书页内联 JSON 抽；正文 PUA 解密。"""

    headers = HEADERS
    sample_url = f"{BASE}/page/7143038691944959011"  # 十日终焉（probe.md 样本）

    @property
    def domain(self) -> str:
        return DOMAIN

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        return _flatten_chapters(_page_from_soup(soup))

    def parse_content(self, soup: BeautifulSoup) -> str:
        """`.muye-reader-content` 内 <p> → PUA 解密；VIP 锁章（≤2 段预览）返回 ''。"""
        container = soup.select_one(".muye-reader-content") or soup
        ps = container.find_all("p")
        if len(ps) <= _LOCK_PARAGRAPH_THRESHOLD:
            return ""  # 锁章仅 2 段预览
        raw = "\n".join(p.get_text(strip=True) for p in ps if p.get_text(strip=True))
        return _decode_pua(raw)

    def get_blurb(self, url: str, fetch) -> str:
        """书页详情 → state.page.abstract。"""
        html = fetch(url, headers=self.headers)
        if not html:
            return ""
        return _extract_state(html).get("page", {}).get("abstract", "") or ""

    def get_category(self, category: str, fetch) -> list:
        """category='male'/'female'（或 '0'/'1'）→ /api/rank/recommend/list。"""
        gender = 1 if category.strip().lower() in ("female", "1", "女") else 0
        url = f"{BASE}/api/rank/recommend/list?aid=1967&gender={gender}"
        return self._fetch_book_list(url, fetch)

    def get_rank(self, rank_type: str, fetch) -> list:
        """rank_type='recommend'(默认) / 'recent'。"""
        rank_type = (rank_type or "recommend").strip().lower()
        if rank_type in ("recent", "update", "最新"):
            url = f"{BASE}/api/rank/recent/update/list?aid=1967&gender=0&page_count=0"
        else:
            url = f"{BASE}/api/rank/recommend/list?aid=1967&gender=0"
        return self._fetch_book_list(url, fetch)

    def _fetch_book_list(self, url: str, fetch) -> list:
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        try:
            resp = json.loads(html)
        except ValueError:
            return []
        return [_book_to_result(b) for b in _book_list(resp) if b.get("bookId") or b.get("id")]

    def search(self, keyword: str, fetch) -> list:
        """❌ 不实现：web XHR 被 secsdk 锁空 body，APP API 签名墙（见 probe.md §1）。"""
        return []


if __name__ == "__main__":
    # ponytail: 真连网烟测；断网/改版时跳过
    from novel_crawler.engine import DownloadEngine

    p = FanqieParser()
    f = DownloadEngine().fetch
    page = "https://fanqienovel.com/page/7143038691944959011"  # 十日终焉
    try:
        blurb = p.get_blurb(page, f)
        print("blurb:", (blurb or "")[:60])
        assert blurb, "blurb empty"
        cat = p.get_category("male", f)
        print("recommend(male):", len(cat))
        assert cat, "recommend empty"
        titles = p.get_chapter_titles(page, f, limit=5)
        print("chapter titles:", titles)
        assert titles, "titles empty"
        print("OK")
    except Exception as e:  # noqa: BLE001
        print("SKIP (网络/改版):", e)
