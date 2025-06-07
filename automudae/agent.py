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
logger.setLevel(logging.DEBUG)


class AutoMudaeAgentState:
    def __init__(self) -> None:
        self.late_claim_best_pick: MudaeClaimableRollResult | None = None
        self.timer_status = MudaeTimerStatus()

        self.roll_command_queue: asyncio.Queue[MudaeRollCommand] = asyncio.Queue()
        self.my_claimable_roll_queue: asyncio.Queue[MudaeClaimableRollResult] = (
            asyncio.Queue()
        )
        self.my_kakera_roll_queue: asyncio.Queue[MudaeKakeraRollResult] = (
            asyncio.Queue()
        )
        self.others_claimable_roll_queue: asyncio.Queue[MudaeClaimableRollResult] = (
            asyncio.Queue()
        )
        self.others_kakera_roll_queue: asyncio.Queue[MudaeKakeraRollResult] = (
            asyncio.Queue()
        )


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
            asyncio.create_task(self.roll_and_handle_my_rolls_loop()),
            asyncio.create_task(self.handle_others_rolls_loop()),
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
            logger.info(claimable_roll)
            if claimable_roll.owner.id == self.user.id:
                await self.state.my_claimable_roll_queue.put(claimable_roll)
            else:
                await self.state.others_claimable_roll_queue.put(claimable_roll)
            return

        if (
            kakera_roll := await MudaeKakeraRollResult.create(
                message, self.state.roll_command_queue
            )
        ) is not None:
            logger.info(kakera_roll)
            if kakera_roll.owner.id == self.user.id:
                await self.state.my_kakera_roll_queue.put(kakera_roll)
            else:
                await self.state.others_kakera_roll_queue.put(kakera_roll)
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

    async def roll_and_handle_my_rolls_loop(self) -> None:
        assert self.mudae_channel
        while True:
            async with self.state.timer_status.lock:
                if self.state.timer_status.rolls_left <= 0:
                    await asyncio.sleep(1)
                    continue
                if (
                    self.config.mudae.roll.doNotRollWhenCanotClaim
                    and not self.state.timer_status.can_claim
                ):
                    await asyncio.sleep(1)
                    continue
                if (
                    self.config.mudae.roll.doNotRollWhenCannotKakeraReact
                    and not self.state.timer_status.can_kakera_react
                ):
                    await asyncio.sleep(1)
                    continue

                async with self.command_rate_limiter:
                    await self.mudae_channel.send(self.config.mudae.roll.command)
                    self.state.timer_status.rolls_left -= 1

                result = await self.wait_for_roll(
                    {
                        asyncio.create_task(self.state.my_claimable_roll_queue.get()),
                        asyncio.create_task(self.state.my_kakera_roll_queue.get()),
                    }
                )
                if isinstance(result, MudaeClaimableRollResult):
                    await self.handle_claim(result)
                elif isinstance(result, MudaeKakeraRollResult):
                    await self.handle_kakera_react(result)

                if self.state.timer_status.rolls_left <= 0:
                    await self.send_timer_status_message()

    async def handle_others_rolls_loop(self) -> None:
        while True:
            result = await self.wait_for_roll(
                {
                    asyncio.create_task(self.state.others_claimable_roll_queue.get()),
                    asyncio.create_task(self.state.others_kakera_roll_queue.get()),
                }
            )
            if isinstance(result, MudaeClaimableRollResult):
                await self.handle_claim(result)
            elif isinstance(result, MudaeKakeraRollResult):
                await self.handle_kakera_react(result)

    async def handle_claim(self, roll: MudaeClaimableRollResult) -> None:

        assert self.user
        assert self.mudae_channel

        if not self.state.timer_status:
            logger.warning("> Not Claiming: Timer Status Not Available")
            return

        if not self.state.timer_status.can_claim:
            logger.info("> Not Claiming: Cannot Claim")
            return

        if not self.state.timer_status:
            logger.warning("> Not Claiming: Timer Status Not Available")
            return

        if not self.state.timer_status.can_claim:
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
                time_to_claim = self.get_reaction_time(roll)
                logger.info("> Snipe: %s", roll.character)
                logger.info("> Reaction Time: %.2fs", time_to_claim)
                await roll.claim()
            self.state.timer_status.can_claim = False
            await self.send_timer_status_message()
            return
        logger.debug("> Failed Snipe Criteria")

        roll_is_mine = roll.owner.id == self.user.id
        if not roll_is_mine:
            logger.debug("> Roll Not Mine")
            return

        early_claim_criteria = self.config.mudae.claim.earlyClaim
        if (
            roll.is_qualified(early_claim_criteria, self.user)
            or roll.wished_by is not None
        ):
            async with self.react_rate_limiter:
                time_to_claim = self.get_reaction_time(roll)
                logger.info("> Early Claim: %s", roll.character)
                logger.info("> Reaction Time: %.2fs", time_to_claim)
                await roll.claim()
            self.state.timer_status.can_claim = False
            await self.send_timer_status_message()
            return
        logger.debug("> Failed Early Claim Criteria")

        if not self.state.timer_status.next_hour_is_reset:
            logger.debug("> Next Hour is Not Reset")
            return

        if self.state.late_claim_best_pick is None:
            logger.debug("> Overriding Late Claim Best Pick: Best Pick is None")
            self.state.late_claim_best_pick = roll
        elif roll.wished_by is not None:
            logger.debug("> Overriding Late Claim Best Pick: Wished by Someone")
            self.state.late_claim_best_pick = roll
        elif self.state.late_claim_best_pick.kakera_value <= roll.kakera_value:
            logger.debug(
                "> Overriding Late Claim Best Pick: Roll Has More Kakera Value"
            )
            self.state.late_claim_best_pick = roll

        assert self.state.late_claim_best_pick
        late_claim_criteria = self.config.mudae.claim.lateClaim
        if not self.state.late_claim_best_pick.is_qualified(
            late_claim_criteria, self.user
        ):
            logger.debug("> Failed Late Claim Criteria")
            logger.debug("> Clearing Late Claim Best Pick")
            self.state.late_claim_best_pick = None
            return

        if self.state.timer_status.rolls_left != 0:
            logger.debug("> Rolls Not 0 Yet")
            return

        async with self.react_rate_limiter:
            time_to_claim = self.get_reaction_time(self.state.late_claim_best_pick)
            logger.info("> Late Claim: %s", self.state.late_claim_best_pick.character)
            logger.info("> Reaction Time: %.2fs", time_to_claim)
            await self.state.late_claim_best_pick.claim()

        self.state.timer_status.can_claim = False
        await self.send_timer_status_message()

        self.state.late_claim_best_pick = None

    async def handle_kakera_react(self, roll: MudaeKakeraRollResult) -> None:

        assert self.user
        assert self.mudae_channel

        async with self.state.timer_status.lock:

            if not self.state.timer_status:
                logger.warning("> Timer Status Unavailable")
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
            for button_name in kakera_buttons:
                if button_name in self.config.mudae.kakeraReact.doNotReactToKakeraTypes:
                    logger.info("> Will not react to %s", button_name)
                    return
            if (
                "kakeraP" not in kakera_buttons
                and not self.state.timer_status.can_kakera_react
            ):
                logger.info("> Cannot react to non-purple kakera")
                return

            time_to_claim = self.get_reaction_time(roll)
            logger.info("> Kakera React: %s", kakera_buttons)
            logger.info("> Reaction Time: %.2fs", time_to_claim)
            async with self.react_rate_limiter:
                await roll.kakera_react()
                self.state.timer_status.can_kakera_react = False

            await self.send_timer_status_message()

    async def wait_for_roll(
        self,
        from_queue: set[
            asyncio.Task[MudaeClaimableRollResult] | asyncio.Task[MudaeKakeraRollResult]
        ],
    ) -> MudaeClaimableRollResult | MudaeKakeraRollResult:
        done, pending = await asyncio.wait(
            from_queue,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        return await next(iter(done))

    def get_reaction_time(self, roll: MudaeRollResult) -> float:
        return (datetime.now(tz=timezone.utc) - roll.message.created_at).total_seconds()
