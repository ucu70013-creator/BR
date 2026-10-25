import asyncio
import aiohttp
import random
import string
from pathlib import Path
from utils import esc_md

# URL relay на PythonAnywhere
RELAY_URL = "https://paradise112.pythonanywhere.com/send"
RELAY_TOKEN = "brv2_relay_secret_2026"


# ─── Спиннер текста (без внешних API) ────────────────────────────────────────

# Синонимы для замены часто встречающихся слов
_SYNONYMS = {
    # русские
    "жалоба": ["обращение", "претензия", "заявление", "сообщение"],
    "жалобу": ["обращение", "претензию", "заявление"],
    "жалобы": ["обращения", "претензии", "заявления"],
    "прошу": ["прошу вас", "хочу", "хотелось бы", "необходимо"],
    "заблокировать": ["заблокировать", "удалить", "ограничить", "принять меры против"],
    "пользователь": ["аккаунт", "пользователь", "участник"],
    "пользователя": ["аккаунта", "пользователя", "участника"],
    "нарушает": ["нарушает", "не соблюдает", "игнорирует"],
    "правила": ["правила", "нормы", "политику"],
    "срочно": ["срочно", "незамедлительно", "как можно скорее"],
    "незаконно": ["незаконно", "противоправно", "недопустимо"],
    "спам": ["спам", "нежелательные сообщения", "массовую рассылку"],
    # английские
    "please": ["please", "kindly", "I ask you to", "I request you to"],
    "block": ["block", "ban", "restrict", "remove"],
    "user": ["user", "account", "member"],
    "violates": ["violates", "breaks", "ignores", "disregards"],
    "rules": ["rules", "guidelines", "terms of service", "policies"],
    "spam": ["spam", "unsolicited messages", "mass messaging"],
    "urgent": ["urgent", "immediate", "as soon as possible"],
    "illegal": ["illegal", "unlawful", "prohibited"],
    "report": ["report", "complaint", "notification"],
}

# Вариации тем писем
_SUBJECT_TEMPLATES = [
    "{base}",
    "{base} — обращение #{num}",
    "Re: {base}",
    "Fwd: {base}",
    "{base} (важно)",
    "{base} | ticket #{num}",
    "[Жалоба] {base}",
    "{base} — требует внимания",
]

_SUBJECT_TEMPLATES_EN = [
    "{base}",
    "Re: {base}",
    "{base} - Case #{num}",
    "Urgent: {base}",
    "{base} (follow-up)",
    "Complaint: {base}",
    "{base} | ref #{num}",
]

# Вступительные фразы для начала письма
_INTROS_RU = [
    "Здравствуйте, ",
    "Добрый день, ",
    "Уважаемая служба поддержки, ",
    "Команда поддержки, ",
    "Обращаюсь к вам по следующему вопросу. ",
    "Пишу вам с жалобой. ",
    "",
]

_INTROS_EN = [
    "Hello, ",
    "Dear support team, ",
    "Hi there, ",
    "To whom it may concern, ",
    "I am writing to report the following. ",
    "",
]

# Завершающие фразы
_OUTROS_RU = [
    "\n\nС уважением.",
    "\n\nПрошу рассмотреть данное обращение.",
    "\n\nЖду ответа.",
    "\n\nСпасибо за внимание.",
    "",
]

_OUTROS_EN = [
    "\n\nBest regards.",
    "\n\nThank you for your attention.",
    "\n\nI await your response.",
    "\n\nSincerely.",
    "",
]


def _is_russian(text: str) -> bool:
    ru_chars = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
    return ru_chars > len(text) * 0.2


def _spin_word(word: str) -> str:
    """Заменяет слово на синоним с вероятностью 40%."""
    lower = word.lower().rstrip('.,!?;:')
    if lower in _SYNONYMS and random.random() < 0.4:
        replacement = random.choice(_SYNONYMS[lower])
        # Сохраняем регистр первой буквы
        if word[0].isupper():
            replacement = replacement.capitalize()
        return replacement
    return word


def spin_text(text: str) -> str:
    """Слегка модифицирует текст: заменяет синонимы + добавляет вступление/концовку."""
    words = text.split()
    spun_words = [_spin_word(w) for w in words]
    spun = " ".join(spun_words)

    is_ru = _is_russian(text)
    intro = random.choice(_INTROS_RU if is_ru else _INTROS_EN)
    outro = random.choice(_OUTROS_RU if is_ru else _OUTROS_EN)

    return intro + spun + outro


def spin_subject(subject: str) -> str:
    """Генерирует уникальную тему на основе оригинала."""
    num = random.randint(1000, 9999)
    is_ru = _is_russian(subject)
    templates = _SUBJECT_TEMPLATES if is_ru else _SUBJECT_TEMPLATES_EN
    template = random.choice(templates)
    return template.format(base=subject, num=num)


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def load_mails(file_path="mails.txt"):
    if not Path(file_path).exists():
        return []
    result = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            parts = line.split(":")
            # formats: email:pass  or  email:pass:smtp.host
            email, password = parts[0], parts[1]
            result.append(f"{email}:{password}")
    return result


def mask_email(email):
    local, domain = email.split("@")
    masked_local = (local[0] + "***") if len(local) >= 2 else "*"
    return f"{masked_local}@{esc_md(domain)}"


