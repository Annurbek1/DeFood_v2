from dataclasses import dataclass
from environs import Env
import sys

@dataclass
class Config:
    env = Env()
    env.read_env()

    try:
        BOT_TOKEN = env.str("API_TOKEN")
        DB_HOST = env.str("DB_HOST")
        DB_USER = env.str("DB_USER")
        DB_PASSWORD = env.str("DB_PASSWORD")
        DB_NAME = env.str("DB_NAME")
        GOOGLE_MAPS_API_KEY = env.str("GOOGLE_MAPS_API_KEY")

    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    CITY_CENTER_LATITUDE = 38.2758164
    CITY_CENTER_LONGITUDE = 67.894829

    MAX_DISTANCE_KM = 6

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("Bot token is required")
        if not all([cls.DB_HOST, cls.DB_USER, cls.DB_NAME]):
            raise ValueError("Database configuration is incomplete")