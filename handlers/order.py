from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from states.states import OrderState
from functions.order_functions import *
import logging
from utils.distance import check_delivery_distance
from config import Config

router = Router()

@router.callback_query(lambda call: call.data == "complete_order")
async def start_order_process(callback: types.CallbackQuery, state: FSMContext):
    """Start order process by requesting phone number"""
    try:
        # Проверяем наличие товаров в корзине
        items, error = await db.get_basket_items(callback.from_user.id)
        if not items:
            await callback.answer("Savatingiz bo'sh!", show_alert=True)
            return

        # Удаляем сообщение с корзиной
        await callback.message.delete()

        # Запрашиваем номер телефона
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
            resize_keyboard=True
        )
        await callback.message.answer(
            "Buyurtma berish uchun telefon raqamingizni yuboring:", 
            reply_markup=keyboard
        )
        await state.set_state(OrderState.waiting_for_phone)
        
    except Exception as e:
        logging.error(f"Error starting order: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.message(OrderState.waiting_for_phone, F.contact)
async def handle_phone(message: types.Message, state: FSMContext):
    """Save phone and show address selection"""
    try:
        await state.update_data(phone_number=message.contact.phone_number)
        addresses, error = await get_user_addresses(message.from_user.id)
        
        if error:
            logging.error(f"Error getting addresses: {error}")
            await message.answer("Manzillarni olishda xatolik yuz berdi")
            return
            
        if not addresses:
            # Если у пользователя нет адресов, сразу предлагаем добавить новый
            await request_location(message, state)
            return
            
        await show_address_selection(message, addresses, state)
        await state.set_state(OrderState.waiting_for_address)
    except Exception as e:
        logging.error(f"Error handling phone: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(OrderState.adding_new_address_location, F.location)
async def handle_location(message: types.Message, state: FSMContext):
    """Handle received location and save as new address"""
    try:
        # Check if location is within delivery range
        user_location = (message.location.latitude, message.location.longitude)
        city_center = (CITY_CENTER_LATITUDE, CITY_CENTER_LONGITUDE)
        distance = geodesic(city_center, user_location).km

        if distance > Config.MAX_DISTANCE_KM:
            await message.answer(
                "Kechirasiz, bu manzil yetkazib berish doirasidan tashqarida. "
                "Iltimos boshqa manzil tanlang."
            )
            return

        # Save location temporarily in state
        await state.update_data(
            new_address_latitude=message.location.latitude,
            new_address_longitude=message.location.longitude
        )

        # Ask for address name
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
            resize_keyboard=True
        )
        
        await message.answer(
            "Iltimos, ushbu manzil uchun nom bering\n"
            "Masalan: Uy, Ish, Do'stim...", 
            reply_markup=keyboard
        )
        await state.set_state(OrderState.adding_new_address_name)

    except Exception as e:
        logging.error(f"Error handling location: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")

@router.message(OrderState.adding_new_address_name)
async def handle_address_name(message: types.Message, state: FSMContext):
    """Handle address name input"""
    try:
        if message.text == "⬅️ Orqaga":
            await back(message, state)
            return

        state_data = await state.get_data()
        latitude = state_data.get('new_address_latitude')
        longitude = state_data.get('new_address_longitude')

        if not (latitude and longitude):
            await message.answer("Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
            return

        # Save new address
        address_id = await db.add_user_address(
            message.from_user.id,
            message.text,
            latitude,
            longitude
        )

        if not address_id:
            await message.answer("Manzilni saqlashda xatolik yuz berdi")
            return

        await state.update_data(selected_address_id=address_id)
        # Request restaurant message after saving address
        await request_restaurant_message(message, state)

    except Exception as e:
        logging.error(f"Error saving address name: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(OrderState.waiting_for_address)
async def handle_address_selection(message: types.Message, state: FSMContext):
    """Handle address selection or request new address"""
    try:
        if message.text == "➕ Yangi manzil qo'shish":
            await request_location(message, state)
            return

        if message.text == "⬅️ Orqaga":
            await back(message, state)
            return

        if message.text.startswith("📍 "):
            address_id = await get_address_id(message.from_user.id, message.text[2:])
            if not address_id:
                await message.answer("Manzil topilmadi")
                return
                
            await state.update_data(selected_address_id=address_id)
            # Запрашиваем сообщение для ресторана
            await request_restaurant_message(message, state)
            
    except Exception as e:
        logging.error(f"Error in address selection: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(OrderState.waiting_restaurant_message)
async def handle_restaurant_message(message: types.Message, state: FSMContext):
    """Handle restaurant message and request delivery message"""
    try:
        if message.text != "⏭ O'tkazib yuborish":
            await state.update_data(restaurant_message=message.text)
            
        # Запрашиваем сообщение для доставщика
        keyboard = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="⏭ O'tkazib yuborish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ], resize_keyboard=True)
        
        await message.answer(
            "Yetkazib beruvchi uchun xabar qoldiring yoki o'tkazib yuboring:",
            reply_markup=keyboard
        )
        await state.set_state(OrderState.waiting_delivery_message)
        
    except Exception as e:
        logging.error(f"Error handling restaurant message: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(OrderState.waiting_delivery_message)
async def handle_delivery_message(message: types.Message, state: FSMContext):
    """Handle delivery message and show order confirmation"""
    try:
        if message.text != "⏭ O'tkazib yuborish":
            await state.update_data(delivery_message=message.text)
            
        # Показываем финальное подтверждение заказа
        state_data = await state.get_data()
        order_details = await format_order_confirmation(message.from_user.id, state_data)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order")]
        ])
        
        # Сохраняем message_id для последующего удаления
        confirm_msg = await message.answer(order_details, reply_markup=keyboard)
        await state.update_data(confirm_message_id=confirm_msg.message_id)
        await state.set_state(OrderState.confirming_order)
        
    except Exception as e:
        logging.error(f"Error handling delivery message: {e}")
        await message.answer("Xatolik yuz berdi")

@router.callback_query(lambda c: c.data == "confirm_order")
async def final_order_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """Create orders in database and send notifications"""
    session = await db.get_session()
    try:
        state_data = await state.get_data()
        grouped_items = await group_cart_items_by_restaurant(callback.from_user.id, session)
        
        if not grouped_items:
            await callback.answer("Savatingiz bo'sh!", show_alert=True)
            return
            
        created_orders = []
        for restaurant_id, restaurant_data in grouped_items.items():
            restaurant_data['restaurant_id'] = restaurant_id
            order_id = await create_restaurant_order(
                callback.from_user.id,
                restaurant_data,
                state_data,
                session
            )
            
            if order_id:
                created_orders.append({
                    'id': order_id,
                    'restaurant_name': restaurant_data['restaurant_name'],
                    'items': restaurant_data['items'],
                    'total': restaurant_data['total'],
                    'restaurant_chat_id': restaurant_data['restaurant_chat_id'] # Changed from admin_telegram_id
                })

        if not created_orders:
            await callback.answer("Buyurtmani saqlashda xatolik", show_alert=True)
            return

        # Clear cart after successful order creation
        await session.execute(
            text("DELETE FROM cart WHERE user_id = (SELECT id FROM users WHERE telegram_id = :telegram_id)"),
            {"telegram_id": callback.from_user.id}
        )
        await session.commit()

        bot = get_bot()
        # Send notifications for each order
        for order in created_orders:
            # Format order items
            items_text = "\n".join([
                f"📍 {item['name']} x{item['quantity']} = {item['total']:,.0f} so'm"
                for item in order['items']
            ])

            # Message for restaurant group
            restaurant_message = (
                f"🆕 Yangi buyurtma #{order['id']}\n\n"
                f"Buyurtma tarkibi:\n{items_text}\n\n"
                f"Umumiy summa: {order['total']:,.0f} so'm\n"
                f"📞 Tel: {state_data.get('phone_number')}\n"
            )

            if state_data.get('restaurant_message'):
                restaurant_message += f"💬 Xabar: {state_data['restaurant_message']}\n"

            # Send to restaurant group chat
            rest_msg = await bot.send_message(
                chat_id=order['restaurant_chat_id'], # Using restaurant_chat_id instead of admin_telegram_id
                text=restaurant_message,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ Qabul qilish",
                        callback_data=f"accept_order_{order['id']}"
                    )],
                    [InlineKeyboardButton(
                        text="❌ Bekor qilish",
                        callback_data=f"cancel_order_{order['id']}"
                    )]
                ])
            )

            # Save notification message for future reference
            await save_notification(
                order_id=order['id'],
                message_id=rest_msg.message_id,
                chat_id=order['restaurant_chat_id'],
                type='restaurant'
            )

        # Message for customer
        orders_text = ""
        total_sum = 0
        for order in created_orders:
            orders_text += (
                f"\n🏪 {order['restaurant_name']}\n"
                f"Buyurtma #{order['id']}\n"
                f"Summa: {order['total']:,.0f} so'm\n"
            )
            total_sum += order['total']

        await callback.message.answer(
            "✅ Buyurtmangiz muvaffaqiyatli qabul qilindi!\n"
            f"{orders_text}\n"
            f"Umumiy summa: {total_sum:,.0f} so'm\n\n"
            "Tez orada siz bilan bog'lanamiz!",
            reply_markup=await main_menu()
        )

        await state.clear()

    except Exception as e:
        logging.error(f"Error confirming orders: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)
        await session.rollback()
    finally:
        await session.close()
        
@router.callback_query(lambda c: c.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    """Cancel order process"""
    state_data = await state.get_data()
    if confirm_message_id := state_data.get('confirm_message_id'):
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=confirm_message_id
            )
        except Exception as e:
            logging.error(f"Error deleting confirmation message: {e}")
    await state.clear()
    await callback.message.answer(
        "Buyurtma bekor qilindi",
        reply_markup=await main_menu()
    )

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.waiting_for_phone)
async def back_from_phone(message: types.Message, state: FSMContext):
    """Return to basket view"""
    await state.set_state(OrderState.viewing_cart)
    await view_basket(message, state)

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.waiting_for_address)
async def back_from_address(message: types.Message, state: FSMContext):
    """Return to phone input"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True
    )
    await state.set_state(OrderState.waiting_for_phone)
    await message.answer("Buyurtma berish uchun telefon raqamingizni yuboring:", reply_markup=keyboard)

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.waiting_restaurant_message)
async def back_from_restaurant_message(message: types.Message, state: FSMContext):
    """Return to address selection"""
    addresses, _ = await get_user_addresses(message.from_user.id)
    await state.set_state(OrderState.waiting_for_address)
    await show_address_selection(message, addresses, state)

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.waiting_delivery_message)
async def back_from_delivery_message(message: types.Message, state: FSMContext):
    """Return to restaurant message"""
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ O'tkazib yuborish")],
        [KeyboardButton(text="⬅️ Orqaga")]
    ], resize_keyboard=True)
    await state.set_state(OrderState.waiting_restaurant_message)
    await message.answer("Restoran uchun xabar qoldiring yoki o'tkazib yuboring:", reply_markup=keyboard)

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.adding_new_address_location)
async def back_from_new_address_location(message: types.Message, state: FSMContext):
    """Return to address selection from new address location request"""
    try:
        # Get existing addresses
        addresses, error = await get_user_addresses(message.from_user.id)
        
        if error:
            logging.error(f"Error getting addresses: {error}")
            await message.answer("Manzillarni olishda xatolik yuz berdi")
            return

        # Show address selection or request phone if no addresses
        if addresses:
            await show_address_selection(message, addresses, state)
            await state.set_state(OrderState.waiting_for_address)
        else:
            # If user has no addresses, go back to phone input
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
                resize_keyboard=True
            )
            await state.set_state(OrderState.waiting_for_phone)
            await message.answer(
                "Buyurtma berish uchun telefon raqamingizni yuboring:", 
                reply_markup=keyboard
            )
            
    except Exception as e:
        logging.error(f"Error handling back from new address location: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(OrderState.handle_new_address_location, F.location)
async def handle_new_address_location(message: types.Message, state: FSMContext):
    """Handle location for new address"""
    try:
        # Check delivery distance
        is_deliverable, distance = check_delivery_distance(
            message.location.latitude,
            message.location.longitude
        )
        
        if not is_deliverable:
            await message.answer(
                f"❌ Kechirasiz, bu manzil yetkazib berish doirasidan tashqarida.\n"
                f"Maksimal masofa: {Config.MAX_DISTANCE_KM} km\n"
                f"Sizning manzilingizgacha: {distance:.1f} km\n\n"
                f"Iltimos, boshqa manzil tanlang."
            )
            return
            
        # Save location data in state
        await state.update_data(
            new_address_lat=message.location.latitude,
            new_address_lon=message.location.longitude
        )
        
        # Ask for address name
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
            resize_keyboard=True
        )
        
        await state.set_state(OrderState.handle_new_address_name)
        await message.answer(
            "Iltimos, bu manzil uchun nom bering:\n"
            "Masalan: Uy, Ish, Do'kon va h.k.",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error saving new address location: {e}")
        await message.answer("Xatolik yuz berdi")
