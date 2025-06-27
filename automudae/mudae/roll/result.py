# pylint: disable=R0903
import logging
import re
from asyncio import Queue
from datetime import datetime

import discord

from automudae.config import Criteria
from automudae.mudae.helper.common import get_buttons
from automudae.mudae.roll import MUDAE_TIMEOUT_SEC, MudaeRoll, MudaeRollOwner
from automudae.mudae.roll.command import MudaeRollCommand
from automudae.mudae.roll.helper import get_roll_command_from_roll_message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def get_roll_command(
    queue: Queue[MudaeRollCommand], message_time: datetime
) -> MudaeRollCommand:
    while True:
        roll_command = await queue.get()
        try:
            if (
                message_time - roll_command.message.created_at
            ).total_seconds() <= MUDAE_TIMEOUT_SEC:
                return roll_command
        finally:
            queue.task_done()


class MudaeClaimableRollResult(MudaeRoll):

    character: str
    series: str
    kakera_value: int
    wished_by: MudaeRollOwner | None = None

    def __repr__(self) -> str:
        wished_by = self.wished_by.name if self.wished_by else None
        return (
            f"{self.__class__.__name__}("
            f"owner={self.owner.name!r}, "
            f"character={self.character!r}, "
            f"series={self.series!r}, "
            f"kakera_value={self.kakera_value}, "
            f"wished_by={wished_by!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    async def claim(self) -> None:
        if self.wished_by is None:
            await self.message.add_reaction("❤️")
            return
        if not self.message.components:
            return
        for button in get_buttons(self.message):
            await button.click()

    def is_qualified(self, criteria: Criteria, user: MudaeRollOwner) -> bool:
        character_qualify = self.character in criteria.character
        series_qualify = self.series in criteria.series
        kakera_qualify = self.kakera_value >= criteria.minKakera
        wish_qualify = (
            criteria.wish
            and self.wished_by is not None
            and self.wished_by.id == user.id
        )
        return character_qualify or series_qualify or kakera_qualify or wish_qualify

    @classmethod
    async def create(cls, message: discord.Message):
        if not message.embeds:
            logger.debug("Not Mudae Roll: No Embeds")
            return None

        embed = message.embeds[0]
        if not embed.description:
            logger.debug("Not Mudae Roll: No Embed Description")
            return None

        reactable = "React with any emoji to claim!" in embed.description
        wished = "Wished by" in message.content
        if not (reactable or wished):
            logger.debug("Not a Mudae Roll: Not Claimable nor Wished")
            return None

        if not embed.author.name:
            logger.debug("Not a Mudae Roll: No Character Name")
            return None

        clean_desc = discord.utils.remove_markdown(embed.description)

        series_kakera_match = re.search(
            r"([\s\S]+)\n([\d,]+)[\s]*<:kakera:[\d]+>", clean_desc
        )
        if not series_kakera_match:
            logger.error(
                "Not a Mudae Roll: No Series Name or No Kakera Value. "
                "Maybe use $togglekakerarolls?"
            )
            return None

        series_name = (
            str(series_kakera_match.group(1))
            .replace("\r\n", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .strip()
        )
        series_name = re.sub(r"\s+", " ", series_name)

        kakera_value_str = str(series_kakera_match.group(2)).replace(",", "")

        msg_is_wished_by = re.search(r"Wished by <@([\d]+)>", message.content)
        wished_by: MudaeRollOwner | None
        if msg_is_wished_by and message.guild:
            wished_by = await message.guild.fetch_member(int(msg_is_wished_by.group(1)))
        else:
            wished_by = None

        owner: MudaeRollOwner
        if message.interaction:
            owner = message.interaction.user
        else:
            roll_command = await get_roll_command_from_roll_message(message)
            owner = roll_command.owner

        return MudaeClaimableRollResult(
            owner=owner,
            message=message,
            character=embed.author.name,
            series=series_name,
            kakera_value=int(kakera_value_str),
            wished_by=wished_by,
        )


KAKERA_TYPES = {
    "kakeraP": 100,
    "kakera": 101,
    "kakeraT": 171,
    "kakeraG": 251,
    "kakeraY": 401,
    "kakeraO": 701,
    "kakeraR": 1401,
    "kakeraW": 3001,
    "kakeraL": 500,
}


class MudaeKakeraRollResult(MudaeRoll):

    buttons: list[discord.Button]
    kakera_value: int

    def __repr__(self) -> str:
        button_names = [button.emoji.name for button in self.buttons if button.emoji]
        return (
            f"{self.__class__.__name__}("
            f"owner={self.owner.name!r}, "
            f"buttons={button_names}, "
            f"kakera_value={self.kakera_value})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    async def kakera_react(self) -> None:
        for button in self.buttons:
            await button.click()

    @classmethod
    async def create(cls, message: discord.Message):
        if not message.components:
            return None

        buttons = [
            button
            for button in get_buttons(message)
            if button.emoji and button.emoji.name in KAKERA_TYPES
        ]
        if len(buttons) == 0:
            return None

        owner: MudaeRollOwner
        if message.interaction:
            owner = message.interaction.user
        else:
            roll_command = await get_roll_command_from_roll_message(message)
            owner = roll_command.owner

        return MudaeKakeraRollResult(
            owner=owner,
            message=message,
            buttons=buttons,
            kakera_value=sum(
                KAKERA_TYPES[button.emoji.name]
                for button in buttons
                if button.emoji is not None
            ),
        )


MudaeRollResult = MudaeClaimableRollResult | MudaeKakeraRollResult
