from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from states.states import OrderState
from database.db import db
from sqlalchemy import text as atext
import logging
from keyboards.reply import *

router = Router()

@router.message(lambda message: message.text == "⚙️ Sozlamalar")
async def settings_menu(message: types.Message, state: FSMContext):
    """Handle settings menu"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
    await state.set_state(OrderState.viewing_settings)
    try:
        session = await db.get_session()
        try:
            # Get addresses
            query = atext("""
                SELECT a.id, a.address_name, a.latitude, a.longitude
                FROM addresses a
                JOIN users u ON a.user_id = u.id
                WHERE u.telegram_id = :telegram_id
                ORDER BY a.created_at DESC
            """)
            result = await session.execute(query, {"telegram_id": message.from_user.id})
            addresses = result.fetchall()
            
            # Create inline keyboard for addresses
            inline_keyboard = []
            
            if addresses:
                text = "📍 Sizning manzillaringiz:"
                for addr in addresses:
                    inline_keyboard.extend([
                        [InlineKeyboardButton(text=f"📍 {addr.address_name}", callback_data=f"show_address_{addr.id}")],
                        [
                            InlineKeyboardButton(text="✏️ O'zgartirish", callback_data=f"edit_address_{addr.id}"),
                            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_address_{addr.id}")
                        ]
                    ])
            else:
                text = "Sizda hali manzillar yo'q.\nYangi manzil qo'shish uchun quyidagi tugmani bosing:"

            # Add "Add new address" button
            inline_keyboard.append([
                InlineKeyboardButton(text="➕ Yangi manzil qo'shish", callback_data="add_new_address")
            ])
            
            # Create reply keyboard with back button
            reply_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="⬅️ Orqaga")]
                ],
                resize_keyboard=True
            )
            
            # First send the addresses with inline keyboard
            await message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
            )
            
            # Then send the back button as reply keyboard
            await message.answer(
                "Boshqa amallar uchun menu:",
                reply_markup=reply_keyboard
            )
            
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error in settings menu: {e}")
        await message.answer("Xatolik yuz berdi.")

@router.message(OrderState.viewing_settings, F.text == "📍 Mening manzillarim")
async def show_addresses(message: types.Message, state: FSMContext):
    """Show user's saved addresses"""
    try:
        session = await db.get_session()
        try:
            # Get user's addresses
            query = atext("""
                SELECT a.id, a.address_name, a.latitude, a.longitude
                FROM addresses a
                JOIN users u ON a.user_id = u.id
                WHERE u.telegram_id = :telegram_id
                ORDER BY a.created_at DESC
            """)
            result = await session.execute(query, {"telegram_id": message.from_user.id})
            addresses = result.fetchall()

            if not addresses:
                await message.answer(
                    "Sizda saqlangan manzillar yo'q.\n"
                    "Yangi manzil qo'shish uchun lokatsiyani yuboring:"
                )
                await state.set_state(OrderState.adding_new_address_location)
                return

            # Create inline keyboard with addresses
            address_buttons = []
            for addr in addresses:
                address_buttons.append([
                    InlineKeyboardButton(
                        text=f"📍 {addr.address_name}",
                        callback_data=f"address_{addr.id}"
                    ),
                    InlineKeyboardButton(
                        text="❌",
                        callback_data=f"delete_address_{addr.id}"
                    )
                ])

            address_buttons.append([
                InlineKeyboardButton(
                    text="➕ Yangi manzil qo'shish",
                    callback_data="add_new_address"
                )
            ])

            markup = InlineKeyboardMarkup(inline_keyboard=address_buttons)
            await message.answer("Sizning manzillaringiz:", reply_markup=markup)

        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error showing addresses: {e}")
        await message.answer("Manzillarni ko'rsatishda xatolik yuz berdi")

