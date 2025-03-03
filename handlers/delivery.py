from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
from database.db import db
from sqlalchemy import text
from core.bot import get_bot

router = Router()

@router.callback_query(lambda c: c.data.startswith('accept_delivery_'))
async def handle_delivery_acceptance(callback: types.CallbackQuery):
    """Handle delivery acceptance by delivery person"""
    try:
        order_id = int(callback.data.split('_')[2])
        session = await db.get_session()
        
        try:
            # Get order details
            query = text("""
                SELECT 
                    o.id, o.total, o.phone_number, o.latitude, o.longitude,
                    o.delivery_message, o.restaurant_message,
                    u.telegram_id as customer_telegram_id,
                    r.name as restaurant_name,
                    r.latitude as restaurant_lat,
                    r.longitude as restaurant_lon
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

            # Update order with delivery person info
            update_query = text("""
                UPDATE orders 
                SET status = 'delivering',
                    active_delivery_person_id = (
                        SELECT id FROM delivery_persons 
                        WHERE telegram_id = :telegram_id
                    )
                WHERE id = :order_id
                RETURNING id
            """)
            await session.execute(
                update_query, 
                {
                    "telegram_id": callback.from_user.id,
                    "order_id": order_id
                }
            )

            # Get delivery person info
            delivery_query = text("""
                SELECT name, phone_number, telegram_id
                FROM delivery_persons
                WHERE telegram_id = :telegram_id
            """)
            delivery_result = await session.execute(
                delivery_query,
                {"telegram_id": callback.from_user.id}
            )
            delivery_person = delivery_result.fetchone()

            if not delivery_person:
                await callback.answer("Yetkazib beruvchi ma'lumotlari topilmadi", show_alert=True)
                return

            await session.commit()

            # Format detailed order info for delivery person
            delivery_info = (
                f"🆕 Yangi buyurtma #{order_id}\n"
                f"🏪 Restoran: {order_data.restaurant_name}\n"
                f"📞 Mijoz telefoni: {order_data.phone_number}\n"
                f"💰 Summa: {order_data.total:,.0f} so'm\n\n"
            )

            if order_data.restaurant_message:
                delivery_info += f"📝 Restoranga xabar: {order_data.restaurant_message}\n"

            if order_data.delivery_message:
                delivery_info += f"🚚 Yetkazib beruvchiga xabar: {order_data.delivery_message}\n"

            # Add restaurant location
            if order_data.restaurant_lat and order_data.restaurant_lon:
                rest_maps_link = f"https://www.google.com/maps?q={order_data.restaurant_lat},{order_data.restaurant_lon}"
                delivery_info += f"\n🏪 Restoran manzili: {rest_maps_link}"

            # Add customer location
            if order_data.latitude and order_data.longitude:
                cust_maps_link = f"https://www.google.com/maps?q={order_data.latitude},{order_data.longitude}"
                delivery_info += f"\n📍 Mijoz manzili: {cust_maps_link}"

            bot = get_bot()
            
            # Send info to delivery person's private chat
            await bot.send_message(
                chat_id=delivery_person.telegram_id,
                text=delivery_info,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ Men yetib keldim",
                        callback_data=f"arrived_{order_id}"
                    )]
                ])
            )

            # Send notification to customer
            customer_message = (
                f"🚚 Sizning #{order_id} raqamli buyurtmangiz yo'lga chiqdi!\n\n"
                f"Yetkazib beruvchi ma'lumotlari:\n"
                f"👤 Ism: {delivery_person.name}\n"
                f"📞 Telefon: {delivery_person.phone_number}"
            )
            
            await bot.send_message(
                chat_id=order_data.customer_telegram_id,
                text=customer_message
            )

            # Update original message in delivery group
            await callback.message.edit_text(
                f"{callback.message.text}\n\n✅ Buyurtma qabul qilindi!",
                reply_markup=None
            )

            await callback.answer("Buyurtma muvaffaqiyatli qabul qilindi!", show_alert=True)

        except Exception as e:
            logging.error(f"Database error in delivery acceptance: {e}")
            await callback.answer("Xatolik yuz berdi", show_alert=True)
            await session.rollback()
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error handling delivery acceptance: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)
        
@router.callback_query(lambda c: c.data.startswith('arrived_'))
async def handle_delivery_arrival(callback: types.CallbackQuery):
    """Handle delivery person arrival"""
    try:
        order_id = int(callback.data.split('_')[1])
        session = await db.get_session()
        
        try:
            # Get customer telegram ID
            query = text("""
                SELECT u.telegram_id
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE o.id = :order_id
            """)
            result = await session.execute(query, {"order_id": order_id})
            customer_data = result.fetchone()

            if not customer_data:
                await callback.answer("Buyurtma topilmadi", show_alert=True)
                return

            # Update order status
            update_query = text("""
                UPDATE orders 
                SET status = 'arrived'
                WHERE id = :order_id
            """)
            await session.execute(update_query, {"order_id": order_id})
            await session.commit()

            # Notify customer
            bot = get_bot()
            await bot.send_message(
                chat_id=customer_data.telegram_id,
                text=(
                    f"🎉 Sizning #{order_id} raqamli buyurtmangiz yetib keldi!\n"
                    "Iltimos, buyurtmani qabul qiling."
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ Buyurtmani qabul qildim",
                        callback_data=f"order_received_{order_id}"
                    )]
                ])
            )

            # Update message for delivery person
            await callback.message.edit_text(
                f"{callback.message.text}\n\n✅ Yetib kelganingiz haqida xabar yuborildi!",
                reply_markup=None
            )

        except Exception as e:
            logging.error(f"Database error in delivery arrival: {e}")
            await callback.answer("Xatolik yuz berdi", show_alert=True)
            await session.rollback()
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error handling delivery arrival: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)

@router.callback_query(lambda c: c.data.startswith('order_received_'))
async def handle_order_received(callback: types.CallbackQuery):
    """Handle order received confirmation from customer"""
    try:
        order_id = int(callback.data.split('_')[2])
        session = await db.get_session()
        
        try:
            # Update order status
            update_query = text("""
                UPDATE orders 
                SET status = 'completed'
                WHERE id = :order_id
            """)
            await session.execute(update_query, {"order_id": order_id})
            await session.commit()

            # Update message for customer
            await callback.message.edit_text(
                f"✅ #{order_id} raqamli buyurtma muvaffaqiyatli yakunlandi!\n"
                "Bizning xizmatdan foydalanganingiz uchun rahmat 😊"
            )

        except Exception as e:
            logging.error(f"Database error in order received: {e}")
            await callback.answer("Xatolik yuz berdi", show_alert=True)
            await session.rollback()
        finally:
            await session.close()

    except Exception as e:
        logging.error(f"Error handling order received: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)
