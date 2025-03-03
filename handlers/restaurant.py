from aiogram import types
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from aiogram.filters import StateFilter
from states.states import OrderState
from keyboards.reply import main_menu
from keyboards.restaurants_buttons import *
from functions.functions import *
from core.bot import get_bot
from aiogram.fsm.storage.base import StorageKey
from datetime import datetime, time
import pytz

router = Router()
@router.message(lambda msg: msg.text == "🚚 Ovqat buyurtma qilish", StateFilter(None))
async def choose_restaurant(message: types.Message, state: FSMContext):
    try:
        await state.set_state(OrderState.selecting_restaurant)
        buttons, error = await create_restaurant_buttons()
        
        if error:
            await message.answer(error)
            await state.clear()
            await message.answer("Bosh menyu:", reply_markup=await main_menu())
            return
            
        await message.answer("Iltimos, restoran tanlang:", reply_markup=buttons)
    except Exception as e:
        logging.error(f"Restaurant selection error: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        await state.clear()
        
@router.message(StateFilter(OrderState.selecting_restaurant))
async def handle_restaurant_selection(message: types.Message, state: FSMContext):
    try:
        if message.text in ["⬅️ Orqaga"]:
            await back_to_main_menu(message, state)
            return

        # Get current time in Tashkent
        tz = pytz.timezone('Asia/Tashkent')
        current_time = datetime.now(tz).time()

        session = await db.get_session()
        try:
            query = text("""
                SELECT name, description, startwork, endwork, delivery_cost 
                FROM restaurants 
                WHERE name = :restaurant_name AND is_active = true
            """)
            result = await session.execute(query, {"restaurant_name": message.text})
            restaurant_data = result.fetchone()
            
            if not restaurant_data:
                await message.answer("Restoran topilmadi.")
                await back_to_main_menu(message, state)
                return

            # Check if restaurant is open
            start_time = restaurant_data.startwork
            end_time = restaurant_data.endwork
            is_open = is_restaurant_open(current_time, start_time, end_time)

            # Format restaurant info
            info_text = f"🏪 {restaurant_data.name}\n\n"
            
            if restaurant_data.description:
                info_text += f"{restaurant_data.description}\n\n"
            
            # Add operating hours info
            info_text += f"⏰ Ish vaqti: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n"
            
            if restaurant_data.delivery_cost is not None:
                if restaurant_data.delivery_cost == 0:
                    info_text += "🚚 Yetkazib berish: Bepul\n"
                else:
                    info_text += f"🚚 Yetkazib berish: {restaurant_data.delivery_cost:,.0f} so'm\n"

            if not is_open:
                next_open = get_next_open_time(current_time, start_time, end_time)
                info_text += f"\n❌ Hozir yopiq!\n⏰ {next_open} da ochiladi."
                await message.answer(info_text)
                return

            # Get category buttons and continue only if restaurant is open
            buttons, error_message = await create_category_buttons(message.text)
            
            if error_message:
                logging.error(f"Error getting categories for {message.text}: {error_message}")
                await message.answer(error_message)
                await back_to_main_menu(message, state)
                return
            
            await state.update_data(restaurant=message.text)
            await message.answer(info_text)
            await message.answer("Iltimos, kategoriyani tanlang:", reply_markup=buttons)
            await state.set_state(OrderState.selecting_category)

        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error in restaurant selection: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        await back_to_main_menu(message, state)

def is_restaurant_open(current_time: time, start_time: time, end_time: time) -> bool:
    """Check if restaurant is currently open"""
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    else:  # Handle case when restaurant works past midnight
        return current_time >= start_time or current_time <= end_time

def get_next_open_time(current_time: time, start_time: time, end_time: time) -> str:
    """Get formatted string of when restaurant will next open"""
    if current_time > end_time:
        # If it's after closing time, opens tomorrow at start_time
        return f"Ertaga {start_time.strftime('%H:%M')}"
    else:
        # If it's before opening time today
        return start_time.strftime('%H:%M')

@router.message(StateFilter(OrderState.selecting_category))
async def choose_eat(message: types.Message, state: FSMContext):
    try:
        category_name = message.text
        
        # Handle basket view
        if message.text == "🛒 Savat":
            await view_basket(message, state)
            return
            
        # Handle back button
        if category_name == "⬅️ Orqaga":
            await back(message, state)
            return
            
        # Get restaurant name from state
        data = await state.get_data()
        restaurant_name = data.get('restaurant')
        
        if not restaurant_name:
            logging.error("Restaurant name not found in state data")
            await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
            await back_to_main_menu(message, state)
            return
            
        # Update state with selected category
        await state.update_data(category=category_name)
        
        # Get food items buttons for selected category
        buttons, error_message = await create_eat_buttons(restaurant_name, category_name)
        
        if error_message:
            logging.error(f"Error getting food items for {restaurant_name}/{category_name}: {error_message}")
            buttons, _ = await create_category_buttons(restaurant_name)
            await message.answer(
                "Kechirasiz, bu kategoriyada taomlar mavjud emas. Iltimos, boshqa kategoriyani tanlang:",
                reply_markup=buttons
            )
            return
            
        # Show food items menu
        await message.answer(
            f"Siz {category_name} kategoriyasini tanladingiz. Endi taom tanlang:",
            reply_markup=buttons
        )
        await state.set_state(OrderState.selecting_food)
        
    except Exception as e:
        logging.error(f"Error in choose_eat handler: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        await back_to_main_menu(message, state)
        
@router.message(StateFilter(OrderState.selecting_food))
async def handle_food_selection(message: types.Message, state: FSMContext):
    try:
        if message.text == "⬅️ Orqaga":
            await back(message, state)
            return
            
        if message.text == "🛒 Savat":
            await view_basket(message, state)
            return
            
        try:
            name, food_id = message.text.rsplit(" | ", 1)
            food_id = int(food_id)  # Преобразуем ID в число
        except ValueError:
            logging.error(f"Invalid food format: {message.text}")
            await message.answer("Noto'g'ri format. Iltimos qaytadan urinib ko'ring.")
            return
            
        # Отправляем информацию о блюде, используя ID вместо имени
        await send_eat_info(message, food_id=food_id)
        
    except Exception as e:
        logging.error(f"Error in food selection: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        
@router.callback_query(lambda c: c.data.startswith('increase_'))
async def increase_quantity(callback_query: types.CallbackQuery):
    try:
        # Parse callback data (format: increase_[eat_id]_[quantity])
        _, eat_id, current_quantity = callback_query.data.split('_')
        
        # Convert to appropriate types
        eat_id = int(eat_id)
        quantity = int(current_quantity) + 1
        
        # Update food info display with new quantity
        await send_eat_info(
            callback_query, 
            food_id=eat_id,
            quantity=quantity
        )
        
    except Exception as e:
        logging.error(f"Error in increase_quantity: {e}")
        await callback_query.answer(
            "Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
            show_alert=True
        )

@router.callback_query(lambda c: c.data.startswith('decrease_'))
async def decrease_quantity(callback_query: types.CallbackQuery):
    try:
        # Parse callback data (format: decrease_[eat_id]_[quantity])
        _, eat_id, current_quantity = callback_query.data.split('_')
        
        # Convert to appropriate types
        eat_id = int(eat_id)
        quantity = int(current_quantity) - 1
        
        # Check minimum quantity
        if quantity < 1:
            await callback_query.answer(
                "1 dan kam buyurtma berish mumkin emas!", 
                show_alert=True
            )
            return
            
        # Update food info display with new quantity
        await send_eat_info(
            callback_query, 
            food_id=eat_id,
            quantity=quantity
        )
        
    except Exception as e:
        logging.error(f"Error in decrease_quantity: {e}")
        await callback_query.answer(
            "Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.",
            show_alert=True
        )
        
@router.callback_query(lambda c: c.data.startswith('add_to_cart_'))
async def confirm_add_to_cart(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback_query.data.split('_')
        eat_id = int(parts[-2])
        quantity = int(parts[-1])
        success, error = await db.add_to_cart(
            user_id=callback_query.from_user.id,
            eat_id=eat_id,
            quantity=quantity
        )

        if not success:
            await callback_query.answer(error, show_alert=True)
            return

        await callback_query.answer("🛒 Mahsulot savatchaga qo'shildi!", show_alert=True)
        
        await callback_query.message.delete()

    except ValueError as ve:
        logging.error(f"Invalid callback data format: {callback_query.data}")
        await callback_query.answer("Xatolik: Noto'g'ri ma'lumot formati", show_alert=True)
    except Exception as e:
        logging.error(f"Error in confirm_add_to_cart: {e}")
        await callback_query.answer("Xatolik yuz berdi", show_alert=True)
        
        
@router.callback_query(lambda c: c.data.startswith('accept_order_'))
async def handle_order_acceptance(callback: types.CallbackQuery):
    """Handle order acceptance by restaurant"""
    try:
        order_id = int(callback.data.split('_')[2])
        session = await db.get_session()
        try:
            # Updated query without address join
            query = text("""
                SELECT 
                    o.id, o.user_id, o.total, o.phone_number,
                    o.latitude, o.longitude, o.delivery_message,
                    u.telegram_id, r.delivery_chat_id, r.name as restaurant_name
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN restaurants r ON o.restaurant_id = r.id
                WHERE o.id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            order_data = result.fetchone()

            if not order_data:
                await callback.answer("Buyurtma topilmadi", show_alert=True)
                return

            # Update order status
            update_query = text("""
                UPDATE orders 
                SET status = 'accepted' 
                WHERE id = :order_id
                RETURNING id
            """)
            await session.execute(update_query, {"order_id": order_id})
            await session.commit()

            # Notify customer
            bot = get_bot()
            await bot.send_message(
                chat_id=order_data.telegram_id,
                text=(
                    f"✅ Sizning #{order_id} raqamli buyurtmangiz "
                    f"{order_data.restaurant_name} tomonidan qabul qilindi!\n"
                    "🚗 Yetkazib beruvchi tayinlanishi kutilmoqda."
                )
            )

            # Format message for delivery group
            delivery_message = (
                f"🆕 Yangi buyurtma #{order_id}\n"
                f"🏪 Restoran: {order_data.restaurant_name}\n"
                f"📞 Telefon: {order_data.phone_number}\n"
                f"💰 Summa: {order_data.total:,.0f} so'm\n"
            )

            # Add Google Maps link if coordinates exist
            if order_data.latitude and order_data.longitude:
                maps_link = f"https://www.google.com/maps?q={order_data.latitude},{order_data.longitude}"
                delivery_message += f"\n📍 Manzil: {maps_link}"

            if order_data.delivery_message:
                delivery_message += f"\n💬 Xabar: {order_data.delivery_message}"

            # Send to delivery group with accept button
            await bot.send_message(
                chat_id=order_data.delivery_chat_id,
                text=delivery_message,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ Qabul qilish",
                        callback_data=f"accept_delivery_{order_id}"
                    )]
                ])
            )

            original_text = callback.message.text
            await callback.message.edit_text(
                f"{original_text}\n\n✅ Buyurtma qabul qilindi!",
                reply_markup=None  # Remove the buttons
            )
            await callback.answer("Buyurtma qabul qilindi", show_alert=True)

        except Exception as e:
            logging.error(f"Database error in order acceptance: {e}")
            await callback.answer("Xatolik yuz berdi", show_alert=True)
            await session.rollback()
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error handling order acceptance: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.callback_query(lambda c: c.data.startswith('cancel_order_'))
async def handle_order_cancellation(callback: types.CallbackQuery, state: FSMContext):
    """Handle order cancellation by restaurant"""
    try:
        order_id = int(callback.data.split('_')[2])
        session = await db.get_session()
        
        try:
            # Get order details including admin's telegram_id
            query = text("""
                SELECT 
                    o.id, o.user_id, o.total,
                    u.telegram_id, r.name as restaurant_name,
                    r.admin_telegram_id
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN restaurants r ON o.restaurant_id = r.id
                WHERE o.id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            order_data = result.fetchone()

            if not order_data:
                await callback.answer("Buyurtma topilmadi", show_alert=True)
                return

            admin_telegram_id = order_data.admin_telegram_id

            # Создаем новый FSMContext для админа
            admin_state = FSMContext(
                storage=state.storage,
                key=StorageKey(
                    chat_id=admin_telegram_id,
                    user_id=admin_telegram_id,
                    bot_id=state.key.bot_id
                )
            )

            # Сохраняем информацию в состоянии админа
            await admin_state.set_state(OrderState.waiting_cancel_reason)
            await admin_state.update_data({
                'canceling_order_id': order_id,
                'customer_telegram_id': order_data.telegram_id,
                'restaurant_name': order_data.restaurant_name,
                'original_message_id': callback.message.message_id,
                'group_chat_id': callback.message.chat.id
            })
            
            # Send message to admin's private chat
            bot = get_bot()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Bekor qilishni bekor qilish",
                    callback_data=f"cancel_cancellation_{order_id}"
                )]
            ])
            
            await bot.send_message(
                chat_id=admin_telegram_id,
                text=(
                    f"Iltimos, #{order_id} raqamli buyurtmani bekor qilish sababini yozing:\n"
                    "Masalan: Oshpaz kasal, Mahsulotlar qolmagan va h.k"
                ),
                reply_markup=keyboard
            )
            
            # Update message in group
            await callback.message.edit_text(
                f"{callback.message.text}\n\n❌ Buyurtma bekor qilinmoqda...",
                reply_markup=None
            )
            
            await callback.answer(
                "Iltimos, botga o'ting va bekor qilish sababini yozing", 
                show_alert=True
            )

        except Exception as e:
            logging.error(f"Database error in order cancellation: {e}")
            await callback.answer("Xatolik yuz berdi", show_alert=True)
            await session.rollback()
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error handling order cancellation: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.callback_query(lambda c: c.data.startswith('cancel_cancellation_'))
async def cancel_cancellation_process(callback: types.CallbackQuery, state: FSMContext):
    """Cancel the cancellation process"""
    try:
        order_id = int(callback.data.split('_')[2])
        state_data = await state.get_data()
        
        if not state_data or state_data.get('canceling_order_id') != order_id:
            await callback.answer("Bu buyurtma uchun bekor qilish jarayoni topilmadi", show_alert=True)
            return

        bot = get_bot()
        
        # Restore original message in group
        try:
            await bot.edit_message_text(
                chat_id=state_data['group_chat_id'],
                message_id=state_data['original_message_id'],
                text=state_data.get('original_message_text', "Buyurtma tiklandi"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_order_{order_id}")],
                    [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_order_{order_id}")]
                ])
            )
        except Exception as e:
            logging.error(f"Error restoring group message: {e}")

        # Delete the admin's message
        await callback.message.delete()
        
        await state.clear()
        await callback.answer("Buyurtmani bekor qilish bekor qilindi", show_alert=True)

    except Exception as e:
        logging.error(f"Error canceling cancellation: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.message(OrderState.waiting_cancel_reason, F.chat.type == "private")
async def handle_cancellation_reason(message: types.Message, state: FSMContext):
    """Process cancellation reason from admin's private chat"""
    try:
        # Get state data
        state_data = await state.get_data()
        if not state_data:
            await message.answer("Xatolik yuz berdi. Ma'lumotlar topilmadi.")
            return

        order_id = state_data.get('canceling_order_id')
        customer_telegram_id = state_data.get('customer_telegram_id')
        restaurant_name = state_data.get('restaurant_name')
        group_chat_id = state_data.get('group_chat_id')
        original_message_id = state_data.get('original_message_id')

        if not all([order_id, customer_telegram_id, restaurant_name]):
            await message.answer("Xatolik yuz berdi. Ma'lumotlar yetishmayapti.")
            return

        session = await db.get_session()
        try:
            # Verify admin permissions
            query = text("""
                SELECT r.admin_telegram_id 
                FROM orders o 
                JOIN restaurants r ON o.restaurant_id = r.id 
                WHERE o.id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            admin_data = result.fetchone()

            if not admin_data or admin_data[0] != message.from_user.id:
                await message.answer("Siz bu buyurtmani bekor qila olmaysiz.")
                return

            # Update order status
            update_query = text("""
                UPDATE orders 
                SET status = 'cancelled', 
                    cancellation_reason = :reason,
                    updated_at = NOW()
                WHERE id = :order_id
            """)
            await session.execute(update_query, {
                "reason": message.text,
                "order_id": order_id
            })
            await session.commit()

            bot = get_bot()

            # Notify customer
            await bot.send_message(
                chat_id=customer_telegram_id,
                text=(
                    f"😔 Kechirasiz, sizning #{order_id} raqamli buyurtmangiz "
                    f"{restaurant_name} tomonidan bekor qilindi.\n\n"
                    f"Sabab: {message.text}\n\n"
                    "Noqulaylik uchun uzr so'raymiz. "
                    "Iltimos, qaytadan buyurtma bering."
                )
            )

            # Update group message
            if group_chat_id and original_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=group_chat_id,
                        message_id=original_message_id,
                        text=(
                            f"❌ Buyurtma #{order_id} bekor qilindi.\n"
                            f"Sabab: {message.text}"
                        )
                    )
                except Exception as e:
                    logging.error(f"Error updating group message: {e}")

            # Confirm to admin
            await message.answer(
                f"✅ #{order_id} raqamli buyurtma bekor qilindi.\n"
                f"Mijozga xabar yuborildi."
            )
            
            # Clear state
            await state.clear()

        except Exception as e:
            logging.error(f"Database error in cancellation reason: {e}")
            await message.answer("Xatolik yuz berdi")
            await session.rollback()
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error processing cancellation reason: {e}")
        await message.answer("Xatolik yuz berdi")
        await state.clear()

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.selecting_restaurant)
async def back_from_restaurant_selection(message: types.Message, state: FSMContext):
    """Return to main menu from restaurant selection"""
    await state.clear()
    keyboard = await main_menu()
    await message.answer("Bosh menyu:", reply_markup=keyboard)

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.selecting_category)
async def back_from_category_selection(message: types.Message, state: FSMContext):
    """Return to restaurant selection"""
    await state.set_state(OrderState.selecting_restaurant)
    buttons, _ = await create_restaurant_buttons()
    await message.answer("Iltimos, restoran tanlang:", reply_markup=buttons)

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.selecting_food)
async def back_from_food_selection(message: types.Message, state: FSMContext):
    """Return to category selection"""
    data = await state.get_data()
    restaurant = data.get('restaurant')
    if restaurant:
        buttons, _ = await create_category_buttons(restaurant)
        await state.set_state(OrderState.selecting_category)
        await message.answer("Iltimos, kategoriya tanlang:", reply_markup=buttons)
    else:
        await state.clear()
        keyboard = await main_menu()
        await message.answer("Bosh menyu:", reply_markup=keyboard)