@router.callback_query(lambda c: c.data.startswith("show_address_"))
async def show_address_details(callback: types.CallbackQuery, state: FSMContext):
    """Show detailed address information"""
    try:
        address_id = int(callback.data.split("_")[2])
        session = await db.get_session()
        
        try:
            query = atext("""
                SELECT a.address_name, a.latitude, a.longitude
                FROM addresses a
                JOIN users u ON a.user_id = u.id
                WHERE a.id = :address_id AND u.telegram_id = :telegram_id
            """)
            result = await session.execute(query, {
                "address_id": address_id,
                "telegram_id": callback.from_user.id
            })
            address = result.fetchone()
            
            if not address:
                await callback.answer("Manzil topilmadi", show_alert=True)
                return
                
            # Send location
            await callback.message.answer_location(
                latitude=address.latitude,
                longitude=address.longitude
            )
            
            # Send address details
            await callback.message.answer(
                f"📍 Manzil: {address.address_name}\n"
                f"🌍 Lokatsiya: {address.latitude}, {address.longitude}"
            )
            
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error showing address details: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("edit_address_"))
async def edit_address_start(callback: types.CallbackQuery, state: FSMContext):
    """Start address editing process"""
    address_id = int(callback.data.split("_")[2])
    await state.update_data(editing_address_id=address_id)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani o'zgartirish")],
            [KeyboardButton(text="✏️ Nomini o'zgartirish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    
    await state.set_state(OrderState.editing_address)
    await callback.message.answer(
        "Manzilni tahrirlash uchun variantni tanlang:",
        reply_markup=keyboard
    )

async def create_address_keyboard(telegram_id: int) -> tuple[InlineKeyboardMarkup, str]:
    """Create keyboard with addresses and return appropriate message text"""
    session = await db.get_session()
    try:
        query = atext("""
            SELECT a.id, a.address_name, a.latitude, a.longitude
            FROM addresses a
            JOIN users u ON a.user_id = u.id
            WHERE u.telegram_id = :telegram_id
            ORDER BY a.created_at DESC
        """)
        result = await session.execute(query, {"telegram_id": telegram_id})
        addresses = result.fetchall()

        keyboard = []
        if addresses:
            text = "📍 Sizning manzillaringiz:"
            for addr in addresses:
                keyboard.extend([
                    [InlineKeyboardButton(text=f"📍 {addr.address_name}", callback_data=f"show_address_{addr.id}")],
                    [
                        InlineKeyboardButton(text="✏️ O'zgartirish", callback_data=f"edit_address_{addr.id}"),
                        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_address_{addr.id}")
                    ]
                ])
        else:
            text = "Sizda hali manzillar yo'q.\nYangi manzil qo'shish uchun quyidagi tugmani bosing:"

        keyboard.append([
            InlineKeyboardButton(text="➕ Yangi manzil qo'shish", callback_data="add_new_address")
        ])
        return InlineKeyboardMarkup(inline_keyboard=keyboard), text

    finally:
        await session.close()

@router.callback_query(lambda c: c.data.startswith("delete_address_"))
async def delete_address(callback: types.CallbackQuery, state: FSMContext):
    """Delete selected address and update keyboard"""
    try:
        address_id = int(callback.data.split("_")[2])
        session = await db.get_session()
        
        try:
            # Delete address
            query = atext("""
                DELETE FROM addresses
                WHERE id = :address_id 
                AND user_id = (
                    SELECT id FROM users 
                    WHERE telegram_id = :telegram_id
                )
                RETURNING id
            """)
            result = await session.execute(query, {
                "address_id": address_id,
                "telegram_id": callback.from_user.id
            })
            
            if result.fetchone():
                await session.commit()
                await callback.answer("Manzil o'chirildi", show_alert=True)
                
                # Create new keyboard and update message
                markup, text = await create_address_keyboard(callback.from_user.id)
                await callback.message.edit_text(text=text, reply_markup=markup)
            else:
                await callback.answer("Manzil topilmadi", show_alert=True)
                
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error deleting address: {e}")
        await callback.answer("Manzilni o'chirishda xatolik", show_alert=True)

@router.message(OrderState.handle_new_address_location, F.location)
async def handle_new_address_location(message: types.Message, state: FSMContext):
    """Handle location for new address"""
    try:
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

@router.message(OrderState.handle_new_address_name)
async def handle_new_address_name(message: types.Message, state: FSMContext):
    """Handle name for new address"""
    try:
        # Get location data from state
        state_data = await state.get_data()
        latitude = state_data.get('new_address_lat')
        longitude = state_data.get('new_address_lon')
        
        if not latitude or not longitude:
            await message.answer("Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring")
            await state.clear()
            return
            
        session = await db.get_session()
        try:
            # Get user_id from telegram_id
            user_query = atext("""
                SELECT id FROM users WHERE telegram_id = :telegram_id
            """)
            result = await session.execute(user_query, {"telegram_id": message.from_user.id})
            user_data = result.fetchone()
            
            if not user_data:
                await message.answer("Foydalanuvchi topilmadi")
                return
                
            # Insert new address
            insert_query = atext("""
                INSERT INTO addresses (user_id, address_name, latitude, longitude)
                VALUES (:user_id, :address_name, :latitude, :longitude)
            """)
            
            await session.execute(insert_query, {
                "user_id": user_data.id,
                "address_name": message.text,
                "latitude": latitude,
                "longitude": longitude
            })
            
            await session.commit()
            
            markup, text = await create_address_keyboard(message.from_user.id)
            await message.answer("✅ Yangi manzil qo'shildi!", reply_markup=markup)
            await state.set_state(OrderState.viewing_settings)
            
        except Exception as e:
            logging.error(f"Database error in adding new address: {e}")
            await session.rollback()
            await message.answer("Xatolik yuz berdi")
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error saving new address: {e}")
        await message.answer("Xatolik yuz berdi")

@router.callback_query(lambda c: c.data == "add_new_address")
async def add_new_address(callback: types.CallbackQuery, state: FSMContext):
    """Start new address addition process"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    await state.set_state(OrderState.handle_new_address_location)
    await callback.message.answer(
        "Yangi manzil uchun lokatsiyani yuboring:",
        reply_markup=keyboard
    )

@router.message(OrderState.editing_address, F.text == "📍 Lokatsiyani o'zgartirish")
async def edit_address_location_start(message: types.Message, state: FSMContext):
    """Start editing address location"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )
    await state.set_state(OrderState.editing_address_location)
    await message.answer("Yangi lokatsiyani yuboring:", reply_markup=keyboard)

@router.message(OrderState.editing_address, F.text == "✏️ Nomini o'zgartirish")
async def edit_address_name_start(message: types.Message, state: FSMContext):
    """Start editing address name"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )
    await state.set_state(OrderState.editing_address_name)
    await message.answer(
        "Yangi nomni kiriting:\n"
        "Masalan: Uy, Ish, Do'kon va h.k.",
        reply_markup=keyboard
    )

@router.message(OrderState.editing_address_location, F.location)
async def handle_edited_location(message: types.Message, state: FSMContext):
    """Handle new location for existing address"""
    try:
        state_data = await state.get_data()
        address_id = state_data.get('editing_address_id')
        
        if not address_id:
            await message.answer("Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring")
            return
            
        session = await db.get_session()
        try:
            # Update address location
            query = atext("""
                UPDATE addresses 
                SET latitude = :latitude, longitude = :longitude
                WHERE id = :address_id 
                AND user_id = (SELECT id FROM users WHERE telegram_id = :telegram_id)
                RETURNING id
            """)
            
            result = await session.execute(query, {
                "address_id": address_id,
                "telegram_id": message.from_user.id,
                "latitude": message.location.latitude,
                "longitude": message.location.longitude
            })
            
            if result.fetchone():
                await session.commit()
                markup, text = await create_address_keyboard(message.from_user.id)
                await message.answer("✅ Manzil lokatsiyasi o'zgartirildi!", reply_markup=markup)
                await state.set_state(OrderState.viewing_settings)
            else:
                await message.answer("Manzil topilmadi")
                
        except Exception as e:
            logging.error(f"Database error in updating address location: {e}")
            await session.rollback()
            await message.answer("Xatolik yuz berdi")
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error updating address location: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(OrderState.editing_address_name)
async def handle_edited_name(message: types.Message, state: FSMContext):
    """Handle new name for existing address"""
    try:
        if message.text == "⬅️ Orqaga":
            markup, text = await create_address_keyboard(message.from_user.id)
            await message.answer(text, reply_markup=markup)
            await state.set_state(OrderState.viewing_settings)
            return

        state_data = await state.get_data()
        address_id = state_data.get('editing_address_id')
        
        if not address_id:
            await message.answer("Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring")
            return
            
        session = await db.get_session()
        try:
            # Update address name
            query = atext("""
                UPDATE addresses 
                SET address_name = :address_name
                WHERE id = :address_id 
                AND user_id = (SELECT id FROM users WHERE telegram_id = :telegram_id)
                RETURNING id
            """)
            
            result = await session.execute(query, {
                "address_id": address_id,
                "telegram_id": message.from_user.id,
                "address_name": message.text
            })
            
            if result.fetchone():
                await session.commit()
                markup, text = await create_address_keyboard(message.from_user.id)
                await message.answer("✅ Manzil nomi o'zgartirildi!", reply_markup=markup)
                await state.set_state(OrderState.viewing_settings)
            else:
                await message.answer("Manzil topilmadi")
                
        except Exception as e:
            logging.error(f"Database error in updating address name: {e}")
            await session.rollback()
            await message.answer("Xatolik yuz berdi")
        finally:
            await session.close()
            
    except Exception as e:
        logging.error(f"Error updating address name: {e}")
        await message.answer("Xatolik yuz berdi")

@router.message(lambda msg: msg.text == "⬅️ Asosiy menyu", StateFilter("*"))
async def back_to_main_menu(message: types.Message, state: FSMContext):
    """Return to main menu from any state"""
    from keyboards.reply import main_menu
    await state.clear()
    await message.answer("Bosh menyu:", reply_markup=await main_menu())

@router.message(lambda message: message.text == "⬅️ Orqaga", OrderState.viewing_settings)
async def back_from_settings(message: types.Message, state: FSMContext):
    """Return to main menu from settings"""
    await state.clear()
    keyboard = await main_menu()
    await message.answer("Bosh menyu:", reply_markup=keyboard)