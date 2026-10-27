# -*- coding: utf-8 -*-
"""ماژول ابزار: نرخ لحظه‌ای ارز/طلا/سکه/تتر (tgju) + آب و هوا (open-meteo).

همه درخواست‌ها با urllib (بدون وابستگی جدید) داخل thread اجرا می‌شوند تا
event loop بلاک نشود؛ نتیجه ۵ دقیقه کش می‌شود."""
import asyncio
import json
import urllib.parse
import urllib.request

from framework import Bot

TGJU_HOSTS = ["call1", "call3", "call4", "call5", "call2"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# کلیدهای tgju → (عنوان فارسی، آیکون)
RATE_KEYS = [
    ("price_dollar_rl", "دلار", "💵"),
    ("price_eur", "یورو", "💶"),
    ("geram18", "طلای ۱۸ عیار", "🥇"),
    ("geram24", "طلای ۲۴ عیار", "🪙"),
    ("sekee", "سکه امامی", "🟡"),
    ("nim", "نیم‌سکه", "🟠"),
    ("rob", "ربع‌سکه", "🟤"),
    ("crypto-tether-irr", "تتر", "🟢"),
]

# شهرهای پرتکرار ایران — بدون نیاز به API جست‌وجو
CITIES = {
    "تهران": (35.6944, 51.4215), "مشهد": (36.2972, 59.6067), "اصفهان": (32.6539, 51.6660),
    "شیراز": (29.6072, 52.5311), "تبریز": (38.0800, 46.2919),
    "کرج": (35.8400, 50.9391), "اهواز": (31.3183, 48.6706), "قم": (34.6416, 50.8746),
    "کرمانشاه": (34.3142, 47.0650), "ارومیه": (37.5527, 45.0759), "رشت": (37.2808, 49.5832),
    "زاهدان": (29.4963, 60.8629), "همدان": (34.7983, 48.5148), "کرمان": (30.2839, 57.0834),
    "یزد": (31.8974, 54.3569), "اردبیل": (38.2498, 48.2933), "بندرعباس": (27.1832, 56.2666),
    "اراک": (34.0917, 48.4630), "جیرفت": (28.6726, 57.7499), "قزوین": (36.4681, 50.0016),
    "سنندج": (35.3219, 46.9862), "خرم‌آباد": (33.4878, 48.3558), "گرگان": (36.8427, 54.4440),
    "نجف‌آباد": (32.6344, 51.3661), "ساری": (36.5633, 53.0601), "ملایر": (34.2979, 48.8217),
    "بوشهر": (28.9234, 50.8203), "زنجان": (36.6736, 48.4787), "بروجرد": (33.9766, 48.7488),
    "کاشان": (33.9850, 51.4100), "سمنان": (35.5768, 53.3921), "ایلام": (33.6374, 46.4227),
    "بیرجند": (32.8663, 59.2211), "شهرکرد": (32.3256, 50.8644), "سیرجان": (29.4526, 55.6822),
    "بم": (29.1060, 58.3570), "چابهار": (25.2919, 60.6430), "کیش": (26.5578, 54.0229),
    "قشم": (26.8101, 55.9000), "لار": (27.6683, 54.3767), "آبادان": (30.3392, 48.3043),
}

WMO = {
    0: "صاف ☀️", 1: "کمی ابری 🌤", 2: "نیمه ابری ⛅", 3: "ابری ☁️",
    45: "مه 🌫", 48: "مه یخ‌زده 🌫",
    51: "نم‌نم خفیف 🌦", 53: "نم‌نم 🌦", 55: "نم‌نم شدید 🌦",
    61: "باران خفیف 🌦", 63: "باران 🌧", 65: "باران شدید 🌧",
    66: "باران یخ‌زده 🌧", 67: "باران یخ‌زده شدید 🌧",
    71: "برف خفیف ❄️", 73: "برف ❄️", 75: "برف سنگین ❄️", 77: "دانه برف ❄️",
    80: "رگبار خفیف 🌦", 81: "رگبار 🌧", 82: "رگبار شدید ⛈",
    85: "رگبار برف 🌨", 86: "رگبار برف سنگین 🌨",
    95: "رعد و برق ⛈", 96: "رعد و برق با تگرگ ⛈", 99: "رعد و برق شدید ⛈",
}


def _fetch(url, timeout=9):
    r = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_tgju():
    last = None
    for h in TGJU_HOSTS:
        try:
            return _fetch(f"https://{h}.tgju.org/ajax.json")["current"]
        except Exception as e:
            last = e
            continue
    raise last or RuntimeError("no host")


def _toman(v):
    """مقدار ریاِل tgju → تومان خوانا."""
    try:
        n = float(str(v).replace(",", "").strip())
    except Exception:
        return None
    t = n / 10.0
    return f"{t:,.0f}" if t >= 100 else f"{t:,.1f}"


def _rate_line(cur, key, title, icon):
    item = cur.get(key)
    if not item:
        return None
    p = _toman(item.get("p"))
    if not p:
        return None
    dp = str(item.get("dp") or "0").strip()
    arrow = "⬆️" if (item.get("dt") == "high") else ("⬇️" if (item.get("dt") == "low") else "🔹")
    return f"{icon} {title}: {p} تومان ({arrow} {dp}%)"


def rates_text():
    """متن کامل نرخ‌ها؛ خطا = exception."""
    cur = _fetch_tgju()
    lines = ["📊 <b>نرخ لحظه‌ای بازار</b>"]
    for key, title, icon in RATE_KEYS:
        ln = _rate_line(cur, key, title, icon)
        if ln:
            lines.append(ln)
    lines.append("—")
    lines.append("💵 دلار حواله: " + (_toman(cur["price_dollar_dt"]["p"]) + " تومان"
                                       if cur.get("price_dollar_dt") else "—"))
    return "\n".join(lines)


def weather_text(city, lat, lon):
    d = _fetch(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&current_weather=true&daily=temperature_2m_max,temperature_2m_min,"
               f"precipitation_probability_max&timezone=auto&forecast_days=2")
    cw = d["current_weather"]
    desc = WMO.get(cw["weathercode"], "—")
    daily = d["daily"]
    t0, t1 = daily["time"][0], daily["time"][1]
    def day(i):
        p = daily["precipitation_probability_max"][i]
        return (f"{'امروز' if i == 0 else 'فردا'}: {daily['temperature_2m_min'][i]} تا "
                f"{daily['temperature_2m_max'][i]}° — بارش {p if p is not None else '?'}%")
    ws = cw.get("windspeed")
    return (f"🌤 <b>{city}</b>\n"
            f"الان: {cw['temperature']}° ({desc})"
            + (f" | باد {ws} km/h" if ws is not None else "")
            + f"\n{day(0)}\n{day(1)}")


def setup(bot: Bot):
    cache = {"ts": 0, "text": None}  # کش ۵ دقیقه‌ای نرخ‌ها

    async def _get_rates():
        import time as t
        if cache["text"] and t.time() - cache["ts"] < 300:
            return cache["text"]
        text = await asyncio.to_thread(rates_text)
        cache["text"], cache["ts"] = text, t.time()
        return text

    async def _show(event, ctx):
        try:
            text = await _get_rates()
        except Exception:
            return await ctx.reply(event, "❌ گرفتن قیمت‌ها ممکن نشد — چند لحظه بعد دوباره بزن")
        await ctx.reply(event, text, parse_mode="html")

    @bot.cmd("ارز", "rates", cat="ابزار",
             help="ارز — نرخ لحظه‌ای دلار/یورو/طلا/سکه/تتر (دستورهای تکی هم کار می‌کنند: دلار)")
    async def _rates(event, ctx, args):
        await _show(event, ctx)

    for _key, _fa, _icon, _en in [("دلار", "دلار", "💵", "usd"), ("یورو", "یورو", "💶", "eur"),
                                  ("طلا", "طلا", "🥇", "gold"), ("سکه", "سکه", "🟡", "coin"),
                                  ("تتر", "تتر", "🟢", "tether")]:
        async def _one(event, ctx, args, _fa=_fa):
            try:
                text = await _get_rates()
            except Exception:
                return await ctx.reply(event, "❌ گرفتن قیمت‌ها ممکن نشد — بعداً دوباره بزن")
            want = {"دلار": ["💵"], "یورو": ["💶"], "طلا": ["🥇", "🪙"],
                    "سکه": ["🟡", "🟠", "🟤"], "تتر": ["🟢"]}[_fa]
            pick = [ln for ln in text.split("\n") if any(w in ln for w in want)]
            await ctx.reply(event, "\n".join(pick) if pick else text, parse_mode="html")
        bot.cmd(_key, _en, cat="ابزار",
                help=f"{_key} — نرخ لحظه‌ای {_fa}")(_one)

    # ---------- آب و هوا ----------
    def _norm(t):
        return (t or "").replace(" ", "").replace("\u200c", "")

    async def _city(text):
        """نام شهر → (نام، lat, lon)؛ اول دیکشنری داخلی، بعد open-meteo."""
        t = _norm(text)
        if not t:
            return None
        for name, (lat, lon) in CITIES.items():
            if t == _norm(name) or _norm(name) in t:
                return name, lat, lon
        try:
            q = urllib.parse.quote(t)
            d = await asyncio.to_thread(
                _fetch, f"https://geocoding-api.open-meteo.com/v1/search?name={q}"
                        f"&count=1&language=fa&format=json")
            r = (d.get("results") or [None])[0]
            if r:
                return r["name"], r["latitude"], r["longitude"]
        except Exception:
            pass
        return None

    async def _weather(event, ctx, args):
        c = await _city(args)
        if not c:
            return await ctx.reply(event, "❗ اسم شهر را بنویس: اب و هوا تهران")
        name, lat, lon = c
        try:
            text = await asyncio.to_thread(weather_text, name, lat, lon)
        except Exception:
            return await ctx.reply(event, "❌ سرویس آب و هوا جواب نداد — بعداً دوباره بزن")
        await ctx.reply(event, text, parse_mode="html")

    bot.cmd("اب و هوا", "weather", cat="ابزار",
            help="اب و هوا <شهر> — وضعیت و دمای امروز/فردا")(_weather)
    bot.cmd("آب و هوا", "weatherfa", cat="ابزار",
            help="آب و هوا <شهر> — همان اب و هوا")(_weather)
    bot.cmd("هوا", "weather2", cat="ابزار",
            help="هوا <شهر> — خلاصه آب و هوا")(_weather)
