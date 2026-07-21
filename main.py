#!/usr/bin/env python3
"""兼容入口：python main.py（等价于 novel-crawler 命令）。

实际逻辑在 novel_crawler/cli.py。保留此文件是为了：
  - 旧用法 `python main.py ...` 不破坏
  - find-novel skill 调 `python main.py ...` 不用改
"""

from novel_crawler.cli import main

if __name__ == "__main__":
    main()
