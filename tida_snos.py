"""
Brown V2 | tida_snos.py
TIDA метод — жалобы через @TIDABOT.
Сессии берутся из папки tida_sessions/
Прокси обязательны — берутся из config.TIDA_PROXY (env) или proxies.txt.
"""

import asyncio
import json
import logging
import os
import random
import socks
import time
import aiohttp
from telethon import TelegramClient, events
from telethon.tl.types import KeyboardButtonCallback
import config
from config import bot_logs
from aiogram import Bot, types
import keyboards
from utils import now_msk, ProgressBar

logger = logging.getLogger(__name__)

GROQ_KEY = os.environ.get("GROQ_KEY", config.GROQ_KEY)

TARGET_LABELS = {
    "account": "user account",
    "bot": "bot",
    "chat": "group chat",
    "channel": "channel",
}

TIDA_SYSTEM_PROMPT = """You are a TIDA report text generator for Telegram's @TIDABOT reporting system.
Generate a formal complaint text in English. Maximum 350 characters total. Do not exceed this limit.
Rules:
- Professional and legal tone
- Reference TIDA/Telegram framework rules relevant to the violation:
  * Personal data / doxxing → Telegram ToS §4 (Privacy), TIDA Privacy Violation category
  * CSAM / child content → Telegram ToS §4 (CSAM), TIDA Child Safety category, UN CRC Art.34
  * Non-consensual intimate images → Telegram ToS §4 (NCII), TIDA Non-Consensual Intimate Images category
  * Illegal goods / drugs → Telegram ToS §4 (Illegal Activities), TIDA Illegal Goods category
  * Violence / terrorism → Telegram ToS §4 (Violence), TIDA Violent Speech category
  * Spam / fraud → Telegram ToS §4 (Spam), TIDA Spam & Scam category
  * Other violations → Telegram ToS (telegram.org/tos), TIDA Other category
- The final sentence MUST say "Requesting permanent {action} of this {target}." where {target} is provided
- Do NOT mention URLs or usernames
- Use ONLY facts from the provided content or description
- Output ONLY the complaint text, nothing else"""


def _classify_violation(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ['csam', 'child', 'minor', 'младенц', 'ребен', 'дет', 'несовершеннолет']):
        return "Child sexual abuse material (CSAM) — explicit sexual content involving minors"
    if any(k in t for k in ['наркот', 'drug', 'мефедрон', 'амфет', 'героин', 'кокаин', 'марихуан', 'закладк']):
        return "Illegal drug distribution and narcotics sales"
    if any(k in t for k in ['пробив', 'доксинг', 'dox', 'личные данные', 'персональн']):
        return "Doxxing and illegal personal data trading"
    if any(k in t for k in ['скам', 'мошен', 'fraud', 'scam', 'развод']):
        return "Fraud and scam activity"
    if any(k in t for k in ['террор', 'экстремизм', 'взрыв', 'убийств', 'насили']):
        return "Terrorism, extremism and violent content"
    if any(k in t for k in ['спам', 'spam', 'реклам']):
        return "Spam and unsolicited advertising"
    return "Systematic violation of Telegram Terms of Service"


async def generate_tida_text(content: str, target_type: str, is_description: bool = False) -> str:
    """Генерирует текст жалобы через Groq для TIDA."""
    target_label = TARGET_LABELS.get(target_type, "resource")
    action = "suspension" if target_type in ("account", "bot") else "removal"

    system = TIDA_SYSTEM_PROMPT.replace("{action}", action).replace("{target}", target_label)

    # Не слать сырое описание — только абстрактную категорию нарушения
    violation_category = _classify_violation(content)
    user_content = f"Violation category: {violation_category}\nTarget type: {target_label}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "openai/gpt-oss-20b",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content}
                    ],
                    "max_tokens": 200,
                    "temperature": 0.7,
                    "reasoning_effort": "low",
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json(content_type=None)
                if "choices" not in data:
                    logger.error(f"[TIDA-AI] Groq error: {data}")
                    return ""
                msg = data["choices"][0]["message"]
                import re
                text = msg.get("content", "").strip()
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
                return text[:350]
    except Exception as e:
        logger.error(f"[TIDA-AI] Groq error: {e}")
        return ""


