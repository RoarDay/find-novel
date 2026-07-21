"""下载一本书：取目录 → 切片 → 并发下载 → 合并写文件。"""

import sys
import time

from bs4 import BeautifulSoup

from novel_crawler import ParserRegistry
from novel_crawler.config import DOWNLOAD_DIR
from novel_crawler.log import get_logger

log = get_logger("download")


def download(catalog_url, args, engine):
    """下载一本书：取目录 → 切片 → 并发下载 → 合并写文件。"""
    registry = ParserRegistry()
    try:
        parser = registry.get_parser(catalog_url)
        log.info("使用解析器: %s", parser.__class__.__name__)
    except ValueError as e:
        log.error("%s", e)
        log.error("当前支持的站点: %s", ", ".join(registry.list_supported()))
        sys.exit(1)

    log.info("[1/3] 获取目录...")
    catalog_html = engine.fetch(catalog_url, headers=parser.headers)
    if not catalog_html:
        log.error("目录页获取失败")
        sys.exit(1)

    soup = BeautifulSoup(catalog_html, "lxml")
    chapters = parser.parse_catalog(soup, catalog_url)
    if not chapters:
        log.error("未解析到章节")
        sys.exit(1)

    start = max(1, args.start)
    end = min(args.end if args.end is not None else len(chapters), len(chapters))
    if start > end:
        log.error("--start 不能大于 --end")
        sys.exit(1)
    chapters = chapters[start - 1:end]
    log.info("[1/3] 共 %d 章（范围: %d-%d）", len(chapters), start, end)

    novel_name_el = soup.select_one("h1")
    novel_name = novel_name_el.get_text(strip=True) if novel_name_el else "未知小说"
    author = "未知"
    meta_author = soup.find("meta", property="og:novel:author")
    if meta_author:
        author = meta_author.get("content", author)

    log.info("[2/3] 开始下载（线程数: %d）...", args.workers)
    t0 = time.perf_counter()

    def on_progress(completed: int, total: int):
        log.info("已完成: %d/%d (%d%%)", completed, total, completed * 100 // total)

    results, failed = engine.download_all(
        chapters, lambda url: engine.fetch_chapter(url, parser), on_progress
    )
    elapsed = time.perf_counter() - t0

    log.info("[3/3] 合并写入文件...")
    filename = engine.save(
        novel_name, author, chapters, results,
        filename=args.output,
        output_dir=None if args.output else DOWNLOAD_DIR,
    )

    log.info("保存至: %s", filename)
    log.info("耗时: %.1f 秒", elapsed)
    if failed:
        log.warning("失败章节: %d 章", len(failed))
        for idx, title, _ in failed[:5]:
            log.warning("  - 第%d章 %s", idx, title)
        if len(failed) > 5:
            log.warning("  ... 还有 %d 章", len(failed) - 5)
    else:
        log.info("全部章节下载成功")
