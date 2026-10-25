"""
Запусти на VPS: python3 set_system_mirror.py SavermodesBot
Помечает зеркало как системное — оно будет стартовать всегда первым.
"""
import asyncio
import sys
import db


async def main():
    if len(sys.argv) < 2:
        print("Использование: python3 set_system_mirror.py <bot_username>")
        return

    username = sys.argv[1].lstrip("@")
    await db.init_db()

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT token, bot_username, user_id FROM mirrors WHERE bot_username ILIKE $1",
            f"%{username}%"
        )
        if not row:
            print(f"❌ Зеркало @{username} не найдено в БД")
            return

        token = row["token"]
        bot_uname = row["bot_username"]
        await conn.execute(
            "UPDATE mirrors SET is_system = TRUE WHERE token = $1",
            token
        )
        print(f"✅ @{bot_uname} помечен как системное зеркало")
        print(f"   Token: {token[:20]}...")


asyncio.run(main())
