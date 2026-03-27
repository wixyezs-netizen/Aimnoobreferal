#!/usr/bin/env python3
"""
Telegram бот для продажи Telegram Premium, звёзд и NFT с оплатой через ЮMoney
Полная рабочая версия с улучшенной логикой
"""

import asyncio
import sqlite3
import uuid
import logging
import html
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlencode, quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, MessageHandler,
    filters
)
from telegram.constants import ParseMode

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8624719452:AAHBAWy6DDzXD_ekK-iI8_rAOj4lUr3PysA"
ADMIN_IDS = [8681521200]  # Список админов

YOOMONEY_WALLET = "4100118889570559"
YOOMONEY_ACCESS_TOKEN = "4100118889570559.3288B2E716CEEB922A26BD6BEAC58648FBFB680CCF64E4E1447D714D6FB5EA5F01F1478FAC686BEF394C8A186C98982DE563C1ABCDF9F2F61D971B61DA3C7E486CA818F98B9E0069F1C0891E090DD56A11319D626A40F0AE8302A8339DED9EB7969617F191D93275F64C4127A3ECB7AED33FCDE91CA68690EB7534C67E6C219E"
YOOMONEY_NOTIFICATION_SECRET = ""  # Секрет для HTTP-уведомлений

# Категории и товары
CATEGORIES = {
    "premium": {
        "name": "⭐ Telegram Premium",
        "emoji": "⭐",
        "products": {
            "premium_1m": {
                "name": "Premium 1 месяц",
                "price": 299,
                "description": "Telegram Premium подписка на 1 месяц.\n"
                               "• Уникальные стикеры и реакции\n"
                               "• Без рекламы\n"
                               "• Загрузка файлов до 4 ГБ\n"
                               "• Быстрая скорость загрузки",
                "delivery_type": "manual"
            },
            "premium_3m": {
                "name": "Premium 3 месяца",
                "price": 799,
                "description": "Telegram Premium подписка на 3 месяца.\nСкидка 11%!",
                "delivery_type": "manual"
            },
            "premium_6m": {
                "name": "Premium 6 месяцев",
                "price": 1499,
                "description": "Telegram Premium подписка на 6 месяцев.\nСкидка 17%!",
                "delivery_type": "manual"
            },
            "premium_12m": {
                "name": "Premium 12 месяцев",
                "price": 2699,
                "description": "Telegram Premium подписка на 12 месяцев.\nСкидка 25%!",
                "delivery_type": "manual"
            },
        }
    },
    "stars": {
        "name": "🌟 Telegram Stars",
        "emoji": "🌟",
        "products": {
            "stars_50": {
                "name": "50 Stars",
                "price": 75,
                "description": "50 Telegram Stars на ваш аккаунт.",
                "stars_amount": 50,
                "delivery_type": "manual"
            },
            "stars_100": {
                "name": "100 Stars",
                "price": 140,
                "description": "100 Telegram Stars на ваш аккаунт.\nСкидка 7%!",
                "stars_amount": 100,
                "delivery_type": "manual"
            },
            "stars_250": {
                "name": "250 Stars",
                "price": 330,
                "description": "250 Telegram Stars на ваш аккаунт.\nСкидка 12%!",
                "stars_amount": 250,
                "delivery_type": "manual"
            },
            "stars_500": {
                "name": "500 Stars",
                "price": 620,
                "description": "500 Telegram Stars на ваш аккаунт.\nСкидка 17%!",
                "stars_amount": 500,
                "delivery_type": "manual"
            },
        }
    },
    "nft": {
        "name": "🎨 NFT Коллекция",
        "emoji": "🎨",
        "products": {
            "nft_basic": {
                "name": "NFT Basic",
                "price": 199,
                "description": "Базовый NFT из нашей коллекции.\nУникальный дизайн!",
                "delivery_type": "manual"
            },
            "nft_rare": {
                "name": "NFT Rare",
                "price": 499,
                "description": "Редкий NFT из лимитированной коллекции.\nОсталось мало!",
                "delivery_type": "manual"
            },
            "nft_legendary": {
                "name": "NFT Legendary",
                "price": 999,
                "description": "Легендарный NFT. Всего 100 штук в мире!",
                "delivery_type": "manual"
            },
        }
    }
}

# Промокоды: код -> {discount_percent, max_uses, current_uses, expires_at}
PROMO_CODES = {}

CHECK_INTERVAL = 30
PAYMENT_TIMEOUT_HOURS = 24
DB_NAME = "bot_shop.db"

# Состояния ConversationHandler
(
    MAIN_MENU,
    SELECTING_CATEGORY,
    SELECTING_PRODUCT,
    PRODUCT_DETAIL,
    ENTERING_PROMO,
    CONFIRMING,
    WAITING_PAYMENT,
    ADMIN_MENU,
    ADMIN_MANUAL_ID,
    ADMIN_ADD_PROMO,
    ADMIN_BROADCAST,
    ENTERING_USERNAME,
) = range(12)

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ShopBot")


