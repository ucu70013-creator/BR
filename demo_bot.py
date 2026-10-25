"""
Brown V2 — DEMO / MEDIA BOT
Полная визуальная копия основного бота.
Сессии НЕ жалуются — всё симуляция с реалистичными логами.

Запуск: python demo_bot.py
Настройка: задай DEMO_TOKEN ниже (отдельный бот через @BotFather)
"""

import os
import asyncio
import random
import io
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InputFile

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DEMO_TOKEN = os.environ.get("DEMO_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")
DEMO_CHANNEL_LINK = "https://t.me/BrownV2_Media"
DEMO_CHANNEL2_LINK = "https://t.me/BrownV2_Media"

bot = Bot(token=DEMO_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ─── IN-MEMORY STORE ──────────────────────────────────────────────────────────
_users: dict = {}   # uid -> {lang, verified, premium, subscribe}
_captcha: dict = {} # uid -> code


def _get_user(uid: int) -> dict:
    if uid not in _users:
        _users[uid] = {
            'lang': 'ru',
            'verified': False,
            'premium': True,
            'subscribe': datetime.now() + timedelta(days=9999),
        }
    return _users[uid]


def t(key: str, lang: str = 'ru') -> str:
    _tr = {
        'menu_caption': {
            'ru': ">🤖 *Brown V2 — Система жалоб*\n*└─ Выберите действие:*",
            'en': ">🤖 *Brown V2 — Report System*\n*└─ Choose action:*",
        },
        'btn_panel': {'ru': '🔥 Открыть панель', 'en': '🔥 Open panel'},
        'btn_info':  {'ru': '❓ Информация',      'en': '❓ Information'},
        'btn_profile': {'ru': '👤 Профиль',         'en': '👤 Profile'},
        'btn_bonuses': {'ru': '🎁 Бонусы',           'en': '🎁 Bonuses'},
        'btn_media':   {'ru': '🎥 Медиа',            'en': '🎥 Media'},
        'btn_probiv':  {'ru': '🕵️ Пробив',           'en': '🕵️ OSINT'},
        'btn_shop':    {'ru': '🛍 Цены',             'en': '🛍 Prices'},
        'btn_settings': {'ru': '⚙️ Настройки',        'en': '⚙️ Settings'},
        'btn_support':  {'ru': '🆘 Поддержка',        'en': '🆘 Support'},
        'btn_back':    {'ru': '[🔙] Назад',           'en': '[🔙] Back'},
        'btn_main_menu': {'ru': '[🔙] Главное меню',  'en': '[🔙] Main menu'},
    }
    row = _tr.get(key, {})
    return row.get(lang, row.get('ru', key))


# ─── KEYBOARDS ────────────────────────────────────────────────────────────────

def kb_main(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_panel', lang),    callback_data='functions'))
    m.add(
        types.InlineKeyboardButton(t('btn_info', lang),      callback_data='information'),
        types.InlineKeyboardButton(t('btn_profile', lang),   callback_data='profile'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_bonuses', lang),   callback_data='bonuses_menu'),
        types.InlineKeyboardButton(t('btn_media', lang),     callback_data='media'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_probiv', lang),    callback_data='probiv'),
        types.InlineKeyboardButton(t('btn_shop', lang),      callback_data='shop'),
    )
    m.add(types.InlineKeyboardButton(t('btn_settings', lang), callback_data='settings_menu'))
    m.add(types.InlineKeyboardButton(t('btn_support', lang),  url='https://t.me/BR_V2_support'))
    return m


def kb_back(lang='ru', to='back') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data=to))
    return m


def kb_main_menu(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton(t('btn_main_menu', lang), callback_data='go_to_main_menu'))
    return m


def kb_panel_select(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton('🔓 Обычный',  callback_data='panel_regular'),
        types.InlineKeyboardButton('👑 Премиум',  callback_data='panel_premium'),
    )
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='back'))
    return m


