"""
Тест подключения TIDA сессии к @TIDAbot через резидентский прокси.
Запуск: python3 test_tida_connection.py
"""
import asyncio
import os
import socks
from telethon import TelegramClient, events

TIDA_SESSIONS_DIR = "tida_sessions"
API_ID = 24565698
API_HASH = "5a084b434f8505ace703485b9da85040"

# Только US прокси
PROXIES = [
    "socks5://kbchjaga:gjgyz024km8f@198.23.243.226:6361",
    "socks5://kbchjaga:gjgyz024km8f@38.154.185.97:6370",
    "socks5://kbchjaga:gjgyz024km8f@191.96.254.138:6185",
    "socks5://kbchjaga:gjgyz024km8f@198.46.161.42:5092",
]


def _parse_proxy(proxy_str):
    proxy_str = proxy_str.replace("socks5://", "")
    auth, hostport = proxy_str.rsplit("@", 1)
    user, password = auth.split(":", 1)
    host, port = hostport.rsplit(":", 1)
    return (socks.SOCKS5, host, int(port), True, user, password)


async def test_proxy(session_path, proxy_str):
    proxy = _parse_proxy(proxy_str)
    host = proxy_str.split("@")[1]
    print(f"\n🔄 Тестируем прокси: {host}")

    client = TelegramClient(session_path, API_ID, API_HASH, proxy=proxy, system_version="4.16.30-vxCUSTOM")

    try:
        await asyncio.wait_for(client.connect(), timeout=15)
    except Exception as e:
        print(f"  ❌ Не удалось подключиться: {e}")
        return False

    if not await client.is_user_authorized():
        print("  ❌ Сессия не авторизована")
        await client.disconnect()
        return False

    received = asyncio.Event()
    result = {"text": "", "ok": False}

    @client.on(events.NewMessage(from_users="TIDAbot"))
    async def handler(event):
        result["text"] = event.message.message
        if "not available" not in result["text"].lower():
            result["ok"] = True
        received.set()

    try:
        bot_entity = await client.get_entity("TIDAbot")
        await client.send_message(bot_entity, "/start")
    except Exception as e:
        print(f"  ❌ Ошибка отправки: {e}")
        await client.disconnect()
        return False

    try:
        await asyncio.wait_for(received.wait(), timeout=20)
        msg = result["text"][:200]
        if result["ok"]:
            print(f"  ✅ РАБОТАЕТ! Ответ: {msg}")
        else:
            print(f"  ⛔ Заблокирован: {msg}")
    except asyncio.TimeoutError:
        print("  ⏳ Таймаут — нет ответа")

    await client.disconnect()
    return result["ok"]


async def main():
    sessions = [f.replace(".session", "") for f in os.listdir(TIDA_SESSIONS_DIR) if f.endswith(".session")]
    if not sessions:
        print(f"❌ Нет сессий в {TIDA_SESSIONS_DIR}/")
        return

    session_path = os.path.join(TIDA_SESSIONS_DIR, sessions[0])
    print(f"📂 Сессия: {sessions[0]}")

    for proxy_str in PROXIES:
        ok = await test_proxy(session_path, proxy_str)
        if ok:
            print(f"\n✅ Рабочий прокси найден: {proxy_str.split('@')[1]}")
            return

    print("\n❌ Ни один US прокси не прошёл — попробуй другие прокси")


if __name__ == "__main__":
    asyncio.run(main())
