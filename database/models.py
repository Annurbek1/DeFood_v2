from sqlalchemy import *
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    full_name = Column(String(100))
    phone_number = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    addresses = relationship("Address", back_populates="user", cascade="all, delete")
    orders = relationship("Order", back_populates="user", cascade="all, delete")
    cart_items = relationship("Cart", back_populates="user", cascade="all, delete")

class Address(Base):
    __tablename__ = 'addresses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    address_name = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="addresses")

class Restaurant(Base):
    __tablename__ = 'restaurants'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    image = Column(Text)
    restaurant_chat_id = Column(BigInteger)
    delivery_chat_id = Column(BigInteger)
    admin_telegram_id = Column(BigInteger)  
    is_active = Column(Boolean, default=True)
    latitude = Column(Float)
    longitude = Column(Float)
    startwork = Column(Time)
    endwork = Column(Time)
    delivery_cost = Column(Float, default=0)
    categories = relationship("Category", back_populates="restaurant", cascade="all, delete")
    foods = relationship("Food", back_populates="restaurant", cascade="all, delete")

class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    restaurant_id = Column(Integer, ForeignKey('restaurants.id', ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=True)
    
    restaurant = relationship("Restaurant", back_populates="categories")
    foods = relationship("Food", back_populates="category", cascade="all, delete")

class Food(Base):
    __tablename__ = 'foods'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    image = Column(Text)
    price = Column(Float, nullable=False)
    restaurant_id = Column(Integer, ForeignKey('restaurants.id', ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id', ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=True)
    
    restaurant = relationship("Restaurant", back_populates="foods")
    category = relationship("Category", back_populates="foods")
    cart_items = relationship("Cart", back_populates="food", cascade="all, delete")
    order_items = relationship("OrderItem", back_populates="food", cascade="all, delete")

class Cart(Base):
    __tablename__ = 'cart'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    food_id = Column(Integer, ForeignKey('foods.id', ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1)
    
    user = relationship("User", back_populates="cart_items")
    food = relationship("Food", back_populates="cart_items")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'food_id', name='uix_user_food'),
    )

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default='pending')
    total = Column(Float, nullable=False)
    phone_number = Column(String(20))
    cancellation_reason = Column(String(255), nullable=True)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now()) 
    restaurant_id = Column(Integer, ForeignKey('restaurants.id', ondelete="SET NULL"))
    active_delivery_person_id = Column(Integer, ForeignKey('delivery_persons.id', ondelete="SET NULL"))
    restaurant_message = Column(String(255), nullable=True)
    delivery_message = Column(String(255), nullable=True)
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete")

class OrderItem(Base):
    __tablename__ = 'order_items'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete="CASCADE"), nullable=False)
    food_id = Column(Integer, ForeignKey('foods.id', ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String(50), default='pending')
    
    order = relationship("Order", back_populates="items")
    food = relationship("Food", back_populates="order_items")

class DeliveryPerson(Base):
    __tablename__ = 'delivery_persons'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BIGINT, unique=True, nullable=False)
    name = Column(String(100))
    phone_number = Column(String(20))
    busy = Column(Boolean, default=False)

class DeliveryMessage(Base):
    __tablename__ = 'delivery_messages'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete="CASCADE"), nullable=False)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(BIGINT, nullable=False)
    type = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    order = relationship("Order", back_populates="delivery_messages")