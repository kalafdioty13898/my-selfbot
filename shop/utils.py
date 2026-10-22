# -*- coding: utf-8 -*-
"""ابزارهای کوچک مشترک."""
import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")
FMT = "%Y-%m-%d %H:%M:%S"
FMT_SHORT = "%Y-%m-%d %H:%M"

# تبدیل ارقام فارسی/عربی به لاتین
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def now():
    return datetime.now(TEHRAN)


def fmt_tom(n) -> str:
    """هزارگازداری عدد برای نمایش."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def fmt_dt(s: str) -> str:
    """نمایش کوتاه تاریخ."""
    return (s or "").replace(":", " ")[:16] if False else (s or "")[:16]


def esc(s) -> str:
    return html.escape(str(s or ""))


def parse_int(v: str):
    """تبدیل رشته (با ارقام فارسی هم) به عدد صحیح؛ ناموفق = None."""
    v = (str(v or "")).strip().translate(DIGITS).replace(",", "")
    try:
        return int(v)
    except ValueError:
        return None


def parse_phone(v: str):
    """شماره تلفن معتبر با کد کشور (+...) یا None."""
    v = (str(v or "")).strip().translate(DIGITS).replace(" ", "").replace("-", "")
    if not v.startswith("+"):
        if v.startswith("00"):
            v = "+" + v[2:]
        elif v.startswith("98") and len(v) >= 11:
            v = "+" + v
        elif v.startswith("0") and len(v) == 11:
            v = "+98" + v[1:]
        elif v.startswith("9") and len(v) == 10:
            v = "+98" + v
        else:
            return None
    body = v[1:]
    if not body.isdigit() or not (8 <= len(body) <= 15):
        return None
    return v


def normalize_code(v: str):
    """استخراج کد ورود تلگرام از ورودی کاربر.

    این‌ها همه باید کار کنند: «52941»، «۵۲۹۴۱»، «۵ ۲ ۹ ۴ ۱»، «5 2 9 4 1»،
    «Login code: 52941» یا کل متن پیام تلگرام. ناموفق = None.
    """
    v = (str(v or "")).strip().translate(DIGITS)
    groups = re.findall(r"\d+", v)
    if not groups:
        return None
    if len(groups) == 1:
        return groups[0]
    # همه تک‌رقمی و حداقل ۴ تا → کد فاصله‌دار («5 2 9 4 1»)
    if len(groups) >= 4 and all(len(g) == 1 for g in groups):
        return "".join(groups)
    cand = [g for g in groups if 4 <= len(g) <= 7]
    return cand[-1] if cand else None


def naive_now():
    """الان به وقت تهران، بدون timezone (برای مقایسه با تاریخ‌های ذخیره‌شده)."""
    return datetime.strptime(now().strftime(FMT), FMT)


def parse_dt(s: str):
    """تبدیل رشته ذخیره‌شده به datetime بدون timezone؛ ناموفق = None."""
    try:
        return datetime.strptime(s, FMT)
    except (ValueError, TypeError):
        return None


def transfer_error(amount, balance, today_sum, min_t, max_t, daily_cap):
    """بررسی قوانین انتقال سکه؛ None یعنی مجاز، در غیر این صورت متن خطا."""
    if amount is None or amount <= 0:
        return "⚠️ لطفاً مقدار سکه را به صورت عددی ارسال کن."
    if amount < min_t:
        return f"⚠️ حداقل انتقال {min_t} سکه است."
    if amount > max_t:
        return f"⚠️ حداکثر انتقال {max_t} سکه است."
    if today_sum + amount > daily_cap:
        return f"⚠️ سقف انتقال ۲۴ ساعته {daily_cap} سکه است؛ امروز {today_sum} سکه انتقال داده‌ای."
    if amount > balance:
        return f"⚠️ موجودی کافی نیست؛ موجودی فعلی تو: {balance} سکه."
    return None


PLAN_LABELS = {
    "coin_1d": "سکه‌ای (۱ روزه)",
    "plan_2m": "۲ ماهه",
    "plan_4m": "۴ ماهه",
    "manual": "دستی (ادمین)",
    "free": "رایگان",
}
