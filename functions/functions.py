from keyboards.reply import main_menu
from aiogram import Dispatcher, Bot, types
from aiogram.fsm.context import FSMContext
import logging
from aiogram.filters import StateFilter
from states.states import OrderState
from keyboards.restaurants_buttons import *
from typing import Union
from keyboards.basket import *
from database.db import db
from sqlalchemy import text
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
import pytz
from datetime import datetime, time, timedelta

def is_restaurant_open(current_time: time, start_time: time, end_time: time) -> bool:
    if not all([current_time, start_time, end_time]):
        return False
        
    if end_time < start_time:
        return current_time >= start_time or current_time <= end_time
    
    return start_time <= current_time <= end_time

def get_next_open_time(current_time: time, start_time: time, end_time: time) -> str:
    if not all([current_time, start_time, end_time]):
        return "Ish vaqti noaniq"

    if is_restaurant_open(current_time, start_time, end_time):
        return ""

    # Format times for display
    start_str = start_time.strftime("%H:%M")
    
    # If current time is after closing, next opening is tomorrow
    if current_time > end_time:
        return f"Ertaga soat {start_str}"
    
    # If current time is before opening, opening is today
    if current_time < start_time:
        return f"Bugun soat {start_str}"
        
    return f"Ertaga soat {start_str}"

async def back_to_main_menu(message: types.Message, state: FSMContext):
    await state.clear()
    buttons = await main_menu()
    await message.answer("Asosiy menyu:", reply_markup=buttons)