async def analyze_tida_link(link: str) -> dict:
    """
    Анализирует ссылку и возвращает:
    {
        target_type: "channel"|"chat"|"bot"|"account",
        has_message_id: bool,
        message_id: int|None,
        username: str,
        is_public: bool,
        message_text: str,  # если публичная + есть msg_id
    }
    """
    result = {
        "target_type": "channel",
        "has_message_id": False,
        "message_id": None,
        "username": link,
        "is_public": False,
        "message_text": "",
    }

    # Нормализуем ссылку
    clean = link.strip()
    is_private = False

    if "joinchat" in clean or "+A" in clean or (clean.startswith("https://t.me/+") or clean.startswith("t.me/+")):
        is_private = True
        result["is_public"] = False
        result["target_type"] = "chat"
        return result

    # Парсим username и message_id
    for prefix in ["https://t.me/", "http://t.me/", "t.me/"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    if clean.startswith("@"):
        clean = clean[1:]

    parts = clean.rstrip("/").split("?")[0].split("/")
    username = parts[0]
    result["username"] = username

    if len(parts) >= 2 and parts[-1].isdigit():
        result["has_message_id"] = True
        result["message_id"] = int(parts[-1])

    # Пробуем получить entity через Telethon
    try:
        import os as _os
        session_folder = "sessions"
        sessions = [f.replace(".session", "") for f in _os.listdir(session_folder)
                    if f.endswith(".session")] if _os.path.exists(session_folder) else []
        if not sessions:
            result["is_public"] = False
            return result

        session_path = _os.path.join(session_folder, random.choice(sessions))
        client = TelegramClient(session_path, int(config.TIDA_API_ID), config.TIDA_API_HASH,
                                system_version="4.16.30-vxCUSTOM")
        for _a in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                break
            except (asyncio.TimeoutError, OSError):
                if _a == 2:
                    return result
                await asyncio.sleep(1)
        if not await client.is_user_authorized():
            await client.disconnect()
            return result

        try:
            entity = await client.get_entity(username)
            from telethon.tl.types import (Channel, Chat, User,
                                            InputPeerChannel, InputPeerChat)

            if hasattr(entity, 'megagroup') and entity.megagroup:
                result["target_type"] = "chat"
            elif isinstance(entity, Channel):
                result["target_type"] = "channel"
            elif isinstance(entity, User):
                result["target_type"] = "bot" if entity.bot else "account"
            elif isinstance(entity, Chat):
                result["target_type"] = "chat"

            result["is_public"] = True

            # Если есть message_id — читаем текст сообщения
            if result["has_message_id"] and result["message_id"]:
                try:
                    msg = await client.get_messages(entity, ids=result["message_id"])
                    if msg:
                        result["message_text"] = (msg.text or msg.caption or "")[:500]
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"[TIDA-AI] get_entity error: {e}")
            result["is_public"] = False

        await client.disconnect()
    except Exception as e:
        logger.warning(f"[TIDA-AI] analyze error: {e}")

    # Если entity-lookup не удался и тип остался "channel" —
    # для голого юзернейма (без message_id, не joinchat) ставим "account"
    if result["target_type"] == "channel" and not result["has_message_id"] and not is_private:
        result["target_type"] = "account"

    return result


async def fetch_tida_message_text(link: str) -> str:
    """Получает текст сообщения по публичной ссылке."""
    try:
        clean = link.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
        parts = clean.rstrip("/").split("/")
        if len(parts) < 2:
            return ""
        username = parts[0]
        msg_id = int(parts[-1])

        session_folder = "sessions"
        import os as _os
        sessions = [f.replace(".session", "") for f in _os.listdir(session_folder)
                    if f.endswith(".session")] if _os.path.exists(session_folder) else []
        if not sessions:
            return ""

        session_path = _os.path.join(session_folder, random.choice(sessions))
        client = TelegramClient(session_path, int(config.TIDA_API_ID), config.TIDA_API_HASH,
                                system_version="4.16.30-vxCUSTOM")
        for _a in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                break
            except (asyncio.TimeoutError, OSError):
                if _a == 2:
                    return ""
                await asyncio.sleep(1)
        if not await client.is_user_authorized():
            await client.disconnect()
            return ""
        msg = await client.get_messages(username, ids=msg_id)
        text = ""
        if msg:
            text = msg.text or msg.caption or ""
        await client.disconnect()
        logger.info(f"[TIDA-AI] получен текст: {text[:80]}")
        return text[:500]
    except Exception as e:
        logger.warning(f"[TIDA-AI] fetch error: {e}")
        return ""

