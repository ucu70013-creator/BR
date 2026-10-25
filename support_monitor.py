"""
Brown V2 | support_monitor.py
Индивидуальный мониторинг после Снос Сессий.
Триггеры: кол-во аватарок упало, ник изменился, описание изменилось, не в сети 24ч+.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.types import UserStatusOffline, UserStatusLastWeek, UserStatusLastMonth
from telethon.errors import FloodWaitError

import config
from utils import now_msk, esc_md

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 15 * 60   # 15 минут
MAX_DURATION   = 38 * 3600  # максимум 38ч мониторинга

_bot      = None
_bot_logs = None

def set_support_monitor_bot(b, logs_chat: int):
    global _bot, _bot_logs
    _bot      = b
    _bot_logs = logs_chat


# {key: {target, user_id, invoker_username, bot_token, snapshot, started_at}}
_monitors: dict = {}
_lock = asyncio.Lock()


def _get_session() -> Optional[str]:
    folder = "sessions"
    if not os.path.exists(folder):
        return None
    for f in os.listdir(folder):
        if f.endswith(".session"):
            return os.path.join(folder, f.replace(".session", ""))
    return None


async def _snapshot(username: str, session_path: str) -> Optional[dict]:
    client = TelegramClient(
        session_path, int(config.TIDA_API_ID), config.TIDA_API_HASH,
        system_version="4.16.30-vxCUSTOM"
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None

        try:
            entity = await client.get_entity(username)
        except Exception as e:
            logger.warning(f"[SUPP_MON] get_entity {esc_md(username)}: {e}")
            await client.disconnect()
            return None

        # Кол-во аватарок
        photo_count = 0
        try:
            res = await client(GetUserPhotosRequest(
                user_id=entity.id, offset=0, max_id=0, limit=100
            ))
            # photos.photosSlice имеет .count (общее), photos.Photos — нет
            photo_count = getattr(res, 'count', len(getattr(res, 'photos', [])))
        except Exception:
            pass

        # Биография
        bio = ""
        try:
            full = await client(GetFullUserRequest(entity))
            bio = full.full_user.about or ""
        except Exception:
            pass

        # Последний онлайн (UTC → наивный UTC для сравнения)
        last_seen_utc = None
        offline_24h = False
        if isinstance(entity.status, UserStatusOffline):
            ws = entity.status.was_online
            if ws.tzinfo is not None:
                last_seen_utc = ws.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                last_seen_utc = ws
        elif isinstance(entity.status, (UserStatusLastWeek, UserStatusLastMonth)):
            offline_24h = True

        await client.disconnect()
        return {
            "username":      (entity.username or "").lower(),
            "photo_count":   photo_count,
            "bio":           bio,
            "last_seen_utc": last_seen_utc,
            "offline_24h":   offline_24h,
        }

    except FloodWaitError as e:
        logger.warning(f"[SUPP_MON] FloodWait {e.seconds}s for {esc_md(username)}")
        try: await client.disconnect()
        except Exception: pass
        return None
    except Exception as e:
        logger.warning(f"[SUPP_MON] snapshot error {esc_md(username)}: {e}")
        try: await client.disconnect()
        except Exception: pass
        return None


async def add_support_monitor(
    target: str,
    user_id: int,
    invoker_username: str = "None",
    bot_token: str = None,
):
    """Запускает индивидуальный мониторинг цели после Снос Сессий."""
    username = target.lstrip("@").lower()
    session_path = _get_session()
    if not session_path:
        logger.warning("[SUPP_MON] Нет доступных сессий, мониторинг не запущен")
        return

    snap = await _snapshot(username, session_path)
    if not snap:
        logger.warning(f"[SUPP_MON] Не удалось получить снимок для {esc_md(username)}")
        return

    key = f"{user_id}:{esc_md(username)}"
    async with _lock:
        _monitors[key] = {
            "target":            username,
            "user_id":           user_id,
            "invoker_username":  invoker_username,
            "bot_token":         bot_token,
            "snapshot":          snap,
            "started_at":        now_msk(),
        }

    logger.info(f"[SUPP_MON] ✅ Мониторинг запущен: *@{username}* → uid {user_id}")

    # Уведомляем пользователя
    try:
        await _get_user_bot(user_id, bot_token).send_message(
            user_id,
            (
                f"🔍 *Мониторинг запущен*\n\n"
                f"🎯 Цель: *@{username}*\n"
                f"📸 Аватарок: {snap['photo_count']}\n\n"
                f"_Уведомлю при вероятном сносе сессий (до 38ч)._"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


def _get_user_bot(user_id: int, bot_token: str = None):
    try:
        from mirror_manager import _mirror_bots
        if bot_token and bot_token in _mirror_bots:
            return _mirror_bots[bot_token]
    except Exception:
        pass
    return _bot


async def _check_one(key: str, data: dict):
    username  = data["target"]
    user_id   = data["user_id"]
    snap      = data["snapshot"]
    bot_token = data["bot_token"]

    session_path = _get_session()
    if not session_path:
        return

    current = await _snapshot(username, session_path)
    if not current:
        return

    triggers = []

    # Аватарки слетели до нуля
    if snap["photo_count"] > 0 and current["photo_count"] == 0:
        triggers.append(
            f"🖼 Аватарки исчезли: было {snap['photo_count']} → стало 0"
        )

    # Ник изменился
    if snap["username"] and current["username"] and current["username"] != snap["username"]:
        triggers.append(
            f"👤 Ник: *@{snap['username']}* → *@{current['username']}*"
        )

    # Биография изменилась / исчезла
    if snap["bio"] and not current["bio"]:
        triggers.append("📝 Описание профиля исчезло")
    elif snap["bio"] and current["bio"] and current["bio"] != snap["bio"]:
        triggers.append("📝 Описание профиля изменилось")

    # Не в сети 24ч+
    is_offline_24h = current.get("offline_24h", False)
    if not is_offline_24h and current["last_seen_utc"]:
        delta = datetime.utcnow() - current["last_seen_utc"]
        if delta >= timedelta(hours=24):
            is_offline_24h = True
    if is_offline_24h:
        triggers.append("🕐 Не в сети 24ч+")

    if not triggers:
        return

    # Снимаем с мониторинга
    async with _lock:
        _monitors.pop(key, None)

    trigger_text = "\n".join(f"• {t}" for t in triggers)

    # Уведомляем пользователя
    try:
        user_bot = _get_user_bot(user_id, bot_token)
        if user_bot:
            await user_bot.send_message(
                user_id,
                (
                    f"🔪 *Вероятный снос сессий*\n\n"
                    f"🎯 Цель: *@{username}*\n\n"
                    f"{trigger_text}\n\n"
                    f"_Мониторинг завершён._"
                ),
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.warning(f"[SUPP_MON] notify user error: {e}")

    # Лог в канал
    try:
        if _bot and _bot_logs:
            try:
                import db as _db
                _hidden = await _db.get_is_hidden(user_id)
            except Exception:
                _hidden = False

            inv = data.get("invoker_username", str(user_id))
            sender = "@скрыт" if _hidden else f"*@{inv}* {user_id}"

            await _bot.send_message(
                _bot_logs,
                (
                    f"🔪 *Снос Сессий — Вероятный снос*\n"
                    f"👤 {sender}\n"
                    f"🎯 Цель: *@{username}*\n\n"
                    f"{trigger_text}"
                ),
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.warning(f"[SUPP_MON] log error: {e}")


async def support_monitor_loop():
    """Фоновый цикл индивидуального мониторинга Снос Сессий."""
    await asyncio.sleep(60)
    while True:
        try:
            async with _lock:
                items = list(_monitors.items())

            now = now_msk()
            for key, data in items:
                started = data["started_at"]
                if isinstance(started, str):
                    started = datetime.strptime(started[:19], "%Y-%m-%d %H:%M:%S")
                if (now - started).total_seconds() > MAX_DURATION:
                    async with _lock:
                        _monitors.pop(key, None)
                    continue

                await _check_one(key, data)
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[SUPP_MON] loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
