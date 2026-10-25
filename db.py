"""
Модуль для работы с PostgreSQL (Supabase) через asyncpg.
Все таблицы создаются автоматически при первом запуске.
"""
import asyncpg
import asyncio
import os
from datetime import datetime

# Connection string берётся из переменной окружения DATABASE_URL
# На сервере (Render) задаётся через Environment Variables
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:Alishka2010@@db.oaisjipniprzcyugxndj.supabase.co:5432/postgres"
)

_pool: asyncpg.Pool = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:  # double-check
                _pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=25,
                                                  command_timeout=15)
    return _pool


async def init_db():
    """Создаёт все таблицы если их нет."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                subscribe TIMESTAMP DEFAULT '1999-01-01 20:00:00',
                premium INT DEFAULT 0,
                verified INT DEFAULT 0,
                referrer_id BIGINT DEFAULT NULL,
                referral_count INT DEFAULT 0,
                free_reports INT DEFAULT 0,
                wheel_last_spin TIMESTAMP DEFAULT '1999-01-01 00:00:00'
            )
        """)
        # Добавляем новые колонки если их нет (для существующих БД)
        for col, definition in [
            ("referrer_id", "BIGINT DEFAULT NULL"),
            ("referral_count", "INT DEFAULT 0"),
            ("free_reports", "INT DEFAULT 0"),
            ("wheel_last_spin", "TIMESTAMP DEFAULT '1999-01-01 00:00:00'"),
            ("wheel_prize", "TEXT DEFAULT ''"),
            ("username", "TEXT DEFAULT ''"),
            ("manual_confirmed", "INT DEFAULT 0"),
            ("lang", "TEXT DEFAULT 'ru'"),
            ("sub_expiry_notified", "BOOLEAN DEFAULT FALSE"),
            ("is_hidden", "BOOLEAN DEFAULT TRUE"),
            ("chatbot_enabled", "BOOLEAN DEFAULT FALSE"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
            except Exception:
                pass
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS business_connections (
                user_id       BIGINT PRIMARY KEY,
                connection_id TEXT NOT NULL,
                connected_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chatbot_mutes (
                user_id  BIGINT,
                chat_id  BIGINT,
                until    TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chatbot_msg_cache (
                user_id    BIGINT,
                chat_id    BIGINT,
                message_id INT,
                from_id    BIGINT,
                text       TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, chat_id, message_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS promocode (
                code TEXT UNIQUE,
                days INT,
                activations INT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id BIGINT PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked (
                user_id BIGINT PRIMARY KEY
            )
        """)
    await init_mirrors_table()
    await _init_paid_invoices_table()
    await init_target_whitelist_table()
    # Создаём таблицу использований промокодов
    pool_db = await get_pool()
    async with pool_db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS promo_uses (
                code TEXT NOT NULL,
                user_id BIGINT NOT NULL,
                PRIMARY KEY (code, user_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS probiv_usage (
                user_id BIGINT PRIMARY KEY,
                last_request_at TIMESTAMPTZ DEFAULT '1999-01-01 00:00:00+00',
                hour_count INT DEFAULT 0,
                hour_window_start TIMESTAMPTZ DEFAULT '1999-01-01 00:00:00+00'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS manual_confirmed_methods (
                user_id BIGINT NOT NULL,
                method  TEXT    NOT NULL,
                PRIMARY KEY (user_id, method)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                admin_id BIGINT NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS log_entries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tg_market_orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                session_file TEXT,
                phone TEXT,
                invoice_id TEXT,
                payment_method TEXT DEFAULT 'sbp',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Добавляем last_bot_token если нет (для существующих БД)
        try:
            await conn.execute("ALTER TABLE mirror_assignments ADD COLUMN IF NOT EXISTS last_bot_token TEXT DEFAULT '__main__'")
        except Exception:
            pass
        # Фикс NULL значений для старых пользователей
        await conn.execute("UPDATE users SET premium = 0 WHERE premium IS NULL")
        await conn.execute("UPDATE users SET free_reports = 0 WHERE free_reports IS NULL")
        await conn.execute("UPDATE users SET referral_count = 0 WHERE referral_count IS NULL")
        await conn.execute("UPDATE users SET verified = 0 WHERE verified IS NULL")
        await conn.execute("UPDATE users SET mirror_bonus_given = 0 WHERE mirror_bonus_given IS NULL")


# ─── Users ────────────────────────────────────────────────────────────────────

async def user_exists(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM users WHERE user_id = $1", user_id)
        return row is not None


async def add_user(user_id: int, username: str = ''):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Сначала вставляем без username (совместимость со старой схемой)
        await conn.execute(
            "INSERT INTO users (user_id, subscribe, premium, verified) VALUES ($1, $2, 0, 0) ON CONFLICT DO NOTHING",
            user_id, datetime(1999, 1, 1, 20, 0, 0)
        )
        # Обновляем username отдельно (колонка может не существовать на старых БД)
        if username:
            try:
                await conn.execute(
                    "UPDATE users SET username = $1 WHERE user_id = $2",
                    username, user_id
                )
            except Exception:
                pass


async def get_user(user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not row:
            return None
        d = dict(row)
        # Заменяем None на дефолтные значения для колонок добавленных позже
        d['premium'] = d.get('premium') or 0
        d['free_reports'] = d.get('free_reports') or 0
        d['referral_count'] = d.get('referral_count') or 0
        d['verified'] = d.get('verified') or 0
        d['mirror_bonus_given'] = d.get('mirror_bonus_given') or 0
        return d


async def set_subscribe(user_id: int, new_date, force: bool = False):
    pool = await get_pool()
    # asyncpg требует datetime объект, не строку
    if isinstance(new_date, str):
        new_date = datetime.strptime(new_date[:19], "%Y-%m-%d %H:%M:%S")
    async with pool.acquire() as conn:
        if not force:
            # Продлеваем подписку: если текущая в будущем — прибавляем к ней, иначе к now()
            current = await conn.fetchval("SELECT subscribe FROM users WHERE user_id = $1", user_id)
            if current and current > datetime.now():
                delta = new_date - datetime.now()
                new_date = current + delta
        await conn.execute(
            "UPDATE users SET subscribe = $1, sub_expiry_notified = FALSE WHERE user_id = $2",
            new_date, user_id
        )


async def set_premium(user_id: int, value: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET premium = $1 WHERE user_id = $2",
            value, user_id
        )


async def set_verified(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET verified = 1 WHERE user_id = $1",
            user_id
        )


async def is_verified(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT verified FROM users WHERE user_id = $1", user_id)
        return bool(row["verified"]) if row else False


async def get_lang(user_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM users WHERE user_id = $1", user_id)
        if not row:
            return 'ru'
        return row['lang'] or 'ru'


async def set_lang(user_id: int, lang: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute("UPDATE users SET lang = $1 WHERE user_id = $2", lang, user_id)
        except Exception:
            pass


async def get_all_user_ids() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [r["user_id"] for r in rows]


async def get_all_users_with_mirrors() -> dict[int, str | None]:
    """Один запрос: {user_id: mirror_token | None} для всех пользователей."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.user_id, ma.mirror_token
            FROM users u
            LEFT JOIN mirror_assignments ma ON ma.user_id = u.user_id
        """)
    return {r["user_id"]: r["mirror_token"] for r in rows}


async def get_users_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


# ─── Blocked ──────────────────────────────────────────────────────────────────

async def is_blocked(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM blocked WHERE user_id = $1", user_id)
        return row is not None


async def block_user(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO blocked (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_id
        )

async def unblock_user(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM blocked WHERE user_id = $1", user_id)


async def delete_user(user_id: int):
    """Полностью удаляет пользователя из БД (users + blocked + зеркала)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM blocked WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM mirrors WHERE user_id = $1", user_id)


# ─── Whitelist ────────────────────────────────────────────────────────────────

async def get_whitelist() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM whitelist")
        return [r["user_id"] for r in rows]


async def add_to_whitelist(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO whitelist (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_id
        )


# ─── Promocodes ───────────────────────────────────────────────────────────────

async def get_promo(code: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM promocode WHERE code = $1", code)
        return dict(row) if row else None


async def create_promo(code: str, days: int, activations: int, promo_type: str = 'normal'):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Добавляем колонку promo_type если нет
        try:
            await conn.execute("ALTER TABLE promocode ADD COLUMN IF NOT EXISTS promo_type TEXT DEFAULT 'normal'")
        except Exception:
            pass
        await conn.execute(
            "INSERT INTO promocode (code, days, activations, promo_type) VALUES ($1, $2, $3, $4)",
            code, days, activations, promo_type
        )


async def use_promo(code: str, user_id: int, new_date):
    if isinstance(new_date, str):
        new_date = datetime.strptime(new_date[:19], "%Y-%m-%d %H:%M:%S")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE promocode SET activations = activations - 1 WHERE code = $1",
            code
        )
        # Промокод всегда продлевает относительно текущей даты (force=False через set_subscribe)
        await conn.execute(
            "UPDATE users SET subscribe = $1 WHERE user_id = $2",
            new_date, user_id
        )


async def is_promo_used_by(code: str, user_id: int) -> bool:
    """Проверяет — активировал ли пользователь уже этот промокод."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM promo_uses WHERE code = $1 AND user_id = $2",
            code, user_id
        )
        return row is not None


async def mark_promo_used(code: str, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO promo_uses (code, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            code, user_id
        )


# ─── Рефералы ─────────────────────────────────────────────────────────────────

async def set_referrer(user_id: int, referrer_id: int):
    """Устанавливает реферера для нового пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET referrer_id = $1 WHERE user_id = $2 AND referrer_id IS NULL",
            referrer_id, user_id
        )


async def increment_referral_count(referrer_id: int) -> int:
    """Увеличивает счётчик рефералов и возвращает новое значение."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1 WHERE user_id = $1 RETURNING referral_count",
            referrer_id
        )
        return int(row["referral_count"]) if row and row["referral_count"] is not None else 1


async def get_referral_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT referral_count FROM users WHERE user_id = $1", user_id)
        return int(row["referral_count"] or 0) if row else 0


async def spend_referrals(user_id: int, amount: int = 10):
    """Снимает amount рефералов у пользователя. Возвращает True если успешно."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET referral_count = referral_count - $1 WHERE user_id = $2 AND referral_count >= $1 RETURNING referral_count",
            amount, user_id
        )
        return row is not None


async def get_referrer_id(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT referrer_id FROM users WHERE user_id = $1", user_id)
        return row["referrer_id"] if row else None


# ─── Бесплатные репорты ───────────────────────────────────────────────────────

async def get_free_reports(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT free_reports FROM users WHERE user_id = $1", user_id)
        return int(row["free_reports"] or 0) if row else 0


async def add_free_reports(user_id: int, amount: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # COALESCE защищает от NULL — NULL + N = NULL в PostgreSQL
        await conn.execute(
            "UPDATE users SET free_reports = COALESCE(free_reports, 0) + $1 WHERE user_id = $2",
            amount, user_id
        )


async def use_free_report(user_id: int) -> bool:
    """Использует 1 бесплатный репорт. Возвращает True если успешно."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET free_reports = free_reports - 1 WHERE user_id = $1 AND free_reports > 0 RETURNING free_reports",
            user_id
        )
        return row is not None


# ─── Колесо удачи ─────────────────────────────────────────────────────────────

async def get_wheel_last_spin(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT wheel_last_spin FROM users WHERE user_id = $1", user_id)
        return row["wheel_last_spin"] if row else None


async def set_wheel_last_spin(user_id: int, dt):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET wheel_last_spin = $1 WHERE user_id = $2",
            dt, user_id
        )


async def get_wheel_prize(user_id: int) -> str:
    """Возвращает последний выигрыш колеса (чтобы знать, заблокирован ли спин)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow("SELECT wheel_prize FROM users WHERE user_id = $1", user_id)
            return row["wheel_prize"] if row and row["wheel_prize"] else ""
        except Exception:
            return ""


async def set_wheel_prize(user_id: int, prize: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "UPDATE users SET wheel_prize = $1 WHERE user_id = $2",
                prize, user_id
            )
        except Exception:
            pass


# ─── Зеркала ──────────────────────────────────────────────────────────────────

async def init_mirrors_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mirrors (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                bot_username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Флаг что бонус за зеркало уже выдан
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mirror_bonus_given INT DEFAULT 0")
        except Exception:
            pass
        # Системные зеркала — только они раздаются gateway ботами
        try:
            await conn.execute("ALTER TABLE mirrors ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE")
        except Exception:
            pass


async def _init_paid_invoices_table():
    """Таблица для защиты от повторного начисления по одному инвойсу."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS paid_invoices (
                invoice_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)


async def is_invoice_used(invoice_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM paid_invoices WHERE invoice_id = $1", invoice_id)
        return row is not None


async def mark_invoice_used(invoice_id: str, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO paid_invoices (invoice_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            invoice_id, user_id
        )


async def add_mirror(user_id: int, token: str, bot_username: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO mirrors (token, user_id, bot_username) VALUES ($1, $2, $3)",
            token, user_id, bot_username
        )


async def get_user_mirrors(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT token, bot_username, created_at FROM mirrors WHERE user_id = $1 ORDER BY created_at",
            user_id
        )
        return [dict(r) for r in rows]


async def count_user_mirrors(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM mirrors WHERE user_id = $1", user_id)


async def token_exists(token: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM mirrors WHERE token = $1", token)
        return row is not None


async def get_all_mirror_tokens() -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT token FROM mirrors")
        return [r["token"] for r in rows]


async def get_all_mirror_tokens_user() -> list[str]:
    """Все зеркала включая пользовательские (для статистики)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT token FROM mirrors")
        return [r["token"] for r in rows]


async def remove_mirror_by_token(token: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM mirrors WHERE token = $1", token)


async def get_mirror_bonus_given(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT mirror_bonus_given FROM users WHERE user_id = $1", user_id)
        return bool(row["mirror_bonus_given"] or 0) if row else False


async def set_mirror_bonus_given(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET mirror_bonus_given = 1 WHERE user_id = $1", user_id)


async def get_all_mirrors() -> list[dict]:
    """Возвращает все зеркала для админ-панели."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT token, user_id, bot_username, created_at FROM mirrors ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]


async def set_free_reports(user_id: int, amount: int):
    """Устанавливает точное количество бесплатных репортов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET free_reports = $1 WHERE user_id = $2", amount, user_id)


async def get_users_page(offset: int = 0, limit: int = 10) -> list[dict]:
    """Возвращает страницу пользователей с основными данными."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, subscribe, premium, free_reports FROM users ORDER BY user_id DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        return [dict(r) for r in rows]


async def get_subscribers_count() -> int:
    """Количество пользователей с активной подпиской."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE subscribe > NOW()"
        )


async def get_users_with_reports_count() -> int:
    """Количество пользователей у которых есть бесплатные репорты."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE free_reports > 0"
        )


async def get_mirrors_count() -> int:
    """Общее количество зеркал."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM mirrors")


async def resolve_user(input_str: str) -> int | None:
    """
    Принимает ID (число) или @username.
    Возвращает user_id или None если не найден.
    """
    input_str = input_str.strip().lstrip('@')
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Если число — ищем по ID
        if input_str.isdigit():
            uid = int(input_str)
            row = await conn.fetchrow("SELECT user_id FROM users WHERE user_id = $1", uid)
            return uid if row else None
        # Иначе ищем по username (без @)
        row = await conn.fetchrow(
            "SELECT user_id FROM users WHERE LOWER(username) = LOWER($1)", input_str
        )
        return row["user_id"] if row else None


async def is_manual_confirmed(user_id: int) -> bool:
    """Проверяет подтвердил ли пользователь прочтение мануала."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow("SELECT manual_confirmed FROM users WHERE user_id = $1", user_id)
            return bool(row["manual_confirmed"] or 0) if row else False
        except Exception:
            return False


async def set_manual_confirmed(user_id: int):
    """Помечает что пользователь прочитал мануал."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute("UPDATE users SET manual_confirmed = 1 WHERE user_id = $1", user_id)
        except Exception:
            pass


async def is_method_manual_confirmed(user_id: int, method: str) -> bool:
    """Проверяет подтвердил ли пользователь мануал для конкретного метода."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT 1 FROM manual_confirmed_methods WHERE user_id=$1 AND method=$2",
                user_id, method)
            return row is not None
        except Exception:
            return False


async def set_method_manual_confirmed(user_id: int, method: str):
    """Помечает что пользователь прочитал мануал для конкретного метода."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO manual_confirmed_methods (user_id, method) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                user_id, method)
        except Exception:
            pass


# ─── Белый список целей (username/channel) ────────────────────────────────────

async def init_target_whitelist_table():
    """Создаёт таблицу белого списка целей."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS target_whitelist (
                pattern TEXT PRIMARY KEY,
                added_by BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)


async def add_target_whitelist(pattern: str, added_by: int = 0):
    """Добавляет паттерн в белый список целей. Паттерн — username без @, строчными."""
    pattern = pattern.strip().lstrip('@').lower()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO target_whitelist (pattern, added_by) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            pattern, added_by
        )


async def remove_target_whitelist(pattern: str):
    """Удаляет паттерн из белого списка."""
    pattern = pattern.strip().lstrip('@').lower()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM target_whitelist WHERE pattern = $1", pattern)


async def get_target_whitelist() -> list[str]:
    """Возвращает все паттерны белого списка."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT pattern FROM target_whitelist ORDER BY created_at")
        return [r["pattern"] for r in rows]


# ─── Кейсы ───────────────────────────────────────────────────────────────────

async def init_cases_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                invoice_id TEXT UNIQUE NOT NULL,
                opened BOOLEAN DEFAULT FALSE,
                prize TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)


async def add_case(user_id: int, invoice_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO cases (user_id, invoice_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id, invoice_id
        )


async def get_unopened_cases(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM cases WHERE user_id = $1 AND opened = FALSE",
            user_id
        ) or 0


async def open_case(user_id: int) -> str | None:
    """Открывает один кейс, возвращает invoice_id или None если нет кейсов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM cases WHERE user_id = $1 AND opened = FALSE ORDER BY created_at LIMIT 1",
            user_id
        )
        if not row:
            return None
        await conn.execute(
            "UPDATE cases SET opened = TRUE WHERE id = $1",
            row["id"]
        )
        return str(row["id"])


async def set_case_prize(case_id: str, prize: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE cases SET prize = $1 WHERE id = $2",
            prize, int(case_id)
        )


async def is_target_whitelisted(target: str) -> bool:
    """
    Проверяет — находится ли цель в белом списке.
    target — username без @, строчными.
    Сравниваем: если паттерн совпадает с началом username (первые N символов) или полностью.
    """
    target = target.strip().lstrip('@').lower()
    patterns = await get_target_whitelist()
    for p in patterns:
        # Точное совпадение ИЛИ username начинается с паттерна
        if target == p or target.startswith(p):
            return True
    return False


# ─── Кейсы ────────────────────────────────────────────────────────────────────

async def init_cases_table():
    """Создаёт таблицу кейсов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                opened BOOLEAN DEFAULT FALSE,
                invoice_id TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)


async def add_case(user_id: int, invoice_id: str = None) -> int:
    """Добавляет кейс пользователю. Возвращает id кейса."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO cases (user_id, invoice_id) VALUES ($1, $2) RETURNING id",
            user_id, invoice_id
        )
        return row["id"]


async def get_unopened_cases(user_id: int) -> int:
    """Возвращает количество неоткрытых кейсов у пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM cases WHERE user_id = $1 AND opened = FALSE",
            user_id
        )


async def open_case(user_id: int) -> bool:
    """Открывает один кейс (помечает как opened). Возвращает True если был кейс."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE cases SET opened = TRUE
               WHERE id = (
                   SELECT id FROM cases WHERE user_id = $1 AND opened = FALSE
                   ORDER BY created_at ASC LIMIT 1
               ) RETURNING id""",
            user_id
        )
        return row is not None


async def is_case_invoice_used(invoice_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM cases WHERE invoice_id = $1", invoice_id
        )
        return row is not None


# ─── Мониторинг ───────────────────────────────────────────────────────────────

async def init_monitors_table():
    """Создаёт таблицу мониторов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monitors (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                target TEXT NOT NULL,
                status TEXT DEFAULT 'alive',
                active BOOLEAN DEFAULT TRUE,
                notified BOOLEAN DEFAULT FALSE,
                notify_silent BOOLEAN DEFAULT FALSE,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                last_check TIMESTAMP DEFAULT NOW()
            )
        """)
        # Добавляем колонки если их нет (для существующих БД)
        await conn.execute("""
            ALTER TABLE monitors ADD COLUMN IF NOT EXISTS notify_silent BOOLEAN DEFAULT FALSE
        """)
        await conn.execute("""
            ALTER TABLE monitors ADD COLUMN IF NOT EXISTS dead_strikes INT DEFAULT 0
        """)


async def add_monitor(user_id: int, target: str, expires_at: datetime) -> int:
    """Добавляет монитор. Возвращает id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO monitors (user_id, target, expires_at)
               VALUES ($1, $2, $3) RETURNING id""",
            user_id, target, expires_at
        )
        return row["id"]


async def get_active_monitors() -> list[dict]:
    """Возвращает все активные мониторы."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM monitors WHERE active = TRUE ORDER BY created_at"
        )
        return [dict(r) for r in rows]


async def get_user_monitors(user_id: int) -> list[dict]:
    """Возвращает все мониторы пользователя (включая неактивные)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM monitors WHERE user_id = $1 ORDER BY created_at DESC",
            user_id
        )
        return [dict(r) for r in rows]


async def get_user_active_monitors_count(user_id: int) -> int:
    """Количество активных мониторов пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM monitors WHERE user_id = $1 AND active = TRUE",
            user_id
        ) or 0


async def is_target_already_monitored(user_id: int, target: str) -> bool:
    """Проверяет — мониторит ли пользователь уже эту цель."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM monitors WHERE user_id = $1 AND target = $2 AND active = TRUE",
            user_id, target
        )
        return row is not None


async def was_target_monitored_before(user_id: int, target: str) -> bool:
    """Проверяет — мониторил ли пользователь эту цель раньше (нельзя дважды)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM monitors WHERE user_id = $1 AND target = $2",
            user_id, target
        )
        return row is not None


async def update_monitor_check(monitor_id: int, new_status: str):
    """Обновляет статус и время последней проверки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE monitors SET status = $1, last_check = NOW() WHERE id = $2",
            new_status, monitor_id
        )


async def increment_monitor_dead_strikes(monitor_id: int) -> int:
    """Увеличивает счётчик подряд-dead. Возвращает новое значение."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE monitors SET dead_strikes = dead_strikes + 1 WHERE id = $1 RETURNING dead_strikes",
            monitor_id
        )
        return row["dead_strikes"] if row else 1


async def reset_monitor_dead_strikes(monitor_id: int):
    """Сбрасывает счётчик dead_strikes при живой цели."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE monitors SET dead_strikes = 0 WHERE id = $1",
            monitor_id
        )