TIDA_DIR = "tida_sessions"
os.makedirs(TIDA_DIR, exist_ok=True)

MAIL_DOMAIN = "br-v2.com"
CODES_DIR = "/tmp/mailcodes"
os.makedirs(CODES_DIR, exist_ok=True)


async def _wait_for_code_file(session_email: str, timeout: int = 60) -> str | None:
    fname = session_email.replace("@", "_at_").replace("/", "_")
    code_file = os.path.join(CODES_DIR, fname)
    started_at = time.time()
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if os.path.exists(code_file):
            try:
                with open(code_file) as f:
                    data = json.load(f)
                if data.get("ts", 0) >= started_at - 60:
                    os.remove(code_file)
                    return data["code"]
                else:
                    os.remove(code_file)
            except Exception:
                pass
        await asyncio.sleep(1)
    return None


bot = None
main_bot = None

def set_bot_tida(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b

LOG_FOLDER = "logs"
os.makedirs(LOG_FOLDER, exist_ok=True)


def _get_sessions():
    files = [f for f in os.listdir(TIDA_DIR) if f.endswith(".session")]
    return [os.path.join(TIDA_DIR, f.replace(".session", "")) for f in files]


def _parse_proxy_str(line: str):
    """Парсит строку прокси в dict для Telethon (rdns=True — DNS через прокси)."""
    try:
        import re as _re
        line = line.strip()
        if not line:
            return None
        proxy_type = "socks5"
        m = _re.match(r'^(http|https|socks4|socks5)://', line, _re.IGNORECASE)
        if m:
            proxy_type = m.group(1).lower()
            if proxy_type == "https":
                proxy_type = "http"
            line = line[m.end():]

        username = password = ip = port = None
        m = _re.match(r'^([^:]+):([^@]+)@([^:]+):(\d+)$', line)
        if m:
            username, password, ip, port = m.groups()
        else:
            parts = line.split(":")
            if len(parts) == 4:
                ip, port, username, password = parts
            elif len(parts) == 2:
                ip, port = parts
            else:
                return None

        if username:
            username = username.split(";")[0]  # strip sticky-session suffix

        return {
            "proxy_type": proxy_type,
            "addr": ip,
            "port": int(port),
            "username": username,
            "password": password,
            "rdns": True,
        }
    except Exception:
        pass
    return None


def _get_all_proxies() -> list:
    """Возвращает список всех прокси для TIDA."""
    # Приоритет 1: env переменные (один прокси)
    host = os.environ.get("TIDA_PROXY_HOST", "")
    port = os.environ.get("TIDA_PROXY_PORT", "")
    user = os.environ.get("TIDA_PROXY_USER", "")
    password = os.environ.get("TIDA_PROXY_PASS", "")

    if host and port:
        return [{"proxy_type": "socks5", "addr": host, "port": int(port),
                 "username": user or None, "password": password or None, "rdns": True}]

    # Приоритет 2: proxies.txt / proxy_input.txt
    for fname in ["proxies.txt", "proxy_input.txt"]:
        if os.path.exists(fname):
            with open(fname, "r") as f:
                result = []
                for line in f:
                    p = _parse_proxy_str(line)
                    if p:
                        result.append(p)
            if result:
                return result
            break

    return []


def _get_proxy():
    """Возвращает один прокси (обратная совместимость)."""
    proxies = _get_all_proxies()
    return proxies[0] if proxies else None




async def _create_client(session_path: str, proxy=None):
    try:
        api_id = int(config.TIDA_API_ID)
        api_hash = config.TIDA_API_HASH
        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy,
                                system_version='4.16.30-vxCUSTOM')
        connected = False
        for db_attempt in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=15)
                connected = True
                break
            except (asyncio.TimeoutError, OSError):
                if db_attempt == 2:
                    logger.warning(f"[TIDA] Таймаут подключения {session_path}")
                    return None
                await asyncio.sleep(1)
            except Exception as e:
                if "database is locked" in str(e) and db_attempt < 2:
                    await asyncio.sleep(random.uniform(1, 2))
                else:
                    raise
        if not connected:
            return None
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        return client
    except Exception as e:
        logger.warning(f"[TIDA] Ошибка подключения {session_path}: {e}")
        return None


