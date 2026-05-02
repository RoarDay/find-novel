"""下载引擎：HTTP 请求、重试、并发调度、顺序写入。"""

import time
import random
import concurrent.futures
import threading
from typing import Callable
import requests
from .proxy import ProxyPool


class DownloadEngine:
    def __init__(
        self,
        max_workers: int = 5,
        use_proxy: bool = False,
        proxy_test_url: str | None = None,
        delay: tuple[float, float] = (0.1, 0.3),
    ):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self.max_workers = max_workers
        self.delay = delay
        self.use_proxy = use_proxy
        self.proxy_pool = ProxyPool() if use_proxy else None
        self.lock = threading.Lock()

        if use_proxy and proxy_test_url:
            self.proxy_pool.refresh(test_url=proxy_test_url, count=20)
            if self.proxy_pool.is_empty():
                print("[Engine] 无可用代理，已回退到直连模式")
                self.use_proxy = False

    def fetch(self, url: str, retries: int = 3) -> str | None:
        """带代理轮换和指数退避的请求。"""
        for i in range(retries):
            try:
                time.sleep(random.uniform(*self.delay))

                proxies = None
                if self.use_proxy:
                    proxy = self.proxy_pool.get()
                    if proxy:
                        proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

                resp = self.session.get(url, timeout=15, proxies=proxies)
                resp.encoding = "utf-8"
                if resp.status_code == 200:
                    return resp.text
            except Exception:
                time.sleep(0.5 * (i + 1))
        return None

    def download_all(
        self,
        chapters: list[tuple[str, str]],
        parse_fn: Callable[[str], str | None],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict[int, tuple[str, str | None]]:
        """
        并发下载所有章节，返回按索引有序的结果字典。
        chapters: [(标题, URL), ...]
        parse_fn: 接收章节URL，返回正文或 None。
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

        return results, failed

    def save(
        self,
        novel_name: str,
        author: str,
        chapters: list[tuple[str, str]],
        results: dict[int, tuple[str, str | None]],
        filename: str | None = None,
    ) -> str:
        """按顺序写入 TXT 文件。"""
        if filename is None:
            filename = f"{novel_name}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"{novel_name}\n作者：{author}\n\n")
            for idx in range(1, len(chapters) + 1):
                title, content = results[idx]
                f.write(f"\n\n{title}\n\n")
                f.write(content if content else "[本章内容获取失败]\n")
        return filename
