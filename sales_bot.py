import telebot
import gspread
from datetime import datetime
import json
import requests
from collections import defaultdict
import sys
import traceback

print("=" * 50)
print("🤖 БОТ ДЛЯ УЧЁТА ПРОДАЖ С АВТООСТАТКАМИ")
print("=" * 50)

# Загружаем конфигурацию
try:
    with open("config.json", 'r') as config_file:
        config = json.load(config_file)
    TOKEN = config['telegram_token']
    print(f"✅ Токен загружен: {TOKEN[:10]}...")
except (FileNotFoundError, json.JSONDecodeError, KeyError) as config_error:
    print(f"❌ Ошибка config.json: {config_error}")
    sys.exit(1)

# Отключаем вебхук
print("\n🔄 Отключаю вебхук...")
try:
    delete_url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    hook_response = requests.get(delete_url, params={"drop_pending_updates": True}, timeout=10)
    print(f"✅ Вебхук отключён")
except (requests.RequestException, ValueError) as hook_error:
    print(f"⚠️ Вебхук: {hook_error}")

# Создаём бота
bot = telebot.TeleBot(TOKEN)

# Подключаемся к Google Sheets
print("\n📊 Подключение к Google Sheets...")
try:
    gc = gspread.service_account(filename='google_key.json')
    sh = gc.open_by_key("1PoiVkQC_P_5CPMqXGh77Jprl7-pGFAMLCFiCUwTYoD4")
    print(f"✅ Таблица: '{sh.title}'")

    # Получаем все листы
    worksheets = sh.worksheets()
    print(f"\n📋 Найдено листов: {len(worksheets)}")
    for ws in worksheets:
        print(f"  • {ws.title}")

    # Лист Для_бота (ИСТОЧНИК ДАННЫХ)
    try:
        bot_ws = sh.worksheet("Для_бота")
        print("✅ Лист 'Для_бота' найден - основной источник")
    except gspread.exceptions.WorksheetNotFound:
        print("❌ Лист 'Для_бота' не найден! Создайте лист с товарами")
        bot_ws = None

    # Лист Продажи (КУДА ЗАПИСЫВАЕМ ПРОДАЖИ)
    try:
        sales_ws = sh.worksheet("Продажи")
        print("✅ Лист 'Продажи' найден")
    except gspread.exceptions.WorksheetNotFound:
        print("➕ Создаю лист 'Продажи'...")
        sales_ws = sh.add_worksheet(title="Продажи", rows=1000, cols=5)
        sales_ws.append_row(["Дата", "Бренд", "Вкус", "Количество", "Сотрудник"])
        print("✅ Лист 'Продажи' создан")

    # Лист Ассортимент (ДЛЯ ОТЧЁТА, НЕОБЯЗАТЕЛЕН)
    try:
        assortment_ws = sh.worksheet("Ассортимент")
        print("✅ Лист 'Ассортимент' найден")
    except gspread.exceptions.WorksheetNotFound:
        print("⚠️ Лист 'Ассортимент' не найден")
        assortment_ws = None

except (gspread.exceptions.GSpreadException, FileNotFoundError) as sheets_error:
    print(f"❌ Ошибка подключения к Google Sheets: {sheets_error}")
    bot_ws = None
    sales_ws = None
    assortment_ws = None

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========

user_states = {}
assortment_cache = []
assortment_by_brand = defaultdict(list)


# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def load_items_from_bot_sheet():
    """Загружает товары из 'Для_бота' с начальными остатками"""
    global assortment_cache, assortment_by_brand

    try:
        if bot_ws is None:
            print("❌ Лист 'Для_бота' не найден")
            return False

        data = bot_ws.get_all_values()
        if len(data) <= 1:
            print("❌ В 'Для_бота' нет данных")
            return False

        print(f"📊 Загружаю товары из 'Для_бота'...")

        assortment_cache = []
        assortment_by_brand.clear()

        # Загружаем все продажи
        all_sales = get_all_sales()

        for row in data[1:]:
            if len(row) >= 2 and row[0] and row[1]:
                brand = row[0].strip()
                taste = row[1].strip()

                # НАЧАЛЬНЫЙ ОСТАТОК ИЗ КОЛОНКИ F (индекс 5)
                initial_stock = 3  # значение по умолчанию
                if len(row) > 5 and row[5]:  # Если есть колонка F
                    try:
                        initial_stock = int(row[5])
                    except ValueError:
                        initial_stock = 3
                elif len(row) > 5 and not row[5]:
                    # Ячейка пустая - оставляем 3
                    initial_stock = 3

                # Считаем текущий остаток
                current_stock = calculate_current_stock(brand, taste, initial_stock, all_sales)

                # Остальные данные
                item_id = row[2] if len(row) > 2 and row[2] else ""
                price = str(row[3]).strip() if len(row) > 3 and row[3] else ""
                strength = str(row[4]).strip() if len(row) > 4 and row[4] else ""

                item = {
                    'brand': brand,
                    'taste': taste,
                    'quantity': current_stock,  # Текущий остаток
                    'initial_stock': initial_stock,  # Начальный остаток из таблицы!
                    'price': price,
                    'strength': strength,
                    'id': item_id
                }

                assortment_cache.append(item)
                assortment_by_brand[brand].append(item)

                # Логируем для отладки
                print(f"  📦 {brand} - {taste}: было {initial_stock}, сейчас {current_stock}")

        print(f"✅ Загружено: {len(assortment_cache)} товаров")
        return True

    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        traceback.print_exc()
        return False


