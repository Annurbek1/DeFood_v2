from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton
import logging
from database.db import db
from sqlalchemy import text
from datetime import datetime
from states.states import OrderState
from geopy.distance import geodesic
from functions.functions import *
from typing import Optional
from core.bot import get_bot

CITY_CENTER_LATITUDE = 38.27559016902529
CITY_CENTER_LONGITUDE = 67.89505672163146
MAX_DISTANCE_KM = 15

async def show_orders(
    message: types.Message,
    telegram_id: int,
    state: FSMContext,
    page: int,
    edit_message: bool = False
):
    try:
        session = await db.get_session()
        try:
            # Get user's database ID
            query = text("""
                SELECT id FROM users WHERE telegram_id = :telegram_id
            """)
            result = await session.execute(query, {"telegram_id": telegram_id})
            user = result.fetchone()
            
            if not user:
                await message.answer("Foydalanuvchi topilmadi")
                await state.clear()
                return

            user_id = user[0]
            
            # Get last 6 orders with pagination
            query = text("""
                SELECT o.id, o.total, o.status, o.created_at 
                FROM orders o 
                WHERE o.user_id = :user_id
                ORDER BY o.created_at DESC
                LIMIT 6
            """)
            result = await session.execute(query, {"user_id": user_id})
            all_orders = result.fetchall()
            
            if not all_orders:
                await message.answer("Sizda hech qanday buyurtma yo'q")
                await state.clear()
                return

            # Calculate pagination
            orders_per_page = 3
            start_idx = (page - 1) * orders_per_page
            end_idx = start_idx + orders_per_page
            orders = all_orders[start_idx:end_idx]
            total_pages = (len(all_orders) + orders_per_page - 1) // orders_per_page

            # Format message
            orders_message = await format_orders_message(session, orders)

            # Create pagination keyboard
            markup = create_pagination_keyboard(page, total_pages)

            # Send or edit message
            if edit_message and hasattr(message, 'edit_text'):
                await message.edit_text(orders_message, reply_markup=markup)
            else:
                await message.answer(orders_message, reply_markup=markup)

        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error showing orders for user {telegram_id}: {e}")
        await message.answer("Buyurtmalarni ko'rsatishda xatolik yuz berdi")
        await state.clear()

async def format_orders_message(session, orders) -> str:
    status_mapping = {
        'pending': '🕔 Kutilmoqda',
        'completed': '✅ Tugallangan',
        'in_delivery': '🕐 Taom tayyorlanyapdi',
        'cancelled': '❌ Bekor qilindi',
        'accepted_by_delivery': '🚚 Yetkazuvchi tomonidan qabul qilindi'
    }

    message = "🛒 Sizning buyurtmalaringiz:\n\n"
    
    for order in orders:
        order_id, total_price, status, created_at = order
        
        # Get order items
        query = text("""
            SELECT f.name, oi.quantity
            FROM order_items oi 
            JOIN foods f ON oi.food_id = f.id 
            WHERE oi.order_id = :order_id
        """)
        result = await session.execute(query, {"order_id": order_id})
        items = result.fetchall()

        # Format order details
        message += (
            f"📝 Buyurtma #{order_id}\n"
            f"💰 Jami: {total_price:,.0f} so'm\n"
            f"📊 Holati: {status_mapping.get(status, status)}\n"
            f"📅 Sana: {created_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"🍽 Taomlar:\n"
        )
        
        for name, quantity in items:
            message += f"  • {name} x{quantity}\n"
        
        message += "\n"

    return message

def create_pagination_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton(
            text="⬅️ Oldingi",
            callback_data=f"orders_page_{current_page - 1}"
        ))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(
            text="Keyingi ➡️",
            callback_data=f"orders_page_{current_page + 1}"
        ))
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None

