from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from states.states import OrderState
import logging
from functions.order_functions import show_orders

router = Router()

@router.message(lambda message: message.text == "🛒 Buyurtmalarim", StateFilter("*"))
async def my_orders_handler(message: types.Message, state: FSMContext):
    await state.set_state(OrderState.viewing_orders)
    await show_orders(message, message.from_user.id, state, page=1)

@router.callback_query(lambda c: c.data.startswith('orders_page_'))
async def process_orders_page(callback: types.CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.split('_')[-1])
        await show_orders(
            message=callback.message,
            telegram_id=callback.from_user.id,
            state=state,
            page=page,
            edit_message=True
        )
    except Exception as e:
        logging.error(f"Error processing orders page: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)
