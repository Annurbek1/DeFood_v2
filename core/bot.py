from aiogram import Bot
from typing import Optional

_bot: Optional[Bot] = None

def set_bot(bot: Bot):
    global _bot
    _bot = bot

def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Bot instance not set")
    return _bot