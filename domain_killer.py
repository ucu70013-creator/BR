"""
Brown V2 | domain_killer.py
Domain Killer — abuse-жалобы регистратору домена через RDAP.
Шаги: парсинг домена → RDAP lookup → Groq генерирует текст → отправка с mails.txt
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

logger = logging.getLogger(__name__)

GROQ_KEY = os.environ.get("GROQ_KEY", config.GROQ_KEY)
MAILS_FILE = Path(__file__).parent / "mails.txt"

_BAR_LEN = 10

SMTP_CONFIGS = {
    "gmail.com":  ("smtp.gmail.com",  587),
    "rambler.ru": ("smtp.rambler.ru", 587),
    "mail.ru":    ("smtp.mail.ru",    587),
    "yandex.ru":  ("smtp.yandex.ru",  587),
    "ya.ru":      ("smtp.yandex.ru",  587),
}
SMTP_TIMEOUT = 20

DOMAIN_WHITELIST = {
    "br-v2.com",
    "www.br-v2.com",
}


def extract_domain(url: str) -> str:
    url = url.strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.split("/")[0].split("?")[0].split("#")[0]


def _get_smtp_cfg(email: str) -> tuple:
    domain = email.split("@")[-1].lower()
    return SMTP_CONFIGS.get(domain, ("smtp." + domain, 587))


def _load_senders() -> list:
    if not MAILS_FILE.exists():
        return []
    senders = []
    for line in MAILS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        email, _, pwd = line.partition(":")
        email = email.strip()
        pwd = pwd.strip()
        if email and pwd:
            senders.append((email, pwd))
    return senders


async def rdap_lookup(domain: str) -> dict:
    result = {"registrar": None, "abuse_emails": []}

    def _walk(entities: list):
        for entity in entities:
            roles = entity.get("roles", [])
            vcard = entity.get("vcardArray", [])
            if vcard and len(vcard) > 1:
                props = vcard[1]
                fn_val = next((p[3] for p in props if isinstance(p, list) and p[0] == "fn"), None)
                email_val = next((p[3] for p in props if isinstance(p, list) and p[0] == "email"), None)
                if "registrar" in roles and fn_val and not result["registrar"]:
                    result["registrar"] = fn_val
                if "abuse" in roles and email_val and email_val not in result["abuse_emails"]:
                    result["abuse_emails"].append(email_val)
            sub = entity.get("entities", [])
            if sub:
                _walk(sub)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://rdap.org/domain/{domain}",
                timeout=aiohttp.ClientTimeout(total=12),
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return result
                data = await resp.json(content_type=None)
        _walk(data.get("entities", []))
    except Exception as e:
        logger.warning(f"[DK] RDAP error for {domain}: {e}")

    return result


async def generate_complaint(domain: str, reason: str, registrar: str) -> str:
    system = (
        "You are an abuse complaint writer. Write a formal professional abuse complaint email body. "
        "English only. 150-250 words. "
        "Structure: identify the domain, describe the violation clearly, request immediate takedown. "
        "Professional legal tone. No markdown. Plain text only. Output ONLY the email body, no subject."
    )
    user_content = (
        f"Domain: {domain}\n"
        f"Registrar: {registrar or 'Unknown'}\n"
        f"Violation: {reason}\n\n"
        "Write a formal abuse complaint requesting takedown of this domain."
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 400,
                    "temperature": 0.7,
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json(content_type=None)
                if "choices" not in data:
                    logger.error(f"[DK] Groq error: {data}")
                    return ""
                text = data["choices"][0]["message"].get("content", "").strip()
                return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    except Exception as e:
        logger.error(f"[DK] Groq error: {e}")
        return ""


def _send_smtp(sender_email: str, sender_pass: str, recipient: str, subject: str, body: str) -> tuple:
    smtp_host, smtp_port = _get_smtp_cfg(sender_email)
    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        srv = smtplib.SMTP(smtp_host, smtp_port, timeout=SMTP_TIMEOUT)
        srv.ehlo()
        srv.starttls()
        srv.ehlo()
        srv.login(sender_email, sender_pass)
        srv.sendmail(sender_email, recipient, msg.as_string())
        srv.quit()
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "auth"
    except Exception as e:
        return False, str(e)[:60]


def _bar(sent: int, total: int) -> str:
    pct = int(sent / total * 100) if total else 0
    filled = round(_BAR_LEN * sent / total) if total else 0
    return f"[{'▓' * filled}{'▒' * (_BAR_LEN - filled)}] {pct}%"


class _DKProgress:
    def __init__(self, bot, chat_id: int):
        self._bot = bot
        self._chat_id = chat_id
        self._msg_id = None
        self._stages: list = []

    def _render(self, sent: int = 0, total: int = 1) -> str:
        lines = [f"🔪 *Domain Killer*\n\n{_bar(sent, total)}\n"]
        for icon, label in self._stages:
            lines.append(f"{icon} {label}")
        return "\n".join(lines)

    async def _edit(self, sent: int = 0, total: int = 1):
        try:
            await self._bot.edit_message_text(
                self._render(sent, total), self._chat_id, self._msg_id, parse_mode="Markdown"
            )
        except Exception:
            pass

    async def start(self):
        msg = await self._bot.send_message(
            self._chat_id, "🔪 *Domain Killer*\n\nЗапускаю...", parse_mode="Markdown"
        )
        self._msg_id = msg.message_id

    async def stage(self, label: str, icon: str = "⏳"):
        self._stages.append([icon, label])
        await self._edit()

    async def ok(self, label: str = None):
        if self._stages:
            self._stages[-1][0] = "✅"
            if label:
                self._stages[-1][1] = label
        await self._edit()

    async def fail(self, label: str = None):
        if self._stages:
            self._stages[-1][0] = "❌"
            if label:
                self._stages[-1][1] = label
        await self._edit()

    async def sending(self, sent: int, total: int):
        if self._stages:
            self._stages[-1][0] = "📤"
            self._stages[-1][1] = f"Этап 4 — {sent}/{total}"
        await self._edit(sent, total)

    async def done(self, sent: int, total: int):
        if self._stages:
            self._stages[-1][0] = "✅"
            self._stages[-1][1] = f"Этап 4 — отправлено {sent}/{total}"
        try:
            text = self._render(sent, total) + f"\n\n📊 Жалоб отправлено: *{sent}/{total}*"
            await self._bot.edit_message_text(text, self._chat_id, self._msg_id, parse_mode="Markdown")
        except Exception:
            pass


async def main_domain_killer(
    domain_input: str,
    reason: str,
    uid: int,
    username: str,
    notify_bot=None,
    log_bot=None,
    log_channel_id=None,
) -> dict:
    from main import bot as _main_bot
    _bot = notify_bot or _main_bot

    prog = _DKProgress(_bot, uid)
    await prog.start()

    # Этап 1 — парсинг домена
    domain = extract_domain(domain_input)
    if domain in DOMAIN_WHITELIST:
        await prog.stage(f"❌ Домен в белом списке")
        return {"ok": False, "domain": domain, "sent": 0, "total": 0}
    await prog.stage(f"Этап 1 — {domain}")
    await asyncio.sleep(0.3)
    await prog.ok()

    # Этап 2 — RDAP lookup
    await prog.stage("Этап 2")
    rdap = await rdap_lookup(domain)
    abuse_emails = rdap["abuse_emails"]
    registrar = rdap["registrar"] or "Unknown"

    if not abuse_emails:
        await prog.fail("Этап 2 — abuse email не найден")
        return {"ok": False, "domain": domain, "sent": 0, "total": 0}

    await prog.ok(f"Этап 2 — {abuse_emails[0]}")

    # Этап 3 — генерация текста через Groq
    await prog.stage("Этап 3")
    base_text = await generate_complaint(domain, reason, registrar)
    if not base_text:
        base_text = (
            f"Dear Abuse Team,\n\n"
            f"I am writing to report the domain {domain} for the following violation:\n{reason}\n\n"
            f"I kindly request immediate investigation and takedown of this domain.\n\nThank you."
        )
    await prog.ok("Этап 3")

    # Этап 4 — отправка
    from mail_snos import spin_text, spin_subject
    senders = _load_senders()
    if not senders:
        await prog.stage("❌ Этап 4 — mails.txt пустой")
        return {"ok": False, "domain": domain, "sent": 0, "total": 0}

    await prog.stage("Этап 4")
    target_email = abuse_emails[0]
    sent = 0
    total = len(senders)

    for email, pwd in senders:
        subj = spin_subject(f"Abuse Report: {domain}")
        body = spin_text(base_text)
        ok, err = await asyncio.get_event_loop().run_in_executor(
            None, _send_smtp, email, pwd, target_email, subj, body
        )
        if ok:
            sent += 1
        else:
            logger.warning(f"[DK] {email}→{target_email}: {err}")
        await prog.sending(sent, total)
        await asyncio.sleep(0.3)

    await prog.done(sent, total)

    # Лог в канал
    if log_bot and log_channel_id:
        try:
            try:
                import db as _db
                _hidden = await _db.get_is_hidden(uid)
            except Exception:
                _hidden = False
            if _hidden:
                sender_line = "👤 @скрыт"
            else:
                sender_line = f"👤 *@{username}* {uid}"
            await log_bot.send_message(
                log_channel_id,
                (
                    f"🔪 *Domain Killer*\n"
                    f"{sender_line}\n"
                    f"🌐 {domain}\n"
                    f"📧 Abuse: {target_email}\n"
                    f"🏢 Регистратор: {registrar}\n"
                    f"📨 Отправлено: {sent}/{total}\n"
                    f"🕐 {now_msk()}"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"[DK] log error: {e}")

    return {
        "ok": sent > 0,
        "domain": domain,
        "sent": sent,
        "total": total,
        "target": target_email,
        "registrar": registrar,
    }
