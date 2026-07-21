"""交互式聚合搜索 + 编号选书。"""

from novel_crawler.log import get_logger

log = get_logger("search")


def search_and_pick(keyword, engine, registry):
    """聚合搜索 + 交互式编号选择，返回目录页 URL 或 None（取消）。"""
    log.info("'%s' 聚合搜索所有站点...", keyword)
    results = registry.search_all(keyword, engine.cached_fetch)
    if not results:
        log.info("未找到结果")
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
        log.error("请输入 1-%d 的编号", len(results))
