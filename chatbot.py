# coding: utf-8
"""
chatbot.py — обработчик Telegram Business Bot API апдейтов.
Подключается пользователем через Настройки ТГ → Автоматизация чатов.

Команды (только в личных чатах):
  .botsnos          — бот-метод на текущего бота (только в чате с ботом)
  .snos             — AU Report на текущий чат (бот или пользователь)
  .session @юз +7   — Снос сессий (только в личном чате с пользователем)
  .spam N [текст]   — отправить N сообщений
  .haha N / .хаха N — отправить N смех-вариантов
"""

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp

import db
from utils import now_msk

logger = logging.getLogger(__name__)

# Единый экземпляр бота — устанавливается из main.py через set_bot()
_bot = None
# КД-словари — разделяем с main.py
_last_used_bot_snos: dict = {}
_last_used_aureport: dict = {}
_last_used_support: dict = {}

SPAM_LIMIT_FREE = 50
SPAM_LIMIT_PREMIUM = 200
HAHA_LIMIT = 50

HAHA_VARIANTS = [
    "АХАХА", "ВХАХА", "ХАХАХА", "ха-ха-ха", "лол", "КЕКУС",
    "ЛМАО", "💀", "хехе", "ахахахах", "LOL", "ХАХАХ",
    "кек", "ХАХА", "ахахаха", "хаха 💀", "ЛОЛ",
]


def set_bot(bot_instance, last_bot_snos: dict, last_aureport: dict, last_support: dict):
    global _bot, _last_used_bot_snos, _last_used_aureport, _last_used_support
    _bot = bot_instance
    _last_used_bot_snos = last_bot_snos
    _last_used_aureport = last_aureport
    _last_used_support = last_support


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _is_private_user(chat: dict) -> bool:
    return chat.get('type') == 'private' and not chat.get('is_bot', False)


def _is_private_bot(chat: dict) -> bool:
    return chat.get('type') == 'private' and chat.get('is_bot', False)


def _is_private_any(chat: dict) -> bool:
    return chat.get('type') == 'private'


