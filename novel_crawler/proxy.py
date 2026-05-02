"""代理池：自动获取、测试、维护可用代理列表。"""

import random
import threading
import concurrent.futures
import requests


class ProxyPool:
    def __init__(self):
        self.proxies: list[str] = []
        self.lock = threading.Lock()

    def fetch(self, count: int = 20, country_code: str = "CN") -> list[str]:
        """从免费 API 获取原始代理列表。"""
        url = (
            f"https://proxy.scdn.io/api/get_proxy.php"
            f"?protocol=http&count={count}&country_code={country_code}"
        )
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            return data["data"]["proxies"]
        except Exception:
            return []

    def _test_one(self, proxy: str, test_url: str) -> str | None:
        """测试单个代理是否可用。"""
        try:
            proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
            resp = requests.get(
                test_url,
                proxies=proxies,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                return proxy
        except Exception:
            pass
        return None

    def refresh(self, test_url: str, count: int = 20) -> list[str]:
        """刷新代理池：获取一批并测试可用性。"""
        raw = self.fetch(count)
        valid: list[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._test_one, p, test_url): p for p in raw}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    valid.append(result)

        with self.lock:
            self.proxies = valid
        return valid

    def get(self) -> str | None:
        """随机取一个可用代理，没有则返回 None。"""
        with self.lock:
            if self.proxies:
                return random.choice(self.proxies)
        return None

    def is_empty(self) -> bool:
        with self.lock:
            return len(self.proxies) == 0
