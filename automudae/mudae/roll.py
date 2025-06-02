import logging
import re
from asyncio import Queue
from typing import Literal, get_args

import discord
from pydantic import BaseModel

from automudae.config import ClaimCriteria

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MUDAE_TIMEOUT_SEC = 0.5
MudaeRollOwner = (
    discord.User | discord.ClientUser | discord.Member | discord.user.BaseUser
)
MudaeRollCommandType = Literal["$wg", "$wa", "$w", "$wx"]


class MudaeRollCommand(BaseModel):

    command: MudaeRollCommandType
    owner: MudaeRollOwner
    message: discord.Message

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}("
            f"owner={self.owner.name!r}, "
            f"command={self.command!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def create(cls, message: discord.Message):
        if message.content not in get_args(MudaeRollCommandType):
            logger.debug(f"Message is not in {get_args(MudaeRollCommandType)}")
            return None

        return MudaeRollCommand(
            command=message.content,  # type: ignore
            owner=message.author,
            message=message,
        )


MudaeRollCommands = Queue[MudaeRollCommand]


class MudaeFailedRollCommand(BaseModel):
    owner: MudaeRollOwner

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:

        return f"{self.__class__.__name__}(owner={self.owner.name!r})"

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    async def create(
        cls, message: discord.Message, roll_commands_queue: MudaeRollCommands
    ):
        clean_msg_content = discord.utils.remove_markdown(message.content)
        if not re.findall(
            r"(.+), the roulette is limited to (\d+) uses per hour. (\d+) min left.",
            clean_msg_content,
        ):
            return None
        owner: MudaeRollOwner
        if message.interaction:
            owner = message.interaction.user
        else:
            while True:
                roll_command = await roll_commands_queue.get()
                try:
                    reply_interval = (
                        message.created_at - roll_command.message.created_at
                    ).total_seconds()
                    if reply_interval <= MUDAE_TIMEOUT_SEC:
                        break
                finally:
                    roll_commands_queue.task_done()
            owner = roll_command.owner
        return MudaeFailedRollCommand(owner=owner)


class MudaeClaimableRoll(BaseModel):

    owner: MudaeRollOwner
    message: discord.Message
    character: str
    series: str
    kakera_value: int
    wished_by: MudaeRollOwner | None

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:
        if self.wished_by:
            wished_by = self.wished_by.name
        else:
            wished_by = None

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
            return None
        elif not self.message.components:
            return None
        for component in self.message.components:
            if not isinstance(component, discord.ActionRow):
                continue
            for child in component.children:
                if not isinstance(child, discord.Button):
                    continue
                if not child.emoji:
                    continue
                await child.click()

    def is_qualified(self, criteria: ClaimCriteria, user: MudaeRollOwner) -> bool:
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
    async def create(
        cls, message: discord.Message, roll_commands_queue: Queue[MudaeRollCommand]
    ):
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
                "Not a Mudae Roll: No Series Name or No Kakera Value. Maybe use $togglekakerarolls?"
            )
            return None

        series_name = str(series_kakera_match.group(1))
        series_name = re.sub(r"[\r\n]+", " ", series_name)
        series_name = re.sub(r"\s+", " ", series_name)
        series_name = series_name.strip()

        kakera_value_str = str(series_kakera_match.group(2))
        kakera_value_str = re.sub(",", "", kakera_value_str)
        kakera_value = int(kakera_value_str)

        msg_is_wished_by = re.search(r"Wished by <@([\d]+)>", message.content)
        wished_by = None
        if msg_is_wished_by and message.guild:
            wished_by = await message.guild.fetch_member(int(msg_is_wished_by.group(1)))

        owner: MudaeRollOwner
        if message.interaction:
            owner = message.interaction.user
        else:
            while True:
                roll_command = await roll_commands_queue.get()
                try:
                    reply_interval = (
                        message.created_at - roll_command.message.created_at
                    ).total_seconds()
                    if reply_interval <= MUDAE_TIMEOUT_SEC:
                        break
                finally:
                    roll_commands_queue.task_done()
            owner = roll_command.owner

        return MudaeClaimableRoll(
            owner=owner,
            message=message,
            character=embed.author.name,
            series=series_name,
            kakera_value=kakera_value,
            wished_by=wished_by,
        )


MudaeClaimableRolls = Queue[MudaeClaimableRoll]


class MudaeKakeraRoll(BaseModel):

    owner: MudaeRollOwner
    message: discord.Message
    buttons: list[discord.Button]

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"owner={self.owner.name!r}, "
            f"buttons={[button.emoji.name for button in self.buttons if button.emoji]})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    async def kakera_react(self) -> None:
        for button in self.buttons:
            await button.click()

    @classmethod
    async def create(
        cls, message: discord.Message, roll_commands_queue: Queue[MudaeRollCommand]
    ):
        if not message.components:
            return None

        buttons: list[discord.Button] = []
        for component in message.components:
            if not isinstance(component, discord.ActionRow):
                continue
            for child in component.children:
                if not isinstance(child, discord.Button):
                    continue
                if not child.emoji:
                    continue
                if "kakera" not in child.emoji.name:
                    continue
                buttons.append(child)
        if len(buttons) == 0:
            return None

        owner: MudaeRollOwner
        if message.interaction:
            owner = message.interaction.user
        else:
            while True:
                roll_command = await roll_commands_queue.get()
                try:
                    reply_interval = (
                        message.created_at - roll_command.message.created_at
                    ).total_seconds()
                    if reply_interval <= MUDAE_TIMEOUT_SEC:
                        break
                finally:
                    roll_commands_queue.task_done()
            owner = roll_command.owner

        return MudaeKakeraRoll(owner=owner, message=message, buttons=buttons)


MudaeKakeraRolls = Queue[MudaeKakeraRoll]
