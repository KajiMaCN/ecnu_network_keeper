from __future__ import annotations

import math
import socket
from random import shuffle
from typing import Callable, Iterable
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_TEST_URLS = (
    "https://www.baidu.com/",
    "https://www.taobao.com/",
    "https://www.amazon.cn/",
    "https://www.jd.com/",
    "https://www.bing.com/",
    "http://www.cnki.net/",
    "https://www.qq.com/",
    "https://www.csdn.net/",
    "https://gitee.com/",
    "https://www.zhihu.com/",
    "https://www.aliyun.com/",
    "https://arxiv.org/",
)


class ConnectivityChecker:
    """Check whether the internet is reachable through multiple probe URLs."""

    def __init__(
        self,
        test_urls: Iterable[str] = DEFAULT_TEST_URLS,
        *,
        pass_ratio: float = 0.6,
        timeout: float = 1.0,
        opener: Callable[[str, float], object] | None = None,
        shuffle_fn: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.test_urls = tuple(test_urls)
        self.pass_ratio = pass_ratio
        self.timeout = timeout
        self._opener = opener or self._default_open
        self._shuffle_fn = shuffle_fn or shuffle

    def is_online(self, *, verbose: bool = False) -> bool:
        if not self.test_urls:
            raise ValueError("At least one test URL is required.")

        urls = list(self.test_urls)
        self._shuffle_fn(urls)

        required_successes = max(1, math.ceil(self.pass_ratio * len(urls)))
        allowed_failures = len(urls) - required_successes
        successes = 0
        failures = 0

        if verbose:
            print("Checking internet connection...")

        for url in urls:
            if self._can_open_url(url):
                successes += 1
                if successes >= required_successes:
                    return True
            else:
                failures += 1
                if failures > allowed_failures:
                    return False

        return successes >= required_successes

    def _can_open_url(self, url: str) -> bool:
        try:
            self._opener(url, self.timeout)
        except (socket.timeout, URLError, ConnectionResetError, OSError):
            return False
        return True

    @staticmethod
    def _default_open(url: str, timeout: float) -> object:
        return urlopen(url, timeout=timeout)