def kb_regular_panel(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton('🤖 Ботнет (55 акков)', callback_data='botnet_method'))
    m.add(
        types.InlineKeyboardButton('🤖 Снос бота', callback_data='bot_method'),
        types.InlineKeyboardButton('📢 Канал-метод', callback_data='channel_method'),
    )
    m.add(types.InlineKeyboardButton('📖 Ручной метод', callback_data='manual_method'))
    m.add(
        types.InlineKeyboardButton('🇦🇺 AU Report', callback_data='aureport_method'),
        types.InlineKeyboardButton('🟣 TIDA',        callback_data='tida_method'),
    )
    m.add(
        types.InlineKeyboardButton('📱 Спам кодами', callback_data='code_method'),
        types.InlineKeyboardButton('🔗 Логгер',      callback_data='logger_method'),
    )
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions'))
    return m


def kb_premium_panel(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton('👑 Премиум ботнет (200 акков)', callback_data='prem_botnet_method'))
    m.add(
        types.InlineKeyboardButton('🌐 Web',    callback_data='web_method'),
        types.InlineKeyboardButton('✉️ Mail',   callback_data='mail_method'),
    )
    m.add(
        types.InlineKeyboardButton('🏦 Банк-метод',  callback_data='bank_method'),
        types.InlineKeyboardButton('🇪🇺 DSA Report', callback_data='dsa_method'),
    )
    m.add(types.InlineKeyboardButton('📄 Telegraph снос', callback_data='telegraph_method'))
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions'))
    return m


def kb_channel_reason(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton('🔐 Персональные данные', callback_data='demo_reason_personal'),
        types.InlineKeyboardButton('📢 Спам / Мошенничество', callback_data='demo_reason_spam'),
        types.InlineKeyboardButton('🔞 18+ Контент',          callback_data='demo_reason_adult'),
        types.InlineKeyboardButton('👶 Детский контент',       callback_data='demo_reason_children'),
        types.InlineKeyboardButton('💥 Насилие / Экстремизм', callback_data='demo_reason_violence'),
        types.InlineKeyboardButton('📝 Прочее',               callback_data='demo_reason_other'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='panel_regular'),
    )
    return m


def kb_bot_reason(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton('🔐 Личные данные', callback_data='demo_botreason_personal'),
        types.InlineKeyboardButton('💊 Наркотики',     callback_data='demo_botreason_drugs'),
        types.InlineKeyboardButton('📝 Прочее',        callback_data='demo_botreason_other'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='panel_regular'),
    )
    return m


def kb_shop(lang='ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton('⚡️ 1 день',   callback_data='demo_shop'),
        types.InlineKeyboardButton('⚡️ 3 дня',    callback_data='demo_shop'),
    )
    m.add(
        types.InlineKeyboardButton('⚡️ 7 дней',   callback_data='demo_shop'),
        types.InlineKeyboardButton('⚡️ 30 дней',  callback_data='demo_shop'),
    )
    m.add(types.InlineKeyboardButton('⚡️ Навсегда', callback_data='demo_shop'))
    m.add(types.InlineKeyboardButton('⭐️ Premium',  callback_data='demo_shop'))
    m.add(types.InlineKeyboardButton('👑 Что такое премиум?', callback_data='preminfo'))
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='back'))
    return m


# ─── FSM ──────────────────────────────────────────────────────────────────────

class CaptchaFSM(StatesGroup):
    code = State()

class LangFSM(StatesGroup):
    select = State()

class DemoLinkFSM(StatesGroup):
    link = State()
    method = State()


# ─── CAPTCHA (простая числовая) ───────────────────────────────────────────────

def _gen_captcha():
    a, b = random.randint(10, 50), random.randint(1, 20)
    return f"{a} + {b}", str(a + b)


# ─── FAKE LOG GENERATOR ───────────────────────────────────────────────────────

