import asyncio
import logging
import re

import discord

from automudae.config.v1 import Config


class Roll:
    def __init__(
        self,
        msg: discord.Message,
        author: discord.User | discord.Member | discord.user.BaseUser,
    ) -> None:
        self.msg = msg
        self.author = author

        embed = msg.embeds[0]

        assert embed.author.name
        self.character = embed.author.name

        assert embed.description
        series_match = re.search(r"(.+)\n", embed.description)
        assert series_match, embed.description
        self.series = str(series_match.group(1))

        kakera_match = re.search(r"\*\*(\d+)\*\*", embed.description)
        assert kakera_match, embed.description
        self.kakera = int(kakera_match.group(1))

    async def claim(self):
        await self.msg.add_reaction("❤️")
    
    async def kakera_react(self):
        if not self.msg.components: return False
        for component in self.msg.components:
            if component.type != discord.ComponentType.button: continue
            if not component.emoji: continue
            if "kakera" not in component.emoji.name: continue
            await component.click()
        return False


logger = logging.getLogger(__name__)


class MudaeRollMixin:
    def __init__(self) -> None:
        super().__init__()

        self.roll_command_queue: list[discord.User | discord.Member] = []
        self.roll_command_lock = asyncio.Lock()

        self.claimable_roll_queue: list[Roll] = []
        self.claimable_roll_lock = asyncio.Lock()

        self.kakera_reactable_roll_queue: list[Roll] = []
        self.kakera_reactable_roll_lock = asyncio.Lock()

        logger.info("Initialization Complete")

    def is_roll_command(self, msg: discord.Message):
        return msg.content.strip() in ["$wg", "$wa", "$w", "$wx"]

    async def enqueue_roll_command(self, msg: discord.Message, config: Config):
        if msg.channel.id != config.discord.channelId:
            return False
        async with self.roll_command_lock:
            self.roll_command_queue.append(msg.author)

    def is_failed_roll_command(self, msg: discord.Message):
        clean_msg = discord.utils.remove_markdown(msg.content)
        return "the roulette is limited" in clean_msg

    async def dequeue_roll_command(self):
        async with self.roll_command_lock:
            return self.roll_command_queue.pop(0)

    def is_claimable_roll(self, msg: discord.Message):
        if len(msg.embeds) == 0:
            return False
        embed = msg.embeds[0]
        if not embed.author.name:
            return False
        if not embed.description:
            return False
        return "React with any emoji to claim!" in embed.description

    async def enqueue_claimable_roll(self, msg: discord.Message):
        async with self.claimable_roll_lock:
            if msg.interaction:
                author = msg.interaction.user
            else:
                author = await self.dequeue_roll_command()
            roll = Roll(msg=msg, author=author)
            self.claimable_roll_queue.append(roll)
            return roll

    def is_kakera_reactable_roll(self, msg: discord.Message):
        if not msg.components: return False
        for component in msg.components:
            if component.type != discord.ComponentType.button: continue
            if not component.emoji: continue
            logger.info(f"Encountered Message with Emoji Component {component.emoji.name}")
            return "kakera" not in component.emoji.name
        return False

    async def enqueue_kakera_reactable_roll(self, msg: discord.Message):
        async with self.kakera_reactable_roll_lock:
            if msg.interaction:
                author = msg.interaction.user
            else:
                author = await self.dequeue_roll_command()
            roll = Roll(msg=msg, author=author)
            self.kakera_reactable_roll_queue.append(roll)
            return roll
