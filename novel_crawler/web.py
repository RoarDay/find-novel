"""轻 Web 界面：浏览器翻看本地 DB（书单/书/历史/协同推荐）。

stdlib `http.server`，零新运行时依赖。纯 DB 读取，不触网。
渲染逻辑全是纯函数（便于单测），handler 只做路由 + 拼 HTTP。
"""

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from novel_crawler import db
from novel_crawler.log import get_logger

log = get_logger("web")


def _esc(s) -> str:
    return html.escape(str(s))


def _q(s) -> str:
    return html.escape(str(s), quote=True)


def _book_link(title: str, url: str, after: str = "") -> str:
    return (
        f"<li><a href='/recommend?url={_q(url)}'>{_esc(title)}</a>{after}</li>"
    )


def _source_tag(source: str) -> str:
    return f" <span class='tag'>{_esc(source)}</span>"


def _author_meta(author: str) -> str:
    return f" <span class='meta'>{_esc(author)}</span>" if author else ""


_CSS = """
body{font:14px/1.6 -apple-system,"PingFang SC",sans-serif;
     max-width:880px;margin:2em auto;color:#222}
a{color:#2563eb;text-decoration:none} a:hover{text-decoration:underline}
.card{border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin:10px 0}
.meta{color:#6b7280;font-size:12px}
h1{font-size:1.4em} nav a{margin-right:12px}
.tag{display:inline-block;background:#eff6ff;color:#1d4ed8;
     border-radius:4px;padding:0 6px;font-size:12px}
.warn{color:#dc2626}
"""


def _page(title: str, body: str) -> str:
    nav = ("<nav><a href='/'>首页</a><a href='/booklists'>书单</a>"
           "<a href='/books'>书籍</a><a href='/history'>历史</a></nav>")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head>"
        f"<body><h1>{_esc(title)}</h1>{nav}{body}</body></html>"
    )


def render_index() -> str:
    return _page("novel-crawler", "<div class='card'>本地小说库浏览器。纯 DB 读取。</div>")


def render_booklists(lists) -> str:
    if not lists:
        return _page("书单", "<div class='card'>（暂无书单）</div>")
    items = "".join(
        f"<li><a href='/booklist?name={_q(bl['name'])}'>{_esc(bl['name'])}</a> "
        f"<span class='meta'>({bl['created_at'][:10]})</span></li>"
        for bl in lists
    )
    return _page("书单", f"<ul>{items}</ul>")


def render_booklist(name: str, books) -> str:
    if not books:
        return _page(f"书单：{name}", "<div class='card'>（空或不存在）</div>")
    items = "".join(
        _book_link(b["title"], b["url"],
                   _source_tag(b["source"]) + _author_meta(b["author"]))
        for b in books
    )
    return _page(f"书单：{name}", f"<ul>{items}</ul>")


def render_books(rows) -> str:
    if not rows:
        return _page("书籍", "<div class='card'>（暂无书籍，先 --search 或 booklist add）</div>")
    items = "".join(
        _book_link(
            r["title"], r["url"],
            _source_tag(r["source"]) + _author_meta(r["author"]),
        )
        for r in rows
    )
    return _page("书籍", f"<ul>{items}</ul>")


def render_history(rows) -> str:
    if not rows:
        return _page("找书历史", "<div class='card'>（暂无历史）</div>")
    items = "".join(
        f"<li>[{r['searched_at'][:19]}] {_esc(r['keyword'])} "
        f"<span class='meta'>({r['result_count']} 条)</span></li>"
        for r in rows
    )
    return _page("找书历史", f"<ul>{items}</ul>")


def render_recommend(url: str, recs, book=None) -> str:
    title = book["title"] if book else url
    body = f"<div class='card'>读过《{_esc(title)}》也读：</div>"
    if not recs:
        body += "<div class='card warn'>（无推荐：该书不在任何书单，或暂无共现）</div>"
    else:
        items = "".join(
            f"<li>{_esc(r['title'])}{_source_tag(r['source'])} "
            f"<span class='meta'>{r['co']} 次共现</span></li>"
            for r in recs
        )
        body += f"<ul>{items}</ul>"
    return _page(f"推荐：{title}", body)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path in ("/", ""):
                body = render_index()
            elif path == "/booklists":
                body = render_booklists(db.list_booklists())
            elif path == "/booklist":
                name = qs.get("name", [""])[0]
                body = render_booklist(name, db.get_booklist_books(name))
            elif path == "/books":
                body = render_books(db.list_all_books())
            elif path == "/history":
                body = render_history(db.list_search_history())
            elif path == "/recommend":
                url = qs.get("url", [""])[0]
                body = render_recommend(url, db.recommend_for(url), db.get_book(url))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404")
                return
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # noqa: BLE001
            log.warning("web 请求失败 %s: %s", path, e)
            self.send_response(500)
            self.end_headers()

    def log_message(self, fmt, *args):  # 静默默认日志，走自己的 logger
        log.info("%s - %s", self.address_string(), fmt % args)


def serve(port: int = 8000) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    log.info("轻Web 已启动：http://127.0.0.1:%d/ （Ctrl+C 退出）", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