async def mark_monitor_notified(monitor_id: int):
    """Помечает монитор как уведомлённый."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE monitors SET notified = TRUE WHERE id = $1",
            monitor_id
        )


async def deactivate_monitor(monitor_id: int):
    """Деактивирует монитор."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE monitors SET active = FALSE WHERE id = $1",
            monitor_id
        )


async def set_monitor_silent(monitor_id: int, user_id: int, silent: bool) -> bool:
    """Включает/выключает тихий режим (без периодических уведомлений). Возвращает True если найден."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE monitors SET notify_silent = $1 WHERE id = $2 AND user_id = $3 RETURNING id",
            silent, monitor_id, user_id
        )
        return row is not None


async def delete_monitor(monitor_id: int, user_id: int) -> bool:
    """Удаляет монитор пользователя. Возвращает True если удалён."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM monitors WHERE id = $1 AND user_id = $2 RETURNING id",
            monitor_id, user_id
        )
        return row is not None


# ─── История атак ─────────────────────────────────────────────────────────────

async def init_attack_log_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS attack_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                target_url TEXT NOT NULL,
                method TEXT NOT NULL,
                success_count INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS attack_log_user_idx ON attack_log(user_id, created_at DESC)")


async def clear_attack_log_current_week():
    """Очищает записи текущей недели (сброс к нулю)."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM attack_log WHERE created_at >= $1", week_start)


async def log_attack(user_id: int, target_url: str, method: str, success_count: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO attack_log (user_id, target_url, method, success_count) VALUES ($1, $2, $3, $4)",
            user_id, target_url[:500], method, success_count
        )


async def get_attack_history(user_id: int, limit: int = 10, offset: int = 0) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT target_url, method, success_count, created_at FROM attack_log WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            user_id, limit, offset
        )
        return [dict(r) for r in rows]


async def get_attack_history_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM attack_log WHERE user_id = $1", user_id)
        return row["cnt"] if row else 0


# ─── Уведомления об истечении подписки ───────────────────────────────────────

async def get_expiring_soon_users() -> list:
    """Возвращает пользователей у которых подписка истекает через 2.5–3.5 ч и ещё не уведомлены."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id FROM users
            WHERE subscribe BETWEEN NOW() + INTERVAL '2.5 hours' AND NOW() + INTERVAL '3.5 hours'
              AND (sub_expiry_notified = FALSE OR sub_expiry_notified IS NULL)
            """
        )
        return [r['user_id'] for r in rows]


async def mark_sub_expiry_notified(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET sub_expiry_notified = TRUE WHERE user_id = $1",
            user_id
        )


async def reset_sub_expiry_notified(user_id: int):
    """Сбрасывает флаг когда подписка продлена (чтобы уведомить при следующем истечении)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET sub_expiry_notified = FALSE WHERE user_id = $1",
            user_id
        )