def get_all_sales():
    """Получает все продажи для быстрого подсчёта"""
    sales_dict = {}

    try:
        if sales_ws is None:
            return sales_dict

        sales_data = sales_ws.get_all_values()
        if len(sales_data) <= 1:
            return sales_dict

        for row in sales_data[1:]:
            if len(row) >= 4:
                brand = row[1].strip()  # Бренд
                taste = row[2].strip()  # Вкус

                # Создаём ключ для словаря
                key = f"{brand}|{taste}"

                # Суммируем количество
                try:
                    quantity = int(row[3]) if row[3].isdigit() else 0
                    sales_dict[key] = sales_dict.get(key, 0) + quantity
                except ValueError:
                    continue

        return sales_dict

    except Exception as e:
        print(f"⚠️ Ошибка получения продаж: {e}")
        return {}


def calculate_current_stock(brand, taste, initial_stock, sales_dict=None):
    """Считает текущий остаток на основе начального количества из 'Для_бота'"""
    try:
        if sales_dict is None:
            sales_dict = get_all_sales()

        clean_brand = brand.split()[0]
        key = f"{clean_brand}|{taste}"

        sold_quantity = sales_dict.get(key, 0)
        current_stock = max(0, initial_stock - sold_quantity)

        return current_stock

    except Exception as e:
        print(f"⚠️ Ошибка подсчёта: {e}")
        return initial_stock


def write_sale(brand, taste, quantity, username):
    """Записывает продажу в таблицу И ОБНОВЛЯЕТ ОСТАТОК"""
    try:
        # 1. Находим товар в кэше, чтобы узнать начальный остаток
        initial_stock = 3  # по умолчанию
        full_brand_name = brand  # Сохраняем полное название с эмодзи

        for item in assortment_cache:
            if item['brand'] == brand and item['taste'] == taste:
                initial_stock = item.get('initial_stock', 3)
                break

        # 2. Для поиска в продажах используем чистый бренд (без эмодзи)
        clean_brand = brand.split()[0]  # "ANIMMA 🐟" → "ANIMMA"

        # 3. Считаем сколько уже продано этого товара
        key = f"{clean_brand}|{taste}"
        all_sales = get_all_sales()
        sold_before = all_sales.get(key, 0)

        # 4. Считаем остатки
        stock_before = max(0, initial_stock - sold_before)
        stock_after = max(0, stock_before - quantity)

        # 5. Проверяем, что не продаём больше, чем есть
        if quantity > stock_before:
            return {
                'success': False,
                'error': f"Недостаточно товара! Остаток: {stock_before} шт."
            }

        # 6. Записываем в таблицу - ВАЖНО: записываем ПОЛНОЕ название!
        row_data = [
            datetime.now().strftime("%d.%m.%Y %H:%M"),  # Дата
            full_brand_name,  # ПОЛНОЕ название бренда с эмодзи!
            taste,  # Вкус
            str(quantity),  # Количество проданного
            f"@{username}" if username else "без_username",  # Продавец
            str(stock_after)  # Остаток после продажи
        ]

        sales_ws.append_row(row_data)

        # 7. Обновляем кэш
        update_item_stock_in_cache(brand, taste, quantity)

        print(f"✅ Продажа записана: {full_brand_name} - {taste}")
        print(f"📊 Остаток: {stock_before} → {stock_after}")

        return {
            'success': True,
            'brand_display': full_brand_name,  # Для отображения
            'brand_search': clean_brand,  # Для поиска
            'stock_before': stock_before,
            'stock_after': stock_after,
            'total_sold': sold_before + quantity
        }

    except Exception as e:
        print(f"❌ Ошибка записи: {e}")
        return {'success': False, 'error': str(e)}

        # 7. Обновляем кэш
        update_item_stock_in_cache(brand, taste, quantity)

        print(f"✅ Продажа: {brand} - {taste}")
        print(f"📊 Начальный: {initial_stock}, Продано всего: {sold_before + quantity}")
        print(f"📊 Остаток: {stock_before} → {stock_after}")

        return {
            'success': True,
            'initial_stock': initial_stock,
            'stock_before': stock_before,
            'stock_after': stock_after,
            'total_sold': sold_before + quantity
        }

    except Exception as e:
        print(f"❌ Ошибка записи: {e}")
        return {'success': False, 'error': str(e)}


