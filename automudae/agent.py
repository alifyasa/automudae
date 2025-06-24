# pylint: disable=R0902,R0911,R0912,R0915,R0903
import asyncio
import logging
from datetime import datetime, time, timezone

import discord
from aiolimiter import AsyncLimiter
from discord.ext import tasks

from automudae.config import Config
from automudae.mudae.roll import (
    MudaeClaimableRollResult,
    MudaeKakeraRollResult,
    MudaeRollCommand,
    MudaeRollResult,
    MudaeRouletteLimitedError,
)
from automudae.mudae.timer import MudaeTimerStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AutoMudaeAgentState:
    def __init__(self) -> None:
        self.best_claim_roll: MudaeClaimableRollResult | None = None
        self.kakera_best_pick: MudaeKakeraRollResult | None = None
        self.timer_status = MudaeTimerStatus()

        self.roll_command_queue: asyncio.Queue[MudaeRollCommand] = asyncio.Queue()
        self.roll_queue: asyncio.Queue[
            MudaeClaimableRollResult | MudaeKakeraRollResult
        ] = asyncio.Queue()


class AutoMudaeAgent(discord.Client):

    def __init__(self, config: Config) -> None:
        super().__init__()

        self.config = config

        self.mudae_channel: discord.TextChannel | None = None
        self.react_rate_limiter = AsyncLimiter(1, 0.25)
        self.command_rate_limiter = AsyncLimiter(1, 1.75)
        self.tasks: list[asyncio.Task[None]] = []
        self.state = AutoMudaeAgentState()

        logger.info("AutoMudae Agent Initialization Complete")

    async def on_ready(self) -> None:

        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel:
            return
        if not isinstance(mudae_channel, discord.TextChannel):
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel

        reset_minute_offset = self.config.mudae.roll.rollResetMinuteOffset
        hourly_roll_loop = tasks.loop(
            time=[
                time(
                    hour=hour, minute=reset_minute_offset, second=5, tzinfo=timezone.utc
                )
                for hour in range(24)
            ]
        )

        self.tasks = [
            hourly_roll_loop(self.send_timer_status_message).start(),
            asyncio.create_task(self.roll_loop()),
            asyncio.create_task(self.handle_rolls_loop()),
            asyncio.create_task(self.refresh_loop()),
        ]

        await self.send_timer_status_message()

        logger.info("AutoMudae Agent is Ready")

    async def on_message(self, message: discord.Message) -> None:

        if not self.user:
            return

        if message.channel.id != self.config.discord.channelId:
            return

        if (roll_command := MudaeRollCommand.create(message)) is not None:
            await self.state.roll_command_queue.put(roll_command)
            logger.debug(roll_command)
            return

        if (
            claimable_roll := await MudaeClaimableRollResult.create(
                message, self.state.roll_command_queue
            )
        ) is not None:
            await self.state.roll_queue.put(claimable_roll)
            return

        if (
            kakera_roll := await MudaeKakeraRollResult.create(
                message, self.state.roll_command_queue
            )
        ) is not None:
            await self.state.roll_queue.put(kakera_roll)
            return

        if (
            roulette_limited_error := await MudaeRouletteLimitedError.create(
                message, self.state.roll_command_queue
            )
        ) is not None:
            logger.debug(roulette_limited_error)
            return

        if (
            timer_status := await MudaeTimerStatus.create(message, self.user)
        ) is not None:
            await self.state.timer_status.update(timer_status)
            logger.info(self.state.timer_status)
            return

    async def send_timer_status_message(self) -> None:
        assert self.mudae_channel
        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

    async def roll_loop(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            async with self.state.timer_status.debug_lock("roll_loop"):
                if not self.mudae_channel:
                    continue

                if self.state.timer_status.rolls_left <= 0:
                    continue

                if (
                    self.config.mudae.roll.doNotRollWhenCanotClaim
                    and not self.state.timer_status.can_claim
                ):
                    continue

                if (
                    self.config.mudae.roll.doNotRollWhenCannotKakeraReact
                    and not self.state.timer_status.can_kakera_react
                ):
                    continue

                async with self.command_rate_limiter:
                    await self.mudae_channel.send(self.config.mudae.roll.command)
                    self.state.timer_status.rolls_left -= 1

                if self.state.timer_status.rolls_left <= 0:
                    await self.send_timer_status_message()

    async def handle_rolls_loop(self) -> None:
        while True:
            result = await self.state.roll_queue.get()
            async with self.state.timer_status.debug_lock("handle_rolls_loop"):
                if isinstance(result, MudaeClaimableRollResult):
                    await self.handle_claim(result)
                else:
                    await self.handle_kakera_react(result)
                await self.handle_finalizer()

    async def handle_claim(self, roll: MudaeClaimableRollResult) -> None:

        logger.info(roll)

        if not self.user:
            logger.error("> Not Logged In")
            return

        if not self.mudae_channel:
            logger.error("> Mudae Channel Not Set")
            return

        if not self.state.timer_status.can_claim:
            logger.info("> Cannot Claim")
            return

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.info("> Roll older than 30 seconds")
            return

        snipe_criteria = self.config.mudae.claim.snipe
        if roll.is_qualified(snipe_criteria, self.user):
            async with self.react_rate_limiter:
                await roll.claim()
            self.state.timer_status.can_claim = False
            return
        logger.debug("> Failed Snipe Criteria")

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.debug("> Roll Not Mine")
            return

        if self.state.best_claim_roll is None:
            logger.info("> Overriding Best Claim Roll: Best Pick is None")
            self.state.best_claim_roll = roll
        elif roll.wished_by is not None:
            logger.info("> Overriding Best Claim Roll: Wished by Someone")
            self.state.best_claim_roll = roll
        elif (
            self.state.best_claim_roll.kakera_value <= roll.kakera_value
            and self.state.best_claim_roll.wished_by is None
        ):
            logger.info("> Overriding Best Claim Roll: Roll Has More Kakera Value")
            self.state.best_claim_roll = roll

        assert self.state.best_claim_roll

        if self.state.timer_status.rolls_left != 0:
            logger.debug("> Rolls Not 0 Yet")
            return

        qualified_early_claim = self.state.best_claim_roll.is_qualified(
            self.config.mudae.claim.earlyClaim, self.user
        )
        qualified_late_claim = self.state.best_claim_roll.is_qualified(
            self.config.mudae.claim.lateClaim, self.user
        )

        if qualified_early_claim or (
            qualified_late_claim and self.state.timer_status.next_hour_is_reset
        ):
            async with self.react_rate_limiter:
                await self.state.best_claim_roll.claim()
            self.state.timer_status.can_claim = False

        self.state.best_claim_roll = None

    async def handle_kakera_react(self, roll: MudaeKakeraRollResult) -> None:

        logger.info(roll)

        if not self.user:
            logger.error("> Not Logged In")
            return

        if not self.mudae_channel:
            logger.error("> Mudae Channel Not Set")
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

        kakera_buttons = [
            button.emoji.name for button in roll.buttons if button.emoji is not None
        ]

        if "kakeraP" in kakera_buttons:
            time_to_claim = self.get_reaction_time(roll)
            logger.info("> Kakera React: %s", kakera_buttons)
            logger.info("> Reaction Time: %.2fs", time_to_claim)
            async with self.react_rate_limiter:
                await roll.kakera_react()
                self.state.timer_status.can_kakera_react = False
            return

        kakera_power_requirements = (
            self.config.mudae.kakeraReact.doNotReactToKakeraTypeIfKakeraPowerLessThan
        )
        for kakera_type, minimum_power in kakera_power_requirements.items():
            if (
                kakera_type in kakera_buttons
                and self.state.timer_status.kakera_power < minimum_power
            ):
                return

        if self.state.kakera_best_pick is None:
            self.state.kakera_best_pick = roll
        elif self.state.kakera_best_pick.kakera_value <= roll.kakera_value:
            self.state.kakera_best_pick = roll

        for button_name in kakera_buttons:
            if button_name in self.config.mudae.kakeraReact.doNotReactToKakeraTypes:
                logger.info("> Will not react to %s", button_name)
                return

        if self.state.timer_status.rolls_left != 0:
            logger.debug("> Rolls Not 0 Yet")
            return

        if not self.state.timer_status.can_kakera_react:
            logger.info("> Cannot React")
            return

        time_to_claim = self.get_reaction_time(roll)
        logger.info("> Kakera React: %s", kakera_buttons)
        logger.info("> Reaction Time: %.2fs", time_to_claim)
        async with self.react_rate_limiter:
            await roll.kakera_react()
            self.state.timer_status.can_kakera_react = False

    async def handle_finalizer(self) -> None:
        if self.state.timer_status.rolls_left != 0:
            logger.debug("> Rolls Not 0 Yet")
            return

        if self.state.best_claim_roll is not None:
            await self.handle_claim(self.state.best_claim_roll)
            self.state.best_claim_roll = None
            return

        if self.state.kakera_best_pick is not None:
            await self.handle_kakera_react(self.state.kakera_best_pick)
            self.state.kakera_best_pick = None
            return

    def get_reaction_time(self, roll: MudaeRollResult) -> float:
        return (datetime.now(tz=timezone.utc) - roll.message.created_at).total_seconds()

    async def refresh_loop(self) -> None:
        while True:
            await asyncio.gather(
                *[connection.refresh() for connection in self.connections]
            )
            await asyncio.sleep(1)
