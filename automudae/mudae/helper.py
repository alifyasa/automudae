import asyncio
import discord
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_buttons(message: discord.Message):
    buttons: list[discord.Button] = []
    for component in message.components:
        if not isinstance(component, discord.ActionRow):
            continue
        for child in component.children:
            if not isinstance(child, discord.Button):
                continue
            if not child.emoji:
                continue
            buttons.append(child)
    return buttons


class LockDebugger:
    def __init__(self, lock: asyncio.Lock, name: str) -> None:
        self.lock = lock
        self.name = name

    async def __aenter__(self) -> None:
        await self.lock.acquire()
        logger.debug("Obtained Lock (%s)", self.name)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.lock.release()
        logger.debug("Released Lock (%s)", self.name)
