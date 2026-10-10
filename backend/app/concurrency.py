import asyncio
from contextlib import asynccontextmanager

from .errors import Busy


class StageLimiter:
    """Bounds simultaneous calls to one model stage; waiting too long -> 503 BUSY."""

    def __init__(self, limit: int, queue_timeout_s: float, name: str):
        self._sem = asyncio.Semaphore(max(1, limit))
        self._timeout = queue_timeout_s
        self._name = name

    @asynccontextmanager
    async def slot(self):
        try:
            await asyncio.wait_for(self._sem.acquire(), self._timeout)
        except asyncio.TimeoutError:
            raise Busy(f"The {self._name} service is busy. Please try again in a moment.")
        try:
            yield
        finally:
            self._sem.release()
