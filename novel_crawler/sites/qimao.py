import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from novel_crawler.base import BaseParser, SearchResult


class QimaoParser(BaseParser):
    """七猫小说 (qimao.com) 解析器。

    Web /search 是 SPA（裸 requests 拿不到），故不实现 search；
    主入口是分类筛选 / 排行 / 详情页（简介 + 推荐书 + 最新章 link）。
    """

    BASE = "https://www.qimao.com"

    @property
    def domain(self) -> str:
        return "qimao.com"

    # ----- 简介详情页 -----

    def get_blurb(self, url: str, fetch) -> str:
        """详情页 NUXT `bookIntroData.intro` 优先，CSS `.book-introduction` 兜底。"""
        html = fetch(url, headers=self.headers)
        if not html:
            return ""
        m = re.search(r'bookIntroData:\{intro:"((?:[^"\\]|\\.)*)"', html)
        if m:
            try:
                return json.loads('"' + m.group(1) + '"').strip()
            except Exception:
                pass
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(".book-introduction")
        return node.get_text(separator="\n", strip=True) if node else ""

    # ----- 分类筛选（推荐候选池主入口） -----

    def get_category(self, category: str, fetch) -> list:
        """category 形如 "{channel}-{cat1}-{cat2}"（"0-56-58" / "0-a-a"），
        或完整的 9 段 URL 段。映射到 /shuku/{7 段}-click-1/。"""
        seg = self._build_category_seg(category)
        if not seg:
            return []
        url = f"{self.BASE}/shuku/{seg}/"
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select(".text-content"):
            a = card.select_one(".s-tit a")
            if not a or not a.get("href"):
                continue
            desc = card.select_one(".s-desc")
            author_a = card.select_one("a.s-author") or card.select_one('a[href*="/zuozhe/"]')
            word_em = card.select_one(".s-words-num")
            results.append(SearchResult(
                title=a.get_text(strip=True),
                url=urljoin(self.BASE + "/", a["href"]),
                source=self.domain,
                author=author_a.get_text(strip=True) if author_a else "",
                blurb=desc.get_text(" ", strip=True) if desc else "",
                word_count=word_em.get_text(strip=True) if word_em else "",
            ))
        return results

    @staticmethod
    def _build_category_seg(category: str) -> str:
        """把 '0-56-58' / '0-a-a' / 完整段统一成 7 段 + '-click-1'。"""
        parts = category.split("-")
        if len(parts) < 2:
            print(f"[qimao] 无法识别分类 {category!r}，需 'channel-cat1-cat2' 格式")
            return ""
        # ponytail: 取前 7 段（channel + cat1/cat2 + 4 个属性位），不足补 'a'
        parts = parts[:7]
        while len(parts) < 7:
            parts.append("a")
        return "-".join(parts) + "-click-1"

    # ----- 排行榜 -----

    def get_rank(self, rank_type: str, fetch) -> list:
        """rank_type 形如 '{boy|girl}/{hot|new|over|collect|update}/{date|month}'。
        也接受用 '-' 分隔。空串默认 boy/hot/date。"""
        rank_type = (rank_type or "boy/hot/date").strip()
        parts = re.split(r"[-/]", rank_type)
        if len(parts) != 3:
            print(
                f"[qimao] 无法识别 rank_type {rank_type!r}，"
                "需 'gender-type-when'（如 boy-hot-date）"
            )
            return []
        gender, rtype, when = parts
        url = f"{self.BASE}/paihang/{gender}/{rtype}/{when}/"
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select(".txt"):
            a = card.select_one(".s-book-title")
            if not a or not a.get("href"):
                continue
            intro = card.select_one(".s-book-intro")
            author_a = card.select_one('a[href*="/zuozhe/"]')
            results.append(SearchResult(
                title=a.get_text(strip=True),
                url=urljoin(self.BASE + "/", a["href"]),
                source=self.domain,
                author=author_a.get_text(strip=True) if author_a else "",
                blurb=intro.get_text(" ", strip=True) if intro else "",
            ))
        return results

    # ----- 相似推荐（详情页 recommendBook） -----

    def get_similar(self, url: str, fetch) -> list:
        html = fetch(url, headers=self.headers)
        if not html:
            return []
        m = re.search(r'recommendBook\s*:\s*\[(.+?)\]', html, re.S)
        if not m:
            return []
        results = []
        for item in re.findall(r"\{([^{}]+)\}", m.group(1)):
            title = re.search(r'title:"((?:[^"\\]|\\.)*)"', item)
            if not title:
                continue
            author = re.search(r'author:"((?:[^"\\]|\\.)*)"', item)
            read_url = re.search(r'book_read_url:"((?:[^"\\]|\\.)*)"', item)
            try:
                title_s = json.loads('"' + title.group(1) + '"')
                author_s = json.loads('"' + author.group(1) + '"') if author else ""
                url_s = json.loads('"' + read_url.group(1) + '"') if read_url else ""
            except Exception:
                continue
            if not url_s:
                continue
            results.append(SearchResult(
                title=title_s,
                url=url_s,
                source=self.domain,
                author=author_s,
                # ponytail: recommendBook.short_comment 是 NUXT 变量引用，
            # 无法裸解析；需简介另发详情页请求
            blurb="",
            ))
        return results

    # ----- 目录 + 正文（下载流程用） -----

    def parse_catalog(self, soup: BeautifulSoup, base_url: str) -> list:
        """详情页只露最新一章 `/shuku/{book}-{chapter}/`；
        完整目录需走 App API（需签名，本场景不实现）。"""
        chapters = []
        for a in soup.select('a[href*="/shuku/"]'):
            href = a.get("href", "")
            # ponytail: 锚定整条 href（否则 /login?redirect=/shuku/{book}-{ch}/ 会误匹配）
            if re.match(r"^(?:https?://[^/]+)?/shuku/\d+-\d+/?$", href) and a.get_text(strip=True):
                chapters.append((a.get_text(strip=True), urljoin(base_url, href)))
                break  # ponytail: 详情页只露最新章；取第 1 个即足够触发下载入口
        return chapters

    def parse_content(self, soup: BeautifulSoup) -> str:
        """章节页 `.reader-layout-theme` 内 `<p>` 标签；兜底全页 `<p>`（>=20 字）。"""
        root = soup.select_one(".reader-layout-theme") or soup
        lines = [p.get_text(strip=True) for p in root.select("p")]
        text = "\n".join(ln for ln in lines if len(ln) >= 20)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


if __name__ == "__main__":
    # ponytail: 真连网烟测；断网/改版时跳过
    from novel_crawler.engine import DownloadEngine
    p = QimaoParser()
    f = DownloadEngine().fetch
    b = p.get_blurb("https://www.qimao.com/shuku/1860026/", f)
    print("blurb:", b[:60])
    assert b, "blurb empty"
    cat = p.get_category("0-a-a", f)
    print("cat:", len(cat))
    assert cat, "category empty"
    sim = p.get_similar("https://www.qimao.com/shuku/1860026/", f)
    print("similar:", len(sim))
    rk = p.get_rank("boy-hot-date", f)
    print("rank:", len(rk))
