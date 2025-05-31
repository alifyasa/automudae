import asyncio
import logging
from datetime import datetime, time, timezone

import discord
from aiolimiter import AsyncLimiter
from discord.ext import tasks

from automudae.config import Config
from automudae.mudae.roll import (
    MudaeClaimableRoll,
    MudaeClaimableRolls,
    MudaeFailedRollCommand,
    MudaeKakeraRoll,
    MudaeKakeraRolls,
    MudaeRollCommand,
    MudaeRollCommands,
)
from automudae.mudae.timer import MudaeTimerStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AutoMudaeAgent(discord.Client):

    def __init__(self, config: Config):
        super().__init__()

        self.config = config

        self.mudae_channel: discord.TextChannel | None = None
        self.mudae_roll_commands = MudaeRollCommands()
        self.mudae_claimable_rolls = MudaeClaimableRolls()
        self.mudae_kakera_rolls = MudaeKakeraRolls()
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
            self.claim_loop.start(),
            self.roll_loop.start(),
            self.timer_status_loop.start(),
            self.kakera_react_loop.start(),
        ]

        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

        logger.info("AutoMudae Agent is Ready")

    async def on_message(self, message: discord.Message) -> None:

        if not self.user:
            return

        if message.channel.id != self.config.discord.channelId:
            return

        roll_command = MudaeRollCommand.create(message)
        if roll_command is not None:
            await self.mudae_roll_commands.put(roll_command)
            logger.debug(
                f"[CMD] {roll_command.command} from {roll_command.owner.display_name}"
            )
            return

        claimable_roll = await MudaeClaimableRoll.create(
            message, self.mudae_roll_commands
        )
        if claimable_roll is not None:
            await self.mudae_claimable_rolls.put(claimable_roll)
            logger.info(claimable_roll)
            return

        kakera_roll = await MudaeKakeraRoll.create(message, self.mudae_roll_commands)
        if kakera_roll is not None:
            await self.mudae_kakera_rolls.put(kakera_roll)
            logger.info(kakera_roll)
            return

        failed_roll_command = await MudaeFailedRollCommand.create(
            message, self.mudae_roll_commands
        )
        if failed_roll_command is not None:
            logger.debug(
                f"[CMD] Failed Roll Command from {failed_roll_command.owner.display_name}"
            )
            return

        timer_status = await MudaeTimerStatus.create(message, self.user)
        if timer_status is not None:
            self.timer_status = timer_status
            logger.info(self.timer_status)
            return

    @tasks.loop(
        time=[
            time(hour=hour, minute=23, second=5, tzinfo=timezone.utc)
            for hour in range(24)
        ]
    )
    async def timer_status_loop(self) -> None:
        if not self.mudae_channel:
            return
        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

    @tasks.loop(seconds=0.25)
    async def claim_loop(self) -> None:

        if not self.user:
            logger.debug("Not Claiming: Not Logged In")
            return

        if not self.timer_status:
            logger.debug("Not Claiming: Timer Status Not Available")
            return

        if not self.mudae_channel:
            logger.debug("Not Claiming: Mudae Channel Unavailable")
            return

        if not self.timer_status.can_claim:
            logger.debug("Not Claiming: Cannot Claim")
            return

        if (
            self.mudae_claimable_rolls.empty()
            and self.timer_status.rolls_left == 0
            and self.late_claim_best_pick is not None
        ):
            logger.info(f"Late Claim <{self.late_claim_best_pick.character}>")
            async with self.react_rate_limiter:
                await self.late_claim_best_pick.claim()
            async with self.command_rate_limiter:
                await self.mudae_channel.send("$tu")
            self.late_claim_best_pick = None
            return

        if self.mudae_claimable_rolls.empty():
            return

        roll = await self.mudae_claimable_rolls.get()
        logger.debug(f" > Processing {roll}")

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.debug(f" > Roll older than 30 seconds, skipping")
            self.mudae_claimable_rolls.task_done()
            return

        snipe_criteria = self.config.mudae.claim.snipe
        if roll.is_qualified(snipe_criteria, self.user):
            logger.info(f"Snipe <{roll.character}>")
            async with self.react_rate_limiter:
                await roll.claim()
            self.mudae_claimable_rolls.task_done()
            return
        logger.debug(f" > Failed Snipe Criteria")

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.debug(f" > Roll Not Mine, skipping")
            self.mudae_claimable_rolls.task_done()
            return

        early_claim_criteria = self.config.mudae.claim.earlyClaim
        if roll.is_qualified(early_claim_criteria, self.user):
            logger.info(f"Early Claim <{roll.character}>")
            async with self.react_rate_limiter:
                await roll.claim()
            async with self.command_rate_limiter:
                await self.mudae_channel.send("$tu")
            self.mudae_claimable_rolls.task_done()
            return
        logger.debug(f" > Failed Early Claim Criteria")

        late_claim_criteria = self.config.mudae.claim.lateClaim
        if not roll.is_qualified(late_claim_criteria, self.user):
            logger.debug(f" > Failed Late Claim Criteria")
            self.mudae_claimable_rolls.task_done()
            return

        if self.late_claim_best_pick is None:
            logger.debug(" > Set as Last Claim Best Pick")
            self.late_claim_best_pick = roll
            self.mudae_claimable_rolls.task_done()
            return
        elif roll.kakera_value > self.late_claim_best_pick.kakera_value:
            logger.debug(
                f" > Overriding Previous Last Claim Best Pick {self.late_claim_best_pick}"
            )
            self.late_claim_best_pick = roll
            self.mudae_claimable_rolls.task_done()
            return

        logger.debug(f" > Failed Overriding Late Claim Best Pick")
        self.mudae_claimable_rolls.task_done()

    @tasks.loop(seconds=0.25)
    async def kakera_react_loop(self) -> None:

        if self.mudae_kakera_rolls.empty():
            return

        if not self.user:
            logger.debug("Not Kakera Reacting: Not Logged In")
            return

        if not self.mudae_channel:
            logger.debug("Not Kakera Reacting: Mudae Channel Unavailable")
            return

        if not self.timer_status:
            logger.debug("Not Kakera Reacting: Timer Status Unavailable")
            return

        if not self.timer_status.can_kakera_react:
            logger.debug("Not Kakera Reacting: Cannot Kakera React")
            return

        roll = await self.mudae_kakera_rolls.get()
        logger.debug(f" > Processing {roll}")

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.debug(f" > Roll older than 30 seconds, skipping")
            self.mudae_kakera_rolls.task_done()
            return

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.debug(f" > Roll Not Mine, skipping")
            self.mudae_kakera_rolls.task_done()
            return

        logger.info(f"Kakera React <{roll}>")
        async with self.react_rate_limiter:
            await roll.kakera_react()

        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

        self.mudae_kakera_rolls.task_done()

    @tasks.loop(seconds=0.25)
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
