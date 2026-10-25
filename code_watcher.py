import asyncio
import re
from telethon import TelegramClient, events

API_ID = 24565698
API_HASH = '5a084b434f8505ace703485b9da85040'
SESSION_PATH = 'sessions/+989339732864'

CODE_RE = re.compile(r'\b(\d{5,6})\b')

async def main():
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH, system_version='4.16.30-vxCUSTOM')
    await client.start()
    me = await client.get_me()
    print(f'Слежу за кодами на аккаунте: {me.first_name} ({me.phone})', flush=True)
    print('Жду сообщений от Telegram...', flush=True)

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        sender = await event.get_sender()
        sender_id = getattr(sender, 'id', None)
        sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', '') or str(sender_id)
        text = event.raw_text or ''

        codes = CODE_RE.findall(text)
        if codes or sender_id == 777000:
            print(f'\n{"="*40}', flush=True)
            print(f'От: {sender_name} (id={sender_id})', flush=True)
            print(f'Текст: {text}', flush=True)
            if codes:
                print(f'>>> КОД: {" / ".join(codes)} <<<', flush=True)
            print('='*40, flush=True)

    await client.run_until_disconnected()

asyncio.run(main())
