import asyncio

import discord
from pydantic import BaseModel, Field

type MudaeRollOwner = discord.User | discord.ClientUser | discord.Member


class MudaeRoll(BaseModel):

    owner: MudaeRollOwner
    message: discord.Message
    character: str
    series: str
    kakera_value: int
    is_wished: bool
    wished_by: MudaeRollOwner | None

    @classmethod
    def from_message(cls, message: discord.Message):
        return MudaeRoll(
            owner=message.author,
            message=message,
            character="",
            series="",
            kakera_value=0,
            is_wished=False,
            wished_by=None,
        )


class MudaeRollQueue(BaseModel):
    queue: list[MudaeRoll] = Field(default_factory=list[MudaeRoll])
    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)
