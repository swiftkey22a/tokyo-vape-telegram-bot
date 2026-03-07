import csv
import io
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3

from config import Config

# Создаём роутер для админ-хэндлеров
admin_router = Router()

# Логирование
logger = logging.getLogger(__name__)


# === Проверка прав администратора ===
def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_IDS


# === Клавиатуры ===
def admin_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_mailing")
    )
    builder.row(
        InlineKeyboardButton(text="📁 Логи", callback_data="admin_logs"),
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Закрыть", callback_data="close")
    )
    return builder.as_markup()


def back_to_admin_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в админку", callback_data="back_to_admin"),
        InlineKeyboardButton(text="❌ Закрыть", callback_data="close")
    )
    return builder.as_markup()


def mailing_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_mailing"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mailing")
    )
    return builder.as_markup()


# === FSM для рассылки ===
class MailingStates(StatesGroup):
    waiting_for_message = State()
    confirm = State()


# === Команда /admin ===
@admin_router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    logger.info(f"Получена команда /admin от пользователя {message.from_user.id}")  # <-- добавить
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer("🔧 **Панель администратора**", reply_markup=admin_main_menu(), parse_mode="Markdown")


# === Кнопка "Назад в админку" ===
@admin_router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("🔧 **Панель администратора**", reply_markup=admin_main_menu(),
                                     parse_mode="Markdown")
    await callback.answer()


# === Статистика ===
@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()

    # Общее количество
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]

    # Активные сегодня
    today = datetime.now().date().isoformat()
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_activity LIKE ?", (f"{today}%",))
    active_today = cursor.fetchone()[0]

    # Активные за последние 7 дней
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_activity >= ?", (week_ago,))
    active_week = cursor.fetchone()[0]

    # Последняя активность
    cursor.execute("SELECT username, last_activity FROM users ORDER BY last_activity DESC LIMIT 1")
    last = cursor.fetchone()
    last_info = f"@{last[0]} - {last[1][:16]}" if last and last[0] else "нет данных"

    conn.close()

    text = (
        f"📊 **Статистика**\n\n"
        f"👥 **Всего пользователей:** {total}\n"
        f"✅ **Активных сегодня:** {active_today}\n"
        f"📅 **За неделю:** {active_week}\n"
        f"🕐 **Последний визит:** {last_info}"
    )
    await callback.message.edit_text(text, reply_markup=back_to_admin_menu(), parse_mode="Markdown")
    await callback.answer()


