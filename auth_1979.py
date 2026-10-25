"""
auth_1979.py — авторизация +19798145893, сессия сохраняется в sessions/
Запуск: python3 auth_1979.py
"""
import asyncio
from telethon import TelegramClient

PHONE   = '+19798145893'
SESSION = f'sessions/{PHONE.replace("+", "")}'
API_ID  = 24565698
API_HASH = '5a084b434f8505ace703485b9da85040'


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH, system_version='4.16.30-vxCUSTOM')
    await client.start(
        phone=lambda: PHONE,
        code_callback=lambda: input('Код из Telegram: '),
        password=lambda: input('2FA пароль (Enter если нет): ') or None,
    )
    me = await client.get_me()
    print(f'✅ Авторизован: {me.first_name} | +{me.phone}')
    print(f'📁 Сессия: {SESSION}.session')
    await client.disconnect()


asyncio.run(main())
