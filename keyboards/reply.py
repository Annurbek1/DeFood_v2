from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

async def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚚 Ovqat buyurtma qilish")],
            [KeyboardButton(text="🛒 Savat"), KeyboardButton(text="⚙️ Sozlamalar")]
        ],
        resize_keyboard=True
    )