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

        self.claim_task: asyncio.Task[None] | None = None
        self.send_tu_task: asyncio.Task[None] | None = None

        logger.setLevel(logging.INFO)
        logger.info("Initialization Complete")

    async def on_ready(self):
        logger.info(f"Client is Ready. Using the following config: {self.config}")
        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel:
            return
        if not isinstance(mudae_channel, discord.TextChannel):
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel

        self.claim_task = self.claim.start()
        self.send_tu_task = self.send_tu.start()

    async def on_message(self, message: discord.Message):
        logger.debug("Handling a Message")
        if self.is_mudae_timer_list_msg(
            msg=message, user=self.user, config=self.config
        ):
            self.update_timer(msg=message)
            logger.info("Handled a Mudae Timer List Message ($tu)")
        elif self.is_roll_command(msg=message):
            await self.enqueue_roll_command(msg=message, config=self.config)
            logger.info(f"Handled a Roll Command by {message.author.display_name}")
        elif self.is_failed_roll_command(msg=message):
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
                f"[QUEUE] {roll_result.author.display_name} => {roll_result.character} from {roll_result.series} @{roll_result.kakera} Kakera"
            )
        else:
            logger.debug(f"Reactions: {message.reactions}")
        # elif self.is_kakera_reactable_roll(msg=message):
        #     roll_result = await self.enqueue_kakera_reactable_roll(msg=message)
        #     logger.info(
        #         f"KAKERA [{roll_result.author.display_name}] {roll_result.character} from {roll_result.series} @{roll_result.kakera} Kakera"
        #     )

    @tasks.loop(
        time=[time(hour=hour, minute=15, tzinfo=timezone.utc) for hour in range(24)]
    )
    async def send_tu(self):
        logger.debug("Send $tu Heartbeat Start")
        async with self.mode_lock:
            await self.__send_tu()
        logger.debug("Send $tu Heartbeat End")

    @tasks.loop(seconds=1.0)
    async def claim(self):
        logger.debug("Claim heartbeat start")
        if not self.user:
            logger.debug("Claim heartbeat end because: Not Logged In")
            return
        if not self.can_claim:
            logger.debug("Claim heartbeat end because: Cannot Claim")
            return
        async with self.mode_lock:
            async with self.claimable_roll_lock:
                claimable_count = len(self.claimable_roll_queue)
                while claimable_count != 0:
                    claimable_roll = self.claimable_roll_queue.pop(0)
                    claimable_count = len(self.claimable_roll_queue)
                    logger.debug(f"[CLAIM] Count: {claimable_count}")

                    character_in_snipelist = (
                        claimable_roll.character in self.config.mudae.snipe.character
                    )
                    character_in_wishlist = (
                        claimable_roll.character in self.config.mudae.wish.character
                    )
                    roll_is_mine = claimable_roll.author.id == self.user.id
                    logger.info(
                        f"[CLAIM] {claimable_roll.character} from {claimable_roll.series} ({character_in_snipelist}, {character_in_wishlist}, {roll_is_mine})"
                    )

                    if character_in_snipelist:
                        await claimable_roll.claim()
                        await self.__send_tu()
                        continue

                    if character_in_wishlist and roll_is_mine:
                        await claimable_roll.claim()
                        await self.__send_tu()
                        continue
        logger.debug("Claim heartbeat end normally")

    async def __send_tu(self):
        logger.info("Sending $tu")
        await self.mudae_channel.send("$tu")