# ─── Еженедельный рейтинг ────────────────────────────────────────────────────

async def init_leaderboard_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leaderboard_winners (
                id SERIAL PRIMARY KEY,
                week_start DATE NOT NULL,
                place INT NOT NULL,
                user_id BIGINT NOT NULL,
                username TEXT DEFAULT '',
                total_reports INT NOT NULL DEFAULT 0,
                stars_prize INT NOT NULL DEFAULT 0,
                paid BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)


async def get_weekly_top3(week_start, week_end) -> list:
    """Топ-3 пользователей по количеству репортов за период."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT al.user_id,
                   COALESCE(u.username, '') AS username,
                   COUNT(*) AS total
            FROM attack_log al
            LEFT JOIN users u ON u.user_id = al.user_id
            WHERE al.created_at >= $1 AND al.created_at < $2
            GROUP BY al.user_id, u.username
            ORDER BY total DESC
            LIMIT 3
        """, week_start, week_end)
        return [dict(r) for r in rows]


async def save_leaderboard_winners(week_start, winners: list):
    """Сохраняет победителей недели в историю."""
    _PRIZES = {1: 150, 2: 75, 3: 50}
    pool = await get_pool()
    async with pool.acquire() as conn:
        for i, row in enumerate(winners, 1):
            await conn.execute("""
                INSERT INTO leaderboard_winners (week_start, place, user_id, username, total_reports, stars_prize)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT DO NOTHING
            """, week_start.date(), i, row['user_id'], row['username'],
                int(row['total']), _PRIZES.get(i, 0))


