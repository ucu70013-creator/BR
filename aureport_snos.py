"""
Brown V2 | aureport_snos.py
AU Report метод — жалобы через @AuReportBot.
Сессии берутся из папки aureport_sessions/
Прокси берутся из au_proxies.txt.
"""

import asyncio
import json
import logging
import os
import random
import time
from telethon import TelegramClient, events
from telethon.tl.types import KeyboardButtonCallback
import config
from config import bot_logs
from utils import now_msk, ProgressBar, esc_md
from aiogram import Bot, types
import keyboards

logger = logging.getLogger(__name__)

AUREPORT_DIR = "aureport_sessions"
os.makedirs(AUREPORT_DIR, exist_ok=True)

MAIL_DOMAIN = "br-v2.com"
CODES_DIR = "/tmp/mailcodes"
os.makedirs(CODES_DIR, exist_ok=True)


async def _wait_for_code_file(session_email: str, timeout: int = 60) -> str | None:
    """Poll /tmp/mailcodes/<email> until mailpipe.py writes a fresh code or timeout."""
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
                # принимаем только код записанный после начала ожидания
                if data.get("ts", 0) >= started_at - 60:
                    os.remove(code_file)
                    return data["code"]
                else:
                    # устаревший файл — удаляем и ждём новый
                    os.remove(code_file)
            except Exception:
                pass
        await asyncio.sleep(1)
    return None

bot = None
main_bot = None

def set_bot_aureport(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b

LOG_FOLDER = "logs"
os.makedirs(LOG_FOLDER, exist_ok=True)

_aureport_lock = asyncio.Lock()   # очередь: один запуск за раз


def _get_sessions():
    files = [f for f in os.listdir(AUREPORT_DIR) if f.endswith(".session")]
    return [os.path.join(AUREPORT_DIR, f.replace(".session", "")) for f in files]


def _load_proxies():
    proxies = []
    if os.path.exists("au_proxies.txt"):
        with open("au_proxies.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    proxies.append(line)
    return proxies


def _parse_proxy(proxy_str):
    """Парсит строку proxy в формат Telethon dict (rdns=True — DNS через прокси)."""
    try:
        import re
        proxy_str = proxy_str.strip()
        proxy_type = "http"
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
            username = username.split(";")[0]  # strip sticky-session suffix (;anon.1)

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
        connected = False
        for _a in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                connected = True
                break
            except (asyncio.TimeoutError, OSError):
                if _a == 2:
                    return None
                await asyncio.sleep(1)
        if not connected:
            return None
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        return client
    except Exception as e:
        logger.warning(f"[AUREPORT] Ошибка подключения {session_path}: {e}")
        return None


_START_REPEATS = 3   # сколько раз слать /start при ответе "australian online safety act"
_START_DELAY  = 2.0  # секунды между повторными /start


async def _send_one_report(client, bot_entity, session_email: str, target: str, report_num: int, reason: str = "pav") -> bool:
    done = asyncio.Event()
    step = 0
    success = False
    start_sent = 1          # уже отправили 1 /start перед регистрацией хендлера
    session_name = os.path.basename(client.session.filename)

    @client.on(events.NewMessage(from_users=bot_entity.id))
    async def handler(event):
        nonlocal step, success, start_sent
        text = event.message.message.strip().lower()
        markup = event.message.reply_markup

        logger.info(f"[AUREPORT] [{session_name}] [{report_num}] 📨 step={step} | {text[:120]!r}")

        # Запрос ссылки проверяем первым — бот может включить его в то же сообщение с disclaimer
        if "please enter a t.me" in text and step == 0:
            await asyncio.sleep(0.3)
            # Шлём t.me/... без https:// — именно так принимает бот
            link = target
            if link.startswith("https://"):
                link = link[len("https://"):]
            elif link.startswith("http://"):
                link = link[len("http://"):]
            await client.send_message(bot_entity, link)
            step = 1
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Ссылка отправлена: {link}")

        elif "select the reason" in text and step == 1:
            await asyncio.sleep(0.3)
            if reason == "child":
                await client.send_message(bot_entity, "Child sexual exploitation material")
                step = 4  # Child: нет шагов с описанием и документами → сразу к confirm
            else:
                await client.send_message(bot_entity, "Drug-related material")
                step = 2
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Причина отправлена (reason={reason})")

        elif "why the content is illegal" in text and step == 2:
            await asyncio.sleep(0.3)
            await client.send_message(
                bot_entity,
                "This account facilitates the active sale and distribution of illegal narcotics."
            )
            step = 3
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Описание отправлено")

        elif "documentation" in text and step == 3:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, "Proceed without documentation")
            step = 4
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Документация пропущена")

        elif "by submitting this report" in text and step == 4:
            await asyncio.sleep(0.3)
            if markup and markup.rows:
                for row in markup.rows:
                    for btn in row.buttons:
                        if "confirm" in btn.text.lower():
                            if isinstance(btn, KeyboardButtonCallback):
                                await event.message.click(data=btn.data)
                                step = 5
                                logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Подтверждено (кнопка)")
                                return
            await client.send_message(bot_entity, "Confirm")
            step = 5
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Подтверждено (текст)")

        elif "please enter your email" in text and step == 5:
            await asyncio.sleep(0.3)
            await client.send_message(bot_entity, session_email)
            step = 6
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Email отправлен ({session_email}), жду код...")

        elif "verification code" in text and step == 6:
            code = await _wait_for_code_file(session_email, timeout=360)
            if code:
                await asyncio.sleep(0.5)
                try:
                    await client.send_message(bot_entity, code)
                    step = 7
                    logger.info(f"[AUREPORT] [{session_name}] [{report_num}] Код отправлен: {code}")
                except Exception as _e:
                    # TypeNotFoundError — Telethon не может распарсить ответ (устаревший TL),
                    # но сообщение с кодом уже доставлено в Telegram.
                    # "Thank you" может прийти в том же пакете или отдельным — проверяем оба варианта.
                    _err_str = str(_e)
                    if "thank you for your report" in _err_str.lower() or "report has been submitted" in _err_str.lower():
                        success = True
                        logger.info(f"[AUREPORT] [{session_name}] [{report_num}] ✅ Успешно (из байт ошибки TL)!")
                    else:
                        # "Thank you" не пришёл вместе — ждём отдельный пакет и поллим историю
                        logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] Ошибка ответа, Thank You не найден, поллинг через 5с...")
                        await asyncio.sleep(5)
                        try:
                            await client.get_messages(bot_entity, limit=3)
                        except Exception as _pe:
                            _pe_str = str(_pe)
                            if "thank you for your report" in _pe_str.lower() or "report has been submitted" in _pe_str.lower():
                                success = True
                                logger.info(f"[AUREPORT] [{session_name}] [{report_num}] ✅ Успешно (поллинг байты)!")
                            else:
                                logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] Поллинг: Thank You не найден: {_pe!r}")
                    step = 7
                    done.set()
            else:
                logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] ⏳ Код не пришёл за 60с")
                done.set()

        elif "thank you for your report" in text or "report has been submitted" in text or "report received" in text:
            success = True
            done.set()
            logger.info(f"[AUREPORT] [{session_name}] [{report_num}] ✅ Успешно!")

        elif "not available in your region" in text or "too many attempts" in text:
            logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] ⛔ Регион/лимит — пропускаем сессию")
            done.set()

        elif ("invalid" in text or "not found" in text or "incorrect" in text or "expired" in text) and step >= 5:
            logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] ❌ Ошибка верификации")
            done.set()
        elif "invalid" in text or "not found" in text:
            logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] ❌ Ошибка от бота")
            done.set()

    await client.send_message(bot_entity, "/start")
    logger.info(f"[AUREPORT] [{session_name}] [{report_num}] /start отправлен")

    try:
        await asyncio.wait_for(done.wait(), timeout=700)
    except asyncio.TimeoutError:
        logger.warning(f"[AUREPORT] [{session_name}] [{report_num}] ⏳ Таймаут")

    client.remove_event_handler(handler)
    return success


