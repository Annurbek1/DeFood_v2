from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging
from database.db import db

async def basket():
    buttons = [
        [
            KeyboardButton(text="🛒 Savatim"),
            KeyboardButton(text="🛒 Buyurtmalarim"),
        ],
        [
            KeyboardButton(text="⬅️ Orqaga"),
        ],
    ]
    basket_kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    return basket_kb

async def generate_basket_keyboard(items, is_empty: bool = False) -> InlineKeyboardMarkup:
    """
    Generate inline keyboard for basket
    items format: (cart_id, name, quantity, price, restaurant_id)
    """
    buttons = []

    if is_empty:
        buttons.append([
            InlineKeyboardButton(
                text="🍽 Buyurtma berish", 
                callback_data="order_from_menu"
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="✅ Buyurtmani yakunlash", 
                callback_data="complete_order"
            )
        ])

        # Add remove buttons for each item
        for cart_id, name, quantity, price, _ in items:
            buttons.append([
                InlineKeyboardButton(
                    text=f"❌ O'chirish {name}", 
                    callback_data=f"remove_{cart_id}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Orqaga", 
                callback_data="back"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)