import os
import random
import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import PeerUser, PeerChannel
from telethon.tl.functions.messages import ReportRequest
from aiogram import Bot, types
import config
from config import bot_logs
import keyboards
from utils import now_msk, ProgressBar, esc_md
from report_texts import GENERAL_TEXTS as reasons_texts

reasons = [
    b'2',  # Child abuse
    b'3',  # Violence
    b'4',  # Illegal goods and services
    b'5',  # Illegal adult content
    b'6',  # Personal data
    b'7',  # Scam or fraud
    b'8',  # Copyright
    b'9',  # Spam
    b'a',  # Other
]

API = [
    '24565698:5a084b434f8505ace703485b9da85040',
    '27904162:e7cba879b1c643ba77490bf328df5eab',
    '23037915:50f06f5b2223586fde0d1379ea91ebc7',
    '29512095:0b29a7d42fff002856b9bed64f7ec919',
    '25055016:25edf5b7becebe91a2d61fe8d9d9931b',
    '21156147:90408de329b27f7dd411dff3e601acc6',
    '29840977:e20b6a9fd01cc9055de0a88a183a030b',
    '29412963:3e37e1d05422db9426aa85e617b441ea',
    '23140129:431e5e839aecf4abdce22d7663acffa7'
]

bot = None  # инициализируется из main.py через set_bot()
main_bot = None  # основной бот — всегда для логов в bot_logs

