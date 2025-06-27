# pylint: disable=R0903
import logging
from typing import get_args

import discord

from automudae.mudae.roll import MudaeRoll, MudaeRollCommandType

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MudaeRollCommand(MudaeRoll):

    command: MudaeRollCommandType

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
            logger.debug("Message is not in %s", get_args(MudaeRollCommandType))
            return None

        return MudaeRollCommand(
            command=message.content,  # type: ignore
            owner=message.author,
            message=message,
        )