async def _single_session_flow(session_path: str, target: str, session_email: str, proxy=None, reason: str = "pav") -> bool:
    session_name = os.path.basename(session_path)
    client = await _create_client(session_path, proxy)
    if not client:
        return False

    try:
        bot_entity = await client.get_entity("AuReportBot")
        logger.info(f"[AUREPORT] [{session_name}] Бот найден | email: {session_email}")

        success1 = await _send_one_report(client, bot_entity, session_email, target, 1, reason)

        return success1
    except Exception as e:
        logger.error(f"[AUREPORT] [{session_name}] Ошибка: {e}")
        return False
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main_aureport(target_link: str, user: int, username: str, silent: bool = False, notify_bot=None, reason: str = "pav"):
    _notify = notify_bot or bot

    if _aureport_lock.locked():
        if not silent:
            try:
                await _notify.send_message(
                    user,
                    "⏳ *AU Report в очереди...*\nДругой отчёт сейчас выполняется\\. Ваш запрос будет обработан автоматически после завершения\\.",
                    parse_mode="Markdown")
            except Exception:
                pass

    async with _aureport_lock:
        pending = await _main_aureport_inner(target_link, user, username, silent, notify_bot, reason)

    # Lock released — send result notifications now
    if pending:
        for coro in pending:
            try:
                await coro
            except Exception:
                pass


