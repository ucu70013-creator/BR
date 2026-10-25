"""
check_sessions.py
Диагностика всех Telethon-сессий из папок sessions/, prem_sessions/,
aureport_sessions/, tida_sessions/, trap_session/
Показывает статус каждой, при вводе y удаляет невалидные.

Запуск: python check_sessions.py
"""

import asyncio
import os
import sys

try:
    from telethon import TelegramClient
    from telethon.errors import AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError
    from telethon.tl.functions.messages import ReportRequest
    from telethon.tl.types import InputPeerChannel
except ImportError:
    print("pip install telethon")
    sys.exit(1)

# ─── API credentials ──────────────────────────────────────────────────────────
API_ID   = 24565698
API_HASH = "5a084b434f8505ace703485b9da85040"

# ─── Папки с сессиями ─────────────────────────────────────────────────────────
SESSION_FOLDERS = [
    "sessions",
    "prem_sessions",
    "aureport_sessions",
    "tida_sessions",
    "trap_session",
]

TIMEOUT = 8
MAX_PARALLEL = 20  # параллельных проверок

# ─── Результаты ───────────────────────────────────────────────────────────────
results = []  # (path, folder, filename, status, info)


async def check_session(session_path: str, folder: str, filename: str) -> tuple:
    """
    Проверяет одну сессию.
    Возвращает (status, info):
      status: "ok" | "invalid" | "banned" | "error"
      info: строка с доп. инфо
    """
    client = TelegramClient(
        session_path, API_ID, API_HASH,
        system_version="4.16.30-vxCUSTOM"
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=TIMEOUT)
        authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=TIMEOUT)

        if not authorized:
            await client.disconnect()
            return "invalid", "не авторизован"

        # Получаем инфо о аккаунте
        try:
            me = await asyncio.wait_for(client.get_me(), timeout=TIMEOUT)
            if me:
                name = f"{me.first_name or ''} {me.last_name or ''}".strip()
                username = f"*@{me.username}*" if me.username else "нет юзера"
                phone = me.phone or "?"
                info = f"{name} | {username} | +{phone}"
            else:
                info = "нет данных"
        except Exception:
            info = "авторизован (инфо недоступно)"

        # Проверяем заморозку через фиктивный ReportRequest
        try:
            dummy = InputPeerChannel(channel_id=1, access_hash=0)
            await client(ReportRequest(peer=dummy, id=[], option=b'', message=''))
        except Exception as e:
            ename = type(e).__name__
            if "Frozen" in ename:
                await client.disconnect()
                return "frozen", f"заморожен ({ename})"
            # ChannelInvalid/PeerIdInvalid — аккаунт рабочий, метод доступен

        await client.disconnect()
        return "ok", info

    except (AuthKeyUnregisteredError,):
        try: await client.disconnect()
        except: pass
        return "invalid", "ключ отозван (AuthKeyUnregistered)"

    except (UserDeactivatedError, UserDeactivatedBanError):
        try: await client.disconnect()
        except: pass
        return "banned", "аккаунт удалён или забанен"

    except asyncio.TimeoutError:
        try: await client.disconnect()
        except: pass
        return "error", "таймаут"

    except Exception as e:
        try: await client.disconnect()
        except: pass
        short = str(e)[:60]
        return "error", short


