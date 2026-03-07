import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Токен бота
    BOT_TOKEN = os.getenv('BOT_TOKEN')

    # URL'ы
    SHOP_URL = os.getenv('SHOP_URL', 'https://swiftkey22a.github.io/tokyo-vape-shop/')
    SUPPORT_URL = os.getenv('SUPPORT_URL', 'https://t.me/drugsoutlety')

    # Администраторы (список ID через запятую, например "123456,789012")
    ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
    ADMIN_IDS = [int(id_.strip()) for id_ in ADMIN_IDS_STR.split(',') if id_.strip().isdigit()]

    # Настройки логирования
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("❌ BOT_TOKEN не найден в .env файле!")
        if not cls.ADMIN_IDS:
            print("⚠️ ВНИМАНИЕ: ADMIN_IDS не задан или пуст. Админ-панель будет недоступна.")
        return True