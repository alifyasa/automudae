import asyncio
import logging
from datetime import datetime, timezone

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
logger.setLevel(logging.DEBUG)


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

        self.tasks = [self.claim_loop.start(), self.roll_loop.start()]

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
            logger.debug(
                f"[ROLL] <{claimable_roll.owner.display_name}> {claimable_roll.character} from {claimable_roll.series}"
            )
            return

        kakera_roll = await MudaeKakeraRoll.create(message, self.mudae_roll_commands)
        if kakera_roll is not None:
            await self.mudae_kakera_rolls.put(kakera_roll)
            logger.debug(
                f"[KAKERA] <{kakera_roll.owner.display_name}> {[button.emoji.name for button in kakera_roll.buttons if button.emoji]}"
            )
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
            logger.debug(f"[TIMER] {self.timer_status}")
            return

    @tasks.loop(seconds=0.25)
    async def claim_loop(self) -> None:

        if not self.user:
            return

        if not self.timer_status:
            return

        if not self.timer_status.can_claim:
            return

        if (
            self.mudae_claimable_rolls.empty()
            and self.timer_status.rolls_left == 0
            and self.late_claim_best_pick is not None
        ):
            async with self.react_rate_limiter:
                await self.late_claim_best_pick.claim()
            self.late_claim_best_pick = None
            return

        roll = await self.mudae_claimable_rolls.get()

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            self.mudae_claimable_rolls.task_done()
            return

        snipe_settings = self.config.mudae.claim.snipe
        if (
            roll.character in snipe_settings.character
            or roll.series in snipe_settings.series
            or roll.kakera_value >= snipe_settings.minKakera
        ):
            async with self.react_rate_limiter:
                await roll.claim()
            self.mudae_claimable_rolls.task_done()
            return

        early_claim_settings = self.config.mudae.claim.earlyClaim
        roll_is_mine = roll.owner.id == self.user.id
        if roll_is_mine and (
            roll.character in early_claim_settings.character
            or roll.series in early_claim_settings.series
            or roll.kakera_value >= early_claim_settings.minKakera
        ):
            async with self.react_rate_limiter:
                await roll.claim()
            self.mudae_claimable_rolls.task_done()
            return

        if not roll_is_mine:
            self.mudae_claimable_rolls.task_done()
            return

        late_claim_settings = self.config.mudae.claim.lateClaim
        if not (
            roll.character in late_claim_settings.character
            or roll.series in late_claim_settings.series
            or roll.kakera_value >= late_claim_settings.minKakera
        ):
            self.mudae_claimable_rolls.task_done()
            return

        if self.late_claim_best_pick is None:
            self.late_claim_best_pick = roll
            self.mudae_claimable_rolls.task_done()
            return
        elif roll.kakera_value > self.late_claim_best_pick.kakera_value:
            self.late_claim_best_pick = roll
            self.mudae_claimable_rolls.task_done()
            return

        self.mudae_claimable_rolls.task_done()

    @tasks.loop(seconds=0.25)
    async def kakera_react_loop(self) -> None:

        if not self.user:
            return

        if not self.mudae_channel:
            return

        if not self.timer_status:
            return

        if not self.timer_status.can_kakera_react:
            return

        roll = await self.mudae_kakera_rolls.get()

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            self.mudae_kakera_rolls.task_done()
            return

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            self.mudae_kakera_rolls.task_done()
            return

        async with self.react_rate_limiter:
            await roll.kakera_react()

        async with self.react_rate_limiter, self.command_rate_limiter:
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

        if not self.timer_status.can_claim:
            return

        if self.timer_status.rolls_left <= 0:
            return

        async with self.command_rate_limiter:
            await self.mudae_channel.send(self.config.mudae.roll.command)
            self.timer_status.rolls_left -= 1

        if self.timer_status.rolls_left <= 0:
            async with self.command_rate_limiter:
                await self.mudae_channel.send("$tu")