# ─── Пробив — лимиты ──────────────────────────────────────────────────────────

async def get_probiv_usage(user_id: int) -> dict:
    """Возвращает данные использования пробива для пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_request_at, hour_count, hour_window_start FROM probiv_usage WHERE user_id = $1",
            user_id
        )
        if not row:
            return {"last_request_at": None, "hour_count": 0, "hour_window_start": None}
        return dict(row)


async def record_probiv_request(user_id: int, now_dt):
    """Записывает новый запрос пробива. Сбрасывает счётчик если прошёл час."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT hour_count, hour_window_start FROM probiv_usage WHERE user_id = $1",
            user_id
        )
        if row is None:
            await conn.execute(
                """INSERT INTO probiv_usage (user_id, last_request_at, hour_count, hour_window_start)
                   VALUES ($1, $2, 1, $2)""",
                user_id, now_dt
            )
        else:
            window = row["hour_window_start"]
            count = row["hour_count"]
            window_cmp = window.replace(tzinfo=None) if (window and getattr(window, "tzinfo", None)) else window
            if window_cmp and (now_dt - window_cmp).total_seconds() < 3600:
                new_count = count + 1
                new_window = window
            else:
                new_count = 1
                new_window = now_dt
            await conn.execute(
                """INSERT INTO probiv_usage (user_id, last_request_at, hour_count, hour_window_start)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (user_id) DO UPDATE
                   SET last_request_at = $2, hour_count = $3, hour_window_start = $4""",
                user_id, now_dt, new_count, new_window
            )


