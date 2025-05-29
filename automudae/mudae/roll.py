import asyncio
import re
from queue import Queue
from typing import Literal, get_args

import discord
from pydantic import BaseModel, Field

type MudaeRollOwner = discord.User | discord.ClientUser | discord.Member


class NotMudaeRollException(BaseException):
    pass


class MudaeRoll(BaseModel):

    owner: MudaeRollOwner
    message: discord.Message
    character: str
    series: str
    kakera_value: int
    is_wished: bool
    wished_by: MudaeRollOwner | None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    async def create(cls, message: discord.Message, roll_owner: MudaeRollOwner):
        embed = message.embeds[0]
        if not embed.author.name:
            raise NotMudaeRollException("Not a Mudae Roll: No Character Name")

        if not embed.description:
            raise NotMudaeRollException("Not a Mudae Roll: No Description")
        clean_desc = discord.utils.remove_markdown(embed.description)

        series_match = re.search(r"(.+)\n", clean_desc)
        if not series_match:
            raise NotMudaeRollException("Not a Mudae Roll: No Series Name")

        kakera_match = re.search(r"([\d,]+)[\s]*<:kakera:[\d]+>", clean_desc)
        if not kakera_match:
            raise NotMudaeRollException("Not a Mudae Roll: No Kakera Value")

        msg_is_wished_by = re.search(r"Wished by <@([\d]+)>", message.content)
        wished_by = None
        if msg_is_wished_by and message.guild:
            wished_by = await message.guild.fetch_member(int(msg_is_wished_by.group(1)))

        return MudaeRoll(
            owner=roll_owner,
            message=message,
            character=embed.author.name,
            series=str(series_match.group(1)),
            kakera_value=int(kakera_match.group(1).replace(",", "")),
            is_wished=bool(msg_is_wished_by),
            wished_by=wished_by,
        )


class MudaeRolls(BaseModel):
    rolls: list[MudaeRoll] = Field(default_factory=list[MudaeRoll])
    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)

    class Config:
        arbitrary_types_allowed = True


type MudaeRollCommandType = Literal["$wg", "$wa", "$w", "$wx"]


class NotMudaeRollCommandException(BaseException):
    pass


class MudaeRollCommand(BaseModel):

    command: MudaeRollCommandType
    author: MudaeRollOwner
    message: discord.Message

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def create(cls, message: discord.Message):
        if message.content not in get_args(MudaeRollCommandType):
            raise NotMudaeRollCommandException(
                f"{message.content} is not in {get_args(MudaeRollCommandType)}"
            )

        return MudaeRollCommand(
            command=message.content,  # type: ignore
            author=message.author,
            message=message,
        )


class MudaeRollCommandQueue(BaseModel):
    queue: Queue[MudaeRollCommand] = Field(default_factory=Queue[MudaeRollCommand])
    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)

    class Config:
        arbitrary_types_allowed = True
