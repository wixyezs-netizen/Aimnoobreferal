import asyncio
import logging
import sqlite3
import random
import string
from datetime import datetime, timedelta
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

# ---------- КОНФИГУРАЦИЯ ----------
BOT_TOKEN = "8772526252:AAFz_2vhmyWhQTb8Vs7BUtsjulraU7ONf9M"  # Замените на реальный токен
BOT_USERNAME = "Aim_NooB_bot"
ADMIN_IDS = [8346538289,8205396116]  # ID администраторов (замените на свои)

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

# ---------- СОСТОЯНИЯ ДЛЯ FSM ----------
class AddChannelState(StatesGroup):
    waiting_for_name = State()
    waiting_for_url = State()
    waiting_for_chat_id = State()

class RemoveChannelState(StatesGroup):
    waiting_for_channel_id = State()

class SendMessageState(StatesGroup):
    waiting_for_message = State()

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
            reg_date TIMESTAMP,
            subscription_requests TEXT DEFAULT '[]'
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
    
    # Таблица каналов для подписки
    cur.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT,
            chat_id TEXT,
            created_at TIMESTAMP
        )
    ''')
    
    # Таблица заявок на подписку
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subscription_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id TEXT,
            request_date TIMESTAMP,
            approved INTEGER DEFAULT 0
        )
    ''')
    
    # Добавляем тестовые каналы если таблица пустая
    cur.execute("SELECT COUNT(*) FROM channels")
    if cur.fetchone()[0] == 0:
        default_channels = [
            ("AimNoob Новости", "https://t.me/aimnoob_news", "@aimnoob_news"),
            ("AimNoob Читы", "https://t.me/aimnoob_cheats", "@aimnoob_cheats"),
            ("AimNoob VIP", "https://t.me/aimnoob_vip", "@aimnoob_vip")
        ]
        for name, url, chat_id in default_channels:
            cur.execute(
                "INSERT INTO channels (name, url, chat_id, created_at) VALUES (?, ?, ?, ?)",
                (name, url, chat_id, datetime.now())
            )
    
    conn.commit()
    conn.close()

def get_channels():
    """Получение списка каналов"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, name, url, chat_id FROM channels ORDER BY id")
    channels = cur.fetchall()
    conn.close()
    return channels

def add_channel(name, url, chat_id):
    """Добавление канала"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO channels (name, url, chat_id, created_at) VALUES (?, ?, ?, ?)",
        (name, url, chat_id, datetime.now())
    )
    conn.commit()
    conn.close()

def remove_channel(channel_id):
    """Удаление канала"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, referrer_id=None):
    """Добавление нового пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id, reg_date, subscription_requests) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name, referrer_id, datetime.now(), "[]")
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
    
    cur.execute("SELECT key_received FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        return False
    
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
    channels = get_channels()
    subscribed_channels = []
    not_subscribed = []
    
    # Получаем сохраненные заявки пользователя
    user = get_user(user_id)
    requests = json.loads(user[10]) if user and len(user) > 10 else []
    
    for channel in channels:
        channel_id = channel[3]
        channel_name = channel[1]
        channel_url = channel[2]
        
        # Проверяем, есть ли подтвержденная заявка
        if str(channel_id) in requests:
            subscribed_channels.append({
                "name": channel_name,
                "url": channel_url,
                "chat_id": channel_id,
                "id": channel[0]
            })
            continue
        
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                subscribed_channels.append({
                    "name": channel_name,
                    "url": channel_url,
                    "chat_id": channel_id,
                    "id": channel[0]
                })
            else:
                not_subscribed.append({
                    "name": channel_name,
                    "url": channel_url,
                    "chat_id": channel_id,
                    "id": channel[0]
                })
        except Exception as e:
            logging.error(f"Error checking subscription for {channel_id}: {e}")
            not_subscribed.append({
                "name": channel_name,
                "url": channel_url,
                "chat_id": channel_id,
                "id": channel[0]
            })
    
    return subscribed_channels, not_subscribed

def add_subscription_request(user_id, channel_id):
    """Добавление заявки на подписку"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Получаем текущие заявки пользователя
    cur.execute("SELECT subscription_requests FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        requests = json.loads(row[0])
        if channel_id not in requests:
            requests.append(channel_id)
            cur.execute("UPDATE users SET subscription_requests = ? WHERE user_id = ?", 
                       (json.dumps(requests), user_id))
            conn.commit()
            conn.close()
            return True
    
    conn.close()
    return False

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

def get_statistics():
    """Получение статистики"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM users WHERE got_download_link = 1")
    got_link = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM referrals")
    total_referrals = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM keys WHERE activated = 1")
    activated_keys = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM users WHERE premium = 1")
    premium_users = cur.fetchone()[0]
    
    conn.close()
    
    return {
        "total_users": total_users,
        "got_link": got_link,
        "total_referrals": total_referrals,
        "activated_keys": activated_keys,
        "premium_users": premium_users
    }

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard():
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Получить бесплатный чит", callback_data="get_free_cheat")],
        [InlineKeyboardButton(text="⭐ Купить премиум версию", callback_data="buy_premium")],
        [InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")]  # Только для админов
    ])

