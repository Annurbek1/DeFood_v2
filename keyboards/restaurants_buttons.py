from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging
from database.db import db

async def create_restaurant_buttons():
    restaurants, error = await db.get_restaurants()
    if error:
        logging.error(f"Error getting restaurants: {error}")
        return None, error
    if not restaurants:
        return None, "Kechirasiz, hozircha faol restoranlar mavjud emas."
    
    try:
        buttons = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=str(restaurant[1]))] for restaurant in restaurants
            ] + [[KeyboardButton(text="⬅️ Orqaga")]],
            resize_keyboard=True
        )
        return buttons, None
    except Exception as e:
        logging.error(f"Error creating restaurant buttons: {e}")
        return None, "Xatolik yuz berdi"    
async def create_category_buttons(restaurant_name):
    categories, error = await db.get_categories(restaurant_name)
    if error:
        return None, error
    if not categories:
        return None, "Kechirasiz, bu restoranda hozircha faol kategoriyalar mavjud emas."

    category_buttons = [KeyboardButton(text=str(name[0])) for name in categories]
    grouped_category_buttons = [category_buttons[i:i+2] for i in range(0, len(category_buttons), 2)]

    control_buttons = [[KeyboardButton(text="🛒 Savat")], [KeyboardButton(text="⬅️ Orqaga")]]

    buttons = ReplyKeyboardMarkup(
        keyboard=grouped_category_buttons + control_buttons,
        resize_keyboard=True
    )

    return buttons, None

async def create_eat_buttons(restaurant_name: str, category_name: str) -> tuple[ReplyKeyboardMarkup, str | None]:
    try:
        # Get eats from database
        eats, error = await db.get_eats(restaurant_name, category_name)
        
        if error:
            logging.error(f"Error fetching eats: {error}")
            return None, error
            
        if not eats:
            return None, "Bu kategoriyada taomlar mavjud emas"

        # Create buttons list with both name and ID
        eat_buttons = []
        row = []
        for eat in eats:
            button_text = f"{eat.name} | {eat.id}"  # Combining name and ID
            row.append(KeyboardButton(text=button_text))
            if len(row) == 2:  # Create rows with 2 buttons each
                eat_buttons.append(row)
                row = []
        
        # Add remaining buttons if any
        if row:
            eat_buttons.append(row)

        # Add control buttons at the bottom
        control_buttons = [
            [KeyboardButton(text="🛒 Savat")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ]

        # Combine all buttons
        keyboard = ReplyKeyboardMarkup(
            keyboard=eat_buttons + control_buttons,
            resize_keyboard=True
        )

        return keyboard, None

    except Exception as e:
        logging.error(f"Error creating eat buttons: {e}")
        return None, "Taomlar ro'yxatini yaratishda xatolik"