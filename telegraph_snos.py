"""
Brown V2 | telegraph_snos.py
Метод: снос Telegraph статей через email-relay
- Парсит содержимое статьи
- Groq генерирует тему и текст (EN, макс 500 символов)
- Отправляет 12 писем через relay (4 почты × 3 адреса)
- spin_text/spin_subject для уникальности каждого письма
"""

import asyncio
import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiohttp

import config
from utils import now_msk, esc_md
from mail_snos import spin_text, spin_subject

logger = logging.getLogger(__name__)

GROQ_KEY = os.environ.get("GROQ_KEY", config.GROQ_KEY)

# ─── SMTP-настройки по домену ─────────────────────────────────────────────────
SMTP_CONFIGS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "rambler.ru": ("smtp.rambler.ru", 587),
    "mail.ru":   ("smtp.mail.ru",   587),
    "yandex.ru": ("smtp.yandex.ru", 587),
    "ya.ru":     ("smtp.yandex.ru", 587),
}
SMTP_TIMEOUT = 20


def _get_smtp_config(email: str) -> tuple[str, int]:
    domain = email.split("@")[-1].lower()
    return SMTP_CONFIGS.get(domain, ("smtp." + domain, 587))


# ─── Загрузка отправителей из mails.txt ──────────────────────────────────────
def _load_senders() -> list[tuple[str, str]]:
    """
    Читает mails.txt (формат 'email:password' или 'email:app password со пробелами').
    Возвращает список (email, password).
    """
    path = Path(__file__).parent / "mails.txt"
    senders = []
    if not path.exists():
        logger.warning("[TELEGRAPH] mails.txt не найден, используем fallback")
        return senders
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            email, _, pwd = line.partition(":")
            email = email.strip()
            pwd = pwd.strip()
            if email and pwd:
                senders.append((email, pwd))
    return senders


SENDERS = _load_senders()

RECIPIENTS = [
    "abuse@telegram.org",
    "support@telegram.org",
    "dmca@telegram.org",
]

bot = None


def set_bot_telegraph(b):
    global bot
    bot = b


# ─── Парсинг статьи через Telegraph API ──────────────────────────────────────
async def fetch_telegraph_text(url: str) -> tuple[str, int]:
    """
    Получает чистый текст статьи через официальный Telegraph API.
    Возвращает (текст, http_status).
    """
    try:
        # Извлекаем path из URL: https://telegra.ph/path-01-01 → path-01-01
        path = url.strip().rstrip("/")
        path = re.sub(r"https?://(telegra\.ph|graph\.org)/", "", path)

        api_url = f"https://api.telegra.ph/getPage/{path}?return_content=true"

        connector = aiohttp.TCPConnector()
        session = aiohttp.ClientSession(connector=connector)
        try:
            async with session.get(
                api_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0"}
            ) as resp:
                if resp.status != 200:
                    return "", resp.status
                data = await resp.json(content_type=None)
        finally:
            await session.close()
            await connector.close()

        if not data.get("ok"):
            return "", 404

        # Рекурсивно извлекаем текст из content nodes
        def extract_text(nodes) -> str:
            if not nodes:
                return ""
            result = []
            for node in nodes:
                if isinstance(node, str):
                    result.append(node)
                elif isinstance(node, dict):
                    children = node.get("children", [])
                    result.append(extract_text(children))
            return " ".join(result)

        content = data.get("result", {}).get("content", [])
        text = extract_text(content)
        text = re.sub(r"\s+", " ", text).strip()

        print(f"[TELEGRAPH] Статья получена: {len(text)} символов", flush=True)
        return text[:3000], 200

    except Exception as e:
        logger.error(f"[TELEGRAPH] fetch error: {e}")
        return "", 0


# ─── Groq генерация ───────────────────────────────────────────────────────────
async def generate_telegraph_text(article_url: str, article_text: str) -> tuple[str, str]:
    print(f"[TELEGRAPH] generate_telegraph_text START", flush=True)
    fallback_subject = f"ToS Violation Report"
    fallback_body = (
        f"Dear Telegram Support,\n\n"
        f"I am reporting a Telegraph article that violates Telegram's Terms of Service "
        f"(telegram.org/tos). The article contains prohibited content.\n\n"
        f"Article: {article_url}\n\n"
        f"Please review and take appropriate action.\n\nThank you."
    )

    prompt = (
        f"Write a short formal complaint email to Telegram support about a Telegraph article.\n"
        f"Article URL: {article_url}\n"
        f"Article content: {article_text[:600]}\n\n"
        f"Rules:\n"
        f"- English only\n"
        f"- Max 400 characters for the body\n"
        f"- Mention the article violates telegram.org/tos\n"
        f"- Include the article URL\n"
        f"- No legal references\n"
        f"- Be direct and formal\n\n"
        f"First line = email subject (max 60 chars)\n"
        f"Rest = email body\n"
        f"No labels, no formatting, just the text."
    )

    connector = aiohttp.TCPConnector()
    session = aiohttp.ClientSession(connector=connector)
    try:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-oss-20b",
                "messages": [
                    {"role": "system", "content": "You generate formal complaint emails. Be concise and professional."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 300,
                "temperature": 0.7,
                "reasoning_effort": "low",
            },
            timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            data = await resp.json(content_type=None)
            if "choices" not in data:
                print(f"[TELEGRAPH] Groq no choices: {str(data)[:400]}", flush=True)
                return fallback_subject, fallback_body

            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            # openai/gpt-oss-20b puts output in `reasoning` when content is empty
            if not content:
                content = (msg.get("reasoning") or "").strip()
                print(f"[TELEGRAPH] Groq using reasoning field: {content[:100]}", flush=True)
            else:
                print(f"[TELEGRAPH] Groq raw: {content[:200]}", flush=True)

            if not content:
                print(f"[TELEGRAPH] Groq both empty, data: {str(data)[:300]}", flush=True)
                return fallback_subject, fallback_body

            lines = content.strip().split("\n")
            subject = lines[0].strip()[:100] if lines else fallback_subject
            body = "\n".join(lines[1:]).strip()[:600] if len(lines) > 1 else fallback_body

            if not subject:
                subject = fallback_subject
            if not body:
                body = fallback_body

            return subject, body

    except Exception as e:
        print(f"[TELEGRAPH] Groq error: {e}", flush=True)
        return fallback_subject, fallback_body
    finally:
        await session.close()
        await connector.close()


# ─── Отправка одного письма через relay ───────────────────────────────────────
def _send_smtp(sender_email: str, sender_pass: str,
               recipient: str, subject: str, body: str) -> tuple[bool, str]:
    """Отправляет письмо через SMTP 587+STARTTLS. Хост определяется по домену отправителя."""
    smtp_host, smtp_port = _get_smtp_config(sender_email)
    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = smtplib.SMTP(smtp_host, smtp_port, timeout=SMTP_TIMEOUT)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_pass)
        server.sendmail(sender_email, recipient, msg.as_string())
        server.quit()
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "auth error"
    except smtplib.SMTPException as e:
        return False, str(e)[:60]
    except Exception as e:
        return False, str(e)[:60]