async def get_user_data(telegram_id: int):
    """Get user data from database"""
    session = await db.get_session()
    try:
        query = text("""
            SELECT id, phone_number 
            FROM users 
            WHERE telegram_id = :telegram_id
        """)
        result = await session.execute(query, {"telegram_id": telegram_id})
        return result.fetchone()
    finally:
        await session.close()

async def get_user_addresses(telegram_id: int) -> tuple[list | None, str | None]:
    """
    Get user addresses from database
    
    Args:
        telegram_id (int): User's Telegram ID
        
    Returns:
        tuple[list | None, str | None]: (addresses list, error message)
    """
    session = await db.get_session()
    try:
        # First get user's database ID
        user_query = text("""
            SELECT id 
            FROM users 
            WHERE telegram_id = :telegram_id
        """)
        result = await session.execute(user_query, {"telegram_id": telegram_id})
        user = result.fetchone()
        
        if not user:
            return None, "Foydalanuvchi topilmadi"
            
        # Then get user's addresses
        address_query = text("""
            SELECT a.id, a.address_name, a.latitude, a.longitude 
            FROM addresses a
            WHERE a.user_id = :user_id
            ORDER BY a.created_at DESC
        """)
        result = await session.execute(address_query, {"user_id": user[0]})
        addresses = result.fetchall()
        
        return addresses, None
        
    except Exception as e:
        logging.error(f"Error getting user addresses: {e}")
        return None, "Manzillarni olishda xatolik yuz berdi"
    finally:
        await session.close()

async def request_phone_number(message: Message, state: FSMContext):
    """Request phone number from user"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    await state.set_state(OrderState.waiting_for_phone)
    await message.answer(
        "Buyurtma berish uchun telefon raqamingizni yuboring:", 
        reply_markup=keyboard
    )

async def request_location(message: Message, state: FSMContext):
    """Request location from user"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    await state.set_state(OrderState.adding_new_address_location)
    await message.answer(
        "Yangi manzil uchun lokatsiyani yuboring:",
        reply_markup=keyboard
    )

async def show_address_selection(message: Message, addresses: list, state: FSMContext):
    """Show address selection keyboard"""
    keyboard_buttons = [
        [KeyboardButton(text=f"📍 {address[1]}")] for address in addresses
    ]
    keyboard_buttons.extend([
        [KeyboardButton(text="➕ Yangi manzil qo'shish")],
        [KeyboardButton(text="⬅️ Orqaga")]
    ])
    
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )
    await message.answer("Yetkazib berish uchun manzilni tanlang:", reply_markup=markup)
    await state.set_state(OrderState.selecting_delivery_address)

async def back(message: Message, state: FSMContext):
    """Handle back button logic for order process"""
    try:
        current_state = await state.get_state()
        
        if current_state == OrderState.waiting_for_phone:
            await view_basket(message, state)
            return
            
        elif current_state == OrderState.selecting_delivery_address:
            await view_basket(message, state)
            return
            
        elif current_state == OrderState.viewing_cart:
            await back_to_main_menu(message, state)
            return
            
        # Default fallback
        await back_to_main_menu(message, state)
        
    except Exception as e:
        logging.error(f"Error in back function: {e}")
        await back_to_main_menu(message, state)

async def validate_delivery_location(latitude: float, longitude: float) -> bool:
    """Check if delivery is possible to given coordinates"""
    try:
        user_location = (latitude, longitude)
        city_center = (CITY_CENTER_LATITUDE, CITY_CENTER_LONGITUDE)
        distance = geodesic(user_location, city_center).kilometers
        
        return distance <= MAX_DISTANCE_KM
        
    except Exception as e:
        logging.error(f"Error validating location: {e}")
        return False

async def process_address_selection(message: Message, state: FSMContext):
    """Process selected address for order"""
    try:
        address_name = message.text[2:]  # Remove 📍 prefix
        session = await db.get_session()
        
        try:
            query = text("""
                SELECT id FROM addresses 
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = :telegram_id)
                AND address_name = :address_name
            """)
            result = await session.execute(query, {
                "telegram_id": message.from_user.id,
                "address_name": address_name
            })
            address = result.fetchone()
            
            if address:
                await state.update_data(selected_address_id=address[0])
                await complete_order_process(message, message.from_user.id, state)
            else:
                await message.answer("Manzil topilmadi")
                
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error processing address selection: {e}")
        await message.answer("Xatolik yuz berdi")

