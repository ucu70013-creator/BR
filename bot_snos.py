# coding: utf-8
"""
Brown V2 | bot-method
"""

import os
import asyncio
import random
import logging
from telethon import TelegramClient, functions, types
from telethon.errors import FloodWaitError
import config
from config import bot_logs
import keyboards
from utils import now_msk, ProgressBar, esc_md

logger = logging.getLogger(__name__)

# ─── Конфиги причин для бот-метода ───────────────────────────────────────────
BOT_REASONS = {
    "personal": {
        "label": "🔐 Персональные данные",
        "text": "Данный бот распространяет персональные данные пользователей, включая ИНН, СНИЛС, паспортные данные, адреса проживания и номера телефонов. Прошу провести проверку и незамедлительно заблокировать этого бота.",
        "reason": types.InputReportReasonPersonalDetails(),
    },
    "drugs": {
        "label": "💊 Наркотики",
        "text": "Drug use promotion - mephedrone. Bot openly writes about injecting mephedrone. Violates Telegram rules against illegal drugs. Delete the bot.",
        "reason": types.InputReportReasonIllegalDrugs(),
    },
    "other": {
        "label": "📝 Прочее",
        "text": "Данный бот распространяет персональные данные пользователей, включая ИНН, СНИЛС, паспортные данные, адреса проживания и номера телефонов. Прошу провести проверку и незамедлительно заблокировать этого бота.",
        "reason": types.InputReportReasonPersonalDetails(),
    },
}

REPORT_TEXT = BOT_REASONS["personal"]["text"]
REPORT_REASON = BOT_REASONS["personal"]["reason"]

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

bot = None
main_bot = None
session_folder = 'sessions'
prem_session_folder = 'prem_sessions'
os.makedirs(session_folder, exist_ok=True)
os.makedirs(prem_session_folder, exist_ok=True)

LOG_FOLDER = "logs"
os.makedirs(LOG_FOLDER, exist_ok=True)

# Ключевой текст для определения "своих" ботов (КД 5 минут)
FAST_KD_KEYWORD = "Пожалуйста, решите капчу"

AUREPORT_SESSION_FOLDER = 'aureport_sessions'


