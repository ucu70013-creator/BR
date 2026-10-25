"""
auth_qr.py — авторизация через QR-код
Запуск: python3 auth_qr.py SESSIONNAME
Пример: python3 auth_qr.py sessions/16399517034
"""
import asyncio
import sys
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

SESSION  = sys.argv[1] if len(sys.argv) > 1 else 'sessions/qr_session'
API_ID   = 24565698
API_HASH = '5a084b434f8505ace703485b9da85040'


def print_qr(url: str):
    """Печатает QR-код в терминал через qrcode."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print(f'\n📲 QR URL (вставь в браузер для генерации): {url}\n')
        print('Установи: pip install qrcode')


async def main():
    if os.path.exists(SESSION + '.session'):
        os.remove(SESSION + '.session')

    client = TelegramClient(SESSION, API_ID, API_HASH, system_version='4.16.30-vxCUSTOM')
    await client.connect()

    print('📲 Генерирую QR-код для входа...')
    print('Открой Swiftgram → Настройки → Устройства → Подключить устройство → сканируй QR\n')

    qr = await client.qr_login()
    print_qr(qr.url)
    print(f'\nURL: {qr.url}\n')

    try:
        await qr.wait(timeout=120)
    except SessionPasswordNeededError:
        pwd = input('2FA пароль: ').strip()
        await client.sign_in(password=pwd)
    except Exception as e:
        print(f'❌ Ошибка: {e}')
        await client.disconnect()
        return

    me = await client.get_me()
    print(f'\n✅ Авторизован: {me.first_name} | +{me.phone}')
    print(f'📁 Сессия: {SESSION}.session')
    await client.disconnect()


asyncio.run(main())
