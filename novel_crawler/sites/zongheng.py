import json
import re
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from novel_crawler.base import BaseParser, SearchResult


class ZonghengParser(BaseParser):
    """纵横中文网 (zongheng.com) 解析器。搜索走 JSON API，自带简介。"""

    @property
    def domain(self) -> str:
        return "zongheng.com"

    def search(self, keyword: str, fetch) -> list:
        """GET search.zongheng.com/search/book JSON API。简介随结果返回，无需补抓详情页。"""
        url = f"https://search.zongheng.com/search/book?keyword={quote(keyword)}&pageNo=1"
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        try:
            data = json.loads(html)
            items = data.get("data", {}).get("datas", {}).get("list", []) or []
        except (ValueError, AttributeError):
            return []
        results = []
        for it in items:
            book_id = it.get("bookId")
            if not book_id:
                continue
            name = re.sub(r"<[^>]+>", "", it.get("name", ""))
            desc = re.sub(r"<[^>]+>", "", it.get("description", ""))
            results.append(SearchResult(
                title=name,
                url=f"https://book.zongheng.com/showchapter/{book_id}.html",
                source=self.domain,
                author=it.get("authorName", ""),
                blurb=desc,
            ))
        return results

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        chapters = []
        for a in soup.select(".chapter-list a"):
            href = a.get("href", "")
            if href:
                chapters.append((a.get_text(strip=True), urljoin(base_url, href)))
        return chapters

    def parse_content(self, soup: BeautifulSoup) -> str:
        content = soup.select_one(".content")
        if not content:
            return ""
        text = content.get_text(separator="\n", strip=True)
        # ponytail: 章节页 title 拼了 `_书名小说最新章节,在线阅读,纵横小说` 后缀，body 偶发渗入，按需剥掉
        text = re.sub(r"_.*?纵横小说", "", text)
        return text.strip()
