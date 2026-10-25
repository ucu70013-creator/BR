"""
set_shadowvpn_avatar.py — устанавливает аватарку Shadow V2 VPN бота.
Запуск: python3 set_shadowvpn_avatar.py
"""
import asyncio
import os
import sys
import requests

IMG_URL  = "https://i.ibb.co/1GnZfHv5/Chat-GPT-Image-28-2026-21-42-28.png"
IMG_PATH = "/tmp/shadowvpn_avatar.png"
BOT_NAME = "Shadow V2 VPN"
BOT_DESC_RU       = "⚡ Быстрый VPN с серверами в 10 странах. Без логов, надёжное шифрование AES-256."
BOT_DESC_EN       = "⚡ Fast VPN with servers in 10 countries. No logs, AES-256 encryption."
BOT_SHORT_DESC_RU = "⚡ Быстрый VPN. Без логов, надёжное шифрование AES-256."
BOT_SHORT_DESC_EN = "⚡ Fast VPN. No logs, AES-256 encryption."


def download_avatar() -> bool:
    print(f"📥 Скачиваю аватарку...")
    try:
        r = requests.get(IMG_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if r.status_code == 200 and len(r.content) > 50000:
            with open(IMG_PATH, "wb") as f:
                f.write(r.content)
            print(f"   ✅ Скачано ({len(r.content)} байт)")
            return True
        print(f"   ❌ Ошибка ({r.status_code}, {len(r.content)} байт)")
    except Exception as e:
        print(f"   ❌ {e}")
    return False


async def set_photo_and_name(api_id: int, api_hash: str, bot_token: str):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.photos import UploadProfilePhotoRequest

    client = TelegramClient(StringSession(""), api_id, api_hash)
    print("🔗 Подключаюсь как бот...")
    await client.start(bot_token=bot_token)

    me = await client.get_me()
    print(f"✅ Вошёл как @{me.username}")

    # Имя через Bot API
    print(f"✏️  Меняю имя на «{BOT_NAME}»...")
    r = requests.post(
        f"https://api.telegram.org/bot{bot_token}/setMyName",
        json={"name": BOT_NAME}, timeout=10,
    )
    if r.json().get("ok"):
        print("✅ Имя обновлено!")
    else:
        print(f"   ⚠️ {r.json().get('description')}")

    # Описание (что умеет бот) через Bot API
    print("📝 Обновляю описание (что умеет бот)...")
    for lang, desc in [("ru", BOT_DESC_RU), ("en", BOT_DESC_EN)]:
        rd = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setMyDescription",
            json={"description": desc, "language_code": lang}, timeout=10,
        )
        if rd.json().get("ok"):
            print(f"   ✅ [{lang}] обновлено!")
        else:
            print(f"   ⚠️ [{lang}] {rd.json().get('description')}")

    # Краткое описание (в профиле бота) через Bot API
    print("📝 Обновляю краткое описание (профиль)...")
    for lang, desc in [("ru", BOT_SHORT_DESC_RU), ("en", BOT_SHORT_DESC_EN)]:
        rs = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setMyShortDescription",
            json={"short_description": desc, "language_code": lang}, timeout=10,
        )
        if rs.json().get("ok"):
            print(f"   ✅ [{lang}] обновлено!")
        else:
            print(f"   ⚠️ [{lang}] {rs.json().get('description')}")

    # Аватарка через MTProto
    print("🖼  Устанавливаю аватарку...")
    uploaded = await client.upload_file(IMG_PATH)
    await client(UploadProfilePhotoRequest(file=uploaded))
    print("✅ Аватарка установлена!")

    await client.disconnect()


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as cfg
    api_id   = int(cfg.AUREPORT_API_ID)
    api_hash = cfg.AUREPORT_API_HASH

    bot_token = input("🤖 Токен бота: ").strip()
    if not bot_token:
        print("❌ Токен пустой.")
        sys.exit(1)

    if not download_avatar():
        print("❌ Не удалось скачать аватарку.")
        sys.exit(1)

    asyncio.run(set_photo_and_name(api_id, api_hash, bot_token))

    try:
        os.remove(IMG_PATH)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
