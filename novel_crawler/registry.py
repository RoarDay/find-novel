"""解析器注册中心：根据 URL 自动匹配对应的站点解析器。"""

import concurrent.futures
import importlib
import inspect
import os
from collections.abc import Callable
from urllib.parse import urlparse

from .base import BaseParser, SearchResult
from .log import get_logger

log = get_logger("registry")


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}
        self._auto_register()

    def _auto_register(self) -> None:
        """自动导入 sites 目录下所有模块，注册解析器实例。"""
        sites_dir = os.path.join(os.path.dirname(__file__), 'sites')
        if not os.path.isdir(sites_dir):
            return

        for filename in sorted(os.listdir(sites_dir)):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue
            module_name = f"novel_crawler.sites.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                for _name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseParser) and obj is not BaseParser:
                        instance = obj()
                        self.register(instance)
            except Exception as e:
                log.warning("加载 %s 失败: %s", module_name, e)

    def register(self, parser: BaseParser) -> None:
        self._parsers[parser.domain] = parser

    def get_parser(self, url: str) -> BaseParser:
        domain = urlparse(url).netloc
        for key, parser in self._parsers.items():
            if domain == key or domain.endswith("." + key):
                return parser
        raise ValueError(f"未找到支持该域名的解析器: {domain}")

    def list_supported(self) -> list[str]:
        return list(self._parsers.keys())

    def get_by_source(self, domain: str) -> BaseParser:
        """按域名取 parser 实例（支持子域）。"""
        for key, parser in self._parsers.items():
            if domain == key or domain.endswith("." + key):
                return parser
        raise ValueError(f"未找到该域名解析器: {domain}")

    def search_all(
        self, keyword: str, fetch: Callable[..., str | None]
    ) -> list[SearchResult]:
        """并发聚合搜索所有已注册站点，单站失败不影响其它。

        结果按站点注册顺序聚合（稳定）；线程数 = min(8, 站点数)。
        requests.Session 线程安全（download_all 已用线程池验证）。
        """
        parsers = list(self._parsers.values())

        def run(parser: BaseParser) -> list[SearchResult]:
            try:
                return parser.search(keyword, fetch)
            except Exception as e:
                log.warning("%s 搜索失败: %s", parser.domain, e)
                return []

        all_results: list[SearchResult] = []
        if not parsers:
            return all_results
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, len(parsers))
        ) as executor:
            for res in executor.map(run, parsers):
                all_results.extend(res)
        return all_results
