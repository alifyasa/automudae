import discord


def discord_message_to_str(message: discord.Message) -> str:
    msg_clean = discord.utils.remove_markdown(message.content)
    partial_msg = get_partial_str(msg_clean)
    if partial_msg == "":
        partial_msg = "<<EMPTY>>"
    parts = [
        f"id={message.id}",
        f"author={message.author.display_name!r}",
    ]
    if partial_msg != "":
        parts.append(f"content={partial_msg!r}")
    return f"DiscordMessage({', '.join(parts)})"


def get_partial_str(
    text: str, start_chars: int = 20, end_chars: int = 20, min_gap: int = 10
) -> str:
    if len(text) <= start_chars + end_chars + min_gap:
        return text
    return f"{text[:start_chars]}...{text[-end_chars:]}"
