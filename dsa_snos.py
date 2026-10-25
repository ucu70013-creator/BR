# coding: utf-8
"""
Brown V2 | dsa_snos.py
DSA Report метод — жалобы через telegram.org/dsa-report
Капча: Cloudflare Turnstile через CapMonster Cloud API
Браузер: Playwright headless (Chromium)
ИИ текст: Groq API
"""

import asyncio
import random
import os
import logging
import aiohttp
from playwright.async_api import async_playwright, Page

import config
from config import bot_logs
import keyboards
from utils import now_msk, ProgressBar, esc_md

logger = logging.getLogger(__name__)

# ─── Конфиг ──────────────────────────────────────────────────────────────────
CAPMONSTER_KEY = os.environ.get("CAPMONSTER_KEY", config.CAPMONSTER_KEY)
GROQ_KEY = os.environ.get("GROQ_KEY", config.GROQ_KEY)
TURNSTILE_SITEKEY = "0x4AAAAAABCHiDxTcTJ4azUp"
TARGET_URL = "https://telegram.org/dsa-report"
DSA_DIR = os.path.join(os.path.dirname(__file__), "dsa_data")

bot = None
main_bot = None

# ─── Маппинг причин ──────────────────────────────────────────────────────────
# callback_data -> (label, radio_text_on_site, sub_radio_text_or_None)
DSA_REASONS = {
    # Без подкатегорий
    "child_abuse":   ("👶 Child abuse",          "Child abuse",       None),
    "violence":      ("💥 Violence",             "Violence",          None),
    "terrorism":     ("💣 Terrorism",            "Terrorism",         None),
    "other":         ("📝 Other",                "Other",             None),
    # С подкатегориями
    "illegal_goods": ("🔫 Illegal goods",        "Illegal goods",     None),
    "illegal_adult": ("🔞 Illegal adult content","Illegal adult content", None),
    "personal_data": ("🔐 Personal data",        "Personal data",     None),
    "scam":          ("📢 Scam or spam",         "Scam or spam",      None),
}

DSA_SUB_REASONS = {
    # Illegal goods
    "weapons":         ("Illegal goods", "Weapons"),
    "drugs":           ("Illegal goods", "Drugs"),
    "fake_docs":       ("Illegal goods", "Fake documents"),
    "counterfeit":     ("Illegal goods", "Counterfeit money"),
    "other_goods":     ("Illegal goods", "Other goods"),
    # Illegal adult content
    "child_abuse_adult": ("Illegal adult content", "Child abuse"),
    "nonconsensual":   ("Illegal adult content", "Distribution of non-consensual sexual imagery"),
    "other_sexual":    ("Illegal adult content", "Other illegal sexual content"),
    # Personal data
    "private_images":  ("Personal data", "Private images"),
    "phone":           ("Personal data", "Phone number"),
    "address":         ("Personal data", "Address"),
    "other_personal":  ("Personal data", "Other personal information"),
    # Scam
    "phishing":        ("Scam or spam", "Phishing"),
    "impersonation":   ("Scam or spam", "Impersonation"),
    "fraud_sales":     ("Scam or spam", "Fraudulent sales"),
}

# Причины с подкатегориями
HAS_SUBCATEGORY = {"illegal_goods", "illegal_adult", "personal_data", "scam"}

def set_bot_dsa(b):
    global bot, main_bot
    bot = b
    if main_bot is None:
        main_bot = b


