from aiogram import types
import config
import json as _json
from translations import t


def styled(markup: types.InlineKeyboardMarkup, style_map: dict) -> str:
    """Bot API 9.4: возвращает JSON-строку клавиатуры с полем style на кнопках.
    style_map = {'callback_data': 'primary'|'success'|'danger'}
    """
    d = markup.to_python()
    for row in d.get('inline_keyboard', []):
        for btn in row:
            s = style_map.get(btn.get('callback_data', ''))
            if s:
                btn['style'] = s
    return _json.dumps(d)


# ─── Статичные кнопки (EN, не переводятся) ───────────────────────────────────
profile = types.InlineKeyboardButton("👤 Профиль", callback_data='profile')
information = types.InlineKeyboardButton("❓ Информация", callback_data='information')
shop = types.InlineKeyboardButton("🛍 Цены", callback_data='shop')
snoser = types.InlineKeyboardButton("🔥 Открыть панель", callback_data='functions')
promo = types.InlineKeyboardButton("🎁 Промокод", callback_data='promo')
referral_btn = types.InlineKeyboardButton("👥 Рефералы", callback_data='referral')
wheel_btn = types.InlineKeyboardButton("🎡 Колесо репортов", callback_data='wheel')
free_btn = types.InlineKeyboardButton("🆓 Бесплатно", callback_data='free_menu')
mirrors_pub_btn = types.InlineKeyboardButton("🪞 Зеркала", callback_data='public_mirrors')
support_btn = types.InlineKeyboardButton("🆘 Поддержка", url='https://t.me/BR_V2_support')
case_btn = types.InlineKeyboardButton("📦 Кейс", callback_data='case_menu')
monitor_btn = types.InlineKeyboardButton("🔍 Мониторинг", callback_data='monitor_menu')
probiv_btn = types.InlineKeyboardButton("🕵️ Пробив", callback_data='probiv')
media_btn = types.InlineKeyboardButton("🎥 Медиа", callback_data='media')

back = types.InlineKeyboardButton("[🔙] Назад", callback_data='back')
back_markup = types.InlineKeyboardMarkup(row_width=2)
back_markup.add(back)

main_menu = types.InlineKeyboardMarkup(row_width=2)
go_to_main_menu = types.InlineKeyboardButton("[🔙] Главное меню", callback_data='go_to_main_menu')
main_menu.add(go_to_main_menu)


# ─── Языкозависимые функции ───────────────────────────────────────────────────

def get_back_btn(lang: str = 'ru') -> types.InlineKeyboardButton:
    return types.InlineKeyboardButton(t('btn_back', lang), callback_data='back')


def get_back_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(get_back_btn(lang))
    return m


def get_panel_back_btn(lang: str = 'ru') -> types.InlineKeyboardButton:
    return types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions')


def get_bonuses_back_btn(lang: str = 'ru') -> types.InlineKeyboardButton:
    return types.InlineKeyboardButton(t('btn_back', lang), callback_data='bonuses_menu')


def get_panel_back_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(get_panel_back_btn(lang))
    return m


def get_main_menu_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_main_menu', lang), callback_data='go_to_main_menu'))
    return m