async def back(message: types.Message, state: FSMContext):
    """
    Handle back button functionality to return to previous state
    """
    try:
        current_state = await state.get_state()
        data = await state.get_data()

        if current_state == OrderState.selecting_category:
            buttons, error = await create_restaurant_buttons()
            if error:
                await message.answer(error)
                await back_to_main_menu(message, state)
                return
                
            await state.set_state(OrderState.selecting_restaurant)
            await message.answer("Iltimos, restoran tanlang:", reply_markup=buttons)
            
        elif current_state == OrderState.selecting_food:
            # Return to category selection
            restaurant_name = data.get('restaurant')
            if not restaurant_name:
                logging.error("Restaurant name not found in state data")
                await back_to_main_menu(message, state)
                return
                
            buttons, error = await create_category_buttons(restaurant_name)
            if error:
                await message.answer(error)
                await back_to_main_menu(message, state)
                return
                
            await state.set_state(OrderState.selecting_category)
            await message.answer(f"Iltimos, kategoriyani tanlang:", reply_markup=buttons)
            
        else:
            # Default case - return to main menu
            await back_to_main_menu(message, state)
            
    except Exception as e:
        logging.error(f"Error in back function: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        await back_to_main_menu(message, state)

async def calculate_basket_totals(items):
    """Calculate basket totals including delivery costs"""
    try:
        if not items:
            return "Sizning savatingiz bo'sh 🛒", 0, 0

        session = await db.get_session()
        try:
            # Get current time in Tashkent
            tz = pytz.timezone('Asia/Tashkent')
            current_time = datetime.now(tz).time()
            
            # Get restaurant information including working hours
            rest_ids = list(set(item[4] for item in items if item[4] is not None))
            if not rest_ids:
                return "Xatolik: Restoran ma'lumotlari topilmadi", 0, 0
                
            query = text("""
                SELECT id, name, delivery_cost, startwork, endwork 
                FROM restaurants 
                WHERE id = ANY(:rest_ids)
            """)
            result = await session.execute(query, {"rest_ids": rest_ids})
            restaurants = {r[0]: {
                "name": r[1], 
                "delivery_cost": r[2] or 0,
                "startwork": r[3],
                "endwork": r[4]
            } for r in result}

            message = "🛒 Sizning savatingiz:\n\n"
            current_rest_id = None
            closed_restaurants = []
            total_sum = 0

            # Process items and check restaurant hours
            for item in sorted(items, key=lambda x: (x[4] or 0)):
                cart_id, name, quantity, price, rest_id = item
                
                if not all([name, quantity, price, rest_id]):
                    continue

                rest_info = restaurants.get(rest_id)
                if not rest_info:
                    continue

                is_open = is_restaurant_open(
                    current_time, 
                    rest_info['startwork'], 
                    rest_info['endwork']
                )

                if not is_open and rest_id not in closed_restaurants:
                    closed_restaurants.append(rest_id)
                    next_open = get_next_open_time(
                        current_time,
                        rest_info['startwork'],
                        rest_info['endwork']
                    )
                    message += f"\n⚠️ {rest_info['name']} hozir yopiq! {next_open} da ochiladi.\n"
                    continue

                try:
                    quantity = int(quantity)
                    price = float(price)
                    item_total = quantity * price
                    
                    if current_rest_id != rest_id:
                        current_rest_id = rest_id
                        message += f"\n🏪 {rest_info['name']}:\n"
                    
                    if rest_id not in closed_restaurants:
                        total_sum += item_total
                        message += f"  {name}\n    {quantity} x {price:,.0f} = {item_total:,.0f} so'm\n"
                    
                except (ValueError, TypeError) as e:
                    logging.error(f"Error processing item {name}: {e}")
                    continue

            # Add delivery costs for open restaurants only
            if restaurants:
                message += "\n🚚 Yetkazib berish:\n"
                delivery_total = 0
                for rest_id, rest_info in restaurants.items():
                    if rest_id not in closed_restaurants:
                        try:
                            delivery_cost = float(rest_info['delivery_cost'])
                            delivery_total += delivery_cost
                            message += f"  {rest_info['name']}: {delivery_cost:,.0f} so'm\n"
                        except (ValueError, TypeError) as e:
                            logging.error(f"Error processing delivery cost for restaurant {rest_info['name']}: {e}")
                            continue

                final_total = total_sum + delivery_total
                message += f"\n💵 Jami: {final_total:,.0f} so'm"

                if closed_restaurants:
                    message += "\n\n⚠️ Buyurtma berish uchun yopiq restoranlardan mahsulotlarni o'chirib tashlang!"

            return message, len(items), total_sum

        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error calculating basket totals: {e}")
        return "Savatni hisoblashda xatolik yuz berdi", 0, 0

async def view_basket(message: types.Message, state: FSMContext, show_simple_back: bool = False):
    """Show user's basket with items grouped by restaurant"""
    try:
        items, error = await db.get_basket_items(message.from_user.id)
        if error:
            await message.answer("Savat ma'lumotlarini olishda xatolik yuz berdi")
            return
        if not items:
            await message.answer(
                "Sizning savatingiz bo'sh 🛒",
                reply_markup=await generate_basket_keyboard([], is_empty=True)
            )
            return
        # Calculate totals and format message
        response_text, _, _ = await calculate_basket_totals(items)
        
        # Create keyboard with just back button if requested
        if show_simple_back:
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
                resize_keyboard=True
            )
        else:
            # Use existing keyboard with category/food buttons
            keyboard = await generate_basket_keyboard(items, is_empty=False)
        
        await message.answer(
            text=response_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error showing basket: {e}")
        await message.answer("Savatchani ko'rsatishda xatolik yuz berdi")

async def send_eat_info(message_or_callback: Union[types.Message, types.CallbackQuery], 
                       food_id: int,
                       quantity: int = 1) -> None:
    """Send food item information with image and inline keyboard"""
    try:
        eat = await db.select_eat_by_id(food_id)  # Новый метод в db
        if not eat:
            chat_id = (message_or_callback.from_user.id 
                      if isinstance(message_or_callback, types.CallbackQuery) 
                      else message_or_callback.chat.id)
            await message_or_callback.bot.send_message(
                chat_id=chat_id, 
                text="Kechirasiz, taom topilmadi."
            )
            return

        # Unpack eat details
        eat_id, name, description, image, price, restaurant_name, category_name = eat
        total_price = price * quantity
        image_path = f'images/{image}'

        # Format caption
        caption = (
            f"🍽 {name}\n\n"
            f"{description}\n\n"
            f"Narxi: {price:,} so'm\n"
            f"Soni: {quantity}\n"
            f"Umumiy: {total_price:,} so'm"
        )

        # Create inline keyboard with proper callback_data format
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➖", 
                        callback_data=f"decrease_{eat_id}_{quantity}"
                    ),
                    InlineKeyboardButton(
                        text=f"{quantity}", 
                        callback_data="quantity"
                    ),
                    InlineKeyboardButton(
                        text="➕", 
                        callback_data=f"increase_{eat_id}_{quantity}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🛒 Savatga qo'shish", 
                        callback_data=f"add_to_cart_{eat_id}_{quantity}"  # Формат: add_to_cart_[id]_[quantity]
                    )
                ]
            ]
        )

        if isinstance(message_or_callback, types.CallbackQuery):
            # Update existing message
            await message_or_callback.message.edit_caption(
                caption=caption,
                reply_markup=buttons
            )
        else:
            # Send new message with photo
            try:
                await message_or_callback.bot.send_photo(
                    chat_id=message_or_callback.chat.id,
                    photo=types.FSInputFile(image_path),
                    caption=caption,
                    reply_markup=buttons
                )
            except FileNotFoundError:
                logging.error(f"Image not found: {image_path}")
                await message_or_callback.answer(
                    "Kechirasiz, rasm topilmadi. Administrator bilan bog'laning."
                )
            except Exception as e:
                logging.error(f"Error sending photo: {e}")
                await message_or_callback.answer(
                    "Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
                )

    except Exception as e:
        logging.error(f"Error in send_eat_info: {e}")
        chat_id = (message_or_callback.from_user.id 
                  if isinstance(message_or_callback, types.CallbackQuery) 
                  else message_or_callback.chat.id)
        await message_or_callback.bot.send_message(
            chat_id=chat_id,
            text="Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
        )