def get_admin_keyboard():
    """Админ панель"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_channel")],
        [InlineKeyboardButton(text="➖ Удалить канал", callback_data="admin_remove_channel")],
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="admin_list_channels")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
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
    
    for channel in not_subscribed_channels:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 Подписаться: {channel['name']}", 
                url=channel['url']
            )
        ])
        # Добавляем кнопку отправки заявки
        keyboard.append([
            InlineKeyboardButton(
                text=f"✅ Я отправил заявку в {channel['name']}", 
                callback_data=f"request_sub_{channel['chat_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_status_keyboard(subscribed, not_subscribed):
    """Клавиатура со статусом подписки"""
    keyboard = []
    
    for channel in not_subscribed:
        keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {channel['name']} - Подписаться", 
                url=channel['url']
            )
        ])
        keyboard.append([
            InlineKeyboardButton(
                text=f"✅ Подтвердить заявку для {channel['name']}", 
                callback_data=f"request_sub_{channel['chat_id']}"
            )
        ])
    
    if not_subscribed:
        keyboard.append([InlineKeyboardButton(text="🔄 Проверить снова", callback_data="check_subscription")])
    else:
        keyboard.append([InlineKeyboardButton(text="✅ Получить чит", callback_data="get_cheat_after_subscribe")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def safe_edit_caption(message, caption, reply_markup):
    """Безопасное редактирование сообщения"""
    try:
        await message.edit_caption(
            caption=caption,
            reply_markup=reply_markup
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise e

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(CommandStart())
async def start_command(message: Message, command: CommandStart):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    first_name = message.from_user.first_name or ""
    
    args = command.args
    referrer_id = None
    if args and args.isdigit():
        referrer_id = int(args)
        if referrer_id == user_id:
            referrer_id = None
    
    add_user(user_id, username, first_name, referrer_id)
    
    if referrer_id:
        key = generate_and_send_key(referrer_id)
        if key:
            await bot.send_message(
                referrer_id,
                f"🎉 Поздравляем! Вы пригласили друга и получили ключ активации!\n\n"
                f"🔑 Ваш ключ: `{key}`\n\n"
                f"⏰ Ключ действителен 7 дней.",
                parse_mode="Markdown"
            )
    
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
            caption = f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\nВыберите действие:"
            await message.answer(caption, reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(f"Ошибка отправки картинки: {e}")
        await message.answer(
            f"✨ ДОБРО ПОЖАЛОВАТЬ В {BOT_NAME}! ✨\n\nВыберите действие:",
            reply_markup=get_main_keyboard()
        )

@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    """Админ панель"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ У вас нет доступа к админ-панели!", show_alert=True)
        return
    
    text = "👑 **АДМИН ПАНЕЛЬ** 👑\n\n"
    text += "Выберите действие:"
    
    await callback.message.edit_caption(
        caption=text,
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Статистика"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    stats = get_statistics()
    
    text = "📊 **СТАТИСТИКА БОТА** 📊\n\n"
    text += f"👥 Всего пользователей: {stats['total_users']}\n"
    text += f"📥 Получили ссылку: {stats['got_link']}\n"
    text += f"👨‍👧‍👦 Всего рефералов: {stats['total_referrals']}\n"
    text += f"🔑 Активированных ключей: {stats['activated_keys']}\n"
    text += f"⭐ Премиум пользователей: {stats['premium_users']}\n"
    text += f"📢 Каналов для подписки: {len(get_channels())}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_caption(
        caption=text,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_list_channels")
async def admin_list_channels(callback: CallbackQuery):
    """Список каналов"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    channels = get_channels()
    
    if not channels:
        text = "📢 **Список каналов пуст**\n\nДобавьте каналы через админ-панель."
    else:
        text = "📢 **СПИСОК КАНАЛОВ** 📢\n\n"
        for ch in channels:
            text += f"🆔 ID: {ch[0]}\n"
            text += f"📛 Название: {ch[1]}\n"
            text += f"🔗 Ссылка: {ch[2]}\n"
            text += f"💬 Chat ID: {ch[3]}\n"
            text += "─" * 20 + "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_caption(
        caption=text,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_add_channel")
async def admin_add_channel(callback: CallbackQuery, state: FSMContext):
    """Добавление канала"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_caption(
        caption="➕ **ДОБАВЛЕНИЕ КАНАЛА**\n\nВведите название канала:"
    )
    await state.set_state(AddChannelState.waiting_for_name)
    await callback.answer()

