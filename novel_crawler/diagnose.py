"""适配健康检查：检测各 parser 的 selector 是否失效（方法返回空/抛异常）。

站点改版常表现为 parse_catalog / parse_content / get_blurb 突然返回空。本模块对每个
声明了 `sample_url` 的 parser 跑关键方法，报 ok / EMPTY（疑似失效）/ ERR，定位到具体方法，
便于快速适配（改版 → 改对应 parser 的 selector）。
"""

from bs4 import BeautifulSoup

from novel_crawler.log import get_logger

log = get_logger("diagnose")

_METHODS = ("blurb", "catalog", "chapters")


def _classify(value, *, empty_when_none=True) -> str:
    if value is None and empty_when_none:
        return "EMPTY"
    return "ok" if value else "EMPTY"


def health_check(registry, fetch, samples: dict | None = None) -> dict:
    """对每个有 sample_url（或 samples 覆盖）的 parser 跑关键方法。
    返回 {domain: {url, blurb, catalog, chapters}}，值为 ok/EMPTY/ERR:类型。"""
    samples = samples or {}
    report: dict[str, dict] = {}
    for domain, parser in registry._parsers.items():
        url = samples.get(domain) or getattr(parser, "sample_url", None)
        if not url:
            continue
        entry: dict = {"url": url}

        try:
            blurb = parser.get_blurb(url, fetch) or ""
            entry["blurb"] = _classify(blurb.strip())
        except Exception as e:  # noqa: BLE001
            entry["blurb"] = f"ERR:{type(e).__name__}"

        try:
            html = fetch(url, headers=getattr(parser, "headers", {}) or {})
            soup = BeautifulSoup(html, "lxml") if html else None
            cats = parser.parse_catalog(soup, url) if soup else []
            entry["catalog"] = _classify(cats)
        except Exception as e:  # noqa: BLE001
            entry["catalog"] = f"ERR:{type(e).__name__}"

        try:
            titles = parser.get_chapter_titles(url, fetch, limit=3)
            entry["chapters"] = _classify(titles)
        except Exception as e:  # noqa: BLE001
            entry["chapters"] = f"ERR:{type(e).__name__}"

        report[domain] = entry
    return report


def format_report(report: dict) -> str:
    """人读报告；非 ok 项加 ⚠ 高亮。"""
    if not report:
        return "（无可诊断的 parser：需在 parser 上设 sample_url，或传 --sample domain=url）"
    lines = []
    for domain, e in report.items():
        flags = " ".join(f"{m}={e.get(m, '-')}" for m in _METHODS)
        mark = " ⚠ 失效" if any(not str(e.get(m, "")).startswith("ok") for m in _METHODS) else ""
        lines.append(f"  [{domain}] {flags}{mark}")
        lines.append(f"      {e['url']}")
    return "\n".join(lines)
