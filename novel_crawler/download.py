"""下载一本书：取目录 → 切片 → 下载 → 合并写文件。

--full（七猫）：走 App API 完整目录 + 全本 zip+AES（_qimao_appapi），
其余走 web parse_catalog + 逐章并发下载。
"""

import sys
import time

from bs4 import BeautifulSoup

from novel_crawler import ParserRegistry
from novel_crawler.config import DOWNLOAD_DIR
from novel_crawler.log import get_logger

log = get_logger("download")


def _meta_from_soup(soup, fallback_url: str) -> tuple[str, str]:
    novel_name_el = soup.select_one("h1")
    novel_name = novel_name_el.get_text(strip=True) if novel_name_el else "未知小说"
    author = "未知"
    meta_author = soup.find("meta", property="og:novel:author")
    if meta_author:
        author = meta_author.get("content", author)
    return novel_name, author


def _slice(chapters: list, args) -> list:
    start = max(1, args.start)
    end = min(args.end if args.end is not None else len(chapters), len(chapters))
    if start > end:
        log.error("--start 不能大于 --end")
        sys.exit(1)
    return chapters[start - 1:end]


def download(catalog_url, args, engine):
    """下载一本书：取目录 → 切片 → 下载 → 合并写文件。"""
    registry = ParserRegistry()
    try:
        parser = registry.get_parser(catalog_url)
        log.info("使用解析器: %s", parser.__class__.__name__)
    except ValueError as e:
        log.error("%s", e)
        log.error("当前支持的站点: %s", ", ".join(registry.list_supported()))
        sys.exit(1)

    # 目录页（web）用于书名/作者元数据；--full 也复用
    catalog_html = engine.fetch(catalog_url, headers=parser.headers)
    if not catalog_html:
        log.error("目录页获取失败")
        sys.exit(1)
    soup = BeautifulSoup(catalog_html, "lxml")
    novel_name, author = _meta_from_soup(soup, catalog_url)

    use_full = args.full and hasattr(parser, "get_full_catalog")
    if use_full:
        chapters, results, failed, elapsed = _full(catalog_url, args, parser)
    else:
        chapters, results, failed, elapsed = _web(catalog_url, args, parser, engine, soup)

    if not chapters:
        log.error("未解析到章节")
        sys.exit(1)

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


def _web(catalog_url, args, parser, engine, soup):
    """web 流程：parse_catalog → 逐章并发下载。"""
    chapters = parser.parse_catalog(soup, catalog_url)
    chapters = _slice(chapters, args)
    log.info("[1/3] 共 %d 章（范围: %d-%d）", len(chapters), args.start,
             args.end if args.end is not None else len(chapters))
    log.info("[2/3] 开始下载（线程数: %d）...", args.workers)
    t0 = time.perf_counter()

    def on_progress(completed: int, total: int):
        log.info("已完成: %d/%d (%d%%)", completed, total, completed * 100 // total)

    results, failed = engine.download_all(
        chapters, lambda url: engine.fetch_chapter(url, parser), on_progress
    )
    return chapters, results, failed, time.perf_counter() - t0


def _full(catalog_url, args, parser):
    """--full 流程：App API 完整目录 + 全本 zip+AES（七猫）。"""
    book_id = parser.book_id_from_url(catalog_url)
    if not book_id:
        log.error("--full 需要 /shuku/{book_id}/ 形式的七猫 URL")
        sys.exit(1)
    log.info("[1/3] App API 完整目录（book_id=%s）...", book_id)
    chapters = parser.get_full_catalog(book_id)
    if not chapters:
        log.error("App API 目录为空（签名失效或网络问题，见 research/sign.md）")
        sys.exit(1)
    chapters = _slice(chapters, args)
    log.info("[1/3] 共 %d 章（范围: %d-%d）", len(chapters), args.start,
             args.end if args.end is not None else len(chapters))
    log.info("[2/3] 全本下载（zip + AES 解密）...")
    t0 = time.perf_counter()
    try:
        content_map = parser.download_full_content(book_id)
    except ImportError as e:
        log.error("全本下载需要 pycryptodome: pip install 'novel-crawler[qimao]'（%s）", e)
        sys.exit(1)
    elapsed = time.perf_counter() - t0
    results = {
        i + 1: (title, content_map.get(cid))
        for i, (title, cid) in enumerate(chapters)
    }
    failed = [
        (i + 1, title, cid)
        for i, (title, cid) in enumerate(chapters)
        if cid not in content_map
    ]
    return chapters, results, failed, elapsed