_SESS_PREFIXES = [
    '8762226901', '8581122255', '8927131052', '8802066587', '8694140385',
    '8951801445', '8868037635', '8950384169', '8982273016', '8888734432',
    '8933334372', '8811536193', '8858383890', '8863873976', '8875162146',
    '8818243150', '8948899254', '8815386438', '8904155277', '8789462916',
    '8863387057', '8872821229', '8838177172', '8854609075', '8859891547',
    '8823958496', '8857668431', '8687843940', '8937384607', '8752998339',
    '8807711784', '8896942889', '8944044153', '8797511484', '8931610952',
]

def _fake_log(target: str, method: str, reason: str = 'Спам', count: int = 35) -> tuple[str, str]:
    """Генерирует реалистичный лог-файл. Возвращает (caption, log_text)."""
    now = datetime.now().strftime('%H:%M:%S')
    sessions = random.sample(_SESS_PREFIXES, min(count, len(_SESS_PREFIXES)))
    valid = 0
    lines = [
        f"Brown V2 log | {method}",
        "-" * 42,
        f"Цель: {target}",
        f"Причина: {reason}",
        f"Время: {now}",
        "-" * 42,
    ]
    for s in sessions:
        suffix = '_new.session' if random.random() > 0.3 else '.session'
        name = f"{s}{suffix}"
        # ~70% success rate
        if random.random() < 0.72:
            lines.append(f"[{now}] {name} -> {target} - [ДОСТАВЛЕНО]")
            valid += 1
        else:
            lines.append(f"[{now}] {name} -> {target} - [ОТКЛОНЕНО]")
    lines += [
        "-" * 42,
        f"Успешно: {valid}",
        f"Неуспешно: {len(sessions) - valid}",
        f"Флудов: 0",
    ]
    log = "\n".join(lines)
    caption = (
        f"📢 *Жалобы завершены!*\n"
        f"*└─ Цель: {target}*\n\n"
        f"🟢 *Успешно: {valid}*\n"
        f"🔴 *Не удалось: {len(sessions) - valid}*"
    )
    return caption, log


# ─── HELPERS ──────────────────────────────────────────────────────────────────

async def show_main_menu(uid: int, lang: str = 'ru', edit_msg=None):
    try:
        photo = open('material/menu.png', 'rb')
    except FileNotFoundError:
        # fallback — простое сообщение если нет картинки
        caption = ">🤖 *Brown V2 — DEMO*\n*└─ Выберите действие:*"
        if edit_msg:
            try:
                await edit_msg.edit_caption(caption=caption, parse_mode='MarkdownV2', reply_markup=kb_main(lang))
            except Exception:
                await bot.send_message(uid, caption, parse_mode='MarkdownV2', reply_markup=kb_main(lang))
        else:
            await bot.send_message(uid, caption, parse_mode='MarkdownV2', reply_markup=kb_main(lang))
        return

    caption = t('menu_caption', lang)
    if edit_msg:
        try:
            await edit_msg.edit_caption(caption=caption, parse_mode='MarkdownV2', reply_markup=kb_main(lang))
            return
        except Exception:
            pass
    await bot.send_photo(uid, photo=photo, caption=caption, parse_mode='MarkdownV2', reply_markup=kb_main(lang))


async def _run_fake_method(uid: int, target: str, method_name: str, reason: str = '📢 Спам'):
    """Симулирует выполнение метода: ожидание → лог."""
    count_map = {
        'Ботнет': 35, 'Премиум ботнет': 55, 'Канал-метод': 35,
        'Снос бота': 35, 'AU Report': 10, 'TIDA': 10,
        'Web': 20, 'Mail': 50, 'Банк-метод': 1,
        'DSA Report': 5, 'Telegraph': 5, 'Спам кодами': 35, 'Логгер': 1,
    }
    wait = await bot.send_message(uid, f"⏳ *Запускаю {method_name}...*\n*└─ Это займёт несколько секунд*", parse_mode='Markdown')
    await asyncio.sleep(random.uniform(2.5, 4.5))
    await wait.delete()

    caption, log_text = _fake_log(target, method_name, reason, count=count_map.get(method_name, 35))
    buf = io.BytesIO(log_text.encode('utf-8'))
    buf.name = f'brown_v2_demo_{method_name.lower().replace(" ", "_")}.txt'
    await bot.send_document(
        uid,
        types.InputFile(buf, filename=buf.name),
        caption=caption,
        parse_mode='Markdown',
        reply_markup=kb_main_menu(),
    )


# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    uid = message.from_user.id
    user = _get_user(uid)

    if not user['verified']:
        question, answer = _gen_captcha()
        _captcha[uid] = answer
        await CaptchaFSM.code.set()
        await bot.send_message(uid,
            f"🤖 *Докажи что ты не бот:*\n\n{question} = ?",
            parse_mode='Markdown')
        return

    await _after_verify(uid, message.from_user.username or '', user['lang'])


@dp.message_handler(state=CaptchaFSM.code)
async def check_captcha(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    expected = _captcha.get(uid, "")
    if message.text.strip() == expected:
        _captcha.pop(uid, None)
        await state.finish()
        _get_user(uid)['verified'] = True
        lang_markup = types.InlineKeyboardMarkup(row_width=2)
        lang_markup.add(
            types.InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_select_ru'),
            types.InlineKeyboardButton("🇬🇧 English",  callback_data='lang_select_en'),
        )
        await bot.send_message(uid, "✅ *Выбери язык / Choose language:*",
            parse_mode='Markdown', reply_markup=lang_markup)
    else:
        question, answer = _gen_captcha()
        _captcha[uid] = answer
        await bot.send_message(uid,
            f"❌ *Неверно. Попробуй снова:*\n\n{question} = ?",
            parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data in ('lang_select_ru', 'lang_select_en'), state='*')
async def lang_select(call: types.CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    lang = 'ru' if call.data == 'lang_select_ru' else 'en'
    _get_user(uid)['lang'] = lang
    _get_user(uid)['verified'] = True
    try:
        await call.message.delete()
    except Exception:
        pass
    try:
        await bot.send_sticker(uid, InputFile("AnimatedSticker.tgs"))
    except Exception:
        pass
    await _after_verify(uid, call.from_user.username or '', lang)


async def _after_verify(uid: int, username: str, lang: str):
    await show_main_menu(uid, lang)


# ─── MAIN CALLBACK HUB ────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: True, state='*')
async def cb_hub(call: types.CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    user = _get_user(uid)
    lang = user.get('lang', 'ru')
    d = call.data

    await call.answer()

    # ── Навигация ──────────────────────────────────────────────────────────────
    if d in ('back', 'go_to_main_menu'):
        await show_main_menu(uid, lang, edit_msg=call.message)
        return

    if d == 'functions':
        try:
            await call.message.edit_caption(
                caption=">⚙️ *Открыть панель*\n*└─ Выберите тип панели:*",
                parse_mode='MarkdownV2', reply_markup=kb_panel_select(lang))
        except Exception:
            await bot.send_message(uid, "⚙️ *Выберите тип панели:*",
                parse_mode='Markdown', reply_markup=kb_panel_select(lang))
        return

    if d == 'panel_regular':
        try:
            await call.message.edit_caption(
                caption=">🔓 *Обычный раздел*\n*└─ Выберите метод:*",
                parse_mode='MarkdownV2', reply_markup=kb_regular_panel(lang))
        except Exception:
            await bot.send_message(uid, "🔓 *Обычный раздел:*",
                parse_mode='Markdown', reply_markup=kb_regular_panel(lang))
        return

    if d == 'panel_premium':
        try:
            await call.message.edit_caption(
                caption=">👑 *Премиум раздел*\n*└─ Выберите метод:*",
                parse_mode='MarkdownV2', reply_markup=kb_premium_panel(lang))
        except Exception:
            await bot.send_message(uid, "👑 *Премиум раздел:*",
                parse_mode='Markdown', reply_markup=kb_premium_panel(lang))
        return

    # ── Профиль ────────────────────────────────────────────────────────────────
    if d == 'profile':
        sub_until = (datetime.now() + timedelta(days=9999)).strftime("%Y-%m-%d")
        text = (
            f"👤 *Профиль*\n"
            f"*├─ ID:* {uid}\n"
            f"*├─ Подписка:* ✅ Активна до {sub_until}\n"
            f"*├─ Премиум:* 👑 Да\n"
            f"*└─ Репорты:* ∞"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton('⚙️ Настройки', callback_data='settings_menu'),
            types.InlineKeyboardButton(t('btn_back', lang), callback_data='back'),
        )
        try:
            await call.message.edit_caption(caption=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
        return

    # ── Информация ─────────────────────────────────────────────────────────────
    if d == 'information':
        text = (
            "❓ *О сервисе Brown V2*\n\n"
            "*🤖 Ботнет:* 55 аккаунтов → жалобы на пользователей и посты\n"
            "*👑 Премиум ботнет:* 200 аккаунтов → максимальная эффективность\n"
            "*📢 Канал-метод:* жалобы на каналы через 55 сессий\n"
            "*🌐 Web:* 200 жалоб через браузер\n"
            "*✉️ Mail:* рассылка жалоб на email Telegram\n"
            "*🇦🇺 AU Report:* австралийская форма жалобы\n"
            "*🟣 TIDA:* жалобы через TIDA систему\n"
            "*🏦 Банк-метод:* жалобы через банковские партнёры\n"
            "*🇪🇺 DSA Report:* европейская форма DSA\n"
            "*📄 Telegraph:* снос Telegraph-статей\n"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton('📖 Мануал', url='https://br-v2.com/manual'),
            types.InlineKeyboardButton(t('btn_back', lang), callback_data='back'),
        )
        try:
            await call.message.edit_caption(caption=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
        return

    # ── Цены ───────────────────────────────────────────────────────────────────
    if d == 'shop':
        text = (
            "🛍 *Тарифы Brown V2*\n\n"
            "*⚡️ 1 день* — 1$ / 100₽\n"
            "*⚡️ 3 дня* — 2$ / 175₽\n"
            "*⚡️ 7 дней* — 4$ / 350₽\n"
            "*⚡️ 30 дней* — 8$ / 700₽\n"
            "*⚡️ Навсегда* — 6$ / 500₽ \\[\\-70%\\]\n"
            "*⭐️ Премиум* — 5$ / 400₽ \\[\\-50%\\]\n\n"
            "_Оплата: CryptoBot / СБП / TonKeeper_"
        )
        try:
            await call.message.edit_caption(caption=text, parse_mode='MarkdownV2', reply_markup=kb_shop(lang))
        except Exception:
            await bot.send_message(uid, text, parse_mode='MarkdownV2', reply_markup=kb_shop(lang))
        return

    if d == 'demo_shop':
        await bot.answer_callback_query(call.id, "💳 Оплата доступна в основном боте @Brrown_V2bot", show_alert=True)
        return

    if d == 'preminfo':
        text = (
            "👑 *Что такое Премиум?*\n\n"
            "*├─ Доступ к Премиум ботнету (200 акков)*\n"
            "*├─ Web-Reports (200 жалоб)*\n"
            "*├─ Mail-Reports (рассылка)*\n"
            "*├─ Банк-метод*\n"
            "*├─ DSA Report*\n"
            "*├─ Telegraph снос*\n"
            "*└─ Снятые ограничения*\n\n"
            "_Подключается как надстройка к любому тарифу_"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='shop'))
        try:
            await call.message.edit_caption(caption=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
        return

    # ── Настройки ──────────────────────────────────────────────────────────────
    if d == 'settings_menu':
        text = "⚙️ *Настройки*"
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton('🌐 Сменить язык', callback_data='lang_change'),
            types.InlineKeyboardButton('🔍 Мониторинг',   callback_data='monitor_stub'),
            types.InlineKeyboardButton(t('btn_back', lang), callback_data='back'),
        )
        try:
            await call.message.edit_caption(caption=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
        return

    if d == 'lang_change':
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton('🇷🇺 Русский', callback_data='lang_select_ru'),
            types.InlineKeyboardButton('🇬🇧 English',  callback_data='lang_select_en'),
        )
        m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='settings_menu'))
        try:
            await call.message.edit_caption(caption="🌐 *Выберите язык:*",
                parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, "🌐 *Выберите язык:*", parse_mode='Markdown', reply_markup=m)
        return

    # ── Бонусы ─────────────────────────────────────────────────────────────────
    if d == 'bonuses_menu':
        text = ">🎁 *Бонусы*\n*└─ Выберите раздел:*"
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton('🎡 Колесо репортов', callback_data='wheel'),
            types.InlineKeyboardButton('📦 Кейс',            callback_data='case_menu'),
        )
        m.add(
            types.InlineKeyboardButton('🎁 Промокод',  callback_data='promo'),
            types.InlineKeyboardButton('👥 Рефералы',  callback_data='referral'),
        )
        m.add(
            types.InlineKeyboardButton('🪞 Зеркала', callback_data='mirrors_menu'),
        )
        m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='back'))
        try:
            await call.message.edit_caption(caption=text, parse_mode='MarkdownV2', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='MarkdownV2', reply_markup=m)
        return

    if d == 'wheel':
        text = "🎡 *Колесо репортов*\n\n*├─ Крути колесо и выигрывай репорты!*\n*└─ Можно крутить 1 раз в сутки*"
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton('🎡 Крутить!', callback_data='spin_wheel'),
            types.InlineKeyboardButton(t('btn_back', lang), callback_data='bonuses_menu'),
        )
        try:
            await call.message.edit_caption(caption=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
        return

    if d == 'spin_wheel':
        prize = random.choice(['🎯 +5 репортов', '🎯 +10 репортов', '🎯 +15 репортов', '⭐️ +1 день подписки'])
        await bot.answer_callback_query(call.id, f"🎡 Выпало: {prize}!", show_alert=True)
        return

    if d in ('case_menu', 'promo', 'referral', 'mirrors_menu', 'monitor_stub', 'probiv', 'media'):
        labels = {
            'case_menu':    '📦 Кейсы',
            'promo':        '🎁 Промокоды',
            'referral':     '👥 Рефералы',
            'mirrors_menu': '🪞 Зеркала',
            'monitor_stub': '🔍 Мониторинг',
            'probiv':       '🕵️ Пробив',
            'media':        '🎥 Медиа',
        }
        back_to = {'case_menu': 'bonuses_menu', 'promo': 'bonuses_menu',
                   'referral': 'bonuses_menu', 'mirrors_menu': 'bonuses_menu'}.get(d, 'back')
        text = f"{labels.get(d, d)}\n\n_Функция демонстрируется визуально. В основном боте — полный функционал._"
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data=back_to))
        try:
            await call.message.edit_caption(caption=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            await bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
        return

    # ── Методы: запрос ссылки ──────────────────────────────────────────────────
    METHOD_MAP = {
        'botnet_method':      ('Ботнет',         'regular', False),
        'prem_botnet_method': ('Премиум ботнет',  'premium', False),
        'bot_method':         ('Снос бота',       'regular', False),
        'channel_method':     ('Канал-метод',     'regular', True),   # True = нужен выбор причины
        'aureport_method':    ('AU Report',       'regular', False),
        'tida_method':        ('TIDA',            'regular', False),
        'code_method':        ('Спам кодами',     'regular', False),
        'logger_method':      ('Логгер',          'regular', False),
        'web_method':         ('Web',             'premium', False),
        'mail_method':        ('Mail',            'premium', False),
        'bank_method':        ('Банк-метод',      'premium', True),
        'dsa_method':         ('DSA Report',      'premium', False),
        'telegraph_method':   ('Telegraph',       'premium', False),
        'manual_method':      ('Ручной метод',    'regular', False),
    }

    if d in METHOD_MAP:
        method_name, panel_type, needs_reason = METHOD_MAP[d]
        await state.update_data(demo_method=method_name, demo_panel=panel_type, demo_needs_reason=needs_reason)

        if d == 'manual_method':
            text = (
                "📖 *Ручной метод*\n\n"
                "*Инструкция:*\n"
                "*1.* Открой профиль цели в Telegram\n"
                "*2.* Нажми ⋮ → Пожаловаться\n"
                "*3.* Выбери причину и отправь\n"
                "*4.* Повтори с разных аккаунтов\n\n"
                "_Подробный мануал:_ br\\-v2\\.top/manual"
            )
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton('📖 Читать мануал', url='https://br-v2.com/manual'),
                types.InlineKeyboardButton(t('btn_back', lang), callback_data='panel_regular'),
            )
            try:
                await call.message.edit_caption(caption=text, parse_mode='MarkdownV2', reply_markup=m)
            except Exception:
                await bot.send_message(uid, text, parse_mode='MarkdownV2', reply_markup=m)
            return

        hint = "@username или ссылка на пост/канал"
        await bot.send_message(uid,
            f"📎 *{method_name}*\n\n*Введи цель:*\n{hint}",
            parse_mode='Markdown',
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton('❌ Отмена', callback_data=f'panel_{panel_type}')
            )
        )
        await DemoLinkFSM.link.set()
        return

    # ── Выбор причины (channel, bank) ─────────────────────────────────────────
    if d.startswith('demo_reason_') or d.startswith('demo_botreason_'):
        reason_labels = {
            'demo_reason_personal': '🔐 Персональные данные',
            'demo_reason_spam':     '📢 Спам / Мошенничество',
            'demo_reason_adult':    '🔞 18+ Контент',
            'demo_reason_children': '👶 Детский контент',
            'demo_reason_violence': '💥 Насилие / Экстремизм',
            'demo_reason_other':    '📝 Прочее',
            'demo_botreason_personal': '🔐 Личные данные',
            'demo_botreason_drugs':    '💊 Наркотики',
            'demo_botreason_other':    '📝 Прочее',
        }
        reason = reason_labels.get(d, 'Прочее')
        fsm = await state.get_data()
        target = fsm.get('demo_target', '@example')
        method_name = fsm.get('demo_method', 'Метод')
        await state.finish()
        asyncio.create_task(_run_fake_method(uid, target, method_name, reason))
        return

    # ── Заглушки для нераспознанных callback ──────────────────────────────────
    await bot.answer_callback_query(call.id)


