from abc import ABC, abstractmethod
from dataclasses import dataclass
from bs4 import BeautifulSoup
from urllib.parse import urljoin


@dataclass
class SearchResult:
    title: str       # 书名
    url: str         # 目录页绝对 URL（直接喂给下载流程）
    source: str      # 来源站域名，用于聚合显示
    author: str = "" # 可选，作者
    blurb: str = ""  # 简介，语义匹配主依据


class BaseParser(ABC):
    """站点解析器基类。新增站点只需继承此类，实现3个方法。"""

    headers: dict = {}  # 子类可覆盖，如起点 iPhone UA

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
        默认实现检测常见的 next_url 和 rel=next 模式。
        特殊站点可覆盖此方法。
        """
        import re
        next_link = soup.select_one('a#next_url') or soup.select_one("a[rel='next']")
        if not next_link:
            return None
        next_href = next_link.get('href', '')
        next_href = urljoin(current_url, next_href)
        if re.search(r'_\d+\.html$', next_href):
            return next_href
        return None

    def search(self, keyword: str, fetch) -> list:
        """
        按关键词搜索本站。
        fetch: callable(url, method="GET", data=None) -> html str | None
        返回: [SearchResult, ...]。默认返回空（站点未实现搜索）。
        """
        return []

    def get_blurb(self, url: str, fetch) -> str:
        """详情页简介。默认空（搜索已带简介的站不需实现）。"""
        return ""

    def get_rank(self, rank_type: str, fetch) -> list:
        """排行榜。默认空。"""
        return []

    def get_category(self, category: str, fetch) -> list:
        """分类/标签筛选。默认空。"""
        return []

    def get_similar(self, url: str, fetch) -> list:
        """相似推荐。默认空。"""
        return []