def update_item_stock_in_cache(brand, taste, sold_quantity):
    """Обновляет остаток в кэше после продажи"""
    try:
        for item in assortment_cache:
            if item['brand'] == brand and item['taste'] == taste:
                item['quantity'] = max(0, item['quantity'] - sold_quantity)
                print(f"📉 Остаток обновлён в кэше: {brand} - {taste} = {item['quantity']} шт.")
                return True

        # Если не нашли в кэше, перезагружаем
        load_items_from_bot_sheet()
        return True

    except Exception as e:
        print(f"⚠️ Ошибка обновления кэша: {e}")
        return False


def get_item_stock(brand, taste):
    """Возвращает текущий остаток товара"""
    for item in assortment_cache:
        if item['brand'] == brand and item['taste'] == taste:
            return item['quantity']

    # Если не нашли, считаем заново
    return calculate_current_stock(brand, taste, 3)


# ========== МЕНЮ БОТА ==========

@bot.message_handler(commands=['start', 'menu'])
def start(message):
    """Главное меню"""
    user_states.pop(message.chat.id, None)

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    markup.add(
        telebot.types.KeyboardButton('📝 Записать продажу'),
        telebot.types.KeyboardButton('📋 Весь ассортимент'),
        telebot.types.KeyboardButton('📊 Статистика'),
        telebot.types.KeyboardButton('🔄 Обновить список'),
        telebot.types.KeyboardButton('📦 Проверить остаток')
    )

    bot.send_message(
        message.chat.id,
        "🤖 <b>Бот для учёта продаж с автоматическими остатками</b>\n\n"
        "📊 <b>Особенности:</b>\n"
        "• Автоматический подсчёт остатков\n"
        "• Актуальные данные в реальном времени\n"
        "• История всех продаж\n\n"
        "Выберите действие:",
        reply_markup=markup,
        parse_mode='HTML'
    )


@bot.message_handler(func=lambda message: message.text == '🔄 Обновить список')
def refresh_list(message):
    """Обновляет список товаров"""
    bot.send_message(message.chat.id, "🔄 Обновляю список товаров...")
    if load_items_from_bot_sheet():
        bot.send_message(message.chat.id, f"✅ Обновлено! Товаров: {len(assortment_cache)}")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось обновить список")


@bot.message_handler(func=lambda message: message.text == '📝 Записать продажу')
def start_sale(message):
    """Начало записи продажи"""
    # Загружаем товары если ещё не загружены
    if not assortment_cache:
        bot.send_message(message.chat.id, "🔄 Загружаю товары...")
        if not load_items_from_bot_sheet():
            bot.send_message(message.chat.id, "❌ Не удалось загрузить товары")
            return

    # Получаем бренды
    brands = sorted(assortment_by_brand.keys())

    if not brands:
        bot.send_message(message.chat.id, "📭 Нет товаров в базе")
        return

    # Создаём меню брендов
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    # Показываем первые 12 брендов
    for brand in brands[:12]:
        markup.add(telebot.types.KeyboardButton(f"🏷️ {brand}"))

    if len(brands) > 12:
        markup.add(telebot.types.KeyboardButton('🔽 Ещё бренды'))

    markup.add(telebot.types.KeyboardButton('↩️ Назад'))

    # Сохраняем состояние
    user_states[message.chat.id] = {'step': 'choose_brand', 'brand_page': 0}

    bot.send_message(
        message.chat.id,
        "🏷️ <b>Выберите бренд:</b>",
        reply_markup=markup,
        parse_mode='HTML'
    )


