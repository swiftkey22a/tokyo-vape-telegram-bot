import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import Config
from admin_handlers import admin_router   # если файл уже создан

# Настройка логирования
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Проверка конфига
Config.validate()

# Инициализация бота и диспетчера
bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(admin_router)   # подключаем админ-роутер

# === БАЗА ДАННЫХ ===
def init_database():
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_activity TIMESTAMP,
            visits INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")


async def log_user_activity(message: types.Message):
    try:
        conn = sqlite3.connect('bot_stats.db')
        cursor = conn.cursor()
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_activity, visits)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                last_activity = excluded.last_activity,
                visits = visits + 1
        ''', (user_id, username, first_name, now))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")


# === КЛАВИАТУРЫ ===
def get_main_menu():
    builder = InlineKeyboardBuilder()
    web_app = WebAppInfo(url=Config.SHOP_URL)

    builder.row(
        InlineKeyboardButton(text="🛒 Открыть магазин", web_app=web_app)
    )
    builder.row(
        InlineKeyboardButton(text="📋 Инструкция", callback_data="instruction"),
        InlineKeyboardButton(text="📱 Поддержка", url=Config.SUPPORT_URL)
    )
    builder.row(
        InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Закрыть", callback_data="close")
    )
    return builder.as_markup()


def back_button():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu"),
        InlineKeyboardButton(text="❌ Закрыть", callback_data="close")
    )
    return builder.as_markup()


# === ХЭНДЛЕРЫ ===
@dp.message(Command('start', 'menu'))
async def cmd_start(message: types.Message):
    await log_user_activity(message)
    await message.answer(
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        f"Добро пожаловать в **Tokyo Vape** 🏯\n"
        f"Выбери действие:",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )


@dp.message(Command('shop'))
async def cmd_shop(message: types.Message):
    web_app = WebAppInfo(url=Config.SHOP_URL)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Открыть магазин", web_app=web_app))
    builder.row(InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu"))

    await message.answer(
        "🛍 **Каталог Tokyo Vape**\n\nНажми кнопку чтобы перейти в магазин:",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )


@dp.callback_query(F.data == "instruction")
async def cb_instruction(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📋 **Инструкция:**\n\n"
        "1️⃣ **Нажми «🛒 Открыть магазин»** в меню\n"
        "2️⃣ **Выбери товар** в каталоге\n"
        "3️⃣ **Оформи заказ** в мини-приложении\n\n"
        "❓ **Вопросы?** @drugsoutlety",
        reply_markup=back_button(),
        parse_mode='Markdown'
    )


@dp.callback_query(F.data == "help")
async def cb_help(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "❓ **ПОМОЩЬ ПО БОТУ**\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🛒 **Открыть магазин** — открыть каталог\n"
        "📋 **Инструкция** — как сделать заказ\n"
        "📱 **Поддержка** — связаться с нами\n"
        "📊 **Статистика** — ваши визиты\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "**Команды:**\n"
        "/start — показать меню\n"
        "/shop — сразу в магазин",
        reply_markup=back_button(),
        parse_mode='Markdown'
    )


@dp.callback_query(F.data == "stats")
async def cb_stats(callback: types.CallbackQuery):
    await callback.answer()
    try:
        conn = sqlite3.connect('bot_stats.db')
        cursor = conn.cursor()
        cursor.execute('SELECT visits, last_activity FROM users WHERE user_id = ?', (callback.from_user.id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            visits, last_activity = result
            date_obj = datetime.fromisoformat(last_activity)
            formatted_date = date_obj.strftime("%d.%m.%Y в %H:%M")
            text = f"📊 **ВАША СТАТИСТИКА**\n\n━━━━━━━━━━━━━━━━━━━━━\n👋 **Визитов:** {visits}\n🕐 **Последний визит:** {formatted_date}"
        else:
            text = "📊 Статистика пока не собрана"

        await callback.message.edit_text(text, reply_markup=back_button(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await callback.message.edit_text("❌ Ошибка статистики", reply_markup=back_button())


@dp.callback_query(F.data == "back_to_menu")
async def cb_back(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🎯 **Главное меню:**",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )


@dp.callback_query(F.data == "close")
async def cb_close(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()


@dp.message(~F.text.startswith('/'))
async def handle_all(message: types.Message):
    await message.answer(
        "❓ Я понимаю только команды.\n\nИспользуй /start чтобы открыть меню:",
        reply_markup=get_main_menu()
    )


# === ЗАПУСК ===
async def set_commands():
    await bot.set_my_commands([
        types.BotCommand(command="start", description="🏠 Открыть меню"),
        types.BotCommand(command="shop", description="🛒 Перейти в магазин")
    ])


async def main():
    init_database()
    await set_commands()
    logger.info("✅ Бот Tokyo Vape запущен (aiogram)")
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
