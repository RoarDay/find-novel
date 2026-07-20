import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from novel_crawler.base import BaseParser, SearchResult


class MinYuanParser(BaseParser):
    """小原文学网 (min-yuan.com) 解析器"""

    @property
    def domain(self) -> str:
        return "min-yuan.com"

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        newlist = soup.select_one("#newlist")
        if not newlist:
            return []

        chapters = []
        for a in newlist.select("dd a[rel='chapter']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if href:
                chapters.append((title, urljoin(base_url, href)))
        return chapters

    def parse_content(self, soup: BeautifulSoup) -> str:
        content_div = soup.select_one("#booktxt")
        if not content_div:
            return ""

        for tag in content_div(["script", "style", "ins", "iframe"]):
            tag.decompose()

        text = content_div.get_text(separator="\n", strip=True)
        text = re.sub(r"请记住本书首发域名：.*", "", text)
        text = re.sub(r"小原文学网.*", "", text)
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

    def has_next_page(self, soup: BeautifulSoup, current_url: str) -> str | None:
        next_link = soup.select_one("a[rel='next']")
        if not next_link:
            return None
        next_href = next_link.get("href", "")
        next_href = urljoin(current_url, next_href)
        if re.search(r"_\d+\.html$", next_href):
            return next_href
        return None

    def search(self, keyword: str, fetch) -> list:
        """POST /search/ 搜索。"""
        url = "https://www.min-yuan.com/search/"
        html = fetch(url, method="POST", data={"searchkey": keyword})
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        results = []
        for item in soup.select("div.item"):
            a = item.select_one("dl dt a")
            if not a or not a.get("href"):
                continue
            # ponytail: 搜索页 btm 区是固定标签非作者，无可靠作者字段，留空
            results.append(SearchResult(
                title=a.get_text(strip=True),
                url=urljoin("https://www.min-yuan.com/", a["href"]),
                source=self.domain,
            ))
        return results
