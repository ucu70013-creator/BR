import asyncio
from telethon import TelegramClient, events

API_ID   = 24565698
API_HASH = "5a084b434f8505ace703485b9da85040"
SESSION  = "aureport_sessions/+61493847044"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH,
                            system_version='4.16.30-vxCUSTOM')
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"✅ Сессия: {me.phone} | *@{me.username}*")
    print("👂 Слушаю все входящие сообщения...\n")

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        try:
            sender = await event.get_sender()
            name = getattr(sender, 'username', None) or getattr(sender, 'first_name', str(event.sender_id))
        except Exception:
            name = str(event.sender_id)
        print(f"[{name}]: {event.message.message}")

    await client.run_until_disconnected()

asyncio.run(main())