# ==================== БАЗА ДАННЫХ ====================
class Database:
    """Менеджер базы данных с контекстным управлением"""

    def __init__(self, db_name: str = DB_NAME):
        self.db_name = db_name
        self._local = {}

    def get_conn(self) -> sqlite3.Connection:
        """Получить соединение"""
        conn = sqlite3.connect(self.db_name, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self):
        """Инициализация всех таблиц"""
        conn = self.get_conn()
        cur = conn.cursor()

        cur.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                referrer_id INTEGER,
                balance INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_key TEXT NOT NULL,
                category TEXT NOT NULL,
                payment_id TEXT NOT NULL UNIQUE,
                payment_label TEXT,
                amount INTEGER NOT NULL,
                original_amount INTEGER,
                promo_code TEXT,
                discount INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                delivery_status TEXT DEFAULT 'not_delivered',
                delivery_info TEXT,
                target_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                delivered_at TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                discount_percent INTEGER NOT NULL,
                max_uses INTEGER DEFAULT -1,
                current_uses INTEGER DEFAULT 0,
                min_amount INTEGER DEFAULT 0,
                valid_products TEXT,
                created_by INTEGER,
                expires_at TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                bonus_given INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
            CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
            CREATE INDEX IF NOT EXISTS idx_payments_label ON payments(payment_label);
        ''')

        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")

    # ---------- Пользователи ----------
    def get_or_create_user(self, user_id: int, username: str = None,
                           first_name: str = None, last_name: str = None,
                           language_code: str = None, referrer_id: int = None) -> dict:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()

        if not user:
            cur.execute(
                """INSERT INTO users 
                   (user_id, username, first_name, last_name, language_code, referrer_id) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, username, first_name, last_name, language_code, referrer_id)
            )
            conn.commit()

            # Реферальная запись
            if referrer_id and referrer_id != user_id:
                cur.execute(
                    "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                    (referrer_id, user_id)
                )
                conn.commit()

            cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cur.fetchone()
        else:
            cur.execute(
                """UPDATE users SET username=?, first_name=?, last_name=?, 
                   language_code=?, updated_at=CURRENT_TIMESTAMP 
                   WHERE user_id=?""",
                (username, first_name, last_name, language_code, user_id)
            )
            conn.commit()

        result = dict(user)
        conn.close()
        return result

    def get_user(self, user_id: int) -> Optional[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_users(self) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def block_user(self, user_id: int, blocked: bool = True):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_blocked = ? WHERE user_id = ?", (int(blocked), user_id))
        conn.commit()
        conn.close()

    def update_user_spent(self, user_id: int, amount: int):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()
        conn.close()

    # ---------- Платежи ----------
    def add_payment(self, user_id: int, product_key: str, category: str,
                    payment_id: str, payment_label: str, amount: int,
                    original_amount: int = None, promo_code: str = None,
                    discount: int = 0, target_username: str = None) -> int:
        conn = self.get_conn()
        cur = conn.cursor()
        expires_at = (datetime.now() + timedelta(hours=PAYMENT_TIMEOUT_HOURS)).isoformat()
        cur.execute(
            """INSERT INTO payments 
               (user_id, product_key, category, payment_id, payment_label, 
                amount, original_amount, promo_code, discount, target_username, expires_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, product_key, category, payment_id, payment_label,
             amount, original_amount or amount, promo_code, discount,
             target_username, expires_at)
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_payment(self, payment_id: str) -> Optional[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_payment_by_label(self, label: str) -> Optional[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM payments WHERE payment_label = ?", (label,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_payment_by_row_id(self, row_id: int) -> Optional[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM payments WHERE id = ?", (row_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_payment_status(self, payment_id: str, status: str):
        conn = self.get_conn()
        cur = conn.cursor()
        paid_at = datetime.now().isoformat() if status == "success" else None
        cur.execute(
            "UPDATE payments SET status = ?, paid_at = ? WHERE payment_id = ?",
            (status, paid_at, payment_id)
        )
        conn.commit()
        conn.close()

    def mark_delivered(self, payment_id: str, delivery_info: str = ""):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            """UPDATE payments SET delivery_status = 'delivered', 
               delivery_info = ?, delivered_at = CURRENT_TIMESTAMP 
               WHERE payment_id = ?""",
            (delivery_info, payment_id)
        )
        conn.commit()
        conn.close()

    def get_pending_payments(self) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM payments 
               WHERE status = 'pending' AND expires_at > datetime('now') 
               ORDER BY created_at ASC"""
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_expired_payments(self) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM payments 
               WHERE status = 'pending' AND expires_at <= datetime('now')"""
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def expire_payments(self):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            """UPDATE payments SET status = 'expired' 
               WHERE status = 'pending' AND expires_at <= datetime('now')"""
        )
        conn.commit()
        count = cur.rowcount
        conn.close()
        return count

    def get_user_payments(self, user_id: int, limit: int = 20) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_user_active_payment(self, user_id: int) -> Optional[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM payments 
               WHERE user_id = ? AND status = 'pending' AND expires_at > datetime('now')
               ORDER BY created_at DESC LIMIT 1""",
            (user_id,)
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_payments(self, limit: int = 50, status: str = None) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM payments WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit)
            )
        else:
            cur.execute("SELECT * FROM payments ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_undelivered_payments(self) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM payments 
               WHERE status = 'success' AND delivery_status = 'not_delivered'
               ORDER BY paid_at ASC"""
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---------- Промокоды ----------
    def add_promo(self, code: str, discount_percent: int, max_uses: int = -1,
                  min_amount: int = 0, expires_at: str = None,
                  created_by: int = None) -> bool:
        conn = self.get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO promo_codes 
                   (code, discount_percent, max_uses, min_amount, expires_at, created_by) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (code.upper(), discount_percent, max_uses, min_amount, expires_at, created_by)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def get_promo(self, code: str) -> Optional[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (code.upper(),))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def use_promo(self, code: str) -> bool:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = ?",
            (code.upper(),)
        )
        conn.commit()
        conn.close()
        return True

    def validate_promo(self, code: str, amount: int = 0) -> Tuple[bool, str, int]:
        """Валидация промокода. Возвращает (valid, message, discount_percent)"""
        promo = self.get_promo(code)
        if not promo:
            return False, "❌ Промокод не найден или неактивен.", 0
        if promo["max_uses"] != -1 and promo["current_uses"] >= promo["max_uses"]:
            return False, "❌ Промокод уже использован максимальное количество раз.", 0
        if promo["expires_at"] and datetime.fromisoformat(promo["expires_at"]) < datetime.now():
            return False, "❌ Срок действия промокода истёк.", 0
        if amount < promo["min_amount"]:
            return False, f"❌ Минимальная сумма для промокода: {promo['min_amount']} руб.", 0
        return True, f"✅ Промокод применён! Скидка {promo['discount_percent']}%", promo["discount_percent"]

    def get_all_promos(self) -> List[dict]:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def deactivate_promo(self, code: str):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE promo_codes SET is_active = 0 WHERE code = ?", (code.upper(),))
        conn.commit()
        conn.close()

    # ---------- Статистика ----------
    def get_stats(self) -> dict:
        conn = self.get_conn()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM payments")
        total_payments = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'success'")
        success_payments = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
        pending_payments = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'success'")
        total_revenue = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'success' AND date(paid_at) = date('now')"
        )
        today_payments = cur.fetchone()[0]

        cur.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'success' AND date(paid_at) = date('now')"
        )
        today_revenue = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
        )
        today_users = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM payments WHERE delivery_status = 'not_delivered' AND status = 'success'"
        )
        undelivered = cur.fetchone()[0]

        conn.close()
        return {
            "total_users": total_users,
            "total_payments": total_payments,
            "success_payments": success_payments,
            "pending_payments": pending_payments,
            "total_revenue": total_revenue,
            "today_payments": today_payments,
            "today_revenue": today_revenue,
            "today_users": today_users,
            "undelivered": undelivered,
        }

    # ---------- Админ лог ----------
    def admin_log(self, admin_id: int, action: str, details: str = ""):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO admin_log (admin_id, action, details) VALUES (?, ?, ?)",
            (admin_id, action, details)
        )
        conn.commit()
        conn.close()

    # ---------- Рефералы ----------
    def get_referral_count(self, user_id: int) -> int:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        count = cur.fetchone()[0]
        conn.close()
        return count

    def get_referral_stats(self, user_id: int) -> dict:
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        total = cur.fetchone()[0]
        cur.execute(
            """SELECT COUNT(DISTINCT r.referred_id) FROM referrals r
               JOIN payments p ON r.referred_id = p.user_id
               WHERE r.referrer_id = ? AND p.status = 'success'""",
            (user_id,)
        )
        active = cur.fetchone()[0]
        conn.close()
        return {"total": total, "active": active}


# Глобальный экземпляр БД
db = Database()


# ==================== ЮMONEY ИНТЕГРАЦИЯ ====================
class YooMoneyPayment:
    """Работа с ЮMoney платежами"""

    @staticmethod
    def generate_payment_form_url(amount: int, label: str, comment: str = "") -> str:
        """Генерация URL формы быстрой оплаты ЮMoney (P2P)"""
        params = {
            "receiver": YOOMONEY_WALLET,
            "quickpay-form": "button",
            "paymentType": "AC",  # AC - банковская карта, PC - кошелёк
            "sum": str(amount),
            "label": label,
            "comment": comment,
            "successURL": "https://t.me/",
            "targets": comment or "Оплата товара",
        }
        return f"https://yoomoney.ru/quickpay/confirm.xml?{urlencode(params)}"

    @staticmethod
    async def check_payment_by_label(label: str, expected_amount: int) -> Tuple[bool, str]:
        """Проверка оплаты через API истории операций"""
        import aiohttp

        if not YOOMONEY_ACCESS_TOKEN:
            return False, "Токен ЮMoney не настроен"

        url = "https://yoomoney.ru/api/operation-history"
        headers = {
            "Authorization": f"Bearer {YOOMONEY_ACCESS_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "type": "deposition",
            "label": label,
            "records": 10
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, data=data, timeout=15) as resp:
                    if resp.status != 200:
                        return False, f"HTTP {resp.status}"
                    result = await resp.json()

                    operations = result.get("operations", [])
                    for op in operations:
                        if op.get("label") == label and op.get("status") == "success":
                            received = float(op.get("amount", 0))
                            if received >= expected_amount:
                                return True, f"Получено {received} руб."
                            else:
                                return False, f"Сумма не совпадает: получено {received}, ожидалось {expected_amount}"

                    return False, "Платёж не найден в истории"

            except asyncio.TimeoutError:
                return False, "Таймаут при проверке"
            except Exception as e:
                logger.exception("Ошибка проверки платежа")
                return False, f"Ошибка: {e}"

    @staticmethod
    async def get_balance() -> Optional[float]:
        """Получить баланс кошелька"""
        import aiohttp

        url = "https://yoomoney.ru/api/account-info"
        headers = {"Authorization": f"Bearer {YOOMONEY_ACCESS_TOKEN}"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("balance")
            except Exception:
                pass
        return None


# ==================== УТИЛИТЫ ====================
def get_product_info(category_key: str, product_key: str) -> Optional[dict]:
    """Получить информацию о товаре"""
    cat = CATEGORIES.get(category_key)
    if not cat:
        return None
    return cat["products"].get(product_key)


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMIN_IDS


def format_price(price: int) -> str:
    """Форматирование цены"""
    return f"{price:,}".replace(",", " ") + " ₽"


def escape_md(text: str) -> str:
    """Экранирование для MarkdownV2"""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text


# ==================== КЛАВИАТУРЫ ====================
def get_main_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("🛍 Каталог товаров", callback_data="catalog")],
        [
            InlineKeyboardButton("📜 Мои покупки", callback_data="my_orders"),
            InlineKeyboardButton("👤 Профиль", callback_data="profile")
        ],
        [
            InlineKeyboardButton("🎁 Промокод", callback_data="enter_promo"),
            InlineKeyboardButton("👥 Рефералка", callback_data="referral")
        ],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help_info")],
    ]

    if user_id and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])

    return InlineKeyboardMarkup(keyboard)


def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура категорий"""
    keyboard = []
    for key, cat in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(
            f"{cat['emoji']} {cat['name']}",
            callback_data=f"cat_{key}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)


def get_products_keyboard(category_key: str) -> InlineKeyboardMarkup:
    """Клавиатура товаров в категории"""
    cat = CATEGORIES.get(category_key)
    if not cat:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="catalog")]])

    keyboard = []
    for key, product in cat["products"].items():
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} — {format_price(product['price'])}",
            callback_data=f"prod_{category_key}_{key}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад в каталог", callback_data="catalog")])
    return InlineKeyboardMarkup(keyboard)


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ-клавиатура"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton("📋 Последние платежи", callback_data="adm_payments")],
        [InlineKeyboardButton("⏳ Ожидающие оплаты", callback_data="adm_pending")],
        [InlineKeyboardButton("📦 Невыданные товары", callback_data="adm_undelivered")],
        [InlineKeyboardButton("🎟 Управление промокодами", callback_data="adm_promos")],
        [InlineKeyboardButton("✅ Подтвердить оплату (ID)", callback_data="adm_confirm_pay")],
        [InlineKeyboardButton("📦 Выдать товар (ID)", callback_data="adm_deliver")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton("💰 Баланс кошелька", callback_data="adm_balance")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== ОБРАБОТЧИКИ ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    referrer_id = None

    # Проверка реферальной ссылки
    if context.args and context.args[0].startswith("ref"):
        try:
            referrer_id = int(context.args[0][3:])
            if referrer_id == user.id:
                referrer_id = None
        except ValueError:
            pass

    db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        referrer_id=referrer_id
    )

    welcome = (
        f"👋 Добро пожаловать, <b>{html.escape(user.first_name)}</b>!\n\n"
        "🏪 Я — бот-магазин. Здесь вы можете приобрести:\n\n"
        "⭐ <b>Telegram Premium</b> — подписка от 1 до 12 месяцев\n"
        "🌟 <b>Telegram Stars</b> — звёзды для вашего аккаунта\n"
        "🎨 <b>NFT</b> — уникальные коллекционные токены\n\n"
        "💳 Оплата через <b>ЮMoney</b> (карта или кошелёк)\n"
        "🔐 Все покупки безопасны и проверены\n\n"
        "Выберите действие:"
    )

    if referrer_id:
        welcome += f"\n\n🎁 Вы пришли по реферальной ссылке!"

    await update.message.reply_text(
        welcome,
        reply_markup=get_main_menu_keyboard(user.id),
        parse_mode=ParseMode.HTML
    )
    return MAIN_MENU


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок главного меню"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "back_main":
        user = update.effective_user
        text = (
            f"🏠 <b>Главное меню</b>\n\n"
            f"Привет, {html.escape(user.first_name)}!\n"
            f"Выберите действие:"
        )
        await query.edit_message_text(
            text,
            reply_markup=get_main_menu_keyboard(user_id),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    elif data == "catalog":
        await query.edit_message_text(
            "🛍 <b>Каталог товаров</b>\n\nВыберите категорию:",
            reply_markup=get_categories_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return SELECTING_CATEGORY

    elif data == "my_orders":
        payments = db.get_user_payments(user_id, limit=10)
        if not payments:
            text = "📭 У вас пока нет покупок.\n\nНажмите «Каталог» чтобы начать!"
        else:
            text = "📜 <b>Ваши последние покупки:</b>\n\n"
            for p in payments:
                status_emoji = {"success": "✅", "pending": "⏳", "expired": "❌", "cancelled": "🚫"}.get(
                    p["status"], "❓")
                delivery = ""
                if p["status"] == "success":
                    delivery = " 📦" if p["delivery_status"] == "delivered" else " ⏳ожидает выдачи"
                product = get_product_info(p["category"], p["product_key"])
                product_name = product["name"] if product else p["product_key"]
                text += (
                    f"{status_emoji} <b>#{p['id']}</b> {product_name}\n"
                    f"   💰 {format_price(p['amount'])} | {p['created_at'][:16]}{delivery}\n\n"
                )

        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    elif data == "profile":
        user_data = db.get_user(user_id)
        ref_stats = db.get_referral_stats(user_id)
        payments = db.get_user_payments(user_id, limit=1000)
        success_count = sum(1 for p in payments if p["status"] == "success")

        text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Имя: {html.escape(user_data.get('first_name', 'Нет'))}\n"
            f"📱 Username: @{user_data.get('username', 'нет')}\n\n"
            f"🛍 Покупок: {success_count}\n"
            f"💰 Потрачено: {format_price(user_data.get('total_spent', 0))}\n"
            f"👥 Рефералов: {ref_stats['total']} (активных: {ref_stats['active']})\n"
            f"📅 Регистрация: {user_data.get('created_at', '')[:10]}"
        )

        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    elif data == "referral":
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
        ref_stats = db.get_referral_stats(user_id)

        text = (
            f"👥 <b>Реферальная программа</b>\n\n"
            f"Приглашайте друзей и получайте бонусы!\n\n"
            f"🔗 Ваша ссылка:\n<code>{ref_link}</code>\n\n"
            f"👥 Приглашено: {ref_stats['total']}\n"
            f"✅ Сделали покупку: {ref_stats['active']}\n\n"
            f"📌 Отправьте ссылку друзьям!"
        )

        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    elif data == "enter_promo":
        context.user_data["awaiting"] = "promo_code"
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="back_main")]]
        await query.edit_message_text(
            "🎁 <b>Введите промокод:</b>\n\nОтправьте промокод сообщением.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return ENTERING_PROMO

    elif data == "help_info":
        text = (
            "ℹ️ <b>Помощь</b>\n\n"
            "🛍 <b>Как купить:</b>\n"
            "1. Выберите товар в каталоге\n"
            "2. Подтвердите покупку\n"
            "3. Оплатите по ссылке (карта или ЮMoney)\n"
            "4. Нажмите «Проверить оплату»\n"
            "5. Получите товар!\n\n"
            "⏱ Платёж действителен 24 часа\n"
            "🔄 Автопроверка каждые 30 секунд\n\n"
            "📞 <b>Поддержка:</b> @your_support\n\n"
            "<b>Команды:</b>\n"
            "/start — главное меню\n"
            "/catalog — каталог\n"
            "/history — мои покупки\n"
            "/help — помощь\n"
            "/check — проверить активный платёж"
        )

        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    elif data == "admin_panel":
        if not is_admin(user_id):
            await query.edit_message_text("⛔ Доступ запрещён.")
            return MAIN_MENU
        await query.edit_message_text(
            "👑 <b>Админ-панель</b>\n\nВыберите действие:",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return ADMIN_MENU


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор категории"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        return await main_menu_callback(update, context)

    if not data.startswith("cat_"):
        return SELECTING_CATEGORY

    category_key = data[4:]
    cat = CATEGORIES.get(category_key)
    if not cat:
        await query.edit_message_text("❌ Категория не найдена.")
        return SELECTING_CATEGORY

    context.user_data["current_category"] = category_key

    text = (
        f"{cat['emoji']} <b>{cat['name']}</b>\n\n"
        f"Выберите товар:"
    )

    await query.edit_message_text(
        text,
        reply_markup=get_products_keyboard(category_key),
        parse_mode=ParseMode.HTML
    )
    return SELECTING_PRODUCT


async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор конкретного товара"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "catalog":
        await query.edit_message_text(
            "🛍 <b>Каталог товаров</b>\n\nВыберите категорию:",
            reply_markup=get_categories_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return SELECTING_CATEGORY

    if not data.startswith("prod_"):
        return SELECTING_PRODUCT

    parts = data.split("_", 2)
    if len(parts) < 3:
        return SELECTING_PRODUCT

    category_key = parts[1]
    product_key = parts[2]

    product = get_product_info(category_key, product_key)
    if not product:
        await query.edit_message_text("❌ Товар не найден.")
        return SELECTING_PRODUCT

    context.user_data["selected_category"] = category_key
    context.user_data["selected_product"] = product_key
    context.user_data["promo_discount"] = 0
    context.user_data["promo_code"] = None

    price = product["price"]
    text = (
        f"🛍 <b>{product['name']}</b>\n\n"
        f"📝 {product['description']}\n\n"
        f"💰 Стоимость: <b>{format_price(price)}</b>\n\n"
        f"Выберите действие:"
    )

    keyboard = [
        [InlineKeyboardButton("💳 Купить", callback_data="buy_confirm")],
        [InlineKeyboardButton("🎁 Применить промокод", callback_data="apply_promo")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"cat_{category_key}")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return PRODUCT_DETAIL


async def product_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали товара и действия"""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Назад в категорию
    if data.startswith("cat_"):
        return await category_callback(update, context)

    if data == "apply_promo":
        context.user_data["awaiting"] = "product_promo"
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="cancel_promo_input")]]
        await query.edit_message_text(
            "🎁 <b>Введите промокод:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return ENTERING_PROMO

    if data == "buy_confirm":
        category_key = context.user_data.get("selected_category")
        product_key = context.user_data.get("selected_product")
        product = get_product_info(category_key, product_key)

        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return MAIN_MENU

        # Проверяем нет ли активного платежа
        active = db.get_user_active_payment(update.effective_user.id)
        if active:
            keyboard = [
                [InlineKeyboardButton("✅ Проверить оплату", callback_data="check_active_payment")],
                [InlineKeyboardButton("❌ Отменить старый платёж", callback_data="cancel_active_payment")],
            ]
            await query.edit_message_text(
                "⚠️ У вас есть незавершённый платёж!\n\n"
                f"Платёж #{active['id']} на сумму {format_price(active['amount'])}\n\n"
                "Сначала завершите или отмените его.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
            return WAITING_PAYMENT

        price = product["price"]
        discount = context.user_data.get("promo_discount", 0)
        promo_code = context.user_data.get("promo_code")
        original_price = price

        if discount > 0:
            price = max(1, int(price * (100 - discount) / 100))

        discount_text = ""
        if discount > 0:
            discount_text = f"\n🎁 Промокод: <code>{promo_code}</code> (−{discount}%)\n💰 Было: <s>{format_price(original_price)}</s>"

        text = (
            f"✅ <b>Подтверждение покупки</b>\n\n"
            f"📦 Товар: <b>{product['name']}</b>\n"
            f"💰 К оплате: <b>{format_price(price)}</b>"
            f"{discount_text}\n\n"
            f"💳 Оплата через ЮMoney (карта/кошелёк)\n\n"
            f"Подтвердите покупку:"
        )

        context.user_data["final_price"] = price
        context.user_data["original_price"] = original_price

        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить и оплатить", callback_data="create_payment")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"prod_{category_key}_{product_key}")],
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return CONFIRMING


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и создание платежа"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("prod_"):
        return await product_callback(update, context)

    if data != "create_payment":
        return CONFIRMING

    user_id = update.effective_user.id
    category_key = context.user_data.get("selected_category")
    product_key = context.user_data.get("selected_product")
    product = get_product_info(category_key, product_key)

    if not product:
        await query.edit_message_text("❌ Ошибка: товар не найден.")
        return MAIN_MENU

    price = context.user_data.get("final_price", product["price"])
    original_price = context.user_data.get("original_price", price)
    promo_code = context.user_data.get("promo_code")
    discount = context.user_data.get("promo_discount", 0)

    # Генерируем уникальные идентификаторы
    payment_id = str(uuid.uuid4())
    label = f"p_{user_id}_{int(time.time())}_{payment_id[:8]}"

    # Создаём ссылку на оплату
    comment = f"Покупка: {product['name']} (ID: {label[:20]})"
    payment_url = YooMoneyPayment.generate_payment_form_url(price, label, comment)

    # Сохраняем в БД
    row_id = db.add_payment(
        user_id=user_id,
        product_key=product_key,
        category=category_key,
        payment_id=payment_id,
        payment_label=label,
        amount=price,
        original_amount=original_price,
        promo_code=promo_code,
        discount=discount
    )

    # Используем промокод
    if promo_code:
        db.use_promo(promo_code)

    context.user_data["active_payment_id"] = payment_id
    context.user_data["active_label"] = label

    text = (
        f"💳 <b>Оплата #{row_id}</b>\n\n"
        f"📦 Товар: {product['name']}\n"
        f"💰 Сумма: <b>{format_price(price)}</b>\n\n"
        f"🔗 <b>Нажмите кнопку ниже для оплаты</b>\n\n"
        f"⏱ Платёж действителен 24 часа\n"
        f"🔄 Автопроверка каждые {CHECK_INTERVAL} сек.\n\n"
        f"После оплаты нажмите «Проверить оплату»"
    )

    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data="check_my_payment")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

    # Уведомляем админа
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🆕 Новый платёж #{row_id}\n"
                f"👤 Пользователь: {user_id} (@{update.effective_user.username})\n"
                f"📦 Товар: {product['name']}\n"
                f"💰 Сумма: {format_price(price)}\n"
                f"🏷 Label: <code>{label}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    return WAITING_PAYMENT


async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок оплаты"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "cancel_payment":
        payment_id = context.user_data.get("active_payment_id")
        if payment_id:
            db.update_payment_status(payment_id, "cancelled")
        context.user_data.pop("active_payment_id", None)
        context.user_data.pop("active_label", None)

        await query.edit_message_text(
            "❌ Платёж отменён.\n\nВернитесь в /start для новой покупки.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]
            ]),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    if data == "cancel_active_payment":
        active = db.get_user_active_payment(user_id)
        if active:
            db.update_payment_status(active["payment_id"], "cancelled")
        await query.edit_message_text(
            "✅ Старый платёж отменён. Можете создать новый.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]
            ])
        )
        return MAIN_MENU

    if data in ("check_my_payment", "check_active_payment"):
        payment_id = context.user_data.get("active_payment_id")

        if not payment_id:
            # Ищем активный платёж
            active = db.get_user_active_payment(user_id)
            if active:
                payment_id = active["payment_id"]
                context.user_data["active_payment_id"] = payment_id
                context.user_data["active_label"] = active["payment_label"]
            else:
                await query.edit_message_text(
                    "❌ Активный платёж не найден.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]
                    ])
                )
                return MAIN_MENU

        payment = db.get_payment(payment_id)
        if not payment:
            await query.edit_message_text("❌ Платёж не найден в базе.")
            return MAIN_MENU

        if payment["status"] == "success":
            await handle_successful_payment(query, context, payment)
            return MAIN_MENU

        if payment["status"] in ("cancelled", "expired"):
            await query.edit_message_text(
                f"❌ Платёж {payment['status']}. Создайте новый.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]
                ])
            )
            return MAIN_MENU

        # Проверяем через API
        label = payment["payment_label"]
        success, msg = await YooMoneyPayment.check_payment_by_label(label, payment["amount"])

        if success:
            db.update_payment_status(payment_id, "success")
            db.update_user_spent(user_id, payment["amount"])
            payment["status"] = "success"
            await handle_successful_payment(query, context, payment)

            # Уведомляем админа
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"💰 Оплата подтверждена!\n"
                        f"Платёж #{payment['id']} | {format_price(payment['amount'])}\n"
                        f"👤 {user_id}\n"
                        f"📦 Требуется выдача товара!",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

            return MAIN_MENU
        else:
            # Ещё не оплачено
            product = get_product_info(payment["category"], payment["product_key"])
            product_name = product["name"] if product else "Товар"
            payment_url = YooMoneyPayment.generate_payment_form_url(
                payment["amount"], label, f"Покупка: {product_name}"
            )

            text = (
                f"⏳ <b>Оплата не найдена</b>\n\n"
                f"📦 Товар: {product_name}\n"
                f"💰 Сумма: {format_price(payment['amount'])}\n\n"
                f"ℹ️ {msg}\n\n"
                f"Убедитесь что вы оплатили и попробуйте через минуту.\n"
                f"Автопроверка работает каждые {CHECK_INTERVAL} сек."
            )

            keyboard = [
                [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
                [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_my_payment")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")],
            ]

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
            return WAITING_PAYMENT


async def handle_successful_payment(query, context, payment: dict):
    """Обработка успешного платежа"""
    product = get_product_info(payment["category"], payment["product_key"])
    product_name = product["name"] if product else payment["product_key"]

    if product and product.get("delivery_type") == "auto":
        # Автоматическая выдача (если настроена)
        success, delivery_msg = await auto_deliver(payment)
        if success:
            db.mark_delivered(payment["payment_id"], delivery_msg)
            text = (
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"📦 {product_name}\n"
                f"💰 {format_price(payment['amount'])}\n\n"
                f"🎉 {delivery_msg}\n\n"
                f"Спасибо за покупку!"
            )
        else:
            text = (
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"📦 {product_name}\n"
                f"💰 {format_price(payment['amount'])}\n\n"
                f"⏳ Товар будет выдан администратором в ближайшее время.\n"
                f"Мы уведомим вас!"
            )
    else:
        # Ручная выдача
        text = (
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"📦 {product_name}\n"
            f"💰 {format_price(payment['amount'])}\n\n"
            f"⏳ Товар будет выдан администратором в ближайшее время.\n"
            f"Вы получите уведомление. Обычно это занимает до 30 минут."
        )

    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


async def auto_deliver(payment: dict) -> Tuple[bool, str]:
    """Автоматическая выдача товара (заглушка)"""
    # Здесь можно добавить реальную логику автовыдачи
    logger.info(f"Автовыдача для платежа {payment['payment_id']}: пока не реализовано")
    return False, "Автовыдача не настроена"


# ==================== ВВОД ПРОМОКОДА ====================
async def promo_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода промокода"""
    awaiting = context.user_data.get("awaiting")

    if awaiting == "promo_code":
        code = update.message.text.strip().upper()
        valid, msg, discount = db.validate_promo(code)

        if valid:
            text = f"🎁 {msg}\n\nИспользуйте его при покупке в каталоге!"
        else:
            text = msg

        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]]
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        context.user_data["awaiting"] = None
        return MAIN_MENU

    elif awaiting == "product_promo":
        code = update.message.text.strip().upper()
        category_key = context.user_data.get("selected_category")
        product_key = context.user_data.get("selected_product")
        product = get_product_info(category_key, product_key)

        if not product:
            await update.message.reply_text("❌ Товар не найден.")
            return MAIN_MENU

        valid, msg, discount = db.validate_promo(code, product["price"])

        if valid:
            context.user_data["promo_discount"] = discount
            context.user_data["promo_code"] = code
            new_price = max(1, int(product["price"] * (100 - discount) / 100))

            text = (
                f"🎁 {msg}\n\n"
                f"📦 {product['name']}\n"
                f"💰 Было: <s>{format_price(product['price'])}</s>\n"
                f"💰 Стало: <b>{format_price(new_price)}</b>\n\n"
                f"Нажмите «Купить» для продолжения."
            )

            keyboard = [
                [InlineKeyboardButton("💳 Купить", callback_data="buy_confirm")],
                [InlineKeyboardButton("🔙 Назад", callback_data=f"cat_{category_key}")],
            ]
        else:
            text = f"{msg}\n\nПопробуйте другой промокод или продолжите без него."
            keyboard = [
                [InlineKeyboardButton("💳 Купить без промокода", callback_data="buy_confirm")],
                [InlineKeyboardButton("🔙 Назад", callback_data=f"cat_{category_key}")],
            ]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        context.user_data["awaiting"] = None
        return PRODUCT_DETAIL


# ==================== АДМИН-ПАНЕЛЬ ====================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка админ-кнопок"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return MAIN_MENU

    data = query.data

    if data == "back_admin":
        await query.edit_message_text(
            "👑 <b>Админ-панель</b>",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return ADMIN_MENU

    if data == "adm_stats":
        stats = db.get_stats()
        balance = await YooMoneyPayment.get_balance()
        balance_text = f"{balance:.2f} ₽" if balance is not None else "Н/Д"

        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {stats['total_users']} (сегодня: +{stats['today_users']})\n\n"
            f"💳 <b>Платежи:</b>\n"
            f"  Всего: {stats['total_payments']}\n"
            f"  ✅ Успешных: {stats['success_payments']}\n"
            f"  ⏳ Ожидающих: {stats['pending_payments']}\n"
            f"  📦 Невыданных: {stats['undelivered']}\n\n"
            f"💰 <b>Доход:</b>\n"
            f"  Всего: {format_price(stats['total_revenue'])}\n"
            f"  Сегодня: {format_price(stats['today_revenue'])} ({stats['today_payments']} платежей)\n\n"
            f"💼 Баланс кошелька: {balance_text}"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return ADMIN_MENU

    elif data == "adm_payments":
        payments = db.get_all_payments(limit=15)
        if not payments:
            text = "📭 Платежей нет."
        else:
            text = "📋 <b>Последние платежи:</b>\n\n"
            for p in payments:
                st = {"success": "✅", "pending": "⏳", "expired": "❌",
                      "cancelled": "🚫"}.get(p["status"], "❓")
                dlv = "📦" if p["delivery_status"] == "delivered" else ""
                text += (
                    f"{st} <b>#{p['id']}</b> | {p['user_id']} | "
                    f"{p['product_key']} | {format_price(p['amount'])} | "
                    f"{p['created_at'][:16]} {dlv}\n"
                )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return ADMIN_MENU

    elif data == "adm_pending":
        payments = db.get_all_payments(limit=20, status="pending")
        if not payments:
            text = "✅ Нет ожидающих платежей."
        else:
            text = "⏳ <b>Ожидающие платежи:</b>\n\n"
            for p in payments:
                text += (
                    f"<b>#{p['id']}</b> | 👤 {p['user_id']} | "
                    f"{p['product_key']} | {format_price(p['amount'])}\n"
                    f"  🏷 <code>{p['payment_label']}</code>\n"
                    f"  📅 {p['created_at'][:16]}\n\n"
                )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return ADMIN_MENU

    elif data == "adm_undelivered":
        payments = db.get_undelivered_payments()
        if not payments:
            text = "✅ Все товары выданы!"
        else:
            text = "📦 <b>Невыданные товары:</b>\n\n"
            for p in payments:
                user = db.get_user(p["user_id"])
                username = f"@{user['username']}" if user and user.get('username') else str(p['user_id'])
                product = get_product_info(p["category"], p["product_key"])
                product_name = product["name"] if product else p["product_key"]

                text += (
                    f"<b>#{p['id']}</b> | {username}\n"
                    f"  📦 {product_name} | {format_price(p['amount'])}\n"
                    f"  💳 Оплачен: {p.get('paid_at', 'N/A')}\n\n"
                )

            text += "\nИспользуйте «Выдать товар» для отметки выдачи."

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return ADMIN_MENU

    elif data == "adm_confirm_pay":
        context.user_data["admin_awaiting"] = "confirm_payment_id"
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="back_admin")]]
        await query.edit_message_text(
            "✅ <b>Ручное подтверждение оплаты</b>\n\n"
            "Введите ID платежа (число #) для подтверждения:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return ADMIN_MANUAL_ID

    elif data == "adm_deliver":
        context.user_data["admin_awaiting"] = "deliver_payment_id"
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="back_admin")]]
        await query.edit_message_text(
            "📦 <b>Выдача товара</b>\n\n"
            "Введите ID платежа (число #) для отметки выдачи:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return ADMIN_MANUAL_ID

    elif data == "adm_promos":
        promos = db.get_all_promos()
        if not promos:
            text = "🎟 Промокодов нет.\n\nСоздайте новый командой:"
        else:
            text = "🎟 <b>Промокоды:</b>\n\n"
            for p in promos:
                active = "✅" if p["is_active"] else "❌"
                uses = f"{p['current_uses']}/{p['max_uses']}" if p["max_uses"] != -1 else f"{p['current_uses']}/∞"
                text += (
                    f"{active} <code>{p['code']}</code> — {p['discount_percent']}% "
                    f"({uses})\n"
                )

        text += "\n\nДля создания промокода введите в формате:\n<code>КОД СКИДКА% МАКС_ИСПОЛЬЗОВАНИЙ</code>\nНапример: <code>SALE20 20 100</code>"

        context.user_data["admin_awaiting"] = "add_promo"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return ADMIN_ADD_PROMO

    elif data == "adm_broadcast":
        context.user_data["admin_awaiting"] = "broadcast_text"
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="back_admin")]]
        await query.edit_message_text(
            "📢 <b>Рассылка</b>\n\n"
            "Введите текст сообщения для рассылки всем пользователям:\n\n"
            "⚠️ Поддерживается HTML-разметка.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return ADMIN_BROADCAST

    elif data == "adm_balance":
        balance = await YooMoneyPayment.get_balance()
        if balance is not None:
            text = f"💰 <b>Баланс кошелька ЮMoney:</b>\n\n{balance:.2f} ₽"
        else:
            text = "❌ Не удалось получить баланс. Проверьте токен."

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_admin")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.HTML)
        return ADMIN_MENU


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений от админа"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    awaiting = context.user_data.get("admin_awaiting")

    if awaiting == "confirm_payment_id":
        try:
            row_id = int(update.message.text.strip().replace("#", ""))
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID платежа.")
            return ADMIN_MANUAL_ID

        payment = db.get_payment_by_row_id(row_id)
        if not payment:
            await update.message.reply_text("❌ Платёж не найден.")
            return ADMIN_MANUAL_ID

        if payment["status"] == "success":
            await update.message.reply_text("✅ Этот платёж уже подтверждён.")
            return ADMIN_MANUAL_ID

        db.update_payment_status(payment["payment_id"], "success")
        db.update_user_spent(payment["user_id"], payment["amount"])
        db.admin_log(user_id, "confirm_payment", f"Платёж #{row_id}")

        # Уведомляем пользователя
        try:
            product = get_product_info(payment["category"], payment["product_key"])
            product_name = product["name"] if product else payment["product_key"]
            await context.bot.send_message(
                payment["user_id"],
                f"✅ <b>Ваш платёж #{row_id} подтверждён!</b>\n\n"
                f"📦 {product_name}\n"
                f"💰 {format_price(payment['amount'])}\n\n"
                f"Товар будет выдан в ближайшее время.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ Платёж #{row_id} подтверждён.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="back_admin")]
            ])
        )
        context.user_data["admin_awaiting"] = None
        return ADMIN_MENU

    elif awaiting == "deliver_payment_id":
        try:
            row_id = int(update.message.text.strip().replace("#", ""))
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID.")
            return ADMIN_MANUAL_ID

        payment = db.get_payment_by_row_id(row_id)
        if not payment:
            await update.message.reply_text("❌ Платёж не найден.")
            return ADMIN_MANUAL_ID

        if payment["status"] != "success":
            await update.message.reply_text("⚠️ Платёж ещё не оплачен!")
            return ADMIN_MANUAL_ID

        if payment["delivery_status"] == "delivered":
            await update.message.reply_text("✅ Товар уже выдан.")
            return ADMIN_MANUAL_ID

        db.mark_delivered(payment["payment_id"], f"Ручная выдача админом {user_id}")
        db.admin_log(user_id, "deliver", f"Платёж #{row_id}")

        # Уведомляем покупателя
        try:
            product = get_product_info(payment["category"], payment["product_key"])
            product_name = product["name"] if product else payment["product_key"]
            await context.bot.send_message(
                payment["user_id"],
                f"🎉 <b>Ваш товар выдан!</b>\n\n"
                f"📦 {product_name}\n\n"
                f"Спасибо за покупку! Если есть вопросы — обращайтесь.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ Товар по платежу #{row_id} отмечен как выданный.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="back_admin")]
            ])
        )
        context.user_data["admin_awaiting"] = None
        return ADMIN_MENU

    elif awaiting == "add_promo":
        parts = update.message.text.strip().split()
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Формат: <code>КОД СКИДКА% [МАКС_ИСПОЛЬЗОВАНИЙ]</code>\n"
                "Пример: <code>SALE20 20 100</code>",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_ADD_PROMO

        code = parts[0].upper()
        try:
            discount = int(parts[1].replace("%", ""))
        except ValueError:
            await update.message.reply_text("❌ Скидка должна быть числом.")
            return ADMIN_ADD_PROMO

        max_uses = -1
        if len(parts) >= 3:
            try:
                max_uses = int(parts[2])
            except ValueError:
                pass

        if discount < 1 or discount > 99:
            await update.message.reply_text("❌ Скидка должна быть от 1 до 99%.")
            return ADMIN_ADD_PROMO

        success = db.add_promo(code, discount, max_uses, created_by=user_id)
        if success:
            db.admin_log(user_id, "add_promo", f"{code} {discount}% max:{max_uses}")
            await update.message.reply_text(
                f"✅ Промокод создан!\n\n"
                f"Код: <code>{code}</code>\n"
                f"Скидка: {discount}%\n"
                f"Использований: {'∞' if max_uses == -1 else max_uses}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Админ-панель", callback_data="back_admin")]
                ])
            )
        else:
            await update.message.reply_text("❌ Промокод с таким кодом уже существует.")

        context.user_data["admin_awaiting"] = None
        return ADMIN_MENU

    elif awaiting == "broadcast_text":
        broadcast_text = update.message.text.strip()
        users = db.get_all_users()

        sent = 0
        failed = 0
        for u in users:
            try:
                await context.bot.send_message(
                    u["user_id"],
                    f"📢 <b>Рассылка:</b>\n\n{broadcast_text}",
                    parse_mode=ParseMode.HTML
                )
                sent += 1
                await asyncio.sleep(0.05)  # Анти-флуд
            except Exception:
                failed += 1

        db.admin_log(user_id, "broadcast", f"Sent: {sent}, Failed: {failed}")
        await update.message.reply_text(
            f"📢 Рассылка завершена!\n\n"
            f"✅ Отправлено: {sent}\n"
            f"❌ Ошибок: {failed}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Админ-панель", callback_data="back_admin")]
            ])
        )
        context.user_data["admin_awaiting"] = None
        return ADMIN_MENU


# ==================== КОМАНДЫ ====================
async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /catalog"""
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        "🛍 <b>Каталог товаров</b>\n\nВыберите категорию:",
        reply_markup=get_categories_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return SELECTING_CATEGORY


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /history"""
    user_id = update.effective_user.id
    payments = db.get_user_payments(user_id, limit=10)

    if not payments:
        await update.message.reply_text("📭 У вас пока нет покупок.")
        return

    text = "📜 <b>Ваши покупки:</b>\n\n"
    for p in payments:
        status_emoji = {"success": "✅", "pending": "⏳", "expired": "❌",
                        "cancelled": "🚫"}.get(p["status"], "❓")
        product = get_product_info(p["category"], p["product_key"])
        product_name = product["name"] if product else p["product_key"]
        text += f"{status_emoji} #{p['id']} {product_name} — {format_price(p['amount'])} ({p['created_at'][:16]})\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /check — проверить активный платёж"""
    user_id = update.effective_user.id
    active = db.get_user_active_payment(user_id)

    if not active:
        await update.message.reply_text("✅ У вас нет активных платежей.")
        return

    label = active["payment_label"]
    success, msg = await YooMoneyPayment.check_payment_by_label(label, active["amount"])

    if success:
        db.update_payment_status(active["payment_id"], "success")
        db.update_user_spent(user_id, active["amount"])

        product = get_product_info(active["category"], active["product_key"])
        product_name = product["name"] if product else active["product_key"]

        await update.message.reply_text(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"📦 {product_name}\n"
            f"💰 {format_price(active['amount'])}\n\n"
            f"Товар будет выдан в ближайшее время!",
            parse_mode=ParseMode.HTML
        )

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"💰 Оплата подтверждена (через /check)!\n"
                    f"#{active['id']} | {user_id} | {product_name} | {format_price(active['amount'])}",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
    else:
        await update.message.reply_text(
            f"⏳ Платёж #{active['id']} ещё не оплачен.\n\n"
            f"ℹ️ {msg}\n\n"
            f"Попробуйте позже или оплатите по ссылке из чата."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    text = (
        "ℹ️ <b>Помощь</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/catalog — каталог товаров\n"
        "/history — история покупок\n"
        "/check — проверить оплату\n"
        "/help — справка\n\n"
        "<b>Как купить:</b>\n"
        "1. Откройте каталог\n"
        "2. Выберите товар\n"
        "3. Подтвердите покупку\n"
        "4. Оплатите по ссылке\n"
        "5. Дождитесь выдачи товара\n\n"
        "📞 Поддержка: @your_support"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    await update.message.reply_text(
        "👑 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ADMIN_MENU


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================
async def background_payment_checker(application: Application):
    """Фоновая проверка платежей"""
    logger.info("Фоновая проверка платежей запущена")

    while True:
        try:
            # Устаревшие платежи
            expired_count = db.expire_payments()
            if expired_count > 0:
                logger.info(f"Истекло {expired_count} платежей")

            # Проверка ожидающих
            pending = db.get_pending_payments()
            for p in pending:
                try:
                    success, msg = await YooMoneyPayment.check_payment_by_label(
                        p["payment_label"], p["amount"]
                    )

                    if success:
                        db.update_payment_status(p["payment_id"], "success")
                        db.update_user_spent(p["user_id"], p["amount"])

                        product = get_product_info(p["category"], p["product_key"])
                        product_name = product["name"] if product else p["product_key"]

                        logger.info(f"Платёж #{p['id']} подтверждён автоматически")

                        # Уведомляем пользователя
                        try:
                            await application.bot.send_message(
                                p["user_id"],
                                f"✅ <b>Платёж #{p['id']} подтверждён!</b>\n\n"
                                f"📦 {product_name}\n"
                                f"💰 {format_price(p['amount'])}\n\n"
                                f"⏳ Товар будет выдан в ближайшее время.",
                                parse_mode=ParseMode.HTML
                            )
                        except Exception:
                            pass

                        # Уведомляем админа
                        for admin_id in ADMIN_IDS:
                            try:
                                await application.bot.send_message(
                                    admin_id,
                                    f"💰 <b>Авто-подтверждение платежа #{p['id']}</b>\n"
                                    f"👤 {p['user_id']} | {product_name} | {format_price(p['amount'])}\n"
                                    f"📦 Требуется выдача!",
                                    parse_mode=ParseMode.HTML
                                )
                            except Exception:
                                pass

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Ошибка проверки платежа {p['id']}: {e}")

        except Exception as e:
            logger.exception(f"Ошибка в фоновой проверке: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def post_init(application: Application):
    """Действия после инициализации бота"""
    # Устанавливаем команды бота
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("catalog", "Каталог товаров"),
        BotCommand("history", "История покупок"),
        BotCommand("check", "Проверить оплату"),
        BotCommand("help", "Помощь"),
    ]
    await application.bot.set_my_commands(commands)

    # Запускаем фоновую проверку
    asyncio.create_task(background_payment_checker(application))

    logger.info("🚀 Бот запущен и готов к работе!")

    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await application.bot.send_message(admin_id, "🟢 Бот запущен и работает!")
        except Exception:
            pass


# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    """Запуск бота"""
    # Инициализация БД
    db.init_db()

    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # ConversationHandler — основной
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("catalog", catalog_command),
        ],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_callback,
                                     pattern="^(back_main|catalog|my_orders|profile|referral|enter_promo|help_info|admin_panel)$"),
            ],
            SELECTING_CATEGORY: [
                CallbackQueryHandler(category_callback, pattern="^(cat_|back_main)"),
            ],
            SELECTING_PRODUCT: [
                CallbackQueryHandler(product_callback, pattern="^(prod_|catalog)"),
            ],
            PRODUCT_DETAIL: [
                CallbackQueryHandler(product_detail_callback,
                                     pattern="^(buy_confirm|apply_promo|cat_)"),
            ],
            ENTERING_PROMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, promo_text_handler),
                CallbackQueryHandler(main_menu_callback, pattern="^(back_main|cancel_promo_input)$"),
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirm_callback, pattern="^(create_payment|prod_)"),
            ],
            WAITING_PAYMENT: [
                CallbackQueryHandler(payment_callback,
                                     pattern="^(check_my_payment|check_active_payment|cancel_payment|cancel_active_payment|back_main)$"),
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback,
                                     pattern="^(adm_|back_admin|back_main)"),
            ],
            ADMIN_MANUAL_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_admin$"),
            ],
            ADMIN_ADD_PROMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_admin$"),
            ],
            ADMIN_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler),
                CallbackQueryHandler(admin_callback, pattern="^back_admin$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ Отменено. /start")),
        ],
        per_user=True,
        per_chat=True,
    )

    application.add_handler(conv_handler)

    # Дополнительные команды (вне conversation)
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))

    # Запуск
    logger.info("Запуск бота...")
    application.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