async def get_is_hidden(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_hidden FROM users WHERE user_id = $1", user_id)
        return bool(row["is_hidden"]) if row else False


async def toggle_hidden(user_id: int) -> bool:
    """Переключает is_hidden, возвращает новое значение."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_hidden FROM users WHERE user_id = $1", user_id)
        new_val = not bool(row["is_hidden"]) if row else True
        await conn.execute("UPDATE users SET is_hidden = $1 WHERE user_id = $2", new_val, user_id)
        return new_val


# ─── Крипто-кошельки (ротация) ────────────────────────────────────────────────

async def init_crypto_wallets_table():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crypto_wallets (
                slot INT PRIMARY KEY CHECK (slot BETWEEN 1 AND 5),
                address TEXT NOT NULL,
                is_active BOOLEAN DEFAULT FALSE
            )
        """)


async def get_active_wallet() -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT address FROM crypto_wallets WHERE is_active = TRUE LIMIT 1")
        return row["address"] if row else None


async def get_all_wallets() -> list:
    """Возвращает все слоты [{'slot': 1, 'address': '...', 'is_active': True/False}, ...]."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT slot, address, is_active FROM crypto_wallets ORDER BY slot")
        return [dict(r) for r in rows]


async def set_wallet_slot(slot: int, address: str):
    """Добавляет или обновляет кошелёк в указанном слоте (1-5)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO crypto_wallets (slot, address, is_active) VALUES ($1, $2, FALSE) "
            "ON CONFLICT (slot) DO UPDATE SET address = $2",
            slot, address
        )


