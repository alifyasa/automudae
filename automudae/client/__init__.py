import asyncio
import logging
from datetime import time, timezone

import discord
from discord.ext import tasks

from automudae.client.roll import MudaeRollMixin
from automudae.client.timers import MudaeTimerMixin
from automudae.config.v1 import Config

logger = logging.getLogger(__name__)


class AutoMudaeClient(MudaeTimerMixin, MudaeRollMixin, discord.Client):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        # Mode is either rolling, claiming, or kakera reacting
        self.mode_lock = asyncio.Lock()

        self.roll_task: asyncio.Task[None] | None = None
        self.claim_task: asyncio.Task[None] | None = None
        self.send_tu_task: asyncio.Task[None] | None = None
        self.kakera_react_task: asyncio.Task[None] | None = None

        logger.setLevel(logging.INFO)
        logger.info("Initialization Complete")

    async def on_ready(self) -> None:
        logger.info(f"Client is Ready. Using the following config: {self.config}")
        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel:
            return
        if not isinstance(mudae_channel, discord.TextChannel):
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel

        self.roll_task = self.roll.start()
        self.claim_task = self.claim.start()
        self.send_tu_task = self.send_tu.start()
        self.kakera_react_task = self.kakera_react.start()

    async def on_message(self, message: discord.Message):
        logger.debug("Handling a Message")
        if self.is_mudae_timer_list_msg(
            msg=message, user=self.user, config=self.config
        ):
            await self.update_timer(msg=message)
            logger.info("Handled a Mudae Timer List Message ($tu)")
        elif self.is_roll_command(msg=message):
            await self.enqueue_roll_command(msg=message, config=self.config)
            logger.info(f"Handled a Roll Command by {message.author.display_name}")
        elif self.is_failed_roll_command(msg=message):
            roll_command_author: discord.user.BaseUser | discord.Member
            if message.interaction:
                roll_command_author = message.interaction.user
            else:
                roll_command_author = await self.dequeue_roll_command()
            logger.info(
                f"Handled a Failed Roll Command by {roll_command_author.display_name}"
            )
        elif self.is_claimable_roll(msg=message):
            roll_result = await self.enqueue_claimable_roll(msg=message)
            logger.info(
                f"[QUEUE] [Character: {roll_result.character}] [Series: {roll_result.series}] [Kakera: {roll_result.kakera}] [User: {roll_result.author.display_name}]"
            )
        elif self.is_kakera_reactable_roll(msg=message):
            roll_result = await self.enqueue_kakera_reactable_roll(msg=message)
            logger.info(
                f"KAKERA [{roll_result.author.display_name}] {roll_result.character} from {roll_result.series} @{roll_result.kakera} Kakera"
            )

    @tasks.loop(
        time=[time(hour=hour, minute=15, tzinfo=timezone.utc) for hour in range(24)]
    )
    async def send_tu(self) -> None:
        async with self.mode_lock:
            await self.__send_tu()

    @tasks.loop(seconds=5.0)
    async def roll(self) -> None:
        if not self.user:
            logger.warning("[ROLL] Roll not processed: User is not logged in")
            return
        async with self.mode_lock, self.timer_lock:
            if not self.can_claim:
                logger.debug("[ROLL] Roll not processed: Cannot Claim")
                return
            if self.rolls_left <= 0:
                logger.debug("[ROLL] Roll not processed: No Rolls Left")
                return

            await self.mudae_channel.send(self.config.mudae.roll.command)
            self.rolls_left -= 1

            # On last roll, send $tu
            if self.rolls_left == 1:
                await asyncio.sleep(2.5)
                await self.__send_tu()

    @tasks.loop(seconds=1.0)
    async def claim(self) -> None:
        if not self.user:
            logger.warning("[CLAIM] Claim not processed: User is not logged in")
            return
        async with self.mode_lock, self.claimable_roll_lock, self.timer_lock:
            claimable_count = len(self.claimable_roll_queue)
            while claimable_count != 0:
                claimable_roll = self.claimable_roll_queue.pop(0)
                claimable_count = len(self.claimable_roll_queue)

                if not self.can_claim:
                    logger.info(
                        "[CLAIM] Claim not processed: User is not eligible to claim"
                    )
                    continue

                snipe_criteria = self.config.mudae.claim.snipe
                character_qualifies = (
                    claimable_roll.character in snipe_criteria.character
                )
                series_qualifies = claimable_roll.series in snipe_criteria.series
                kakera_qualifies = claimable_roll.kakera >= snipe_criteria.minKakera
                if character_qualifies or series_qualifies or kakera_qualifies:
                    logger.info(
                        f"[CLAIM] Sniping {claimable_roll.character} from {claimable_roll.author.display_name}"
                    )
                    await claimable_roll.claim()
                    await self.__send_tu()
                    continue

                roll_is_mine = claimable_roll.author.id == self.user.id

                early_claim_criteria = self.config.mudae.claim.earlyClaim
                character_qualifies = (
                    claimable_roll.character in early_claim_criteria.character
                )
                series_qualifies = claimable_roll.series in early_claim_criteria.series
                kakera_qualifies = (
                    claimable_roll.kakera >= early_claim_criteria.minKakera
                )
                if roll_is_mine and (
                    character_qualifies or series_qualifies or kakera_qualifies
                ):
                    logger.info(
                        f"[CLAIM] Claiming {claimable_roll.character} ({claimable_roll.series})"
                    )
                    await claimable_roll.claim()
                    await self.__send_tu()
                    continue

                efficient_claim_criteria = self.config.mudae.claim.efficientClaim
                character_qualifies = (
                    claimable_roll.character in efficient_claim_criteria.character
                )
                series_qualifies = (
                    claimable_roll.series in efficient_claim_criteria.series
                )
                kakera_qualifies = (
                    claimable_roll.kakera >= efficient_claim_criteria.minKakera
                )
                if (
                    roll_is_mine
                    and self.next_hour_is_claim_reset
                    and (character_qualifies or series_qualifies or kakera_qualifies)
                ):
                    logger.info(
                        f"[CLAIM] Claiming {claimable_roll.character} ({claimable_roll.series})"
                    )
                    await claimable_roll.claim()
                    await self.__send_tu()
                    continue

                logger.info(
                    f"[CLAIM] Not claiming {claimable_roll.character} ({claimable_roll.series})"
                )

    @tasks.loop(seconds=1.0)
    async def kakera_react(self) -> None:
        if not self.user:
            logger.warning("[KAKERA] Kakera not processed: User is not logged in")
            return
        async with self.mode_lock, self.kakera_reactable_roll_lock:
            kakera_reactable_count = len(self.kakera_reactable_roll_queue)
            while kakera_reactable_count != 0:
                claimable_roll = self.kakera_reactable_roll_queue.pop(0)
                kakera_reactable_count = len(self.kakera_reactable_roll_queue)

                roll_is_mine = claimable_roll.author.id == self.user.id
                logger.info(
                    f"[KAKERA] {claimable_roll.character} from {claimable_roll.series} ({roll_is_mine}, {kakera_reactable_count})"
                )

                if not self.can_react_to_kakera:
                    logger.warning(
                        "[KAKERA] Kakera not processed: Cannot react to Kakera"
                    )
                    continue

                if roll_is_mine:
                    logger.warning(
                        f"[KAKERA] Kakera React to {claimable_roll.character}"
                    )
                    await claimable_roll.kakera_react()
                    await self.__send_tu()
                    continue

    async def __send_tu(self) -> None:
        logger.info("Sending $tu")
        await self.mudae_channel.send("$tu")
