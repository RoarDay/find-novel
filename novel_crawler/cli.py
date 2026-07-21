"""小说爬虫 CLI 入口（novel-crawler 命令；python main.py 兼容薄壳调这里）。"""

import argparse
import json
import sys
from urllib.parse import urlparse

from novel_crawler import DownloadEngine, ParserRegistry, config, db
from novel_crawler.base import SearchResult
from novel_crawler.config import DEFAULT_DELAY
from novel_crawler.download import download
from novel_crawler.interactive import search_and_pick
from novel_crawler.log import get_logger

log = get_logger("cli")


def parse_args():
    parser = argparse.ArgumentParser(description="极简多站小说爬虫")
    parser.add_argument(
        "url", nargs="?", default=None,
        help="小说目录页 URL（与 --search 二选一）",
    )
    parser.add_argument(
        "--search", type=str, default=None,
        help="按书名聚合搜索所有站点，交互式选书",
    )
    parser.add_argument("--workers", type=int, default=8, help="并发线程数 (默认: 8)")
    parser.add_argument(
        "--delay-min", type=float, default=DEFAULT_DELAY[0],
        help=f"最小请求延迟秒数 (默认: {DEFAULT_DELAY[0]})",
    )
    parser.add_argument(
        "--delay-max", type=float, default=DEFAULT_DELAY[1],
        help=f"最大请求延迟秒数 (默认: {DEFAULT_DELAY[1]})",
    )
    parser.add_argument(
        "--start", type=int, default=1,
        help="起始章节索引，从1开始 (默认: 1)",
    )
    parser.add_argument("--end", type=int, default=None, help="结束章节索引 (默认: 全部)")
    parser.add_argument("--output", type=str, default=None, help="自定义输出文件名")
    parser.add_argument(
        "--json", action="store_true",
        help="非交互 JSON 输出（配合 --search/--category/--rank）",
    )
    parser.add_argument(
        "--blurb", nargs="+", default=None,
        help="批量取详情页简介，输出 {url: blurb} JSON",
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="分类/标签筛选（需 --source 指定站）",
    )
    parser.add_argument(
        "--rank", type=str, default=None,
        help="排行榜类型（需 --source 指定站）",
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help="指定站点域名（配合 --category/--rank）",
    )
    parser.add_argument(
        "--chapters", nargs="+", default=None,
        help="取目录页前 N 章标题 JSON {url: [title...]}（配合 --top）",
    )
    parser.add_argument(
        "--top", type=int, default=50,
        help="--chapters 取的章节数（默认 50）",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="七猫走 App API 完整目录 + 全本下载（zip+AES，需 pycryptodome）",
    )
    parser.add_argument(
        "--preview", type=int, default=None, metavar="N",
        help="取前 N 章正文（试读文笔），配合 positional <url>，JSON 输出",
    )
    return parser.parse_args()


def _r_dict(r):
    """SearchResult → dict（JSON 输出）。"""
    return {
        "title": r.title,
        "url": r.url,
        "source": r.source,
        "author": r.author,
        "blurb": r.blurb,
        "word_count": r.word_count,
    }


def _json_dump(obj):
    """JSON 出口：唯一允许写 stdout 的地方。"""
    print(json.dumps(obj, ensure_ascii=False))


# ── 子命令：booklist / history ─────────────────────────────────────────
# ponytail: 现有 parser 用 positional `url`，与 argparse subparsers 冲突，
# 直接 peek sys.argv[1] 派发，保持现有 CLI 完全不变。

def _cli_booklist(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="novel-crawler booklist", description="书单管理")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("create", help="建书单")
    sp.add_argument("name")

    sp = sub.add_parser("add", help="加书到书单（从 url 取信息入库）")
    sp.add_argument("name")
    sp.add_argument("url")

    sp = sub.add_parser("list", help="列出所有书单或某书单里的书")
    sp.add_argument("--name", default=None)

    sp = sub.add_parser("remove", help="从书单移除书")
    sp.add_argument("name")
    sp.add_argument("url")

    sp = sub.add_parser("track", help="追更：抓目录比对快照，报告新增章节")
    sp.add_argument("name")

    ns = p.parse_args(argv)

    if ns.cmd == "create":
        try:
            db.create_booklist(ns.name)
            print(f"已创建书单: {ns.name}")
        except ValueError as e:
            log.error("%s", e)

    elif ns.cmd == "add":
        _booklist_add(ns.name, ns.url)

    elif ns.cmd == "list":
        if ns.name:
            books = db.get_booklist_books(ns.name)
            if not books:
                print(f"书单 '{ns.name}' 为空或不存在")
                return
            print(f"书单 '{ns.name}'（{len(books)} 本）：")
            for b in books:
                line = f"  - {b['title']}"
                if b["author"]:
                    line += f" / {b['author']}"
                line += f"  [{b['source']}]"
                print(line)
        else:
            lists = db.list_booklists()
            if not lists:
                print("（暂无书单，先 novel-crawler booklist create <name>）")
                return
            print(f"书单（{len(lists)} 个）：")
            for bl in lists:
                print(f"  - {bl['name']}  (创建于 {bl['created_at'][:10]})")

    elif ns.cmd == "remove":
        try:
            db.remove_from_booklist(ns.name, ns.url)
            print(f"已从 '{ns.name}' 移除: {ns.url}")
        except ValueError as e:
            log.error("%s", e)

    elif ns.cmd == "track":
        _booklist_track(ns.name)