async def remove_wallet_slot(slot: int):
    """Удаляет кошелёк из слота. Если он был активным — ротация на следующий."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_active FROM crypto_wallets WHERE slot = $1", slot)
        was_active = row["is_active"] if row else False
        await conn.execute("DELETE FROM crypto_wallets WHERE slot = $1", slot)
    if was_active:
        await rotate_wallet()


async def rotate_wallet() -> str | None:
    """Переключает активный кошелёк на следующий. Возвращает новый адрес или None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT slot, address FROM crypto_wallets ORDER BY slot"
        )
        if not rows:
            return None
        slots = [dict(r) for r in rows]
        active_row = await conn.fetchrow("SELECT slot FROM crypto_wallets WHERE is_active = TRUE LIMIT 1")
        current_slot = active_row["slot"] if active_row else 0

        # Ищем следующий слот после текущего (с wraparound)
        next_entry = None
        for entry in slots:
            if entry["slot"] > current_slot:
                next_entry = entry
                break
        if next_entry is None:
            next_entry = slots[0]  # wraparound

        await conn.execute("UPDATE crypto_wallets SET is_active = FALSE WHERE is_active = TRUE")
        await conn.execute("UPDATE crypto_wallets SET is_active = TRUE WHERE slot = $1", next_entry["slot"])
        return next_entry["address"]


