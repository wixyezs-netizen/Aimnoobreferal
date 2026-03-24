import asyncio
import logging
import sqlite3
import random
import string
from datetime import datetime, timedelta
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

# ---------- КОНФИГУРАЦИЯ ----------
BOT_TOKEN = "8772526252:AAFz_2vhmyWhQTb8Vs7BUtsjulraU7ONf9M"  # Замените на реальный токен бота @Aim_NooB_bot
BOT_USERNAME = "Aim_NooB_bot"  # Username вашего бота

# Каналы для подписки (название, ссылка, ID)
CHANNELS = [
    {
        "name": "AimNooB АПК ЧИТЫ",
        "url": "https://t.me/+NwnmmEH8H40yZmIy",
        "chat_id": "-1003638838896"
    }
]

# Путь к картинке
IMAGE_PATH = "images/aimnoob.jpg"

# Ссылка на скачивание чита
DOWNLOAD_LINK = "https://go.linkify.ru/2GPF"

# Название бота
BOT_NAME = "AimNoob Cheats"

# База данных
DB_NAME = "aimnoob.db"

# ---------- ИНИЦИАЛИЗАЦИЯ ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# ---------- РАБОТА С БАЗОЙ ДАННЫХ ----------
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            referrer_id INTEGER,
            got_download_link INTEGER DEFAULT 0,
            key_received INTEGER DEFAULT 0,
            premium INTEGER DEFAULT 0,
            premium_expires TIMESTAMP,
            reg_date TIMESTAMP
        )
    ''')
    
    # Таблица рефералов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_user_id INTEGER PRIMARY KEY,
            date TIMESTAMP
        )
    ''')
    
    # Таблица ключей активации
    cur.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            activated INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, referrer_id=None):
    """Добавление нового пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id, reg_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, referrer_id, datetime.now())
        )
        conn.commit()
        
        if referrer_id:
            cur.execute("INSERT INTO referrals (referrer_id, referred_user_id, date) VALUES (?, ?, ?)",
                        (referrer_id, user_id, datetime.now()))
            conn.commit()
    
    conn.close()

def get_user(user_id):
    """Получение информации о пользователе"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

def set_download_link_got(user_id):
    """Отметить, что пользователь получил ссылку на скачивание"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET got_download_link = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_referral_count(user_id):
    """Получение количества рефералов"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_referral_link(user_id):
    """Получение реферальной ссылки"""
    return f"https://t.me/{BOT_USERNAME}?start={user_id}"

def generate_key():
    """Генерация случайного ключа"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def generate_and_send_key(user_id):
    """Генерация и отправка ключа пользователю"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Проверяем, получал ли пользователь уже ключ
    cur.execute("SELECT key_received FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        return False
    
    # Проверяем количество рефералов
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cur.fetchone()[0]
    
    if count >= 3:
        key = generate_key()
        expires = datetime.now() + timedelta(days=7)
        cur.execute("INSERT INTO keys (key, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (key, user_id, datetime.now(), expires))
        cur.execute("UPDATE users SET key_received = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return key
    else:
        conn.close()
        return None

async def check_subscriptions(user_id):
    """Проверка подписки на все каналы"""
    subscribed_channels = []
    not_subscribed = []
    
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["chat_id"], user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                subscribed_channels.append(channel)
            else:
                not_subscribed.append(channel)
        except Exception as e:
            logging.error(f"Ошибка проверки подписки на {channel['chat_id']}: {e}")
            not_subscribed.append(channel)
    
    return subscribed_channels, not_subscribed

def activate_premium_key(key, user_id):
    """Активация премиум ключа"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT key, expires_at, activated FROM keys WHERE key = ?", (key,))
    row = cur.fetchone()
    
    if row and not row[2] and datetime.now() < datetime.fromisoformat(row[1]):
        cur.execute("UPDATE keys SET activated = 1 WHERE key = ?", (key,))
        cur.execute("UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?", 
                   (row[1], user_id))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard():
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Получить бесплатный чит", callback_data="get_free_cheat")],
        [InlineKeyboardButton(text="⭐ Купить премиум версию", callback_data="buy_premium")]
    ])

def get_cheat_menu(user_id):
    """Меню после получения чита"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Проверить рефералов", callback_data="check_referrals")],
        [InlineKeyboardButton(text="📋 Моя реферальная ссылка", callback_data="copy_link")],
        [InlineKeyboardButton(text="⭐ Купить премиум", callback_data="buy_premium")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_menu")]
    ])