@bot.message_handler(func=lambda message:
user_states.get(message.chat.id, {}).get('step') == 'choose_brand'
and message.text == '🔽 Ещё бренды')
def show_more_brands(message):
    """Показывает следующую страницу брендов"""
    state = user_states[message.chat.id]
    page = state.get('brand_page', 0) + 1

    brands = sorted(assortment_by_brand.keys())
    start_idx = page * 12
    end_idx = start_idx + 12

    if start_idx >= len(brands):
        bot.send_message(message.chat.id, "✅ Это все бренды")
        return

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    for brand in brands[start_idx:end_idx]:
        markup.add(telebot.types.KeyboardButton(f"🏷️ {brand}"))

    if end_idx < len(brands):
        markup.add(telebot.types.KeyboardButton('🔽 Ещё бренды'))

    markup.add(telebot.types.KeyboardButton('↩️ Назад'))

    state['brand_page'] = page

    bot.send_message(
        message.chat.id,
        f"🏷️ <b>Бренды (страница {page + 1}):</b>",
        reply_markup=markup,
        parse_mode='HTML'
    )


@bot.message_handler(func=lambda message:
user_states.get(message.chat.id, {}).get('step') == 'choose_brand'
and message.text.startswith('🏷️'))
def choose_brand(message):
    """Обработка выбора бренда"""
    brand = message.text.replace('🏷️', '').strip()

    if brand not in assortment_by_brand:
        bot.send_message(message.chat.id, f"❌ Бренд '{brand}' не найден")
        start(message)
        return

    # Получаем товары этого бренда
    items = assortment_by_brand[brand]

    # Создаём меню вкусов
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)

    for item in items:
        taste = item['taste']
        stock = item['quantity']

        # Подсветка в зависимости от остатка
        if stock == 0:
            emoji = "❌"
        elif stock <= 2:
            emoji = "⚠️"
        else:
            emoji = "✅"

        btn_text = f"{emoji} {taste}"

        # Добавляем цену если есть
        if item.get('price'):
            btn_text += f" ({item['price']} руб)"

        markup.add(telebot.types.KeyboardButton(btn_text))

    markup.add(telebot.types.KeyboardButton('↩️ Выбрать другой бренд'))
    markup.add(telebot.types.KeyboardButton('🏠 Главное меню'))

    # Сохраняем состояние
    user_states[message.chat.id] = {
        'step': 'choose_taste',
        'brand': brand
    }

    bot.send_message(
        message.chat.id,
        f"🏷️ <b>Бренд:</b> {brand}\n"
        f"🍇 <b>Выберите вкус:</b>",
        reply_markup=markup,
        parse_mode='HTML'
    )


@bot.message_handler(func=lambda message:
user_states.get(message.chat.id, {}).get('step') == 'choose_taste'
and any(emoji in message.text for emoji in ['✅', '⚠️', '❌']))
def choose_taste(message):
    """Обработка выбора вкуса"""
    # Извлекаем название вкуса
    taste_text = message.text
    taste = taste_text.split(' (')[0]  # Убираем цену
    taste = taste.replace('✅', '').replace('⚠️', '').replace('❌', '').strip()

    brand = user_states[message.chat.id]['brand']

    # Находим товар
    item = None
    for it in assortment_by_brand[brand]:
        if it['taste'] == taste:
            item = it
            break

    if not item:
        bot.send_message(message.chat.id, f"❌ Вкус '{taste}' не найден")
        choose_brand(message)
        return

    # Проверяем остаток
    if item['quantity'] <= 0:
        bot.send_message(
            message.chat.id,
            f"❌ <b>Товар закончился!</b>\n\n"
            f"{brand} - {taste}\n"
            f"Остаток: 0 шт.\n\n"
            f"Выберите другой товар:",
            parse_mode='HTML'
        )
        choose_brand(message)
        return

    # Сохраняем выбранный товар
    user_states[message.chat.id] = {
        'step': 'choose_quantity',
        'brand': brand,
        'taste': taste,
        'current_stock': item['quantity'],
        'price': item.get('price', ''),
        'strength': item.get('strength', '')
    }

    # Создаём меню количества
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)

    # Предлагаем доступные количества (не больше остатка)
    max_qty = min(item['quantity'], 3)
    for qty in range(1, max_qty + 1):
        markup.add(telebot.types.KeyboardButton(str(qty)))

    markup.add(telebot.types.KeyboardButton('↩️ Выбрать другой вкус'))
    markup.add(telebot.types.KeyboardButton('🏠 Главное меню'))

    # Формируем сообщение
    info_lines = []
    if item.get('price'):
        info_lines.append(f"💰 <b>Цена:</b> {item['price']} руб")
    if item.get('strength'):
        info_lines.append(f"⚡ <b>Крепость:</b> {item['strength']}")

    extra_info = "\n".join(info_lines) + "\n" if info_lines else ""

    bot.send_message(
        message.chat.id,
        f"🏷️ <b>Бренд:</b> {brand}\n"
        f"🍇 <b>Вкус:</b> {taste}\n"
        f"{extra_info}"
        f"📦 <b>В наличии:</b> {item['quantity']} шт.\n\n"
        f"<b>Сколько продали?</b>",
        reply_markup=markup,
        parse_mode='HTML'
    )


