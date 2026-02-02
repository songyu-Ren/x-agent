import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], max_attempts: int = 3, base_delay_s: float = 0.5) -> T:
    last_exc: Exception | None = None
    delay = base_delay_s
    for _ in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            time.sleep(delay)
            delay *= 2
    raise last_exc or RuntimeError("retry_failed")