async def save_address(user_id: int, address_name: str, state_data: dict) -> Optional[int]:
    """Save new address and return its ID"""
    session = await db.get_session()
    try:
        # Get user's database ID
        query = text("SELECT id FROM users WHERE telegram_id = :telegram_id")
        result = await session.execute(query, {"telegram_id": user_id})
        user = result.fetchone()
        
        if not user:
            return None
            
        # Insert new address
        query = text("""
            INSERT INTO addresses (user_id, address_name, latitude, longitude)
            VALUES (:user_id, :address_name, :latitude, :longitude)
            RETURNING id
        """)
        result = await session.execute(query, {
            "user_id": user[0],
            "address_name": address_name,
            "latitude": state_data.get('new_address_latitude'),
            "longitude": state_data.get('new_address_longitude')
        })
        await session.commit()
        
        new_address = result.fetchone()
        return new_address[0] if new_address else None
        
    except Exception as e:
        logging.error(f"Error saving address: {e}")
        return None
    finally:
        await session.close()

async def complete_order_process(message: Message, telegram_id: int, state: FSMContext):
    """Process order completion with phone verification and messaging options"""
    try:
        # 1. Запрашиваем номер телефона (обязательно)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
            resize_keyboard=True
        )
        await message.answer(
            "Buyurtmani tasdiqlash uchun telefon raqamingizni yuboring:", 
            reply_markup=keyboard
        )
        await state.set_state(OrderState.confirming_phone)
        
    except Exception as e:
        logging.error(f"Error starting order process: {e}")
        await message.answer("Xatolik yuz berdi")
        await state.clear()

async def process_order_phone(message: Message, state: FSMContext):
    """Handle phone number submission and show address selection"""
    try:
        if not message.contact or not message.contact.phone_number:
            await message.answer("Iltimos, telefon raqamingizni yuboring")
            return

        # Сохраняем номер телефона
        phone_number = message.contact.phone_number
        await state.update_data(phone_number=phone_number)

        # Получаем существующие адреса пользователя
        addresses = await get_user_addresses(message.from_user.id)
        
        # Создаем клавиатуру с адресами
        keyboard_buttons = []
        if addresses:
            for addr in addresses:
                keyboard_buttons.append([KeyboardButton(text=f"📍 {addr[1]}")])
        
        keyboard_buttons.extend([
            [KeyboardButton(text="➕ Yangi manzil qo'shish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ])
        
        markup = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
        
        if addresses:
            text = "Mavjud manzillardan birini tanlang yoki yangi manzil qo'shing:"
        else:
            text = "Sizda saqlangan manzillar yo'q. Yangi manzil qo'shing:"
            
        await message.answer(text, reply_markup=markup)
        await state.set_state(OrderState.selecting_delivery_address)
        
    except Exception as e:
        logging.error(f"Error processing phone: {e}")
        await message.answer("Xatolik yuz berdi")

async def finalize_order(message: Message, state: FSMContext):
    """Final order processing and notifications"""
    session = await db.get_session()
    try:
        state_data = await state.get_data()
        
        # Create order in DB with session
        order_id = await create_order_in_db(
            telegram_id=message.from_user.id,
            state_data=state_data,
            session=session  # Передаем session явно
        )
        
        if not order_id:
            await message.answer("Buyurtmani saqlashda xatolik yuz berdi")
            return

        # Ask about message for restaurant
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Restoranga xabar yuborish",
                    callback_data=f"msg_rest_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Keyingisi",
                    callback_data=f"skip_rest_msg_{order_id}"
                )
            ]
        ])
        
        await message.answer(
            "Buyurtmangiz qabul qilindi! ✅\n"
            "Restoranga xabar yubormoqchimisiz?",
            reply_markup=keyboard
        )
        
        await state.set_state(OrderState.waiting_restaurant_message)
        
    except Exception as e:
        logging.error(f"Error finalizing order: {e}")
        await message.answer("Buyurtmani yakunlashda xatolik yuz berdi")
        await state.clear()
    finally:
        await session.close()
        
