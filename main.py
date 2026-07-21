#!/usr/bin/env python3
"""
极简多站小说爬虫 —— 入口脚本

用法：
    python main.py <目录页URL> [选项]                       # 直接下载
    python main.py --search <书名> [选项]                   # 聚合搜索后交互式选书
    python main.py --search <词> --json                     # 非交互 JSON（给 Claude 调）
    python main.py --blurb <url> [<url>...]                 # 批量取简介 JSON
    python main.py --category <cat> --source <域名> --json  # 单站分类 JSON
    python main.py --rank <type> --source <域名> --json     # 单站排行 JSON

示例：
    python main.py https://www.92yanqing.com/read/36979/
    python main.py --search 斗破苍穹 --workers 10
"""

import argparse
import json
import sys
import time
from bs4 import BeautifulSoup
from novel_crawler import ParserRegistry, DownloadEngine

DOWNLOAD_DIR = "novels"  # 小说下载目录（已加入 .gitignore）


def parse_args():
    parser = argparse.ArgumentParser(description="极简多站小说爬虫")
    parser.add_argument("url", nargs="?", default=None, help="小说目录页 URL（与 --search 二选一）")
    parser.add_argument("--search", type=str, default=None, help="按书名聚合搜索所有站点，交互式选书")
    parser.add_argument("--workers", type=int, default=8, help="并发线程数 (默认: 8)")
    parser.add_argument("--delay-min", type=float, default=0.1, help="最小请求延迟秒数 (默认: 0.1)")
    parser.add_argument("--delay-max", type=float, default=0.3, help="最大请求延迟秒数 (默认: 0.3)")
    parser.add_argument("--start", type=int, default=1, help="起始章节索引，从1开始 (默认: 1)")
    parser.add_argument("--end", type=int, default=None, help="结束章节索引 (默认: 全部)")
    parser.add_argument("--output", type=str, default=None, help="自定义输出文件名")
    # 非交互 JSON 出口（给 Claude 调用）
    parser.add_argument("--json", action="store_true", help="非交互 JSON 输出（配合 --search/--category/--rank）")
    parser.add_argument("--blurb", nargs="+", default=None, help="批量取详情页简介，输出 {url: blurb} JSON")
    parser.add_argument("--category", type=str, default=None, help="分类/标签筛选（需 --source 指定站）")
    parser.add_argument("--rank", type=str, default=None, help="排行榜类型（需 --source 指定站）")
    parser.add_argument("--source", type=str, default=None, help="指定站点域名（配合 --category/--rank）")
    parser.add_argument("--chapters", nargs="+", default=None, help="取目录页前 N 章标题 JSON {url: [title...]}（配合 --top）")
    parser.add_argument("--top", type=int, default=50, help="--chapters 取的章节数（默认 50）")
    return parser.parse_args()


def _r_dict(r):
    """SearchResult → dict（JSON 输出）。"""
    return {"title": r.title, "url": r.url, "source": r.source, "author": r.author, "blurb": r.blurb, "word_count": r.word_count}


def _json_dump(obj):
    print(json.dumps(obj, ensure_ascii=False))


def search_and_pick(keyword, engine, registry):
    """聚合搜索 + 交互式编号选择，返回目录页 URL 或 None（取消）。"""
    print(f"[搜索] '{keyword}' 聚合搜索所有站点...")
    results = registry.search_all(keyword, engine.fetch)
    if not results:
        print("[搜索] 未找到结果")
        return None
    for i, r in enumerate(results, 1):
        line = f"  {i}. [{r.source}] {r.title}"
        if r.author:
            line += f" / {r.author}"
        print(line)
    while True:
        choice = input("输入编号下载（0 取消）: ").strip()
        if choice in ("0", ""):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            return results[int(choice) - 1].url
        print(f"[错误] 请输入 1-{len(results)} 的编号")


