import asyncio
import logging
import re
from typing import Self

import discord
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

MudaeTimerOwner = (
    discord.User | discord.ClientUser | discord.Member | discord.user.BaseUser
)


class MudaeTimerStatus(BaseModel):

    can_claim: bool = False
    rolls_left: int = 0
    can_kakera_react: bool = False
    next_hour_is_reset: bool = False

    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"can_claim={self.can_claim}, "
            f"rolls_left={self.rolls_left}, "
            f"can_kakera_react={self.can_kakera_react}, "
            f"next_hour_is_reset={self.next_hour_is_reset})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    async def create(cls, message: discord.Message, current_user: MudaeTimerOwner):
        clean_msg = discord.utils.remove_markdown(message.content)

        is_my_message = clean_msg.startswith(current_user.name)
        is_mudae_timer_list_msg = "=> $tuarrange" in clean_msg
        if not (is_mudae_timer_list_msg and is_my_message):
            return None

        claim_pattern = re.search(r"you (can|can\'t) claim", clean_msg)
        if not claim_pattern:
            return None

        rolls_pattern = re.search(r"You have (\d+) rolls? left", clean_msg)
        if not rolls_pattern:
            return None

        kakera_pattern = re.search(r"You (can|can\'t) react to kakera", clean_msg)
        if not kakera_pattern:
            return None

        claim_reset_pattern = re.search(
            r"(?:The next claim reset is in|you can't claim for another)\s+(?:(\d+)h\s*)?(\d+)\s*min",  # pylint: disable=C0301
            clean_msg,
        )
        if not claim_reset_pattern:
            return None

        claim_reset_hours = (
            int(claim_reset_pattern.group(1)) if claim_reset_pattern.group(1) else 0
        )
        claim_reset_minutes = (
            int(claim_reset_pattern.group(2)) if claim_reset_pattern.group(2) else 0
        )
        next_claim_reset_in_minutes = claim_reset_hours * 60 + claim_reset_minutes

        return MudaeTimerStatus(
            can_claim=claim_pattern.group(1) == "can",
            rolls_left=int(rolls_pattern.group(1)) if rolls_pattern.group(1) else 0,
            can_kakera_react=kakera_pattern.group(1) == "can",
            next_hour_is_reset=next_claim_reset_in_minutes <= 60,
        )

    async def update(self, new_timer_status: Self) -> None:
        async with self.lock:
            self.can_claim = new_timer_status.can_claim
            self.rolls_left = new_timer_status.rolls_left
            self.can_kakera_react = new_timer_status.can_kakera_react
            self.next_hour_is_reset = new_timer_status.next_hour_is_reset
