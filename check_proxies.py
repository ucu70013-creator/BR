"""
Проверка прокси — HTTP / SOCKS4 / SOCKS5
Читает proxy_input.txt (ip:port без префикса),
пробует каждый прокси через все три протокола,
сохраняет живые в proxies.txt с нужным префиксом.
"""

import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType

TEST_URL = "http://httpbin.org/ip"
TIMEOUT = 2
CONCURRENCY = 200


def load_proxies(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        # убираем дубликаты и мусор
        seen = set()
        result = []
        for line in lines:
            # убираем префиксы если есть
            for pfx in ("http://", "socks4://", "socks5://"):
                if line.startswith(pfx):
                    line = line[len(pfx):]
            if ":" in line and line not in seen:
                seen.add(line)
                result.append(line)
        return result
    except FileNotFoundError:
        print(f"[!] Файл {path} не найден")
        return []


def proxy_url(raw: str, scheme: str) -> str:
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"{scheme}://{user}:{pwd}@{esc_md(host)}:{port}"
    return f"{scheme}://{raw}"


async def check_http(session: aiohttp.ClientSession, proxy: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            url = proxy_url(proxy, "http")
            async with session.get(
                TEST_URL,
                proxy=url,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                ssl=False
            ) as r:
                if r.status == 200:
                    return proxy, "http"
        except Exception:
            pass
    return proxy, None


async def check_socks(proxy: str, sem: asyncio.Semaphore, ptype: ProxyType, label: str):
    async with sem:
        try:
            parts = proxy.split(":")
            host, port = parts[0], int(parts[1])
            user = parts[2] if len(parts) >= 4 else None
            pwd  = parts[3] if len(parts) >= 4 else None
            connector = ProxyConnector(
                proxy_type=ptype,
                host=host, port=port,
                username=user, password=pwd,
                rdns=True
            )
            async with aiohttp.ClientSession(connector=connector) as s:
                async with s.get(
                    TEST_URL,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                    ssl=False
                ) as r:
                    if r.status == 200:
                        return proxy, label
        except Exception:
            pass
    return proxy, None


async def main():
    proxies = load_proxies("proxy_input.txt")
    if not proxies:
        print("Нет прокси для проверки. Создай proxy_input.txt с ip:port построчно.")
        return

    print(f"Загружено прокси: {len(proxies)}")
    print(f"Проверяем HTTP + SOCKS4 + SOCKS5 (таймаут {TIMEOUT}с, параллельно {CONCURRENCY})...\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    alive: list[str] = []

    # ── HTTP ──────────────────────────────────────────────────────────────────
    print("→ Проверяем HTTP...")
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_http(session, p, sem) for p in proxies]
        results = await asyncio.gather(*tasks)
    http_alive = [f"http://{p}" for p, t in results if t == "http"]
    print(f"  HTTP живых: {len(http_alive)}")
    alive.extend(http_alive)

    # ── SOCKS4 ────────────────────────────────────────────────────────────────
    print("→ Проверяем SOCKS4...")
    tasks = [check_socks(p, sem, ProxyType.SOCKS4, "socks4") for p in proxies]
    results = await asyncio.gather(*tasks)
    socks4_alive = [f"socks4://{p}" for p, t in results if t == "socks4"]
    print(f"  SOCKS4 живых: {len(socks4_alive)}")
    alive.extend(socks4_alive)

    # ── SOCKS5 ────────────────────────────────────────────────────────────────
    print("→ Проверяем SOCKS5...")
    tasks = [check_socks(p, sem, ProxyType.SOCKS5, "socks5") for p in proxies]
    results = await asyncio.gather(*tasks)
    socks5_alive = [f"socks5://{p}" for p, t in results if t == "socks5"]
    print(f"  SOCKS5 живых: {len(socks5_alive)}")
    alive.extend(socks5_alive)

    # ── Итог ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*45}")
    print(f"✅ Итого живых: {len(alive)} из {len(proxies)}")
    print(f"   HTTP:   {len(http_alive)}")
    print(f"   SOCKS4: {len(socks4_alive)}")
    print(f"   SOCKS5: {len(socks5_alive)}")
    print(f"{'='*45}")

    if alive:
        # убираем дубликаты (прокси может работать по нескольким протоколам)
        seen_hosts = set()
        unique = []
        for entry in alive:
            host = entry.split("://")[1]
            if host not in seen_hosts:
                seen_hosts.add(host)
                unique.append(entry)

        with open("proxies.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(unique))
        print(f"\n💾 Сохранено в proxies.txt — {len(unique)} уникальных прокси")

        print("\nЖивые:")
        for p in unique:
            print(f"  {p}")
    else:
        print("\n⚠️ Живых прокси не найдено.")


if __name__ == "__main__":
    asyncio.run(main())
