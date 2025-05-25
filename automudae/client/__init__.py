import logging

import discord

from automudae.config.v1 import Config
from automudae.client.timers import MudaeTimerMixin

logger = logging.getLogger(__name__)


class AutoMudaeClient(discord.Client, MudaeTimerMixin):
    def __init__(self, config: Config):
        super().__init__()
        
        self.config = config
        self.is_rolling = False
        self.mudae_channel = None

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

    # @tasks.loop(time=time(tzinfo=timezone.utc, minute=50))
    # async def start_rolling(self):
    #     self.is_rolling = True
    
    # async def stop_rolling(self):
    #     self.is_rolling = False

    # @tasks.loop(seconds=5)
    # async def roll(self):
    #     if not self.is_rolling: return
    #     if not self.mudae_channel: return
    #     await self.mudae_channel.send(self.config.mudae.roll.command)


    
    # def is_claimable(self, message: discord.Message):
    #     if not message.embeds: return False
    #     embed = message.embeds[0]
    #     if not embed.author.name: return False
    #     if not embed.description: return False
    #     return "React with any emoji to claim!" in embed.description
    
    # async def claim(self, message: discord.Message):
    #     await message.fetch()
    #     if not message.embeds: return
    #     embed = message.embeds[0]
    #     if not embed.author.name: return
    #     if not embed.description: return
    #     rematch = re.match(r"^(.*)\\n\*\*(\d+)\*\*", embed.description)
    #     if not rematch: return
    #     # rolledCharacter = embed.author.name
    #     # rolledSeries = rematch.group(1)
    #     # rolledKakera = rematch.group(2)

    #     # characterIsWished = rolledCharacter in self.config.mudae.wish.character
    #     # seriesIsWished = rolledSeries in self.config.mudae.wish.series
    #     # kakeraIsDesired = 

    # def is_stop_roll_message(self, messageContent: str):
    #     if not self.user: return False
    #     return f"**{self.user.display_name}**, the roulette is limited to" in messageContent
