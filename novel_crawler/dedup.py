"""跨站去重 + 元数据聚合：按规范化(书名,作者)把多站命中的同一本书合并。"""

import re

# sqlite3.Row 仅用于类型提示，运行时鸭子类型（测试用 dict）
try:
    from sqlite3 import Row  # noqa: F401
except ImportError:  # pragma: no cover
    pass


def normalize(title: str, author: str) -> tuple[str, str]:
    """去空白/标点/下划线 + 小写，保留 CJK 与字母数字 → 稳定 key。"""

    def _norm(s: str) -> str:
        s = s or ""
        return re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE).lower()

    return _norm(title), _norm(author)


def _parse_wc(s: str | None) -> float | None:
    """`767.59万字` / `2089021` → 可比较的数字（万 → ×10000）。"""
    s = s or ""
    m = re.search(r"([\d.]+)\s*万", s)
    if m:
        return float(m.group(1)) * 10000
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else None


def group_books(rows) -> list[dict]:
    """按 normalize(书名,作者) 分组。每组聚合来源/字数(取大)/简介(取最长)/url。
    按来源数降序、书名升序。row 鸭子类型（sqlite3.Row 或 dict，按键取值）。"""
    groups: dict[tuple[str, str], dict] = {}
    for r in rows:
        title = r["title"]
        author = r["author"] or ""
        key = normalize(title, author)
        g = groups.setdefault(
            key,
            {
                "title": title, "author": author, "sources": set(),
                "urls": [], "word_count": "", "blurb": "",
                "_wc_num": None, "n": 0,
            },
        )
        g["sources"].add(r["source"])
        g["urls"].append(r["url"])
        g["n"] += 1
        blurb = r["blurb"] or ""
        if blurb and len(blurb) > len(g["blurb"]):
            g["blurb"] = blurb
        wc = _parse_wc(r["word_count"])
        if wc and (g["_wc_num"] is None or wc > g["_wc_num"]):
            g["_wc_num"] = wc
            g["word_count"] = r["word_count"]
    out = []
    for g in groups.values():
        g["sources"] = sorted(g["sources"])
        g.pop("_wc_num", None)
        out.append(g)
    out.sort(key=lambda x: (-len(x["sources"]), x["title"]))
    return out