@bot.message_handler(func=lambda message:
user_states.get(message.chat.id, {}).get('step') == 'choose_quantity'
and message.text.isdigit())
def finalize_sale(message):
    """Завершение продажи"""
    quantity = int(message.text)
    user_data = user_states[message.chat.id]

    brand = user_data['brand']
    taste = user_data['taste']
    price = user_data.get('price', '')
    strength = user_data.get('strength', '')
    username = message.from_user.username

    # Проверяем, что не продаём больше, чем есть
    if quantity > user_data['current_stock']:
        bot.send_message(
            message.chat.id,
            f"❌ <b>Недостаточно товара!</b>\n"
            f"Остаток: {user_data['current_stock']} шт.\n"
            f"Вы пытаетесь продать: {quantity} шт.",
            parse_mode='HTML'
        )
        return

    # Записываем продажу
    success = write_sale(brand, taste, quantity, username)

    if success:
        # Формируем чек
        receipt_text = "🧾 <b>ЧЕК ПРОДАЖИ</b>\n"
        receipt_text += "─" * 30 + "\n\n"

        receipt_text += f"🏷️ <b>Бренд:</b> {brand}\n"
        receipt_text += f"🍇 <b>Вкус:</b> {taste}\n"

        if price:
            total_price = int(price) * quantity if price.isdigit() else 0
            receipt_text += f"💰 <b>Цена:</b> {price} руб\n"
            if total_price > 0:
                receipt_text += f"💵 <b>Итого:</b> {total_price} руб\n"

        if strength:
            receipt_text += f"⚡ <b>Крепость:</b> {strength}\n"

        receipt_text += f"📦 <b>Продано:</b> {quantity} шт.\n"
        receipt_text += f"👤 <b>Сотрудник:</b> @{username or 'без_username'}\n"
        receipt_text += f"🕐 <b>Время:</b> {datetime.now().strftime('%H:%M')}\n\n"

        receipt_text += "✅ <b>Продажа записана!</b>\n\n"
        receipt_text += "📝 Новая продажа: /start"

        bot.send_message(
            message.chat.id,
            receipt_text,
            parse_mode='HTML'
        )
    else:
        bot.send_message(message.chat.id, "❌ Ошибка записи продажи")

    # Сбрасываем состояние
    user_states.pop(message.chat.id, None)


@bot.message_handler(func=lambda message: message.text == '📋 Весь ассортимент')
def show_all_items(message):
    """Показывает все товары"""
    if not assortment_cache:
        if not load_items_from_bot_sheet():
            bot.send_message(message.chat.id, "❌ Не удалось загрузить товары")
            return

    if not assortment_cache:
        bot.send_message(message.chat.id, "📭 Нет товаров")
        return

    response_text = "📦 <b>ВЕСЬ АССОРТИМЕНТ</b>\n"
    response_text += "─" * 30 + "\n\n"

    total_items = 0
    for brand, items in sorted(assortment_by_brand.items()):
        response_text += f"<b>{brand}:</b>\n"

        for item in items[:6]:  # Первые 6 вкусов каждого бренда
            stock = item['quantity']

            if stock == 0:
                emoji = "❌"
            elif stock <= 2:
                emoji = "⚠️"
            else:
                emoji = "✅"

            response_text += f"  {emoji} {item['taste']}"

            if item.get('price'):
                response_text += f" ({item['price']} руб)"

            response_text += f" [{stock} шт.]\n"
            total_items += 1

        if len(items) > 6:
            response_text += f"  ... и ещё {len(items) - 6} вкусов\n"

        response_text += "\n"

    response_text += f"📊 <b>Всего товаров:</b> {len(assortment_cache)}\n"
    response_text += f"🏷️ <b>Брендов:</b> {len(assortment_by_brand)}\n"
    response_text += f"📦 <b>Товаров в наличии:</b> {sum(item['quantity'] for item in assortment_cache)} шт.\n"
    response_text += "🔄 Обновить: /start"

    bot.send_message(message.chat.id, response_text, parse_mode='HTML')