def _booklist_track(name: str) -> None:
    """追更：抓书单每本书目录，与上次快照比对，打印新增章节。"""
    from novel_crawler.registry import ParserRegistry
    from novel_crawler.tracker import track_booklist

    engine = DownloadEngine(delay=DEFAULT_DELAY)
    registry = ParserRegistry()
    report = track_booklist(name, engine, registry)
    if not report:
        return
    has_new = False
    for e in report:
        if e["status"] != "ok":
            print(f"  - {e['title']} [{e['source']}]（{e['status']}）")
            continue
        new = e["new"]
        marker = ""
        if new and new > 0:
            marker = f"  ⭐新增 {new} 章"
            has_new = True
        prev = e["prev_total"] if e["prev_total"] is not None else "?"
        print(f"  - {e['title']} [{e['source']}] {prev}→{e['curr_total']} 章{marker}")
        print(f"      最新: {e['last_chapter']}")
    if not has_new:
        print("（无新增章节）")


def _booklist_add(name: str, url: str) -> None:
    """从 url 取 book 信息入库 + 加书单。已在 books 表则直接加。"""
    if not any(b["name"] == name for b in db.list_booklists()):
        log.error("书单 '%s' 不存在，先 novel-crawler booklist create %s", name, name)
        return
    if db.get_book(url) is None:
        try:
            engine = DownloadEngine(delay=DEFAULT_DELAY)
            registry = ParserRegistry()
            parser = registry.get_parser(url)
            html = engine.cached_fetch(url, headers=parser.headers)
            title = url
            blurb = ""
            if html:
                # ponytail: get_blurb 内部会重新 fetch，sub-optimal 但 parser API
                # 设计如此；保持一致而非绕开。
                blurb = parser.get_blurb(url, engine.cached_fetch)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "lxml")
                h1 = soup.select_one("h1")
                if h1:
                    title = h1.get_text(strip=True)
            db.add_book(SearchResult(
                title=title or url, url=url,
                source=urlparse(url).netloc, blurb=blurb,
            ))
        except Exception as e:
            log.error("取 book 信息失败: %s", e)
            return
    try:
        db.add_to_booklist(name, url)
        print(f"已加入 '{name}': {url}")
    except ValueError as e:
        log.error("%s", e)


def _cli_history(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="novel-crawler history", description="找书历史")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出最近的搜索")
    ns = p.parse_args(argv)

    if ns.cmd == "list":
        rows = db.list_search_history()
        if not rows:
            print("（暂无找书历史）")
            return
        print(f"找书历史（最近 {len(rows)} 条）：")
        for r in rows:
            ts = r["searched_at"][:19].replace("T", " ")
            print(f"  [{ts}] {r['keyword']}  ({r['result_count']} 条)")


def _cli_recommend(argv: list[str]) -> None:
    p = argparse.ArgumentParser(
        prog="novel-crawler recommend", description="协同推荐（读过 X 也读 Y）"
    )
    p.add_argument("url", help="书的目录页 URL（需已在某书单）")
    p.add_argument("--limit", type=int, default=10)
    ns = p.parse_args(argv)
    rows = db.recommend_for(ns.url, ns.limit)
    if not rows:
        print("（无推荐：该书不在任何书单，或暂无共现）")
        return
    book = db.get_book(ns.url)
    title = book["title"] if book else ns.url
    print(f"读过《{title}》也读：")
    for r in rows:
        line = f"  - {r['title']}（{r['co']} 次共现）[{r['source']}]"
        if r["author"]:
            line += f" / {r['author']}"
        print(line)


