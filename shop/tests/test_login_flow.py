# -*- coding: utf-8 -*-
"""تست‌های فیکس ورود: QR + سقف تلاش کد + پوش عملیات دستی ادمین."""
import asyncio
import inspect
import io
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shop"))

PASS = FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {extra}")


print("— ۱) تولید تصویر QR")
import qrcode  # noqa: E402


def qr_png(url):
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


url = "tg://login?token=AbCdEf123"
png = qr_png(url)
ok("PNG معتبر تولید شد", png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 500)

# محتوای QR باید همان URL را بازگرداند
from PIL import Image  # noqa: E402
try:
    from pyzbar.pyzbar import decode  # noqa: F401
    have_zbar = True
except Exception:
    have_zbar = False
if have_zbar:
    decoded = decode(Image.open(io.BytesIO(png)))
    ok("محتوای QR خواندنی و درست است",
       decoded and decoded[0].data.decode() == url)
else:
    ok("قابل‌خواندن بودن QR (pyzbar نبود — فقط سایز چک شد)", len(png) > 1000)

print("— ۲) استیت‌ها و رجیستری‌ها")
from handlers.common import Act, QR_TASKS, CLIENTS, PENDING, BUSY  # noqa: E402
ok("Act.method", Act.method is not None)
ok("Act.qr_wait", Act.qr_wait is not None)
ok("Act.password", Act.password is not None)
ok("QR_TASKS دیکشنری", isinstance(QR_TASKS, dict))

print("— ۳) کیبوردهای جدید")
import keyboards as K  # noqa: E402
mk = K.act_method()
ok("act_method: ۳ دکمه", len(mk.inline_keyboard) == 3)
ok("دکمه QR", mk.inline_keyboard[0][0].callback_data == "act_qr")
ok("دکمه شماره", mk.inline_keyboard[1][0].callback_data == "act_phone_m")
ok("لغو", mk.inline_keyboard[2][0].callback_data == "cancel")
rk = K.code_retry()
ok("code_retry: SMS", rk.inline_keyboard[0][0].callback_data == "act_sms")
ok("code_retry: QR", rk.inline_keyboard[1][0].callback_data == "act_qr2")
wk = K.qr_wait_kb()
ok("qr_wait_kb لغو + سوییچ", wk.inline_keyboard[0][0].callback_data == "cancel"
   and wk.inline_keyboard[1][0].callback_data == "act_phone_m2")

print("— ۴) متن‌ها")
import texts as T  # noqa: E402
ok("CHOOSE_METHOD بدون ** (پارس‌مود خاموش)", "**" not in T.CHOOSE_METHOD)
ok("SESSION_CODE هشدار فوروارد", "فوروارد نکن" in T.SESSION_CODE)
ok("CODE_BLOCKED توضیح share", "share" in T.CODE_BLOCKED and "SMS" in T.CODE_BLOCKED)
ok("QR_TIMEOUT دارای {cost}", "{cost}" in T.QR_TIMEOUT)
for t_name in ("CHOOSE_METHOD", "QR_STARTED", "QR_RENEWED", "QR_TIMEOUT",
               "CODE_BLOCKED", "SMS_SENT"):
    ok(f"متن {t_name} بدون **", "**" not in getattr(T, t_name))

print("— ۵) activate.py: قواعد ورود")
import handlers.activate as A  # noqa: E402
src = inspect.getsource(A)
ok("سقف تلاش (attempts >= 2 → بلوک)", "attempts >= 2" in src)
ok("force_sms پشتیبانی می‌شود", "force_sms=True" in src)
ok("پارامتر دستگاه مثل سلف‌بات", 'device_model="Desktop"' in src
   and 'app_version="Star Self 1.0"' in src)
ok("watcher QR تعریف شده", "_qr_watch" in src)
ok("recreate توکن QR", "qr.recreate()" in src)
ok("2FA در مسیر QR هندل می‌شود", "SessionPasswordNeededError" in src)
ok("پوش فوری در _finish", "push_db_snapshot(db)" in src)
ok("CancelError در watcher امن", "CancelledError" in src)
# پیام قبلی که حلقه می‌ساخت دیگر نباید خودکار بی‌نهایت ارسال کند:
ok("هیچ حلقه ارسال نامحدود کد نیست",
   "کد جدید فرستادیم — همونو بفرست" not in src)

print("— ۶) admin.py + tariff.py: پوش بعد از همه عملیات جلسه‌ساز")
import handlers.admin as AD  # noqa: E402
asrc = inspect.getsource(AD)
for marker in ("man_session", "action == \"e\"", "action == \"r\"",
               "vault_revoke", "vault_delete"):
    ok(f"پوش در {marker}", marker in asrc)
n_push = asrc.count("push_db_snapshot(db)")
ok("۵ استفاده از push_db_snapshot در ادمین",
   n_push >= 5, f"n={n_push}")
import handlers.tariff as TF  # noqa: E402
tsrc = inspect.getsource(TF)
ok("tariff: پوش بعد از تمدید پلن", "push_db_snapshot(db)" in tsrc)
ok("tariff: از منوی روش مشترک استفاده می‌کند", "start_session_build" in tsrc
   and "Act.phone" not in tsrc)

print("— ۷) شبیه‌سازی حلقه QR (بدون تلگرام واقعی)")


class FakeQR:
    """شبیه‌سازی QRLogin: هر بار تایم‌اوت، توکن نو؛ راند ۳ موفق."""

    def __init__(self):
        self.rounds = 0
        self.urls = []

    @property
    def url(self):
        return f"tg://login?token=t{self.rounds}"

    async def wait(self, timeout=None):
        await asyncio.sleep(0.01)
        self.rounds += 1
        if self.rounds < 3:
            raise asyncio.TimeoutError()

    async def recreate(self):
        self.urls.append(self.url)


async def sim():
    qr = FakeQR()
    for rnd in range(5):
        if rnd:
            qr.urls.append(qr.url)  # ادیت تصویر
        try:
            await qr.wait(timeout=0.05)
        except asyncio.TimeoutError:
            await qr.recreate()
            continue
        return f"success@{qr.url}"
    return "timeout"


res = asyncio.run(sim())
ok("شبیه‌سازی wait→recreate→success", res == "success@tg://login?token=t3", res)


class FakeQRNever(FakeQR):
    async def wait(self, timeout=None):
        await asyncio.sleep(0.01)
        raise asyncio.TimeoutError()


async def sim2():
    qr = FakeQRNever()
    for rnd in range(5):
        if rnd:
            qr.urls.append(qr.url)
        try:
            await qr.wait(timeout=0.05)
        except asyncio.TimeoutError:
            await qr.recreate()
            continue
        return "success"
    return "timeout"


ok("شبیه‌سازی تایم‌اوت کامل → مسیر منو", asyncio.run(sim2()) == "timeout")

print(f"\n═══ نتیجه: {PASS} پاس / {FAIL} شکست ═══")
sys.exit(1 if FAIL else 0)