async def _send_one_report(client, bot_entity, session_email: str, target: str, custom_text: str, report_num: int) -> bool:
    done = asyncio.Event()
    step = 0
    success = False
    session_name = os.path.basename(client.session.filename)

    @client.on(events.NewMessage(from_users=bot_entity.id))
    async def handler(event):
        nonlocal step, success
        text = event.message.message.strip().lower()
        markup = event.message.reply_markup

        logger.info(f"[TIDA] [{session_name}] [{report_num}] 📨 TIDABOT: step={step} | text={text[:120]!r}")

        if ("please enter a t.me" in text or "enter the link" in text or "enter a link" in text or "t.me link" in text) and step == 0:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, target)
            step = 1
            logger.info(f"[TIDA] [{session_name}] [{report_num}] Ссылка отправлена")

        elif ("select the reason" in text or "choose the reason" in text or "reason for" in text or "select a reason" in text) and step == 1:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, "Non-consensual intimate image sharing")
            step = 2
            logger.info(f"[TIDA] [{session_name}] [{report_num}] Причина отправлена")

        elif ("why the content is illegal" in text or "describe" in text or "explain" in text or "provide details" in text or "additional information" in text) and step == 2:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, custom_text)
            step = 3
            logger.info(f"[TIDA] [{session_name}] [{report_num}] Описание отправлено")

        elif ("documentation" in text or "evidence" in text or "attach" in text or "upload" in text or "skip" in text) and step == 3:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, "Proceed without documentation")
            step = 4
            logger.info(f"[TIDA] [{session_name}] [{report_num}] Документация пропущена")

        elif "by submitting this report" in text and step == 4:
            await asyncio.sleep(0.3)
            if markup and markup.rows:
                for row in markup.rows:
                    for btn in row.buttons:
                        if "confirm" in btn.text.lower():
                            if isinstance(btn, KeyboardButtonCallback):
                                await event.message.click(data=btn.data)
                                step = 5
                                logger.info(f"[TIDA] [{session_name}] [{report_num}] Подтверждено (кнопка)")
                                return
            await client.send_message(bot_entity, "Confirm")
            step = 5
            logger.info(f"[TIDA] [{session_name}] [{report_num}] Подтверждено (текст)")

        elif "please enter your email" in text and step == 5:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, session_email)
            step = 6
            logger.info(f"[TIDA] [{session_name}] [{report_num}] Email отправлен ({session_email}), жду код...")

        elif "verification code" in text and step == 6:
            code = await _wait_for_code_file(session_email, timeout=360)
            if code:
                await asyncio.sleep(0.5)
                await client.send_message(bot_entity, code)
                step = 7
                logger.info(f"[TIDA] [{session_name}] [{report_num}] Код отправлен: {code}")
            else:
                logger.warning(f"[TIDA] [{session_name}] [{report_num}] ⏳ Код не пришёл за 60с")
                done.set()

        elif "thank you for your report" in text or "report has been submitted" in text or "report received" in text:
            success = True
            done.set()
            logger.info(f"[TIDA] [{session_name}] [{report_num}] ✅ Успешно!")

        elif "not available in your region" in text or "too many attempts" in text:
            logger.warning(f"[TIDA] [{session_name}] [{report_num}] ⛔ Регион/лимит — пропускаем сессию")
            done.set()

        elif "create_report_failed" in text or "failed" in text:
            logger.warning(f"[TIDA] [{session_name}] [{report_num}] ❌ CREATE_REPORT_FAILED — нужен другой прокси")
            done.set()

        elif ("invalid" in text or "not found" in text or "incorrect" in text or "expired" in text) and step >= 5:
            logger.warning(f"[TIDA] [{session_name}] [{report_num}] ❌ Ошибка верификации")
            done.set()

        elif "invalid" in text or "not found" in text:
            logger.warning(f"[TIDA] [{session_name}] [{report_num}] ❌ Ошибка от бота")
            done.set()

    await client.send_message(bot_entity, "/start")
    logger.info(f"[TIDA] [{session_name}] [{report_num}] /start отправлен")

    try:
        await asyncio.wait_for(done.wait(), timeout=700)
    except asyncio.TimeoutError:
        logger.warning(f"[TIDA] [{session_name}] [{report_num}] ⏳ Таймаут")

    client.remove_event_handler(handler)
    return success


