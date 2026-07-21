"""章节正文试读：取一本书前 N 章的标题 + 正文，用于判断文笔。

区别于 `--chapters`（仅章名）：本模块读真实正文。VIP 锁章 / 抓取失败 → content 空、locked=True。
"""

from bs4 import BeautifulSoup

from novel_crawler.log import get_logger

log = get_logger("preview")


def preview(url: str, n: int, engine, registry) -> list[dict]:
    """前 N 章正文。返回 [{title, url, content, locked}]。"""
    parser = registry.get_parser(url)
    html = engine.cached_fetch(url, headers=parser.headers)
    if not html:
        log.warning("目录页获取失败: %s", url)
        return []
    soup = BeautifulSoup(html, "lxml")
    chapters = parser.parse_catalog(soup, url)[: max(1, n)]
    if not chapters:
        log.warning("未解析到章节: %s", url)
        return []
    out: list[dict] = []
    for title, ch_url in chapters:
        content = engine.fetch_chapter(ch_url, parser) or ""
        out.append({
            "title": title,
            "url": ch_url,
            "content": content,
            "locked": not bool(content),
        })
    return out
