import asyncio
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LockDebugger:
    def __init__(self, lock: asyncio.Lock, name: str) -> None:
        self.lock = lock
        self.name = name

    async def __aenter__(self) -> None:
        await self.lock.acquire()
        logger.debug("Obtained Lock (%s)", self.name)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        self.lock.release()
        logger.debug("Released Lock (%s)", self.name)


class EventDebugger:
    def __init__(self, event: asyncio.Event, name: str) -> None:
        self.event = event
        self.name = name

    async def wait(self) -> None:
        logger.debug("Waiting for Event: %s", self.name)
        await self.event.wait()
        logger.debug("Obtained Event: %s", self.name)