def _get_random_line(filename: str) -> str:
    path = os.path.join(DSA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        return random.choice(lines) if lines else ""
    except FileNotFoundError:
        logger.warning(f"[DSA] файл не найден: {path}")
        return ""


# ─── Groq — генерация текста жалобы ─────────────────────────────────────────
async def generate_complaint_text(reason: str, sub_reason: str, message_text: str = "") -> str:
    """Генерирует текст жалобы через Groq API."""
    system_prompt = (
        "You are a DSA complaint text generator for Telegram's official reporting system. "
        "Generate a complaint in English. "
        "CRITICAL: response must be UNDER 200 characters. No exceptions. "
        "Be direct and concise. No intro phrases. "
        "Do NOT mention @usernames or Telegram handles. "
        "Output ONLY the complaint text."
    )

    user_content = f"Report reason: {reason}"
    if sub_reason:
        user_content += f"\nSub-reason: {sub_reason}"
    if message_text:
        user_content += f"\nMessage content: {message_text[:300]}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "max_tokens": 50,
                    "temperature": 0.6,
                    "reasoning_effort": "none",
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json(content_type=None)
                if "choices" not in data:
                    logger.error(f"[DSA] Groq unexpected response: {data}")
                    return _get_random_line("reptexts.txt")
                text = data["choices"][0]["message"]["content"].strip()
                # Убираем <think>...</think> блок если есть (chain-of-thought модели)
                import re
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
                return text[:250]
    except Exception as e:
        logger.error(f"[DSA] Groq error: {e}")
        return _get_random_line("reptexts.txt")


# ─── Telethon — получение текста сообщения ───────────────────────────────────
async def fetch_message_text(link: str) -> str:
    """Получает текст сообщения по ссылке через Telethon."""
    try:
        from telethon import TelegramClient
        import os as _os
        # Парсим ссылку
        clean = link.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
        parts = clean.rstrip("/").split("/")
        if len(parts) < 2:
            return ""
        username = parts[0]
        msg_id = int(parts[-1])

        # Берём первую доступную сессию из sessions/
        session_folder = "sessions"
        sessions = [f.replace(".session", "") for f in _os.listdir(session_folder)
                    if f.endswith(".session")] if _os.path.exists(session_folder) else []
        if not sessions:
            logger.warning("[DSA] нет сессий для fetch_message_text")
            return ""

        session_path = _os.path.join(session_folder, random.choice(sessions))
        creds = random.choice([
            ("24565698", "5a084b434f8505ace703485b9da85040"),
            ("27904162", "e7cba879b1c643ba77490bf328df5eab"),
        ])
        client = TelegramClient(session_path, int(creds[0]), creds[1],
                                system_version="4.16.30-vxCUSTOM")
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            logger.warning("[DSA] сессия не авторизована для fetch")
            return ""
        msg = await client.get_messages(username, ids=msg_id)
        text = ""
        if msg:
            text = msg.text or msg.caption or ""
        await client.disconnect()
        logger.info(f"[DSA] получен текст сообщения: {text[:80]}")
        return text[:500]
    except Exception as e:
        logger.warning(f"[DSA] fetch_message_text error: {e}")
        return ""


# ─── CapMonster — решение Turnstile ──────────────────────────────────────────
async def _solve_turnstile(page_url: str) -> str | None:
    async with aiohttp.ClientSession() as session:
        payload = {
            "clientKey": CAPMONSTER_KEY,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": TURNSTILE_SITEKEY,
            }
        }
        try:
            async with session.post(
                "https://api.capmonster.cloud/createTask",
                json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    text = await resp.text()
                    logger.error(f"[DSA] CapMonster bad response: {text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"[DSA] CapMonster createTask error: {e}")
            return None

        if data.get("errorId") != 0:
            logger.error(f"[DSA] CapMonster error: {data.get('errorDescription')}")
            return None

        task_id = data.get("taskId")
        logger.info(f"[DSA] CapMonster taskId={task_id}")

        for _ in range(60):
            await asyncio.sleep(3)
            try:
                async with session.post(
                    "https://api.capmonster.cloud/getTaskResult",
                    json={"clientKey": CAPMONSTER_KEY, "taskId": task_id},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    result = await resp.json(content_type=None)
            except Exception as e:
                logger.warning(f"[DSA] CapMonster getTaskResult error: {e}")
                continue

            if result.get("status") == "ready":
                return result.get("solution", {}).get("token")
            elif result.get("errorId") != 0:
                logger.error(f"[DSA] CapMonster task error: {result.get('errorDescription')}")
                return None

    logger.error("[DSA] CapMonster timeout")
    return None


# ─── Playwright форма ─────────────────────────────────────────────────────────
async def _wait_element(page: Page, selector: str, timeout: float = 30.0) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=timeout * 1000)
        return True
    except Exception:
        return False


def _xpath_text(text: str) -> str:
    if "'" not in text:
        return f"//*[text()='{text}']"
    parts = text.split("'")
    concat_args = ", \"'\", ".join(f"'{p}'" for p in parts)
    return f"//*[text()=concat({concat_args})]"


async def _click_radio(page: Page, text: str, timeout: int = 15000) -> bool:
    xpath = _xpath_text(text)
    try:
        await page.wait_for_selector(xpath, timeout=timeout)
    except Exception:
        logger.warning(f"[DSA] radio '{text}' не появился")
        return False
    for sel in [f"span.radio-label >> text={text}", f"label.radio-item >> text={text}", xpath]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click(force=True)
                return True
        except Exception:
            continue
    return False


async def _type_text(page: Page, text: str):
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(30, 80))


async def _fill_input_and_send(page: Page, text: str) -> bool:
    if not await _wait_element(page, ".cd-comment-input", timeout=30):
        return False
    await asyncio.sleep(random.uniform(0.3, 0.6))
    await page.locator(".cd-comment-input").first.click()
    await asyncio.sleep(0.1)
    await _type_text(page, text)
    await asyncio.sleep(random.uniform(0.2, 0.4))
    await page.locator(".cd-submit-comment-btn").first.click()
    return True


# ─── Основной флоу репорта ────────────────────────────────────────────────────
async def _run_single_report(target_link: str, reason_radio: str, sub_reason_radio: str,
                              complaint_text: str) -> bool:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-infobars", "--window-size=1920,1080"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)
        page = await context.new_page()

        try:
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            token = await _solve_turnstile(TARGET_URL)
            if not token:
                print("[DSA] не получили токен капчи", flush=True)
                return False
            print(f"[DSA] токен получен: {token[:20]}...", flush=True)

            await page.evaluate(f"""
                (token) => {{
                    const inputs = document.querySelectorAll('input[name="cf-turnstile-response"], input[id*="cf-chl-widget"]');
                    inputs.forEach(el => {{ el.value = token; }});
                    if (window.onTurnstileSuccess) window.onTurnstileSuccess(token);
                    if (window.turnstileCallback) window.turnstileCallback(token);
                    const btn = document.querySelector('.js-report-start-btn');
                    if (btn) {{ btn.removeAttribute('disabled'); btn.classList.remove('disabled'); }}
                }}
            """, token)
            await asyncio.sleep(1)

            # Закрываем алерт-попап если он перекрывает кнопку
            try:
                await page.evaluate("""
                    () => {
                        const popup = document.querySelector('.popup-container.alert-popup-container, .aj_popup');
                        if (popup) popup.remove();
                        document.querySelectorAll('.popup-overlay, .modal-overlay').forEach(el => el.remove());
                    }
                """)
                await asyncio.sleep(0.5)
            except Exception:
                pass

            btn = await page.query_selector(".js-report-start-btn")
            if btn:
                try:
                    async with page.expect_popup(timeout=8000) as popup_info:
                        await btn.click(force=True)
                    oauth_page = await popup_info.value
                    await oauth_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    await asyncio.sleep(1)
                    for sel in ["a[href*='unauth=1']", ".login_footer_text a",
                                "a:has-text('without logging in')"]:
                        try:
                            el = await oauth_page.wait_for_selector(sel, timeout=3000, state="visible")
                            if el:
                                await el.click()
                                await asyncio.sleep(2)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"[DSA] popup: {e}")
                    await btn.click(force=True)
                    await asyncio.sleep(2)

            if not await _wait_element(page, ".cd-comment-input", timeout=40):
                # Проверяем все открытые страницы — форма может быть в другой вкладке
                pages = page.context.pages
                print(f"[DSA] форма не на основной странице, проверяем {len(pages)} страниц", flush=True)
                for p in pages:
                    print(f"[DSA] проверяем: {p.url}", flush=True)
                    if await _wait_element(p, ".cd-comment-input", timeout=5):
                        page = p
                        print(f"[DSA] форма найдена на: {p.url}", flush=True)
                        break
                else:
                    try:
                        await pages[-1].screenshot(path="/tmp/dsa_debug.png")
                    except Exception:
                        pass
                    print("[DSA] форма не найдена ни на одной странице", flush=True)
                    return False
            print("[DSA] форма загрузилась, начинаем заполнение", flush=True)

            # Шаг 1: ссылка
            await _fill_input_and_send(page, target_link)
            await asyncio.sleep(1)

            # Шаг 2: причина
            await _click_radio(page, reason_radio)
            await asyncio.sleep(0.8)

            # Шаг 2b: подкатегория (если есть)
            if sub_reason_radio:
                await _click_radio(page, sub_reason_radio)
                await asyncio.sleep(0.8)

            # Шаг 3: текст жалобы
            await _fill_input_and_send(page, complaint_text)
            await asyncio.sleep(1)

            # Шаг 4: ссылка повторно
            await _fill_input_and_send(page, target_link)
            await asyncio.sleep(1)

            # Шаг 5: страна
            await _wait_element(page, ".radio-item, span.radio-label", timeout=15)
            await _click_radio(page, "Germany")
            await asyncio.sleep(0.8)
            await _click_radio(page, "Proceed without documentation")
            await asyncio.sleep(0.8)
            await _click_radio(page, "My own behalf")
            await asyncio.sleep(0.8)

            # Шаг 6: имя
            name = _get_random_line("names.txt")
            famili = _get_random_line("familis.txt")
            fullname = f"{name} {famili}"
            await _fill_input_and_send(page, fullname)
            await asyncio.sleep(0.8)

            # Шаг 7: адрес, email, телефон
            await _fill_input_and_send(page, _get_random_line("adreses.txt"))
            await asyncio.sleep(0.8)
            await _fill_input_and_send(page, _get_random_line("emails.txt"))
            await asyncio.sleep(0.8)
            await _fill_input_and_send(page, _get_random_line("numbers.txt"))
            await asyncio.sleep(0.8)

            # Шаг 8: финал
            await _click_radio(page, "I don't have a court order")
            await asyncio.sleep(0.8)
            await _click_radio(page, "Confirm")
            await asyncio.sleep(0.8)
            await _fill_input_and_send(page, fullname)
            await asyncio.sleep(2)

            logger.info("[DSA] ✅ репорт завершён успешно")
            return True

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[DSA] ошибка в репорте: {e}", flush=True)
            print(f"[DSA] traceback: {tb}", flush=True)
            logger.error(f"[DSA] ошибка: {e}")
            try:
                err_short = str(e)[:300]
                if main_bot:
                    await main_bot.send_message(
                        bot_logs,
                        f"🇪🇺 *DSA ERROR*\n`{err_short}`",
                        parse_mode="Markdown"
                    )
            except Exception:
                pass
            return False
        finally:
            await browser.close()


