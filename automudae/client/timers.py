import asyncio
import logging
import re

import discord

from automudae.config.v1 import Config

logger = logging.getLogger(__name__)


class MudaeTimerMixin:
    def __init__(self) -> None:
        super().__init__()
        self.timer_lock = asyncio.Lock()
        self.can_claim = False
        self.can_react_to_kakera = False
        self.rolls_left = 0
        self.next_hour_is_claim_reset = False
        logger.info("Initialization Complete")

    def is_mudae_timer_list_msg(
        self, msg: discord.Message, user: discord.ClientUser | None, config: Config
    ):
        if not user:
            return False
        if msg.channel.id != config.discord.channelId:
            return False
        if msg.author.id != config.discord.mudaeBotId:
            return False

        clean_msg = discord.utils.remove_markdown(msg.content)
        is_my_message = clean_msg.startswith(user.display_name)
        is_mudae_timer_list_msg = "=> $tuarrange" in clean_msg
        return is_my_message and is_mudae_timer_list_msg

    async def update_timer(self, msg: discord.Message):
        async with self.timer_lock:
            clean_msg = discord.utils.remove_markdown(msg.content)

            claim_pattern = re.search(r"you (can|can\'t) claim", clean_msg)
            self.can_claim = bool(claim_pattern and claim_pattern.group(1) == "can")

            rolls_pattern = re.search(r"You have (\d+) rolls? left", clean_msg)
            self.rolls_left = bool(rolls_pattern and int(rolls_pattern.group(1)))

            kakera_pattern = re.search(r"You (can|can\'t) react to kakera", clean_msg)
            self.can_react_to_kakera = bool(
                kakera_pattern and kakera_pattern.group(1) == "can"
            )

            claim_reset_pattern = re.search(
                r"(?:The next claim reset is in|you can't claim for another)\s+(?:(\d+)h\s*)?(\d+)\s*min", clean_msg
            )
            assert claim_reset_pattern
            claim_reset_hours = (
                int(claim_reset_pattern.group(1)) if claim_reset_pattern.group(1) else 0
            )
            claim_reset_minutes = (
                int(claim_reset_pattern.group(2)) if claim_reset_pattern.group(2) else 0
            )
            next_claim_reset_in_minutes = claim_reset_hours * 60 + claim_reset_minutes
            self.next_hour_is_claim_reset = next_claim_reset_in_minutes <= 60
            logger.info(f"[Claim: {self.can_claim}] [Kakera React: {self.can_react_to_kakera}] [Rolls: {self.rolls_left}] [NextHourClaimReset: {self.next_hour_is_claim_reset}]")