@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_stats(message):
    """Показывает статистику продаж"""
    try:
        if sales_ws is None:
            bot.send_message(message.chat.id, "📊 Лист 'Продажи' не найден")
            return

        sales_data = sales_ws.get_all_values()

        if len(sales_data) <= 1:
            bot.send_message(message.chat.id, "📊 Продаж ещё нет")
            return

        today = datetime.now().strftime("%d.%m.%Y")
        today_sales = [row for row in sales_data[1:] if row[0].startswith(today)]

        stats_text = f"📊 <b>СТАТИСТИКА ЗА {today}</b>\n"
        stats_text += "─" * 30 + "\n\n"

        stats_text += f"🛒 <b>Всего продаж:</b> {len(today_sales)}\n"

        if today_sales:
            total_qty = sum(int(row[3]) for row in today_sales if row[3].isdigit())
            stats_text += f"📦 <b>Общее количество:</b> {total_qty} шт.\n\n"

            # Топ брендов
            brand_counts = {}
            for row in today_sales:
                brand = row[1]
                qty = int(row[3]) if row[3].isdigit() else 0
                brand_counts[brand] = brand_counts.get(brand, 0) + qty

            if brand_counts:
                stats_text += "<b>🏆 Топ брендов:</b>\n"
                for brand, qty in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
                    stats_text += f"  • {brand}: {qty} шт.\n"

        stats_text += "\n📝 Новая продажа: /start"

        bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

    except Exception as stats_error:
        bot.send_message(message.chat.id, f"📊 <b>Ошибка статистики:</b>\n{str(stats_error)[:100]}")


@bot.message_handler(func=lambda message: message.text == '📦 Проверить остаток')
def check_stock_start(message):
    """Начало проверки остатка"""
    bot.send_message(
        message.chat.id,
        "🔍 <b>Проверка остатка</b>\n\n"
        "Введите название товара в формате:\n"
        "<code>Бренд Вкус</code>\n\n"
        "Пример: <code>ANIMMA INDRA КИВИ-КЛУБНИКА</code>",
        parse_mode='HTML'
    )

    bot.register_next_step_handler(message, check_stock_process)


def check_stock_process(message):
    """Обработка запроса на проверку остатка"""
    try:
        query = message.text.strip()

        if not query:
            bot.send_message(message.chat.id, "❌ Введите название товара")
            return

        # Пробуем найти в кэше
        found_items = []

        for item in assortment_cache:
            clean_brand = item['brand'].split()[0]  # Убираем эмодзи
            if query.lower() in clean_brand.lower() or query.lower() in item['taste'].lower():
                found_items.append(item)

        if found_items:
            if len(found_items) == 1:
                item = found_items[0]
                stock = get_item_stock(item['brand'], item['taste'])

                response = f"📊 <b>Остаток товара:</b>\n\n"
                response += f"🏷️ <b>Бренд:</b> {item['brand']}\n"
                response += f"🍇 <b>Вкус:</b> {item['taste']}\n"

                if item.get('price'):
                    response += f"💰 <b>Цена:</b> {item['price']} руб\n"
                if item.get('strength'):
                    response += f"⚡ <b>Крепость:</b> {item['strength']}\n"

                if stock == 0:
                    response += f"📦 <b>Остаток:</b> <code>❌ ЗАКОНЧИЛСЯ</code>\n"
                elif stock <= 2:
                    response += f"📦 <b>Остаток:</b> <code>⚠️ {stock} шт. (МАЛО)</code>\n"
                else:
                    response += f"📦 <b>Остаток:</b> <code>✅ {stock} шт.</code>\n"

                bot.send_message(message.chat.id, response, parse_mode='HTML')
            else:
                response = f"🔍 <b>Найдено товаров:</b> {len(found_items)}\n\n"
                for item in found_items[:5]:
                    stock = get_item_stock(item['brand'], item['taste'])
                    emoji = "❌" if stock == 0 else "⚠️" if stock <= 2 else "✅"
                    response += f"{emoji} {item['brand']} - {item['taste']} ({stock} шт.)\n"

                if len(found_items) > 5:
                    response += f"\n... и ещё {len(found_items) - 5} товаров"

                bot.send_message(message.chat.id, response, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "❌ Товар не найден. Попробуйте уточнить запрос.")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка поиска: {e}")


@bot.message_handler(
    func=lambda message: message.text in ['↩️ Назад', '↩️ Выбрать другой бренд', '↩️ Выбрать другой вкус',
                                          '🏠 Главное меню'])
