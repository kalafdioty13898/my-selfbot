# -*- coding: utf-8 -*-
"""کیبوردهای شیشه‌ای ربات فروش (ربات رسمی → دکمه اینلاین آزاد است)."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])


def url_kb(rows):
    """ردیف‌هایی که ممکن است URL داشته باشند: (text, url=None, cb=None)."""
    out = []
    for row in rows:
        line = []
        for item in row:
            t, url, cb = item
            if url:
                line.append(InlineKeyboardButton(text=t, url=url))
            else:
                line.append(InlineKeyboardButton(text=t, callback_data=cb))
        out.append(line)
    return InlineKeyboardMarkup(inline_keyboard=out)


# ---------- منوی اصلی ----------
def main_menu():
    return kb([
        [("⚡️ فعال‌سازی سلف", "cb_act"), ("👛 کیف پول", "cb_wallet")],
        [("🛒 خرید سکه", "cb_buy"), ("🎛 راهنمای پنل سلف", "cb_guide")],
        [("👥 زیرمجموعه‌گیری", "cb_ref"), ("🩺 سلامت و وضعیت سلف", "cb_health")],
        [("❓ سلف چیست؟", "cb_whatis"), ("💎 تعرفه سلف", "cb_tariff")],
        [("📜 قوانین", "cb_rules"), ("💬 پشتیبانی", "cb_support")],
    ])


def back_menu(cb="menu"):
    return kb([[("🔄 بازگشت", cb)]])


# ---------- فعال‌سازی ----------
def act_confirm():
    return kb([[("✅ بله، خرید سلف", "act_yes")], [("❌ لغو", "cancel")]])


def act_method():
    """انتخاب روش ورود بعد از پرداخت — QR سریع‌ترین و بدون کد است."""
    return kb([
        [("🟦 ورود سریع با QR (پیشنهادی)", "act_qr")],
        [("📱 ورود با شماره و کد", "act_phone_m")],
        [("❌ لغو", "cancel")],
    ])


def code_retry():
    """وقتی تلگرام کد را باطل می‌کند — دیگر ارسال خودکار نداریم."""
    return kb([
        [("📩 دریافت کد با پیامک (SMS)", "act_sms")],
        [("🟦 ورود با QR", "act_qr2")],
        [("❌ لغو", "cancel")],
    ])


def qr_wait_kb():
    return kb([[("❌ لغو", "cancel")], [("📱 روش شماره و کد", "act_phone_m2")]])


def need_coins():
    return kb([[("🛒 خرید سکه", "cb_buy")], [("👥 زیرمجموعه‌گیری", "cb_ref")]])


def qr_retry():
    return kb([[("🔄 دوباره QR", "act_qr2")], [("📱 شماره و کد", "act_phone_m2")],
               [("❌ لغو", "cancel")]])


# ---------- کیف پول ----------
def wallet_menu():
    return kb([
        [("💸 انتقال سکه", "cb_transfer"), ("➕ افزایش موجودی", "cb_buy")],
        [("📜 قوانین", "cb_rules"), ("🧾 تراکنش‌ها", "tx")],
        [("🔄 بازگشت", "menu")],
    ])


def transfer_confirm():
    return kb([[("❌ لغو", "cancel")], [("💸 انتقال سکه", "tr_yes")]])


# ---------- خرید سکه ----------
def buy_method():
    return kb([[("💳 کارت به کارت", "buy_card")], [("❌ لغو", "cancel")]])


def after_receipt():
    return kb([[("🏠 منوی اصلی", "menu")]])


# ---------- تعرفه ----------
def tariff_menu(p2, p4):
    return kb([
        [(f"🌟 ۲ ماه // {p2} تومان", "tar_2m")],
        [(f"🚀 ۴ ماه // {p4} تومان", "tar_4m")],
        [("🎁 فعال‌سازی رایگان", "tar_free")],
        [("🔄 بازگشت", "menu")],
    ])


def plan_confirm(label):
    return kb([[("✅ تأیید و پرداخت", f"tard_{label}")], [("❌ لغو", "cancel")]])


# ---------- زیرمجموعه ----------
def ref_menu():
    return kb([
        [("🛒 خرید سکه", "cb_buy"), ("📊 آمار دعوت", "cb_refstat")],
        [("🔄 بازگشت", "menu")],
    ])


def ref_stats_back():
    return kb([[("🔄 بازگشت", "cb_ref")], [("🏠 منوی اصلی", "menu")]])


# ---------- پشتیبانی ----------
def support_kb():
    return kb([[("❌ لغو", "cancel")]])


def force_join_kb(channels):
    rows = [[(f"📣 {c['title']}", c["link"], None)] for c in channels]
    rows.append([("✅ عضویت را بررسی کن", None, "fj_check")])
    return url_kb(rows)


# ---------- پنل ادمین ----------
def admin_menu():
    return kb([
        [("📊 آمار", "ad_stats"), ("🧾 رسیدها", "ad_receipts")],
        [("👥 کاربران", "ad_users"), ("➕ سلف دستی", "ad_manual")],
        [("🔐 گیت‌واوت", "ad_vault"), ("💸 کیف پول من", "ad_wallet")],
        [("📢 اجباری عضویت", "ad_force"), ("📣 پیام همگانی", "ad_bcast")],
        [("⚙️ تنظیمات", "ad_settings"), ("🏠 بستن", "ad_close")],
    ])


def admin_back(cb="ad_home"):
    return kb([[("🔄 بازگشت", cb)]])


def user_card_kb(uid):
    return kb([
        [("➕ شارژ سکه", f"adu_c_{uid}"), ("➖ کسر سکه", f"adu_d_{uid}")],
        [("⛔ بن / آزاد", f"adu_b_{uid}"), ("🎁 تمدید ۷ روز", f"adu_e_{uid}")],
        [("⛔ لغو سلف", f"adu_r_{uid}"), ("🔄 بازگشت", "ad_users")],
    ])


def vault_kb(items, page, pages):
    rows = [[(f"🔑 #{a['id']} — 🆔{a['user_id']}", f"va_{a['id']}")] for a in items]
    nav = []
    if page > 0:
        nav.append(("⬅️ قبلی", f"vp_{page - 1}"))
    if page + 1 < pages:
        nav.append(("بعدی ➡️", f"vp_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("🔄 بازگشت", "ad_vault0")])
    return kb(rows)


def vault_item_kb(aid):
    return kb([
        [("📋 نمایش سشن", f"vas_{aid}")],
        [("⛔ لغو سلف", f"var_{aid}"), ("🗑 حذف رکورد", f"vax_{aid}")],
        [("🔄 بازگشت", "ad_vault0")],
    ])


def receipt_kb(rid):
    return kb([
        [("✅ تأیید", f"rc_ok_{rid}"), ("❌ رد", f"rc_no_{rid}")],
    ])


def force_admin_kb(on, n):
    return kb([
        [("🔘 روشن/خاموش", "fj_toggle"), ("➕ افزودن", "fj_add")],
        [("🗑 حذف", "fj_rm"), ("🔄 بازگشت", "ad_home")],
    ])


def broadcast_confirm():
    return kb([[("✅ ارسال به همه", "bc_go")], [("❌ لغو", "ad_home")]])


def settings_kb():
    keys = [
        ("💰 قیمت سکه (تومان)", "coin_price"),
        ("🔢 حداقل خرید", "min_buy"),
        ("⚡️ هزینه فعال‌سازی (سکه)", "activation_cost"),
        ("🗓 اعتبار اولیه (روز)", "initial_days"),
        ("🔄 تمدید روزانه (سکه)", "daily_renew"),
        ("💳 شماره کارت", "card_number"),
        ("👤 صاحب کارت", "card_owner"),
        ("🌟 پلن ۲ ماه (تومان)", "plan_2m_price"),
        ("🚀 پلن ۴ ماه (تومان)", "plan_4m_price"),
        ("🪙 حداقل انتقال", "min_transfer"),
        ("🪙 حداکثر انتقال", "max_transfer"),
        ("📊 سقف روزانه انتقال", "daily_cap"),
        ("👥 پاداش دعوت", "ref_reward"),
        ("🎁 هدیه دعوت‌شده", "ref_gift"),
        ("🏷 متن برند روی سلف", "admin_note"),
    ]
    rows = [[(t, f"set_{k}")] for t, k in keys]
    rows.append([("🔄 بازگشت", "ad_home")])
    return kb(rows)
