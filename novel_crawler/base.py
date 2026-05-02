from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from urllib.parse import urljoin


class BaseParser(ABC):
    """站点解析器基类。新增站点只需继承此类，实现3个方法。"""

    @property
    @abstractmethod
    def domain(self) -> str:
        """匹配域名，如 '92yanqing.com'。支持子域名匹配。"""
        pass

    def normalize_url(self, href: str, base_url: str) -> str:
        return urljoin(base_url, href)

    @abstractmethod
    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        """
        解析目录页。
        返回: [(章节标题, 章节绝对URL), ...]
        """
        pass

    @abstractmethod
    def parse_content(self, soup: BeautifulSoup) -> str:
        """
        解析单页正文。
        返回: 清洗后的纯文本。
        """
        pass

    def has_next_page(self, soup: BeautifulSoup, current_url: str) -> str | None:
        """
        检查是否有下一页（分页）。
        返回: 下一页绝对URL，或 None。
        默认实现检测常见的 _2.html、_3.html 模式。
        特殊站点可覆盖此方法。
        """
        import re
        next_link = soup.select_one('a#next_url')
        if not next_link:
            return None
        next_href = next_link.get('href', '')
        next_href = urljoin(current_url, next_href)
        if re.search(r'_\d+\.html$', next_href):
            return next_href
        return None
