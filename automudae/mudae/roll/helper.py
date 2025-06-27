import logging
from datetime import timedelta

import discord

from automudae.mudae.roll.command import MudaeRollCommand

logger = logging.getLogger(__name__)

MUDAE_ROLL_TIMEOUT_SECONDS = 0.5


async def get_roll_command_from_roll_message(msg: discord.Message) -> MudaeRollCommand:
    possible_owners: list[MudaeRollCommand] = []
    for multiplier in range(1, 4):
        history = msg.channel.history(
            before=msg.created_at,
            after=msg.created_at
            - timedelta(seconds=MUDAE_ROLL_TIMEOUT_SECONDS * multiplier),
        )
        async for history_msg in history:
            if roll_command := MudaeRollCommand.create(history_msg):
                possible_owners.append(roll_command)
        # If empty, reprocess with longer window
        if len(possible_owners) == 0:
            possible_owners = []
            continue
        # If not, just use that
        break
    assert len(possible_owners) != 0
    return possible_owners[-1]