async def _single_session_flow(session_path: str, target: str, custom_text: str,
                                proxy=None, tida_peer_ref=None, all_proxies=None,
                                session_email: str = "") -> bool:
    session_name = os.path.basename(session_path)
    if tida_peer_ref is None:
        tida_peer_ref = [None]

    MAX_PROXY_RETRIES = min(2, len(all_proxies)) if all_proxies else 1
    used_proxies = set()
    current_proxy = proxy

    for attempt in range(MAX_PROXY_RETRIES):
        client = await _create_client(session_path, current_proxy)
        if not client:
            # Попробуй другой прокси
            if all_proxies:
                remaining = [p for i, p in enumerate(all_proxies) if i not in used_proxies]
                if remaining:
                    current_proxy = random.choice(remaining)
                    used_proxies.add(all_proxies.index(current_proxy))
            continue

        try:
            try:
                bot_entity = await client.get_entity("TIDABOT")
                if tida_peer_ref[0] is None:
                    tida_peer_ref[0] = bot_entity.id
            except Exception as e:
                if tida_peer_ref[0] is not None and "No user has" in str(e):
                    bot_entity = await client.get_entity(tida_peer_ref[0])
                else:
                    logger.error(f"[TIDA] [{session_name}] Не найден TIDABOT: {e}")
                    await client.disconnect()
                    return False

            logger.info(f"[TIDA] [{session_name}] Попытка {attempt + 1}/{MAX_PROXY_RETRIES} | прокси: {current_proxy[1] if current_proxy else 'нет'} | email: {session_email}")
            success = await _send_one_report(client, bot_entity, session_email, target, custom_text, attempt + 1)

            if success:
                return True

            # CREATE_REPORT_FAILED — меняем прокси и пробуем снова
            if all_proxies and attempt + 1 < MAX_PROXY_RETRIES:
                proxy_list = list(range(len(all_proxies)))
                remaining = [i for i in proxy_list if i not in used_proxies]
                if remaining:
                    idx = random.choice(remaining)
                    used_proxies.add(idx)
                    current_proxy = all_proxies[idx]
                    logger.info(f"[TIDA] [{session_name}] Меняем прокси → {current_proxy[1]}")
                else:
                    logger.warning(f"[TIDA] [{session_name}] Все прокси исчерпаны")
                    return False

        except Exception as e:
            logger.error(f"[TIDA] [{session_name}] Ошибка: {e}")
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    return False


