"""
Brown V2 | monitor_snos.py
Мониторинг сноса целей через Telethon.
Проверка каждые 10 минут, уведомление при сносе.
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Optional

from telethon import TelegramClient
from telethon.errors import (
    UsernameNotOccupiedError, UsernameInvalidError,
    ChannelPrivateError, UserDeactivatedError, UserDeactivatedBanError,
    InviteHashExpiredError, InviteHashInvalidError,
    FloodWaitError, RPCError
)
from telethon.tl.types import Channel, Chat, User

import config
from utils import now_msk

logger = logging.getLogger(__name__)

# ─── Пул сессий ───────────────────────────────────────────────────────────────
# session_path → список monitor_id которые она обслуживает
_session_load: dict[str, list[int]] = {}

MONITOR_INTERVAL = 10 * 60  # 10 минут

# Максимум 5 параллельных проверок чтобы не перегружать сессии
_check_semaphore = asyncio.Semaphore(5)

_bot = None
_bot_logs = None

def set_monitor_bot(b, logs_chat: int):
    global _bot, _bot_logs
    _bot = b
    _bot_logs = logs_chat


def _get_all_sessions() -> list[str]:
    """Собирает .session файлы ТОЛЬКО из папки sessions/ (основной ботнет).
    TIDA и AU сессии не используем — они могут быть заняты другими методами."""
    result = []
    folder = "sessions"
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.endswith(".session"):
                result.append(os.path.join(folder, f.replace(".session", "")))
    return result


async def _is_session_valid(session_path: str) -> bool:
    """Быстро проверяет что сессия авторизована. Таймаут 5с."""
    try:
        client = TelegramClient(
            session_path, int(config.TIDA_API_ID), config.TIDA_API_HASH,
            system_version="4.16.30-vxCUSTOM"
        )
        await asyncio.wait_for(client.connect(), timeout=5)
        ok = await asyncio.wait_for(client.is_user_authorized(), timeout=3)
        await client.disconnect()
        return ok
    except Exception:
        try:
            await client.disconnect()
        except Exception:
            pass
        return False


async def _pick_session(monitor_id: int) -> Optional[str]:
    """
    Выбирает сессию с минимальной нагрузкой.
    Если все заняты — берёт занятую с наименьшей нагрузкой.
    """
    all_sessions = _get_all_sessions()
    if not all_sessions:
        return None

    random.shuffle(all_sessions)

    # Сортируем по нагрузке (меньше = лучше)
    def load(s):
        return len(_session_load.get(s, []))

    all_sessions.sort(key=load)

    # Пробуем найти валидную начиная с наименее загруженной
    for s in all_sessions:
        if await _is_session_valid(s):
            _session_load.setdefault(s, []).append(monitor_id)
            return s

    return None


def _release_session(session_path: str, monitor_id: int):
    """Освобождает monitor_id из сессии."""
    if session_path in _session_load:
        try:
            _session_load[session_path].remove(monitor_id)
        except ValueError:
            pass


# ─── Логика проверки целей ────────────────────────────────────────────────────

def _parse_target(target: str) -> dict:
    """
    Разбирает ссылку и возвращает тип цели:
    {
        type: private_channel | bot | channel | channel_msg | account_msg,
        username: str | None,
        invite_hash: str | None,
        msg_id: int | None,
        raw: str
    }
    """
    info = {"type": "channel", "username": None, "invite_hash": None, "msg_id": None, "raw": target}

    clean = target.strip()

    # Приватный канал
    if "joinchat/" in clean or clean.startswith("https://t.me/+") or clean.startswith("t.me/+"):
        info["type"] = "private_channel"
        # Извлекаем хеш
        for prefix in ["https://t.me/+", "t.me/+", "https://t.me/joinchat/", "t.me/joinchat/"]:
            if clean.startswith(prefix):
                info["invite_hash"] = clean[len(prefix):].split("?")[0]
                break
        return info

    # Нормализуем
    for prefix in ["https://t.me/", "http://t.me/", "t.me/"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    if clean.startswith("@"):
        clean = clean[1:]

    parts = clean.rstrip("/").split("?")[0].split("/")
    username = parts[0]
    info["username"] = username

    if len(parts) >= 2 and parts[-1].isdigit():
        info["msg_id"] = int(parts[-1])
        # Определяем тип — channel_msg или account_msg позже по entity
        info["type"] = "channel_msg"
    else:
        # Пока channel, уточним по entity
        info["type"] = "channel"

    return info


async def check_target(target: str, session_path: str) -> dict:
    """
    Проверяет цель и возвращает:
    {
        alive: bool,
        reason: str,   # описание что случилось
        status: str    # "alive" | "dead" | "msg_deleted" | "error"
    }
    """
    info = _parse_target(target)

    try:
        client = TelegramClient(
            session_path, int(config.TIDA_API_ID), config.TIDA_API_HASH,
            system_version="4.16.30-vxCUSTOM"
        )
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"alive": True, "reason": "session_invalid", "status": "error"}

        try:
            # ── Приватный канал ────────────────────────────────────────────────
            if info["type"] == "private_channel":
                try:
                    from telethon.tl.functions.messages import CheckChatInviteRequest
                    await client(CheckChatInviteRequest(hash=info["invite_hash"]))
                    await client.disconnect()
                    return {"alive": True, "reason": "", "status": "alive"}
                except (InviteHashExpiredError, InviteHashInvalidError):
                    await client.disconnect()
                    return {"alive": False, "reason": "Приватная ссылка недействительна", "status": "dead"}

            # ── Цель с username ────────────────────────────────────────────────
            username = info["username"]
            if not username:
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "error"}

            try:
                entity = await client.get_entity(username)
            except (UsernameNotOccupiedError, UsernameInvalidError):
                await client.disconnect()
                return {"alive": False, "reason": "Username не существует", "status": "dead"}
            except (UserDeactivatedError, UserDeactivatedBanError):
                await client.disconnect()
                return {"alive": False, "reason": "Аккаунт удалён / заморожен", "status": "dead"}
            except ChannelPrivateError:
                # Канал приватный или у сессии нет доступа — не значит что удалён
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "error"}
            except RPCError as e:
                err = str(e).lower()
                if "deactivated" in err or "deleted" in err or "banned" in err:
                    await client.disconnect()
                    return {"alive": False, "reason": f"Удалён/заблокирован: {e}", "status": "dead"}
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "error"}

            # Уточняем тип если это аккаунт + сообщение
            if info["msg_id"] and isinstance(entity, User):
                info["type"] = "account_msg"

            # ── Бот ────────────────────────────────────────────────────────────
            if isinstance(entity, User) and entity.bot:
                if entity.deleted or getattr(entity, 'deactivated', False):
                    await client.disconnect()
                    return {"alive": False, "reason": "Бот удалён / заморожен", "status": "dead"}
                # Дополнительно — пробуем отправить /start и проверяем нет ли ошибки
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "alive"}

            # ── Аккаунт (не бот) ───────────────────────────────────────────────
            if isinstance(entity, User) and not entity.bot:
                if entity.deleted or getattr(entity, 'deactivated', False):
                    await client.disconnect()
                    return {"alive": False, "reason": "Аккаунт удалён", "status": "dead"}
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "alive"}

            # ── Канал/чат с сообщением ─────────────────────────────────────────
            if info["msg_id"] and info["type"] in ("channel_msg", "account_msg"):
                try:
                    msg = await client.get_messages(entity, ids=info["msg_id"])
                    if msg is None:
                        await client.disconnect()
                        return {"alive": False, "reason": "Сообщение удалено", "status": "msg_deleted"}
                except FloodWaitError as e:
                    await client.disconnect()
                    logger.warning(f"[MONITOR] FloodWait {e.seconds}s при получении сообщения {target}")
                    return {"alive": True, "reason": "", "status": "error"}
                except Exception as e:
                    await client.disconnect()
                    logger.warning(f"[MONITOR] Ошибка get_messages {target}: {e}")
                    return {"alive": True, "reason": "", "status": "error"}
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "alive"}

            # ── Просто канал/чат ───────────────────────────────────────────────
            if isinstance(entity, (Channel, Chat)):
                if getattr(entity, 'deactivated', False):
                    await client.disconnect()
                    return {"alive": False, "reason": "Канал/чат удалён", "status": "dead"}
                await client.disconnect()
                return {"alive": True, "reason": "", "status": "alive"}

            await client.disconnect()
            return {"alive": True, "reason": "", "status": "alive"}

        except FloodWaitError as e:
            await client.disconnect()
            logger.warning(f"[MONITOR] FloodWait {e.seconds}s для {session_path}")
            return {"alive": True, "reason": "", "status": "error"}
        except Exception as e:
            logger.warning(f"[MONITOR] Ошибка проверки {target}: {e}")
            await client.disconnect()
            return {"alive": True, "reason": "", "status": "error"}

    except Exception as e:
        logger.error(f"[MONITOR] Ошибка подключения {session_path}: {e}")
        return {"alive": True, "reason": "", "status": "error"}


# ─── Фоновый цикл мониторинга ─────────────────────────────────────────────────

async def monitor_loop():
    """Основной цикл — запускается при старте бота."""
    import db
    logger.info("[MONITOR] 🚀 Цикл мониторинга запущен")
    # Ждём 60 секунд после старта — даём боту и зеркалам полностью подняться
    await asyncio.sleep(60)

    while True:
        try:
            await _run_checks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[MONITOR] Ошибка цикла: {e}")
        await asyncio.sleep(MONITOR_INTERVAL)


async def _run_checks():
    """Один проход — проверяет все активные мониторы."""
    import db

    monitors = await db.get_active_monitors()
    if not monitors:
        return

    logger.info(f"[MONITOR] 🔍 Проверяем {len(monitors)} целей")

    now = now_msk()

    tasks = []
    for m in monitors:
        # Проверяем не истёк ли срок
        expires_at = m["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.strptime(expires_at[:19], "%Y-%m-%d %H:%M:%S")
        if now > expires_at:
            await db.deactivate_monitor(m["id"])
            continue

        tasks.append(_check_one(m))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _check_one(monitor: dict):
    """Проверяет одну цель и уведомляет при изменении статуса."""
    async with _check_semaphore:
        import db

        monitor_id = monitor["id"]
        target = monitor["target"]
        user_id = monitor["user_id"]
        prev_status = monitor["status"]

        session_path = await _pick_session(monitor_id)
        if not session_path:
            logger.warning(f"[MONITOR] Нет доступных сессий для {target}")
            return

        try:
            result = await check_target(target, session_path)
        finally:
            _release_session(session_path, monitor_id)

        if result["status"] == "error":
            # Ошибка сети/сессии — не считаем за страйк, игнорируем
            return

        new_alive = result["alive"]
        new_status = "alive" if new_alive else "dead"

        await db.update_monitor_check(monitor_id, new_status)

        if new_status == "dead" and not monitor.get("notified"):
            strikes = await db.increment_monitor_dead_strikes(monitor_id)
            if strikes >= 2:
                # Два подряд dead — теперь уведомляем
                await db.mark_monitor_notified(monitor_id)
                await _notify_user(user_id, target, result["reason"], result["status"])
                await db.deactivate_monitor(monitor_id)
            else:
                logger.info(f"[MONITOR] {target} — dead strike {strikes}/2, ждём подтверждения")
        elif new_status == "alive":
            await db.reset_monitor_dead_strikes(monitor_id)
            if not monitor.get("notify_silent"):
                await _notify_user_alive(user_id, target, monitor_id)


async def _get_user_bot(user_id: int):
    """Возвращает бот юзера: его зеркало → любое живое зеркало → основной бот."""
    try:
        import db as _db
        from mirror_manager import _mirror_bots
        token = await _db.get_user_mirror(user_id)
        if token and token in _mirror_bots:
            return _mirror_bots[token]
        if _mirror_bots:
            return next(iter(_mirror_bots.values()))
    except Exception:
        pass
    return _bot


async def _notify_user_alive(user_id: int, target: str, monitor_id: int):
    """Периодическое уведомление — цель жива."""
    if not _bot:
        return
    from aiogram import types as tg_types
    markup = tg_types.InlineKeyboardMarkup(row_width=1)
    markup.add(tg_types.InlineKeyboardButton(
        "🔕 Отключить до сноса", callback_data=f'monitor_mute_{monitor_id}'
    ))
    send_bot = await _get_user_bot(user_id)
    try:
        await send_bot.send_message(
            user_id,
            f"🔍 *Мониторинг BR V2*\n\n"
            f"🟢 *Цель жива*\n\n"
            f"🎯 *Цель:* {target}\n"
            f"🕐 *Следующая проверка через 10 минут*",
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"[MONITOR] Ошибка alive-уведомления {user_id}: {e}")


async def _notify_user(user_id: int, target: str, reason: str, status: str):
    """Отправляет уведомление пользователю о сносе."""
    if not _bot:
        return

    status_emoji = {
        "dead": "🔴 *Цель снесена!*",
        "msg_deleted": "🔴 *Сообщение удалено!*",
    }.get(status, "🔴 *Цель недоступна!*")

    target_escaped = target.replace('_', '\\_').replace('.', '\\.')
    reason_text = f"\n*└─ Причина:* {reason}" if reason else ""

    send_bot = await _get_user_bot(user_id)
    try:
        await send_bot.send_message(
            user_id,
            f"🔍 *Мониторинг BR V2*\n\n"
            f"{status_emoji}\n\n"
            f"🎯 *Цель:* {target}"
            f"{reason_text}\n\n"
            f"🕐 *Время:* {now_msk().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"[MONITOR] Ошибка уведомления {user_id}: {e}")

    # Лог
    try:
        if _bot_logs:
            import db as _db_mod
            _is_hid = await _db_mod.get_is_hidden(user_id)
            _log_uid = "скрыт" if _is_hid else str(user_id)
            await _bot.send_message(
                _bot_logs,
                f"🔍 *Монитор:* {_log_uid} — цель {target} снесена",
                parse_mode="Markdown"
            )
    except Exception:
        pass

# ─── Мониторинг Telegraph-статей ─────────────────────────────────────────────
# Формат: {url: str, user_id: int, added_at: datetime}
_telegraph_monitors: list[dict] = []
_telegraph_lock = asyncio.Lock()


def telegraph_monitor_add(url: str, user_id: int):
    """Добавляет Telegraph-статью в мониторинг."""
    # Убираем дубли по url+user_id
    for m in _telegraph_monitors:
        if m["url"] == url and m["user_id"] == user_id:
            return
    _telegraph_monitors.append({
        "url": url,
        "user_id": user_id,
        "added_at": now_msk(),
        "notified": False,
    })
    logger.info(f"[MONITOR-TELEGRAPH] Добавлена {url} для {user_id}")


def telegraph_monitor_remove(url: str, user_id: int):
    """Удаляет Telegraph-статью из мониторинга."""
    global _telegraph_monitors
    _telegraph_monitors = [
        m for m in _telegraph_monitors
        if not (m["url"] == url and m["user_id"] == user_id)
    ]


async def _check_telegraph_url(url: str) -> int:
    """Проверяет статью по HTTP. Возвращает HTTP статус."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True
            ) as resp:
                return resp.status
    except Exception as e:
        logger.error(f"[MONITOR-TELEGRAPH] HTTP error {url}: {e}")
        return 0


