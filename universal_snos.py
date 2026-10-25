# coding: utf-8
"""
Brown V2 | universal_snos.py
Универсальный метод — жалобы через все доступные методы по одной ссылке.
"""

import re
import os
import random
import asyncio
import logging
from datetime import timedelta
from typing import Optional

from telethon import TelegramClient
from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError, ChannelPrivateError

import config
from config import bot_logs
import keyboards
from utils import now_msk, esc_md

logger = logging.getLogger(__name__)

bot = None
main_bot = None

# Лок per-user — один запуск на пользователя одновременно
_user_locks: dict = {}  # uid -> asyncio.Lock

def _get_user_lock(uid: int) -> asyncio.Lock:
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]

def set_bot_universal(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b

# ─── API для резолва ──────────────────────────────────────────────────────────
API = [
    '24565698:5a084b434f8505ace703485b9da85040',
    '27904162:e7cba879b1c643ba77490bf328df5eab',
    '23037915:50f06f5b2223586fde0d1379ea91ebc7',
]

SESSION_FOLDER = 'sessions'

def _get_sessions():
    if not os.path.exists(SESSION_FOLDER):
        return []
    return [f.replace('.session', '') for f in os.listdir(SESSION_FOLDER) if f.endswith('.session')]

def _random_creds():
    raw = random.choice(API)
    api_id, api_hash = raw.split(':', 1)
    return int(api_id), api_hash

# ─── Парсер ссылок ────────────────────────────────────────────────────────────

# Типы результата
TYPE_PRIVATE_CHANNEL = "private_channel"   # t.me/c/... — запрещено
TYPE_INVITE          = "invite"            # t.me/+..., joinchat, uppercase hash
TYPE_MESSAGE         = "message"           # t.me/username/123
TYPE_BOT             = "bot"               # t.me/somebot
TYPE_USER_CHANNEL    = "user_channel"      # t.me/username
TYPE_INVALID         = "invalid"           # не распознана


def parse_link(raw: str) -> dict:
    """
    Возвращает:
      {
        "type": TYPE_*,
        "username": str | None,
        "message_id": int | None,
        "normalized": str,          # https://t.me/...
        "error": str | None,
      }
    """
    raw = raw.strip()

    # Извлечь URL из Markdown формата [текст](url)
    md = re.search(r'\[.*?\]\((https?://[^\)]+)\)', raw)
    if md:
        raw = md.group(1)

    # @username → https://t.me/username
    if raw.startswith('@') and '/' not in raw:
        raw = 'https://t.me/' + raw[1:]

    # Нормализовать схему
    if raw.startswith('t.me/'):
        raw = 'https://' + raw
    elif raw.startswith('http://t.me/'):
        raw = 'https://t.me/' + raw[len('http://t.me/'):]

    # Должно начинаться с https://t.me/
    if not raw.startswith('https://t.me/'):
        return _inv("Не распознана как ссылка Telegram")

    path = raw[len('https://t.me/'):].strip('/')

    if not path:
        return _inv("Пустой путь")

    # 1. Приватный канал t.me/c/NUMBER/NUMBER — запрещено
    if re.match(r'^c/\d+(/\d+)?$', path):
        return {
            "type": TYPE_PRIVATE_CHANNEL,
            "username": None, "message_id": None,
            "normalized": raw, "error": None,
        }

    # 2. Инвайт: t.me/+ или t.me/joinchat/
    if path.startswith('+') or path.startswith('joinchat/'):
        return {
            "type": TYPE_INVITE,
            "username": None, "message_id": None,
            "normalized": raw, "error": None,
        }

    # 3. Сегмент содержит заглавные буквы и нет слэша — инвайт-хэш
    segment = path.split('/')[0]
    if re.search(r'[A-Z]', segment) and '/' not in path:
        return {
            "type": TYPE_INVITE,
            "username": None, "message_id": None,
            "normalized": raw, "error": None,
        }

    # 4. Ссылка на сообщение: t.me/username/NUMBER
    msg_match = re.match(r'^([a-zA-Z][a-zA-Z0-9_]{3,})/(\d+)$', path)
    if msg_match:
        uname = msg_match.group(1).lower()
        mid = int(msg_match.group(2))
        return {
            "type": TYPE_MESSAGE,
            "username": uname, "message_id": mid,
            "normalized": f"https://t.me/{uname}/{mid}", "error": None,
        }

    # 5. Просто username
    if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', path):
        uname = path.lower()
        link_type = TYPE_BOT if uname.endswith('bot') else TYPE_USER_CHANNEL
        return {
            "type": link_type,
            "username": uname, "message_id": None,
            "normalized": f"https://t.me/{uname}", "error": None,
        }

    return _inv("Формат ссылки не распознан")


def _inv(msg: str) -> dict:
    return {"type": TYPE_INVALID, "username": None, "message_id": None, "normalized": "", "error": msg}


# ─── Валидация через Telegram API ─────────────────────────────────────────────

async def validate_link(parsed: dict) -> dict:
    """
    Для инвайтов и приват-каналов не валидируем (нельзя без вступления).
    Для остальных — резолвим через Telethon.
    Возвращает parsed обновлённый, добавляет "valid": bool, "error" если есть.
    """
    t = parsed["type"]

    if t in (TYPE_PRIVATE_CHANNEL, TYPE_INVALID):
        return {**parsed, "valid": False}

    if t == TYPE_INVITE:
        # Нельзя проверить без вступления — доверяем формату
        return {**parsed, "valid": True}

    # Нужна Telethon-сессия
    sessions = _get_sessions()
    if not sessions:
        logger.warning("[UNIVERSAL] Нет сессий для валидации, пропускаем")
        return {**parsed, "valid": True}

    session_path = os.path.join(SESSION_FOLDER, random.choice(sessions))
    api_id, api_hash = _random_creds()

    client = None
    try:
        client = TelegramClient(session_path, api_id, api_hash,
                                system_version='4.16.30-vxCUSTOM')

        try:
            await asyncio.wait_for(client.connect(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("[UNIVERSAL] validate_link: connect timeout")
            return {**parsed, "valid": True}

        try:
            authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("[UNIVERSAL] validate_link: is_user_authorized timeout")
            return {**parsed, "valid": True}

        if not authorized:
            return {**parsed, "valid": True}  # сессия протухла — пропускаем

        uname = parsed["username"]
        try:
            entity = await asyncio.wait_for(client.get_entity(uname), timeout=10)
        except asyncio.TimeoutError:
            logger.warning(f"[UNIVERSAL] get_entity timeout для *@{uname}*")
            return {**parsed, "valid": True}
        except (UsernameNotOccupiedError, UsernameInvalidError):
            return {**parsed, "valid": False, "error": f"*@{uname}* не существует"}
        except ChannelPrivateError:
            return {**parsed, "valid": False, "error": "Канал приватный"}
        except Exception as e:
            logger.warning(f"[UNIVERSAL] get_entity error: {e}")
            return {**parsed, "valid": True}  # при ошибке не блокируем

        # Для сообщения — проверяем что оно существует
        if parsed["type"] == TYPE_MESSAGE and parsed["message_id"]:
            try:
                msgs = await asyncio.wait_for(
                    client.get_messages(entity, ids=[parsed["message_id"]]), timeout=10
                )
                if not msgs or msgs[0] is None:
                    return {**parsed, "valid": False,
                            "error": f"Сообщение #{parsed['message_id']} не найдено"}
            except asyncio.TimeoutError:
                logger.warning("[UNIVERSAL] get_messages timeout")
            except Exception as e:
                logger.warning(f"[UNIVERSAL] get_messages error: {e}")

        return {**parsed, "valid": True}

    except Exception as e:
        logger.warning(f"[UNIVERSAL] validate error: {e}")
        return {**parsed, "valid": True}
    finally:
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=5)
            except Exception:
                pass


# ─── Запуск всех методов ──────────────────────────────────────────────────────

async def run_universal(parsed: dict, tida_text: str, user: int, username: str,
                        status_msg_id: int, bot_instance, cd_state: dict = None):
    """
    Запускает все подходящие методы последовательно в рандомном порядке.
    Обновляет status_msg_id по ходу выполнения.
    cd_state = {
        "user": uid, "admins": [...], "no_kd": [...],
        "botnet": last_used_botnet_dict, "botnet2": ..., ...
    }
    """
    from botnet_snos import main as botnet_main
    from botnet_snos_premium import main2 as botnet_main2
    from aureport_snos import main_aureport
    from tida_snos import main_tida
    from channel_snos import main_channel_snos
    from dsa_snos import main_dsa_snos
    from bot_snos import main_bot_snos

    link_type = parsed["type"]
    norm = parsed["normalized"]
    uname = parsed.get("username")
    mid = parsed.get("message_id")

    # DSA defaults
    dsa_reason = "scam"
    dsa_sub = "None"
    dsa_text = tida_text or "This account is involved in scam or spam activity."

    # Длительности КД в минутах (совпадают с main.py)
    CD_DURATIONS = {
        "botnet": 5, "botnet2": 30, "bot_snos": 60,
        "channel": 30, "aureport": 30, "tida": 30, "dsa": 60,
    }

    def _check_cd(cd_key: str):
        """Возвращает timedelta остатка КД или None если КД нет."""
        if not cd_state or not cd_key:
            return None
        uid = cd_state.get("user")
        if uid in cd_state.get("admins", []) or uid in cd_state.get("no_kd", []):
            return None
        d = cd_state.get(cd_key)
        if not isinstance(d, dict) or uid not in d:
            return None
        duration = timedelta(minutes=CD_DURATIONS.get(cd_key, 30))
        elapsed = now_msk() - d[uid]
        remaining = duration - elapsed
        return remaining if remaining.total_seconds() > 0 else None

    def _set_cd(cd_key: str):
        """Ставит КД для текущего пользователя."""
        if not cd_state or not cd_key:
            return
        uid = cd_state.get("user")
        d = cd_state.get(cd_key)
        if isinstance(d, dict) and uid:
            d[uid] = now_msk()

    # Определяем набор методов — 3-tuple: (label, factory, cd_key)
    tasks_info = []

    _nb = bot_instance  # notify_bot для sub-методов

    if link_type == TYPE_MESSAGE:
        tasks_info = [
            ("🕸 Ботнет",      lambda: botnet_main(uname, mid, user, username, norm, silent=True, notify_bot=_nb),  "botnet"),
            ("👑 Ботнет Прем", lambda: botnet_main2(uname, mid, user, username, norm, silent=True), "botnet2"),
            ("🔍 AU Report",   lambda: main_aureport(norm, user, username, silent=True, notify_bot=_nb),             "aureport"),
            ("🎵 TIDA",        lambda: main_tida(norm, dsa_text, user, username, silent=True, notify_bot=_nb),       "tida"),
            ("📢 Канал",       lambda: main_channel_snos(uname, "spam", user, username, mid, silent=True, notify_bot=_nb), "channel"),
            ("🇪🇺 DSA",        lambda: main_dsa_snos(norm, user, username, dsa_reason, dsa_sub, dsa_text, silent=True, _bot=_nb), "dsa"),
        ]

    elif link_type == TYPE_INVITE:
        tasks_info = [
            ("🔍 AU Report",   lambda: main_aureport(norm, user, username, silent=True, notify_bot=_nb), "aureport"),
            ("🎵 TIDA",        lambda: main_tida(norm, dsa_text, user, username, silent=True, notify_bot=_nb), "tida"),
        ]

    elif link_type == TYPE_BOT:
        tasks_info = [
            ("🤖 Бот-метод",   lambda: main_bot_snos(f"*@{uname}*", "personal", user, username, norm, silent=True, notify_bot=_nb), "bot_snos"),
            ("🇪🇺 DSA",        lambda: main_dsa_snos(norm, user, username, dsa_reason, dsa_sub, dsa_text, silent=True, _bot=_nb), "dsa"),
            ("🔍 AU Report",   lambda: main_aureport(norm, user, username, silent=True, notify_bot=_nb), "aureport"),
            ("🎵 TIDA",        lambda: main_tida(norm, dsa_text, user, username, silent=True, notify_bot=_nb), "tida"),
        ]

    elif link_type == TYPE_USER_CHANNEL:
        tasks_info = [
            ("🇪🇺 DSA",        lambda: main_dsa_snos(norm, user, username, dsa_reason, dsa_sub, dsa_text, silent=True, _bot=_nb), "dsa"),
            ("🔍 AU Report",   lambda: main_aureport(norm, user, username, silent=True, notify_bot=_nb), "aureport"),
            ("🎵 TIDA",        lambda: main_tida(norm, dsa_text, user, username, silent=True, notify_bot=_nb), "tida"),
        ]

    import time as _time

    total = len(tasks_info)
    results = {}        # label -> "✅" | "❌" | "⏩ КД Xм"
    results_data = {}   # label -> (suc, tot)
    start_ts = _time.monotonic()

    BAR_LEN = 10

    def _bar(pct: int) -> str:
        filled = round(BAR_LEN * pct / 100)
        return "[" + "▓" * filled + "▒" * (BAR_LEN - filled) + "]"

    def _eta(done: int) -> str:
        if done == 0:
            return ""
        elapsed = _time.monotonic() - start_ts
        per_task = elapsed / done
        remaining_sec = int(per_task * (total - done))
        if remaining_sec < 60:
            return f"~{remaining_sec} сек"
        return f"~{remaining_sec // 60} мин {remaining_sec % 60} сек"

    def _status_text() -> str:
        done = sum(1 for v in results.values() if v != "⏳")
        pct = round(done / total * 100) if total else 100
        lines = [f"⚙️ *Универсальный метод*\n{norm}\n"]
        if done < total:
            eta = _eta(done)
            eta_str = f" — {eta}" if eta else ""
            lines.append(f"{_bar(pct)} *{pct}%*{eta_str}\n")
        for label, _, _ in tasks_info:
            mark = results.get(label, "⏳")
            rd = results_data.get(label)
            stat = f" {rd[0]}/{rd[1]}" if rd else ""
            lines.append(f"{mark} {label}{stat}")
        ok = sum(1 for v in results.values() if v == "✅")
        fail = sum(1 for v in results.values() if v == "❌")
        if done == total:
            lines.append(f"\n{_bar(100)} *100%*")
            lines.append(f"✅ *{ok}/{total}* успешно, ❌ *{fail}* ошибок")
        return "\n".join(lines)

    async def _update():
        try:
            await bot_instance.edit_message_text(
                _status_text(), user, status_msg_id, parse_mode="Markdown")
        except Exception:
            pass

    async def _run_one(label: str, factory, cd_key: str):
        # Проверяем КД перед запуском
        remaining = _check_cd(cd_key)
        if remaining:
            total_sec = int(remaining.total_seconds())
            mins = total_sec // 60
            secs = total_sec % 60
            time_str = f"{mins}м {secs}с" if secs else f"{mins}м"
            results[label] = f"❌ КД {time_str}"
            await _update()
            return

        try:
            ret = await factory()
            results[label] = "✅"
            if isinstance(ret, tuple) and len(ret) == 2:
                results_data[label] = ret
            _set_cd(cd_key)
        except Exception as e:
            logger.warning(f"[UNIVERSAL] {label} error: {e}")
            results[label] = "❌"
        await _update()

    # Лок per-user — не даём одному пользователю запустить дважды
    _lock = _get_user_lock(user)
    if _lock.locked():
        try:
            await bot_instance.edit_message_text(
                "⏳ *Универсальный метод уже запущен.*\n"
                "Подожди пока он завершится.",
                user, status_msg_id, parse_mode="Markdown")
        except Exception:
            pass
        return

    async with _lock:
        # Начальное состояние
        await _update()

        # Запуск последовательно в рандомном порядке
        shuffled = random.sample(tasks_info, len(tasks_info))
        for label, factory, cd_key in shuffled:
            await _run_one(label, factory, cd_key)

    # ─── Единый итоговый отчёт ────────────────────────────────────────────────
    now_str = now_msk().strftime("%d.%m.%Y %H:%M:%S")
    norm_escaped = norm.replace('_', '\\_')

    lines_user = [f"🌐 *Универсальный метод завершён!*\n\n🎯 *Цель:* {norm_escaped}\n🕐 *Время:* {now_str}\n"]
    for label, _, _ in tasks_info:
        mark = results.get(label, "❌")
        rd = results_data.get(label)
        stat = f" {rd[0]}/{rd[1]}" if rd else ""
        lines_user.append(f"{mark} {label}{stat}")
    caption_user = "\n".join(lines_user)

    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "скрыт" if _is_hid else str(user)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    lines_log = [f"🌐 *Универсальный метод*\n\n🎯 *Цель:* {norm_escaped}\n👤 *Пользователь:* {_log_uid} (*@{_log_uname}*)\n🕐 *Время:* {now_str}\n"]
    for label, _, _ in tasks_info:
        mark = results.get(label, "❌")
        rd = results_data.get(label)
        stat = f" {rd[0]}/{rd[1]}" if rd else ""
        lines_log.append(f"{mark} {label}{stat}")
    caption_log = "\n".join(lines_log)

    try:
        await bot_instance.send_message(user, caption_user, parse_mode="Markdown",
                                        reply_markup=keyboards.main_menu)
    except Exception as e:
        logger.error(f"[UNIVERSAL] Ошибка отправки отчёта пользователю: {e}")

    try:
        _lb = main_bot or bot_instance
        await _lb.send_message(bot_logs, caption_log, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"[UNIVERSAL] Ошибка отправки лога: {e}")