# ─── Gateway / Mirror assignments ─────────────────────────────────────────────

async def init_gateway_tables():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mirror_assignments (
                user_id BIGINT PRIMARY KEY,
                mirror_token TEXT NOT NULL,
                gateway_bot_id INT DEFAULT 1,
                assigned_at TIMESTAMP DEFAULT NOW()
            )
        """)


async def get_user_mirror(user_id: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT mirror_token FROM mirror_assignments WHERE user_id = $1", user_id
        )


async def assign_mirror_to_user(user_id: int, mirror_token: str, gateway_bot_id: int = 1):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mirror_assignments (user_id, mirror_token, gateway_bot_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET mirror_token = $2, gateway_bot_id = $3, assigned_at = NOW()
        """, user_id, mirror_token, gateway_bot_id)


async def touch_user_mirror(user_id: int, mirror_token: str):
    """Обновляет активное зеркало юзера не меняя gateway_bot_id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mirror_assignments (user_id, mirror_token, gateway_bot_id, last_bot_token)
            VALUES ($1, $2, 0, $2)
            ON CONFLICT (user_id) DO UPDATE SET mirror_token = $2, assigned_at = NOW(), last_bot_token = $2
        """, user_id, mirror_token)


async def touch_user_main_bot(user_id: int):
    """Фиксирует, что юзер последний раз взаимодействовал с основным ботом."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute("""
                INSERT INTO mirror_assignments (user_id, mirror_token, gateway_bot_id, last_bot_token)
                VALUES ($1, '', 0, '__main__')
                ON CONFLICT (user_id) DO UPDATE SET last_bot_token = '__main__', assigned_at = NOW()
            """, user_id)
        except Exception:
            pass


async def get_user_last_bot(user_id: int) -> str:
    """Возвращает '__main__' или токен зеркала — через что юзер писал последний раз."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            val = await conn.fetchval(
                "SELECT last_bot_token FROM mirror_assignments WHERE user_id = $1", user_id
            )
            return val or '__main__'
        except Exception:
            return '__main__'


