import asyncio
import os
from telethon import TelegramClient

SESSION = 'user_session'
API_ID = 31467182
API_HASH = '20d357428e67033087cfc123cf954a71'
PHONE = '+33772290110'

async def main():
    if os.path.exists(SESSION + '.session'):
        os.remove(SESSION + '.session')
        print('Старая сессия удалена.')

    c = TelegramClient(SESSION, API_ID, API_HASH)

    await c.start(
        phone=lambda: PHONE,
        code_callback=lambda: input('Код из Telegram: '),
        password=lambda: input('2FA пароль: '),
    )

    me = await c.get_me()
    print(f'Успешно! Аккаунт: {me.first_name} (*@{me.username}*)')
    await c.disconnect()

asyncio.run(main())