# === Рассылка: начало ===
@admin_router.callback_query(F.data == "admin_mailing")
async def start_mailing(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text(
        "📝 **Отправьте сообщение для рассылки**\n\n"
        "Поддерживается: текст, фото, видео, документы, голосовые сообщения.\n"
        "Чтобы отменить, отправьте /cancel"
    )
    await state.set_state(MailingStates.waiting_for_message)
    await callback.answer()


# === Отмена через команду /cancel ===
@admin_router.message(Command("cancel"), StateFilter(MailingStates.waiting_for_message, MailingStates.confirm))
async def cancel_mailing_command(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Рассылка отменена.", reply_markup=admin_main_menu())


# === Получение сообщения для рассылки ===
@admin_router.message(MailingStates.waiting_for_message)
async def get_mailing_message(message: types.Message, state: FSMContext, bot: Bot):
    # Сохраняем информацию о сообщении
    data = {
        'type': None,
        'content': None,
        'caption': None,
        'parse_mode': None,
        'reply_markup': None
    }

    if message.text:
        data['type'] = 'text'
        data['content'] = message.text
        data['parse_mode'] = 'Markdown' if message.parse_mode else None
    elif message.photo:
        data['type'] = 'photo'
        data['content'] = message.photo[-1].file_id
        data['caption'] = message.caption
        data['parse_mode'] = message.caption_entities
    elif message.video:
        data['type'] = 'video'
        data['content'] = message.video.file_id
        data['caption'] = message.caption
        data['parse_mode'] = message.caption_entities
    elif message.document:
        data['type'] = 'document'
        data['content'] = message.document.file_id
        data['caption'] = message.caption
        data['parse_mode'] = message.caption_entities
    elif message.audio:
        data['type'] = 'audio'
        data['content'] = message.audio.file_id
        data['caption'] = message.caption
        data['parse_mode'] = message.caption_entities
    elif message.voice:
        data['type'] = 'voice'
        data['content'] = message.voice.file_id
        data['caption'] = message.caption
        data['parse_mode'] = message.caption_entities
    else:
        await message.answer("❌ Неподдерживаемый тип сообщения. Отправьте текст, фото, видео или документ.")
        return

    await state.update_data(mailing=data)

    # Показываем подтверждение
    await message.answer(
        "⚠️ **Подтверждение рассылки**\n\n"
        f"Тип: {data['type']}\n"
        f"Получателей: ? (будет подсчитано при отправке)\n\n"
        "Начать рассылку?",
        reply_markup=mailing_confirm_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MailingStates.confirm)


# === Подтверждение рассылки ===
@admin_router.callback_query(MailingStates.confirm, F.data == "confirm_mailing")
async def confirm_mailing(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    mailing_data = data.get('mailing')
    await state.clear()

    await callback.message.edit_text("⏳ **Рассылка начата...** Подсчёт пользователей...", parse_mode="Markdown")

    # Получаем всех пользователей из БД
    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    total_users = len(users)
    await callback.message.edit_text(f"⏳ Рассылка начата... Всего получателей: {total_users}")

    success = 0
    failed = 0
    for (user_id,) in users:
        try:
            if mailing_data['type'] == 'text':
                await bot.send_message(user_id, mailing_data['content'], parse_mode=mailing_data['parse_mode'])
            elif mailing_data['type'] == 'photo':
                await bot.send_photo(user_id, mailing_data['content'], caption=mailing_data.get('caption'),
                                     parse_mode=mailing_data['parse_mode'])
            elif mailing_data['type'] == 'video':
                await bot.send_video(user_id, mailing_data['content'], caption=mailing_data.get('caption'),
                                     parse_mode=mailing_data['parse_mode'])
            elif mailing_data['type'] == 'document':
                await bot.send_document(user_id, mailing_data['content'], caption=mailing_data.get('caption'),
                                        parse_mode=mailing_data['parse_mode'])
            elif mailing_data['type'] == 'audio':
                await bot.send_audio(user_id, mailing_data['content'], caption=mailing_data.get('caption'),
                                     parse_mode=mailing_data['parse_mode'])
            elif mailing_data['type'] == 'voice':
                await bot.send_voice(user_id, mailing_data['content'], caption=mailing_data.get('caption'),
                                     parse_mode=mailing_data['parse_mode'])
            success += 1
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
        await asyncio.sleep(0.03)  # Небольшая задержка для избежания флуд-контроля

    await callback.message.answer(
        f"✅ **Рассылка завершена!**\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=admin_main_menu(),
        parse_mode="Markdown"
    )


# === Отмена рассылки ===
@admin_router.callback_query(MailingStates.confirm, F.data == "cancel_mailing")
async def cancel_mailing(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=admin_main_menu())
    await callback.answer()


# === Просмотр логов ===
@admin_router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        with open('bot.log', 'r', encoding='utf-8') as f:
            # Читаем последние 30 строк
            lines = f.readlines()[-30:]
            logs = ''.join(lines)
            if not logs:
                logs = "Лог-файл пуст."
    except FileNotFoundError:
        logs = "Файл логов не найден. Убедитесь, что логирование настроено в файл."

    # Если лог слишком длинный, обрезаем
    if len(logs) > 3500:
        logs = logs[-3500:] + "\n\n... (обрезано)"

    await callback.message.edit_text(
        f"📁 **Последние логи:**\n\n```\n{logs}\n```",
        reply_markup=back_to_admin_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()


# === Раздел "Пользователи" ===
@admin_router.callback_query(F.data == "admin_users")
async def admin_users_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📎 Выгрузить CSV", callback_data="export_csv"),
        InlineKeyboardButton(text="🚫 Блокировка", callback_data="ban_user")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Разблокировка", callback_data="unban_user"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")
    )
    await callback.message.edit_text(
        "👥 **Управление пользователями**\n\nВыберите действие:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


# === Выгрузка CSV ===
@admin_router.callback_query(F.data == "export_csv")
async def export_csv(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    conn = sqlite3.connect('bot_stats.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, first_name, last_activity, visits FROM users")
    rows = cursor.fetchall()
    conn.close()

    # Создаём CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['user_id', 'username', 'first_name', 'last_activity', 'visits'])
    writer.writerows(rows)
    csv_data = output.getvalue().encode('utf-8')
    output.close()

    # Отправляем файл
    from aiogram.types import BufferedInputFile
    file = BufferedInputFile(csv_data, filename="users.csv")
    await callback.message.answer_document(file, caption="📎 Список пользователей")
    await callback.answer()


# === Заглушки для блокировки (можно развить) ===
@admin_router.callback_query(F.data == "ban_user")
async def ban_user_prompt(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text(
        "🚫 **Блокировка пользователя**\n\n"
        "Эта функция пока не реализована. Вы можете добавить поле `banned` в таблицу users и фильтровать при рассылке.",
        reply_markup=back_to_admin_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()


@admin_router.callback_query(F.data == "unban_user")
async def unban_user_prompt(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text(
        "✅ **Разблокировка пользователя**\n\n"
        "Функция в разработке.",
        reply_markup=back_to_admin_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()


# === Общая кнопка "Закрыть" (уже есть в основном файле, но дублируем на всякий случай) ===
@admin_router.callback_query(F.data == "close")
async def close_message(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()