async def get_free_mirror(exclude: str = None) -> str | None:
    """Возвращает токен зеркала с наименьшим числом назначений.
    Сначала ищет незанятое, иначе возвращает наименее загруженное."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exclude_clause = "AND m.token != $1" if exclude else ""
        params = [exclude] if exclude else []
        # Берём зеркало с минимумом назначений
        row = await conn.fetchrow(f"""
            SELECT m.token, COUNT(a.user_id) as cnt
            FROM mirrors m
            LEFT JOIN mirror_assignments a ON a.mirror_token = m.token
            WHERE 1=1 {exclude_clause}
            GROUP BY m.token
            ORDER BY cnt ASC
            LIMIT 1
        """, *params)
        return row["token"] if row else None


async def add_system_mirror(token: str, bot_username: str):
    """Добавляет системное зеркало (для gateway). user_id=0 — наше."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mirrors (token, user_id, bot_username, is_system)
            VALUES ($1, 0, $2, TRUE)
            ON CONFLICT (token) DO UPDATE SET is_system = TRUE, bot_username = $2
        """, token, bot_username)


async def get_mirror_user_count(mirror_token: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM mirror_assignments WHERE mirror_token = $1", mirror_token
        ) or 0


# ─── TG Маркет ────────────────────────────────────────────────────────────────

async def create_market_order(user_id: int, payment_method: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO tg_market_orders (user_id, payment_method) VALUES ($1, $2) RETURNING id",
            user_id, payment_method
        )
        return row["id"]


async def fulfill_market_order(order_id: int, session_file: str, phone: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tg_market_orders SET session_file=$1, phone=$2, status='paid' WHERE id=$3",
            session_file, phone, order_id
        )


async def get_market_order(order_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tg_market_orders WHERE id=$1", order_id)
        return dict(row) if row else None


async def get_user_active_market_order(user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tg_market_orders WHERE user_id=$1 AND status='pending' ORDER BY created_at DESC LIMIT 1",
            user_id
        )
        return dict(row) if row else None


async def set_market_order_invoice(order_id: int, invoice_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tg_market_orders SET invoice_id=$1 WHERE id=$2",
            invoice_id, order_id
        )


async def get_market_order_by_invoice(invoice_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tg_market_orders WHERE invoice_id=$1", invoice_id
        )
        return dict(row) if row else None


async def get_user_fulfilled_market_orders(user_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tg_market_orders WHERE user_id=$1 AND status='paid' ORDER BY created_at DESC LIMIT 10",
            user_id
        )
        return [dict(r) for r in rows]


# ─── Предупреждения ───────────────────────────────────────────────────────────

async def add_warning(user_id: int, admin_id: int, reason: str) -> int:
    """Добавляет предупреждение. Возвращает новый счётчик предупреждений."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO warnings (user_id, admin_id, reason) VALUES ($1, $2, $3)",
            user_id, admin_id, reason
        )
        return await conn.fetchval(
            "SELECT COUNT(*) FROM warnings WHERE user_id = $1", user_id
        )


async def get_warning_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM warnings WHERE user_id = $1", user_id
        ) or 0


async def get_warnings(user_id: int, limit: int = 20, offset: int = 0) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, admin_id, reason, created_at FROM warnings WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            user_id, limit, offset
        )
        return [dict(r) for r in rows]


async def add_log_entry(user_id: int) -> int:
    """Создаёт запись лога, возвращает её ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO log_entries (user_id) VALUES ($1) RETURNING id",
            user_id
        )


async def get_log_entry_user(log_id: int) -> int | None:
    """Возвращает user_id по ID лога, или None если не найден."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT user_id FROM log_entries WHERE id = $1",
            log_id
        )


# ─── Chatbot (Business Bot API) ───────────────────────────────────────────────

async def chatbot_save_connection(user_id: int, connection_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO business_connections (user_id, connection_id)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET connection_id=$2, connected_at=NOW()""",
            user_id, connection_id
        )
        await conn.execute(
            "UPDATE users SET chatbot_enabled=TRUE WHERE user_id=$1", user_id
        )


async def chatbot_remove_connection(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM business_connections WHERE user_id=$1", user_id)
        await conn.execute(
            "UPDATE users SET chatbot_enabled=FALSE WHERE user_id=$1", user_id
        )


async def chatbot_get_connection(user_id: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT connection_id FROM business_connections WHERE user_id=$1", user_id
        )


async def chatbot_get_user_by_connection(connection_id: str) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT user_id FROM business_connections WHERE connection_id=$1", connection_id
        )


async def chatbot_is_enabled(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT chatbot_enabled FROM users WHERE user_id=$1", user_id
        )
        return bool(val)


async def chatbot_set_mute(user_id: int, chat_id: int, until=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO chatbot_mutes (user_id, chat_id, until)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id, chat_id) DO UPDATE SET until=$3""",
            user_id, chat_id, until
        )


async def chatbot_remove_mute(user_id: int, chat_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chatbot_mutes WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id
        )


async def chatbot_is_muted(user_id: int, chat_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT until FROM chatbot_mutes WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id
        )
        if not row:
            return False
        if row['until'] is None:
            return True
        from utils import now_msk
        return now_msk() < row['until'].replace(tzinfo=None)


async def chatbot_cache_message(user_id: int, chat_id: int, message_id: int, from_id: int, text: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO chatbot_msg_cache (user_id, chat_id, message_id, from_id, text)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (user_id, chat_id, message_id) DO NOTHING""",
            user_id, chat_id, message_id, from_id, text
        )


async def chatbot_get_cached_messages(user_id: int, chat_id: int, message_ids: list) -> list:
    if not message_ids:
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT message_id, from_id, text FROM chatbot_msg_cache
               WHERE user_id=$1 AND chat_id=$2 AND message_id=ANY($3::int[])""",
            user_id, chat_id, message_ids
        )
        return [dict(r) for r in rows]


async def chatbot_clean_old_cache():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chatbot_msg_cache WHERE created_at < NOW() - INTERVAL '48 hours'"
        )