async def send_order_to_restaurant(order_id: int, customer_message: str = None):
    bot = get_bot()
    """Send order notification to restaurant group"""
    try:
        session = await db.get_session()
        try:
            # Получаем данные заказа и чата ресторана
            query = text("""
                SELECT o.*, r.restaurant_chat_id, r.name as restaurant_name
                FROM orders o
                JOIN foods f ON f.id = (
                    SELECT food_id FROM order_items 
                    WHERE order_id = o.id LIMIT 1
                )
                JOIN restaurants r ON r.id = f.restaurant_id
                WHERE o.id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            order_data = result.fetchone()
            
            if not order_data or not order_data.restaurant_chat_id:
                raise Exception("Restaurant chat ID not found")
                
            # Формируем сообщение
            message_text = (
                f"🆕 Yangi buyurtma #{order_id}\n"
                f"Telefon: {order_data.phone_number}\n"
                f"Summa: {order_data.total:,.0f} so'm\n"
            )
            
            if customer_message:
                message_text += f"\n💬 Xabar: {customer_message}"
                
            # Отправляем в группу ресторана
            await bot.send_message(
                chat_id=order_data.restaurant_chat_id,
                text=message_text
            )
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error sending order to restaurant: {e}")

async def save_phone_number(telegram_id: int, phone_number: str) -> bool:
    """Save or update user's phone number"""
    session = await db.get_session()
    try:
        query = text("""
            UPDATE users 
            SET phone_number = :phone_number
            WHERE telegram_id = :telegram_id
            RETURNING id
        """)
        result = await session.execute(query, {
            "telegram_id": telegram_id,
            "phone_number": phone_number
        })
        await session.commit()
        
        return bool(result.fetchone())
        
    except Exception as e:
        logging.error(f"Error saving phone number: {e}")
        return False
    finally:
        await session.close()

async def request_address_name(message: Message, state: FSMContext):
    """Request name for new address"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )
    await message.answer(
        "Iltimos, yangi manzil uchun nom bering\n"
        "Masalan: Uy, Ish, Do'stim uyida", 
        reply_markup=keyboard
    )
    await state.set_state(OrderState.adding_new_address_name)

async def create_order_in_db(telegram_id: int, state_data: dict, session) -> Optional[int]:
    """Create new order in database and return order ID"""
    try:
        # Get user's database ID
        query = text("""
            SELECT id FROM users 
            WHERE telegram_id = :telegram_id
        """)
        result = await session.execute(query, {"telegram_id": telegram_id})
        user = result.fetchone()
        if not user:
            return None

        user_id = user[0]

        # Get cart items and calculate total
        query = text("""
            SELECT c.food_id, c.quantity, f.price, f.restaurant_id
            FROM cart c
            JOIN foods f ON c.food_id = f.id
            WHERE c.user_id = :user_id
        """)
        result = await session.execute(query, {"user_id": user_id})
        cart_items = result.fetchall()

        if not cart_items:
            return None

        # Get address coordinates
        address_id = state_data.get('selected_address_id')
        query = text("""
            SELECT latitude, longitude 
            FROM addresses 
            WHERE id = :address_id
        """)
        result = await session.execute(query, {"address_id": address_id})
        address = result.fetchone()
        if not address:
            return None

        # Calculate order total and get restaurant_id (берем из первого товара)
        total_sum = 0
        restaurant_id = cart_items[0][3]  # Берем restaurant_id из первого товара
        
        for _, quantity, price, _ in cart_items:
            total_sum += quantity * price

        # Add delivery cost
        query = text("SELECT delivery_cost FROM restaurants WHERE id = :rest_id")
        result = await session.execute(query, {"rest_id": restaurant_id})
        delivery_cost = result.fetchone()
        if delivery_cost and delivery_cost[0]:
            total_sum += float(delivery_cost[0])

        # Create new order with restaurant_id
        query = text("""
            INSERT INTO orders (
                user_id, 
                total, 
                status,
                phone_number,
                latitude,
                longitude,
                restaurant_id,
                restaurant_message,
                delivery_message, 
                created_at
            ) VALUES (
                :user_id,
                :total,
                'pending',
                :phone_number,
                :latitude,
                :longitude,
                :restaurant_id,
                :restaurant_message,
                :delivery_message,
                CURRENT_TIMESTAMP
            ) RETURNING id
        """)
        
        result = await session.execute(query, {
            "user_id": user_id,
            "total": total_sum,
            "phone_number": state_data.get('phone_number'),
            "latitude": address.latitude,
            "longitude": address.longitude,
            "restaurant_id": restaurant_id,
            "restaurant_message": state_data.get('restaurant_message'),
            "delivery_message": state_data.get('delivery_message')
        })
        order = result.fetchone()
        if not order:
            return None

        order_id = order[0]

        # Add order items
        query = text("""
            INSERT INTO order_items (
                order_id, 
                food_id, 
                quantity, 
                price,
                status
            ) VALUES (
                :order_id,
                :food_id,
                :quantity,
                :price,
                'pending'
            )
        """)

        for food_id, quantity, price, _ in cart_items:
            await session.execute(query, {
                "order_id": order_id,
                "food_id": food_id,
                "quantity": quantity,
                "price": price
            })

        # Clear user's cart
        query = text("DELETE FROM cart WHERE user_id = :user_id")
        await session.execute(query, {"user_id": user_id})

        await session.commit()
        return order_id

    except Exception as e:
        logging.error(f"Error creating order: {e}")
        await session.rollback()
        return None

async def request_restaurant_message(message: Message, state: FSMContext):
    """Request message for restaurant"""
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ O'tkazib yuborish")],
        [KeyboardButton(text="⬅️ Orqaga")]
    ], resize_keyboard=True)
    
    await message.answer(
        "Restoran uchun xabar qoldiring yoki o'tkazib yuboring:\n"
        "(Masalan: Ovqatni o'tkir qilmang)",
        reply_markup=keyboard
    )
    await state.set_state(OrderState.waiting_restaurant_message)

async def format_order_confirmation(telegram_id: int, state_data: dict) -> str:
    """Format order details for confirmation"""
    try:
        items, _ = await db.get_basket_items(telegram_id)
        message = "📝 Buyurtmangizni tasdiqlang:\n\n"
        
        # Add items and total
        total = 0
        current_restaurant = None
        
        for _, name, quantity, price, rest_id in items:
            if current_restaurant != rest_id:
                restaurant_name = await get_restaurant_name(rest_id)
                message += f"\n🏪 {restaurant_name}:\n"
                current_restaurant = rest_id
            
            item_total = quantity * price
            total += item_total
            message += f"  • {name} x{quantity} = {item_total:,.0f} so'm\n"

        # Add delivery costs
        delivery_total = await calculate_delivery_cost(items)
        message += f"\n🚚 Yetkazib berish: {delivery_total:,.0f} so'm"
        
        # Add messages if exist
        if state_data.get('restaurant_message'):
            message += f"\n\n💬 Restoranga xabar: {state_data['restaurant_message']}"
        if state_data.get('delivery_message'):
            message += f"\n🚚 Yetkazib beruvchiga xabar: {state_data['delivery_message']}"
            
        message += f"\n\n💵 Jami: {total + delivery_total:,.0f} so'm"
        
        return message
        
    except Exception as e:
        logging.error(f"Error formatting order confirmation: {e}")
        return "Buyurtma ma'lumotlarini ko'rsatishda xatolik"

async def send_order_notifications(order_id: int, state_data: dict):
    """Send notifications to restaurant chat"""
    try:
        session = await db.get_session()
        try:
            # Get order and restaurant details
            query = text("""
                SELECT o.id, o.total, o.phone_number, o.latitude, o.longitude,
                       r.restaurant_chat_id, r.name as restaurant_name
                FROM orders o
                JOIN restaurants r ON o.restaurant_id = r.id
                WHERE o.id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            order_data = result.fetchone()
            if not order_data or not order_data.restaurant_chat_id:
                raise Exception("Restaurant chat ID not found")
            # Get order items
            query = text("""
                SELECT f.name, oi.quantity, oi.price
                FROM order_items oi
                JOIN foods f ON oi.food_id = f.id
                WHERE oi.order_id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            items = result.fetchall()
            # Format message
            message_text = (
                f"🆕 Yangi buyurtma #{order_id}\n"
                f"📞 Telefon: {order_data.phone_number}\n"
                f"💰 Summa: {order_data.total:,.0f} so'm\n\n"
                "🍽 Buyurtma tarkibi:\n"
            )
            for name, quantity, price in items:
                message_text += f"• {name} x{quantity} = {quantity * price:,.0f} so'm\n"
            if state_data.get('restaurant_message'):
                message_text += f"\n💬 Xabar: {state_data['restaurant_message']}"
            bot = get_bot()
            print('bot')
            if order_data.latitude and order_data.longitude:
                maps_link = f"https://www.google.com/maps?q={order_data.latitude},{order_data.longitude}"
                message_text += f"\n📍 Manzil: {maps_link}\n"
            # Send order details
            await bot.send_message(
                chat_id=order_data.restaurant_chat_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_order_{order_id}")],
                    [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_order_{order_id}")]
                ])
            )
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error sending order notifications: {e}")

async def calculate_delivery_cost(items) -> float:
    """Calculate total delivery cost for all restaurants in order"""
    try:
        session = await db.get_session()
        total_delivery = 0
        
        try:
            # Get unique restaurant IDs from items
            restaurant_ids = set(item[4] for item in items if item[4])
            
            if not restaurant_ids:
                return 0
            
            # Get delivery costs
            query = text("""
                SELECT delivery_cost 
                FROM restaurants 
                WHERE id = ANY(:rest_ids)
            """)
            result = await session.execute(query, {"rest_ids": list(restaurant_ids)})
            
            # Sum up delivery costs
            for (delivery_cost,) in result:
                if delivery_cost:
                    total_delivery += float(delivery_cost)
                    
            return total_delivery
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error calculating delivery cost: {e}")
        return 0

async def get_restaurant_name(restaurant_id: int) -> str:
    """Get restaurant name by ID"""
    try:
        session = await db.get_session()
        try:
            query = text("""
                SELECT name 
                FROM restaurants 
                WHERE id = :rest_id
            """)
            result = await session.execute(query, {"rest_id": restaurant_id})
            restaurant = result.fetchone()
            
            return restaurant[0] if restaurant else "Restaurant"
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error getting restaurant name: {e}")
        return "Restaurant"

async def save_notification(order_id: int, message_id: int, chat_id: int, type: str):
    """Save notification message details"""
    try:
        session = await db.get_session()
        try:
            query = text("""
                INSERT INTO delivery_messages 
                (order_id, message_id, chat_id, type)
                VALUES (:order_id, :message_id, :chat_id, :type)
            """)
            await session.execute(query, {
                "order_id": order_id,
                "message_id": message_id,
                "chat_id": chat_id,
                "type": type
            })
            await session.commit()
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error saving notification: {e}")

async def get_address_id(telegram_id: int, address_name: str) -> Optional[int]:
    """Get address ID by name and user's telegram ID"""
    try:
        session = await db.get_session()
        try:
            query = text("""
                SELECT a.id 
                FROM addresses a
                JOIN users u ON a.user_id = u.id
                WHERE u.telegram_id = :telegram_id
                AND a.address_name = :address_name
            """)
            result = await session.execute(query, {
                "telegram_id": telegram_id,
                "address_name": address_name
            })
            address = result.fetchone()
            
            return address[0] if address else None
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error getting address ID: {e}")
        return None

async def group_cart_items_by_restaurant(user_id: int, session) -> dict:
    """Group cart items by restaurant"""
    query = text("""
        SELECT 
            c.id as cart_id,
            c.quantity,
            f.name as food_name,
            f.price,
            r.id as restaurant_id,
            r.name as restaurant_name,
            r.restaurant_chat_id
        FROM cart c
        JOIN foods f ON c.food_id = f.id
        JOIN restaurants r ON f.restaurant_id = r.id
        WHERE c.user_id = (SELECT id FROM users WHERE telegram_id = :user_id)
    """)
    result = await session.execute(query, {"user_id": user_id})
    items = result.fetchall()
    
    grouped_items = {}
    for item in items:
        if item.restaurant_id not in grouped_items:
            grouped_items[item.restaurant_id] = {
                'items': [],
                'restaurant_name': item.restaurant_name,
                'restaurant_chat_id': item.restaurant_chat_id,  # Store restaurant_chat_id
                'total': 0
            }
        
        item_total = item.price * item.quantity
        grouped_items[item.restaurant_id]['items'].append({
            'cart_id': item.cart_id,
            'name': item.food_name,
            'quantity': item.quantity,
            'price': item.price,
            'total': item_total
        })
        grouped_items[item.restaurant_id]['total'] += item_total
    
    return grouped_items

async def create_restaurant_order(
    user_id: int, 
    restaurant_data: dict, 
    state_data: dict, 
    session
) -> int:
    """Create order for specific restaurant"""
    try:
        # Get user record ID
        user_query = text("SELECT id FROM users WHERE telegram_id = :telegram_id")
        user_result = await session.execute(user_query, {"telegram_id": user_id})
        user_record = user_result.fetchone()
        
        if not user_record:
            return None

        # Get address coordinates
        address_query = text("""
            SELECT latitude, longitude 
            FROM addresses 
            WHERE id = :address_id
        """)
        address_result = await session.execute(address_query, {
            "address_id": state_data.get('selected_address_id')
        })
        address = address_result.fetchone()
            
        # Insert order
        order_query = text("""
            INSERT INTO orders (
                user_id, restaurant_id, status, total,
                phone_number, latitude, longitude, 
                restaurant_message, delivery_message
            )
            VALUES (
                :user_id, :restaurant_id, 'pending', :total,
                :phone_number, :latitude, :longitude,
                :restaurant_message, :delivery_message
            )
            RETURNING id
        """)
        
        order_result = await session.execute(order_query, {
            "user_id": user_record.id,
            "restaurant_id": restaurant_data['restaurant_id'],
            "total": restaurant_data['total'],
            "phone_number": state_data.get('phone_number'),
            "latitude": address.latitude if address else None,
            "longitude": address.longitude if address else None,
            "restaurant_message": state_data.get('restaurant_message'),
            "delivery_message": state_data.get('delivery_message')
        })
        
        order_id = order_result.fetchone().id
        
        # Create order items
        items_query = text("""
            INSERT INTO order_items (order_id, food_id, quantity, price)
            SELECT :order_id, c.food_id, c.quantity, f.price
            FROM cart c
            JOIN foods f ON c.food_id = f.id
            WHERE c.id = :cart_id
        """)
        
        for item in restaurant_data['items']:
            await session.execute(items_query, {
                "order_id": order_id,
                "cart_id": item['cart_id']
            })
        
        return order_id
        
    except Exception as e:
        logging.error(f"Error creating restaurant order: {e}")
        await session.rollback()
        return None