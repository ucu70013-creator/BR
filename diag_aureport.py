"""
Диагностика сессий aureport_sessions/
Показывает: авторизована ли сессия, имя аккаунта, телефон, премиум, дату флуд-вейта.

Запуск: python3 diag_aureport.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

API_ID   = int(config.AUREPORT_API_ID)
API_HASH = config.AUREPORT_API_HASH
DIR      = "aureport_sessions"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"


async def check_session(path: str) -> dict:
    from telethon import TelegramClient
    from telethon.errors import (
        AuthKeyUnregisteredError, UserDeactivatedError,
        UserDeactivatedBanError, FloodWaitError, SessionExpiredError,
    )

    name = os.path.basename(path)
    result = {"name": name, "ok": False, "info": "", "error": ""}

    try:
        client = TelegramClient(path, API_ID, API_HASH,
                                system_version="4.16.30-vxCUSTOM")
        await client.connect()

        if not await client.is_user_authorized():
            result["error"] = "НЕ АВТОРИЗОВАНА"
            await client.disconnect()
            return result

        me = await client.get_me()
        name_str = f"{me.first_name or ''} {me.last_name or ''}".strip()
        phone    = me.phone or "?"
        prem     = "👑 Premium" if getattr(me, "premium", False) else "free"
        result["ok"]   = True
        result["info"] = f"{name_str} | +{phone} | {prem} | id={me.id}"
        await client.disconnect()

    except (AuthKeyUnregisteredError, SessionExpiredError):
        result["error"] = "СЕССИЯ ИСТЕКЛА / невалидна"
    except (UserDeactivatedError, UserDeactivatedBanError):
        result["error"] = "АККАУНТ ЗАБАНЕН / деактивирован"
    except FloodWaitError as e:
        result["error"] = f"FLOOD WAIT {e.seconds}s"
    except Exception as e:
        result["error"] = str(e)

    return result


async def main():
    if not os.path.isdir(DIR):
        print(f"{RED}❌ Папка {DIR}/ не найдена{RESET}")
        sys.exit(1)

    sessions = sorted(
        os.path.join(DIR, f[:-8])
        for f in os.listdir(DIR) if f.endswith(".session")
    )

    if not sessions:
        print(f"{YELLOW}⚠️  В {DIR}/ нет .session файлов{RESET}")
        sys.exit(0)

    print(f"\n🔍 Диагностика {DIR}/ — {len(sessions)} сессий\n{'─'*60}")

    tasks = [check_session(s) for s in sessions]
    results = await asyncio.gather(*tasks)

    ok_count = 0
    for r in results:
        if r["ok"]:
            ok_count += 1
            print(f"{GREEN}✅ {r['name']:<30}{RESET} {r['info']}")
        else:
            print(f"{RED}❌ {r['name']:<30}{RESET} {r['error']}")

    print(f"\n{'─'*60}")
    print(f"Итог: {GREEN}{ok_count} рабочих{RESET} / {RED}{len(results)-ok_count} нерабочих{RESET} из {len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
