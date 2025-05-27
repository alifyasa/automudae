import logging
import discord

from automudae.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class AutoMudaeAgent(discord.Client):
    def __init__(self, config: Config):
        super().__init__()

        self.config = config
        self.mudae_channel: discord.TextChannel | None = None

        logger.info("AutoMudae Agent Initialization Complete")
    
    async def on_ready(self) -> None:
        logger.info("Agent is Ready")

        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel:
            return
        if not isinstance(mudae_channel, discord.TextChannel):
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel

    async def on_message(self, message: discord.Message) -> None:

        if message.channel.id != self.config.discord.channelId:
            return

        logger.debug(f"<@{message.author.display_name}>: {message.content}")
