import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import Config
from handlers.user import router as user_router
from handlers.restaurant import router as restaurant_router
from handlers.basket import router as basket_router
from handlers.orders import router as orders_router
from handlers.order import router as order_router
from handlers.settings import router as settings_router
from handlers.delivery import router as delivery_router
from database.db import db
from core.bot import set_bot

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    Config.validate()

    storage = MemoryStorage()
    
    bot = Bot(token=Config.BOT_TOKEN)
    set_bot(bot)  # Set bot instance globally
    dp = Dispatcher(storage=storage)
    
    # Register routers
    dp.include_router(user_router)
    dp.include_router(restaurant_router)
    dp.include_router(basket_router)
    dp.include_router(orders_router)
    dp.include_router(order_router)
    dp.include_router(settings_router)
    dp.include_router(delivery_router)
    try:
        await db.connect()
        logging.info("Database connection established")
        
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Error during startup: {e}")
        raise
    finally:
        # Close database connection
        await db.close()
        
        # Close bot session
        if bot.session:
            await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")
    except Exception as e:
        logging.error(f"Error: {e}")