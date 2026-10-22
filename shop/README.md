# ⭐️ star self — ربات فروش سلف

ربات فروشگاهی تلگرام (بات رسمی BotFather) برای فروش خودکار سلف‌بات:
کیف پول سکه‌ای، خرید کارت‌به‌کارت با رسید، انتقال سکه، سیستم زیرمجموعه‌گیری،
فعال‌سازی خودکار سلف با ساخت سشن داخل چت ربات، پنل ادمین کامل و API اتصال به سلف.

---

## ✨ امکانات

**بخش مشتری**
- 🏠 منوی اصلی ۱۰گانه با دکمه شیشه‌ای (فعال‌سازی، کیف پول، خرید سکه، راهنما، زیرمجموعه، سلامت سلف، سلف چیست، تعرفه، قوانین، پشتیبانی)
- 👛 کیف پول: موجودی، ارزش ریالی، وضعیت سلف، رسید در انتظار، تراکنش‌ها
- 💸 انتقال سکه (۲ مرحله‌ای): حداقل ۲۰ / حداکثر ۱۰,۰۰۰ / سقف روزانه ۵,۰۰۰
- 🛒 خرید سکه با کارت‌به‌کارت و ارسال عکس/PDF رسید → تایید ادمین → واریز خودکار
- ⚡️ فعال‌سازی سلف: کسر سکه → **ساخت سشن داخل چت ربات** (شماره → کد → رمز دوم) → ثبت رمزنگاری‌شده
- 💎 تعرفه: پلن ۲ ماهه / ۴ ماهه / فعال‌سازی رایگان (زیرمجموعه‌گیری)
- 👥 زیرمجموعه: لینک دعوت اختصاصی، پاداش ۳ سکه + هدیه ۲ سکه
- 🩺 سلامت سلف: وضعیت آنلاین (با پینگ)، اعتبار، پلن
- 💬 پشتیبانی: پیام مستقیم برای مدیر

**پنل ادمین** (`/panel`)
- 📊 آمار کامل | 🧾 تایید/رد رسیدها با یک کلیک
- 👥 کاربران: شارژ/کسر/بن/تمدید/لغو سلف
- ➕ سلف دستی: آیدی + روز + سشن → ثبت مستقیم
- 🔐 گیت‌واوت: مشاهده سشن ۳۶۰ حرفی و شماره هر مشتری + لغو فوری
- 💸 کیف پول ادمین با ۱,۰۰۰,۰۰۰ سکه اولیه
- 📢 عضویت اجباری تا ۵ کانال/گروه | 📣 پیام همگانی | ⚙️ تنظیم قیمت‌ها و کارت

**خودکارسازی**
- ⏳ انقضای خودکار سلف + اخطار ۴۸ ساعت قبل
- 🔄 تمدید خودکار روزانه (۳ سکه) اگر موجودی کافی باشد
- 🔌 API سشن‌ها برای سلف: `GET /api/active_sessions?key=SHOP_KEY`
- 💓 ضربان سلامت: `POST /api/heartbeat`
- 🚀 (اختیاری) فعال‌سازی آنی با اجرای workflow سلف روی GitHub Actions

---

## 📁 ساختار

```
star_self_bot/
├── bot.py              # نقطه ورود (polling + API + تسک نگهداری)
├── config.py           # تنظیمات از .env
├── db.py               # SQLite (aiosqlite)
├── crypto.py           # رمزنگاری سشن‌ها (Fernet)
├── api.py              # API سشن‌ها و heartbeat
├── texts.py            # همه متن‌ها
├── keyboards.py        # کیبوردهای شیشه‌ای
├── handlers/           # start, wallet, coins, activate, tariff, misc, admin
├── tests/smoke.py      # تست دود (۵۴ تست)
└── data/               # دیتابیس + کلید رمزنگاری (بکاپ بگیر!)
```

---

## 🚀 نصب روی سرور (VPS / هاست لینوکسی)

نیاز: **Python 3.10+**

```bash
# ۱) آپلود پوشه پروژه روی سرور (مثلاً /opt/star_self_bot)
cd /opt/star_self_bot

# ۲) محیط مجازی و وابستگی‌ها
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# ۳) تنظیمات
cp .env.example .env
nano .env        # BOT_TOKEN, ADMIN_ID, API_ID, API_HASH, SHOP_KEY را پر کن

# ۴) تست
python tests/smoke.py

# ۵) اجرا
python bot.py
```

