"""
purge_frozen.py — удаляет сессии с FrozenMethodInvalidError.

Логика проверки:
  ReportRequest с заведомо неправильным peer →
    ChannelInvalidError   → аккаунт рабочий (метод доступен, peer просто неверный)
    FrozenMethodInvalidError → аккаунт заморожен → удаляем
    AuthKeyUnregisteredError / UserDeactivatedBanError → невалид → удаляем тоже

Запуск:
  python purge_frozen.py              — dry-run (только список)
  python purge_frozen.py --delete     — реально удалить
  python purge_frozen.py --workers 10 — параллельность (default 8)
"""

import os
import sys
import glob
import random
import asyncio
import argparse

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    AuthKeyUnregisteredError,
    UserDeactivatedBanError,
    UserDeactivatedError,
)
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import InputPeerChannel

SESSIONS_DIR = "./sessions"
API_LIST = [
    '24565698:5a084b434f8505ace703485b9da85040',
    '27904162:e7cba879b1c643ba77490bf328df5eab',
    '23037915:50f06f5b2223586fde0d1379ea91ebc7',
    '29512095:0b29a7d42fff002856b9bed64f7ec919',
    '25055016:25edf5b7becebe91a2d61fe8d9d9931b',
]

DEAD_EXCEPTIONS = (AuthKeyUnregisteredError, UserDeactivatedBanError, UserDeactivatedError)


def _get_sessions():
    paths = glob.glob(os.path.join(SESSIONS_DIR, "*.session"))
    return [os.path.splitext(os.path.basename(p))[0] for p in paths]


async def _check_one(session: str, sem: asyncio.Semaphore) -> tuple[str, str]:
    """Возвращает (session, статус): 'ok' | 'frozen' | 'dead' | 'flood' | 'error'"""
    async with sem:
        api_id, api_hash = random.choice(API_LIST).split(":", 1)
        client = TelegramClient(
            f"{SESSIONS_DIR}/{session}", int(api_id), api_hash,
            system_version='4.16.30-vxCUSTOM'
        )
        try:
            await asyncio.wait_for(client.connect(), timeout=10)
            if not await client.is_user_authorized():
                return session, "dead"

            # Заведомо неверный peer → ChannelInvalidError (ок) или FrozenMethodInvalidError (заморожен)
            dummy_peer = InputPeerChannel(channel_id=1, access_hash=0)
            try:
                await client(ReportRequest(peer=dummy_peer, id=[], option=b'', message=''))
                return session, "ok"  # вдруг прошло — тоже ок
            except Exception as e:
                name = type(e).__name__
                if "Frozen" in name:
                    return session, "frozen"
                if "ChannelInvalid" in name or "PeerIdInvalid" in name or "ChatIdInvalid" in name:
                    return session, "ok"
                if any(isinstance(e, t) for t in DEAD_EXCEPTIONS):
                    return session, "dead"
                if isinstance(e, FloodWaitError):
                    return session, f"flood:{e.seconds}"
                return session, f"error:{name}"
        except asyncio.TimeoutError:
            return session, "error:Timeout"
        except Exception as e:
            name = type(e).__name__
            if any(isinstance(e, t) for t in DEAD_EXCEPTIONS):
                return session, "dead"
            return session, f"error:{name}"
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


def _delete_session(session: str):
    for ext in (".session", ".session-journal"):
        path = os.path.join(SESSIONS_DIR, session + ext)
        if os.path.exists(path):
            os.remove(path)


async def main(do_delete: bool, workers: int):
    sessions = _get_sessions()
    total = len(sessions)
    print(f"Найдено сессий: {total}")
    print(f"Режим: {'УДАЛЕНИЕ' if do_delete else 'DRY-RUN (--delete чтобы удалить)'}")
    print("-" * 48)

    sem = asyncio.Semaphore(workers)
    tasks = [_check_one(s, sem) for s in sessions]

    ok = frozen = dead = flood = errors = 0
    to_delete = []

    done = 0
    for coro in asyncio.as_completed(tasks):
        session, status = await coro
        done += 1
        print(f"[{done}/{total}] {session} → {status}")

        if status == "ok":
            ok += 1
        elif status == "frozen":
            frozen += 1
            to_delete.append(session)
        elif status == "dead":
            dead += 1
            to_delete.append(session)
        elif status.startswith("flood"):
            flood += 1
        else:
            errors += 1

    print("\n" + "=" * 48)
    print(f"  Рабочих:    {ok}")
    print(f"  Заморожен:  {frozen}")
    print(f"  Мёртвых:    {dead}")
    print(f"  Флудов:     {flood}")
    print(f"  Ошибок:     {errors}")
    print(f"  К удалению: {len(to_delete)}")
    print("=" * 48)

    if to_delete:
        if do_delete:
            for s in to_delete:
                _delete_session(s)
                print(f"  ✅ Удалено: {s}")
            print(f"\nГотово. Удалено {len(to_delete)} сессий.")
        else:
            print("\nСессии для удаления (запусти с --delete):")
            for s in to_delete:
                print(f"  {s}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="Реально удалить сессии")
    parser.add_argument("--workers", type=int, default=8, help="Параллельность (default 8)")
    args = parser.parse_args()
    asyncio.run(main(args.delete, args.workers))