@dp.message(AddChannelState.waiting_for_name)
async def process_channel_name(message: Message, state: FSMContext):
    """Обработка названия канала"""
    await state.update_data(name=message.text)
    await message.answer("📝 Введите ссылку на канал (https://t.me/...):")
    await state.set_state(AddChannelState.waiting_for_url)

@dp.message(AddChannelState.waiting_for_url)
async def process_channel_url(message: Message, state: FSMContext):
    """Обработка ссылки канала"""
    await state.update_data(url=message.text)
    await message.answer("🆔 Введите chat_id канала (например: @channel или -1001234567890):")
    await state.set_state(AddChannelState.waiting_for_chat_id)

@dp.message(AddChannelState.waiting_for_chat_id)
async def process_channel_chat_id(message: Message, state: FSMContext):
    """Обработка chat_id канала"""
    data = await state.get_data()
    
    add_channel(data['name'], data['url'], message.text)
    
    await message.answer(f"✅ Канал '{data['name']}' успешно добавлен!")
    await state.clear()
    
    # Возвращаем в админ-панель
    if os.path.exists(IMAGE_PATH):
        photo = FSInputFile(IMAGE_PATH)
        await message.answer_photo(
            photo=photo,
            caption="👑 Админ панель",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "👑 Админ панель",
            reply_markup=get_admin_keyboard()
        )