async def main():
    # Собираем все сессии
    all_sessions = []
    for folder in SESSION_FOLDERS:
        if not os.path.exists(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if f.endswith(".session"):
                name = f.replace(".session", "")
                path = os.path.join(folder, name)
                all_sessions.append((path, folder, f))

    if not all_sessions:
        print("Сессий не найдено.")
        return

    total = len(all_sessions)
    print(f"\n{'='*60}")
    print(f"  Диагностика сессий | Всего: {total}")
    print(f"{'='*60}\n")

    # Проверяем параллельно пачками
    sem = asyncio.Semaphore(MAX_PARALLEL)

    async def bounded_check(session_path, folder, filename):
        async with sem:
            status, info = await check_session(session_path, folder, filename)
            return (session_path, folder, filename, status, info)

    tasks = [bounded_check(p, f, fn) for p, f, fn in all_sessions]
    checked = await asyncio.gather(*tasks)

    # Сортировка по числовому ID (старые первые) происходит в блоке вывода
    checked = list(checked)

    ok_count = 0
    invalid_count = 0
    frozen_count = 0
    error_count = 0
    bad_list = []

    # Извлекаем числовой ID из имени файла для сортировки
    def sort_key(item):
        path, folder, filename, status, info = item
        stem = filename.replace(".session", "").replace("_new", "").replace("_telethon", "")
        # Убираем + в начале (для aureport типа +61...)
        stem = stem.lstrip("+").replace(" ", "")
        try:
            return (folder, int(stem))
        except ValueError:
            return (folder, 0)

    checked = sorted(checked, key=sort_key)

    # Заголовок таблицы
    print(f"\n{'Сессия':<45} {'Папка':<20} {'Статус':<8} {'Ник':<20} {'Юз':<22} {'Номер'}")
    print("-" * 130)

    for path, folder, filename, status, info in checked:
        if status == "ok":
            ok_count += 1
            icon = "✅"
            # Парсим info: "Ник | @юз | +номер" или "Ник | нет юзера | +номер"
            parts = [p.strip() for p in info.split("|")]
            nick = parts[0] if len(parts) > 0 else "-"
            uz   = parts[1] if len(parts) > 1 else "-"
            num  = parts[2] if len(parts) > 2 else "-"
        elif status == "invalid":
            icon = "❌"
            invalid_count += 1
            bad_list.append((path, folder, filename, status, info))
            nick, uz, num = "не авторизован", "-", "-"
        elif status == "banned":
            icon = "🚫"
            invalid_count += 1
            bad_list.append((path, folder, filename, status, info))
            nick, uz, num = "забанен/удалён", "-", "-"
        elif status == "frozen":
            icon = "🧊"
            frozen_count += 1
            invalid_count += 1
            bad_list.append((path, folder, filename, status, info))
            nick, uz, num = "заморожен", "-", "-"
        else:
            icon = "⚠️ "
            error_count += 1
            bad_list.append((path, folder, filename, status, info))
            nick, uz, num = info[:30], "-", "-"

        stem = filename.replace(".session", "")
        print(f"{icon} {stem:<43} {folder:<20} {status:<8} {nick:<20} {uz:<22} {num}")

    print("-" * 130)
    print(f"\n{'='*60}")
    print(f"✅ Валидных   : {ok_count}")
    print(f"❌ Невалидных : {invalid_count - frozen_count}")
    print(f"🧊 Заморожен  : {frozen_count}")
    print(f"⚠️  Ошибок     : {error_count}")
    print(f"📦 Всего      : {total}\n")

    if not bad_list:
        print("Все сессии валидны!")
        return

    # Спрашиваем об удалении
    print(f"\nНевалидных сессий: {invalid_count} (+ {error_count} ошибок соединения)")
    print("Удалить все невалидные? (y/n/s - выбрать конкретные)\n  y = только invalid/banned, e = + ошибки/таймауты, s = выбрать вручную: ", end="", flush=True)
    choice = input().strip().lower()

    if choice == "y":
        deleted = 0
        for path, folder, filename, status, info in bad_list:
            if status == "error":
                continue
            session_file = path + ".session"
            journal_file = path + ".session-journal"
            try:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    deleted += 1
                if os.path.exists(journal_file):
                    os.remove(journal_file)
                print(f"  🗑 Удалено: {folder}/{filename} ({status}: {info})")
            except Exception as e:
                print(f"  ⚠️  Ошибка удаления {filename}: {e}")
        print(f"\nУдалено сессий: {deleted}")

    elif choice == "e":
        deleted = 0
        for path, folder, filename, status, info in bad_list:
            session_file = path + ".session"
            journal_file = path + ".session-journal"
            try:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    deleted += 1
                if os.path.exists(journal_file):
                    os.remove(journal_file)
                print(f"  🗑 Удалено: {folder}/{filename} ({status}: {info})")
            except Exception as e:
                print(f"  ⚠️  Ошибка удаления {filename}: {e}")
        print(f"\nУдалено сессий: {deleted}")

    elif choice == "s":
        print("\nВыбери что удалить (введи номера через запятую, например: 1,3,5):\n")
        for i, (path, folder, filename, status, info) in enumerate(bad_list, 1):
            print(f"  [{i}] {folder}/{filename} — {status}: {info}")
        print("\nНомера: ", end="", flush=True)
        nums_str = input().strip()
        try:
            nums = [int(x.strip()) for x in nums_str.split(",") if x.strip().isdigit()]
        except Exception:
            nums = []
        deleted = 0
        for n in nums:
            if 1 <= n <= len(bad_list):
                path, folder, filename, status, info = bad_list[n - 1]
                session_file = path + ".session"
                journal_file = path + ".session-journal"
                try:
                    if os.path.exists(session_file):
                        os.remove(session_file)
                        deleted += 1
                    if os.path.exists(journal_file):
                        os.remove(journal_file)
                    print(f"  🗑 Удалено: {folder}/{filename}")
                except Exception as e:
                    print(f"  ⚠️  Ошибка: {e}")
        print(f"\nУдалено сессий: {deleted}")

    else:
        print("Отменено. Сессии не удалены.")


if __name__ == "__main__":
    asyncio.run(main())