async def main_tida(target_link: str, custom_text: str, user: int, username: str, _log_user=None, silent: bool = False, notify_bot=None):
    _notify = notify_bot or bot
    sessions = _get_sessions()
    if not sessions:
        await _notify.send_message(user,
            "❌ *Нет сессий для TIDA!*\n*Положи .session файлы в папку* `tida_sessions/`",
            parse_mode="Markdown", reply_markup=keyboards.main_menu)
        return

    # Нормализуем target → всегда t.me/username[/msg_id]
    target = target_link.strip()
    # Убираем любые протоколы
    target = target.replace("https://", "").replace("http://", "")
    # Убираем @ в начале
    if target.startswith("@"):
        target = target[1:]
    # Убираем www.
    target = target.replace("www.", "")
    # Если уже начинается с t.me/ — ок, иначе добавляем
    if not target.startswith("t.me/"):
        target = f"t.me/{target}"
    # Защита от t.me/ без юзернейма
    parts = target.split("/")
    if len(parts) < 2 or not parts[1]:
        await _notify.send_message(user, "❌ *Неверная ссылка!*", parse_mode="Markdown", reply_markup=keyboards.main_menu)
        return

    all_proxies = _get_all_proxies()
    if not all_proxies:
        await _notify.send_message(user,
            "⚠️ *TIDA работает без прокси — это может не сработать.*\n*Рекомендуется добавить SOCKS5 прокси.*",
            parse_mode="Markdown")

    total = len(sessions)

    # Ротация сессий: берём один аккаунт по очереди
    rotation_file = os.path.join(TIDA_DIR, ".rotation_index")
    try:
        with open(rotation_file) as f:
            rot_idx = int(f.read().strip())
    except Exception:
        rot_idx = 0
    rot_idx = rot_idx % total
    active_session = sessions[rot_idx]
    try:
        with open(rotation_file, "w") as f:
            f.write(str((rot_idx + 1) % total))
    except Exception:
        pass

    # Ротация email: независимый счётчик, каждый запуск — новый email
    email_counter_file = os.path.join(TIDA_DIR, ".email_counter")
    try:
        with open(email_counter_file) as f:
            email_idx = int(f.read().strip())
    except Exception:
        email_idx = 0
    try:
        with open(email_counter_file, "w") as f:
            f.write(str(email_idx + 1))
    except Exception:
        pass

    logger.info(f"[TIDA] 🚀 Запуск | Цель: {target} | Сессий: {total} | Ротация: {rot_idx} ({os.path.basename(active_session)}) | Прокси: {len(all_proxies)}")

    ACCOUNTS_TO_USE = min(2, total)
    tida_peer_ref = [None]
    pb = ProgressBar(_notify, user, total=ACCOUNTS_TO_USE, title="🎵 *TIDA*", silent=silent)
    await pb.start()

    # Всегда отправляем с ACCOUNTS_TO_USE аккаунтов подряд, не останавливаясь после первого успеха
    successful_count = 0
    last_email_idx = email_idx
    for attempt in range(ACCOUNTS_TO_USE):
        sess_idx = (rot_idx + attempt) % total
        session_path = sessions[sess_idx]
        cur_email_idx = email_idx + attempt
        last_email_idx = cur_email_idx
        session_email = f"td{cur_email_idx:04d}@{MAIL_DOMAIN}"
        logger.info(f"[TIDA] Аккаунт {attempt + 1}/{ACCOUNTS_TO_USE} | сессия: {os.path.basename(session_path)} | email: {session_email}")
        ok = await _single_session_flow(
            session_path, target, custom_text,
            random.choice(all_proxies) if all_proxies else None,
            tida_peer_ref,
            all_proxies if all_proxies else None,
            session_email=session_email)
        if ok:
            successful_count += 1
        else:
            logger.warning(f"[TIDA] Сессия {os.path.basename(session_path)} не сработала")

    try:
        with open(email_counter_file, "w") as f:
            f.write(str(last_email_idx + 1))
    except Exception:
        pass

    real_result = successful_count > 0

    # Визуально показываем все аккаунты как выполненные
    for i in range(ACCOUNTS_TO_USE):
        await pb.update(i + 1)
        if i < ACCOUNTS_TO_USE - 1:
            await asyncio.sleep(0.05)

    await pb.finish()

    if not real_result:
        logger.warning(f"[TIDA] ❌ Оба аккаунта не смогли отправить жалобу")
        if not silent:
            try:
                await _notify.send_message(
                    user,
                    f"🟣 *TIDA*\n\n❌ *Не удалось отправить жалобу ни с одного аккаунта\\!*\n🎯 *Цель:* {target.replace('_', chr(92)+'_')}",
                    parse_mode="Markdown", reply_markup=keyboards.main_menu)
            except Exception as e:
                logger.error(f"[TIDA] Ошибка отправки ошибки пользователю: {e}")
        return (0, ACCOUNTS_TO_USE)

    successful = successful_count

    logger.info(f"[TIDA] 🏁 Итог: {successful}/{ACCOUNTS_TO_USE}")

    now_str = now_msk().strftime("%d.%m.%Y %H:%M:%S")

    target_escaped = target.replace('_', '\\_')
    caption_user = (
        f"🟣 *TIDA завершён!*\n\n"
        f"🎯 *Цель:* {target_escaped}\n"
        f"🕐 *Время:* {now_str}\n\n"
        f"🟢 *Успешно: {successful}*\n"
        f"🔴 *Не удалось: {ACCOUNTS_TO_USE - successful}*"
    )
    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "скрыт" if _is_hid else str(user)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    caption_log = (
        f"🟣 *TIDA*\n\n"
        f"🎯 *Цель:* {target_escaped}\n"
        f"🗒️ *Текст:* {custom_text[:100]}{'...' if len(custom_text) > 100 else ''}\n"
        f"👤 *Пользователь:* {_log_uid} (@{_log_uname})\n"
        f"🕐 *Время:* {now_str}\n\n"
        f"🟢 *Успешно: {successful}*\n"
        f"🔴 *Не удалось: {ACCOUNTS_TO_USE - successful}*"
    )

    if not silent:
        try:
            await _notify.send_message(user, caption_user, parse_mode="Markdown", reply_markup=keyboards.main_menu)
        except Exception as e:
            logger.error(f"[TIDA] Ошибка отправки результата пользователю: {e}")

        try:
            await main_bot.send_message(bot_logs, caption_log, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[TIDA] Ошибка отправки лога: {e}")

    return (successful, ACCOUNTS_TO_USE)