def download(catalog_url, args, engine):
    """下载一本书：取目录 → 切片 → 并发下载 → 合并写文件。"""
    registry = ParserRegistry()
    try:
        parser = registry.get_parser(catalog_url)
        print(f"[匹配] 使用解析器: {parser.__class__.__name__}")
    except ValueError as e:
        print(f"[错误] {e}")
        print(f"当前支持的站点: {', '.join(registry.list_supported())}")
        sys.exit(1)

    # 1. 获取目录
    print("[1/3] 获取目录...")
    catalog_html = engine.fetch(catalog_url, headers=parser.headers)
    if not catalog_html:
        print("[错误] 目录页获取失败")
        sys.exit(1)

    soup = BeautifulSoup(catalog_html, "lxml")
    chapters = parser.parse_catalog(soup, catalog_url)
    if not chapters:
        print("[错误] 未解析到章节")
        sys.exit(1)

    # 2. 章节范围切片
    start = max(1, args.start)
    end = min(args.end if args.end is not None else len(chapters), len(chapters))
    if start > end:
        print("[错误] --start 不能大于 --end")
        sys.exit(1)
    chapters = chapters[start - 1:end]
    print(f"[1/3] 共 {len(chapters)} 章（范围: {start}-{end}）")

    # 3. 获取小说元数据（标题、作者）
    novel_name = soup.select_one("h1")
    novel_name = novel_name.get_text(strip=True) if novel_name else "未知小说"
    author = "未知"
    meta_author = soup.find("meta", property="og:novel:author")
    if meta_author:
        author = meta_author.get("content", author)

    # 4. 并发下载
    print(f"[2/3] 开始下载（线程数: {args.workers}）...")
    t0 = time.perf_counter()

    def on_progress(completed: int, total: int):
        print(f"  -> 已完成: {completed}/{total} ({completed * 100 // total}%)")

    results, failed = engine.download_all(
        chapters, lambda url: engine.fetch_chapter(url, parser), on_progress
    )
    elapsed = time.perf_counter() - t0

    # 5. 写入文件
    print("[3/3] 合并写入文件...")
    filename = engine.save(
        novel_name, author, chapters, results,
        filename=args.output,
        output_dir=None if args.output else DOWNLOAD_DIR,
    )

    print(f"\n[完成] 保存至: {filename}")
    print(f"⏱️  耗时: {elapsed:.1f} 秒")
    if failed:
        print(f"⚠️  失败章节: {len(failed)} 章")
        for idx, title, _ in failed[:5]:
            print(f"   - 第{idx}章 {title}")
        if len(failed) > 5:
            print(f"   ... 还有 {len(failed) - 5} 章")
    else:
        print("✅ 全部章节下载成功")


def main():
    args = parse_args()
    engine = DownloadEngine(
        max_workers=args.workers,
        delay=(args.delay_min, args.delay_max),
    )
    registry = ParserRegistry()

    # 非交互 JSON 出口（给 Claude 调用）
    if args.blurb:
        out = {}
        for u in args.blurb:
            try:
                out[u] = registry.get_parser(u).get_blurb(u, engine.fetch)
            except Exception:
                out[u] = ""
        _json_dump(out)
        return
    if args.chapters:
        out = {}
        for u in args.chapters:
            try:
                out[u] = registry.get_parser(u).get_chapter_titles(u, engine.fetch, args.top)
            except Exception:
                out[u] = []
        _json_dump(out)
        return
    if args.json and args.search:
        _json_dump([_r_dict(r) for r in registry.search_all(args.search, engine.fetch)])
        return
    if args.json and args.category and args.source:
        try:
            p = registry.get_by_source(args.source)
            _json_dump([_r_dict(r) for r in p.get_category(args.category, engine.fetch)])
        except Exception as e:
            _json_dump({"error": str(e)})
        return
    if args.json and args.rank and args.source:
        try:
            p = registry.get_by_source(args.source)
            _json_dump([_r_dict(r) for r in p.get_rank(args.rank, engine.fetch)])
        except Exception as e:
            _json_dump({"error": str(e)})
        return

    # 原有交互/下载
    if not args.url and not args.search:
        print("[错误] 必须提供目录页 URL 或 --search 关键词")
        print("  用法: python main.py <URL>  或  python main.py --search <书名>")
        sys.exit(1)

    catalog_url = args.url
    if args.search:
        catalog_url = search_and_pick(args.search, engine, registry)
        if not catalog_url:
            return

    download(catalog_url, args, engine)


if __name__ == "__main__":
    main()
