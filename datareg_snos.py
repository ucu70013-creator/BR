"""
datareg_snos.py
Определение даты регистрации через @WhenJoinedBot.
Использует сессии из aureport_sessions/.
"""

import asyncio
import logging
import os
import re

from telethon import TelegramClient, events
import config
from utils import now_msk

logger = logging.getLogger(__name__)

AUREPORT_DIR = "aureport_sessions"

bot = None

def set_bot_datareg(b):
    global bot
    bot = b


def _get_sessions():
    if not os.path.exists(AUREPORT_DIR):
        return []
    files = [f for f in os.listdir(AUREPORT_DIR) if f.endswith(".session")]
    return [os.path.join(AUREPORT_DIR, f.replace(".session", "")) for f in files]


def _load_proxies():
    proxies = []
    if os.path.exists("au_proxies.txt"):
        with open("au_proxies.txt") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    proxies.append(line)
    return proxies


def _parse_proxy(proxy_str):
    try:
        proxy_str = proxy_str.strip()
        proxy_type = "socks5"
        m = re.match(r'^(http|https|socks4|socks5)://', proxy_str, re.IGNORECASE)
        if m:
            proxy_type = m.group(1).lower()
            if proxy_type == "https":
                proxy_type = "http"
            proxy_str = proxy_str[m.end():]

        username = password = ip = port = None
        m = re.match(r'^([^:]+):([^@]+)@([^:]+):(\d+)$', proxy_str)
        if m:
            username, password, ip, port = m.groups()
        else:
            parts = proxy_str.split(":")
            if len(parts) == 4:
                ip, port, username, password = parts
            elif len(parts) == 2:
                ip, port = parts
            else:
                return None

        if username:
            username = username.split(";")[0]

        return {
            "proxy_type": proxy_type,
            "addr": ip,
            "port": int(port),
            "username": username,
            "password": password,
            "rdns": True,
        }
    except Exception:
        return None


async def _create_client(session_path: str, proxy=None):
    try:
        api_id = int(config.AUREPORT_API_ID)
        api_hash = config.AUREPORT_API_HASH
        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy,
                                system_version='4.16.30-vxCUSTOM')
        for attempt in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                break
            except (asyncio.TimeoutError, OSError):
                if attempt == 2:
                    return None
                await asyncio.sleep(1)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        return client
    except Exception as e:
        logger.error(f"[DATAREG] Ошибка создания клиента: {e}")
        return None


def _parse_whenjoinedbot_response(text: str):
    """
    Парсит ответ @WhenJoinedBot (EN и RU форматы).
    Возвращает (account_id, username_or_none, date_from, date_to) или None.
    """
    username = None

    # EN: "User @tarismit with ID 8904492648"
    m_user_en = re.search(r'User\s+(@\S+)\s+with ID\s+(\d+)', text, re.IGNORECASE)
    # EN: "Registered between 2026-05-01 and 2026-10-20"
    m_dates_en = re.search(r'Registered between\s+([\d\-]+)\s+and\s+([\d\-]+)', text, re.IGNORECASE)

    if m_user_en and m_dates_en:
        username = m_user_en.group(1)
        acc_id = m_user_en.group(2)
        date_from = m_dates_en.group(1)
        date_to = m_dates_en.group(2)
        return acc_id, username, date_from, date_to

    # EN без юзернейма: "User with ID 8904492648"
    m_id_en = re.search(r'with ID\s+(\d+)', text, re.IGNORECASE)
    if m_id_en and m_dates_en:
        return m_id_en.group(1), None, m_dates_en.group(1), m_dates_en.group(2)

    # RU: "идентификатором 8871068832" + "с 01.05.2026 по 20.10.2026"
    m_id_ru = re.search(r'идентификатором\s+(\d+)', text)
    m_dates_ru = re.search(r'с\s+([\d.]+)\s+по\s+([\d.]+)', text)
    if m_id_ru and m_dates_ru:
        return m_id_ru.group(1), None, m_dates_ru.group(1), m_dates_ru.group(2)

    return None


async def check_reg_date(target: str, notify_bot=None) -> str:
    """
    Проверяет дату регистрации target (юзернейм или айди).
    Возвращает строку с результатом.
    """
    _notify = notify_bot or bot

    sessions = _get_sessions()
    if not sessions:
        return "❌ Нет сессий для проверки. Добавь .session файлы в aureport_sessions/"

    proxies = _load_proxies()

    # Пробуем сессии по очереди
    for i, session_path in enumerate(sessions):
        proxy = _parse_proxy(proxies[i % len(proxies)]) if proxies else None
        client = await _create_client(session_path, proxy)
        if not client:
            continue

        session_name = os.path.basename(session_path)
        try:
            bot_entity = await asyncio.wait_for(client.get_entity("WhenJoinedBot"), timeout=10)
        except Exception as e:
            logger.warning(f"[DATAREG] [{session_name}] Не удалось найти WhenJoinedBot: {e}")
            await client.disconnect()
            continue

        done = asyncio.Event()
        result_text = None

        @client.on(events.NewMessage(from_users=bot_entity.id))
        async def handler(event):
            nonlocal result_text
            result_text = event.message.message or ""
            logger.info(f"[DATAREG] [{session_name}] Ответ: {result_text[:200]!r}")
            done.set()

        try:
            await client.send_message(bot_entity, target)
            await asyncio.wait_for(done.wait(), timeout=20)
        except asyncio.TimeoutError:
            logger.warning(f"[DATAREG] [{session_name}] Таймаут")
        except Exception as e:
            logger.error(f"[DATAREG] [{session_name}] Ошибка отправки: {e}")
        finally:
            client.remove_event_handler(handler)
            try:
                await client.disconnect()
            except Exception:
                pass

        if result_text:
            parsed = _parse_whenjoinedbot_response(result_text)
            if parsed:
                acc_id, uname, date_from, date_to = parsed
                uname_line = f"👤 *Username:* {uname}\n" if uname else ""
                return (
                    f"📅 *Дата регистрации*\n\n"
                    f"{uname_line}"
                    f"🆔 *ID:* `{acc_id}`\n"
                    f"📆 *Зарегистрирован:* с *{date_from}* по *{date_to}*"
                )
            # Ответ пришёл но в неизвестном формате — отдаём первые 2 строки
            first_lines = "\n".join(result_text.splitlines()[:3]).strip()
            safe = first_lines.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            return f"📅 *Дата регистрации*\n\n{safe}"

    return "❌ Не удалось получить дату регистрации. Попробуй позже."
