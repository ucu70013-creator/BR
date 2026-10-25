"""
Brown V2 | bank_snos.py
Метод блокировки банковских карт по 115-ФЗ.
"""

import random
from config import bot_logs
from aiogram import Bot
import keyboards
from utils import esc_md

bot = None
main_bot = None


def set_bot_bank(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


BANKS = {
    "tbank":   "Т-Банк (Тинькофф)",
    "alfa":    "Альфа-Банк",
    "sber":    "Сбер Банк",
    "ozon":    "Озон Банк",
}

_BANK_EMAILS = {
    "tbank": "support@tinkoff.ru",
    "alfa":  "mail@alfabank.ru",
    "sber":  "help@sberbank.ru",
    "ozon":  "help@finance.ozon.ru",
}

_BANK_SUBJECTS = {
    "tbank": "Сообщение о признаках незаконной предпринимательской деятельности и нарушении 115-ФЗ клиентом Т-Банк",
    "alfa":  "Сообщение о признаках незаконной предпринимательской деятельности и нарушении 115-ФЗ клиентом Альфа-Банк",
    "sber":  "Сообщение о признаках незаконной предпринимательской деятельности и нарушении 115-ФЗ клиентом Сбер Банк",
    "ozon":  "Сообщение о признаках незаконной предпринимательской деятельности и нарушении 115-ФЗ клиентом Озон Банк",
}

_FIRST_NAMES = [
    "Александр", "Дмитрий", "Иван", "Михаил", "Андрей",
    "Сергей", "Алексей", "Николай", "Владимир", "Артём",
    "Елена", "Наталья", "Мария", "Анна", "Ольга",
    "Татьяна", "Ирина", "Светлана", "Юлия", "Екатерина",
]

_LAST_NAMES = [
    "Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев",
    "Петров", "Соколов", "Михайлов", "Новиков", "Фёдоров",
    "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов",
    "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
]

_PATRONYMICS_M = [
    "Александрович", "Дмитриевич", "Иванович", "Михайлович", "Андреевич",
    "Сергеевич", "Алексеевич", "Николаевич", "Владимирович", "Артёмович",
]

_PATRONYMICS_F = [
    "Александровна", "Дмитриевна", "Ивановна", "Михайловна", "Андреевна",
    "Сергеевна", "Алексеевна", "Николаевна", "Владимировна", "Артёмовна",
]

_FEMALE_NAMES = {
    "Елена", "Наталья", "Мария", "Анна", "Ольга",
    "Татьяна", "Ирина", "Светлана", "Юлия", "Екатерина",
}


def _random_fio() -> str:
    first = random.choice(_FIRST_NAMES)
    last = random.choice(_LAST_NAMES)
    if first in _FEMALE_NAMES:
        patr = random.choice(_PATRONYMICS_F)
        last += "а"
    else:
        patr = random.choice(_PATRONYMICS_M)
    return f"{last} {first} {patr}"


def _build_email_body(bank_name: str, card_data: str, fio: str) -> str:
    return (
        f"Здравствуйте!\n\n"
        f"Обращаюсь к вам для инициации проверки в отношении клиента {bank_name}. "
        f"Имеются веские основания полагать, что данный клиент использует свой личный банковский счет "
        f"для ведения скрытой (теневой) коммерческой деятельности, что является нарушением "
        f"Федерального закона № 115-ФЗ, а также Условий банковского обслуживания физических лиц.\n\n"
        f"По имеющейся информации, клиент занимается продажей сомнительных цифровых услуг и "
        f"программного обеспечения в интернете (в частности, в мессенджере Telegram) и на регулярной "
        f"основе принимает платежи от третьих (физических) лиц на свою дебетовую карту.\n\n"
        f"Известные реквизиты клиента:\n\n"
        f" Номер банковской карты / номер телефона СБП ({bank_name}): {card_data}\n\n"
        f"К сожалению, на данный момент я не располагаю скриншотами переписки или номером телефона "
        f"нарушителя. Однако характер его деятельности можно легко установить путем анализа активности "
        f"на его счете.\n\n"
        f"Прошу службу безопасности и подразделение финансового мониторинга проанализировать "
        f"транзакционную историю по указанной карте. Прошу обратить особое внимание на частоту, "
        f"однотипность и количество входящих переводов от разных физических лиц. В случае подтверждения "
        f"признаков систематического получения дохода от незарегистрированной коммерческой деятельности, "
        f"прошу принять соответствующие меры реагирования и ограничить дистанционное обслуживание "
        f"клиента в рамках 115-ФЗ.\n\n"
        f"Заранее благодарю за проведение проверки.\n\n"
        f"С уважением,\n\n"
        f"{fio}"
    )


async def process_bank_report(bank_key: str, card_data: str, user: int, username: str, notify_bot=None):
    _notify = notify_bot or bot
    bank_name = BANKS.get(bank_key, bank_key)
    bank_email = _BANK_EMAILS.get(bank_key)
    subject = _BANK_SUBJECTS.get(bank_key, "Обращение по 115-ФЗ")

    caption_user = (
        f"🏦 *Заявка на блокировку карты принята!*\n\n"
        f"*└─ Банк:* {bank_name}\n"
        f"*└─ Данные:* {card_data}\n\n"
        f"⏳ *Примерное время блокировки по 115-ФЗ — 3 дня*\n\n"
        f"_Заявка передана администратору_"
    )

    caption_log = (
        f"🏦 *БЛОКИРОВКА КАРТЫ*\n\n"
        f"*└─ Банк:* {bank_name}\n"
        f"*└─ Данные:* {card_data}\n"
        f"*└─ Пользователь:* {user} (*@{username}*)"
    )

    try:
        await _notify.send_message(user, caption_user, parse_mode="Markdown", reply_markup=keyboards.main_menu)
    except Exception as e:
        print(f"[BANK] Ошибка отправки пользователю: {e}")

    try:
        await main_bot.send_message(bot_logs, caption_log, parse_mode="Markdown")
    except Exception as e:
        print(f"[BANK] Ошибка отправки лога: {e}")

    # Автоматическая отправка жалоб в банк
    if bank_email:
        try:
            from mail_snos import load_mails, send_email_async
            mails = load_mails()
            if mails:
                fio = _random_fio()
                body = _build_email_body(bank_name, card_data, fio)
                success = 0
                errors = 0
                for entry in mails:
                    sender_login, sender_pass = entry.split(":", 1)
                    ok, _ = await send_email_async(sender_login, bank_email, subject, body, sender_pass)
                    if ok:
                        success += 1
                    else:
                        errors += 1
                try:
                    await main_bot.send_message(
                        bot_logs,
                        f"📧 *Авто-рассылка в {bank_name}:*\n"
                        f"*└─ Отправлено:* ✅ {success} / ❌ {errors}\n"
                        f"*└─ На адрес:* `{bank_email}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"[BANK] Ошибка авто-рассылки: {e}")
