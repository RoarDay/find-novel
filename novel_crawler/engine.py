"""下载引擎：HTTP 请求、重试、并发调度、顺序写入。"""

import concurrent.futures
import random
import threading
import time
from collections.abc import Callable

import requests

from novel_crawler.config import DEFAULT_DELAY, DEFAULT_UA


class DownloadEngine:
    def __init__(
        self,
        max_workers: int = 5,
        delay: tuple[float, float] = DEFAULT_DELAY,
    ):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self.max_workers = max_workers
        self.delay = delay
        self.lock = threading.Lock()

    def fetch(
        self,
        url: str,
        retries: int = 3,
        method: str = "GET",
        data: dict | None = None,
        headers: dict | None = None,
        cache: bool = False,
        cache_ttl: int | None = None,
    ) -> str | None:
        """带指数退避的请求。

        method/data 支持 POST；headers 支持 per-parser 覆盖（如起点 iPhone UA）。
        cache=True 时走短期缓存（搜索/详情页等元数据；下载流程不要开）。
        """
        if cache:
            from novel_crawler import cache as cache_mod
            from novel_crawler import config

            key = cache_mod.make_key(method, url, data, headers)
            hit = cache_mod.get(key, cache_ttl if cache_ttl is not None else config.CACHE_TTL)
            if hit is not None:
                return hit
        for i in range(retries):
            try:
                time.sleep(random.uniform(*self.delay))
                if method == "POST":
                    resp = self.session.post(url, data=data, headers=headers, timeout=15)
                else:
                    resp = self.session.get(url, headers=headers, timeout=15)
                resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
                if resp.status_code == 200:
                    if cache:
                        cache_mod.set(key, resp.text)
                    return resp.text
            except Exception:
                time.sleep(0.5 * (i + 1))
        return None

    def cached_fetch(
        self,
        url: str,
        retries: int = 3,
        method: str = "GET",
        data: dict | None = None,
        headers: dict | None = None,
    ) -> str | None:
        """engine.fetch 的 cache=True 便捷包装，供 registry/cli 抓元数据用。"""
        return self.fetch(
            url, retries=retries, method=method, data=data, headers=headers, cache=True
        )

    def fetch_chapter(self, url: str, parser, max_pages: int = 10) -> str | None:
        """下载单章（含分页），返回合并后的正文。"""
        from bs4 import BeautifulSoup

        all_text = []
        current_url = url
        page_count = 0

        while current_url and page_count < max_pages:
            page_count += 1
            html = self.fetch(current_url, headers=parser.headers)
            if not html:
                break
            soup = BeautifulSoup(html, "lxml")
            text = parser.parse_content(soup)
            if text:
                all_text.append(text)

            next_url = parser.has_next_page(soup, current_url)
            if not next_url:
                break
            current_url = next_url

        return "\n".join(all_text) if all_text else None

    def download_all(
        self,
        chapters: list[tuple[str, str]],
        parse_fn: Callable[[str], str | None],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[dict[int, tuple[str, str | None]], list[tuple[int, str, str]]]:
        """
        并发下载所有章节，返回 (results, failed)。
        chapters: [(标题, URL), ...]
        parse_fn: 接收章节URL，返回正文或 None。
        results: {idx: (title, content|None)}；failed: [(idx, title, url)]。
        """
        results: dict[int, tuple[str, str | None]] = {}
        failed: list[tuple[int, str, str]] = []

        def worker(idx: int, title: str, url: str):
            content = parse_fn(url)
            if content is None:
                with self.lock:
                    failed.append((idx, title, url))
            return idx, title, content

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            futures = {
                executor.submit(worker, i + 1, t, u): i + 1
                for i, (t, u) in enumerate(chapters)
            }
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                idx, title, content = future.result()
                results[idx] = (title, content)
                completed += 1
                if on_progress and (completed % 50 == 0 or completed == len(chapters)):
                    on_progress(completed, len(chapters))

        # 自动重试失败章节一次
        if failed:
            retry_targets = failed[:]
            failed.clear()
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = {
                    executor.submit(worker, idx, title, url): idx
                    for idx, title, url in retry_targets
                }
                for future in concurrent.futures.as_completed(futures):
                    idx, title, content = future.result()
                    if content is not None:
                        results[idx] = (title, content)

        return results, failed

    def save(
        self,
        novel_name: str,
        author: str,
        chapters: list[tuple[str, str]],
        results: dict[int, tuple[str, str | None]],
        filename: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """按顺序写入 TXT 文件。output_dir 指定时写入子目录（自动创建）。"""
        import os
        import re

        if filename is None:
            filename = f"{novel_name}.txt"
        # 清理 Windows 非法字符和控制字符
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", filename)
        filename = filename.strip(". ")
        if not filename:
            filename = "novel.txt"
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = os.path.join(output_dir, filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"{novel_name}\n作者：{author}\n\n")
            for idx in range(1, len(chapters) + 1):
                title, content = results[idx]
                f.write(f"\n\n{title}\n\n")
                f.write(content if content else "[本章内容获取失败]\n")
        return filename