async def _telegraph_monitor_loop():
    """Цикл проверки Telegraph-статей каждые 10 минут."""
    while True:
        await asyncio.sleep(10 * 60)  # 10 минут
        if not _telegraph_monitors:
            continue

        async with _telegraph_lock:
            to_remove = []
            for m in list(_telegraph_monitors):
                if m.get("notified"):
                    to_remove.append(m)
                    continue

                status = await _check_telegraph_url(m["url"])
                logger.info(f"[MONITOR-TELEGRAPH] {m['url']} → {status}")

                if status == 404:
                    # Статья удалена — уведомляем
                    m["notified"] = True
                    to_remove.append(m)
                    await _notify_telegraph(m["user_id"], m["url"])

            for m in to_remove:
                try:
                    _telegraph_monitors.remove(m)
                except ValueError:
                    pass


async def _notify_telegraph(user_id: int, url: str):
    """Уведомляет пользователя об удалении Telegraph-статьи."""
    if not _bot:
        return

    try:
        await _bot.send_message(
            user_id,
            f"🔍 *Мониторинг BR V2*\n\n"
            f"🔴 *Telegraph статья удалена!*\n\n"
            f"📄 *Статья:* {url}\n"
            f"🕐 *Время:* {now_msk().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        logger.info(f"[MONITOR-TELEGRAPH] Уведомил {user_id} об удалении {url}")
    except Exception as e:
        logger.error(f"[MONITOR-TELEGRAPH] Ошибка уведомления {user_id}: {e}")

    try:
        if _bot_logs:
            import db as _db_mod
            _is_hid = await _db_mod.get_is_hidden(user_id)
            _log_uid = "скрыт" if _is_hid else str(user_id)
            await _bot.send_message(
                _bot_logs,
                f"📄 *Telegraph удалена:* {url}\n👤 {_log_uid}",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
    except Exception:
        pass