# ─── Главная функция ──────────────────────────────────────────────────────────
async def main_telegraph_snos(
    article_url: str,
    user_id: int,
    username: str,
    custom_text: str = "",
    custom_subject: str = "",
    notify_bot=None,
) -> dict:
    from config import bot_logs
    import keyboards
    from aiogram import types as aiogram_types

    print(f"\n[TELEGRAPH] 🚀 Старт | {article_url} | {user_id} (*@{username}*)", flush=True)

    if custom_text and custom_subject:
        subject = custom_subject
        body = custom_text
        print(f"[TELEGRAPH] Используем пользовательский текст", flush=True)
    else:
        article_text, status = await fetch_telegraph_text(article_url)
        if status == 404:
            return {"ok": 0, "fail": 0, "error": "404"}
        print(f"[TELEGRAPH] Генерирую текст через Groq...", flush=True)
        subject, body = await generate_telegraph_text(article_url, article_text)

    print(f"[TELEGRAPH] Тема: {subject}", flush=True)
    print(f"[TELEGRAPH] Текст: {body[:80]}...", flush=True)

    ok = 0
    fail = 0
    total = len(SENDERS) * len(RECIPIENTS)

    if total == 0:
        print("[TELEGRAPH] ⚠️ SENDERS пуст — нет почт в mails.txt", flush=True)
        return {"ok": 0, "fail": 0, "subject": subject, "body": body}

    # Все письма параллельно — каждое со своим спином
    async def send_one(sender_email, sender_pass, recipient):
        spun_subj = spin_subject(subject)
        spun_body = spin_text(body)
        ok, err = await asyncio.get_event_loop().run_in_executor(
            None, _send_smtp, sender_email, sender_pass, recipient, spun_subj, spun_body
        )
        if not ok:
            print(f"[TELEGRAPH] SMTP {sender_email}→{recipient}: {err}", flush=True)
        return ok, recipient

    tasks = [
        send_one(email, pwd, recipient)
        for email, pwd in SENDERS
        for recipient in RECIPIENTS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    for result, recipient in results:
        if result:
            ok += 1
            print(f"[TELEGRAPH] ✅ → {recipient}", flush=True)
        else:
            fail += 1
            print(f"[TELEGRAPH] ❌ → {recipient}", flush=True)
    print(f"[TELEGRAPH] Итого: ✅ {ok} / ❌ {fail}", flush=True)

    # Добавляем в мониторинг
    if ok > 0:
        try:
            from monitor_snos import telegraph_monitor_add
            telegraph_monitor_add(article_url, user_id)
        except Exception as e:
            print(f"[TELEGRAPH] Ошибка мониторинга: {e}", flush=True)

    caption = (
        f"📄 *Telegraph снос завершён!*\n"
        f"*└─* [Статья]({article_url})\n\n"
        f"📨 *Жалоб отправлено:* {ok}/{total}\n"
        f"✅ *Успешно:* {ok}\n"
        f"❌ *Ошибок:* {fail}"
    )

    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user_id)
        _log_uid = "скрыт" if _is_hid else str(user_id)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user_id), username

    caption_log = (
        f"📄 *Telegraph*\n"
        f"*└─* [Статья]({article_url})\n"
        f"✅ {ok} | ❌ {fail}\n"
        f"👤 {_log_uid} (*@{_log_uname}*)"
    )

    _notify = notify_bot or bot
    try:
        await _notify.send_message(
            user_id, caption,
            parse_mode="Markdown",
            reply_markup=keyboards.main_menu,
            disable_web_page_preview=True
        )
        await (bot or _notify).send_message(
            bot_logs, caption_log,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"[TELEGRAPH] Ошибка отправки отчёта: {e}", flush=True)

    return {"ok": ok, "fail": fail, "subject": subject, "body": body}
