"""解析器注册中心：根据 URL 自动匹配对应的站点解析器。"""

import os
import importlib
import inspect
from urllib.parse import urlparse
from .base import BaseParser


class ParserRegistry:
    def __init__(self):
        self._parsers: dict[str, BaseParser] = {}
        self._auto_register()

    def _auto_register(self):
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
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseParser) and obj is not BaseParser:
                        instance = obj()
                        self.register(instance)
            except Exception as e:
                print(f"[Registry] 加载 {module_name} 失败: {e}")

    def register(self, parser: BaseParser):
        self._parsers[parser.domain] = parser

    def get_parser(self, url: str) -> BaseParser:
        domain = urlparse(url).netloc
        for key, parser in self._parsers.items():
            if key in domain:
                return parser
        raise ValueError(f"未找到支持该域名的解析器: {domain}")

    def list_supported(self) -> list[str]:
        return list(self._parsers.keys())
