import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from novel_crawler.base import BaseParser, SearchResult


class Yanqing92Parser(BaseParser):
    """就爱言情小说网 (92yanqing.com) 解析器"""

    @property
    def domain(self) -> str:
        return "92yanqing.com"

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        catalog_div = soup.select_one(".all")
        if not catalog_div:
            return []

        chapters = []
        for a in catalog_div.select("ul li a[rel='chapter']"):
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
        text = re.sub(r"就爱言情小说网.*", "", text)
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

    def search(self, keyword: str, fetch) -> list:
        """GET /s/?searchkey= 搜索。"""
        url = f"https://www.92yanqing.com/s/?searchkey={quote(keyword)}"
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        results = []
        for dl in soup.select(".ranklist dl"):
            a = dl.select_one("dt a")
            if not a or not a.get("href"):
                continue
            dds = dl.select("dd")
            author_a = dl.select_one('dd a[href^="/author/"]')
            # ponytail: dd[1] 的 span 序列是 [状态, 字数]，取末个即字数（如 "11万字"）
            meta_spans = dds[1].find_all("span") if len(dds) > 1 else []
            word_count = meta_spans[-1].get_text(strip=True) if meta_spans else ""
            results.append(SearchResult(
                title=a.get_text(strip=True),
                url=urljoin("https://www.92yanqing.com/", a["href"]),
                source=self.domain,
                author=author_a.get_text(strip=True) if author_a else "",
                blurb=dds[0].get_text(strip=True) if dds else "",
                word_count=word_count,
            ))
        return results
