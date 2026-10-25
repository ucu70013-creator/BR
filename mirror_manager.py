"""
Brown V2 | mirror_manager.py
Зеркальные боты — полный функционал как основной бот.
Callback делегируется в handle_callback из main.py.
"""

import asyncio
import os
import random
import time as _time
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InputFile, ParseMode
from aiogram.utils.exceptions import Unauthorized, TerminatedByOtherGetUpdates

import config
import db
import keyboards
import stars_pay as _stars_pay
from captcha import generate_captcha_text, generate_captcha_image
from translations import t
from utils import now_msk, esc_md

_running_mirrors: dict[str, asyncio.Task] = {}
_mirror_bots: dict[str, Bot] = {}  # token → Bot instance
# Вложенный словарь: {mirror_token: {user_id: captcha_code}}
# Предотвращает коллизии когда один uid открыл несколько зеркал
_mirror_captcha_codes: dict[str, dict[int, str]] = {}

MIRROR_LIMIT = 100  # максимум активных зеркал одновременно
INVITE_API = "http://127.0.0.1:8181/invite"
CHECK_API  = "http://127.0.0.1:8181/check"


async def _api_get_invite_links() -> tuple[str, str]:
    """Получает свежие инвайт-ссылки у основного бота по HTTP."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(INVITE_API, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                return data.get("link1", ""), data.get("link2", "")
    except Exception:
        return "", ""


async def _api_check_subscription(uid: int) -> bool:
    """Проверяет подписку юзера через HTTP API основного бота."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CHECK_API, params={"uid": uid},
                                   timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                return bool(data.get("subscribed", False))
    except Exception:
        return True  # при ошибке пропускаем (чтоб не блокировать юзера)


class MirrorCaptchaFSM(StatesGroup):
    code = State()

class MirrorCreateFSM(StatesGroup):
    token = State()


async def _mirror_send_subscribe(uid: int, mirror_bot: Bot):
    """Отправляет юзеру требование подписки, получая ссылки через HTTP API."""
    try:
        lang = await db.get_lang(uid)
    except Exception:
        lang = 'ru'
    link1, link2 = await _api_get_invite_links()
    from translations import t
    import config as _cfg
    if not link1:
        link1 = _cfg.bot_channel_link
    if not link2:
        link2 = _cfg.bot_channel2_link
    markup = _build_sub_markup(link1, link2, lang)
    await mirror_bot.send_message(uid, t('sub_required', lang), parse_mode="Markdown", reply_markup=markup)


def _build_sub_markup(link1: str, link2: str, lang: str):
    from aiogram import types as _types
    from translations import t
    markup = _types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        _types.InlineKeyboardButton(t('sub_btn_1', lang), url=link1),
        _types.InlineKeyboardButton(t('sub_btn_2', lang), url=link2),
        _types.InlineKeyboardButton(t('sub_btn_check', lang), callback_data='start_check_sub'),
    )
    return markup