def generate_log_filename():
    rand = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
    return f"brown_v2_mail_log_{rand}.txt"


# ─── Отправка одного письма через relay ──────────────────────────────────────

async def _send_via_relay(sender_email, receiver_email, subject, body, password) -> tuple[bool, str]:
    payload = {
        "token": RELAY_TOKEN,
        "sender": sender_email,
        "password": password,
        "receiver": receiver_email,
        "subject": subject,
        "body": body,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(RELAY_URL, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.content_type != "application/json":
                return False, f"relay bad response: {resp.status}"
            data = await resp.json()
            if data.get("ok"):
                return True, ""
            return False, data.get("error", "relay error")


async def _send_via_smtp(sender_email, receiver_email, subject, body, password) -> tuple[bool, str]:
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    domain = sender_email.split("@")[-1].lower()
    smtp_map = {
        "gmail.com":    ("smtp.gmail.com", 587),
        "yahoo.com":    ("smtp.mail.yahoo.com", 587),
        "outlook.com":  ("smtp.office365.com", 587),
        "hotmail.com":  ("smtp.office365.com", 587),
        "mail.ru":      ("smtp.mail.ru", 587),
        "yandex.ru":    ("smtp.yandex.ru", 587),
        "icloud.com":   ("smtp.mail.me.com", 587),
    }
    host, port = smtp_map.get(domain, ("smtp.gmail.com", 587))

    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        loop = asyncio.get_event_loop()
        def _do_send():
            ctx = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.login(sender_email, password)
                s.sendmail(sender_email, receiver_email, msg.as_string())
        await loop.run_in_executor(None, _do_send)
        return True, ""
    except Exception as e:
        return False, str(e)


async def send_email_async(sender_email, receiver_email, subject, body, password):
    """Отправляет письмо: сначала через relay, при сбое — прямо по SMTP."""
    try:
        ok, err = await _send_via_relay(sender_email, receiver_email, subject, body, password)
        if ok:
            return True, ""
    except Exception as e:
        err = str(e)
    # relay недоступен — прямой SMTP
    try:
        return await _send_via_smtp(sender_email, receiver_email, subject, body, password)
    except Exception as e:
        return False, f"smtp: {e}"


# ─── Массовая отправка ────────────────────────────────────────────────────────

async def send_bulk_emails(subject, text, mails, receiver_emails, user_id, username, bot=None, chat_id=None):
    try:
        success = 0
        error = 0
        log = []
        log.append("Brown V2 log | mail-method")
        log.append("-" * 42)
        log.append(f"Пользователь: {user_id} (*@{username}*)")
        log.append(f"Тема: {subject}")
        log.append(f"Текст: {text}")
        log.append("-" * 42)

        total = len(mails) * len(receiver_emails)

        # Рассчитываем среднее время ожидания
        avg_delay = (2 + 3) / 2  # 2.5 сек
        estimated_seconds = int(total * avg_delay)
        estimated_minutes = estimated_seconds // 60
        estimated_secs_left = estimated_seconds % 60

        if estimated_minutes > 0:
            time_str = f"~{estimated_minutes} мин {estimated_secs_left} сек"
        else:
            time_str = f"~{estimated_seconds} сек"

        # Отправляем прогресс-сообщение пользователю
        progress_msg_id = None
        if bot and chat_id:
            try:
                sent_msg = await bot.send_message(
                    chat_id,
                    f"📤 *Жалобы отправляются...*\n"
                    f"*└─ Писем всего: {total}*\n"
                    f"*└─ Среднее время ожидания: {time_str}*\n\n"
                    f"⏳ *Пожалуйста, подождите...*",
                    parse_mode="Markdown"
                )
                progress_msg_id = sent_msg.message_id
            except Exception:
                pass

        message_counter = 1

        for sender in mails:
            sender_login, sender_pass = sender.split(":", 1)
            masked_sender = mask_email(sender_login)

            for receiver in receiver_emails:
                # Уникальная тема и текст для каждого письма
                unique_subject = spin_subject(subject)
                unique_body = spin_text(text)

                sent, err_text = await send_email_async(
                    sender_login, receiver, unique_subject, unique_body, sender_pass
                )

                if sent:
                    status = "[ДОСТАВЛЕНО]"
                    success += 1
                else:
                    status = f"[НЕ ДОСТАВЛЕНО] ({err_text.strip()})"
                    error += 1

                log.append(f"[{message_counter}] {masked_sender} ---> {receiver} {status}")
                message_counter += 1

                # Задержка между письмами — укладываемся в 5 минут
                if message_counter <= total:
                    delay = random.uniform(2, 3)
                    await asyncio.sleep(delay)

        log.append("-" * 42)
        log.append(f"Успешно: {success}")
        log.append(f"Неуспешно: {error}")

        # Удаляем прогресс-сообщение
        if bot and chat_id and progress_msg_id:
            try:
                await bot.delete_message(chat_id, progress_msg_id)
            except Exception:
                pass

        log_filename = generate_log_filename()
        log_path = Path(log_filename)
        log_path.write_text("\n".join(log), encoding="utf-8")

        return success, error, str(log_path)

    except Exception as e:
        print("Ошибка при отправке:", e)
        return 0, 0, ""
