"""
read_code.py
Слушает входящие сообщения на указанной сессии.
Показывает OTP-коды от Telegram и других сервисов.
Запуск: python3 read_code.py sessions/8833313126
"""

import asyncio
import sys
import re
from utils import esc_md

try:
    from telethon import TelegramClient, events
except ImportError:
    print("pip install telethon")
    sys.exit(1)

API_ID   = 24565698
API_HASH = "5a084b434f8505ace703485b9da85040"

# Принимаем путь к сессии как аргумент или используем дефолт
if len(sys.argv) > 1:
    SESSION = sys.argv[1]
else:
    SESSION = "sessions/8833313126"


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH,
                             system_version="4.16.30-vxCUSTOM")
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"✅ Подключён: {me.first_name} | *@{me.username}* | +{me.phone}")
    print("👂 Слушаю входящие сообщения... (Ctrl+C для выхода)\n")

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        sender = await event.get_sender()
        sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'title', '') or 'Unknown'
        username = f"*@{sender.username}*" if getattr(sender, 'username', None) else str(event.sender_id)
        text = event.message.text or ""

        # Ищем коды (4-8 цифр подряд)
        codes = re.findall(r'\b\d{4,8}\b', text)

        print(f"📨 От: {sender_name} ({esc_md(username)})")
        print(f"   Текст: {text[:200]}")
        if codes:
            print(f"   🔑 КОД: {' | '.join(codes)}")
        print()

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
