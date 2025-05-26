import asyncio
import logging
import re

import discord

from automudae.config.v1 import ClaimPreferences, Config


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

        kakera_match = re.search(r"\*\*([\d,]+)\*\*", embed.description)
        assert kakera_match, embed.description
        self.kakera = int(kakera_match.group(1).replace(",", ""))

        self.is_wished = "Wished by" in self.msg.content

    async def claim(self) -> None:
        if not self.is_wished:
            await self.msg.add_reaction("❤️")
        else:
            await self.click()

    async def kakera_react(self) -> None:
        await self.click()

    async def click(self) -> None:
        button = self.get_action_button()
        if not button:
            return
        await button.click()
    
    def is_wished_by(self, user: discord.ClientUser) -> bool:
        return f"Wished by <@{user.id}>" == self.msg.content

    def get_action_button(self, emoji_name: str = "") -> discord.Button | None:
        if not self.msg.components:
            return None
        for component in self.msg.components:
            if not isinstance(component, discord.ActionRow):
                continue
            for child in component.children:
                if not isinstance(child, discord.Button):
                    continue
                if not child.emoji:
                    continue
                if emoji_name not in child.emoji.name:
                    continue
                return child
        return None

    def is_qualified_using_criteria(self, criteria: ClaimPreferences) -> bool:
        character_qualifies = self.character in criteria.character
        series_qualifies = self.series in criteria.series
        kakera_qualifies = self.kakera >= criteria.minKakera

        return character_qualifies or series_qualifies or kakera_qualifies


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

    async def dequeue_roll_command(self) -> discord.User | discord.Member:
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
        
        reactable = "React with any emoji to claim!" in embed.description
        wished = "Wished by" in msg.content
        return reactable or wished

    async def enqueue_claimable_roll(self, msg: discord.Message):
        async with self.claimable_roll_lock:
            author: discord.user.BaseUser | discord.Member
            if msg.interaction:
                author = msg.interaction.user
            else:
                author = await self.dequeue_roll_command()
            roll = Roll(msg=msg, author=author)
            self.claimable_roll_queue.append(roll)
            return roll

    def is_kakera_reactable_roll(self, msg: discord.Message):
        if not msg.components:
            return False
        for component in msg.components:
            if not isinstance(component, discord.ActionRow):
                continue
            for child in component.children:
                if not isinstance(child, discord.Button):
                    continue
                if not child.emoji:
                    continue
                logger.info(
                    f"Encountered Message with Emoji Component {child.emoji.name}"
                )
                return "kakera" in child.emoji.name
        return False

    async def enqueue_kakera_reactable_roll(self, msg: discord.Message):
        async with self.kakera_reactable_roll_lock:
            author: discord.user.BaseUser | discord.Member
            if msg.interaction:
                author = msg.interaction.user
            else:
                author = await self.dequeue_roll_command()
            roll = Roll(msg=msg, author=author)
            self.kakera_reactable_roll_queue.append(roll)
            return roll
