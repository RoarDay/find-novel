import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from novel_crawler.base import BaseParser


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