def get_menu(is_admin: bool = False, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_panel', lang), callback_data='functions'))
    m.add(
        types.InlineKeyboardButton(t('btn_info', lang), callback_data='information'),
        types.InlineKeyboardButton(t('btn_profile', lang), callback_data='profile'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_bonuses', lang), callback_data='bonuses_menu'),
        types.InlineKeyboardButton(t('btn_media', lang), callback_data='media'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_probiv', lang), callback_data='probiv'),
        types.InlineKeyboardButton(t('btn_shop', lang), callback_data='shop'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_settings', lang), callback_data='settings_menu'),
        types.InlineKeyboardButton('🛒 TG Маркет', callback_data='tg_market'),
    )
    if is_admin:
        m.add(types.InlineKeyboardButton(t('btn_admin', lang), callback_data='admin_panel'))
    m.add(types.InlineKeyboardButton(t('btn_support', lang), url='https://t.me/BR_V2_support'))
    return styled(m, {'functions': 'primary'})


def get_bonuses_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_wheel', lang), callback_data='wheel'))
    m.add(
        types.InlineKeyboardButton(t('btn_cases', lang), callback_data='case_menu'),
        types.InlineKeyboardButton(t('btn_promo', lang), callback_data='promo'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_referral', lang), callback_data='referral'),
        types.InlineKeyboardButton(t('btn_mirrors', lang), callback_data='mirrors_menu'),
    )
    m.add(types.InlineKeyboardButton('🏆 Топ рейтинг', callback_data='top_rating'))
    m.add(get_back_btn(lang))
    return m


def get_settings_markup(lang: str = 'ru', is_hidden: bool = False, chatbot_enabled: bool = False) -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    hide_text = t('profile_hide_on', lang) if is_hidden else t('profile_hide_off', lang)
    chatbot_text = ('🤖 Чат-бот ✔' if chatbot_enabled else '🤖 Чат-бот ✘') if lang == 'ru' else ('🤖 Chatbot ✔' if chatbot_enabled else '🤖 Chatbot ✘')
    m.add(
        types.InlineKeyboardButton(t('profile_lang_btn', lang), callback_data='lang_change'),
        types.InlineKeyboardButton(hide_text, callback_data='profile_toggle_hidden'),
        types.InlineKeyboardButton(t('profile_history_btn', lang), callback_data='profile_history'),
        types.InlineKeyboardButton('⚠️ История предупреждений' if lang == 'ru' else '⚠️ Warning History', callback_data='warn_history'),
        types.InlineKeyboardButton(t('btn_monitor', lang), callback_data='monitor_menu'),
        types.InlineKeyboardButton(chatbot_text, callback_data='chatbot_info'),
        get_back_btn(lang),
    )
    return m


def get_mirrors_menu_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('btn_mirror_create_bonus', lang), callback_data='mirror_create'),
        types.InlineKeyboardButton(t('btn_mirror_random', lang), callback_data='public_mirrors'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='bonuses_menu'),
    )
    return m


menu = get_menu(is_admin=False)


def get_panel_select_markup(lang: str = 'ru', is_admin: bool = False) -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton(t('panel_select_regular', lang), callback_data='panel_regular'),
        types.InlineKeyboardButton(t('panel_select_premium', lang), callback_data='panel_premium'),
    )
    m.add(get_back_btn(lang))
    return m


def get_functions(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Обычный раздел — методы без premium."""
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_botnet', lang), callback_data='botnet_method'))
    m.add(
        types.InlineKeyboardButton(t('btn_bot_method', lang), callback_data='bot_method'),
        types.InlineKeyboardButton(t('btn_channel_method', lang), callback_data='channel_method'),
    )
    m.add(types.InlineKeyboardButton(t('btn_manual_method', lang), callback_data='manual_method'))
    m.add(
        types.InlineKeyboardButton(t('btn_aureport_method', lang), callback_data='aureport_method'),
        types.InlineKeyboardButton(t('btn_tida_method', lang), callback_data='tida_method'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_logger_method', lang), callback_data='logger_method'),
        types.InlineKeyboardButton('⚡ L4 Стрессер', callback_data='l4_method'),
    )
    m.add(types.InlineKeyboardButton(t('btn_datareg_method', lang), callback_data='datareg_method'))
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions'))
    return m


def get_premium_functions(lang: str = 'ru', is_admin: bool = False) -> types.InlineKeyboardMarkup:
    """Премиум раздел — методы требующие premium + admin-only методы."""
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_prem_botnet', lang), callback_data='prem_botnet_method'))
    m.add(
        types.InlineKeyboardButton(t('btn_web_method', lang), callback_data='web_method'),
        types.InlineKeyboardButton(t('btn_mail_method', lang), callback_data='mail_method'),
    )
    m.add(
        types.InlineKeyboardButton(t('btn_bank_method', lang), callback_data='bank_method'),
        types.InlineKeyboardButton(t('btn_dsa_method', lang), callback_data='dsa_method'),
    )
    m.add(types.InlineKeyboardButton(t('btn_telegraph_method', lang), callback_data='telegraph_method'))
    m.add(types.InlineKeyboardButton(t('btn_universal_method', lang), callback_data='universal_method'))
    m.add(types.InlineKeyboardButton(t('btn_session_method', lang), callback_data='support_method'))
    m.add(types.InlineKeyboardButton(t('btn_domain_killer', lang), callback_data='domain_killer_method'))
    m.add(types.InlineKeyboardButton('👤 Username-метод', callback_data='prem_username_method'))
    if is_admin:
        m.add(types.InlineKeyboardButton(t('btn_profile_report', lang), callback_data='profile_method'))
        m.add(types.InlineKeyboardButton(t('btn_trap_method', lang), callback_data='trap_method'))
    m.add(types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions'))
    return m


def get_channel_reason_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('ch_reason_personal', lang), callback_data='ch_reason_personal'),
        types.InlineKeyboardButton(t('ch_reason_spam', lang), callback_data='ch_reason_spam'),
        types.InlineKeyboardButton(t('ch_reason_adult', lang), callback_data='ch_reason_adult'),
        types.InlineKeyboardButton(t('ch_reason_children', lang), callback_data='ch_reason_children'),
        types.InlineKeyboardButton(t('ch_reason_violence', lang), callback_data='ch_reason_violence'),
        types.InlineKeyboardButton(t('ch_reason_other', lang), callback_data='ch_reason_other'),
        get_panel_back_btn(lang),
    )
    return m


def get_bot_reason_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('bot_reason_personal', lang), callback_data='bot_reason_personal'),
        types.InlineKeyboardButton(t('bot_reason_drugs', lang), callback_data='bot_reason_drugs'),
        types.InlineKeyboardButton(t('bot_reason_other', lang), callback_data='bot_reason_other'),
        get_panel_back_btn(lang),
    )
    return m


def get_tida_target_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('tida_target_account', lang), callback_data='tida_target_account'),
        types.InlineKeyboardButton(t('tida_target_bot', lang), callback_data='tida_target_bot'),
        types.InlineKeyboardButton(t('tida_target_chat', lang), callback_data='tida_target_chat'),
        types.InlineKeyboardButton(t('tida_target_channel', lang), callback_data='tida_target_channel'),
        get_panel_back_btn(lang),
    )
    return m


def get_free_menu_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('free_create_mirror', lang), callback_data='mirror_create'),
        types.InlineKeyboardButton(t('free_my_mirrors', lang), callback_data='mirror_list'),
        get_back_btn(lang),
    )
    return m


def get_admin_functions_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    return get_panel_select_markup(lang, is_admin=True)


def monitor_add_markup(target: str, can_add: bool, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    if can_add:
        import urllib.parse
        safe = urllib.parse.quote(target, safe='')
        markup.add(types.InlineKeyboardButton(
            t('monitor_btn_add', lang), callback_data=f'monitor_add_{safe[:50]}'
        ))
    else:
        markup.add(types.InlineKeyboardButton(
            t('monitor_btn_limit', lang), callback_data='monitor_limit'
        ))
    markup.add(types.InlineKeyboardButton(t('btn_main_menu', lang), callback_data='go_to_main_menu'))
    return markup


def tida_text_method_markup(target_type: str, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t('tida_ai_link', lang), callback_data=f'tida_ai_link_{target_type}'),
        types.InlineKeyboardButton(t('tida_ai_desc', lang), callback_data=f'tida_ai_desc_{target_type}'),
        types.InlineKeyboardButton(t('tida_manual_text', lang), callback_data=f'tida_manual_{target_type}'),
        get_panel_back_btn(lang),
    )
    return markup


def tida_text_confirm_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t('tida_confirm_use', lang), callback_data='tida_text_confirm'),
        types.InlineKeyboardButton(t('tida_confirm_change', lang), callback_data='tida_text_change'),
        types.InlineKeyboardButton(t('tida_ai_desc', lang), callback_data='tida_choose_ai_desc'),
        get_panel_back_btn(lang),
    )
    return markup


def manual_confirm_step1(method: str, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t('manual_read_btn', lang), url='https://br-v2.com/manual'),
        types.InlineKeyboardButton(t('manual_confirm_btn', lang), callback_data=f'manual_step2_{method}'),
        get_panel_back_btn(lang),
    )
    return markup


def manual_confirm_step2(method: str, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t('manual_confirm2_btn', lang), callback_data=f'manual_confirm_{method}'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions'),
    )
    return markup


# ─── Статичные клавиатуры (без перевода / частичный перевод) ─────────────────

functions = get_functions('ru')


# ─── DSA причины ──────────────────────────────────────────────────────────────
def get_dsa_reason_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("👶 Child abuse", callback_data='dsa_r_child_abuse'),
        types.InlineKeyboardButton("💥 Violence", callback_data='dsa_r_violence'),
        types.InlineKeyboardButton("🔫 Illegal goods", callback_data='dsa_r_illegal_goods'),
        types.InlineKeyboardButton("🔞 Illegal adult content", callback_data='dsa_r_illegal_adult'),
        types.InlineKeyboardButton("🔐 Personal data", callback_data='dsa_r_personal_data'),
        types.InlineKeyboardButton("💣 Terrorism", callback_data='dsa_r_terrorism'),
        types.InlineKeyboardButton("📢 Scam or spam", callback_data='dsa_r_scam'),
        types.InlineKeyboardButton("📝 Other", callback_data='dsa_r_other'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='functions'),
    )
    return m


# ─── DSA подкатегории ─────────────────────────────────────────────────────────
def get_dsa_sub_illegal_goods(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("🔫 Weapons", callback_data='dsa_s_weapons'),
        types.InlineKeyboardButton("💊 Drugs", callback_data='dsa_s_drugs'),
        types.InlineKeyboardButton("📄 Fake documents", callback_data='dsa_s_fake_docs'),
        types.InlineKeyboardButton("💵 Counterfeit money", callback_data='dsa_s_counterfeit'),
        types.InlineKeyboardButton("📦 Other goods", callback_data='dsa_s_other_goods'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='dsa_method'),
    )
    return m


def get_dsa_sub_illegal_adult(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("👶 Child abuse", callback_data='dsa_s_child_abuse_adult'),
        types.InlineKeyboardButton("📸 Non-consensual sexual imagery", callback_data='dsa_s_nonconsensual'),
        types.InlineKeyboardButton("🔞 Other illegal sexual content", callback_data='dsa_s_other_sexual'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='dsa_method'),
    )
    return m


def get_dsa_sub_personal_data(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("🖼 Private images", callback_data='dsa_s_private_images'),
        types.InlineKeyboardButton("📱 Phone number", callback_data='dsa_s_phone'),
        types.InlineKeyboardButton("🏠 Address", callback_data='dsa_s_address'),
        types.InlineKeyboardButton("📋 Other personal information", callback_data='dsa_s_other_personal'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='dsa_method'),
    )
    return m


def get_dsa_sub_scam(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("🎣 Phishing", callback_data='dsa_s_phishing'),
        types.InlineKeyboardButton("🎭 Impersonation", callback_data='dsa_s_impersonation'),
        types.InlineKeyboardButton("💸 Fraudulent sales", callback_data='dsa_s_fraud_sales'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='dsa_method'),
    )
    return m


# Обратная совместимость — статичные ru-версии
dsa_reason_markup = get_dsa_reason_markup('ru')
dsa_sub_illegal_goods = get_dsa_sub_illegal_goods('ru')
dsa_sub_illegal_adult = get_dsa_sub_illegal_adult('ru')
dsa_sub_personal_data = get_dsa_sub_personal_data('ru')
dsa_sub_scam = get_dsa_sub_scam('ru')


def dsa_text_confirm_markup(text_preview: str, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(t('dsa_use_text', lang), callback_data='dsa_text_confirm'),
        types.InlineKeyboardButton(t('dsa_custom_text', lang), callback_data='dsa_text_custom'),
        get_back_btn(lang),
    )
    return markup


# ─── Кейсы ────────────────────────────────────────────────────────────────────
case_menu_markup = types.InlineKeyboardMarkup(row_width=1)
case_menu_markup.add(
    types.InlineKeyboardButton("📦 Купить кейс — 2$ / 200₽", callback_data='case_buy'),
    types.InlineKeyboardButton("📦 Открыть кейс", callback_data='case_open'),
    back,
)

def get_case_menu_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('btn_case_buy', lang), callback_data='case_buy'),
        types.InlineKeyboardButton(t('btn_case_open', lang), callback_data='case_open'),
        get_bonuses_back_btn(lang),
    )
    return m


def get_referral_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('refs_exchange', lang), callback_data='exchange_refs'),
        get_bonuses_back_btn(lang),
    )
    return m


def get_case_buy_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("🇷🇺 СБП — 200 ₽", callback_data='case_buy_sbp'),
        types.InlineKeyboardButton("🚀 xRocket — 2 USDT", callback_data='case_buy_xrocket'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='case_menu'),
    )
    return m


def get_case_open_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('case_open_confirm', lang), callback_data='case_open_confirm'),
        types.InlineKeyboardButton(t('btn_back', lang), callback_data='case_menu'),
    )
    return m


# Обратная совместимость
case_buy_markup = get_case_buy_markup('ru')
case_open_markup = get_case_open_markup('ru')


# ─── Промо-тип ────────────────────────────────────────────────────────────────
def get_promo_type_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('promo_type_normal', lang), callback_data='promo_type_normal'),
        types.InlineKeyboardButton(t('promo_type_premium', lang), callback_data='promo_type_premium'),
        types.InlineKeyboardButton(t('promo_type_reports', lang), callback_data='promo_type_reports'),
        get_back_btn(lang),
    )
    return m


promo_type_markup = get_promo_type_markup('ru')

channel_reason_markup = get_channel_reason_markup('ru')
bot_reason_markup = get_bot_reason_markup('ru')
tida_target_markup = get_tida_target_markup('ru')
free_menu_markup = get_free_menu_markup('ru')

# ─── Меню Бесплатно ───────────────────────────────────────────────────────────
# (kept for compat, use get_free_menu_markup(lang) for language-aware version)

def get_pay_method_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton(t('pay_sbp', lang), callback_data='yoomoney'), get_back_btn(lang))
    return m


pay_method = get_pay_method_markup('ru')


def get_info_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('btn_info_manual', lang), url='https://br-v2.com/manual'),
        get_back_btn(lang),
    )
    return m


info_markup = get_info_markup('ru')


def get_del_message_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('btn_read_done', lang), callback_data='close'),
        types.InlineKeyboardButton(t('btn_subscribe_chan', lang), url=config.bot_channel_link),
    )
    return m


def get_close_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton(t('btn_close', lang), callback_data='close'))
    return m


del_message = get_del_message_markup('ru')
del_message2 = get_close_markup('ru')

admin_markup = types.InlineKeyboardMarkup(row_width=2)
add_subsribe = types.InlineKeyboardButton("[+] Выдать подписку", callback_data='add_subsribe')
clear_subscribe = types.InlineKeyboardButton("[-] Забрать подписку", callback_data='clear_subscribe')
add_prem = types.InlineKeyboardButton("[+] Выдать премиум", callback_data='add_prem')
clear_prem = types.InlineKeyboardButton("[-] Забрать премиум", callback_data='clear_prem')
send_all = types.InlineKeyboardButton("[📢] Рассылка", callback_data='send_all')
block_user_btn = types.InlineKeyboardButton("[🚫] Заблокировать", callback_data='block_user_admin')
unblock_user_btn = types.InlineKeyboardButton("[✅] Разблокировать", callback_data='unblock_user_admin')
delete_user_btn = types.InlineKeyboardButton("[🗑] Удалить из БД", callback_data='delete_user_admin')
users_list_btn = types.InlineKeyboardButton("[👥] Список пользователей", callback_data='users_list_0')
mirrors_list_btn = types.InlineKeyboardButton("[🪞] Зеркала", callback_data='admin_mirrors_0')
add_reports_btn = types.InlineKeyboardButton("[🎯+] Выдать репорты", callback_data='admin_add_reports')
remove_reports_btn = types.InlineKeyboardButton("[🎯-] Забрать репорты", callback_data='admin_remove_reports')
create_promo_btn = types.InlineKeyboardButton("[💎] Создать промокод", callback_data='admin_create_promo')
add_case_btn = types.InlineKeyboardButton("[🎁+] Выдать кейс", callback_data='admin_add_case')
admin_markup.add(add_subsribe, clear_subscribe)
admin_markup.add(add_prem, clear_prem)
admin_markup.add(send_all)
admin_markup.add(block_user_btn, unblock_user_btn)
admin_markup.add(delete_user_btn)
admin_markup.add(users_list_btn)
admin_markup.add(mirrors_list_btn)
admin_markup.add(add_reports_btn, remove_reports_btn)
admin_markup.add(create_promo_btn)
admin_markup.add(add_case_btn)
check_user_btn = types.InlineKeyboardButton("[🔍] Проверить пользователя", callback_data='admin_check_user')
admin_markup.add(check_user_btn)
send_msg_btn = types.InlineKeyboardButton("[✉️] Отправить сообщение", callback_data='admin_send_msg')
admin_markup.add(send_msg_btn)
maintenance_btn = types.InlineKeyboardButton("🔧 Включить тех. работы", callback_data='toggle_maintenance')
admin_markup.add(maintenance_btn)
rotate_send_btn = types.InlineKeyboardButton("🔄 Изменить Send", callback_data='admin_rotate_send')
manage_wallets_btn = types.InlineKeyboardButton("💼 Кошельки", callback_data='admin_manage_wallets')
admin_markup.add(rotate_send_btn, manage_wallets_btn)
warn_user_btn = types.InlineKeyboardButton("[⚠️] Выдать предупреждение", callback_data='admin_warn_user')
admin_markup.add(warn_user_btn)
give_tg_btn = types.InlineKeyboardButton("[📲] Выдать TG аккаунт", callback_data='admin_give_tg')
admin_markup.add(give_tg_btn)

shop_markup = types.InlineKeyboardMarkup(row_width=2)
sub1 = types.InlineKeyboardButton("⚡️ 1 день", callback_data='sub_1')
sub3 = types.InlineKeyboardButton("⚡️ 3 дня", callback_data='sub_3')
sub7 = types.InlineKeyboardButton("⚡️ 7 дней", callback_data='sub_7')
sub30 = types.InlineKeyboardButton("⚡️ 30 дней", callback_data='sub_30')
subforever = types.InlineKeyboardButton("⚡️ 60 дней", callback_data='sub_60')
premupgrade = types.InlineKeyboardButton("⭐️ Premium", callback_data='sub_premupgrade')
buyforadmins = types.InlineKeyboardButton("💳 Оплата картой", callback_data='buyforadmins')
preminfo = types.InlineKeyboardButton("👑 Что такое премиум?", callback_data='preminfo')
shop_markup.add(sub1, sub3)
shop_markup.add(sub7, sub30)
shop_markup.add(subforever)
shop_markup.add(premupgrade)
shop_markup.add(preminfo)
shop_markup.add(back)

check_markup = types.InlineKeyboardMarkup(row_width=1)
channel = types.InlineKeyboardButton("[1️⃣] Подпишись", url=config.bot_channel_link)
channel2 = types.InlineKeyboardButton("[2️⃣] Подпишись", url=config.bot_channel2_link)
check_sub = types.InlineKeyboardButton("[🔎] Проверить", callback_data='back')
check_markup.add(channel, channel2, check_sub)

referral_markup = types.InlineKeyboardMarkup(row_width=1)
exchange_refs_btn = types.InlineKeyboardButton("🔄 Обменять 10 рефералов → 1 день", callback_data='exchange_refs')
referral_markup.add(exchange_refs_btn, back)

wheel_markup = types.InlineKeyboardMarkup(row_width=1)
spin_btn = types.InlineKeyboardButton("🎡 Крутить!", callback_data='spin_wheel')
wheel_markup.add(spin_btn, back)

def get_wheel_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('btn_spin', lang), callback_data='spin_wheel'),
        get_bonuses_back_btn(lang),
    )
    return m

bank_select_markup = types.InlineKeyboardMarkup(row_width=1)
bank_select_markup.add(
    types.InlineKeyboardButton("🟡 Т-Банк (Тинькофф)", callback_data='bank_tbank'),
    types.InlineKeyboardButton("🔴 Альфа-Банк", callback_data='bank_alfa'),
    types.InlineKeyboardButton("🟢 Сбер Банк", callback_data='bank_sber'),
    types.InlineKeyboardButton("🔵 Озон Банк", callback_data='bank_ozon'),
    back
)

telegraph_confirm_markup = types.InlineKeyboardMarkup(row_width=1)
telegraph_confirm_markup.add(
    types.InlineKeyboardButton("✅ Отправить", callback_data='telegraph_confirm'),
    types.InlineKeyboardButton("✏️ Написать свой текст", callback_data='telegraph_custom'),
    back,
)

trap_done_markup = types.InlineKeyboardMarkup(row_width=1)
trap_done_markup.add(
    types.InlineKeyboardButton("✅ Готово — жертва написала /start", callback_data='trap_done'),
    types.InlineKeyboardButton("❌ Отмена", callback_data='trap_cancel'),
)

media_markup = types.InlineKeyboardMarkup(row_width=1)
media_markup.add(
    types.InlineKeyboardButton("📤 Отправить видео", callback_data='media_submit'),
    types.InlineKeyboardButton("📋 Мои заявки", callback_data='media_my'),
    types.InlineKeyboardButton("📜 Условия", callback_data='media_terms'),
    back,
)

def get_media_markup(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton(t('btn_media_submit', lang), callback_data='media_submit'),
        types.InlineKeyboardButton(t('btn_media_my', lang), callback_data='media_my'),
        types.InlineKeyboardButton(t('btn_media_terms', lang), callback_data='media_terms'),
        get_back_btn(lang),
    )
    return m

media_platform_markup = types.InlineKeyboardMarkup(row_width=1)
media_platform_markup.add(
    types.InlineKeyboardButton("🎵 TikTok", callback_data='media_p_tiktok'),
    types.InlineKeyboardButton("🔴 YouTube", callback_data='media_p_youtube'),
    types.InlineKeyboardButton("▶️ YouTube Shorts", callback_data='media_p_shorts'),
    types.InlineKeyboardButton("[🔙] Назад", callback_data='media'),
)


def media_confirm_markup(platform: str, link: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data='media_confirm'),
        types.InlineKeyboardButton("✏️ Изменить ссылку", callback_data='media_submit'),
        types.InlineKeyboardButton("[🔙] Назад", callback_data='media'),
    )
    return markup


def media_admin_markup(sub_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f'media_ok_{sub_id}'),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f'media_rej_{sub_id}'),
    )
    return markup
