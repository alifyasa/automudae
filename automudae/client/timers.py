import re
import discord
import logging
from automudae.config.v1 import Config

logger = logging.getLogger(__name__)
class MudaeTimerMixin:
    def __init__(self) -> None:
        self.can_claim = False
        self.can_react_to_kakera = False
        self.rolls_left = 0
        
    def is_mudae_timer_list_msg(self, msg: discord.Message, user: discord.ClientUser | None, config: Config):
        if not user: return False
        if msg.channel.id != config.discord.channelId: return False
        if msg.author.id != config.discord.mudaeBotId: return False

        clean_msg = discord.utils.remove_markdown(msg.content)
        is_my_message = clean_msg.startswith(user.display_name)
        is_mudae_timer_list_msg = "=> $tuarrange" in clean_msg
        return is_my_message and is_mudae_timer_list_msg
    
    def update_timer(self, msg: discord.Message):
        clean_msg = discord.utils.remove_markdown(msg.content)

        claim_pattern = re.search(r'you (can|can\'t) claim', clean_msg)
        self.can_claim = claim_pattern and claim_pattern.group(1) == "can"

        rolls_pattern = re.search(r'You have (\d+) rolls left', clean_msg)
        self.rolls_left = rolls_pattern and int(rolls_pattern.group(1))

        kakera_pattern = re.search(r'You (can|can\'t) react to kakera', clean_msg)
        self.can_react_to_kakera = kakera_pattern and kakera_pattern.group(1) == "can"