def get_subscription_keyboard(not_subscribed_channels):
    """Клавиатура для подписки с кнопками на каждый канал"""
    keyboard = []
    
    # Добавляем кнопки для каждого канала
    for channel in not_subscribed_channels:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 Подписаться: {channel['name']}", 
                url=channel['url']
            )
        ])
    
    # Добавляем кнопку проверки
    keyboard.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_status_keyboard(subscribed, not_subscribed):
    """Клавиатура со статусом подписки"""
    keyboard = []
    
    # Показываем подписанные каналы (галочки)
    for channel in subscribed:
        keyboard.append([
            InlineKeyboardButton(
                text=f"✅ {channel['name']} - Подписан", 
                callback_data="dummy",
                url=channel['url']
            )
        ])
    
    # Показываем неподписанные каналы (кнопки подписки)
    for channel in not_subscribed:
        keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {channel['name']} - Подписаться", 
                url=channel['url']
            )
        ])
    
    # Добавляем кнопку проверки
    if not_subscribed:
        keyboard.append([InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")])
    else:
        keyboard.append([InlineKeyboardButton(text="✅ Получить чит", callback_data="get_cheat_after_subscribe")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(CommandStart())
async def start_command(message: Message, command: CommandStart):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    first_name = message.from_user.first_name or ""
    
    # Обработка реферальной ссылки
    args = command.args
    referrer_id = None
    if args and args.isdigit():
        referrer_id = int(args)
        if referrer_id == user_id:
            referrer_id = None
    
    # Добавляем пользователя
    add_user(user_id, username, first_name, referrer_id)
    
    # Если пользователь пришел по реферальной ссылке
    if referrer_id:
        key = generate_and_send_key(referrer_id)
        if key:
            await bot.send_message(
                referrer_id,
                f"🎉 Поздравляем! Вы пригласили друга и получили ключ активации!\n\n"
                f"🔑 Ваш ключ: `{key}`\n\n"
                f"⏰ Ключ действителен 7 дней.\n"
                f"Используйте его в нашем софте для активации премиум функций.",
                parse_mode="Markdown"
            )
    
    # Отправляем приветствие с картинкой
    try:
        if os.path.exists(IMAGE_PATH):
            photo = FSInputFile(IMAGE_PATH)
            caption = f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\n"
            caption += "🎯 Лучшие читы для Standoff 2\n"
            caption += "🔥 AIMBOT | WALLHACK | ESP | NO RECOIL\n\n"
            caption += "Выберите действие:"
            
            await message.answer_photo(
                photo=photo, 
                caption=caption, 
                reply_markup=get_main_keyboard()
            )
        else:
            caption = f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\n"
            caption += "Выберите действие:"
            await message.answer(
                caption, 
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logging.error(f"Ошибка отправки картинки: {e}")
        await message.answer(
            f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\nВыберите действие:",
            reply_markup=get_main_keyboard()
        )

@dp.callback_query(lambda c: c.data == "get_free_cheat")
async def get_free_cheat(callback: CallbackQuery):
    """Получение бесплатного чита - проверка подписки"""
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    # Проверяем, получал ли пользователь уже ссылку
    if user and user[3] == 1:
        text = f"✅ Вы уже получили ссылку на скачивание!\n\n"
        text += f"🔗 Ссылка: {DOWNLOAD_LINK}\n\n"
        text += f"❗ Для активации чита вам понадобится ключ.\n"
        text += f"Получите ключ, пригласив 3 друзей:\n\n"
        text += f"🔗 {get_referral_link(user_id)}\n\n"
        text += f"👥 Приглашено: {get_referral_count(user_id)} из 3\n\n"
        text += f"⏰ Ключ действует 7 дней."
        
        await callback.message.edit_caption(
            caption=text,
            reply_markup=get_cheat_menu(user_id)
        )
        await callback.answer()
        return
    
    # Проверяем подписки
    subscribed, not_subscribed = await check_subscriptions(user_id)
    
    if not not_subscribed:
        # Если подписан на все каналы
        set_download_link_got(user_id)
        text = f"✅ Подписка подтверждена!\n\n"
        text += f"🔗 Ссылка на скачивание:\n{DOWNLOAD_LINK}\n\n"
        text += f"❗ Для активации чита вам понадобится ключ.\n"
        text += f"Получите ключ, пригласив 3 друзей:\n\n"
        text += f"🔗 {get_referral_link(user_id)}\n\n"
        text += f"👥 Приглашено: {get_referral_count(user_id)} из 3\n\n"
        text += f"⏰ Ключ действует 7 дней."
        
        await callback.message.edit_caption(
            caption=text,
            reply_markup=get_cheat_menu(user_id)
        )
    else:
        # Показываем список каналов для подписки
        text = "📢 ДЛЯ ПОЛУЧЕНИЯ ЧИТА НЕОБХОДИМО ПОДПИСАТЬСЯ НА КАНАЛЫ:\n\n"
        text += "👇 Нажмите на кнопки ниже, чтобы подписаться:\n\n"
        
        for channel in not_subscribed:
            text += f"❌ {channel['name']}\n"
        
        text += f"\n✅ После подписки нажмите 'Проверить подписку'"
        
        await callback.message.edit_caption(
            caption=text,
            reply_markup=get_subscription_keyboard(not_subscribed)
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription(callback: CallbackQuery):
    """Проверка подписки на каналы"""
    user_id = callback.from_user.id
    
    subscribed, not_subscribed = await check_subscriptions(user_id)
    
    if not not_subscribed:
        # Если подписан на все каналы
        user = get_user(user_id)
        if user and user[3] == 0:  # Если еще не получал ссылку
            set_download_link_got(user_id)
            text = f"✅ ПОЗДРАВЛЯЕМ! ВЫ ПОДПИСАНЫ НА ВСЕ КАНАЛЫ! ✅\n\n"
            text += f"🔗 Ссылка на скачивание:\n{DOWNLOAD_LINK}\n\n"
            text += f"❗ Для активации чита вам понадобится ключ.\n"
            text += f"Получите ключ, пригласив 3 друзей:\n\n"
            text += f"🔗 {get_referral_link(user_id)}\n\n"
            text += f"👥 Приглашено: {get_referral_count(user_id)} из 3\n\n"
            text += f"⏰ Ключ действует 7 дней."
            
            await callback.message.edit_caption(
                caption=text,
                reply_markup=get_cheat_menu(user_id)
            )
        else:
            await callback.message.edit_caption(
                caption=f"✅ Вы уже получили доступ к читу!\n\nСсылка: {DOWNLOAD_LINK}",
                reply_markup=get_cheat_menu(user_id)
            )
    else:
        # Показываем статус подписки с кнопками
        text = "📢 СТАТУС ПОДПИСКИ:\n\n"
        
        for channel in subscribed:
            text += f"✅ {channel['name']} - Подписан\n"
        
        for channel in not_subscribed:
            text += f"❌ {channel['name']} - НЕ ПОДПИСАН\n"
        
        text += "\n👇 Подпишитесь на недостающие каналы и нажмите проверку:"
        
        await callback.message.edit_caption(
            caption=text,
            reply_markup=get_subscription_status_keyboard(subscribed, not_subscribed)
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "get_cheat_after_subscribe")
async def get_cheat_after_subscribe(callback: CallbackQuery):
    """Получение чита после успешной подписки"""
    user_id = callback.from_user.id
    
    # Еще раз проверяем подписку
    subscribed, not_subscribed = await check_subscriptions(user_id)
    
    if not not_subscribed:
        set_download_link_got(user_id)
        text = f"✅ ПОДПИСКА ПОДТВЕРЖДЕНА! ✅\n\n"
        text += f"🔗 Ссылка на скачивание:\n{DOWNLOAD_LINK}\n\n"
        text += f"❗ Для активации чита вам понадобится ключ.\n"
        text += f"Получите ключ, пригласив 3 друзей:\n\n"
        text += f"🔗 {get_referral_link(user_id)}\n\n"
        text += f"👥 Приглашено: {get_referral_count(user_id)} из 3\n\n"
        text += f"⏰ Ключ действует 7 дней."
        
        await callback.message.edit_caption(
            caption=text,
            reply_markup=get_cheat_menu(user_id)
        )
    else:
        await callback.answer("❌ Вы не подписаны на все каналы!", show_alert=True)
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "check_referrals")
async def check_referrals(callback: CallbackQuery):
    """Проверка количества рефералов"""
    user_id = callback.from_user.id
    count = get_referral_count(user_id)
    user = get_user(user_id)
    
    if count >= 3:
        if user and user[4] == 1:
            text = f"✅ ВЫ УЖЕ ПОЛУЧИЛИ КЛЮЧ АКТИВАЦИИ!\n\n"
            text += f"👥 Приглашено друзей: {count}\n"
            text += f"🔑 Ключ был отправлен вам в личные сообщения."
        else:
            text = f"🎉 ПОЗДРАВЛЯЕМ! ВЫ ПРИГЛАСИЛИ {count} ДРУЗЕЙ! 🎉\n\n"
            text += f"🔑 Генерирую ключ активации..."
            await callback.message.answer(text)
            
            key = generate_and_send_key(user_id)
            if key:
                text = f"✅ ВАШ КЛЮЧ АКТИВАЦИИ:\n\n"
                text += f"🔑 `{key}`\n\n"
                text += f"⏰ Действителен 7 дней\n"
                text += f"Используйте его для активации чита.\n\n"
                text += f"💡 Команда для активации: /activate {key}"
                await callback.message.answer(text, parse_mode="Markdown")
            return
    else:
        text = f"👥 СТАТИСТИКА РЕФЕРАЛОВ:\n\n"
        text += f"📊 Приглашено друзей: {count} из 3\n"
        text += f"📢 Осталось пригласить: {3 - count}\n\n"
        text += f"🔗 ВАША РЕФЕРАЛЬНАЯ ССЫЛКА:\n"
        text += f"`{get_referral_link(user_id)}`\n\n"
        text += f"💡 Отправьте ссылку друзьям - после их регистрации счетчик увеличится.\n"
        text += f"🎁 За 3 приглашенных друзей вы получите ключ активации на 7 дней!"
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "copy_link")
async def copy_link(callback: CallbackQuery):
    """Отправка реферальной ссылки"""
    user_id = callback.from_user.id
    link = get_referral_link(user_id)
    
    text = f"🔗 ВАША РЕФЕРАЛЬНАЯ ССЫЛКА:\n\n"
    text += f"`{link}`\n\n"
    text += f"📤 Отправьте её друзьям, чтобы пригласить их.\n"
    text += f"👥 Пригласите 3 друзей и получите ключ активации!\n\n"
    text += f"🎁 Бонус: {3 - get_referral_count(user_id)} друг(а) до получения ключа!"
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "refresh_menu")
async def refresh_menu(callback: CallbackQuery):
    """Обновление меню"""
    user_id = callback.from_user.id
    
    text = f"✅ ВАШ ДОСТУП К ЧИТУ АКТИВЕН!\n\n"
    text += f"🔗 Ссылка на скачивание:\n{DOWNLOAD_LINK}\n\n"
    text += f"👥 Приглашено друзей: {get_referral_count(user_id)} из 3\n\n"
    text += f"🔗 Реферальная ссылка:\n{get_referral_link(user_id)}\n\n"
    text += f"💡 Пригласите 3 друзей и получите ключ активации!"
    
    await callback.message.edit_caption(
        caption=text,
        reply_markup=get_cheat_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "buy_premium")
async def buy_premium(callback: CallbackQuery):
    """Покупка премиум версии"""
    text = f"⭐ ПРЕМИУМ ВЕРСИЯ {BOT_NAME} ⭐\n\n"
    text += "🔥 РАСШИРЕННЫЕ ВОЗМОЖНОСТИ:\n"
    text += "• AIMBOT с точной настройкой\n"
    text += "• ESP через стены (WALLHACK)\n"
    text += "• NO RECOIL + NO SPREAD\n"
    text += "• TRIGGER BOT\n"
    text += "• SKELETON ESP\n"
    text += "• Приоритетная поддержка 24/7\n"
    text += "• Без рекламы и ожидания\n\n"
    text += "💰 СТОИМОСТЬ: 499 ₽ / месяц\n"
    text += "💎 1299 ₽ / 3 месяца (скидка 15%)\n"
    text += "👑 2499 ₽ / 6 месяцев (скидка 20%)\n\n"
    text += "📦 СПОСОБЫ ОПЛАТЫ:\n"
    text += "• Карты РФ (Сбер, Тинькофф)\n"
    text += "• Криптовалюта (USDT, BTC)\n"
    text += "• Qiwi, YooMoney\n\n"
    text += "💬 ДЛЯ ПОКУПКИ СВЯЖИТЕСЬ С МЕНЕДЖЕРОМ:\n"
    text += "@AimNoobSupport"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/AimNoobSupport")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback.message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    try:
        if os.path.exists(IMAGE_PATH):
            photo = FSInputFile(IMAGE_PATH)
            caption = f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\n"
            caption += "🎯 Лучшие читы для Standoff 2\n"
            caption += "🔥 AIMBOT | WALLHACK | ESP | NO RECOIL\n\n"
            caption += "Выберите действие:"
            
            await callback.message.edit_media(
                types.InputMediaPhoto(media=photo, caption=caption),
                reply_markup=get_main_keyboard()
            )
        else:
            await callback.message.edit_caption(
                caption=f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\nВыберите действие:",
                reply_markup=get_main_keyboard()
            )
    except Exception:
        await callback.message.delete()
        if os.path.exists(IMAGE_PATH):
            photo = FSInputFile(IMAGE_PATH)
            await callback.message.answer_photo(
                photo=photo,
                caption=f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\nВыберите действие:",
                reply_markup=get_main_keyboard()
            )
        else:
            await callback.message.answer(
                f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\nВыберите действие:",
                reply_markup=get_main_keyboard()
            )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "dummy")
async def dummy_callback(callback: CallbackQuery):
    """Заглушка для кнопок без действия"""
    await callback.answer()

@dp.message(Command("activate"))
async def activate_key(message: Message):
    """Активация премиум ключа"""
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "🔑 ИСПОЛЬЗОВАНИЕ: /activate КЛЮЧ\n\n"
            "📝 Пример: /activate ABC123XYZ789\n\n"
            "💡 Где взять ключ?\n"
            "• Пригласите 3 друзей по вашей реферальной ссылке\n"
            "• Купите премиум версию у @AimNoobSupport"
        )
        return
    
    key = parts[1].strip()
    user_id = message.from_user.id
    
    if activate_premium_key(key, user_id):
        await message.answer(
            "✅ КЛЮЧ УСПЕШНО АКТИВИРОВАН! ✅\n\n"
            "🎉 ПОЗДРАВЛЯЕМ! Теперь у вас есть доступ ко всем ПРЕМИУМ функциям!\n\n"
            "🔥 ДОСТУПНЫЕ ФУНКЦИИ:\n"
            "• AIMBOT с настройкой\n"
            "• WALLHACK (ESP через стены)\n"
            "• NO RECOIL + NO SPREAD\n"
            "• TRIGGER BOT\n"
            "• SKELETON ESP\n\n"
            "💪 Наслаждайтесь игрой с AimNoob Cheats!"
        )
    else:
        await message.answer(
            "❌ НЕВЕРНЫЙ ИЛИ ИСТЕКШИЙ КЛЮЧ ❌\n\n"
            "🔑 Проверьте правильность ввода ключа\n"
            "⏰ Ключ действителен 7 дней\n\n"
            "💡 ПОЛУЧИТЕ НОВЫЙ КЛЮЧ:\n"
            "• Пригласите 3 друзей по реферальной ссылке\n"
            "• Купите премиум у @AimNoobSupport\n\n"
            f"🔗 Ваша реферальная ссылка: {get_referral_link(user_id)}"
        )

@dp.message(Command("help"))
async def help_command(message: Message):
    """Команда помощи"""
    text = f"📚 ПОМОЩЬ ПО БОТУ {BOT_NAME} 📚\n\n"
    text += "🔹 /start - Главное меню\n"
    text += "🔹 /activate КЛЮЧ - Активация ключа\n"
    text += "🔹 /help - Это сообщение\n\n"
    text += "💡 КАК ПОЛУЧИТЬ ЧИТ:\n"
    text += "1️⃣ Нажмите 'Получить бесплатный чит'\n"
    text += "2️⃣ Подпишитесь на все каналы (кнопками)\n"
    text += "3️⃣ Нажмите 'Проверить подписку'\n"
    text += "4️⃣ Получите ссылку на скачивание\n"
    text += "5️⃣ Пригласите 3 друзей для ключа активации\n\n"
    text += "⭐ ПРЕМИУМ ФУНКЦИИ:\n"
    text += "• Расширенный AIMBOT\n"
    text += "• ESP через стены\n"
    text += "• NO RECOIL\n"
    text += "• Приоритетная поддержка\n\n"
    text += "💬 ПО ВОПРОСАМ: @AimNoobSupport"
    
    await message.answer(text)

# ---------- ЗАПУСК БОТА ----------
async def main():
    """Запуск бота"""
    print(f"🚀 Запуск бота {BOT_NAME}...")
    print(f"📁 База данных: {DB_NAME}")
    print(f"🖼️ Картинка: {IMAGE_PATH if os.path.exists(IMAGE_PATH) else 'Не найдена'}")
    print(f"📢 Каналы для подписки:")
    for channel in CHANNELS:
        print(f"   • {channel['name']}: {channel['chat_id']}")
    print(f"🔗 Ссылка на скачивание: {DOWNLOAD_LINK}")
    print("-" * 50)
    
    init_db()
    print("✅ База данных инициализирована")
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот готов к работе!")
    print("🎯 AimNoob Cheats Bot запущен!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
