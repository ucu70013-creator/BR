"""
tg_market.py — TG Маркет: работа с пулом .session файлов Telethon.
"""
import os
import re
import sqlite3
import random

MARKET_DIR = "TG market"
ARH_DIR = "TG Arh"

_API_ID   = 24565698
_API_HASH = "5a084b434f8505ace703485b9da85040"


def get_available_count() -> int:
    if not os.path.exists(MARKET_DIR):
        return 0
    return len([f for f in os.listdir(MARKET_DIR) if f.endswith('.session')])


def _get_phone_from_session(path: str) -> str | None:
    """Пробует достать номер телефона из SQLite-сессии Telethon."""
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        try:
            # Исключаем 42777 (Telegram-сервис 777000) и короткие номера < 10 цифр
            cur.execute(
                "SELECT phone FROM entities "
                "WHERE phone IS NOT NULL AND phone != '' AND phone != '42777' "
                "AND LENGTH(phone) >= 10 LIMIT 1"
            )
            row = cur.fetchone()
            if row and row[0]:
                conn.close()
                p = str(row[0]).strip()
                return p if p.startswith('+') else f"+{p}"
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return None


async def _get_phone_via_telethon(session_path_no_ext: str) -> str | None:
    """Подключается к аккаунту и получает номер через get_me()."""
    try:
        from telethon import TelegramClient
        client = TelegramClient(session_path_no_ext, _API_ID, _API_HASH,
                                system_version="4.16.30-vxCUSTOM")
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        me = await client.get_me()
        await client.disconnect()
        if me and me.phone:
            p = str(me.phone).strip()
            return p if p.startswith('+') else f"+{p}"
        return None
    except Exception as e:
        print(f"[tg_market] _get_phone_via_telethon error: {e}")
        return None


async def pick_session_async() -> tuple[str, str] | tuple[None, None]:
    """Берёт случайный .session, получает телефон (SQLite → Telethon). Возвращает (filename, phone) или (None, None)."""
    if not os.path.exists(MARKET_DIR):
        return None, None
    files = [f for f in os.listdir(MARKET_DIR) if f.endswith('.session')]
    if not files:
        return None, None
    # Перемешиваем и перебираем пока не найдём рабочую сессию с телефоном
    random.shuffle(files)
    for filename in files:
        full_path = os.path.join(MARKET_DIR, filename)
        phone = _get_phone_from_session(full_path)
        if not phone:
            session_path = full_path[:-8] if full_path.endswith('.session') else full_path
            phone = await _get_phone_via_telethon(session_path)
        if phone:
            return filename, phone
    return None, None


def pick_session() -> tuple[str, str] | tuple[None, None]:
    """Синхронная версия (только SQLite). Используй pick_session_async() для полного поиска."""
    if not os.path.exists(MARKET_DIR):
        return None, None
    files = [f for f in os.listdir(MARKET_DIR) if f.endswith('.session')]
    if not files:
        return None, None
    filename = random.choice(files)
    phone = _get_phone_from_session(os.path.join(MARKET_DIR, filename))
    return filename, phone


def archive_session(filename: str):
    """Перемещает файл из MARKET_DIR в ARH_DIR."""
    src = os.path.join(MARKET_DIR, filename)
    os.makedirs(ARH_DIR, exist_ok=True)
    dst = os.path.join(ARH_DIR, filename)
    if os.path.exists(src):
        os.rename(src, dst)


async def get_auth_code(session_filename: str) -> str | None:
    """
    Подключается к аккаунту через Telethon и ищет последний код авторизации
    в сообщениях от 777000.
    """
    try:
        from telethon import TelegramClient

        # Ищем файл — сначала в архиве, потом в пуле
        path = None
        for directory in (ARH_DIR, MARKET_DIR):
            candidate = os.path.join(directory, session_filename)
            if os.path.exists(candidate):
                path = candidate
                break
        if path is None:
            return None

        # Telethon принимает путь без .session
        session_path = path[:-8] if path.endswith('.session') else path

        client = TelegramClient(session_path, _API_ID, _API_HASH,
                                system_version="4.16.30-vxCUSTOM")
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None

        msgs = await client.get_messages(777000, limit=10)
        await client.disconnect()

        for msg in msgs:
            if msg and msg.text:
                match = re.search(r'\b(\d{5,6})\b', msg.text)
                if match:
                    return match.group(1)
        return None
    except Exception as e:
        print(f"[tg_market] get_auth_code error: {e}")
        return None
