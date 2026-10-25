"""
gateway_bot.py — Шлюзовые боты (до 3 шт.).

Каждый шлюзовой бот на /start:
  1. Смотрит — есть ли у юзера уже назначенное зеркало
  2. Если нет — берёт из БД свободное зеркало (min назначений)
  3. Проверяет токен через getMe
  4. Записывает user_id → mirror_token в mirror_assignments
  5. Шлёт юзеру ссылку на его "личный" бот

Запуск:
  GATEWAY_TOKEN_1=xxx GATEWAY_TOKEN_2=yyy python gateway_bot.py
"""

import asyncio
import os

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import db
from mirror_manager import validate_token

GATEWAY_TOKENS = [
    os.environ.get("GATEWAY_TOKEN_1", "").strip(),
    os.environ.get("GATEWAY_TOKEN_2", "").strip(),
    os.environ.get("GATEWAY_TOKEN_3", "").strip(),
]

INVITE_API = "http://127.0.0.1:8181/invite"
FREE_MIRROR_API = "http://127.0.0.1:8181/free_mirror"


async def get_invite_links() -> tuple[str, str]:
    """Получает свежие инвайт-ссылки у основного бота через HTTP API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(INVITE_API, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                return data.get("link1", ""), data.get("link2", "")
    except Exception:
        return "", ""


async def get_free_mirror_token(exclude: str = None) -> str | None:
    """Получает токен наименее загруженного ЗАПУЩЕННОГО зеркала через HTTP API."""
    try:
        params = {}
        if exclude:
            params["exclude"] = exclude
        async with aiohttp.ClientSession() as session:
            async with session.get(FREE_MIRROR_API, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data.get("token")
    except Exception:
        pass
    return None


def _build_gateway_dispatcher(token: str, gateway_id: int) -> tuple[Bot, Dispatcher]:
    gbot = Bot(token=token)
    dp = Dispatcher(gbot, storage=MemoryStorage())

    @dp.message_handler(commands=["start"])
    async def on_start(message: types.Message):
        uid = message.from_user.id
        first_name = message.from_user.first_name or "Пользователь"

        # Уже назначен?
        existing_token = await db.get_user_mirror(uid)
        if existing_token:
            username = await validate_token(existing_token)
            if username:
                clean = username.lstrip("@")
                await message.answer(
                    f"🤖 *Твой личный бот уже создан:*\n\n"
                    f"👉 [Запустить {username}](https://t.me/{clean})",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                return
            # Токен умер — переназначим
            existing_token = None

        # Анимация поиска
        msg = await message.answer("🔍 *Ищу токен...*", parse_mode="Markdown")
        await asyncio.sleep(1)

        # Получаем свободное зеркало из числа ЗАПУЩЕННЫХ через HTTP API
        mirror_token = await get_free_mirror_token()
        if not mirror_token:
            await gbot.edit_message_text(
                "❌ *Нет доступных зеркал. Попробуй позже.*",
                chat_id=uid, message_id=msg.message_id, parse_mode="Markdown",
            )
            return

        await gbot.edit_message_text(
            "⚙️ *Создаю бота...*",
            chat_id=uid, message_id=msg.message_id, parse_mode="Markdown",
        )
        await asyncio.sleep(1)

        # Проверяем токен
        username = await validate_token(mirror_token)
        if not username:
            # Мёртвый — берём следующий из запущенных
            mirror_token = await get_free_mirror_token(exclude=mirror_token)
            if mirror_token:
                username = await validate_token(mirror_token)

        if not username or not mirror_token:
            await gbot.edit_message_text(
                "❌ *Нет доступных зеркал. Попробуй позже.*",
                chat_id=uid, message_id=msg.message_id, parse_mode="Markdown",
            )
            return

        # Назначаем
        await db.assign_mirror_to_user(uid, mirror_token, gateway_id)

        clean = username.lstrip("@")
        user_count = await db.get_mirror_user_count(mirror_token)

        await gbot.edit_message_text(
            f"✅ *Привет, {first_name}!*\n\n"
            f"*Вот твой личный бот:*\n"
            f"👉 [Запустить {username}](https://t.me/{clean})\n\n"
            f"_Бот работает полностью — как основной._",
            chat_id=uid, message_id=msg.message_id,
            parse_mode="Markdown", disable_web_page_preview=True,
        )

    @dp.message_handler()
    async def on_any(message: types.Message):
        await message.answer(
            "👋 Нажми /start чтобы получить своего бота.",
            parse_mode="Markdown",
        )

    return gbot, dp


async def run_gateways():
    await db.init_db()
    await db.init_gateway_tables()

    tasks = []
    for i, token in enumerate(GATEWAY_TOKENS, 1):
        if not token:
            print(f"[GATEWAY] GATEWAY_TOKEN_{i} не задан, пропускаем", flush=True)
            continue
        gbot, gdp = _build_gateway_dispatcher(token, i)
        me = await gbot.get_me()
        # Сбрасываем вебхук и очищаем очередь апдейтов
        await gbot.delete_webhook(drop_pending_updates=True)
        # Ждём пока предыдущий long-poll умрёт
        for _ in range(6):
            try:
                await gbot.get_updates(offset=-1, timeout=0, limit=1)
                break
            except Exception:
                await asyncio.sleep(3)
        await asyncio.sleep(1)
        print(f"[GATEWAY] #{i} *@{me.username}* запущен", flush=True)
        tasks.append(asyncio.ensure_future(gdp.start_polling(timeout=20)))

    if not tasks:
        print("[GATEWAY] Нет токенов! Задай GATEWAY_TOKEN_1 / _2 / _3 в env", flush=True)
        return

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(run_gateways())