@bot.message_handler(
    func=lambda message: message.text in ['↩️ Назад', '↩️ Выбрать другой бренд', '↩️ Выбрать другой вкус',
                                          '🏠 Главное меню'])
@bot.message_handler(
    func=lambda message: message.text in ['↩️ Назад', '↩️ Выбрать другой бренд', '↩️ Выбрать другой вкус',
                                          '🏠 Главное меню'])

def handle_back(message):
    """Обработка кнопок назад"""
    text = message.text

    if text == '🏠 Главное меню':
        start(message)

    elif text == '↩️ Назад':
        start(message)

    elif text == '↩️ Выбрать другой бренд':
        # Показываем бренды с первой страницы
        if not assortment_cache:
            bot.send_message(message.chat.id, "🔄 Загружаю товары...")
            if not load_items_from_bot_sheet():
                bot.send_message(message.chat.id, "❌ Не удалось загрузить товары")
                return

        brands = sorted(assortment_by_brand.keys())
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

        for brand in brands[:12]:
            markup.add(telebot.types.KeyboardButton(f"🏷️ {brand}"))

        if len(brands) > 12:
            markup.add(telebot.types.KeyboardButton('🔽 Ещё бренды'))

        markup.add(telebot.types.KeyboardButton('↩️ Назад'))

        user_states[message.chat.id] = {'step': 'choose_brand', 'brand_page': 0}

        bot.send_message(
            message.chat.id,
            "🏷️ <b>Выберите бренд:</b>",
            reply_markup=markup,
            parse_mode='HTML'
        )

    elif text == '↩️ Выбрать другой вкус':
        # Возвращаем к выбору вкусов текущего бренда
        user_data = user_states.get(message.chat.id, {})

        if 'brand' in user_data:
            brand = user_data['brand']

            if brand in assortment_by_brand:
                items = assortment_by_brand[brand]
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)

                for item in items:
                    taste = item['taste']
                    stock = item['quantity']
                    emoji = "❌" if stock == 0 else "⚠️" if stock <= 2 else "✅"
                    btn_text = f"{emoji} {taste}"

                    if item.get('price'):
                        btn_text += f" ({item['price']} руб)"

                    markup.add(telebot.types.KeyboardButton(btn_text))

                markup.add(telebot.types.KeyboardButton('↩️ Выбрать другой бренд'))
                markup.add(telebot.types.KeyboardButton('🏠 Главное меню'))

                user_states[message.chat.id] = {'step': 'choose_taste', 'brand': brand}

                bot.send_message(
                    message.chat.id,
                    f"🏷️ <b>Бренд:</b> {brand}\n🍇 <b>Выберите вкус:</b>",
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                return

        # Если дошли сюда, показываем бренды
        bot.send_message(message.chat.id, "Выберите бренд:")
        handle_back_message = type('obj', (object,), {'text': '↩️ Выбрать другой бренд', 'chat': message.chat})()
        handle_back(handle_back_message)


# ========== ЗАПУСК БОТА ==========
if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("✅ БОТ ЗАПУЩЕН")
    print("=" * 50)
    print("\n🎯 Источник данных: лист 'Для_бота'")
    print("📝 Запись продаж: лист 'Продажи'")
    print("📊 Автоматический подсчёт остатков: ВКЛЮЧЕН")
    print("\n🛑 Для остановки: Ctrl+C\n")

    # Пробуем загрузить товары при старте
    try:
        load_items_from_bot_sheet()
    except Exception as e:
        print(f"⚠️ Не удалось загрузить товары при старте: {e}")
        print("ℹ️ Товары загрузятся при первом использовании")

    try:
        bot.polling(none_stop=True, interval=2)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
        sys.exit(0)
    except Exception as polling_error:
        print(f"\n❌ Ошибка бота: {polling_error}")
        traceback.print_exc()
        sys.exit(1)
# ========== ЗАПУСК БОТА (ВЕРСИЯ ДЛЯ BAT-ФАЙЛА) ==========
if __name__ == '__main__':
    import time
    import traceback
    from datetime import datetime

    # Создаём папку для логов
    import os

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    print("\n" + "=" * 60)
    print("🤖 БОТ TOKYO VAPE - ПРОДАВЕЦ ВЕРСИЯ")
    print("=" * 60)
    print("📅 Запущен:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    print("👤 Для управления используйте файл bot_manager.bat")
    print("📁 Логи ошибок: папка 'logs'")
    print("🔄 Автоперезапуск: ВКЛЮЧЕН")
    print("=" * 60 + "\n")

    # Загружаем товары
    try:
        load_items_from_bot_sheet()
    except Exception as e:
        print(f"⚠️ Не удалось загрузить товары: {e}")

    # Бесконечный цикл с перезапуском
    restart_count = 0

    while restart_count < 100:  # Максимум 100 перезапусков
        try:
            print(f"\n🌀 Запуск бота...")
            bot.polling(none_stop=True, interval=2, timeout=30)

        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен (Ctrl+C)")
            break

        except Exception as e:
            restart_count += 1
            error_time = datetime.now().strftime("%H:%M:%S")

            # Логируем ошибку
            log_file = os.path.join(log_dir, f"error_{datetime.now().strftime('%Y%m%d')}.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 50}\n")
                f.write(f"Ошибка [{error_time}]: {str(e)}\n")
                f.write(f"Перезапуск #{restart_count}\n")
                f.write(f"{traceback.format_exc()}\n")

            print(f"\n❌ Ошибка [{error_time}]: {str(e)}")
            print(f"🔄 Перезапуск через 10 секунд... ({restart_count}/100)")

            # Ждём перед перезапуском
            time.sleep(10)

            # Очищаем кэш при перезапуске
            user_states.clear()
            assortment_cache.clear()
            assortment_by_brand.clear()

    print(f"\n🚫 Достигнут максимум перезапусков. Бот остановлен.")
    print("Для повторного запуска откройте start_bot.bat")
    input("Нажмите Enter для выхода...")
print(f"\n🚫 Достигнут максимум перезапусков. Бот остановлен.")
print("Для повторного запуска откройте start_bot.bat")
input("Нажмите Enter для выхода...")


def send_admin_alert(message):
    """Отправляет уведомление админу (тебе)"""
    try:
        admin_id = 1497851087  # Твой ID в Telegram - ЗАМЕНИ НА СВОЙ!
        bot.send_message(admin_id, f"⚠️ {message}")
    except Exception as alert_error:
        print(f"Не удалось отправить алерт: {alert_error}")
        pass


# ========== ЗАПУСК БОТА ==========
if __name__ == '__main__':
    import time
    import traceback
    from datetime import datetime

    print("\n" + "=" * 60)
    print("🤖 БОТ TOKYO VAPE - ПРОДАВЕЦ ВЕРСИЯ")
    print("=" * 60)
    print("📅 Запущен:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    print("📱 Продавцы работают через Telegram на телефонах")
    print("💻 Компьютер в магазине должен быть всегда включен")
    print("🔄 Автоперезапуск при ошибках: ВКЛЮЧЕН")
    print("=" * 60 + "\n")

    # Загружаем товары
    try:
        load_items_from_bot_sheet()
    except Exception as load_error:
        print(f"⚠️ Не удалось загрузить товары: {load_error}")
        send_admin_alert(f"Не загрузились товары: {load_error}")

    # Бесконечный цикл с перезапуском
    restart_count = 0

    while restart_count < 100:  # Максимум 100 перезапусков
        try:
            print(f"\n🌀 Запуск бота...")
            bot.polling(none_stop=True, interval=2, timeout=30)

        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен (Ctrl+C)")
            send_admin_alert("Бот остановлен вручную")
            break

        except Exception as polling_error:
            restart_count += 1
            error_time = datetime.now().strftime("%H:%M:%S")

            # Отправляем уведомление тебе
            send_admin_alert(f"Бот упал: {str(polling_error)[:50]}")

            # Логируем ошибку
            log_dir = "logs"
            import os

            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            log_file = os.path.join(log_dir, f"error_{datetime.now().strftime('%Y%m%d')}.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 50}\n")
                f.write(f"Ошибка [{error_time}]: {str(polling_error)}\n")
                f.write(f"Перезапуск #{restart_count}\n")
                f.write(f"{traceback.format_exc()}\n")

            print(f"\n❌ Ошибка [{error_time}]: {str(polling_error)}")
            print(f"🔄 Перезапуск через 10 секунд... ({restart_count}/100)")

            # Ждём перед перезапуском
            time.sleep(10)

            # Очищаем кэш при перезапуске
            user_states.clear()
            assortment_cache.clear()
            assortment_by_brand.clear()

    print(f"\n🚫 Достигнут максимум перезапусков. Бот остановлен.")
    send_admin_alert("🚫 Бот остановлен: максимум перезапусков")
    print("Для повторного запуска откройте start_bot.bat")
    input("Нажмите Enter для выхода...")