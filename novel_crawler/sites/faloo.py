"""飞卢小说 (faloo.com) 解析器。

飞卢是强分类/排行驱动的男频同人站，反爬最轻（裸 requests + 桌面 UA），
全站 GBK 编码（engine 已用 apparent_encoding，无需手动）。
search 首期不做（社区教程零覆盖；分类/排行更划算），实现 get_category/get_rank/get_blurb。
"""

import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from novel_crawler.base import BaseParser, SearchResult

# 详情页/目录页同页：https://b.faloo.com/{bookId}.html
# 章节正文页：https://b.faloo.com/{bookId}_{N}.html
_BOOKID_RE = re.compile(r"/(\d+)\.html$")
_CHAPTER_HREF_RE = re.compile(r"/\d+_\d+\.html$")


class FalooParser(BaseParser):
    """飞卢小说解析器。详情页即目录页。"""

    @property
    def domain(self) -> str:
        return "faloo.com"

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        # ponytail: #mulu 容器实测含全部章节链接（2222/476534），不需走 c_con_li_detail_p（research 给的 selector 实测未命中）
        mulu = soup.select_one("#mulu")
        if not mulu:
            return []
        seen = set()
        chapters = []
        for a in mulu.find_all("a", href=_CHAPTER_HREF_RE):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or href in seen:
                continue
            seen.add(href)
            chapters.append((title, urljoin(base_url, href)))
        return chapters

    def parse_content(self, soup: BeautifulSoup) -> str:
        div = soup.select_one("div.noveContent")
        if not div:
            return ""
        for tag in div(["script", "style"]):
            tag.decompose()
        # ponytail: noveContent 内 <p> 是段落，join 成 \n 比 .text 更干净
        ps = div.find_all("p")
        if ps:
            text = "\n".join(p.get_text(strip=True) for p in ps if p.get_text(strip=True))
        else:
            text = div.get_text("\n", strip=True)
        return text

    def get_blurb(self, url: str, fetch) -> str:
        """详情页简介。实测 selector: div.T-L-T-Content（c_con_rl_intro 等未命中）。"""
        html = fetch(url, headers=self.headers)
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        div = soup.select_one("div.T-L-T-Content")
        if not div:
            return ""
        for tag in div(["script", "style", "a"]):
            tag.decompose()
        text = div.get_text(" ", strip=True)
        # 去掉签约声明前缀与免责声明后缀
        text = re.sub(r"^【飞卢小说网[^】]*】\s*", "", text)
        text = re.sub(r"\s*飞卢小说网提醒您：.*$", "", text)
        return text.strip()

    def get_category(self, category: str, fetch) -> list:
        """分类筛选。category 形如 '{catId}_{subId}'（如 '44_69'=同人/动漫同人）。"""
        m = re.match(r"^(\d+)_(\d+)$", category.strip())
        if not m:
            return []
        url = f"https://b.faloo.com/y_{m.group(1)}_{m.group(2)}_1.html"
        return self._extract_book_list(url, fetch)

    def get_rank(self, rank_type: str, fetch) -> list:
        """排行榜。rank_type='sell' → 销售天榜，否则综合榜。"""
        if rank_type == "sell":
            url = "https://b.faloo.com/top/sellrank.aspx"
        else:
            url = "https://b.faloo.com/top/top.aspx"
        return self._extract_book_list(url, fetch)

    def _extract_book_list(self, url: str, fetch) -> list:
        """从分类/排行页提取去重的书候选。blurb 留空（详情页按需补）。
        分类页 .TwoBox02_02 卡片含「字数：N万」，填 word_count；
        排行页无卡片容器（裸 <a>），word_count 留空。"""
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        # ponytail: 字数只在分类页 .TwoBox02_02 卡片里；排行页是裸 <a>，无字数
        word_by_bid = {}
        for card in soup.select(".TwoBox02_02"):
            bid = None
            for a in card.find_all("a", href=_BOOKID_RE):
                bid = _BOOKID_RE.search(a["href"]).group(1)
                break
            if not bid:
                continue
            for span in card.select(".TwoBox02_05"):
                m_wc = re.search(r"字数[：:]\s*(\S+)", span.get_text(" ", strip=True))
                if m_wc:
                    word_by_bid[bid] = m_wc.group(1)
                    break
        results = []
        seen_bid = set()
        for a in soup.find_all("a", href=_BOOKID_RE):
            bid = _BOOKID_RE.search(a["href"]).group(1)
            title = a.get_text(strip=True)
            if not title or bid in seen_bid:
                continue
            seen_bid.add(bid)
            results.append(SearchResult(
                title=title,
                url=f"https://b.faloo.com/{bid}.html",
                source=self.domain,
                word_count=word_by_bid.get(bid, ""),
            ))
        return results
