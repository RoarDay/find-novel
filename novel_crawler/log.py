"""日志配置：写 stderr，不污染 stdout（保证 JSON 出口干净）。"""

import logging
import sys

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s %(message)s"))
_root = logging.getLogger("novel_crawler")
_root.addHandler(_handler)
_root.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """取带 `novel_crawler.` 前缀的 logger。"""
    return _root.getChild(name)
