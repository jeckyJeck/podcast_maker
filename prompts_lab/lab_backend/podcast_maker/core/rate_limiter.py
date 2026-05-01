import time
from collections import deque
from threading import Lock


class RateLimiter:
    def __init__(self, max_requests: int, period_seconds: int):
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than 0")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be greater than 0")

        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self._request_timestamps = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        while True:
            sleep_seconds = 0.0
            now = time.time()

            with self._lock:
                while self._request_timestamps and now - self._request_timestamps[0] >= self.period_seconds:
                    self._request_timestamps.popleft()

                if len(self._request_timestamps) < self.max_requests:
                    self._request_timestamps.append(now)
                    return

                oldest_timestamp = self._request_timestamps[0]
                sleep_seconds = self.period_seconds - (now - oldest_timestamp)

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)