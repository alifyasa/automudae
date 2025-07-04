# pylint: disable=R0903
import asyncio
import logging
import re
from typing import Self

import discord
from pydantic import BaseModel, Field

from automudae.mudae.helper.concurrency import EventDebugger, LockDebugger

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

MudaeTimerOwner = (
    discord.User | discord.ClientUser | discord.Member | discord.user.BaseUser
)


class MudaeTimerStatus(BaseModel):

    can_claim: bool = False
    rolls_available: int = 0
    can_kakera_react: bool = False
    next_hour_is_reset: bool = False
    kakera_power: int = 0

    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)
    roll_is_available: asyncio.Event = Field(default_factory=asyncio.Event)

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"can_claim={self.can_claim}, "
            f"rolls_available={self.rolls_available}, "
            f"can_kakera_react={self.can_kakera_react}, "
            f"next_hour_is_reset={self.next_hour_is_reset}, "
            f"kakera_power={self.kakera_power})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def debug_lock(self, name: str) -> LockDebugger:
        return LockDebugger(self.lock, name)

    async def wait_for_rolls(self) -> None:
        event_debugger = EventDebugger(self.roll_is_available, "Roll is Available")
        await event_debugger.wait()

    @classmethod
    async def create(cls, message: discord.Message, current_user: MudaeTimerOwner):
        clean_msg = discord.utils.remove_markdown(message.content)

        is_my_message = clean_msg.startswith(current_user.name)
        if not is_my_message:
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

        kakera_power = re.search(r"(\d+)%", clean_msg)
        if not kakera_power:
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
            rolls_available=(
                int(rolls_pattern.group(1)) if rolls_pattern.group(1) else 0
            ),
            can_kakera_react=kakera_pattern.group(1) == "can",
            next_hour_is_reset=next_claim_reset_in_minutes <= 60,
            kakera_power=int(kakera_power.group(1)) if kakera_power.group(1) else 0,
        )

    async def update(self, new_timer_status: Self) -> None:
        async with self.debug_lock("update"):
            self.can_claim = new_timer_status.can_claim
            self.rolls_available = new_timer_status.rolls_available
            self.can_kakera_react = new_timer_status.can_kakera_react
            self.next_hour_is_reset = new_timer_status.next_hour_is_reset
            self.kakera_power = new_timer_status.kakera_power

            if self.rolls_available > 0:
                self.roll_is_available.set()
            else:
                self.roll_is_available.clear()
