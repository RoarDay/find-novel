"""书单追更：抓书单每本书的目录，与上次快照比对，报告新增章节。"""

from bs4 import BeautifulSoup

from novel_crawler import db
from novel_crawler.log import get_logger

log = get_logger("tracker")


def catalog_meta(parser, url: str, fetch) -> tuple[int, str] | None:
    """通用取目录元数据：parse_catalog 全量 → (总章数, 末章标题)。
    抓取失败或无章节返回 None。七猫 web 仅露最新 1 章（精度低，限制）。"""
    html = fetch(url, headers=getattr(parser, "headers", {}) or {})
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    chapters = parser.parse_catalog(soup, url)
    if not chapters:
        return None
    return len(chapters), chapters[-1][0]


def track_booklist(name: str, engine, registry) -> list[dict]:
    """遍历书单每本书：抓目录 → 与上次快照比对 new=curr-prev → upsert 快照。
    返回 [{title, source, url, prev_total, curr_total, new, last_chapter, status}]。
    new=None 表示首次追踪（无上次快照）。"""
    books = db.get_booklist_books(name)
    if not books:
        log.info("书单 '%s' 为空或不存在", name)
        return []
    report: list[dict] = []
    for b in books:
        entry = {
            "title": b["title"], "source": b["source"], "url": b["url"],
            "prev_total": None, "curr_total": None, "new": None,
            "last_chapter": "", "status": "ok",
        }
        try:
            parser = registry.get_parser(b["url"])
        except ValueError:
            entry["status"] = "no_parser"
            report.append(entry)
            continue
        meta = catalog_meta(parser, b["url"], engine.cached_fetch)
        if not meta:
            entry["status"] = "fetch_failed"
            report.append(entry)
            continue
        curr_total, last_title = meta
        prev = db.get_snapshot(int(b["id"]))
        prev_total = prev["chapter_total"] if prev else None
        entry["curr_total"] = curr_total
        entry["last_chapter"] = last_title
        entry["prev_total"] = prev_total
        entry["new"] = (curr_total - prev_total) if prev_total is not None else None
        db.upsert_snapshot(int(b["id"]), curr_total, last_title)
        report.append(entry)
    return report
