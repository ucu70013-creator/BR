"""
Brown V2 | utils.py
Общие утилиты.
"""
from datetime import datetime
import pytz
import time as _time

_MSK = pytz.timezone("Europe/Moscow")


def esc_md(s) -> str:
    """Escape underscores in user-provided strings for Telegram Markdown v1."""
    return str(s or "").replace("_", "\\_")


def now_msk() -> datetime:
    """Возвращает текущее время в московском часовом поясе (UTC+3)."""
    return datetime.now(_MSK).replace(tzinfo=None)


# ─── Прогресс-бар ─────────────────────────────────────────────────────────────

_BAR_LEN = 10


def _pbar_str(pct: int) -> str:
    filled = round(_BAR_LEN * pct / 100)
    return "[" + "▓" * filled + "▒" * (_BAR_LEN - filled) + "]"


class ProgressBar:
    """
    Живой прогресс-бар в Telegram.

    Использование:
        pb = ProgressBar(bot, user_id, total=len(sessions), title="🕸 Ботнет")
        await pb.start()
        # в цикле:
        await pb.update(done=i+1)
        # в конце:
        await pb.finish()   # удаляет прогресс-сообщение (итог шлёт сам метод)
    """

    def __init__(self, bot, user_id: int, total: int, title: str = "", silent: bool = False):
        self._bot = bot
        self._uid = user_id
        self._total = total
        self._title = title
        self._silent = silent
        self._msg_id: int | None = None
        self._start = _time.monotonic()
        self._last_edit: float = 0.0
        self._last_pct: int = -1

    def _text(self, done: int) -> str:
        pct = round(done / self._total * 100) if self._total else 100
        bar = _pbar_str(pct)
        eta = self._eta(done)
        eta_str = f" — {eta}" if eta else ""
        header = f"{self._title}\n" if self._title else ""
        return f"{header}{bar} *{pct}%*{eta_str}\n{done}/{self._total} сессий"

    def _eta(self, done: int) -> str:
        if done == 0:
            return ""
        elapsed = _time.monotonic() - self._start
        remaining = int(elapsed / done * (self._total - done))
        if remaining <= 0:
            return ""
        if remaining < 60:
            return f"~{remaining} сек"
        return f"~{remaining // 60} мин {remaining % 60} сек"

    async def start(self):
        if self._silent:
            return
        try:
            msg = await self._bot.send_message(
                self._uid, self._text(0), parse_mode="Markdown")
            self._msg_id = msg.message_id
            self._last_pct = 0
        except Exception:
            pass

    async def update(self, done: int):
        if not self._msg_id:
            return
        pct = round(done / self._total * 100) if self._total else 100
        # Обновляем только на каждые 10% или на 100%
        milestone = (pct // 10) * 10
        if milestone <= self._last_pct and done < self._total:
            return
        try:
            await self._bot.edit_message_text(
                self._text(done), self._uid, self._msg_id, parse_mode="Markdown")
            self._last_pct = milestone
        except Exception:
            pass

    async def finish(self):
        if not self._msg_id:
            return
        try:
            await self._bot.delete_message(self._uid, self._msg_id)
        except Exception:
            pass
