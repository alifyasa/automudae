import logging

import discord

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_buttons(message: discord.Message):
    buttons: list[discord.Button] = []
    for component in message.components:
        if not isinstance(component, discord.ActionRow):
            continue
        for child in component.children:
            if not isinstance(child, discord.Button):
                continue
            if not child.emoji:
                continue
            buttons.append(child)
    return buttons
