# -*- coding: utf-8 -*-
"""ابزارهای کمکی: متغیرها، دسترسی sudo، تشخیص دستور، ادمین، فایل موقت."""
import asyncio
import datetime
import os
import random
import re
import time
import zoneinfo

_var_re = re.compile(r"\b(TIME|HOUR|MIN|SEC|DAY|MONTH|YEAR|DATE|STRDAY|STRMONTH|NAME|USERNAME|ID)\b")
_rand_re = re.compile(r"RANDNUM(\d+)-(\d+)")

FA_DAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]
FA_MONTHS = ["", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def to_jalali(gd):
    """تبدیل تاریخ میلادی به شمسی (الگوریتم ساده)."""
    gy, gm, gd_ = gd.year, gd.month, gd.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) \
        + ((gy2 + 399) // 400) + gd_ + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def now(tzname):
    return datetime.datetime.now(zoneinfo.ZoneInfo(tzname))


def render_vars(text, tzname="Asia/Tehran", user=None):
    """جایگذاری متغیرها داخل متن‌ها: TIME, DATE, RANDNUM1-99, NAME و ..."""
    if not text:
        return text
    n = now(tzname)
    jy, jm, jd = to_jalali(n.date())

    text = _rand_re.sub(lambda m: str(random.randint(int(m.group(1)), int(m.group(2)))), text)

    def rep(m):
        t = m.group(1)
        if t == "TIME":
            return n.strftime("%H:%M")
        if t == "HOUR":
            return f"{n.hour:02d}"
        if t == "MIN":
            return f"{n.minute:02d}"
        if t == "SEC":
            return f"{n.second:02d}"
        if t == "DAY":
            return str(jd)
        if t == "MONTH":
            return str(jm)
        if t == "YEAR":
            return str(jy)
        if t == "DATE":
            return f"{jy}/{jm:02d}/{jd:02d}"
        if t == "STRDAY":
            return FA_DAYS[n.weekday()]
        if t == "STRMONTH":
            return FA_MONTHS[jm]
        if t == "NAME":
            full = ((user.first_name or "") + " " + (user.last_name or "")).strip() if user else ""
            return full or "دوست عزیز"
        if t == "USERNAME":
            return ("@" + user.username) if (user and user.username) else "دوست عزیز"
        if t == "ID":
            return str(user.id) if user else ""
        return m.group(0)

    return _var_re.sub(rep, text)


def match_cmd(text, alias, prefix):
    """اگر متن با دستور مطابقت داشت، آرگومان‌ها را برمی‌گرداند وگرنه None.
    دستورهای انگلیسی (ASCII) با پیشوند مثل !save و فارسی بدون پیشوند مثل ذخیره.
    مرز کلمه رعایت می‌شود: !onto دیگر با on تطبیق نمی‌کند."""
    import re as _re
    if not text:
        return None
    if alias.isascii():
        full = _re.escape((prefix + alias).lower())
        m = _re.match(rf"{full}(?:\s+|$)", text.lower())
        if m:
            return text[m.end():].strip()
        return None
    if text == alias:
        return ""
    if text.startswith(alias + " "):
        return text[len(alias) + 1:].strip()
    return None


async def get_user(client, event, args):
    """کاربر هدف: اول ریپلی، بعد متن دستور."""
    if event.is_reply:
        m = await event.get_reply_message()
        if m and m.sender_id:
            try:
                return await client.get_entity(m.sender_id)
            except Exception:
                pass
    a = (args or "").strip().split()
    if a:
        t = a[0].lstrip("@")
        try:
            return await client.get_entity(int(t) if t.lstrip("-").isdigit() else t)
        except Exception:
            return None
    return None


class AdminCache:
    """کش ادمین‌های هر گروه برای ۵ دقیقه."""

    def __init__(self):
        self._c = {}

    async def is_admin(self, client, chat_id, uid):
        key = str(chat_id)
        ts, ids = self._c.get(key, (0, set()))
        if time.time() - ts > 300:
            try:
                from telethon.tl.types import ChannelParticipantsAdmins
                ids = {p.id async for p in client.iter_participants(
                    chat_id, filter=ChannelParticipantsAdmins())}
            except Exception:
                ids = set()
            self._c[key] = (time.time(), ids)
        return uid in ids


def tmp_path(ext):
    d = os.path.join(os.getcwd(), "tmp_dl")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{int(time.time() * 1000)}_{random.randint(100, 999)}.{ext}")


def marked_id(ent):
    """آیدی marked قابل‌استفاده‌ی پایدار برای ذخیره در تنظیمات.

    id خام مثبت کانال‌ها بعد از ری‌استارت (کش خالی StringSession) resolve
    نمی‌شود؛ فرم marked (-100...) یا @username همیشه کار می‌کند."""
    un = getattr(ent, "username", None)
    if un:
        return "@" + un
    try:
        from telethon.tl import types as tl
        if isinstance(ent, tl.Channel):
            return f"-100{ent.id}"
        if isinstance(ent, tl.Chat):
            return f"-{ent.id}"
    except Exception:
        pass
    return str(getattr(ent, "id", ent))


def human_size(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def chunk_text(text, limit=4000):
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur += ("\n" if cur else "") + line
    if cur:
        out.append(cur)
    return out


# ---------- تایپ جادویی ----------
async def typing_then(ctx, chat, send):
    """قبل از ارسال خودکار، «در حال تایپ...» نشان بده تا طبیعی به نظر برسد.
    send = تابع بدون‌آرگومان که coroutine ارسال برمی‌گرداند.
    اگر «تایپ جادویی خاموش» باشد یا client.action در دسترس نباشد، مستقیم ارسال می‌شود."""
    try:
        on = ctx.acc["sec"].get("typing", True)
    except Exception:
        on = True
    if not on:
        return await send()
    try:
        async with ctx.client.action(chat, "typing"):
            await asyncio.sleep(1.1)
            return await send()
    except Exception:
        return await send()


def fmt_status(status, tzname="Asia/Tehran"):
    """آخرین بازدید کاربر به فارسی."""
    try:
        from telethon.tl import types as tl
        if isinstance(status, tl.UserStatusOnline):
            return "🟢 آنلاین"
        if isinstance(status, tl.UserStatusRecently):
            return "🟡 اخیراً آنلاین"
        if isinstance(status, tl.UserStatusOffline):
            d = datetime.datetime.now(datetime.timezone.utc) - status.was_at
            m = int(d.total_seconds() // 60)
            if m < 60:
                return f"🟠 {max(m, 1)} دقیقه پیش"
            if m < 1440:
                return f"🟠 {m // 60} ساعت پیش"
            return f"🔴 {m // 1440} روز پیش"
        if isinstance(status, tl.UserStatusLastWeek):
            return "🔴 این هفته"
        if isinstance(status, tl.UserStatusLastMonth):
            return "🔴 این ماه"
    except Exception:
        pass
    return "—"


def parse_shift(arg):
    """«9 تا 18» یا «9:30 تا 21:30» → (from_min, to_min)؛ None = خطا.
    شیفت شب (تا < از) هم مجاز است."""
    m = re.match(r"^\s*(\d{1,2})(?::(\d{1,2}))?\s*(?:تا|به|-|–|—|to)\s*(\d{1,2})(?::(\d{1,2}))?\s*$",
                 (arg or "").strip())
    if not m:
        return None
    h1, m1, h2, m2 = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
    if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
        return None
    return h1 * 60 + m1, h2 * 60 + m2


def in_shift(shift, tzname="Asia/Tehran"):
    """الان داخل شیفت کاری است؟"""
    if not shift:
        return True
    n = now(tzname)
    t = n.hour * 60 + n.minute
    f, to = shift["from"], shift["to"]
    if f <= to:
        return f <= t < to
    return t >= f or t < to  # شیفت شب (مثلاً 22 تا 6)
