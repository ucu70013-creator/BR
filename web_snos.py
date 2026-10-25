import random
import asyncio
import aiohttp
import os
import string
import aiofiles
from utils import now_msk, esc_md

codes = ["495", "499", "812", "900", "901", "902", "903", "904", "905", "906", "908", "909", "910", "911", "912", "913", "914", "915", "916", "917", "918", "919", "920", "921", "922", "923", "924", "925", "926", "927", "928", "929", "930", "931", "932", "933", "934", "936", "937", "938", "939", "941", "950", "951", "952", "953", "954", "955", "958", "960", "961"]
names = ["ilya", "dima", "ivan", "alexey", "sergey", "mikhail", "andrey", "pavel", "nikolay", "vladimir", "anatoly", "boris", "egor", "danil", "viktor", "yuri", "maksim", "grigory", "oleg", "timofey", "arseniy", "roman", "konstantin", "gennady", "artem", "vadim", "vitaly", "nikita", "stanislav", "alexander", "vasily", "leonid", "valery", "eduard", "denis", "kirill", "fedor", "petya", "yegor", "german", "stepan", "platon", "bogdan", "ignat", "arkady", "yaroslav", "matvey", "rostan", "vsevolod", "semyon", "anton", "zahar", "timur", "roksana", "daniil", "afanasiy", "innokentiy", "rodion", "valentin", "nikifor", "petr", "filipp", "martin", "adrian", "georgy", "vladislav", "arseny", "artur", "mark", "prokhor", "lavrenty", "anastasiya", "olga", "anna", "ekaterina", "maria", "tatiana", "sofia", "elena", "natalia", "svetlana", "valentina", "lyubov", "galina", "lidiya", "nina", "darya", "alisa", "veronika", "irina", "arina", "kristina", "oksana", "polina", "viktoriya", "karina", "milana", "zinaida", "angelina", "yulia", "zoya", "ksenia"]
last_names = ["ivanov", "petrov", "sidorov", "smirnov", "kozlov", "popov", "vasilyev", "novikov", "morozov", "solovyov", "pavlov", "semenov", "golubev", "vinogradov", "bogdanov", "vorobyev", "fedorov", "mikhailov", "tarasov", "belov", "komarov", "oronov", "nikolaev", "makarov", "zaitsev", "sokolov", "mironov", "romanov", "levin", "kulikov", "kuznetsov", "stepanov", "nikitin", "oronin", "safonov", "shestakov", "kravtsov", "gusev", "arkhipov", "andreev", "yakovlev", "borisov", "zhukov", "prokhorov", "savelyev", "dorokhov", "zakharyin", "melnikov", "shapovalov", "egorov", "berezin"]
years = [str(year) for year in range(1960, 2006)]
domains = ["gmail.com", "yahoo.com", "outlook.com", "mail.ru", "yandex.ru", "rambler.ru", "bk.ru", "list.ru", "inbox.ru", "protonmail.com", "icloud.com", "hotmail.com", "aol.com", "zoho.com", "gmx.com", "qq.com", "126.com", "163.com", "sina.com", "comcast.net", "verizon.net", "live.com", "msn.com", "me.com", "mail.com", "fastmail.com", "rediffmail.com", "tutanota.com", "ukr.net", "web.de"]

def generatenumber():
    code = random.choice(codes)
    number = str(random.randint(1000000, 9999999))
    return "+7" + code + number

def generatemail():
    name = random.choice(names)
    last_name = random.choice(last_names)
    year = random.choice(years)
    domain = random.choice(domains)
    return f"{name}.{last_name}.{year}@{esc_md(domain)}"

LOGS_DIR = "logs"

def generate_log_filename():
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
    return os.path.join(LOGS_DIR, f"brown_v2_web_log_{rand}.txt")

# Семафор для ограничения параллельных запросов
_SEMAPHORE = None

def _get_semaphore():
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(100)
    return _SEMAPHORE

async def _send_one(session, i, message_text, subject, log_file):
    """Отправляет одну жалобу, возвращает (success: bool, log_line: str)."""
    url = "https://telegram.org/support?setln=ru"
    payload = {
        "subject": subject,
        "message": message_text,
        "email": generatemail(),
        "phone": generatenumber()
    }
    timestamp = now_msk().strftime("[%Y-%m-%d %H:%M:%S]")
    try:
        async with _get_semaphore():
            async with session.post(url, data=payload, ssl=False) as response:
                if response.status == 200:
                    line = f"{timestamp} Жалоба #{i} — ДОШЛА ✅\n"
                    print(f"[WEB] #{i} ✅ ДОШЛА (200)", flush=True)
                    return True, line
                else:
                    line = f"{timestamp} Жалоба #{i} — НЕ ДОШЛА ❌ (статус: {response.status})\n"
                    print(f"[WEB] #{i} ❌ НЕ ДОШЛА (статус: {response.status})", flush=True)
                    return False, line
    except aiohttp.ClientError as e:
        line = f"{timestamp} Жалоба #{i} — ОШИБКА ❌ ({type(e).__name__}: {e})\n"
        print(f"[WEB] #{i} ❌ ОШИБКА ({type(e).__name__}: {str(e)[:60]})", flush=True)
        return False, line
    except Exception as e:
        line = f"{timestamp} Жалоба #{i} — НЕОЖИДАННАЯ ОШИБКА ❌ ({type(e).__name__}: {e})\n"
        print(f"[WEB] #{i} ❌ НЕОЖИДАННАЯ ОШИБКА ({type(e).__name__}: {str(e)[:60]})", flush=True)
        return False, line


async def web(session, message_text, count, log_path=None, user_id=None, username=None):
    subject = "Complaint About Fraudulent Telegram Group"
    success, error = 0, 0

    print(f"\n{'='*50}", flush=True)
    print(f"[WEB] 🚀 Запуск веб-жалоб", flush=True)
    print(f"[WEB] 👤 Пользователь: {user_id} (*@{username}*)", flush=True)
    print(f"[WEB] 📝 Текст: {message_text[:80]}{'...' if len(message_text) > 80 else ''}", flush=True)
    print(f"[WEB] 📊 Количество жалоб: {count}", flush=True)
    print(f"{'='*50}", flush=True)

    if log_path:
        os.makedirs(LOGS_DIR, exist_ok=True)

    # Запускаем все запросы параллельно
    tasks = [_send_one(session, i, message_text, subject, None) for i in range(1, count + 1)]
    results = await asyncio.gather(*tasks)

    log_lines = []
    for ok, line in results:
        if ok:
            success += 1
        else:
            error += 1
        log_lines.append(line)

    print(f"\n[WEB] {'='*50}", flush=True)
    print(f"[WEB] 🏁 Итоги: ✅ {success} дошло, ❌ {error} не дошло", flush=True)
    print(f"[WEB] {'='*50}\n", flush=True)

    if log_path:
        header = (
            "Brown V2 log | web-method\n"
            "------------------------------------------\n"
            f"Пользователь: {user_id} (*@{username if username else 'без username'}*)\n"
            f"Текст: {message_text}\n"
            "------------------------------------------\n"
        )
        footer = (
            "------------------------------------------\n"
            f"Успешно: {success}\n"
            f"Неуспешно: {error}\n"
        )
        async with aiofiles.open(log_path, mode='w', encoding='utf-8') as f:
            await f.write(header)
            await f.writelines(log_lines)
            await f.write(footer)

    return success, error
