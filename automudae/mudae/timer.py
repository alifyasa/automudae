
import logging
import re
import discord
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MudaeTimerOwner = discord.User | discord.ClientUser | discord.Member | discord.user.BaseUser
class MudaeTimerStatus(BaseModel):
    can_claim: bool
    rolls_left: int
    can_kakera_react: bool
    next_hour_is_reset: bool
    owner: MudaeTimerOwner
    
    class Config:
        arbitrary_types_allowed = True

    @classmethod
    async def create(cls, message: discord.Message, current_user: MudaeTimerOwner):
        clean_msg = discord.utils.remove_markdown(message.content)

        is_my_message = clean_msg.startswith(current_user.display_name)
        is_mudae_timer_list_msg = "=> $tuarrange" in clean_msg
        if not (is_my_message and is_mudae_timer_list_msg):
            return None
        
        claim_pattern = re.search(r"you (can|can\'t) claim", clean_msg)
        if not claim_pattern:
            return None
        
        rolls_pattern = re.search(r"You have (\d+) rolls? left", clean_msg)
        if not rolls_pattern:
            return None
        
        kakera_pattern = re.search(r"You (can|can\'t) react to kakera", clean_msg)
        if not kakera_pattern:
            return None

        claim_reset_pattern = re.search(
                r"(?:The next claim reset is in|you can't claim for another)\s+(?:(\d+)h\s*)?(\d+)\s*min",
                clean_msg,
            )
        if not claim_reset_pattern:
            return None

        claim_reset_hours = (
                int(claim_reset_pattern.group(1)) if claim_reset_pattern.group(1) else 0
            )
        claim_reset_minutes = (
                int(claim_reset_pattern.group(2)) if claim_reset_pattern.group(2) else 0
            )
        next_claim_reset_in_minutes = claim_reset_hours * 60 + claim_reset_minutes

        return MudaeTimerStatus(
            owner=current_user, 
            can_claim=claim_pattern.group(1) == "can",
            rolls_left=int(rolls_pattern.group(1)) if rolls_pattern.group(1) else 0,
            can_kakera_react=kakera_pattern.group(1) == "can",
            next_hour_is_reset=next_claim_reset_in_minutes <= 60
        )
