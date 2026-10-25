"""
Brown V2 | stars_pay.py
Оплата Telegram Stars через @Hemoroyybot.
Сессия: aureport_sessions/+61435551379.session
Схема: Stars → @Hemoroyybot → USDT TON → наш адрес → проверяем tonapi.io
"""

import asyncio
import os
import random
import re
import string
import time

import aiohttp
from telethon import TelegramClient, events
from telethon.tl.types import KeyboardButtonCallback

import config

AUREPORT_DIR = "aureport_sessions"
STARS_SESSION = os.path.join(AUREPORT_DIR, "+61435551379")
HEMOMOY_BOT = "@Hemoroyybot"
TON_ADDRESS = "UQDeT6tcvKiwrR_fCa0ORJ_OOKPQbnvbzyB8l1YXzXK0iLCf"

# stars count per subscription tier
STARS_COUNT = {
    "1":  100,
    "3":  185,
    "7":  370,
    "30": 740,
    "60": 740,
}

# expected USDT payout (~$0.0108/star)
STARS_USDT = {
    "1":  1.0,
    "3":  2.0,
    "7":  4.0,
    "30": 8.0,
    "60": 8.0,
}


def gen_hash(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


async def _create_client() -> TelegramClient | None:
    try:
        client = TelegramClient(
            STARS_SESSION,
            int(config.AUREPORT_API_ID),
            config.AUREPORT_API_HASH,
            system_version="4.16.30-vxCUSTOM",
        )
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await client.is_user_authorized():
            await client.disconnect()
            print("[STARS] Сессия не авторизована", flush=True)
            return None
        return client
    except Exception as e:
        print(f"[STARS] Ошибка подключения: {e}", flush=True)
        return None


def _find_btn(msg, *keywords: str):
    """Ищет кнопку по ключевым словам (все должны совпасть)."""
    if not msg.reply_markup:
        return None
    for row in msg.reply_markup.rows:
        for btn in row.buttons:
            t = btn.text.lower()
            if all(k in t for k in keywords):
                return btn
    return None


async def _press(client, bot_entity, msg, btn) -> None:
    """Нажимает кнопку: inline → .click(), reply-keyboard → send text."""
    if isinstance(btn, KeyboardButtonCallback):
        await msg.click(text=btn.text)
    else:
        await client.send_message(bot_entity, btn.text)


async def _hemoroy_flow(client: TelegramClient, stars_amount: int, memo: str) -> str | None:
    """
    Проходит диалог с @Hemoroyybot кнопками и возвращает ссылку https://t.me/$...
    """
    msgs_queue: asyncio.Queue = asyncio.Queue()
    bot_entity = await client.get_entity(HEMOMOY_BOT)

    @client.on(events.NewMessage(from_users=bot_entity.id))
    async def _handler_new(event):
        await msgs_queue.put(event)

    @client.on(events.MessageEdited(from_users=bot_entity.id))
    async def _handler_edit(event):
        await msgs_queue.put(event)

    async def wait_msg(timeout: int = 30):
        return await asyncio.wait_for(msgs_queue.get(), timeout=timeout)

    pay_link = None
    try:
        # /start → ждём сообщение с кнопкой "Продать"
        await client.send_message(bot_entity, "/start")
        menu_msg = None
        for _ in range(6):
            msg = await wait_msg(timeout=15)
            print(f"[STARS] step0 text={msg.text[:80]!r} has_markup={bool(msg.reply_markup)}", flush=True)
            if _find_btn(msg, "продать"):
                menu_msg = msg
                break
        if not menu_msg:
            print("[STARS] Меню с кнопкой 'Продать' не найдено", flush=True)
            return None

        # Нажимаем кнопку "Продать зв..."
        await asyncio.sleep(0.5)
        await _press(client, bot_entity, menu_msg, _find_btn(menu_msg, "продать"))
        msg = await wait_msg()
        print(f"[STARS] step1 text={msg.text[:80]!r}", flush=True)

        # Вводим количество звёзд (текст, там нет кнопок)
        await asyncio.sleep(0.5)
        await client.send_message(bot_entity, str(stars_amount))
        msg = await wait_msg()
        print(f"[STARS] step2 text={msg.text[:80]!r}", flush=True)

        # Нажимаем кнопку method_sell_stars:TON
        await asyncio.sleep(0.5)
        btn = _find_btn(msg, "usdt", "ton") or _find_btn(msg, "ton")
        if btn:
            await _press(client, bot_entity, msg, btn)
        else:
            await client.send_message(bot_entity, "USDT TON")
        msg = await wait_msg()
        print(f"[STARS] step3 text={msg.text[:80]!r}", flush=True)

        # Вводим TON-адрес
        await asyncio.sleep(0.5)
        await client.send_message(bot_entity, TON_ADDRESS)
        msg = await wait_msg()
        print(f"[STARS] step4 text={msg.text[:80]!r}", flush=True)

        # Вводим memo
        await asyncio.sleep(0.5)
        await client.send_message(bot_entity, memo)

        # Собираем все сообщения от бота за 5 секунд после мемо
        collected = []
        for _ in range(6):
            try:
                m2 = await asyncio.wait_for(msgs_queue.get(), timeout=3)
                collected.append(m2)
                print(f"[STARS] step5 msg={m2.text[:100]!r}", flush=True)
            except asyncio.TimeoutError:
                break

        order_id = None
        for m2 in collected:
            if m2.text:
                oid = re.search(r'ID\s+заявки[:\s]+(\d+)', m2.text, re.IGNORECASE)
                if oid:
                    order_id = oid.group(1)
            if not pay_link:
                if m2.reply_markup:
                    for row in m2.reply_markup.rows:
                        for b in row.buttons:
                            url = getattr(b, "url", None)
                            if url and "t.me/$" in url:
                                pay_link = url
                                break
                if not pay_link and m2.text:
                    mt = re.search(r"https://t\.me/\$[\w\-]+", m2.text)
                    if mt:
                        pay_link = mt.group(0)

        print(f"[STARS] pay_link={pay_link} order_id={order_id}", flush=True)

    except asyncio.TimeoutError:
        print("[STARS] Timeout при диалоге с @Hemoroyybot", flush=True)
    except Exception as e:
        print(f"[STARS] Ошибка flow: {e}", flush=True)
    finally:
        client.remove_event_handler(_handler_new)
        client.remove_event_handler(_handler_edit)

    return pay_link, order_id


async def create_invoice(user_id: int, st: str) -> dict | None:
    """
    Создаёт инвойс через @Hemoroyybot.
    Возвращает {'link': str, 'hash': str, 'stars': int, 'order_id': str} или None при ошибке.
    """
    stars = STARS_COUNT.get(st)
    if stars is None:
        return None

    unique_hash = gen_hash(8)
    memo = f"{user_id}{unique_hash}"

    client = await _create_client()
    if not client:
        return None

    try:
        link, order_id = await _hemoroy_flow(client, stars, memo)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    if not link:
        return None

    return {"link": link, "hash": unique_hash, "stars": stars, "order_id": order_id or ""}


async def check_payment(user_id: int, unique_hash: str, st: str, order_id: str = "") -> tuple[bool, str | None]:
    """
    Проверяет оплату по двум каналам:
    1. Сообщения от @Hemoroyybot к нашей сессии (подтверждение выплаты по order_id)
    2. Fallback: tonapi.io JettonTransfer с memo и суммой ≥90% ожидаемой.
    """
    memo_expected = f"{user_id}{unique_hash}"

    # --- Канал 1: проверяем сообщения @Hemoroyybot нашей AU-сессии ---
    if order_id:
        client = await _create_client()
        if client:
            try:
                bot_entity = await client.get_entity(HEMOMOY_BOT)
                msgs = await client.get_messages(bot_entity, limit=50)
                for m in msgs:
                    if not m.text:
                        continue
                    text = m.text
                    # Ищем сообщение с нашим order_id И признаком выплаты
                    if order_id in text:
                        tl = text.lower()
                        if any(w in tl for w in ["выплат", "отправ", "завершен", "выполнен", "перевед", "paid", "sent", "completed"]):
                            print(f"[STARS] confirmed via TG msg order_id={order_id}", flush=True)
                            return True, f"tg_msg_{order_id}"
            except Exception as e:
                print(f"[STARS] TG msg check error: {e}", flush=True)
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    # --- Канал 2: tonapi.io JettonTransfer ---
    expected_usdt = STARS_USDT.get(st, 1.0)
    min_amount = int(expected_usdt * 0.90 * 1_000_000)  # USDT-TON: 6 decimals

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://tonapi.io/v2/accounts/{TON_ADDRESS}/events",
                params={"limit": "50", "subject_only": "true"},
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                data = await resp.json()

        for event in data.get("events", []):
            for action in event.get("actions", []):
                if action.get("type") != "JettonTransfer":
                    continue
                jt = action.get("JettonTransfer", {})
                comment = jt.get("comment", "")
                amount = int(jt.get("amount", "0"))
                if comment == memo_expected and amount >= min_amount:
                    tx_hash = event.get("event_id", memo_expected)
                    return True, tx_hash

    except Exception as e:
        print(f"[STARS] tonapi check error: {e}", flush=True)

    return False, None
