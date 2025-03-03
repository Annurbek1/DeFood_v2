from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging
from config import Config
from sqlalchemy.sql import text
from typing import Optional

class Database:
    def __init__(self):
        self._engine = None
        self._session_factory = None

    def _get_database_url(self):
        return f"postgresql+asyncpg://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}/{Config.DB_NAME}"

    async def connect(self):
        if not self._engine:
            try:
                self._engine = create_async_engine(
                    self._get_database_url(),
                    echo=False,
                    pool_size=20,
                    max_overflow=10
                )
                self._session_factory = sessionmaker(
                    self._engine, 
                    class_=AsyncSession,
                    expire_on_commit=False
                )
            except Exception as e:
                logging.error(f"Database connection error: {e}")
                raise

    async def get_session(self) -> AsyncSession:
        if not self._session_factory:
            await self.connect()
        return self._session_factory()

    async def add_or_update_user(self, telegram_id: int, username: str) -> tuple[bool, str | None]:
        """Add new user or update existing one"""
        session = await self.get_session()
        try:
            # Check if user exists
            query = text("""
                SELECT id FROM users 
                WHERE telegram_id = :telegram_id
            """)
            result = await session.execute(query, {"telegram_id": telegram_id})
            user = result.fetchone()

            if not user:
                # Insert new user
                query = text("""
                    INSERT INTO users (full_name, telegram_id, created_at) 
                    VALUES (:username, :telegram_id, CURRENT_TIMESTAMP)
                """)
                await session.execute(query, {
                    "username": username,
                    "telegram_id": telegram_id
                })
                await session.commit()
                logging.info(f"New user added: {username} ({telegram_id})")

            return True, None

        except Exception as e:
            logging.error(f"Error adding/updating user: {e}")
            return False, "Foydalanuvchi ma'lumotlarini saqlashda xatolik"
        finally:
            await session.close()
    
    async def get_restaurants(self):
        session = await self.get_session()
        try:
            query = text("SELECT id, name FROM restaurants WHERE is_active = true")
            result = await session.execute(query)
            return result.fetchall(), None
        except Exception as e:
            logging.error(f"Ошибка при получении ресторанов: {e}")
            return None, "Xatolik yuz berdi."
        finally:
            await session.close()

    async def get_categories(self, restaurant_name):
        session = await self.get_session()
        try:
            # Get restaurant ID with logging
            query = text("SELECT id FROM restaurants WHERE name = :name AND is_active = true")
            result = await session.execute(query, {"name": restaurant_name})
            restaurant = result.fetchone()
            
            if not restaurant:
                logging.warning(f"Restaurant not found: {restaurant_name}")
                return None, "Restoran topilmadi"
            
            # Get categories with logging
            query = text("""
                SELECT name 
                FROM categories
                WHERE restaurant_id = :restaurant_id 
                AND is_active = true
            """)
            result = await session.execute(query, {"restaurant_id": restaurant[0]})
            categories = result.fetchall()
            
            if not categories:
                logging.info(f"No categories found for restaurant: {restaurant_name}")
                return None, "Bu restoranda kategoriyalar mavjud emas"
                
            logging.info(f"Found {len(categories)} categories for restaurant {restaurant_name}")
            return categories, None
            
        except Exception as e:
            logging.error(f"Error getting categories: {e}")
            return None, "Xatolik yuz berdi"
        finally:
            await session.close()


    async def get_eats(self, restaurant_name, category_name):
        session = await self.get_session()
        try:
            # Get restaurant ID
            query = text("SELECT id FROM restaurants WHERE name = :name AND is_active = true")
            result = await session.execute(query, {"name": restaurant_name})
            restaurant = result.fetchone()
            
            if not restaurant:
                logging.warning(f"Restaurant not found: {restaurant_name}")
                return None, "Restoran topilmadi"
            
            # Get category ID and eats
            query = text("""
                SELECT f.id, f.name 
                FROM foods f
                JOIN categories c ON f.category_id = c.id
                WHERE f.restaurant_id = :restaurant_id 
                AND c.name = :category_name 
                AND f.is_active = true
            """)
            result = await session.execute(query, {
                "restaurant_id": restaurant[0],
                "category_name": category_name
            })
            eats = result.fetchall()
            
            if not eats:
                logging.info(f"No active eats found for category {category_name}")
                return None, "Bu kategoriyada taomlar mavjud emas"
                
            # Convert to namedtuple for easier access
            from collections import namedtuple
            Food = namedtuple('Food', 'id name')
            eats = [Food(id=eat[0], name=eat[1]) for eat in eats]
            
            return eats, None
            
        except Exception as e:
            logging.error(f"Error getting eats: {e}")
            return None, "Xatolik yuz berdi"
        finally:
            await session.close()

    async def get_basket_items(self, telegram_id: int):
        """Get user's basket items with restaurant information"""
        session = await self.get_session()
        try:
            query = text("""
                SELECT 
                    c.id,
                    f.name,
                    c.quantity,
                    f.price,
                    f.restaurant_id
                FROM cart c
                JOIN foods f ON c.food_id = f.id
                JOIN users u ON c.user_id = u.id
                WHERE u.telegram_id = :telegram_id
                AND f.is_active = true
                AND c.quantity > 0  -- Добавляем проверку на количество
                ORDER BY f.restaurant_id, f.name
            """)
            result = await session.execute(query, {"telegram_id": telegram_id})
            items = result.fetchall()
            
            if not items:
                return [], None
                
            return items, None
        except Exception as e:
            logging.error(f"Error getting basket items: {e}")
            return None, "Savatni olishda xatolik yuz berdi"
        finally:
            await session.close()
            
    async def select_eat_by_id(self, food_id: int):
        session = await self.get_session()
        try:
            query = text("""
                SELECT f.id, f.name, f.description, f.image, f.price,
                       r.name as restaurant_name, c.name as category_name
                FROM foods f
                JOIN restaurants r ON f.restaurant_id = r.id
                JOIN categories c ON f.category_id = c.id
                WHERE f.id = :food_id AND f.is_active = true
            """)
            result = await session.execute(query, {"food_id": food_id})
            eat = result.fetchone()
            
            if not eat:
                logging.warning(f"Food item not found: ID {food_id}")
                return None
                
            logging.info(f"Found food item: {eat.name}")
            return eat
            
        except Exception as e:
            logging.error(f"Error selecting eat by ID: {e}")
            return None
        finally:
            await session.close()
            
    async def close(self):
        if self._engine:
            await self._engine.dispose()
            
    async def add_to_cart(self, user_id: int, eat_id: int, quantity: int) -> tuple[bool, str | None]:
        """Add or update item in cart"""
        session = await self.get_session()
        try:
            # First get user's database id from telegram_id
            query = text("SELECT id FROM users WHERE telegram_id = :telegram_id")
            result = await session.execute(query, {"telegram_id": user_id})
            user = result.fetchone()
            
            if not user:
                return False, "Foydalanuvchi topilmadi"
                
            user_db_id = user[0]
            
            # Check if food exists and is active
            query = text("SELECT id FROM foods WHERE id = :food_id AND is_active = true")
            result = await session.execute(query, {"food_id": eat_id})
            if not result.fetchone():
                return False, "Kechirasiz, bu taom mavjud emas"
                
            # Add or update cart item
            query = text("""
                INSERT INTO cart (user_id, food_id, quantity) 
                VALUES (:user_id, :food_id, :quantity)
                ON CONFLICT (user_id, food_id) 
                DO UPDATE SET quantity = cart.quantity + :quantity
            """)
            
            await session.execute(query, {
                "user_id": user_db_id,
                "food_id": eat_id,
                "quantity": quantity
            })
            await session.commit()
            
            return True, None
            
        except Exception as e:
            logging.error(f"Error adding to cart: {e}")
            return False, "Savatga qo'shishda xatolik yuz berdi"
        finally:
            await session.close()

    async def remove_from_cart(self, cart_id: int) -> tuple[bool, str | None]:
        """Remove item from cart"""
        session = await self.get_session()
        try:
            query = text("""
                DELETE FROM cart 
                WHERE id = :cart_id
                RETURNING id
            """)
            result = await session.execute(query, {"cart_id": cart_id})
            deleted = result.fetchone()
            
            if not deleted:
                return False, "Mahsulot topilmadi"
                
            await session.commit()
            return True, None
            
        except Exception as e:
            logging.error(f"Error removing from cart: {e}")
            return False, "Savatdan o'chirishda xatolik yuz berdi"
        finally:
            await session.close()
            
    async def add_user_address(self, telegram_id: int, address_name: str, 
                         latitude: float, longitude: float) -> Optional[int]:
        """Add new address for user and return address ID"""
        session = await self.get_session()
        try:
            # Get user ID
            query = text("SELECT id FROM users WHERE telegram_id = :telegram_id")
            result = await session.execute(query, {"telegram_id": telegram_id})
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
                "latitude": latitude,
                "longitude": longitude
            })
            
            address_id = result.fetchone()[0]
            await session.commit()
            
            return address_id

        except Exception as e:
            logging.error(f"Error adding user address: {e}")
            await session.rollback()
            return None
        finally:
            await session.close()

db = Database()