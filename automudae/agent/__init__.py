import asyncio
import logging
from datetime import datetime, time, timezone

import discord
from aiolimiter import AsyncLimiter
from discord.ext import tasks

from automudae.config import Config
from automudae.mudae.roll import (
    MudaeClaimableRoll,
    MudaeFailedRollCommand,
    MudaeKakeraRoll,
    MudaeRollCommand,
    MudaeRollCommands,
)
from automudae.mudae.timer import MudaeTimerStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AutoMudaeAgent(discord.Client):

    def __init__(self, config: Config):
        super().__init__()

        self.config = config

        self.mudae_channel: discord.TextChannel | None = None
        self.mudae_roll_commands = MudaeRollCommands()
        self.timer_status: MudaeTimerStatus | None = None
        self.react_rate_limiter = AsyncLimiter(1, 0.25)
        self.command_rate_limiter = AsyncLimiter(1, 1.75)
        self.tasks: list[asyncio.Task[None]] = []
        self.late_claim_best_pick: MudaeClaimableRoll | None = None

        logger.info("AutoMudae Agent Initialization Complete")

    async def on_ready(self) -> None:

        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel:
            return
        if not isinstance(mudae_channel, discord.TextChannel):
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel

        self.tasks = [
            self.roll_loop.start(),
            self.timer_status_loop.start(),
        ]

        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

        logger.info("AutoMudae Agent is Ready")

    async def on_message(self, message: discord.Message) -> None:

        if not self.user:
            return

        if message.channel.id != self.config.discord.channelId:
            return

        logger.debug(f"Received Message {message.id}")

        roll_command = MudaeRollCommand.create(message)
        if roll_command is not None:
            await self.mudae_roll_commands.put(roll_command)
            logger.debug(roll_command)
            return

        claimable_roll = await MudaeClaimableRoll.create(
            message, self.mudae_roll_commands
        )
        if claimable_roll is not None:
            logger.info(claimable_roll)
            await self.handle_claim(claimable_roll)
            return

        kakera_roll = await MudaeKakeraRoll.create(message, self.mudae_roll_commands)
        if kakera_roll is not None:
            logger.info(kakera_roll)
            await self.handle_kakera_react(kakera_roll)
            return

        failed_roll_command = await MudaeFailedRollCommand.create(
            message, self.mudae_roll_commands
        )
        if failed_roll_command is not None:
            logger.debug(failed_roll_command)
            return

        timer_status = await MudaeTimerStatus.create(message, self.user)
        if timer_status is not None:
            self.timer_status = timer_status
            logger.info(self.timer_status)
            return

    @tasks.loop(
        time=[
            time(hour=hour, minute=30, second=5, tzinfo=timezone.utc)
            for hour in range(24)
        ]
    )
    async def timer_status_loop(self) -> None:
        if not self.mudae_channel:
            return
        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

    async def handle_claim(self, roll: MudaeClaimableRoll) -> None:

        if not self.user:
            logger.warning("> Not Claiming: Not Logged In")
            return

        if not self.timer_status:
            logger.warning("> Not Claiming: Timer Status Not Available")
            return

        if not self.mudae_channel:
            logger.warning("> Not Claiming: Mudae Channel Unavailable")
            return

        if not self.timer_status.can_claim:
            logger.info("> Not Claiming: Cannot Claim")
            return

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.debug("> Roll older than 30 seconds")
            return

        snipe_criteria = self.config.mudae.claim.snipe
        if roll.is_qualified(snipe_criteria, self.user):
            async with self.react_rate_limiter:
                current_time = datetime.now(tz=timezone.utc)
                time_to_claim = (current_time - roll.message.created_at).total_seconds()
                logger.info(
                    f"> Snipe: {roll.character} - Reaction Time: {time_to_claim:.2f}s"
                )
                await roll.claim()
            async with self.command_rate_limiter:
                await self.mudae_channel.send("$tu")
            return
        logger.debug("> Failed Snipe Criteria")

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.debug("> Roll Not Mine")
            return

        early_claim_criteria = self.config.mudae.claim.earlyClaim
        if roll.is_qualified(early_claim_criteria, self.user):
            async with self.react_rate_limiter:
                current_time = datetime.now(tz=timezone.utc)
                time_to_claim = (current_time - roll.message.created_at).total_seconds()
                logger.info(
                    f"> Early Claim: {roll.character} - Reaction Time: {time_to_claim:.2f}s"
                )
                await roll.claim()
            async with self.command_rate_limiter:
                await self.mudae_channel.send("$tu")
            return
        logger.debug("> Failed Early Claim Criteria")

        if not self.timer_status.next_hour_is_reset:
            logger.debug("> Next Hour is Not Reset")
            return

        if self.late_claim_best_pick is None:
            logger.debug("> Overriding Late Claim Best Pick: Best Pick is None")
            self.late_claim_best_pick = roll
        elif roll.wished_by is not None:
            logger.debug("> Overriding Late Claim Best Pick: Wished by Someone")
            self.late_claim_best_pick = roll
        elif self.late_claim_best_pick.kakera_value <= roll.kakera_value:
            logger.debug(
                "> Overriding Late Claim Best Pick: Roll Has More Kakera Value"
            )
            self.late_claim_best_pick = roll

        late_claim_criteria = self.config.mudae.claim.lateClaim
        if (
            self.late_claim_best_pick.wished_by is not None
            and not self.late_claim_best_pick.is_qualified(
                late_claim_criteria, self.user
            )
        ):
            logger.debug("> Failed Late Claim Criteria")
            logger.debug("> Clearing Late Claim Best Pick")
            self.late_claim_best_pick = None
            return

        if self.timer_status.rolls_left != 0:
            logger.debug("> Rolls Not 0 Yet")
            return

        async with self.react_rate_limiter:
            current_time = datetime.now(tz=timezone.utc)
            time_to_claim = (
                current_time - self.late_claim_best_pick.message.created_at
            ).total_seconds()
            logger.info(
                f"> Late Claim: {self.late_claim_best_pick.character} - Reaction Time: {time_to_claim:.2f}s"
            )
            await self.late_claim_best_pick.claim()
        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

        self.late_claim_best_pick = None

    async def handle_kakera_react(self, roll: MudaeKakeraRoll) -> None:

        if not self.user:
            logger.warning("> Not Logged In")
            return

        if not self.mudae_channel:
            logger.warning("> Mudae Channel Unavailable")
            return

        if not self.timer_status:
            logger.warning("> Timer Status Unavailable")
            return

        if not self.timer_status.can_kakera_react:
            logger.info("> Cannot Kakera React")
            return

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.debug("> Roll older than 30 seconds")
            return

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.debug("> Roll Not Mine")
            return

        current_time = datetime.now(tz=timezone.utc)
        time_to_claim = (current_time - roll.message.created_at).total_seconds()
        logger.info(
            f"> Kakera React: {[button.emoji.name for button in roll.buttons if button.emoji]} - Reaction Time: {time_to_claim:.2f}s"
        )
        async with self.react_rate_limiter:
            await roll.kakera_react()

        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

    @tasks.loop(seconds=0.1)
    async def roll_loop(self) -> None:

        if not self.user:
            return

        if not self.mudae_channel:
            return

        if not self.timer_status:
            return

        if (
            self.config.mudae.roll.doNotRollWhenCanotClaim
            and not self.timer_status.can_claim
        ):
            return

        if (
            self.config.mudae.roll.doNotRollWhenCannotKakeraReact
            and not self.timer_status.can_kakera_react
        ):
            return

        if self.timer_status.rolls_left <= 0:
            return

        async with self.command_rate_limiter:
            await self.mudae_channel.send(self.config.mudae.roll.command)
            self.timer_status.rolls_left -= 1

        if self.timer_status.rolls_left <= 0:
            async with self.command_rate_limiter:
                await self.mudae_channel.send("$tu")
