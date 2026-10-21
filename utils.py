# -*- coding: utf-8 -*-
"""ابزارهای کمکی: متغیرها، دسترسی sudo، تشخیص دستور، ادمین، فایل موقت."""
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
    دستورهای انگلیسی (ASCII) با پیشوند مثل !save و فارسی بدون پیشوند مثل ذخیره."""
    if not text:
        return None
    if alias.isascii():
        full = prefix + alias
        if text.lower().startswith(full.lower()):
            return text[len(full):].strip()
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
