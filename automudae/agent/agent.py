import logging

import discord

from automudae.config import Config
from automudae.mudae.roll import MudaeClaimableRoll, MudaeKakeraRoll, MudaeRollCommands, MudaeRollCommand, MudaeClaimableRolls, MudaeFailedRollCommand, MudaeKakeraRolls

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AutoMudaeAgent(discord.Client):
    def __init__(self, config: Config):
        super().__init__()

        self.config = config

        self.mudae_channel: discord.TextChannel | None = None
        self.mudae_roll_commands = MudaeRollCommands()
        self.mudae_claimable_rolls = MudaeClaimableRolls()
        self.mudae_kakera_rolls = MudaeKakeraRolls()

        logger.info("AutoMudae Agent Initialization Complete")

    async def on_ready(self) -> None:

        mudae_channel = self.get_channel(self.config.discord.channelId)
        if not mudae_channel:
            return
        if not isinstance(mudae_channel, discord.TextChannel):
            logger.error("Channel is not a Text Channel")
            return
        self.mudae_channel = mudae_channel

        logger.info("AutoMudae Agent is Ready")

    async def on_message(self, message: discord.Message) -> None:

        if not self.user:
            return

        if message.channel.id != self.config.discord.channelId:
            return

        roll_command = MudaeRollCommand.create(message)
        if roll_command is not None:
            await self.mudae_roll_commands.put(roll_command)
            logger.debug(f"[CMD] {roll_command.command} from {roll_command.owner.display_name}. Queue Size: {self.mudae_roll_commands.qsize()}")
            return
            
        claimable_roll = await MudaeClaimableRoll.create(message, self.mudae_roll_commands)
        if claimable_roll is not None:
            await self.mudae_claimable_rolls.put(claimable_roll)
            logger.debug(f"[ROLL] {claimable_roll.character}. Queue Size: {self.mudae_claimable_rolls.qsize()}")
            return
        
        kakera_roll = await MudaeKakeraRoll.create(message, self.mudae_roll_commands)
        if kakera_roll is not None:
            await self.mudae_kakera_rolls.put(kakera_roll)
            logger.debug(f"[KAKERA] {[button.emoji.name for button in kakera_roll.buttons if button.emoji]}. Queue Size: {self.mudae_kakera_rolls.qsize()}")
            return
        
        failed_roll_command = await MudaeFailedRollCommand.create(message, self.mudae_roll_commands)
        if failed_roll_command is not None:
            logger.debug(f"[CMD] Failed Roll Command from {failed_roll_command.owner.display_name}")
            return
