# pylint: disable=R0903
import logging
from typing import Literal

import discord
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MUDAE_TIMEOUT_SEC = 0.5
MudaeRollOwner = (
    discord.User | discord.ClientUser | discord.Member | discord.user.BaseUser
)
MudaeRollCommandType = Literal["$wg", "$wa", "$w", "$wx"]


class MudaeRoll(BaseModel):
    owner: MudaeRollOwner
    message: discord.Message

    class Config:
        arbitrary_types_allowed = True