### اجرای دائمی با systemd

```bash
sudo tee /etc/systemd/system/star-self.service > /dev/null <<EOF
[Unit]
Description=star self shop bot
After=network.target

[Service]
WorkingDirectory=/opt/star_self_bot
ExecStart=/opt/star_self_bot/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now star-self
sudo journalctl -u star-self -f     # مشاهده لاگ زنده
```

---

## 🔑 ساخت .env

| متغیر | توضیح |
|---|---|
| `BOT_TOKEN` | توکن از [@BotFather](https://t.me/BotFather) → /newbot |
| `ADMIN_ID` | آیدی عددی خودت (@userinfobot) |
| `API_ID` / `API_HASH` | از my.telegram.org (همان سلف) — برای ساخت سشن مشتری‌ها |
| `SHOP_KEY` | یک رشته تصادفی بلند — کلید API سشن‌ها |
| `ENCRYPTION_KEY` | خالی بگذار → خودکار ساخته و در `data/.secret.key` ذخیره می‌شود |
| `PORT` | پورت API (پیش‌فرض 8080) |
| `BOT_USERNAME` | یوزرنیم ربات بدون @ (برای لینک دعوت) |
| `GH_REPO` / `GH_TOKEN` / `GH_WORKFLOW` | اختیاری — فعال‌سازی آنی روی GitHub Actions (فاز ۲) |

## 🤖 تنظیم BotFather

- `/setcommands` → `panel - پنل ادمین`
- `/setuserpic` و توضیحات ربات را کامل کن

---

## 🔌 API (اتصال سلف در فاز ۲)

```
GET  /api/active_sessions?key=SHOP_KEY
→ [{"user_id": 123, "session": "...", "plan": "coin_1d",
    "expires_at": "2026-01-01 12:00:00", "note": "سلف خریداری شده از @st4r_self_bot"}]

POST /api/heartbeat   {"key": "SHOP_KEY", "user_id": 123}
GET  /health
```

سلف روی GitHub Actions با یک مرحله `curl` این لیست را می‌گیرد و هر مشتری فعال
را اجرا می‌کند؛ انقضا یا لغو = حذف از لیست = قطع خودکار.

---

## 🔐 امنیت (مهم)

- سشن‌های مشتریان با **Fernet** رمزنگاری و در SQLite ذخیره می‌شوند؛ کلید در `data/.secret.key` است — **از این فایل و `data/star.db` بکاپ بگیر!**
- `SHOP_KEY` و `ENCRYPTION_KEY` را جایی فاش نکن؛ API بدون کلید جواب نمی‌دهد.
- گیت‌واوت فقط برای ADMIN_ID قابل دسترسی است.
- برای HTTPS پشت API می‌توانی از Nginx/Caddy reverse proxy استفاده کنی (فاز ۲ راهنمایت می‌کنم).
- درگاه پرداخت کارت‌به‌کارت دستی است؛ رسیدها را فقط از داخل پنل تایید کن.

## 🛠 عیب‌یابی

- `❌ BOT_TOKEN` → فایل `.env` کنار bot.py است؟ `systemctl status star-self`
- کد ورود نیامد → شماره با کد کشور (+98...) باشد؛ کد از تلگرام رسمی می‌آید
- API از بیرون باز نمی‌شود → پورت در فایروال باز است؟ (`ufw allow 8080`)

## 🔧 فیکس‌های نسخه فعلی

- **کد ورود تلگرام**: حالا ارقام فارسی (۵۲۹۴۱)، فاصله‌دار (5 2 9 4 1) و حتی کل متن پیام تلگرام قبول می‌شود؛ کد منقضی هم خودکار دوباره فرستاده می‌شود
- **گیت‌واوت**: هر ۳ دکمه (نمایش/لغو/حذف) درست کار می‌کند
- **بازگشت سکه**: لغو/خطای فعال‌سازی، دقیقاً همان مبلغ پرداختی (فعال‌سازی یا پلن) را برمی‌گرداند — حتی لغو با دکمه