def set_bot(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b
session_folder = 'sessions'
os.makedirs(session_folder, exist_ok=True)

def _get_sessions():
    return [f.replace('.session', '') for f in os.listdir(session_folder) if f.endswith('.session')]

LOG_FOLDER = "logs"
os.makedirs(LOG_FOLDER, exist_ok=True)

async def extract_username_and_message_id(message_url):
    # Убираем query string если есть
    message_url = message_url.split('?')[0].rstrip('/')
    path = message_url[len('https://t.me/'):].split('/')
    if len(path) == 2:
        # Обычный формат: t.me/username/123
        chat_username = path[0]
        message_id = int(path[1])
        return chat_username, message_id
    elif len(path) == 3:
        # Форум/тред: t.me/group/thread_id/message_id
        chat_username = path[0]
        message_id = int(path[2])
        return chat_username, message_id
    raise ValueError("Неверная ссылка!")

def format_log_line(session, message_url, status):
    now = now_msk().strftime("%H:%M:%S")
    return f"[{now}] {session}.session -> {message_url} - [{status}]"

async def _report_one_session(session, chat_username, message_id, message_url, whitelist, target_ref, peer_ref):
    """
    Отправляет жалобу от одной сессии.
    target_ref — список [TARGET, target_username], общий для всех задач.
    peer_ref — список [chat_id | None], кешируем числовой ID канала после первого резолва.
    Возвращает (status: str, flood_seconds: int | None)
    """
    random_api = random.choice(API)
    api_id, api_hash = random_api.split(":", 1)
    random_reason = random.choice(reasons)
    random_reason_text = random.choice(reasons_texts)

    print(f"[BOTNET] [{session}] Подключаемся (api_id={api_id})...", flush=True)

    try:
        client = TelegramClient(
            f"./sessions/{session}", int(api_id), api_hash,
            system_version='4.16.30-vxCUSTOM'
        )
    except Exception as e:
        print(f"[BOTNET] [{session}] ❌ Ошибка открытия сессии: {e}", flush=True)
        return "ОШИБКА СЕССИИ", None
    try:
        connected = False
        for db_attempt in range(3):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                connected = True
                break
            except (asyncio.TimeoutError, OSError):
                if db_attempt == 2:
                    print(f"[BOTNET] [{session}] ❌ ОШИБКА СОЕДИНЕНИЯ (timeout)", flush=True)
                    return "ОШИБКА СОЕДИНЕНИЯ", None
                await asyncio.sleep(1)
            except Exception as e:
                if "database is locked" in str(e) and db_attempt < 2:
                    print(f"[BOTNET] [{session}] 🔒 database is locked, retry {db_attempt + 1}...", flush=True)
                    await asyncio.sleep(random.uniform(1, 2))
                else:
                    raise
        if not connected:
            return "ОШИБКА СОЕДИНЕНИЯ", None

        if not await client.is_user_authorized():
            print(f"[BOTNET] [{session}] ❌ НЕВАЛИД (не авторизован)", flush=True)
            return "НЕВАЛИД", None

        # Fix 2: резолвим канал один раз, остальные используют числовой ID
        try:
            chat = await client.get_entity(chat_username)
            if peer_ref[0] is None:
                peer_ref[0] = chat.id
        except Exception as e:
            if peer_ref[0] is not None and "No user has" in str(e):
                print(f"[BOTNET] [{session}] ⚠️ Username не резолвится, используем peer_id={peer_ref[0]}", flush=True)
                chat = await client.get_entity(peer_ref[0])
            else:
                raise
        print(f"[BOTNET] [{session}] ✅ Подключён, чат получен: {chat_username}", flush=True)

        # Получаем TARGET только один раз (первая сессия, которая успела)
        if target_ref[0] is None:
            msg = await client.get_messages(chat, ids=message_id)
            if msg.from_id is not None:
                if isinstance(msg.from_id, PeerChannel):
                    # Пост от имени канала внутри группы — репортим само сообщение, юзер не нужен
                    chan_id = msg.from_id.channel_id
                    target_ref[0] = f"channel:{chan_id}"
                    target_ref[1] = f"channel_{chan_id}"
                    print(f"[BOTNET] [{session}] ℹ️ Пост от канала {chan_id} в группе — жалуемся на сообщение", flush=True)
                    # whitelist не применяем к каналам
                elif isinstance(msg.from_id, PeerUser):
                    user_entity = await client.get_entity(msg.from_id)
                    target_ref[0] = msg.from_id.user_id
                    target_ref[1] = user_entity.username or "Нет username"
                    print(f"[BOTNET] [{session}] 🎯 Таргет определён: ID={target_ref[0]}, *@{target_ref[1]}*", flush=True)
                    if target_ref[0] in whitelist:
                        print(f"[BOTNET] [{session}] 🍕 WHITELIST — таргет в белом списке", flush=True)
                        return "WHITELIST", None
                else:
                    target_ref[0] = "?"
                    target_ref[1] = "unknown"
            else:
                # Анонимный пост канала — from_id=None, репортим само сообщение
                target_ref[0] = f"channel:{chat.id}"
                target_ref[1] = getattr(chat, 'username', None) or str(chat.id)
                print(f"[BOTNET] [{session}] ℹ️ from_id=None — анонимный пост канала {chat.id}, жалуемся на сообщение", flush=True)

        # Получаем список причин от сервера динамически (3-шаговый флоу)
        try:
            # Шаг 1: получаем категории
            print(f"[BOTNET] [{session}] 📤 Шаг 1: запрашиваем категории жалоб...", flush=True)
            r1 = await client(ReportRequest(peer=chat, id=[message_id], option=b'', message=''))
            print(f"[BOTNET] [{session}] 📥 Шаг 1 ответ: {type(r1).__name__} | options={[o.option for o in r1.options] if hasattr(r1, 'options') and r1.options else 'нет'}", flush=True)
            if hasattr(r1, 'options') and r1.options:
                cat = random.choice(r1.options).option
                print(f"[BOTNET] [{session}] 📤 Шаг 2: выбрана категория {cat!r}", flush=True)
            else:
                cat = random_reason
                print(f"[BOTNET] [{session}] 📤 Шаг 2: категории не получены, используем fallback {cat!r}", flush=True)

            # Шаг 2: выбираем категорию — может вернуть подкатегории
            r2 = await client(ReportRequest(peer=chat, id=[message_id], option=cat, message=''))
            print(f"[BOTNET] [{session}] 📥 Шаг 2 ответ: {type(r2).__name__} | options={[o.option for o in r2.options] if hasattr(r2, 'options') and r2.options else 'нет'}", flush=True)
            if hasattr(r2, 'options') and r2.options:
                sub = random.choice(r2.options).option
                print(f"[BOTNET] [{session}] 📤 Шаг 3: выбрана подкатегория {sub!r}, отправляем текст...", flush=True)
                # Шаг 3: выбираем подкатегорию и передаём текст
                r3 = await client(ReportRequest(peer=chat, id=[message_id], option=sub, message=random_reason_text))
                print(f"[BOTNET] [{session}] 📥 Шаг 3 ответ: {type(r3).__name__} | result={r3}", flush=True)
            else:
                print(f"[BOTNET] [{session}] 📤 Шаг 3: подкатегорий нет, отправляем с текстом напрямую...", flush=True)
                # r2 уже ReportResultAddComment или Reported — отправляем с текстом
                r3 = await client(ReportRequest(peer=chat, id=[message_id], option=cat, message=random_reason_text))
                print(f"[BOTNET] [{session}] 📥 Шаг 3 ответ: {type(r3).__name__} | result={r3}", flush=True)
        except Exception as report_err:
            # Fallback — просто отправляем с hardcoded option
            print(f"[BOTNET] [{session}] ⚠️ Ошибка в 3-шаговом флоу ({report_err!s:.60}), используем fallback...", flush=True)
            r_fb = await client(ReportRequest(peer=chat, id=[message_id], option=random_reason, message=random_reason_text))
            print(f"[BOTNET] [{session}] 📥 Fallback ответ: {type(r_fb).__name__} | result={r_fb}", flush=True)

        await asyncio.sleep(random.uniform(0.05, 0.5))
        print(f"[BOTNET] [{session}] ✅ ДОСТАВЛЕНО", flush=True)
        return "ДОСТАВЛЕНО", None

    except FloodWaitError as e:
        print(f"[BOTNET] [{session}] 🌊 FLOOD — ждать {e.seconds}с", flush=True)
        return "FLOOD", e.seconds
    except Exception as e:
        if "Could not find" in str(e):
            print(f"[BOTNET] [{session}] ❌ NOT_FOUND — {e!s:.80}", flush=True)
            return "NOT_FOUND", None
        print(f"[BOTNET] [{session}] ❌ ОШИБКА — {e!s:.80}", flush=True)
        return f"ОШИБКА: {str(e)[:50]}", None
    finally:
        if client.is_connected():
            await client.disconnect()


async def main(chat_username, message_id, user, username, message_url, _log_user=None, silent: bool = False, notify_bot=None):
    # Получаем вайтлист из PostgreSQL (db.py)
    _notify = notify_bot or bot
    try:
        import db as db_module
        whitelist = await db_module.get_whitelist()
    except Exception as e:
        print(f"[BOTNET] Ошибка получения вайтлиста: {e}", flush=True)
        whitelist = []

    # ─── Проверка белого списка целей по username из ссылки ───────────────────
    try:
        import db as db_module
        check_target = chat_username.strip().lstrip('@').lower()
        if await db_module.is_target_whitelisted(check_target):
            await _notify.send_message(user,
                "❌ *Цель в белом списке!*\n*└─ Жалобы на эту цель запрещены.*",
                parse_mode="Markdown", reply_markup=keyboards.main_menu)
            try:
                await main_bot.send_message(bot_logs,
                    f"⚠️ *Попытка снести цель из белого списка!*\n"
                    f"*└─ Цель:* {chat_username}\n"
                    f"*└─ Пользователь:* {user} (*@{username}*)\n"
                    f"*└─ Метод:* Ботнет",
                    parse_mode="Markdown")
            except Exception:
                pass
            return
    except Exception as wl_e:
        print(f"[BOTNET] Ошибка проверки белого списка: {wl_e}", flush=True)
    # ──────────────────────────────────────────────────────────────────────────

    if "_" in username:
        username = "None"

    print(f"\n{'='*50}", flush=True)
    print(f"[BOTNET] 🚀 Запуск ботнета", flush=True)
    print(f"[BOTNET] 👤 Пользователь: {user} (*@{username}*)", flush=True)
    print(f"[BOTNET] 🔗 Ссылка: {message_url}", flush=True)
    _sessions = _get_sessions()
    print(f"[BOTNET] 📦 Сессий загружено: {len(_sessions)}", flush=True)
    print(f"{'='*50}", flush=True)

    # Общий изменяемый объект для TARGET между параллельными задачами
    target_ref = [None, "Неизвестный пользователь"]
    peer_ref = [None]  # кешируем числовой ID канала после первого резолва

    # Запускаем сессии пачками по 8 с задержкой 3-5 сек между пачками
    BATCH_SIZE = 8
    results = []
    pb = ProgressBar(_notify, user, total=len(_sessions), title="🕸 *Ботнет*", silent=silent)
    await pb.start()
    done_count = 0
    for i in range(0, len(_sessions), BATCH_SIZE):
        batch = _sessions[i:i + BATCH_SIZE]
        batch_tasks = [_report_one_session(s, chat_username, message_id, message_url, whitelist, target_ref, peer_ref) for s in batch]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        results.extend(zip(batch, batch_results))
        done_count += len(batch)
        await pb.update(done_count)
        if i + BATCH_SIZE < len(_sessions):
            delay = random.uniform(3, 5)
            print(f"[BOTNET] ⏳ Пачка {i//BATCH_SIZE + 1} завершена, ждём {delay:.1f}с перед следующей...", flush=True)
            await asyncio.sleep(delay)
    await pb.finish()

    valid, ne_valid, flood = 0, 0, 0
    log_lines = [
        "Brown V2 log | botnet-method",
        "-" * 42,
        f"Пользователь: {user} (*@{username}*)",
        f"Ссылка: {message_url}",
        "-" * 42
    ]

    for session, result in results:
        if isinstance(result, Exception):
            ne_valid += 1
            print(f"[BOTNET] [{session}] 💥 ИСКЛЮЧЕНИЕ: {str(result)[:80]}", flush=True)
            log_lines.append(format_log_line(session, message_url, f"ИСКЛЮЧЕНИЕ: {str(result)[:50]}"))
            continue

        status, flood_sec = result

        if status == "WHITELIST":
            print(f"[BOTNET] ⛔ Таргет в вайтлисте, прерываем", flush=True)
            if not silent:
                await _notify.send_message(user, "🍕 *Какая-то ошибка!*", parse_mode="Markdown", reply_markup=keyboards.main_menu)
                try:
                    await bot.send_message(target_ref[0], f"🍕 *Попытка жалобы на* [сообщение]({message_url}) *от ID {user}!*", parse_mode="Markdown", disable_web_page_preview=True)
                except:
                    pass
            return (0, len(_sessions))
        elif status == "NO_ID":
            print(f"[BOTNET] ⚠️ Не удалось получить ID пользователя", flush=True)
            if not silent:
                await _notify.send_message(user, "🍕 *Не удалось получить ID пользователя!*", parse_mode="Markdown", reply_markup=keyboards.main_menu)
            return (0, len(_sessions))
        elif status == "NOT_FOUND":
            print(f"[BOTNET] ❌ Не могу получить ID — NOT_FOUND", flush=True)
            if not silent:
                await _notify.send_message(user,
                    "❌ *Не могу найти автора сообщения!*\n"
                    "*└─ Возможно, пост опубликован от имени канала*\n"
                    "*└─ Для сноса канала используй Channel-метод*",
                    parse_mode="Markdown", reply_markup=keyboards.main_menu)
            return (0, len(_sessions))
        elif status == "ДОСТАВЛЕНО":
            valid += 1
            log_lines.append(format_log_line(session, message_url, "ДОСТАВЛЕНО"))
        elif status == "FLOOD":
            flood += 1
            log_lines.append(format_log_line(session, message_url, f"FLOOD {flood_sec}s"))
        else:
            ne_valid += 1
            log_lines.append(format_log_line(session, message_url, status))

    TARGET = target_ref[0]
    target_username = target_ref[1]

    print(f"\n[BOTNET] {'='*50}", flush=True)
    print(f"[BOTNET] 🏁 Итоги:", flush=True)
    print(f"[BOTNET] 🎯 Таргет: ID={TARGET}, *@{target_username}*", flush=True)
    print(f"[BOTNET] ✅ Доставлено: {valid}", flush=True)
    print(f"[BOTNET] ❌ Не доставлено: {ne_valid}", flush=True)
    print(f"[BOTNET] 🌊 Флудов: {flood}", flush=True)
    print(f"[BOTNET] {'='*50}\n", flush=True)

    log_lines.append("-" * 42)
    log_lines.append("[TARGET]")
    log_lines.append(f"ID: {TARGET}")
    log_lines.append(f"USERNAME: *@{target_username}*")
    log_lines.append("-" * 42)
    log_lines.append(f"Успешно: {valid}")
    log_lines.append(f"Неуспешно: {ne_valid}")
    log_lines.append(f"Флудов: {flood}")

    log_name = f"brown_v2_botnet_log_{os.urandom(10).hex()}.txt"
    log_path = os.path.join(LOG_FOLDER, log_name)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    caption_user = (
        f"🍕 *Пицца доставлена!*\n"
        f"*└─📂 Пицца: обычная*\n\n"
        f"🟢 *Успешно отправлено: {valid}*\n"
        f"🔴 *Не удалось отправить: {ne_valid}*"
    )
    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "скрыт" if _is_hid else str(user)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    caption_log = (
        f"📈 *Бот завершил работу*\n* └─📂 Метод: B0tN3t-method*\n\n"
        f"🎯 *Таргет*\n*└─ ID: {TARGET}*\n*└─ USERNAME: *@{target_username}**\n\n"
        f"🟢 *Успешно отправлено: {valid}*\n🔴 *Не удалось отправить: {ne_valid}*\n\n"
        f"⛓️‍💥 *Ссылка:* [тык]({message_url})\n👤 *Пользователь:* {_log_uid} (*@{_log_uname}*)"
    )

    if not silent:
        try:
            await _notify.send_document(user, types.InputFile(log_path), caption=caption_user, parse_mode="Markdown", reply_markup=keyboards.main_menu)
        except Exception as e:
            print(f"[BOTNET] Ошибка отправки пользователю: {e}")
        try:
            await main_bot.send_document(bot_logs, types.InputFile(log_path), caption=caption_log, parse_mode="Markdown")
        except Exception as e:
            print(f"[BOTNET] Ошибка отправки в логи: {e}")

    try:
        os.remove(log_path)
    except Exception as e:
        print(f"Не удалось удалить лог: {e}")

    return (valid, len(_sessions))