def _fmt_rem(rem: timedelta) -> str:
    total = int(rem.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    if h > 0:
        return f"{h}ч {m}м" if m else f"{h}ч"
    return f"{m}м"


class _BotProxy:
    """Минимальный прокси: send_message / send_photo идут через нужный токен."""
    def __init__(self, token: str):
        self._token = token

    async def send_message(self, chat_id, text, **kwargs):
        return await _api_call('sendMessage', _token=self._token, chat_id=chat_id, text=text, **kwargs)

    async def send_photo(self, chat_id, photo, **kwargs):
        return await _api_call('sendPhoto', _token=self._token, chat_id=chat_id, photo=photo, **kwargs)

    async def send_document(self, chat_id, document, **kwargs):
        return await _api_call('sendDocument', _token=self._token, chat_id=chat_id, document=document, **kwargs)


def _notify_bot(bot_token: str):
    """Возвращает прокси-бот с правильным токеном, или основной бот если токен не передан."""
    if bot_token:
        return _BotProxy(bot_token)
    return _bot


async def _api_call(method: str, _token: str = '', **kwargs):
    """Прямой вызов Bot API через aiohttp (нужен business_connection_id)."""
    token = _token or (getattr(_bot, '_token', None) or '')
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=kwargs, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json()
    except Exception as e:
        logger.error(f"[CHATBOT] api_call {method} error: {e}")
        return {}


async def _edit_message(business_connection_id: str, chat_id: int, message_id: int, text: str, bot_token: str = ''):
    await _api_call(
        "editMessageText",
        _token=bot_token,
        business_connection_id=business_connection_id,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
    )


async def _send_message(business_connection_id: str, chat_id: int, text: str, bot_token: str = ''):
    await _api_call(
        "sendMessage",
        _token=bot_token,
        business_connection_id=business_connection_id,
        chat_id=chat_id,
        text=text,
    )


async def _delete_message(business_connection_id: str, chat_id: int, message_id: int, bot_token: str = ''):
    # Сначала пробуем deleteMessage (singular) — работает для исходящих
    r = await _api_call("deleteMessage", _token=bot_token,
                        business_connection_id=business_connection_id,
                        chat_id=chat_id, message_id=message_id)
    print(f"[CHATBOT] deleteMessage singular msg={message_id} result={r}", flush=True)
    if not (r or {}).get('result'):
        # Фолбэк: deleteMessages (plural) — работает для входящих
        r2 = await _api_call("deleteMessages", _token=bot_token,
                             business_connection_id=business_connection_id,
                             chat_id=chat_id, message_ids=[message_id])
        print(f"[CHATBOT] deleteMessages plural msg={message_id} result={r2}", flush=True)


# ─── Обработчики апдейтов ─────────────────────────────────────────────────────


async def _resolve_connection(connection_id: str, bot_token: str = '') -> int | None:
    """Ищет user_id в DB; если нет — авторегистрация через getBusinessConnection."""
    user_id = await db.chatbot_get_user_by_connection(connection_id)
    if user_id:
        return user_id
    logger.info(f"[CHATBOT] connection {connection_id!r} не в DB, пробуем getBusinessConnection")
    data = await _api_call('getBusinessConnection', _token=bot_token, business_connection_id=connection_id)
    logger.info(f"[CHATBOT] getBusinessConnection → {data}")
    if not data.get('ok'):
        return None
    conn = data.get('result', {})
    uid = conn.get('user', {}).get('id')
    if uid:
        await db.chatbot_save_connection(uid, connection_id)
        logger.info(f"[CHATBOT] Авторегистрация connection {connection_id} → user {uid}")
    return uid or None


async def handle_business_connection(raw: dict, bot_token: str = ''):
    """Вызывается при подключении / отключении чат-бота пользователем."""
    bc = raw.get('business_connection', {})
    user_id = bc.get('user', {}).get('id')
    connection_id = bc.get('id', '')
    is_enabled = bc.get('is_enabled', False)

    if not user_id:
        return

    if is_enabled:
        await db.chatbot_save_connection(user_id, connection_id)
        logger.info(f"[CHATBOT] Пользователь {user_id} подключил чат-бота (conn={connection_id})")
        try:
            await _api_call(
                'sendMessage',
                _token=bot_token,
                chat_id=user_id,
                text=(
                    "🤖 Чат-бот подключён ✔️\n\n"
                    "Доступные команды в личных чатах:\n\n"
                    ".botsnos — бот-метод на текущего бота\n"
                    ".snos — AU Report на цель\n"
                    ".session @юз +7номер — снос сессий\n"
                    ".spam N [текст] — авто-спам (макс 50/200)\n"
                    ".haha N / .хаха N — смех-спам (макс 50)\n\n"
                    "Чтобы отключить — зайди в Настройки ТГ → Мой профиль → Автоматизация чатов и удали бота.\n"
                    "Фото инструкция тут - https://t.me/BrownV2chat/2"
                ),
                parse_mode='HTML',
            )
        except Exception:
            pass
    else:
        await db.chatbot_remove_connection(user_id)
        logger.info(f"[CHATBOT] Пользователь {user_id} отключил чат-бота")


async def handle_business_message(raw: dict, bot_token: str = ''):
    """Все сообщения в чатах пользователя через Business API."""
    msg = raw.get('business_message', {})
    connection_id = msg.get('business_connection_id', '')
    chat = msg.get('chat', {})
    chat_id = chat.get('id', 0)
    message_id = msg.get('message_id', 0)
    from_user = msg.get('from', {})
    from_id = from_user.get('id', 0)
    text = msg.get('text', '') or msg.get('caption', '')

    user_id = await _resolve_connection(connection_id, bot_token)
    print(f"[CHATBOT] msg from={from_id} chat={chat_id} user_id={user_id} conn={connection_id[:8] if connection_id else ''}", flush=True)
    if not user_id:
        return

    is_outgoing = (from_id == user_id)

    if is_outgoing:
        # Обрабатываем команды
        if text and text.startswith('.'):
            await _handle_command(user_id, connection_id, chat, chat_id, message_id, text, bot_token)
        return

    # Входящее сообщение — кэшируем
    if text:
        try:
            await db.chatbot_cache_message(user_id, chat_id, message_id, from_id, text)
        except Exception:
            pass


async def handle_deleted_business_messages(raw: dict, bot_token: str = ''):
    """Удалённые сообщения — ищем в кэше и пересылаем пользователю."""
    data = raw.get('deleted_business_messages', {})
    connection_id = data.get('business_connection_id', '')
    chat = data.get('chat', {})
    chat_id = chat.get('id', 0)
    message_ids = data.get('message_ids', [])

    user_id = await _resolve_connection(connection_id, bot_token)
    if not user_id or not message_ids:
        return

    cached = await db.chatbot_get_cached_messages(user_id, chat_id, message_ids)
    if not cached:
        return

    chat_title = chat.get('title') or chat.get('username') or chat.get('first_name') or str(chat_id)
    lines = [f"🗑 *Удалённые сообщения* из чата *{chat_title}*:\n"]
    for row in cached:
        lines.append(f"• {row['text'][:300]}")

    try:
        await _api_call('sendMessage', _token=bot_token,
                        chat_id=user_id, text="\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"[CHATBOT] Ошибка отправки удалённых сообщений: {e}")


# ─── Обработка команд ─────────────────────────────────────────────────────────

async def _check_subscription(user_id: int) -> bool:
    """True если подписка активна."""
    try:
        user_data = await db.get_user(user_id)
        if not user_data:
            return False
        sub = user_data.get('subscribe')
        if not sub:
            return False
        if isinstance(sub, str):
            from datetime import datetime as _dt
            sub = _dt.strptime(str(sub)[:19], "%Y-%m-%d %H:%M:%S")
        return sub > now_msk()
    except Exception:
        return False


async def _handle_command(user_id: int, connection_id: str, chat: dict,
                          chat_id: int, message_id: int, text: str, bot_token: str = ''):
    cmd_lower = text.lower().strip()

    # ── Проверка подписки ─────────────────────────────────────────────────────
    from main import admins, no_kd
    if user_id not in admins and user_id not in no_kd:
        if not await _check_subscription(user_id):
            await _edit_message(connection_id, chat_id, message_id,
                                "❌ Нужна подписка для использования команд", bot_token)
            return

    # ── .botsnos ──────────────────────────────────────────────────────────────
    if cmd_lower.startswith('.botsnos'):
        await _cmd_botsnos(user_id, connection_id, chat, chat_id, message_id, text, bot_token)
        return

    # ── .snos ─────────────────────────────────────────────────────────────────
    if cmd_lower == '.snos':
        if not _is_private_any(chat):
            await _edit_message(connection_id, chat_id, message_id,
                                "❌ .snos работает только в личных чатах", bot_token)
            return
        await _cmd_snos(user_id, connection_id, chat, chat_id, message_id, bot_token)
        return

    # ── .session ──────────────────────────────────────────────────────────────
    if cmd_lower.startswith('.session'):
        if not _is_private_user(chat):
            await _edit_message(connection_id, chat_id, message_id,
                                "❌ .session работает только в личном чате с пользователем", bot_token)
            return
        await _cmd_session(user_id, connection_id, chat, chat_id, message_id, text, bot_token)
        return

    # ── .spam ─────────────────────────────────────────────────────────────────
    if cmd_lower.startswith('.spam'):
        if not _is_private_any(chat):
            return
        await _cmd_spam(user_id, connection_id, chat_id, message_id, text, bot_token)
        return

    # ── .haha / .хаха ─────────────────────────────────────────────────────────
    if cmd_lower.startswith('.haha') or cmd_lower.startswith('.хаха'):
        if not _is_private_any(chat):
            return
        await _cmd_haha(user_id, connection_id, chat_id, message_id, text, bot_token)
        return



# ─── .botsnos ─────────────────────────────────────────────────────────────────

async def _cmd_botsnos(user_id: int, connection_id: str, chat: dict, chat_id: int, message_id: int, text: str = '', bot_token: str = ''):
    from main import last_used_bot_snos, no_kd, admins
    from bot_snos import main_bot_snos

    # Парсим аргумент: .botsnos @username или .botsnos username
    parts = text.strip().split(None, 1)
    arg = parts[1].lstrip('@').strip() if len(parts) > 1 else ''
    target = arg or chat.get('username', '')

    if not target:
        await _edit_message(connection_id, chat_id, message_id,
                            "❌ Укажи username\nПример: .botsnos @GraphWorks", bot_token)
        return

    if user_id not in admins and user_id not in no_kd:
        if user_id in last_used_bot_snos and (now_msk() - last_used_bot_snos[user_id]) < timedelta(minutes=30):
            rem = timedelta(minutes=30) - (now_msk() - last_used_bot_snos[user_id])
            await _edit_message(connection_id, chat_id, message_id,
                                f"❌ КД ещё {_fmt_rem(rem)} ✘", bot_token)
            return

    await _edit_message(connection_id, chat_id, message_id, "Отправка начата ✔", bot_token)
    last_used_bot_snos[user_id] = now_msk()

    nb = _notify_bot(bot_token)

    async def run():
        try:
            user_data = await db.get_user(user_id)
            username = (user_data or {}).get('username', 'None')
            await main_bot_snos(f"@{target}", 'other', user_id, username, f"@{target}", notify_bot=nb)
        except Exception as e:
            logger.error(f"[CHATBOT] .botsnos error: {e}")
            try:
                await nb.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
            except Exception:
                pass

    asyncio.create_task(run())


# ─── .snos ────────────────────────────────────────────────────────────────────

async def _cmd_snos(user_id: int, connection_id: str, chat: dict, chat_id: int, message_id: int, bot_token: str = ''):
    from main import last_used_aureport, no_kd, admins
    from aureport_snos import main_aureport

    target = chat.get('username') or str(chat_id)

    if user_id not in admins and user_id not in no_kd:
        if user_id in last_used_aureport and (now_msk() - last_used_aureport[user_id]) < timedelta(minutes=30):
            rem = timedelta(minutes=30) - (now_msk() - last_used_aureport[user_id])
            await _edit_message(connection_id, chat_id, message_id,
                                f"❌ КД ещё {_fmt_rem(rem)} ✘", bot_token)
            return

    await _edit_message(connection_id, chat_id, message_id, "Отправка начата ✔", bot_token)
    last_used_aureport[user_id] = now_msk()

    nb = _notify_bot(bot_token)

    async def run():
        try:
            user_data = await db.get_user(user_id)
            username = (user_data or {}).get('username', 'None')
            await main_aureport(target, user_id, username, notify_bot=nb)
        except Exception as e:
            logger.error(f"[CHATBOT] .snos error: {e}")
            try:
                await nb.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
            except Exception:
                pass

    asyncio.create_task(run())


# ─── .session ─────────────────────────────────────────────────────────────────

async def _cmd_session(user_id: int, connection_id: str, chat: dict,
                       chat_id: int, message_id: int, text: str, bot_token: str = ''):
    from main import last_used_support, no_kd, admins
    from support_snos import main_support

    parts = text.strip().split()
    phone = ''
    target = ''

    for p in parts[1:]:
        if p.startswith('+') and any(c.isdigit() for c in p):
            phone = p
        elif p.startswith('@'):
            target = p.lstrip('@')
        elif p.isdigit():
            target = p

    if not target:
        target = chat.get('username') or str(chat_id)

    if not phone:
        await _edit_message(connection_id, chat_id, message_id,
                            "❌ Укажи номер телефона\nПример: .session @username +79001234567", bot_token)
        return

    if user_id not in admins and user_id not in no_kd:
        if user_id in last_used_support and (now_msk() - last_used_support[user_id]) < timedelta(hours=2):
            rem = timedelta(hours=2) - (now_msk() - last_used_support[user_id])
            await _edit_message(connection_id, chat_id, message_id,
                                f"❌ КД ещё {_fmt_rem(rem)} ✘", bot_token)
            return

    await _edit_message(connection_id, chat_id, message_id, "Отправка начата ✔", bot_token)
    last_used_support[user_id] = now_msk()

    nb = _notify_bot(bot_token)

    async def run():
        try:
            user_data = await db.get_user(user_id)
            username = (user_data or {}).get('username', 'None')
            await main_support(target, phone, user_id, username, notify_bot=nb)
        except Exception as e:
            logger.error(f"[CHATBOT] .session error: {e}")
            try:
                await nb.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")
            except Exception:
                pass

    asyncio.create_task(run())


# ─── .spam ────────────────────────────────────────────────────────────────────

async def _cmd_spam(user_id: int, connection_id: str, chat_id: int, message_id: int, text: str, bot_token: str = ''):
    parts = text.split(None, 2)
    try:
        n = int(parts[1]) if len(parts) > 1 else 1
    except ValueError:
        await _edit_message(connection_id, chat_id, message_id,
                            "❌ Укажи число\nПример: .spam 5 Привет!", bot_token)
        return

    spam_text = parts[2] if len(parts) > 2 else "."

    try:
        user_data = await db.get_user(user_id)
        premium = (user_data or {}).get('premium', 0)
    except Exception:
        premium = 0

    limit = SPAM_LIMIT_PREMIUM if premium else SPAM_LIMIT_FREE
    n = max(1, min(n, limit))

    await _delete_message(connection_id, chat_id, message_id, bot_token)

    async def run():
        for _ in range(n):
            try:
                await _send_message(connection_id, chat_id, spam_text, bot_token)
            except Exception:
                pass
            await asyncio.sleep(0.5)

    asyncio.create_task(run())


# ─── .haha / .хаха ───────────────────────────────────────────────────────────

async def _cmd_haha(user_id: int, connection_id: str, chat_id: int, message_id: int, text: str, bot_token: str = ''):
    import random
    parts = text.split(None, 1)
    try:
        n = int(parts[1]) if len(parts) > 1 else 5
    except ValueError:
        n = 5
    n = max(1, min(n, HAHA_LIMIT))

    await _delete_message(connection_id, chat_id, message_id, bot_token)

    async def run():
        for _ in range(n):
            try:
                await _send_message(connection_id, chat_id, random.choice(HAHA_VARIANTS), bot_token)
            except Exception:
                pass
            await asyncio.sleep(0.3)

    asyncio.create_task(run())


