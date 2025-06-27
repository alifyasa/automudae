# pylint: disable=R0902,R0911,R0912,R0915,R0903
import asyncio
import logging
from datetime import datetime, time, timezone

import discord
from aiolimiter import AsyncLimiter
from discord.ext import tasks

from automudae.config import Config
from automudae.helper import discord_message_to_str
from automudae.mudae.roll.result import (
    MudaeClaimableRollResult,
    MudaeKakeraRollResult,
    MudaeRollResult,
)
from automudae.mudae.timer import MudaeTimerStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AutoMudaeAgentState:
    def __init__(self) -> None:
        self.best_claim_roll: MudaeClaimableRollResult | None = None
        self.kakera_best_pick: MudaeKakeraRollResult | None = None

        self.timer_status = MudaeTimerStatus()
        self.rolls_executed = 0
        self.rolls_handled = 0

        self.roll_queue: asyncio.Queue[
            MudaeClaimableRollResult | MudaeKakeraRollResult
        ] = asyncio.Queue()


class AutoMudaeAgent(discord.Client):

    def __init__(self, config: Config) -> None:
        super().__init__()

        self.config = config

        self.mudae_channel: discord.TextChannel | None = None
        self.react_rate_limiter = AsyncLimiter(1, 0.25)
        self.command_rate_limiter = AsyncLimiter(1, 1)
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
            asyncio.create_task(self.execute_rolls_loop()),
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

        logger.debug(discord_message_to_str(message))

        if (
            claimable_roll := await MudaeClaimableRollResult.create(message)
        ) is not None:
            await self.state.roll_queue.put(claimable_roll)
            return

        if (kakera_roll := await MudaeKakeraRollResult.create(message)) is not None:
            await self.state.roll_queue.put(kakera_roll)
            return

        if (
            timer_status := await MudaeTimerStatus.create(message, self.user)
        ) is not None:
            await self.state.timer_status.update(timer_status)
            self.state.rolls_handled = 0
            self.state.rolls_executed = 0
            logger.info(self.state.timer_status)
            return

    async def send_timer_status_message(self) -> None:
        assert self.mudae_channel
        async with self.command_rate_limiter:
            await self.mudae_channel.send("$tu")

    async def execute_rolls_loop(self) -> None:
        while True:
            async with self.command_rate_limiter:
                await self.state.timer_status.wait_for_rolls()
                async with self.state.timer_status.debug_lock("execute_rolls_loop"):
                    if not self.mudae_channel:
                        continue

                    if (
                        self.state.rolls_handled
                        >= self.state.timer_status.rolls_available
                    ):
                        await self.send_timer_status_message()
                        continue

                    if (
                        self.config.mudae.roll.doNotRollWhenCannotClaim
                        and not self.state.timer_status.can_claim
                    ):
                        continue

                    if (
                        self.config.mudae.roll.doNotRollWhenCannotKakeraReact
                        and not self.state.timer_status.can_kakera_react
                    ):
                        continue

                    await self.mudae_channel.send(self.config.mudae.roll.command)
                    self.state.rolls_executed += 1

    async def handle_rolls_loop(self) -> None:
        while True:
            result = await self.state.roll_queue.get()
            async with self.state.timer_status.debug_lock("handle_rolls_loop"):

                if self.user and result.owner.id == self.user.id:
                    self.state.rolls_handled += 1

                if isinstance(result, MudaeClaimableRollResult):
                    await self.handle_claim(result)
                else:
                    await self.handle_kakera_react(result)

                await self.handle_finalizer()

                if self.user and result.owner.id == self.user.id:
                    logger.info(
                        "ROLL PROCESSING COMPLETE: %d rolls remaining",
                        self.state.timer_status.rolls_available
                        - self.state.rolls_handled,
                    )

    async def handle_claim(self, roll: MudaeClaimableRollResult) -> None:
        logger.info(roll)

        if not self.user:
            logger.error("CLAIM FAILED: Not logged in - cannot identify user")
            return

        if not self.mudae_channel:
            logger.error("CLAIM FAILED: Mudae channel not configured")
            return

        if not self.state.timer_status.can_claim:
            logger.info("CLAIM SKIPPED: Timer cooldown active - cannot claim yet")
            return

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.info(
                "CLAIM SKIPPED: Roll too old (%.1fs > 30s timeout)",
                roll_time_elapsed.total_seconds(),
            )
            return

        # Check snipe criteria and exceptions
        meets_snipe_criteria = roll.is_qualified(
            self.config.mudae.claim.snipe, self.user
        )
        meets_snipe_exception = roll.is_qualified(
            self.config.mudae.claim.snipe.exception, self.user
        )

        logger.info(
            "SNIPE EVALUATION: Meets criteria: %s, Meets exception: %s",
            meets_snipe_criteria,
            meets_snipe_exception,
        )

        if meets_snipe_criteria and not meets_snipe_exception:
            logger.info("CLAIMING: Roll meets snipe criteria - immediate claim")
            async with self.react_rate_limiter:
                await roll.claim()
            self.state.timer_status.can_claim = False
            return

        if meets_snipe_exception:
            logger.info(
                "SNIPE REJECTED: Roll meets snipe criteria exception - skipping immediate claim"
            )
        else:
            logger.info("SNIPE REJECTED: Roll doesn't meet snipe criteria")

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.info(
                "PROCESSING SKIPPED: Roll belongs to user %s, not me (%s)",
                roll.owner.id,
                self.user.id,
            )
            return

        logger.info("PROCESSING: Roll is mine, evaluating for best claim selection")

        # Update best claim roll logic
        if self.state.best_claim_roll is None:
            logger.info(
                "BEST ROLL UPDATED: No previous best roll - setting this as best"
            )
            self.state.best_claim_roll = roll
        elif roll.wished_by is not None:
            logger.info(
                "BEST ROLL UPDATED: Roll is wished by %s - prioritizing over previous best",
                roll.wished_by,
            )
            self.state.best_claim_roll = roll
        elif (
            self.state.best_claim_roll.kakera_value <= roll.kakera_value
            and self.state.best_claim_roll.wished_by is None
        ):
            logger.info(
                "BEST ROLL UPDATED: Higher kakera value (%s >= %s) and no wishes on previous best",
                roll.kakera_value,
                self.state.best_claim_roll.kakera_value,
            )
            self.state.best_claim_roll = roll
        else:
            logger.info(
                "BEST ROLL UNCHANGED: Current roll (kakera: %s, wished: %s) doesn't beat existing best (kakera: %s, wished: %s)",
                roll.kakera_value,
                roll.wished_by is not None,
                self.state.best_claim_roll.kakera_value,
                self.state.best_claim_roll.wished_by is not None,
            )

        assert self.state.best_claim_roll

        # Wait for more rolls if available
        if self.state.timer_status.rolls_available > self.state.rolls_handled:
            logger.info(
                "CLAIM DEFERRED: Waiting for %s more rolls before claiming best",
                self.state.timer_status.rolls_available - self.state.rolls_handled,
            )
            return

        # Evaluate claim criteria and exceptions
        meets_early_claim_criteria = self.state.best_claim_roll.is_qualified(
            self.config.mudae.claim.earlyClaim, self.user
        )
        meets_late_claim_criteria = self.state.best_claim_roll.is_qualified(
            self.config.mudae.claim.lateClaim, self.user
        )
        meets_early_claim_exception = self.state.best_claim_roll.is_qualified(
            self.config.mudae.claim.earlyClaim.exception, self.user
        )
        meets_late_claim_exception = self.state.best_claim_roll.is_qualified(
            self.config.mudae.claim.lateClaim.exception, self.user
        )

        logger.info(
            "CLAIM EVALUATION: Early criteria: %s, Early exception: %s, Late criteria: %s, Late exception: %s, Next hour is reset: %s",
            meets_early_claim_criteria,
            meets_early_claim_exception,
            meets_late_claim_criteria,
            meets_late_claim_exception,
            self.state.timer_status.next_hour_is_reset,
        )

        # Determine if we should claim based on criteria and exceptions
        should_claim_early = (
            meets_early_claim_criteria and not meets_early_claim_exception
        )
        should_claim_late = (
            meets_late_claim_criteria
            and not meets_late_claim_exception
            and self.state.timer_status.next_hour_is_reset
        )

        if should_claim_early or should_claim_late:
            if should_claim_early:
                if meets_early_claim_exception:
                    logger.info(
                        "CLAIMING: Best roll meets early claim criteria but also meets exception - evaluating late claim"
                    )
                else:
                    logger.info(
                        "CLAIMING: Best roll meets early claim criteria and doesn't meet exception"
                    )

            if should_claim_late and not should_claim_early:
                if meets_late_claim_exception:
                    logger.info(
                        "CLAIMING: Best roll meets late claim criteria but also meets exception - skipping claim"
                    )
                else:
                    logger.info(
                        "CLAIMING: Best roll meets late claim criteria, doesn't meet exception, and next hour is reset"
                    )

            async with self.react_rate_limiter:
                await self.state.best_claim_roll.claim()
            self.state.timer_status.can_claim = False
        else:
            # Detailed rejection logging
            if meets_early_claim_criteria and meets_early_claim_exception:
                logger.info(
                    "CLAIM REJECTED: Roll meets early criteria but also meets early claim exception"
                )
            elif meets_late_claim_criteria and meets_late_claim_exception:
                logger.info(
                    "CLAIM REJECTED: Roll meets late criteria but also meets late claim exception"
                )
            elif (
                meets_late_claim_criteria
                and not self.state.timer_status.next_hour_is_reset
            ):
                logger.info(
                    "CLAIM REJECTED: Roll meets late criteria but next hour is not reset"
                )
            elif not meets_early_claim_criteria and not meets_late_claim_criteria:
                logger.info(
                    "CLAIM REJECTED: Roll doesn't meet early or late claim criteria"
                )
            else:
                logger.info(
                    "CLAIM REJECTED: Unknown rejection reason - criteria evaluation may need review"
                )

        logger.info("PROCESSING COMPLETE: Resetting best claim roll")
        self.state.best_claim_roll = None

    async def handle_kakera_react(self, roll: MudaeKakeraRollResult) -> None:

        logger.info(roll)

        if not self.user:
            logger.error("KAKERA REACT FAILED: Not logged in - cannot identify user")
            return

        if not self.mudae_channel:
            logger.error("KAKERA REACT FAILED: Mudae channel not configured")
            return

        current_time = datetime.now(tz=timezone.utc)
        roll_time_elapsed = current_time - roll.message.created_at
        if roll_time_elapsed.total_seconds() >= 30:
            logger.info(
                "KAKERA REACT SKIPPED: Roll too old (%.1fs > 30s timeout)",
                roll_time_elapsed.total_seconds(),
            )
            return

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.info(
                "KAKERA REACT SKIPPED: Roll belongs to user %s, not me (%s)",
                roll.owner.id,
                self.user.id,
            )
            return

        kakera_buttons = [
            button.emoji.name for button in roll.buttons if button.emoji is not None
        ]
        logger.info("KAKERA BUTTONS FOUND: %s", kakera_buttons)

        if "kakeraP" in kakera_buttons:
            time_to_claim = self.get_reaction_time(roll)
            logger.info(
                "KAKERA REACTING: kakeraP found - immediate reaction (reaction time: %.2fs)",
                time_to_claim,
            )
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
                logger.info(
                    "KAKERA REACT SKIPPED: %s requires %s power but only have %s",
                    kakera_type,
                    minimum_power,
                    self.state.timer_status.kakera_power,
                )
                return

        logger.info("PROCESSING: Evaluating for best kakera pick selection")

        if self.state.kakera_best_pick is None:
            logger.info(
                "BEST KAKERA UPDATED: No previous best pick - setting this as best (value: %s)",
                roll.kakera_value,
            )
            self.state.kakera_best_pick = roll
        elif self.state.kakera_best_pick.kakera_value <= roll.kakera_value:
            logger.info(
                "BEST KAKERA UPDATED: Higher value (%s >= %s) - replacing previous best",
                roll.kakera_value,
                self.state.kakera_best_pick.kakera_value,
            )
            self.state.kakera_best_pick = roll
        else:
            logger.info(
                "BEST KAKERA UNCHANGED: Current roll value (%s) doesn't beat existing best (%s)",
                roll.kakera_value,
                self.state.kakera_best_pick.kakera_value,
            )

        for button_name in kakera_buttons:
            if button_name in self.config.mudae.kakeraReact.doNotReactToKakeraTypes:
                logger.info(
                    "KAKERA REACT BLOCKED: %s is in blocked kakera types list",
                    button_name,
                )
                return

        if self.state.timer_status.rolls_available > self.state.rolls_handled:
            remaining_rolls = (
                self.state.timer_status.rolls_available - self.state.rolls_handled
            )
            logger.info(
                "KAKERA REACT DEFERRED: Waiting for %s more rolls before reacting to best",
                remaining_rolls,
            )
            return

        if not self.state.timer_status.can_kakera_react:
            logger.info(
                "KAKERA REACT BLOCKED: Timer cooldown active - cannot react yet"
            )
            return

        time_to_claim = self.get_reaction_time(roll)
        logger.info(
            "KAKERA REACTING: Best pick selected with buttons %s (reaction time: %.2fs)",
            kakera_buttons,
            time_to_claim,
        )
        async with self.react_rate_limiter:
            await roll.kakera_react()
            self.state.timer_status.can_kakera_react = False

        self.state.kakera_best_pick = None

    async def handle_finalizer(self) -> None:
        if self.state.timer_status.rolls_available > self.state.rolls_handled:
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
