"""
update_mirrors_profile.py — обновляет имя / описание / аватарку всех зеркал.
Запуск: python3 update_mirrors_profile.py [MAIN_TOKEN]
"""
import asyncio, io, sys
sys.path.insert(0, ".")
import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest
import config, db

NAME       = "Brown V2"
DESC       = "Наш сайт - br-v2.com"
SHORT_DESC = "Наш сайт - br-v2.com"
MAIN_TOK   = sys.argv[1] if len(sys.argv) > 1 else config.TOKEN
API_ID     = int(config.AUREPORT_API_ID)
API_HASH   = config.AUREPORT_API_HASH
CONCUR_HTTP = 30   # параллельных HTTP запросов (name/desc)
CONCUR_TG   = 8    # параллельных Telethon сессий (photo)


async def download_avatar(session: aiohttp.ClientSession) -> bytes:
    async with session.get(f"https://api.telegram.org/bot{MAIN_TOK}/getMe") as r:
        resp = await r.json()
    if not resp.get("ok"):
        raise RuntimeError(f"getMe failed: {resp}")
    bot_id = resp["result"]["id"]

    async with session.get(
        f"https://api.telegram.org/bot{MAIN_TOK}/getUserProfilePhotos",
        params={"user_id": bot_id, "limit": 1}
    ) as r:
        result = (await r.json())["result"]
    if not result["total_count"]:
        raise RuntimeError("У главного бота нет аватарки")
    file_id = result["photos"][0][-1]["file_id"]

    async with session.get(
        f"https://api.telegram.org/bot{MAIN_TOK}/getFile",
        params={"file_id": file_id}
    ) as r:
        path = (await r.json())["result"]["file_path"]

    async with session.get(f"https://api.telegram.org/file/bot{MAIN_TOK}/{path}") as r:
        return await r.read()


async def set_text_fields(session: aiohttp.ClientSession, token: str) -> list[str]:
    errs = []
    for method, kw in [
        ("setMyName",             {"name": NAME}),
        ("setMyDescription",      {"description": DESC}),
        ("setMyShortDescription", {"short_description": SHORT_DESC}),
    ]:
        try:
            async with session.post(
                f"https://api.telegram.org/bot{token}/{method}",
                json=kw,
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                res = await r.json()
            if not res.get("ok"):
                errs.append(f"{method}: {res.get('description')}")
        except Exception as e:
            errs.append(f"{method}: {e}")
    return errs


async def set_photo_telethon(token: str, photo_bytes: bytes) -> str | None:
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.start(bot_token=token)
        buf = io.BytesIO(photo_bytes)
        buf.name = "avatar.jpg"
        uploaded = await client.upload_file(buf)
        await client(UploadProfilePhotoRequest(file=uploaded))
        return None
    except Exception as e:
        return f"setPhoto: {e}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def update(
    session: aiohttp.ClientSession,
    token: str,
    photo: bytes,
    http_sem: asyncio.Semaphore,
    tg_sem: asyncio.Semaphore,
):
    tag = token[:22] + "…"
    errs = []

    async with http_sem:
        errs.extend(await set_text_fields(session, token))

    async with tg_sem:
        err = await set_photo_telethon(token, photo)
        if err:
            errs.append(err)

    if errs:
        print(f"  ⚠  {tag}  —  {' | '.join(errs)}")
    else:
        print(f"  ✅ {tag}")


async def main():
    await db.init_db()
    tokens = await db.get_all_mirror_tokens()
    if not tokens:
        print("Зеркал нет."); return

    print(f"Зеркал: {len(tokens)}")
    connector = aiohttp.TCPConnector(limit=CONCUR_HTTP)
    async with aiohttp.ClientSession(connector=connector) as session:
        print("📥 Скачиваю аватарку главного бота…")
        photo = await download_avatar(session)
        print(f"   {len(photo):,} байт\n🔄 Обновляю…\n")

        http_sem = asyncio.Semaphore(CONCUR_HTTP)
        tg_sem   = asyncio.Semaphore(CONCUR_TG)
        await asyncio.gather(*[update(session, t, photo, http_sem, tg_sem) for t in tokens])

    print("\n✅ Готово.")


asyncio.run(main())