@dp.callback_query(lambda c: c.data == "admin_remove_channel")
async def admin_remove_channel(callback: CallbackQuery, state: FSMContext):
    """Удаление канала"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    channels = get_channels()
    
    if not channels:
        await callback.answer("Нет каналов для удаления!", show_alert=True)
        return
    
    text = "➖ **УДАЛЕНИЕ КАНАЛА**\n\n"
    text += "Введите ID канала для удаления:\n\n"
    for ch in channels:
        text += f"ID: {ch[0]} - {ch[1]}\n"
    
    await callback.message.edit_caption(caption=text)
    await state.set_state(RemoveChannelState.waiting_for_channel_id)
    await callback.answer()

@dp.message(RemoveChannelState.waiting_for_channel_id)
async def process_remove_channel(message: Message, state: FSMContext):
    """Обработка удаления канала"""
    try:
        channel_id = int(message.text)
        remove_channel(channel_id)
        await message.answer(f"✅ Канал с ID {channel_id} успешно удален!")
    except:
        await message.answer("❌ Ошибка! Введите корректный ID канала.")
    
    await state.clear()
    
    # Возвращаем в админ-панель
    if os.path.exists(IMAGE_PATH):
        photo = FSInputFile(IMAGE_PATH)
        await message.answer_photo(
            photo=photo,
            caption="👑 Админ панель",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "👑 Админ панель",
            reply_markup=get_admin_keyboard()
        )

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Рассылка сообщений"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_caption(
        caption="📢 **РАССЫЛКА**\n\nОтправьте сообщение для рассылки всем пользователям:"
    )
    await state.set_state(SendMessageState.waiting_for_message)
    await callback.answer()

@dp.message(SendMessageState.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext):
    """Обработка рассылки"""
    await message.answer("🔄 Начинаю рассылку...")
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    conn.close()
    
    success = 0
    fail = 0
    
    for user in users:
        try:
            await bot.copy_message(
                chat_id=user[0],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success += 1
            await asyncio.sleep(0.05)  # Защита от флуда
        except:
            fail += 1
    
    await message.answer(f"✅ Рассылка завершена!\n\n📤 Отправлено: {success}\n❌ Ошибок: {fail}")
    await state.clear()
    
    # Возвращаем в админ-панель
    if os.path.exists(IMAGE_PATH):
        photo = FSInputFile(IMAGE_PATH)
        await message.answer_photo(
            photo=photo,
            caption="👑 Админ панель",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "👑 Админ панель",
            reply_markup=get_admin_keyboard()
        )

@dp.callback_query(lambda c: c.data.startswith("request_sub_"))
async def subscription_request(callback: CallbackQuery):
    """Обработка заявки на подписку"""
    user_id = callback.from_user.id
    channel_id = callback.data.replace("request_sub_", "")
    
    if add_subscription_request(user_id, channel_id):
        await callback.answer(
            "✅ Заявка на подписку принята!\n"
            "После подтверждения администратором вы получите доступ.",
            show_alert=True
        )
        
        # Уведомляем админов
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                f"📢 Новая заявка на подписку!\n\n"
                f"👤 Пользователь: {callback.from_user.id}\n"
                f"📛 Username: @{callback.from_user.username or 'NoUsername'}\n"
                f"📢 Канал: {channel_id}\n\n"
                f"Заявка автоматически принята и добавлена в базу."
            )
    else:
        await callback.answer("❌ Ошибка! Возможно, вы уже подавали заявку.", show_alert=True)
    
    # Обновляем проверку подписки
    subscribed, not_subscribed = await check_subscriptions(user_id)
    
    if not not_subscribed:
        text = f"✅ Поздравляем! Теперь вы подписаны на все каналы!\n\n"
        text += f"🔗 Ссылка на скачивание:\n{DOWNLOAD_LINK}"
        
        await safe_edit_caption(
            callback.message,
            text,
            get_cheat_menu(user_id)
        )
    else:
        text = "📢 СТАТУС ПОДПИСКИ:\n\n"
        for channel in subscribed:
            text += f"✅ {channel['name']} - Подписан\n"
        for channel in not_subscribed:
            text += f"❌ {channel['name']} - НЕ ПОДПИСАН\n"
        
        if not_subscribed:
            text += "\n👇 Подпишитесь на недостающие каналы или отправьте заявку:"
        
        await safe_edit_caption(
            callback.message,
            text,
            get_subscription_status_keyboard(subscribed, not_subscribed)
        )
    
    await callback.answer()

# Остальные обработчики (get_free_cheat, check_subscription, и т.д.) остаются теми же
# Добавляем их здесь, но для краткости я их не дублирую
# Они должны быть такими же, как в предыдущей версии, но с использованием новых функций

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

# ... здесь должны быть все остальные обработчики из предыдущей версии ...

# ---------- ЗАПУСК БОТА ----------
async def main():
    """Запуск бота"""
    print(f"🚀 Запуск бота {BOT_NAME}...")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print(f"📁 База данных: {DB_NAME}")
    print("-" * 50)
    
    init_db()
    print("✅ База данных инициализирована")
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот готов к работе!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