async def detect_bot_type(bot_username: str) -> bool:
    """
    Отправляет /start боту и проверяет есть ли в ответе FAST_KD_KEYWORD.
    Возвращает True если это "свой" бот (КД 5 минут).
    Использует одну сессию из aureport_sessions/.
    """
    if not os.path.exists(AUREPORT_SESSION_FOLDER):
        return False

    sessions = [
        os.path.join(AUREPORT_SESSION_FOLDER, f.replace('.session', ''))
        for f in os.listdir(AUREPORT_SESSION_FOLDER)
        if f.endswith('.session')
    ]
    if not sessions:
        return False

    session_path = random.choice(sessions)
    creds = random.choice(API)
    api_id, api_hash = creds.split(':', 1)

    client = TelegramClient(session_path, int(api_id), api_hash,
                            system_version='4.16.30-vxCUSTOM')
    try:
        await asyncio.wait_for(client.connect(), timeout=8)
        if not await client.is_user_authorized():
            await client.disconnect()
            return False

        # Получаем entity бота
        entity = await client.get_entity(bot_username)

        # Отправляем /start
        await client.send_message(entity, '/start')
        await asyncio.sleep(2)

        # Читаем последние сообщения от бота
        messages = await client.get_messages(entity, limit=3)
        for msg in messages:
            if msg.out:
                continue
            text = msg.text or ''
            if FAST_KD_KEYWORD.lower() in text.lower():
                await client.disconnect()
                print(f'[BOT-SNOS] detect_bot_type: FAST KD detected for {bot_username}', flush=True)
                return True

        await client.disconnect()
        return False

    except Exception as e:
        print(f'[BOT-SNOS] detect_bot_type error: {e}', flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return False


def set_bot_snos(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


def _get_sessions():
    sessions = []
    for folder in [session_folder, prem_session_folder]:
        if os.path.exists(folder):
            sessions += [
                os.path.join(folder, f.replace('.session', ''))
                for f in os.listdir(folder)
                if f.endswith('.session')
            ]
    return sessions


def _load_proxies():
    for fname in ["proxies.txt", "proxy_input.txt"]:
        if os.path.exists(fname):
            with open(fname, "r") as f:
                lines = [l.strip() for l in f if l.strip() and ":" in l]
            if lines:
                return lines
    return []


def _parse_proxy(proxy_str):
    try:
        import socks
        proxy_str = proxy_str.replace("socks5://", "").replace("socks4://", "").replace("http://", "")
        if "@" in proxy_str:
            # формат: user:pass@host:port
            host, port = hostport.rsplit(":", 1)
            if len(parts) >= 4:
                host, port, user, password = parts[0], parts[1], parts[2], ":".join(parts[3:])
            elif len(parts) == 2:
                host, port = parts
                user, password = None, None
            else:
                return None
        if user and password:
            return (socks.SOCKS5, host, int(port), True, user, password)
        return (socks.SOCKS5, host, int(port))
    except Exception:
        return None


def format_log_line(session, target, status):
    now = now_msk().strftime("%H:%M:%S")
    return f"[{now}] {os.path.basename(session)}.session -> {target} - [{status}]"


async def _attack_with_session(session_path, idx, bot_username, proxies, reason_key="personal"):
    session_name = os.path.basename(session_path)

    proxy = None
    if proxies:
        proxy = _parse_proxy(proxies[idx % len(proxies)])

    creds = random.choice(API)
    api_id, api_hash = creds.split(":", 1)

    try:
        client = TelegramClient(
            session_path, int(api_id), api_hash,
            proxy=proxy, system_version='4.16.30-vxCUSTOM'
        )
    except Exception as e:
        logger.warning(f"[BOT-SNOS] [{session_name}] failed to open session: {e}")
        return 0
    try:
        connected = False
        for db_attempt in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                connected = True
                break
            except (asyncio.TimeoutError, OSError):
                if db_attempt == 2:
                    logger.warning(f"[BOT-SNOS] [{session_name}] ОШИБКА СОЕДИНЕНИЯ")
                    return 0
                await asyncio.sleep(1)
            except Exception as e:
                if "database is locked" in str(e) and db_attempt < 2:
                    await asyncio.sleep(random.uniform(1, 2))
                else:
                    raise
        if not connected:
            return 0

        if not await client.is_user_authorized():
            logger.warning(f"[BOT-SNOS] [{session_name}] not authorized")
            await client.disconnect()
            return 0

        try:
            entity = await client.get_entity(bot_username)
        except Exception as e:
            logger.warning(f"[BOT-SNOS] [{session_name}] entity error: {e}")
            await client.disconnect()
            return 0

        try:
            reason_cfg = BOT_REASONS.get(reason_key, BOT_REASONS["personal"])
            await client(functions.account.ReportPeerRequest(
                peer=entity,
                reason=reason_cfg["reason"],
                message=reason_cfg["text"]
            ))
            logger.info(f"[BOT-SNOS] [{session_name}] OK")
            print(f"[BOT-SNOS] [{session_name}] OK", flush=True)
            await client.disconnect()
            return 1
        except FloodWaitError as e:
            logger.warning(f"[BOT-SNOS] [{session_name}] flood {e.seconds}s")
            print(f"[BOT-SNOS] [{session_name}] FLOOD {e.seconds}s", flush=True)
            await asyncio.sleep(min(e.seconds, 10))
            await client.disconnect()
            return 0
        except Exception as e:
            logger.warning(f"[BOT-SNOS] [{session_name}] err: {str(e)[:60]}")
            print(f"[BOT-SNOS] [{session_name}] ERR: {str(e)[:100]}", flush=True)
            await client.disconnect()
            return 0

    except Exception as e:
        logger.warning(f"[BOT-SNOS] [{session_name}] {str(e)[:60]}")
        print(f"[BOT-SNOS] [{session_name}] OUTER ERR: {str(e)[:100]}", flush=True)
        return 0
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass


async def main_bot_snos(bot_username, reason_key, user, username, bot_url, _log_user=None, silent: bool = False, notify_bot=None):
    from aiogram import types as aiogram_types
    _notify = notify_bot or bot

    # Проверка белого списка
    try:
        import db as db_module
        check_target = bot_username.strip().lstrip('@').lower()
        if await db_module.is_target_whitelisted(check_target):
            await _notify.send_message(
                user,
                "*\u26d4 \u0426\u0435\u043b\u044c \u0432 \u0431\u0435\u043b\u043e\u043c \u0441\u043f\u0438\u0441\u043a\u0435!*\n"
                "*\u0416\u0430\u043b\u043e\u0431\u044b \u043d\u0430 \u044d\u0442\u0443 \u0446\u0435\u043b\u044c \u0437\u0430\u043f\u0440\u0435\u0449\u0435\u043d\u044b.*",
                parse_mode="Markdown",
                reply_markup=keyboards.main_menu
            )
            try:
                await main_bot.send_message(
                    bot_logs,
                    "*\u26a0 \u041f\u043e\u043f\u044b\u0442\u043a\u0430 \u0441\u043d\u0435\u0441\u0442\u0438 "
                    "\u0446\u0435\u043b\u044c \u0438\u0437 \u0431\u0435\u043b\u043e\u0433\u043e \u0441\u043f\u0438\u0441\u043a\u0430!*\n"
                    f"*\u0426\u0435\u043b\u044c:* {bot_username}\n"
                    f"*\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c:* {user} (*@{username}*)\n"
                    "*\u041c\u0435\u0442\u043e\u0434:* \u0411\u043e\u0442-\u043c\u0435\u0442\u043e\u0434",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return
    except Exception as wl_e:
        logger.warning(f"[BOT-SNOS] whitelist check error: {wl_e}")

    if "_" in username:
        username = "None"

    sessions = _get_sessions()
    proxies = _load_proxies()
    total = len(sessions)

    logger.info(f"[BOT-SNOS] start | target: {bot_url} | sessions: {total} | proxies: {len(proxies)}")

    # Пачки по 8 — чтобы не было database is locked и массовых таймаутов
    BATCH_SIZE = 8
    results = []
    pb = ProgressBar(_notify, user, total=total, title="🤖 *Бот-метод*", silent=silent)
    await pb.start()
    done_count = 0
    for i in range(0, total, BATCH_SIZE):
        batch = sessions[i:i + BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[_attack_with_session(s, i + j, bot_username, proxies, reason_key)
              for j, s in enumerate(batch)],
            return_exceptions=True
        )
        for r in batch_results:
            results.append(0 if isinstance(r, Exception) else r)
        done_count += len(batch)
        await pb.update(done_count)
        if i + BATCH_SIZE < total:
            await asyncio.sleep(2)
    await pb.finish()
    successful = sum(results)

    logger.info(f"[BOT-SNOS] done: {successful}/{total}")

    from datetime import datetime as _dt
    now_str = now_msk().strftime("%d.%m.%Y %H:%M:%S")
    reason_label = BOT_REASONS.get(reason_key, BOT_REASONS["personal"])["label"]

    log_lines = [
        "Brown V2 log | bot-method",
        "-" * 42,
        f"User: {user} (*@{username}*)",
        f"Target: {bot_url}",
        f"Time: {now_str}",
        "-" * 42,
    ]
    for session, result in zip(sessions, results):
        status = "OK" if result == 1 else "FAIL"
        log_lines.append(format_log_line(session, bot_url, status))
    log_lines += ["-" * 42, f"Success: {successful}", f"Failed: {total - successful}"]

    log_name = f"brown_v2_bot_log_{os.urandom(10).hex()}.txt"
    log_path = os.path.join(LOG_FOLDER, log_name)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "\u0441\u043a\u0440\u044b\u0442" if _is_hid else str(user)
        _log_uname = "\u0441\u043a\u0440\u044b\u0442" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    bot_url_escaped = bot_url.replace('_', '\\_')
    caption_user = (
        f"*\U0001f916 \u0411\u043e\u0442-\u043c\u0435\u0442\u043e\u0434 \u0437\u0430\u0432\u0435\u0440\u0448\u0451\u043d!*\n\n"
        f"*\U0001f3af \u0426\u0435\u043b\u044c:* {bot_url_escaped}\n"
        f"*\U0001f550 \u0412\u0440\u0435\u043c\u044f:* {now_str}\n\n"
        f"*\U0001f7e2 \u0423\u0441\u043f\u0435\u0448\u043d\u043e: {successful}*\n"
        f"*\U0001f534 \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c: {total - successful}*"
    )
    caption_log = (
        f"*\U0001f4c8 bot-method*\n\n"
        f"*\U0001f3af \u0426\u0435\u043b\u044c:* {bot_url_escaped}\n"
        f"*\U0001f550 \u0412\u0440\u0435\u043c\u044f:* {now_str}\n"
        f"\U0001f7e2 {successful} | \U0001f534 {total - successful}\n"
        f"\U0001f464 {_log_uid} (*@{_log_uname}*)"
    )

    if not silent:
        try:
            await _notify.send_document(
                user, aiogram_types.InputFile(log_path),
                caption=caption_user, parse_mode="Markdown",
                reply_markup=keyboards.main_menu
            )
        except Exception as e:
            logger.error(f"[BOT-SNOS] user send error: {e}")
        try:
            await main_bot.send_document(
                bot_logs, aiogram_types.InputFile(log_path),
                caption=caption_log, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"[BOT-SNOS] logs send error: {e}")

    try:
        os.remove(log_path)
    except Exception:
        pass

    return (successful, total)