def _cli_dedup(argv: list[str]) -> None:
    from novel_crawler.dedup import group_books

    p = argparse.ArgumentParser(
        prog="novel-crawler dedup", description="跨站去重 + 元数据聚合"
    )
    p.add_argument("--all", action="store_true", help="显示全部分组（默认仅多源重复）")
    ns = p.parse_args(argv)
    groups = group_books(db.list_all_books())
    shown = groups if ns.all else [g for g in groups if len(g["sources"]) > 1]
    if not shown:
        print("（无跨站重复" + ("，--all 查看全部" if not ns.all else "）"))
        return
    for g in shown:
        print(f"  《{g['title']}》/ {g['author']}  [{'+'.join(g['sources'])}]")
        wc = g["word_count"] or "?"
        print(f"      {wc}字  {len(g['sources'])} 源  {len(g['urls'])} 条记录")


def _cli_diagnose(argv: list[str]) -> None:
    from novel_crawler.diagnose import format_report, health_check

    p = argparse.ArgumentParser(
        prog="novel-crawler diagnose",
        description="站点 selector 健康检查（失效检测，定位改版）",
    )
    p.add_argument(
        "--sample", action="append", default=[], metavar="DOMAIN=URL",
        help="覆盖/补充某 domain 的样本 URL（可多次）",
    )
    ns = p.parse_args(argv)
    samples = {}
    for item in ns.sample:
        if "=" in item:
            k, v = item.split("=", 1)
            samples[k.strip()] = v.strip()
    engine = DownloadEngine(delay=DEFAULT_DELAY)
    registry = ParserRegistry()
    report = health_check(registry, engine.cached_fetch, samples)
    print(format_report(report))


def _cli_web(argv: list[str]) -> None:
    from novel_crawler.web import serve

    p = argparse.ArgumentParser(prog="novel-crawler web", description="轻Web界面（浏览器看本地库）")
    p.add_argument("--port", type=int, default=8000)
    ns = p.parse_args(argv)
    serve(ns.port)


def main():
    # 子命令派发：booklist / history / recommend 不走原 positional url 流。
    argv = sys.argv[1:]
    if argv and argv[0] == "booklist":
        _cli_booklist(argv[1:])
        return
    if argv and argv[0] == "history":
        _cli_history(argv[1:])
        return
    if argv and argv[0] == "recommend":
        _cli_recommend(argv[1:])
        return
    if argv and argv[0] == "dedup":
        _cli_dedup(argv[1:])
        return
    if argv and argv[0] == "diagnose":
        _cli_diagnose(argv[1:])
        return
    if argv and argv[0] == "web":
        _cli_web(argv[1:])
        return

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
                out[u] = registry.get_parser(u).get_blurb(u, engine.cached_fetch)
            except Exception:
                out[u] = ""
        _json_dump(out)
        return
    if args.chapters:
        out = {}
        for u in args.chapters:
            try:
                out[u] = registry.get_parser(u).get_chapter_titles(u, engine.cached_fetch, args.top)
            except Exception:
                out[u] = []
        _json_dump(out)
        return
    if args.json and args.search:
        results = registry.search_all(args.search, engine.cached_fetch)
        if config.enable_history:
            try:
                db.record_search(args.search, len(results))
                for r in results:
                    db.add_book(r)
            except Exception as e:
                log.warning("记录找书历史失败: %s", e)
        _json_dump([_r_dict(r) for r in results])
        return
    if args.json and args.category and args.source:
        try:
            p = registry.get_by_source(args.source)
            _json_dump([_r_dict(r) for r in p.get_category(args.category, engine.cached_fetch)])
        except Exception as e:
            _json_dump({"error": str(e)})
        return
    if args.json and args.rank and args.source:
        try:
            p = registry.get_by_source(args.source)
            _json_dump([_r_dict(r) for r in p.get_rank(args.rank, engine.cached_fetch)])
        except Exception as e:
            _json_dump({"error": str(e)})
        return
    if args.preview is not None and args.url:
        from novel_crawler.preview import preview

        try:
            _json_dump(preview(args.url, args.preview, engine, registry))
        except Exception as e:
            _json_dump({"error": str(e)})
        return

    # 原有交互/下载
    if not args.url and not args.search:
        log.error("必须提供目录页 URL 或 --search 关键词")
        log.error("用法: novel-crawler <URL>  或  novel-crawler --search <书名>")
        sys.exit(1)

    catalog_url = args.url
    if args.search:
        catalog_url = search_and_pick(args.search, engine, registry)
        if not catalog_url:
            return

    download(catalog_url, args, engine)


if __name__ == "__main__":
    main()
