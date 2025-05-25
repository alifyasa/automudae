import asyncio
import logging

import discord

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

    async def on_message(self, message: discord.Message):
        if self.is_mudae_timer_list_msg(
            msg=message, user=self.user, config=self.config
        ):
            self.update_timer(msg=message)
            logger.info("Handled a Mudae Timer List Message ($tu)")
        elif self.is_roll_command(msg=message):
            await self.enqueue_roll_command(msg=message, config=self.config)
            logger.info(f"Handled a Roll Command by {message.author.display_name}")
        elif self.is_failed_roll_command(msg=message):
            roll_command_author = await self.dequeue_roll_command()
            logger.info(
                f"Handled a Failed Roll Command by {roll_command_author.display_name}"
            )
        elif self.is_claimable_roll(msg=message):
            roll_result = await self.enqueue_claimable_roll(msg=message)
            logger.info(
                f"CLAIM [{roll_result.author.display_name}] {roll_result.character} from {roll_result.series} @{roll_result.kakera} Kakera"
            )
        elif self.is_kakera_reactable_roll(msg=message):
            roll_result = await self.enqueue_kakera_reactable_roll(msg=message)
            logger.info(
                f"KAKERA [{roll_result.author.display_name}] {roll_result.character} from {roll_result.series} @{roll_result.kakera} Kakera"
            )
