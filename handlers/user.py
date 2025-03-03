from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from aiogram.filters import StateFilter
from keyboards.reply import main_menu
from states.states import OrderState
import logging
from database.db import db

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    try:
        await state.clear()
        
        user_name = message.from_user.username
        if not user_name:
            user_name = message.from_user.first_name or "Hurmatli foydalanuvchi"
            
        success, error = await db.add_or_update_user(
            telegram_id=message.from_user.id,
            username=user_name
        )
        
        if not success:
            logging.error(f"Failed to save user data: {error}")
            
        keyboard = await main_menu()
        await message.answer(
            "Xush kelibsiz! 😊 Iltimos, amalni tanlang:", 
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in start command: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")

@router.message(lambda message: message.text == "⬅️ Orqaga", StateFilter(None))
async def back_to_main_without_state(message: Message, state: FSMContext):
    """Handle back button when no state is set"""
    keyboard = await main_menu()
    await message.answer("Bosh menyu:", reply_markup=keyboard)