def _build_mirror_dispatcher(token: str) -> tuple[Bot, Dispatcher]:
    mirror_bot = Bot(token=token)
    storage = MemoryStorage()
    dp = Dispatcher(mirror_bot, storage=storage)

    # Подключаем middleware тех. работ
    from main import MaintenanceMiddleware
    dp.middleware.setup(MaintenanceMiddleware())

    # ─── /admin команда ───────────────────────────────────────────────────────
    @dp.message_handler(commands=['admin'])
    async def mirror_admin(message: types.Message):
        if message.chat.id not in config.ADMINS:
            return
        import main as main_module
        import os as _os
        session_folder = 'sessions'
        session_folder_prem = 'prem_sessions'
        users_count = await main_module.db.get_users_count()
        sessions_count = len(_os.listdir(session_folder)) if _os.path.exists(session_folder) else 0
        sessions_count_prem = len(_os.listdir(session_folder_prem)) if _os.path.exists(session_folder_prem) else 0
        subscribers_count = await main_module.db.get_subscribers_count()
        mirrors_count = await main_module.db.get_mirrors_count()
        reports_users_count = await main_module.db.get_users_with_reports_count()
        try:
            with open("mails.txt", "r", encoding="utf-8") as f:
                mails_count = len([l for l in f if l.strip()])
        except FileNotFoundError:
            mails_count = 0
        text = (
            ">🤖 *Админ меню:*\n\n📊 *Статистика:*\n"
            f"*├─👥 Всего пользователей:* {users_count}\n"
            f"*├─💳 С подпиской:* {subscribers_count}\n"
            f"*├─🎯 С репортами:* {reports_users_count}\n"
            f"*├─🪞 Зеркал:* {mirrors_count}\n"
            f"*├─🕒 Сессий в ботнете:* {sessions_count}\n"
            f"*├─👑 Сессий в премиум ботнете:* {sessions_count_prem}\n"
            f"*├─✉️ Почт добавлено:* {mails_count}\n\n"
            "*/promo PROMOCODE DAYS ACTIVATIONS \- создать промокод*\n"
            "*/on \- включить бота*\n*/off \- выключить бота*\n"
            "*/addwl ID \- добавить в вайтлист*\n"
            "*/addtargetwl @username \- добавить цель в WL*\n"
            "*/rmtargetwl @username \- убрать цель из WL*\n"
            "*/listtargetwl \- список целей WL*"
        )
        import keyboards as _kb
        await mirror_bot.send_message(message.chat.id, text, reply_markup=_kb.admin_markup, parse_mode="MarkdownV2")

    @dp.message_handler(commands=['test'])
    async def mirror_cmd_test(message: types.Message):
        if message.from_user.id not in config.ADMINS:
            return
        import main as _main
        await _main._run_test_session(message.from_user.id, mirror_bot)

    @dp.message_handler(commands=['testsess'])
    async def mirror_cmd_testsess(message: types.Message):
        if message.from_user.id not in config.ADMINS:
            return
        from support_snos import main_support
        await main_support(
            target="@oishois",
            phone="+61455112151",
            uid=message.from_user.id,
            username=message.from_user.username or "",
            notify_bot=mirror_bot,
            log_bot=mirror_bot,
            log_channel_id=config.bot_logs,
            quick=True,
        )

    @dp.message_handler(commands=['mail'])
    async def mirror_cmd_mail(message: types.Message):
        if message.from_user.id not in config.ADMINS:
            return
        parts = message.text.split(maxsplit=1)
        sub_cmd = parts[1].strip() if len(parts) > 1 else ""
        if sub_cmd != "test":
            await mirror_bot.send_message(message.chat.id, "ℹ️ Использование: `/mail test`", parse_mode="Markdown")
            return
        from mail_snos import load_mails, send_email_async, spin_subject, spin_text, mask_email
        mails = load_mails()
        if not mails:
            await mirror_bot.send_message(message.chat.id, "❌ *mails.txt пуст или не найден*", parse_mode="Markdown")
            return
        receiver = "fyckwefi@gmail.com"
        await mirror_bot.send_message(
            message.chat.id,
            f"📤 *Тест почты*\n└─ Аккаунтов: `{len(mails)}`\n└─ Получатель: `{receiver}`\n\n⏳ Отправляю без задержки...",
            parse_mode="Markdown"
        )
        success = 0
        fail = 0
        lines = []
        for sender in mails:
            sender_login, sender_pass = sender.split(":", 1)
            ok, err = await send_email_async(sender_login, receiver, spin_subject("test"), spin_text("test"), sender_pass)
            masked = mask_email(sender_login)
            if ok:
                success += 1
                lines.append(f"✅ {masked}")
            else:
                fail += 1
                lines.append(f"❌ {masked} — {err[:60]}")
        report = "\n".join(lines[:30])
        if len(lines) > 30:
            report += f"\n...и ещё {len(lines) - 30}"
        await mirror_bot.send_message(
            message.chat.id,
            f"📊 *Результат теста*\n✅ Успешно: `{success}`\n❌ Ошибок: `{fail}`\n\n{report}",
            parse_mode="Markdown"
        )

    # ─── /addtargetwl, /rmtargetwl, /listtargetwl ────────────────────────────
    @dp.message_handler(commands=['addtargetwl'])
    async def mirror_addtargetwl(message: types.Message):
        if message.chat.id not in config.ADMINS:
            return
        parts = message.text.split()
        if len(parts) != 2:
            await mirror_bot.send_message(message.chat.id, "❗️ */addtargetwl @username*", parse_mode="Markdown")
            return
        pattern = parts[1].lstrip('@').lower()
        await db.add_target_whitelist(pattern, message.from_user.id)
        await mirror_bot.send_message(message.chat.id,
            f"✅ **@{pattern}* добавлен в белый список целей!*", parse_mode="Markdown")

    @dp.message_handler(commands=['rmtargetwl'])
    async def mirror_rmtargetwl(message: types.Message):
        if message.chat.id not in config.ADMINS:
            return
        parts = message.text.split()
        if len(parts) != 2:
            await mirror_bot.send_message(message.chat.id, "❗️ */rmtargetwl @username*", parse_mode="Markdown")
            return
        pattern = parts[1].lstrip('@').lower()
        await db.remove_target_whitelist(pattern)
        await mirror_bot.send_message(message.chat.id,
            f"🗑 **@{pattern}* удалён из белого списка!*", parse_mode="Markdown")

    @dp.message_handler(commands=['listtargetwl'])
    async def mirror_listtargetwl(message: types.Message):
        if message.chat.id not in config.ADMINS:
            return
        patterns = await db.get_target_whitelist()
        if not patterns:
            await mirror_bot.send_message(message.chat.id, "📋 *Белый список целей пуст.*", parse_mode="Markdown")
            return
        lines = ["📋 *Белый список целей:*\n"] + [f"• *@{p}*" for p in patterns]
        await mirror_bot.send_message(message.chat.id, "\n".join(lines), parse_mode="Markdown")

    async def _send_and_pin_site_msg(uid: int):
        try:
            msg = await mirror_bot.send_message(
                uid,
                "🔗 *Бот удален?* — @Brown\_V2 \| [br\-v2\.com](https://br-v2.com)",
                parse_mode="MarkdownV2",
                disable_web_page_preview=False
            )
            await mirror_bot.pin_chat_message(uid, msg.message_id, disable_notification=True)
        except Exception as e:
            print(f"[MIRROR PIN] Ошибка: {e}", flush=True)

    # ─── /start ───────────────────────────────────────────────────────────────
    @dp.message_handler(commands=['start'], state='*')
    async def mirror_start(message: types.Message, state: FSMContext):
        uid = message.chat.id
        await state.finish()  # сбрасываем любое старое состояние
        try:
            await db.touch_user_mirror(uid, token)
        except Exception:
            pass
        if await db.is_blocked(uid):
            return
        is_new = not await db.user_exists(uid)
        await db.add_user(uid)
        if not await db.is_verified(uid):
            code = generate_captcha_text()
            _mirror_captcha_codes.setdefault(token, {})[uid] = code
            img = generate_captcha_image(code)
            await mirror_bot.send_photo(
                uid, photo=img,
                caption=f"*Привет, {message.from_user.first_name}!*\n\n*Докажи, что ты не робот 🤖*\n*└─ Введи код с картинки:*",
                parse_mode="Markdown")
            await state.set_state(MirrorCaptchaFSM.code.state)
            if is_new:
                args = message.get_args()
                if args and args.startswith("ref_"):
                    await state.update_data(ref_arg=args)
            return
        await mirror_bot.send_sticker(uid, InputFile("AnimatedSticker.tgs"))
        # Проверяем подписку через HTTP API основного бота
        if not await _api_check_subscription(uid):
            await _mirror_send_subscribe(uid, mirror_bot)
            return
        await _send_and_pin_site_msg(uid)
        await mirror_bot.send_photo(
            uid, photo=open('material/menu.png', 'rb'),
            caption='>*Добро пожаловать в Brown V2\!*\n\n*Меню:*',
            parse_mode="MarkdownV2", reply_markup=keyboards.menu)

    # ─── Капча ────────────────────────────────────────────────────────────────
    @dp.message_handler(state=MirrorCaptchaFSM.code)
    async def mirror_captcha(message: types.Message, state: FSMContext):
        uid = message.from_user.id
        token_codes = _mirror_captcha_codes.get(token, {})
        if message.text.strip().lower() == token_codes.get(uid, "").lower():
            fsm_data = await state.get_data()
            await state.finish()
            _mirror_captcha_codes.get(token, {}).pop(uid, None)
            await db.set_verified(uid)
            ref_arg = fsm_data.get('ref_arg')
            if ref_arg and ref_arg.startswith("ref_"):
                try:
                    referrer_id = int(ref_arg[4:])
                    if referrer_id != uid and await db.user_exists(referrer_id):
                        await db.set_referrer(uid, referrer_id)
                        new_count = await db.increment_referral_count(referrer_id)
                        await mirror_bot.send_message(
                            referrer_id,
                            f"👥 *По вашей ссылке зарегистрировался новый пользователь!*\n"
                            f"*└─ Всего рефералов: {new_count}*",
                            parse_mode="Markdown")
                except Exception:
                    pass
            await mirror_bot.send_sticker(uid, InputFile("AnimatedSticker.tgs"))
            # Проверяем подписку через HTTP API основного бота
            if not await _api_check_subscription(uid):
                await _mirror_send_subscribe(uid, mirror_bot)
                return
            await _send_and_pin_site_msg(uid)
            await mirror_bot.send_photo(
                uid, photo=open('material/menu.png', 'rb'),
                caption='>*Добро пожаловать в Brown V2\!*\n\n*Меню:*',
                parse_mode="MarkdownV2", reply_markup=keyboards.menu)
        else:
            code = generate_captcha_text()
            _mirror_captcha_codes.setdefault(token, {})[uid] = code
            await mirror_bot.send_photo(
                uid, photo=generate_captcha_image(code),
                caption="*❌ Неверно! Попробуй ещё раз:*", parse_mode="Markdown")

    _MIRROR_SUB_MAP = {
        "1":          ("1",  "1",   "sub_1d",      "100"),
        "3":          ("2",  "3",   "sub_3d",      "175"),
        "7":          ("4",  "7",   "sub_7d",      "350"),
        "30":         ("8",  "30",  "sub_30d",     "700"),
        "60":         ("8",  "60",  "sub_60d",     "900"),
        "premupgrade":("5",  "1",   "sub_premium", "400"),
    }
    _MIRROR_YM_WALLET = "4100118677444773"
    _MIRROR_TON_ADDRESS = "UQDeT6tcvKiwrR_fCa0ORJ_OOKPQbnvbzyB8l1YXzXK0iLCf"
    _MIRROR_TON_PRICES = {"1": "1", "3": "2", "7": "3", "30": "6", "60": "8"}
    _MIRROR_TON_NANO_TO_DAYS = {
        1_000_000_000: 1,
        2_000_000_000: 3,
        3_000_000_000: 7,
        6_000_000_000: 30,
        8_000_000_000: 60,
    }

    async def _mirror_edit(callback_query, caption, markup):
        try:
            await mirror_bot.edit_message_caption(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                caption=caption, parse_mode="MarkdownV2", reply_markup=markup)
        except Exception:
            await mirror_bot.edit_message_text(
                caption, chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                parse_mode="MarkdownV2", reply_markup=markup)

    async def _mirror_create_pay_link(ym_url: str) -> str:
        try:
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as _s:
                async with _s.post(
                    'http://127.0.0.1:8080/register_pay',
                    json={'url': ym_url},
                    timeout=_aiohttp.ClientTimeout(total=5)
                ) as resp:
                    data = await resp.json()
                    return f"https://br-v2.com/pay/{data['token']}"
        except Exception:
            return ym_url

    _MIRROR_SUB_LABELS = {
        "1": "1 день", "3": "3 дня", "7": "7 дней",
        "30": "30 дней", "60": "60 дней",
        "premupgrade": "Premium", "test": "Тест",
    }

    async def _mirror_create_cispay(user_id: int, st: str) -> str | None:
        _, _, _, amount_rub = _MIRROR_SUB_MAP[st]
        label = _MIRROR_SUB_LABELS.get(st, st)
        order_id = f"cispay_{user_id}_{st}_{int(_time.time())}"
        try:
            async with aiohttp.ClientSession() as _s:
                async with _s.post(
                    "https://api.cispay.app/payments",
                    json={
                        "amount": int(amount_rub) * 100,
                        "currency": "RUB",
                        "order_id": order_id,
                        "payment_method": "SBP",
                        "customer_id": str(user_id),
                        "description": f"Подписка BR V2 · {label}",
                    },
                    headers={
                        "X-Shop-ID": config.CISPAY_SHOP_ID,
                        "X-Api-Key": config.CISPAY_API_KEY,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
            return data.get("payment_url")
        except Exception as _e:
            print(f"[MIRROR] cisPay create error: {_e}")
            return None

    async def _mirror_create_xrocket(user_id: int, st: str) -> str | None:
        amount_usd, _, _, _ = _MIRROR_SUB_MAP[st]
        label = _MIRROR_SUB_LABELS.get(st, st)
        payload = f"xrocket_{user_id}_{st}_{int(_time.time())}"
        try:
            async with aiohttp.ClientSession() as _s:
                async with _s.post(
                    "https://pay.api.xrocket.exchange/api/v1/invoices",
                    json={
                        "priceAmount": amount_usd,
                        "priceCurrency": "USDT",
                        "description": f"Подписка BR V2 · {label}",
                        "payload": payload,
                        "clientInvoiceId": payload,
                    },
                    headers={"Authorization": f"Bearer {config.XROCKET_API_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    status = resp.status
                    data = await resp.json()
                    print(f"[MIRROR] xRocket response [{status}]: {data}")
            link = data.get("links", {}).get("telegramBotLink")
            return link
        except Exception as _e:
            print(f"[MIRROR] xRocket create error: {_e}")
        return None

    # ─── Оплата sub_ ──────────────────────────────────────────────────────────
    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('sub_'), state='*')
    async def mirror_sub(callback_query: types.CallbackQuery):
        try:
            await callback_query.answer()
            st = callback_query.data.split('_', 1)[1]
            if st not in _MIRROR_SUB_MAP:
                return
            amount_usd, _, _, amount_rub = _MIRROR_SUB_MAP[st]
            label = _MIRROR_SUB_LABELS.get(st, st)
            method_markup = types.InlineKeyboardMarkup(row_width=1)
            method_markup.add(
                types.InlineKeyboardButton(f"🇷🇺 СБП — {amount_rub} ₽", callback_data=f'pay_cispay_{st}'),
                types.InlineKeyboardButton(f"🚀 xRocket — {amount_usd} USDT", callback_data=f'pay_xrocket_{st}'),
            )
            if st in _MIRROR_TON_PRICES:
                method_markup.add(types.InlineKeyboardButton(f"💎 TON — {_MIRROR_TON_PRICES[st]} TON", callback_data=f'pay_ton_{st}'))
            if st in _stars_pay.STARS_COUNT:
                method_markup.add(types.InlineKeyboardButton(f"⭐ Звёзды — {_stars_pay.STARS_COUNT[st]} Stars", callback_data=f'pay_stars_{st}'))
            method_markup.add(keyboards.back)
            await _mirror_edit(
                callback_query,
                (
                    f"💳 *Выберите способ оплаты*\n\n"
                    f"*└─ Тариф:* {label}\n\n"
                    f"После оплаты подписка активируется автоматически\\."
                ),
                method_markup,
            )
        except Exception as e:
            print(f"[MIRROR] sub: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('pay_cispay_'), state='*')
    async def mirror_pay_cispay(callback_query: types.CallbackQuery):
        try:
            await callback_query.answer()
            user_id = callback_query.from_user.id
            st = callback_query.data[len('pay_cispay_'):]
            if st not in _MIRROR_SUB_MAP:
                return
            _, _, _, amount_rub = _MIRROR_SUB_MAP[st]
            label = _MIRROR_SUB_LABELS.get(st, st)
            payment_url = None
            if config.CISPAY_SHOP_ID and config.CISPAY_API_KEY:
                payment_url = await _mirror_create_cispay(user_id, st)
            if not payment_url:
                err_markup = types.InlineKeyboardMarkup(row_width=1)
                err_markup.add(keyboards.back)
                await _mirror_edit(callback_query,
                    "⚠️ *Не удалось создать счёт\\.*\n\nПопробуйте позже или свяжитесь с поддержкой\\.",
                    err_markup)
                return
            pay_markup = types.InlineKeyboardMarkup(row_width=1)
            pay_markup.add(types.InlineKeyboardButton(f"💳 Оплатить {amount_rub} ₽ через СБП", url=payment_url))
            pay_markup.add(keyboards.back)
            await _mirror_edit(callback_query,
                (
                    f"📲 *Оплата через СБП*\n\n"
                    f"*└─ Тариф:* {label}\n"
                    f"*└─ Сумма:* {amount_rub} ₽\n\n"
                    f"Нажмите кнопку ниже — откроется форма СБП\\.\n"
                    f"После оплаты подписка активируется автоматически\\."
                ),
                pay_markup)
        except Exception as e:
            print(f"[MIRROR] pay_cispay: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('pay_xrocket_'), state='*')
    async def mirror_pay_xrocket(callback_query: types.CallbackQuery):
        try:
            await callback_query.answer()
            user_id = callback_query.from_user.id
            st = callback_query.data[len('pay_xrocket_'):]
            if st not in _MIRROR_SUB_MAP:
                return
            amount_usd, _, _, _ = _MIRROR_SUB_MAP[st]
            label = _MIRROR_SUB_LABELS.get(st, st)
            invoice_url = None
            if config.XROCKET_API_KEY:
                invoice_url = await _mirror_create_xrocket(user_id, st)
            if not invoice_url:
                err_markup = types.InlineKeyboardMarkup(row_width=1)
                err_markup.add(keyboards.back)
                await _mirror_edit(callback_query,
                    "⚠️ *Не удалось создать счёт\\.*\n\nПопробуйте позже или свяжитесь с поддержкой\\.",
                    err_markup)
                return
            pay_markup = types.InlineKeyboardMarkup(row_width=1)
            pay_markup.add(types.InlineKeyboardButton(f"🚀 Оплатить {amount_usd} USDT в xRocket", url=invoice_url))
            pay_markup.add(keyboards.back)
            await _mirror_edit(callback_query,
                (
                    f"🚀 *Оплата через xRocket*\n\n"
                    f"*└─ Тариф:* {label}\n"
                    f"*└─ Сумма:* {amount_usd} USDT\n\n"
                    f"Нажмите кнопку ниже — откроется Telegram бот xRocket\\.\n"
                    f"После оплаты подписка активируется автоматически\\."
                ),
                pay_markup)
        except Exception as e:
            print(f"[MIRROR] pay_xrocket: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('pay_crypto_'), state='*')
    async def mirror_pay_crypto(callback_query: types.CallbackQuery):
        try:
            await callback_query.answer()
        except Exception as e:
            print(f"[MIRROR] pay_crypto: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('pay_sbp_'), state='*')
    async def mirror_pay_sbp(callback_query: types.CallbackQuery):
        try:
            await callback_query.answer()
        except Exception as e:
            print(f"[MIRROR] pay_sbp: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('sbp_paid_'), state='*')
    async def mirror_sbp_paid(callback_query: types.CallbackQuery):
        try:
            await callback_query.answer()
        except Exception as e:
            print(f"[MIRROR] sbp_paid: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('pay_ton_'), state='*')
    async def mirror_pay_ton(callback_query: types.CallbackQuery):
        try:
            user_id = callback_query.from_user.id
            st = callback_query.data[len('pay_ton_'):]
            if st not in _MIRROR_SUB_MAP:
                await callback_query.answer()
                return
            await callback_query.answer()
            label = _MIRROR_SUB_LABELS.get(st, st)
            ton_amount = _MIRROR_TON_PRICES.get(st, "?")
            pay_markup = types.InlineKeyboardMarkup(row_width=1)
            pay_markup.add(
                types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f'check_ton_{st}'),
                keyboards.back,
            )
            await _mirror_edit(
                callback_query,
                (
                    f"💎 *Оплата через TON \\(Gram\\)*\n\n"
                    f"*└─ Тариф:* {label}\n"
                    f"*└─ Сумма:* {ton_amount} TON\n\n"
                    f"📋 *Адрес кошелька:*\n"
                    f"`{_MIRROR_TON_ADDRESS}`\n\n"
                    f"🔖 *Комментарий \\(Memo\\):*\n"
                    f"`{user_id}`\n\n"
                    f"⚠️ *ВАЖНО:* Без комментария перевод не будет засчитан\\!\n\n"
                    f"После оплаты нажмите кнопку ниже\\."
                ),
                pay_markup,
            )
        except Exception as e:
            print(f"[MIRROR] pay_ton: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('check_ton_'), state='*')
    async def mirror_check_ton(callback_query: types.CallbackQuery):
        try:
            user_id = callback_query.from_user.id
            st = callback_query.data[len('check_ton_'):]
            if st not in _MIRROR_SUB_MAP:
                await callback_query.answer()
                return
            await callback_query.answer(text="🔍 Проверяем...")
            ton_amount = _MIRROR_TON_PRICES.get(st, "?")
            found_hash = None
            found_days = None
            try:
                async with aiohttp.ClientSession() as _s:
                    async with _s.get(
                        "https://toncenter.com/api/v2/getTransactions",
                        params={"address": _MIRROR_TON_ADDRESS, "limit": "50"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        data = await resp.json()
                for tx in data.get("result", []):
                    in_msg = tx.get("in_msg", {})
                    comment = in_msg.get("message", "").strip()
                    value = int(in_msg.get("value", 0))
                    tx_hash = tx.get("transaction_id", {}).get("hash", "")
                    if comment != str(user_id):
                        continue
                    days = _MIRROR_TON_NANO_TO_DAYS.get(value)
                    if days is None:
                        continue
                    if await db.is_invoice_used(tx_hash):
                        continue
                    found_hash = tx_hash
                    found_days = days
                    break
            except Exception as _e:
                print(f"[MIRROR] check_ton toncenter error: {_e}")

            if not found_hash:
                err_markup = types.InlineKeyboardMarkup(row_width=1)
                err_markup.add(
                    types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f'check_ton_{st}'),
                    keyboards.back,
                )
                await _mirror_edit(
                    callback_query,
                    (
                        f"❌ *Оплата не найдена*\n\n"
                        f"Убедитесь, что:\n"
                        f"• Перевод сделан на правильный адрес\n"
                        f"• В комментарии указан ваш ID: `{user_id}`\n"
                        f"• Сумма: {ton_amount} TON\n\n"
                        f"Транзакции обновляются с задержкой\\. Попробуйте через минуту\\."
                    ),
                    err_markup,
                )
                return

            await db.mark_invoice_used(found_hash, user_id)
            new_date = (now_msk() + timedelta(days=found_days)).strftime("%Y-%m-%d %H:%M:%S")
            await db.set_subscribe(user_id, new_date)

            referrer_id = await db.get_referrer_id(user_id)
            if referrer_id:
                bonus_days = max(1, int(found_days * 0.1))
                ref_new_date = (now_msk() + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
                await db.set_subscribe(referrer_id, ref_new_date)
                try:
                    await mirror_bot.send_message(
                        referrer_id,
                        f"💰 *Реферальный бонус\\!*\n"
                        f"*└─ Ваш реферал купил подписку*\n"
                        f"*└─ Вам начислено: \\+{bonus_days} день подписки*",
                        parse_mode="MarkdownV2")
                except Exception:
                    pass

            label = _MIRROR_SUB_LABELS.get(st, st)
            back_markup = types.InlineKeyboardMarkup(row_width=1)
            back_markup.add(keyboards.back)
            await _mirror_edit(
                callback_query,
                (
                    f"✅ *Оплата получена\\!*\n\n"
                    f"*└─ Подписка активирована:* {label}\n\n"
                    f"Спасибо за покупку\\!"
                ),
                back_markup,
            )
        except Exception as e:
            print(f"[MIRROR] check_ton: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('pay_stars_'), state='*')
    async def mirror_pay_stars(callback_query: types.CallbackQuery):
        try:
            user_id = callback_query.from_user.id
            st = callback_query.data[len('pay_stars_'):]
            if st not in _MIRROR_SUB_MAP or st not in _stars_pay.STARS_COUNT:
                await callback_query.answer()
                return
            await callback_query.answer()
            label = _MIRROR_SUB_LABELS.get(st, st)
            stars = _stars_pay.STARS_COUNT[st]

            wait_markup = types.InlineKeyboardMarkup(row_width=1)
            wait_markup.add(keyboards.back)
            await _mirror_edit(
                callback_query,
                (
                    f"⭐ *Оплата через Telegram Stars*\n\n"
                    f"*└─ Тариф:* {label}\n"
                    f"*└─ Сумма:* {stars} Stars\n\n"
                    f"⏳ Создаём счёт\\.\\.\\."
                ),
                wait_markup,
            )

            result = await _stars_pay.create_invoice(user_id, st)
            if not result or not result.get("link"):
                err_markup = types.InlineKeyboardMarkup(row_width=1)
                err_markup.add(keyboards.back)
                await _mirror_edit(
                    callback_query,
                    "⚠️ *Не удалось создать счёт\\.*\n\nПопробуйте позже или выберите другой способ оплаты\\.",
                    err_markup,
                )
                return

            pay_link = result["link"]
            unique_hash = result["hash"]
            order_id = result.get("order_id", "")

            pay_markup = types.InlineKeyboardMarkup(row_width=1)
            pay_markup.add(
                types.InlineKeyboardButton(f"⭐ Оплатить {stars} Stars", url=pay_link),
                types.InlineKeyboardButton("✅ Я оплатил", callback_data=f'check_stars_{st}_{unique_hash}_{order_id}'),
                keyboards.back,
            )
            await _mirror_edit(
                callback_query,
                (
                    f"⭐ *Оплата через Telegram Stars*\n\n"
                    f"*└─ Тариф:* {label}\n"
                    f"*└─ Сумма:* {stars} Stars\n\n"
                    f"Нажмите кнопку ниже — откроется диалог для оплаты\\.\n"
                    f"После оплаты нажмите *«Я оплатил»*\\."
                ),
                pay_markup,
            )
        except Exception as e:
            print(f"[MIRROR] pay_stars: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('check_stars_'), state='*')
    async def mirror_check_stars(callback_query: types.CallbackQuery):
        try:
            user_id = callback_query.from_user.id
            parts = callback_query.data[len('check_stars_'):].split('_', 2)
            if len(parts) < 2:
                await callback_query.answer()
                return
            st = parts[0]
            unique_hash = parts[1]
            order_id = parts[2] if len(parts) > 2 else ""
            if st not in _MIRROR_SUB_MAP:
                await callback_query.answer()
                return
            await callback_query.answer(text="🔍 Проверяем...")

            found, tx_hash = await _stars_pay.check_payment(user_id, unique_hash, st, order_id)

            if not found:
                err_markup = types.InlineKeyboardMarkup(row_width=1)
                err_markup.add(
                    types.InlineKeyboardButton("✅ Я оплатил", callback_data=f'check_stars_{st}_{unique_hash}_{order_id}'),
                    keyboards.back,
                )
                stars = _stars_pay.STARS_COUNT.get(st, "?")
                await _mirror_edit(
                    callback_query,
                    (
                        f"❌ *Оплата не найдена*\n\n"
                        f"Убедитесь что перевод завершён\\.\n"
                        f"Транзакции обновляются с задержкой 1\\-3 мин\\.\n"
                        f"*└─ Ожидаем:* {stars} Stars\n\n"
                        f"Попробуйте через минуту\\."
                    ),
                    err_markup,
                )
                return

            if await db.is_invoice_used(tx_hash):
                await callback_query.answer(text="✅ Уже активировано!", show_alert=True)
                return

            await db.mark_invoice_used(tx_hash, user_id)
            _, days_str, _, _ = _MIRROR_SUB_MAP[st]
            found_days = int(days_str)
            new_date = (now_msk() + timedelta(days=found_days)).strftime("%Y-%m-%d %H:%M:%S")
            await db.set_subscribe(user_id, new_date)

            referrer_id = await db.get_referrer_id(user_id)
            if referrer_id:
                bonus_days = max(1, int(found_days * 0.1))
                ref_new_date = (now_msk() + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
                await db.set_subscribe(referrer_id, ref_new_date)
                try:
                    await mirror_bot.send_message(
                        referrer_id,
                        f"💰 *Реферальный бонус\\!*\n"
                        f"*└─ Ваш реферал купил подписку*\n"
                        f"*└─ Вам начислено: \\+{bonus_days} день подписки*",
                        parse_mode="MarkdownV2")
                except Exception:
                    pass

            label = _MIRROR_SUB_LABELS.get(st, st)
            back_markup = types.InlineKeyboardMarkup(row_width=1)
            back_markup.add(keyboards.back)
            await _mirror_edit(
                callback_query,
                (
                    f"✅ *Оплата получена\\!*\n\n"
                    f"*└─ Подписка активирована:* {label}\n\n"
                    f"Спасибо за покупку\\!"
                ),
                back_markup,
            )
        except Exception as e:
            print(f"[MIRROR] check_stars: {e}")

    @dp.callback_query_handler(lambda c: c.data and c.data.startswith('check_status_'), state='*')
    async def mirror_check_status(callback_query: types.CallbackQuery):
        try:
            from pyCryptoPayAPI import pyCryptoPayAPI
            _crypto = pyCryptoPayAPI(api_token=config.CRYPTO, result_as_class=False)
            parts = callback_query.data.split('_')
            invoice_id, sub_type, sub_days = parts[2], parts[3], parts[4]
            user_id = callback_query.from_user.id
            _lang = await db.get_lang(user_id)
            old_invoice = await asyncio.to_thread(_crypto.get_invoices, invoice_ids=invoice_id)
            if old_invoice['items'][0]['status'] != "paid":
                await mirror_bot.send_message(user_id, t('pay_not_received', _lang), parse_mode=ParseMode.MARKDOWN)
                return
            if await db.is_invoice_used(invoice_id):
                await mirror_bot.send_message(user_id, t('pay_already_processed', _lang), parse_mode=ParseMode.MARKDOWN)
                return
            await db.mark_invoice_used(invoice_id, user_id)
            try:
                await mirror_bot.edit_message_caption(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    caption=t('pay_thanks', _lang), parse_mode="MarkdownV2",
                    reply_markup=keyboards.back_markup)
            except Exception:
                pass
            if sub_type != "premupgrade":
                new_date = (now_msk() + timedelta(days=int(sub_days))).strftime("%Y-%m-%d %H:%M:%S")
                await db.set_subscribe(user_id, new_date)
                referrer_id = await db.get_referrer_id(user_id)
                if referrer_id:
                    bonus_days = max(1, int(int(sub_days) * 0.1))
                    ref_new_date = (now_msk() + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
                    await db.set_subscribe(referrer_id, ref_new_date)
                    await mirror_bot.send_message(
                        referrer_id,
                        f"💰 *Реферальный бонус!*\n"
                        f"*└─ Ваш реферал купил подписку*\n"
                        f"*└─ Вам начислено: +{bonus_days} день подписки*",
                        parse_mode="Markdown")
            else:
                await db.set_premium(user_id, 1)
        except Exception as e:
            print(f"[MIRROR] check_status: {e}")

    # ─── Главный callback — делегируем в handle_callback из main.py ───────────
    @dp.callback_query_handler(lambda call: True, state='*')
    async def mirror_callback(call: types.CallbackQuery, state: FSMContext):
        from main import handle_callback
        await handle_callback(call, mirror_bot, dp, state)

    # ─── FSM создания зеркала ─────────────────────────────────────────────────
    @dp.message_handler(state=MirrorCreateFSM.token, content_types=types.ContentTypes.TEXT)
    async def mirror_create_token(message: types.Message, state: FSMContext):
        uid = message.from_user.id
        new_token = message.text.strip()

        if new_token.startswith('/'):
            await state.finish()
            if new_token.startswith('/start'):
                await db.add_user(uid)
                if not await db.is_verified(uid):
                    code = generate_captcha_text()
                    _mirror_captcha_codes.setdefault(token, {})[uid] = code
                    img = generate_captcha_image(code)
                    await mirror_bot.send_photo(uid, photo=img,
                        caption=f"*Привет, {message.from_user.first_name}!*\n\n*Докажи, что ты не робот 🤖*\n*└─ Введи код с картинки:*",
                        parse_mode="Markdown")
                    await state.set_state(MirrorCaptchaFSM.code.state)
                    return
                await mirror_bot.send_sticker(uid, InputFile("AnimatedSticker.tgs"))
                await mirror_bot.send_photo(uid, photo=open('material/menu.png', 'rb'),
                    caption='>*Добро пожаловать в Brown V2\!*\n\n*Меню:*',
                    parse_mode="MarkdownV2", reply_markup=keyboards.menu)
            else:
                await mirror_bot.send_message(uid, "❌ *Отменено.*", parse_mode="Markdown")
            return

        if ':' not in new_token or len(new_token) < 30:
            await state.finish()
            await mirror_bot.send_message(uid,
                "❌ *Неверный формат токена!*\n*Пример:* 1234567890:ABCdef...",
                parse_mode="Markdown")
            return

        await state.finish()

        if await db.token_exists(new_token):
            await mirror_bot.send_message(uid, "❌ *Этот токен уже зарегистрирован!*", parse_mode="Markdown")
            return

        wait_msg = await mirror_bot.send_message(uid, "⏳ *Проверяем токен...*", parse_mode="Markdown")
        bot_username = await validate_token(new_token)
        try:
            await mirror_bot.delete_message(uid, wait_msg.message_id)
        except Exception:
            pass

        if not bot_username:
            await mirror_bot.send_message(uid,
                "❌ *Токен невалидный!* Проверь и попробуй снова.", parse_mode="Markdown")
            return

        await db.add_mirror(uid, new_token, bot_username)
        await start_mirror(new_token)

        mirror_count = await db.count_user_mirrors(uid)
        bonus_msg = ""
        if mirror_count >= 2 and not await db.get_mirror_bonus_given(uid):
            await db.add_free_reports(uid, 1)
            await db.set_mirror_bonus_given(uid)
            bonus_msg = "\n🎯 *Бонус: +1 бесплатный репорт за 2 зеркала!*"

        await mirror_bot.send_message(
            uid,
            f"✅ *Зеркало создано!*\n\n"
            f"🤖 *Бот:* {bot_username}\n"
            f"📊 *Всего зеркал: {mirror_count}*"
            f"{bonus_msg}",
            parse_mode="Markdown")
        # Лог в основной бот
        try:
            from main import bot as main_bot, bot_logs
            await main_bot.send_message(
                bot_logs,
                f"🪞 *Новое зеркало*\n"
                f"*└─ Пользователь:* {uid}\n"
                f"*└─ Бот:* {bot_username}\n"
                f"*└─ Всего зеркал:* {mirror_count}",
                parse_mode="Markdown")
        except Exception:
            pass

    # ─── FSM хендлеры — все методы работают через зеркало ────────────────────

    @dp.message_handler(state='*', content_types=types.ContentTypes.TEXT)
    async def mirror_fsm_router(message: types.Message, state: FSMContext):
        """Перенаправляет все текстовые FSM состояния в обработчики main.py"""
        uid = message.from_user.id
        # Фиксируем последнее активное зеркало юзера
        try:
            await db.touch_user_mirror(uid, token)
        except Exception:
            pass
        current_state = await state.get_state()
        if current_state is None:
            try:
                await message.answer("👋 Нажми /start чтобы начать.", parse_mode="Markdown")
            except Exception:
                pass
            return

        from main import (
            send_web_reports, get_mail_subject, start_bulk_email,
            botnet_step1_normal, botnet_step1_premium, bot_snos_step1,
            mirror_token_received, enter_promo, stress_step1, channel_step1,
            aureport_step1, datareg_step1, tida_step1, tida_step2, tida_target_step, tida_ai_desc_step, bank_step1, dsa_step1, dsa_custom_text,
            add_sub_uid, add_sub_days, clear_sub_uid,
            add_prem_uid, clear_prem_uid, sendall,
            admin_block_user, admin_unblock_user, admin_delete_user,
            admin_add_reports_uid, admin_add_reports_amount,
            admin_remove_reports_uid, admin_remove_reports_amount,
            admin_add_case_uid, admin_add_case_amount,
            create_promo_code, create_promo_days, create_promo_activations,
            admin_send_msg_target, admin_send_msg_text, AdminSendMsgFSM,
            WaitProbivFSM, probiv_query,
            WaitTextFSM, WaitMailTopicFSM, WaitMailTextFSM,
            WaitLinkFSM, WaitLinkPREMFSM, WaitBotLinkFSM,
            WaitMirrorTokenFSM, WaitPromoFSM, WaitStressFSM, WaitChannelFSM,
            WaitAuReportFSM, WaitDataRegFSM, WaitTidaFSM, WaitBankFSM, WaitDsaFSM,
            AddSubscribeFSM, ClearSubscribeFSM,
            AddPremFSM, ClearPremFSM, WaitTextZFSM,
            BlockUserFSM, UnblockUserFSM, DeleteUserFSM, CreatePromoFSM,
            AdminAddReportsFSM, AdminRemoveReportsFSM, AdminAddCaseFSM,
            WaitProfileFSM, profile_step1,
            WaitTrapFSM, trap_step1,
            WaitUsernamePremFSM, username_prem_got,
            WaitTelegraphFSM, telegraph_step1, telegraph_custom_text,
            WaitUniversalFSM, universal_step_link, universal_step_tida_text,
            WaitCaptchaFSM, check_captcha,
            WaitCodeFSM, code_step1,
            CheckUserFSM, admin_check_user_fsm,
            WaitSupportFSM, support_step1, support_step2,
            WaitDomainKillerFSM, domain_killer_step1, domain_killer_step2,
            WaitL4FSM, l4_step_target, l4_step_time, l4_net_tcp_handler, l4_net_udp_handler,
        )

        handlers = {
            WaitTextFSM.text.state: send_web_reports,
            WaitMailTopicFSM.topic.state: get_mail_subject,
            WaitMailTextFSM.text.state: start_bulk_email,
            WaitLinkFSM.link.state: botnet_step1_normal,
            WaitLinkPREMFSM.link.state: botnet_step1_premium,
            WaitBotLinkFSM.link.state: bot_snos_step1,
            WaitMirrorTokenFSM.token.state: mirror_token_received,
            WaitPromoFSM.promo.state: enter_promo,
            WaitStressFSM.link.state: stress_step1,
            WaitChannelFSM.link.state: channel_step1,
            WaitAuReportFSM.link.state: aureport_step1,
            WaitDataRegFSM.target.state: datareg_step1,
            WaitDsaFSM.link.state: dsa_step1,
            WaitDsaFSM.text.state: dsa_custom_text,
            WaitTidaFSM.link.state: tida_step1,
            WaitTidaFSM.target.state: tida_target_step,
            WaitTidaFSM.ai_desc.state: tida_ai_desc_step,
            WaitTidaFSM.text.state: tida_step2,
            WaitBankFSM.card.state: bank_step1,
            AddSubscribeFSM.user_id.state: add_sub_uid,
            AddSubscribeFSM.days.state: add_sub_days,
            ClearSubscribeFSM.user_id.state: clear_sub_uid,
            AddPremFSM.user_id.state: add_prem_uid,
            ClearPremFSM.user_id.state: clear_prem_uid,
            WaitTextZFSM.text.state: sendall,
            BlockUserFSM.user_id.state: admin_block_user,
            UnblockUserFSM.user_id.state: admin_unblock_user,
            DeleteUserFSM.user_id.state: admin_delete_user,
            CreatePromoFSM.code.state: create_promo_code,
            CreatePromoFSM.days.state: create_promo_days,
            CreatePromoFSM.activations.state: create_promo_activations,
            AdminAddReportsFSM.user_id.state: admin_add_reports_uid,
            AdminAddReportsFSM.amount.state: admin_add_reports_amount,
            AdminRemoveReportsFSM.user_id.state: admin_remove_reports_uid,
            AdminRemoveReportsFSM.amount.state: admin_remove_reports_amount,
            AdminAddCaseFSM.user_id.state: admin_add_case_uid,
            AdminAddCaseFSM.amount.state: admin_add_case_amount,
            WaitProfileFSM.link.state: profile_step1,
            WaitTrapFSM.victim.state: trap_step1,
            WaitUsernamePremFSM.username.state: username_prem_got,
            WaitTelegraphFSM.link.state: telegraph_step1,
            WaitTelegraphFSM.custom_text.state: telegraph_custom_text,
            AdminSendMsgFSM.target.state: admin_send_msg_target,
            AdminSendMsgFSM.text.state: admin_send_msg_text,
            WaitProbivFSM.query.state: probiv_query,
            WaitUniversalFSM.link.state: universal_step_link,
            WaitUniversalFSM.tida_text.state: universal_step_tida_text,
            WaitCaptchaFSM.code.state: check_captcha,
            WaitCodeFSM.phone.state: code_step1,
            CheckUserFSM.query.state: admin_check_user_fsm,
            WaitSupportFSM.target.state: support_step1,
            WaitSupportFSM.phone.state: support_step2,
            WaitDomainKillerFSM.domain.state: domain_killer_step1,
            WaitDomainKillerFSM.reason.state: domain_killer_step2,
            WaitL4FSM.target.state: l4_step_target,
            WaitL4FSM.time_dur.state: l4_step_time,
            WaitL4FSM.net_tcp_port.state: l4_net_tcp_handler,
            WaitL4FSM.net_udp_port.state: l4_net_udp_handler,
        }

        handler = handlers.get(current_state)
        if handler:
            await handler(message, state)

    return mirror_bot, dp


_MIRROR_ALLOWED = [
    'message', 'edited_message', 'callback_query', 'inline_query',
    'chosen_inline_result', 'channel_post', 'edited_channel_post',
    'business_connection', 'business_message', 'deleted_business_messages',
]

async def _poll_loop(mirror_bot, dp):
    """Ручной polling loop — даёт полный контроль над исключениями.
    Использует raw aiohttp вместо mirror_bot.get_updates(), чтобы business_*
    апдейты не дропались aiogram при парсинге types.Update."""
    import chatbot as _chatbot
    from aiogram import Bot as _Bot, Dispatcher as _Dispatcher

    token = getattr(mirror_bot, '_token', '') or ''
    offset = 0

    async with aiohttp.ClientSession() as http:
        while True:
            params = {'timeout': 20, 'limit': 100, 'allowed_updates': _MIRROR_ALLOWED}
            if offset:
                params['offset'] = offset

            async with http.post(
                f'https://api.telegram.org/bot{token}/getUpdates',
                json=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()

            if not data.get('ok'):
                err_code = data.get('error_code', 0)
                desc = data.get('description', '')
                if err_code == 401:
                    raise Unauthorized(desc)
                if err_code == 409:
                    raise TerminatedByOtherGetUpdates(desc)
                raise Exception(f"getUpdates error {err_code}: {desc}")

            for upd in data.get('result', []):
                uid = upd['update_id']
                if uid >= offset:
                    offset = uid + 1

                upd_keys = [k for k in upd if k != 'update_id']
                if any(k in upd for k in ('business_connection', 'business_message', 'deleted_business_messages')):
                    print(f"[MIRROR POLL] {token[:15]} upd#{uid} BUSINESS type={upd_keys}", flush=True)

                try:
                    if 'business_connection' in upd:
                        asyncio.ensure_future(_chatbot.handle_business_connection(upd, bot_token=token))
                    elif 'business_message' in upd:
                        txt = upd['business_message'].get('text', '')[:40]
                        print(f"[MIRROR POLL] → business_message text={txt!r}", flush=True)
                        asyncio.ensure_future(_chatbot.handle_business_message(upd, bot_token=token))
                    elif 'deleted_business_messages' in upd:
                        asyncio.ensure_future(_chatbot.handle_deleted_business_messages(upd, bot_token=token))
                    else:
                        update_obj = types.Update(**upd)
                        _Bot.set_current(mirror_bot)
                        _Dispatcher.set_current(dp)
                        asyncio.ensure_future(dp.process_update(update_obj))
                except Exception as e:
                    print(f"[MIRROR POLL] update error: {e}", flush=True)


async def _run_mirror(token: str):
    max_retries = 5
    for attempt in range(max_retries):
        mirror_bot, dp = _build_mirror_dispatcher(token)
        _mirror_bots[token] = mirror_bot
        try:
            print(f"[MIRROR] 🚀 Запуск зеркала {token[:20]}... (попытка {attempt+1})", flush=True)
            # Сначала сбрасываем вебхук — это освобождает слот быстрее
            try:
                await mirror_bot.delete_webhook(drop_pending_updates=True)
            except Exception:
                pass
            # Ждём пока старая long-poll сессия умрёт
            for kick in range(10):
                try:
                    await mirror_bot.get_updates(offset=-1, timeout=0, limit=1)
                    break
                except TerminatedByOtherGetUpdates:
                    print(f"[MIRROR] ⏳ Слот занят {token[:20]}, жду 2с... ({kick+1}/10)", flush=True)
                    await asyncio.sleep(2)
                except Exception:
                    break
            await _poll_loop(mirror_bot, dp)
            break  # нормальный выход из цикла (polling остановлен снаружи)
        except Unauthorized:
            print(f"[MIRROR] 🚫 Токен невалидный, удаляем: {token[:20]}", flush=True)
            await db.remove_mirror_by_token(token)
            break
        except TerminatedByOtherGetUpdates:
            backoff = min(35 * (attempt + 1), 120)
            print(f"[MIRROR] ⚠️ Конфликт {token[:20]}, повтор через {backoff}с...", flush=True)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[MIRROR] ❌ Ошибка зеркала {token[:20]}: {e}", flush=True)
            break
        finally:
            try:
                await dp.storage.close()
                await dp.storage.wait_closed()
            except Exception:
                pass
            try:
                if mirror_bot._session and not mirror_bot._session.closed:
                    await mirror_bot._session.close()
            except Exception:
                pass
            _mirror_bots.pop(token, None)
        if attempt < max_retries - 1:
            await asyncio.sleep(backoff)
    _running_mirrors.pop(token, None)
    print(f"[MIRROR] 🔴 Зеркало {token[:20]} остановлено", flush=True)


async def start_mirror(token: str):
    if token in _running_mirrors:
        return
    if token == os.environ.get("TOKEN", ""):
        print(f"[MIRROR] ⛔ Попытка запустить главный токен как зеркало — пропускаем", flush=True)
        return
    task = asyncio.ensure_future(_run_mirror(token))
    _running_mirrors[token] = task
    await asyncio.sleep(0.1)


async def start_all_mirrors():
    main_token = os.environ.get("TOKEN", "")

    # Системные зеркала — запускаем НЕМЕДЛЕННО, не ждём валидацию остальных
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        sys_rows = await conn.fetch(
            "SELECT token FROM mirrors WHERE is_system = TRUE AND token != $1", main_token
        )
    system_tokens = [r["token"] for r in sys_rows]

    if system_tokens:
        print(f"[MIRROR] Запускаем {len(system_tokens)} системных зеркал немедленно...", flush=True)
        for token in system_tokens:
            asyncio.ensure_future(start_mirror(token))

    tokens = await db.get_all_mirror_tokens()
    tokens = [t for t in tokens if t != main_token and t not in system_tokens]
    print(f"[MIRROR] Загружаем {len(tokens)} зеркал + {len(system_tokens)} системных из БД...", flush=True)

    async def check_token(token: str) -> tuple:
        result = await validate_token(token)
        if result is None:
            print(f"[MIRROR] Невалидный токен, удаляем: {token[:20]}", flush=True)
            await db.remove_mirror_by_token(token)
            return token, False
        return token, True

    valid_tokens = []
    batch_size = 50
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        results = await asyncio.gather(*[check_token(t) for t in batch])
        valid_tokens.extend(t for t, ok in results if ok)

    valid_tokens = valid_tokens[:MIRROR_LIMIT]
    print(f"[MIRROR] Валидных: {len(valid_tokens)} обычных + {len(system_tokens)} системных", flush=True)
    asyncio.ensure_future(_start_mirrors_background(valid_tokens))
    print(f"[MIRROR] Запуск зеркал в фоне...", flush=True)


async def _start_mirrors_background(tokens: list):
    batch_size = 20
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        await asyncio.gather(*[start_mirror(t) for t in batch])
        await asyncio.sleep(0.3)


def get_running_tokens() -> list:
    return [t for t, task in _running_mirrors.items() if not task.done()]


async def validate_token(token: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return "@" + data["result"]["username"]
                return None
    except Exception:
        return None