async def _main_aureport_inner(target_link: str, user: int, username: str, silent: bool = False, notify_bot=None, reason: str = "pav"):
    _notify = notify_bot or bot
    sessions = _get_sessions()
    if not sessions:
        return [_notify.send_message(user,
            "❌ *Нет сессий для AU Report!*\n*Положи .session файлы в папку* aureport_sessions/",
            parse_mode="Markdown", reply_markup=keyboards.main_menu)]

    # Нормализуем target
    target = target_link.strip()
    if target.startswith("@"):
        target = f"t.me/{target[1:]}"
    elif target.startswith("https://t.me/"):
        target = target[len("https://"):]
    elif target.startswith("http://t.me/"):
        target = target[len("http://"):]
    elif not target.startswith("t.me/"):
        target = f"t.me/{target}"

    proxies = _load_proxies()
    total = len(sessions)

    # Ротация сессий: берём один аккаунт по очереди
    rotation_file = os.path.join(AUREPORT_DIR, ".rotation_index")
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
    email_counter_file = os.path.join(AUREPORT_DIR, ".email_counter")
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

    logger.info(f"[AUREPORT] 🚀 Запуск | Цель: {target} | Сессий: {total} | Ротация: {rot_idx} ({os.path.basename(active_session)}) | Прокси: {len(proxies)}")

    pb = ProgressBar(_notify, user, total=total, title="🔍 *AU Report*", silent=silent)
    await pb.start()

    # Пробуем аккаунты по очереди начиная с текущего; при ошибке — следующий (самый давний)
    real_result = False
    for attempt in range(total):
        sess_idx = (rot_idx + attempt) % total
        session_path = sessions[sess_idx]
        proxy = _parse_proxy(proxies[sess_idx % len(proxies)]) if proxies else None
        cur_email_idx = email_idx + attempt
        session_email = f"au{cur_email_idx:04d}@{MAIL_DOMAIN}"
        logger.info(f"[AUREPORT] Попытка {attempt + 1}/{total} | сессия: {os.path.basename(session_path)} | email: {session_email}")
        real_result = await _single_session_flow(session_path, target, session_email, proxy, reason)
        if real_result:
            # Обновляем email счётчик до следующего после последнего использованного
            try:
                with open(email_counter_file, "w") as f:
                    f.write(str(cur_email_idx + 1))
            except Exception:
                pass
            break
        logger.warning(f"[AUREPORT] Сессия {os.path.basename(session_path)} не сработала, пробуем следующую")

    if not real_result:
        try:
            with open(email_counter_file, "w") as f:
                f.write(str(email_idx + total))
        except Exception:
            pass

    # Визуально показываем все сессии как выполненные
    for i in range(total):
        await pb.update(i + 1)
        if i < total - 1:
            await asyncio.sleep(0.05)

    await pb.finish()

    if not real_result:
        logger.warning(f"[AUREPORT] ❌ Все {total} аккаунтов не смогли отправить жалобу")
        if not silent:
            return [_notify.send_message(
                user,
                f"🇦🇺 *AU Report*\n\n❌ *Не удалось отправить жалобу ни с одного аккаунта\\!*\n🎯 *Цель:* {target.replace('_', chr(92)+'_')}",
                parse_mode="Markdown", reply_markup=keyboards.main_menu)]
        return []

    successful = total

    logger.info(f"[AUREPORT] 🏁 Итог: {successful}/{total}")

    now_str = now_msk().strftime("%d.%m.%Y %H:%M:%S")

    target_escaped = target.replace('_', '\\_')
    reason_label = "💊 ПАВ" if reason == "pav" else "🔞 Child"
    caption_user = (
        f"🇦🇺 *AU Report завершён!*\n\n"
        f"🎯 *Цель:* {target_escaped}\n"
        f"🕐 *Время:* {now_str}\n\n"
        f"🟢 *Успешно: {successful}*\n"
        f"🔴 *Не удалось: {total - successful}*"
    )
    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "скрыт" if _is_hid else str(user)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    caption_log = (
        f"🇦🇺 *AU Report*\n\n"
        f"🎯 *Цель:* {target_escaped}\n"
        f"{reason_label} *Причина:* {'ПАВ' if reason == 'pav' else 'Child'}\n"
        f"👤 *Пользователь:* {_log_uid} (*@{_log_uname}*)\n"
        f"🕐 *Время:* {now_str}\n\n"
        f"🟢 *Успешно: {successful}*\n"
        f"🔴 *Не удалось: {total - successful}*"
    )

    if not silent:
        _log_bot = main_bot or bot

        async def _send_results():
            try:
                await _notify.send_message(user, caption_user, parse_mode="Markdown", reply_markup=keyboards.main_menu)
            except Exception as e:
                logger.error(f"[AUREPORT] Ошибка отправки результата пользователю: {e}")
            for attempt in range(3):
                try:
                    if _log_bot:
                        await _log_bot.send_message(bot_logs, caption_log, parse_mode="Markdown")
                        break
                except Exception as e:
                    logger.error(f"[AUREPORT] Ошибка отправки лога (попытка {attempt+1}): {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)

        return [_send_results()]

    return []
