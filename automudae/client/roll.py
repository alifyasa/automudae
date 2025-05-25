from dataclasses import dataclass
import discord
import asyncio
import logging
from automudae.config.v1 import Config

@dataclass
class Roll:
    id: str
    character: str
    series: str
    kakera: int
    msg: discord.Message

logger = logging.getLogger(__name__)
class MudaeRollMixin:
    def __init__(self) -> None:
        super().__init__()
        self.rolls: list[Roll] = []

        self.roll_command_queue: list[discord.User | discord.Member] = []
        self.roll_command_lock = asyncio.Lock()

        logger.info("Initialization Complete")
    
    def is_roll_command(self, msg: discord.Message):
        return msg.content.strip() in ["$wg","$wa","$w","$wx"]
    
    async def enqueue_roll_command(self, msg: discord.Message, config: Config):
        if msg.channel.id != config.discord.channelId: return False
        async with self.roll_command_lock:
            self.roll_command_queue.append(msg.author)
