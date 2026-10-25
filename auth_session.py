import asyncio
import sys
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

API_ID = 24565698
API_HASH = '5a084b434f8505ace703485b9da85040'

PHONE = '+989339732864'
SESSION_PATH = 'sessions/+989339732864'

async def main():
    import os
    os.makedirs('sessions', exist_ok=True)
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH, system_version='4.16.30-vxCUSTOM')
    await client.connect()

    if await client.is_user_authorized():
        print('Сессия уже авторизована!')
        await client.disconnect()
        return

    await client.send_code_request(PHONE)
    print(f'Код отправлен на {PHONE}')
    code = input('Введи код: ').strip()

    try:
        await client.sign_in(PHONE, code)
    except SessionPasswordNeededError:
        pw = input('Введи пароль 2FA: ').strip()
        await client.sign_in(password=pw)

    print(f'Авторизация успешна! Сессия сохранена: {SESSION_PATH}.session')
    await client.disconnect()

asyncio.run(main())
