from aiogram import types
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from aiogram.filters import StateFilter
from states.states import OrderState
from keyboards.reply import *
from keyboards.basket import *
from keyboards.restaurants_buttons import *
from functions.functions import *

router = Router()
@router.message(lambda message: message.text == "🛒 Savat")
async def view_basket_selection(message: types.Message, state: FSMContext):
    try:
        if StateFilter(None):
            await state.set_state(OrderState.viewing_cart)
            basket_kb = await basket()
            await message.answer("Qaysi bo'limga o'tmoqchisiz.\nBo'limni tanlang", reply_markup=basket_kb)
        else:
            # Get basket items from database
            items, error = await db.get_basket_items(message.from_user.id)
            
            if error:
                logging.error(f"Error getting basket items: {error}")
                await message.answer("Savatni ko'rsatishda xatolik yuz berdi.")
                return

            # Calculate totals and generate message
            response_text, total_items, total_sum = await calculate_basket_totals(items or [])

            # Generate keyboard based on basket contents
            keyboard = await generate_basket_keyboard(
                items=items, 
                is_empty=not bool(items)
            )

            # Send response with basket contents and keyboard
            await message.answer(
                text=response_text,
                reply_markup=keyboard
            )

            # Update state to basket viewing
            await state.set_state(OrderState.viewing_cart_to_restaurant)

    except Exception as e:
        logging.error(f"Error in view_basket_selection: {e}")
        await message.answer(
            "Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
            reply_markup=await main_menu()
        )
        await state.clear()
        
@router.message(lambda message: message.text == "🛒 Savatim", StateFilter(OrderState.viewing_cart))
async def view_basket(message: types.Message, state: FSMContext):
    try:
        items, error = await db.get_basket_items(message.from_user.id)
            
        if error:
            logging.error(f"Error getting basket items: {error}")
            await message.answer("Savatni ko'rsatishda xatolik yuz berdi.")
            return

        # Calculate totals and generate message
        response_text, total_items, total_sum = await calculate_basket_totals(items or [])

        # Generate keyboard based on basket contents
        keyboard = await generate_basket_keyboard(
            items=items, 
            is_empty=not bool(items)
        )

        # Send response with basket contents and keyboard
        await message.answer(
            text=response_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error in view_basket_selection_to_restaurant: {e}")
        await message.answer(
            "Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
            reply_markup=await main_menu()
        )
        await state.clear()

@router.callback_query(lambda c: c.data.startswith('remove_'))
async def remove_from_cart(callback: types.CallbackQuery, state: FSMContext):
    try:
        cart_id = int(callback.data.split('_')[1])
        success, error = await db.remove_from_cart(cart_id)
        
        if not error:
            await callback.answer("✅ Mahsulot savatdan o'chirildi")
            
            # Обновляем содержимое корзины
            items, error = await db.get_basket_items(callback.from_user.id)
            if error:
                await callback.message.answer("Savat ma'lumotlarini olishda xatolik")
                return
                
            if not items:
                await callback.message.edit_text(
                    "Sizning savatingiz bo'sh 🛒",
                    reply_markup=await generate_basket_keyboard([], is_empty=True)
                )
                return
                
            # Показываем обновленную корзину
            response_text, _, _ = await calculate_basket_totals(items)
            await callback.message.edit_text(
                response_text,
                reply_markup=await generate_basket_keyboard(items, is_empty=False)
            )
        else:
            await callback.answer(f"Xatolik: {error}", show_alert=True)
            
    except Exception as e:
        logging.error(f"Error removing item from cart: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.message(lambda message: message.text == "⬅️ Orqaga", StateFilter(OrderState.viewing_cart))
async def back_from_basket(message: types.Message, state: FSMContext):
    """Return to main menu from basket"""
    await state.clear()
    keyboard = await main_menu()
    await message.answer("Bosh menyu:", reply_markup=keyboard)

@router.message(lambda message: message.text == "⬅️ Orqaga", StateFilter(OrderState.viewing_cart_to_restaurant))
async def back_from_basket_restaurant(message: types.Message, state: FSMContext):
    """Return to restaurant menu from basket"""
    await state.set_state(OrderState.selecting_food)
    # Restore previous restaurant menu
    data = await state.get_data()
    restaurant = data.get('restaurant')
    category = data.get('category')
    if restaurant and category:
        buttons, _ = await create_eat_buttons(restaurant, category)
        await message.answer(f"Kategoriya: {category}", reply_markup=buttons)
    else:
        # Fallback to main menu if no restaurant data
        await state.clear()
        keyboard = await main_menu()
        await message.answer("Bosh menyu:", reply_markup=keyboard)
