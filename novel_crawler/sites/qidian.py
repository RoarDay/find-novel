import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from novel_crawler.base import BaseParser, SearchResult


def _extract_page_context(html: str) -> dict:
    """从 m.qidian.com SSR HTML 抽出 vite-plugin-ssr 内联 JSON 的 pageData。"""
    m = re.search(
        r'<script id="vite-plugin-ssr_pageContext" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
        return data.get("pageContext", {}).get("pageProps", {}).get("pageData", {})
    except (ValueError, KeyError):
        return {}


class QidianParser(BaseParser):
    """起点中文网 (qidian.com) 解析器。走移动站 (m.)，iPhone UA 破 probe.js。"""

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
    }

    @property
    def domain(self) -> str:
        return "qidian.com"

    def search(self, keyword: str, fetch) -> list:
        """GET /so/<kw>.html，inline JSON records[] 直接带 desc。"""
        html = fetch(f"https://m.qidian.com/so/{quote(keyword)}.html", headers=self.headers)
        if not html:
            return []
        records = _extract_page_context(html).get("bookInfo", {}).get("records", []) or []
        results = []
        for r in records:
            bid = r.get("bid")
            if not bid:
                continue
            results.append(SearchResult(
                title=r.get("bName", ""),
                url=f"https://m.qidian.com/book/{bid}/catalog/",
                source=self.domain,
                author=r.get("bAuth", ""),
                blurb=r.get("desc", ""),
                word_count=r.get("cnt", ""),
            ))
        return results

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        """catalog 页 inline JSON vs[].cs[]；章节 URL 用 bid+id 拼（cU 字段为空）。"""
        m_bid = re.search(r"/book/(\d+)", base_url)
        if not m_bid:
            return []
        bid = m_bid.group(1)

        # soup 拿不到内联 JSON，回源 html 找 script
        html = str(soup)
        page_data = _extract_page_context(html)
        chapters = []
        for vol in page_data.get("vs", []) or []:
            for ch in vol.get("cs", []) or []:
                cid = ch.get("id")
                if not cid:
                    continue
                chapters.append((ch.get("cN", ""), f"https://m.qidian.com/chapter/{bid}/{cid}/"))
        return chapters

    def parse_content(self, soup: BeautifulSoup) -> str:
        """<main class='content ...'> 取正文；含 lock-mask 即 VIP 锁，返回空。"""
        main = soup.find("main", class_="content")
        if not main:
            return ""
        if "lock-mask" in (main.get("class") or []):
            return ""
        return main.get_text(separator="\n", strip=True)