# ─── FSM: ввод ссылки ─────────────────────────────────────────────────────────

@dp.message_handler(state=DemoLinkFSM.link)
async def demo_got_link(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    target = message.text.strip()
    fsm = await state.get_data()
    method_name = fsm.get('demo_method', 'Метод')
    needs_reason = fsm.get('demo_needs_reason', False)
    panel_type = fsm.get('demo_panel', 'regular')

    await state.update_data(demo_target=target)

    if needs_reason:
        await state.finish()
        # Показываем выбор причины
        kb = kb_channel_reason() if 'Канал' in method_name or 'Банк' in method_name else kb_bot_reason()
        await bot.send_message(uid,
            f"📎 *{method_name}*\n*└─ Цель: {target}*\n\n*Выберите причину жалобы:*",
            parse_mode='Markdown', reply_markup=kb)
    else:
        await state.finish()
        asyncio.create_task(_run_fake_method(uid, target, method_name))


# ─── ЗАПУСК ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if DEMO_TOKEN == "ВСТАВЬ_ТОКЕН_СЮДА":
        print("❌ Задай DEMO_TOKEN в коде или через переменную среды DEMO_TOKEN=...")
        exit(1)
    print(f"🚀 Demo bot запущен")
    executor.start_polling(dp, skip_updates=True)
