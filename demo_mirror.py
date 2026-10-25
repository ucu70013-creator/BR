"""
demo_mirror.py — Демо-зеркало Brown V2.

Запускается как первое зеркало, использует реальную инфраструктуру
(DB, капча, проверка подписки), но все методы репортов — симуляция:
реальные сессии не задействуются, лог генерируется на лету.

Запуск:
  DEMO_TOKEN=<токен_бота> python demo_mirror.py
"""

import asyncio
import io
import os
import random
from datetime import datetime

# ─── 1. Импортируем main — это создаёт Bot/Dispatcher, регистрирует хендлеры ─
#        Импорт безопасен: polling стартует только в if __name__ == '__main__'
import main as _main  # noqa: E402

# ─── 2. Общий контекст: сюда fake set_bot функции складывают Bot-инстанс ─────
_ctx: dict = {"bot": None}


def _fake_set_bot(b) -> None:
    _ctx["bot"] = b


# ─── 3. Генератор реалистичного лог-файла ─────────────────────────────────────
def _make_fake_log(method: str, target: str) -> str:
    n = random.randint(30, 55)
    header = [
        f"Brown V2 | {method}",
        f"Цель: {target}",
        f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        "─" * 46,
    ]
    pool = ["ДОСТАВЛЕНО"] * 7 + ["ОТКЛОНЕНО"] * 3
    rows = []
    for i in range(n):
        sess = f"acc_{random.randint(100_000, 999_999)}"
        rows.append(f"[{i + 1}/{n}] {sess} → {random.choice(pool)}")
    delivered = sum(1 for r in rows if "ДОСТАВЛЕНО" in r)
    footer = ["─" * 46, f"Итого доставлено: {delivered} / {n}"]
    return "\n".join(header + rows + footer)


# ─── 4. Единая async-заглушка: отправляет "работаю..." → ждёт → шлёт лог ─────
async def _fake_report(method_label: str, uid: int, target: str) -> None:
    from aiogram.types import InputFile

    bot = _ctx.get("bot")
    if bot is None or uid is None:
        return

    msg = await bot.send_message(uid, f"⏳ *{method_label}...*", parse_mode="Markdown")
    await asyncio.sleep(random.uniform(2.5, 4.5))
    try:
        await bot.delete_message(uid, msg.message_id)
    except Exception:
        pass

    log_text = _make_fake_log(method_label, target)
    ts = datetime.now().strftime("%H%M%S")
    filename = f"DEMO_{method_label.replace(' ', '_')}_{ts}.txt"
    doc = InputFile(io.BytesIO(log_text.encode("utf-8")), filename=filename)
    await bot.send_document(
        uid,
        doc,
        caption=f"✅ *{method_label} завершён (демо)*",
        parse_mode="Markdown",
    )


def _uid_from_args(args: tuple) -> int | None:
    """Ищет Telegram UID среди позиционных аргументов (int, 5–10 цифр)."""
    for a in args:
        if isinstance(a, int) and 10_000 < a < 10_000_000_000:
            return a
    return None


def _make_fake_fn(method_label: str, uid_idx: int | None = None):
    """Возвращает async-заглушку с нужной сигнатурой."""

    async def _fake(*args, **kwargs):
        uid = None
        if uid_idx is not None and uid_idx < len(args):
            uid = args[uid_idx]
        if uid is None:
            uid = _uid_from_args(args)
        if uid is None:
            uid = kwargs.get("uid") or kwargs.get("chat_id")
        target = str(args[0]) if args else "цель"
        await _fake_report(method_label, uid, target)

    return _fake


# ─── 5. Monkey-patch: set_bot-функции и исполнительные функции в main ─────────

# Подписка в демо — полностью убрана
async def _fake_check_subscription(uid: int) -> bool:
    return True

async def _fake_send_subscribe_required(uid: int, bot) -> None:
    import keyboards
    await bot.send_photo(
        uid, photo=open('material/menu.png', 'rb'),
        caption='>*Добро пожаловать в Brown V2\!*\n\n*Меню:*',
        parse_mode="MarkdownV2", reply_markup=keyboards.menu)

_main.check_subscription = _fake_check_subscription
_main.send_subscribe_required = _fake_send_subscribe_required

