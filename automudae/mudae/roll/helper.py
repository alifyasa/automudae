import logging
from datetime import timedelta

import discord

from automudae.mudae.roll.command import MudaeRollCommand

logger = logging.getLogger(__name__)

MUDAE_ROLL_TIMEOUT_SECONDS = 0.25


async def get_roll_command_from_roll_message(msg: discord.Message) -> MudaeRollCommand:
    possible_owners: list[MudaeRollCommand] = []
    max_multiplier = 7  # up to 1.75 seconds
    for multiplier in range(1, max_multiplier + 1):
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

    if len(possible_owners) == 0:
        total_seconds_searched = MUDAE_ROLL_TIMEOUT_SECONDS * max_multiplier
        raise ValueError(
            f"Owner not found! Tried to search the past {total_seconds_searched} seconds"
        )

    return possible_owners[-1]