# ─── Главная функция ──────────────────────────────────────────────────────────
async def main_dsa_snos(target_link: str, user: int, username: str,
                         reason_key: str, sub_key: str, complaint_text: str,
                         count: int = 1, _bot=None, silent: bool = False):
    _send_bot = _bot or bot

    target = target_link.strip()
    if not target.startswith("https://"):
        target = "https://" + target.lstrip("@").replace("t.me/", "https://t.me/", 1)

    # Получаем тексты радио из маппинга
    reason_radio = DSA_REASONS.get(reason_key, ("", "Personal data", None))[1]
    sub_reason_radio = DSA_SUB_REASONS.get(sub_key, (None, None))[1] if sub_key else None

    # Метка для логов
    reason_label = DSA_REASONS.get(reason_key, ("DSA", "", None))[0]
    sub_label = DSA_SUB_REASONS.get(sub_key, ("", sub_key))[1] if sub_key else ""

    logger.info(f"[DSA] запуск | цель: {target} | причина: {reason_label} | текст: {complaint_text[:50]}")

    successful = 0
    failed = 0

    pb = ProgressBar(_send_bot, user, total=count, title="🇪🇺 *DSA Report*", silent=silent)
    await pb.start()
    for i in range(count):
        result = await _run_single_report(target, reason_radio, sub_reason_radio, complaint_text)
        if result:
            successful += 1
        else:
            failed += 1
        await pb.update(i + 1)
        if i + 1 < count:
            await asyncio.sleep(random.uniform(3, 6))
    await pb.finish()

    now_str = now_msk().strftime("%d.%m.%Y %H:%M:%S")
    target_escaped = target.replace('_', '\\_')
    reason_escaped = reason_label.replace('_', '\\_')

    caption_user = (
        f"🇪🇺 *DSA Report завершён!*\n\n"
        f"🎯 *Цель:* {target_escaped}\n"
        f"📋 *Причина:* {reason_escaped}\n"
        f"🕐 *Время:* {now_str}\n\n"
        f"🟢 *Успешно: {successful}*\n"
        f"🔴 *Не удалось: {failed}*"
    )
    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user)
        _log_uid = "скрыт" if _is_hid else str(user)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user), username

    caption_log = (
        f"🇪🇺 *DSA Report*\n\n"
        f"🎯 *Цель:* {target_escaped}\n"
        f"📋 *Причина:* {reason_escaped}"
        + (f" → {sub_label}" if sub_label else "") + "\n"
        f"👤 *Пользователь:* {_log_uid} (*@{_log_uname}*)\n"
        f"🕐 *Время:* {now_str}\n\n"
        f"🟢 *Успешно: {successful}*\n"
        f"🔴 *Не удалось: {failed}*"
    )

    if not silent:
        try:
            await _send_bot.send_message(user, caption_user, parse_mode="Markdown",
                                         reply_markup=keyboards.main_menu)
            try:
                from main import bot as _main_bot
                await _main_bot.send_message(bot_logs, caption_log, parse_mode="Markdown")
            except Exception:
                if main_bot:
                    await main_bot.send_message(bot_logs, caption_log, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[DSA] ошибка отправки результата: {e}")

    return (successful, count)
