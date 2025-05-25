import logging

import discord

from automudae.config.v1 import Config
from automudae.client.timers import MudaeTimerMixin
from automudae.client.roll import MudaeRollMixin

logger = logging.getLogger(__name__)


class AutoMudaeClient(MudaeTimerMixin, MudaeRollMixin, discord.Client):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        logger.info("Initialization Complete")

    async def on_ready(self):
        logger.info(f"Client is Ready. Using the following config: {self.config}")
        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel: return
        if not isinstance(mudae_channel, discord.TextChannel): 
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel
        
    async def on_message(self, message: discord.Message):
        if self.is_mudae_timer_list_msg(msg=message, user=self.user, config=self.config):
            self.update_timer(msg=message)
            logger.info("Handled a Mudae Timer List Message ($tu)")
        elif self.is_roll_command(msg=message):
            await self.enqueue_roll_command(msg=message, config=self.config)
            logger.info(f"Handled a Roll Command by {message.author.display_name}")
