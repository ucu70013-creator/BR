# coding: utf-8
"""
Запуск: python3 wait_code.py /root/BR/tida_sessions/+14702014831.session
Ждёт входящее сообщение с кодом и печатает его в терминал.
"""
import sys
import asyncio
import re
from telethon import TelegramClient, events

API_ID  = 24565698
API_HASH = "5a084b434f8505ace703485b9da85040"

SESSION = sys.argv[1] if len(sys.argv) > 1 else "+14702014831.session"

CODE_RE = re.compile(r"\b(\d{5,6})\b")


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    me = await client.get_me()
    print(f"[+] Подключено: {me.phone} | {me.first_name}")
    print("[*] Жду входящее сообщение с кодом...\n")

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        text = event.message.message or ""
        sender = await event.get_sender()
        name = getattr(sender, "username", None) or getattr(sender, "first_name", "?")

        match = CODE_RE.search(text)
        code_str = f"  КОД: {match.group(1)}" if match else ""

        print(f"[MSG] От: {name}")
        print(f"  Текст: {text[:200]}")
        if code_str:
            print(code_str)
        print()

    await client.run_until_disconnected()


asyncio.run(main())
