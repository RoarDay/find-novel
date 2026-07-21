"""集中常量：路径、UA、延迟、DB、开关。"""

DOWNLOAD_DIR = "novels"  # 小说下载目录（已 .gitignore）
DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DEFAULT_DELAY = (0.1, 0.3)  # (min, max) 秒
DB_PATH = "novels/novel-crawler.db"  # SQLite：books/search_history/booklists
enable_history: bool = True  # --search 是否记录找书历史 + 入 books 表