# set_bot — все перенаправляют Bot-инстанс в наш _ctx
for _attr in (
    "botnet_set_bot", "botnet_set_bot2",
    "set_bot_snos", "set_bot_channel", "set_bot_aureport",
    "set_bot_tida", "set_bot_bank", "set_bot_code",
    "set_bot_dsa", "set_bot_telegraph", "set_bot_profile",
    "set_bot_trap", "set_bot_stress", "set_bot_session",
):
    if hasattr(_main, _attr):
        setattr(_main, _attr, _fake_set_bot)

# Основные исполнительные функции (подписи взяты из main.py):
#   botnet_main(chat_username, message_id, uid, username, url)
_main.botnet_main = _make_fake_fn("Ботнет NORMAL", uid_idx=2)
#   botnet_main2(chat_username, message_id, uid, username, url)
_main.botnet_main2 = _make_fake_fn("Ботнет PREMIUM", uid_idx=2)
#   main_bot_snos(bot_link, uid, username)
_main.main_bot_snos = _make_fake_fn("Bot Snos", uid_idx=1)
#   main_channel_snos(channel_username, reason_key, message_id, uid, username)
_main.main_channel_snos = _make_fake_fn("Channel Snos", uid_idx=3)
#   main_aureport(link, uid, username)
_main.main_aureport = _make_fake_fn("Au Report", uid_idx=1)
#   main_tida(link, target, text, uid, username)
_main.main_tida = _make_fake_fn("TIDA", uid_idx=3)
#   process_bank_report(card, uid, username)
_main.process_bank_report = _make_fake_fn("Bank Report", uid_idx=1)
#   main_code_snos(code, uid, username, ...)
_main.main_code_snos = _make_fake_fn("Code Snos", uid_idx=1)
#   main_dsa_snos(link, uid, username, text)
_main.main_dsa_snos = _make_fake_fn("DSA Snos", uid_idx=1)
#   main_telegraph_snos(link, uid, username, text)
_main.main_telegraph_snos = _make_fake_fn("Telegraph Snos", uid_idx=1)
#   main_profile_snos(link, uid, username)
_main.main_profile_snos = _make_fake_fn("Profile Snos", uid_idx=1)
#   main_trap_snos(victim, uid, username)
_main.main_trap_snos = _make_fake_fn("Trap Snos", uid_idx=1)
#   main_session_snos(...)
if hasattr(_main, "main_session_snos"):
    _main.main_session_snos = _make_fake_fn("Session Snos", uid_idx=1)
#   send_bulk_emails(subject, text, uid, ...)
_main.send_bulk_emails = _make_fake_fn("Mail Snos", uid_idx=2)
#   web(link, text, uid, ...)
_main.web = _make_fake_fn("Web Snos", uid_idx=2)
#   main_bot_stress(...)
if hasattr(_main, "main_bot_stress"):
    _main.main_bot_stress = _make_fake_fn("Stress", uid_idx=1)


# ─── 6. Запуск как первое зеркало ─────────────────────────────────────────────
async def run_demo() -> None:
    import db
    from mirror_manager import _build_mirror_dispatcher

    DEMO_TOKEN = os.environ.get("DEMO_TOKEN", "").strip()
    if not DEMO_TOKEN:
        raise RuntimeError(
            "Укажи токен: DEMO_TOKEN=<токен> python demo_mirror.py"
        )

    await db.init_db()

    # Регистрируем демо-зеркало в БД если ещё нет
    if not await db.token_exists(DEMO_TOKEN):
        try:
            await db.add_mirror(0, DEMO_TOKEN, "@demo_mirror_bot")
            print("[DEMO] ✅ Демо-зеркало добавлено в БД", flush=True)
        except Exception as e:
            print(f"[DEMO] ⚠️ add_mirror: {e}", flush=True)
    else:
        print("[DEMO] ℹ️ Демо-зеркало уже есть в БД", flush=True)

    mirror_bot, dp = _build_mirror_dispatcher(DEMO_TOKEN)
    _ctx["bot"] = mirror_bot  # fallback если set_bot не вызвался

    print("[DEMO] 🚀 Запуск демо-зеркала...", flush=True)
    await mirror_bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    await dp.start_polling()


if __name__ == "__main__":
    asyncio.run(run_demo())
