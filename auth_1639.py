"""
auth_1639.py — авторизация +16399517034, сессия сохраняется в sessions/
Запуск: python3 auth_1639.py
"""
import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

PHONE    = '+16399517034'
SESSION  = f'sessions/{PHONE.replace("+", "")}'
API_ID   = 24565698
API_HASH = '5a084b434f8505ace703485b9da85040'


async def main():
    # Удаляем старый файл сессии чтобы начать чисто
    if os.path.exists(SESSION + '.session'):
        os.remove(SESSION + '.session')
        print('🗑 Старая сессия удалена, начинаем заново')

    client = TelegramClient(SESSION, API_ID, API_HASH, system_version='4.16.30-vxCUSTOM')
    await client.connect()

    print(f'📤 Отправляем код на {PHONE}...')
    sent = await client.send_code_request(PHONE)
    print(f'✅ Код отправлен (тип: {type(sent.type).__name__})')

    code = input('Введи код: ').strip()
    try:
        await client.sign_in(PHONE, code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        print('⚠️  2FA включена.')
        pwd = input('2FA пароль: ').strip()
        if pwd:
            await client.sign_in(password=pwd)
        else:
            print('❌ Без пароля не войти.')
            await client.disconnect()
            return

    me = await client.get_me()
    print(f'✅ Авторизован: {me.first_name} | +{me.phone}')
    print(f'📁 Сессия: {SESSION}.session')
    await client.disconnect()


asyncio.run(main())
