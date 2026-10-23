# -*- coding: utf-8 -*-
"""فعال‌سازی سلف + ساخت سشن داخل چت ربات.

دو روش ورود:
  🟦 QR  — بدون کد و بدون شماره؛ immune به بلاک «کد share شده» تلگرام.
  📱 شماره و کد — کد در اپ می‌آید (یا SMS)؛ با هشدار فوروارد-نکن و سقف تلاش.

چرا QR؟ تلگرام وقتی کد ورود در چت دیگری فوروارد/کپی شود، همان لحظه آن را
باطل می‌کند (محافظت ضد-فیشینگ). نتیجه: حلقه بی‌پایان «منقضی شد → کد جدید».
QR این کلاس از مشکل را کامل حذف می‌کند.
"""
import asyncio
import io
import logging  # noqa: F401 — سازگاری با ایمپورت‌های قبلی

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

import keyboards as K
import texts as T
from crypto import enc
from git_sync import push_db_snapshot
from handlers.common import (Act, CLIENTS, PENDING, BUSY, QR_TASKS,
                             maybe_dispatch, fire_and_forget, log)
from handlers.common import start_session_build  # noqa: F401 — منوی انتخاب روش (QR/شماره)
from utils import parse_phone, normalize_code, PLAN_LABELS

# پارامترهای دستگاهِ لاگین = دقیقاً همان پارامترهای سلف‌بات؛
# هم هشدار «ورود جدید» تلگرام طبیعی دیده می‌شود هم سشن با همان دستگاه ادامه می‌یابد.
DEVICE = dict(device_model="Desktop", system_version="Windows 10",
              app_version="Star Self 1.0")

QR_ROUNDS = 5      # هر راند ~۳۰ ثانیه → پنجره کل ~۲/۵ دقیقه
QR_WAIT = 28       # کمی کمتر از عمر توکن (۳۰ ثانیه)


def _qr_png(url: str) -> bytes:
    """تصویر PNG کد QR برای لینک ورود تلگرام."""
    import qrcode
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def build(cfg, db):
    r = Router()

    r.start_session_build = start_session_build  # سازگاری با کالرهای قدیمی

    async def cleanup(uid):
        cl = CLIENTS.pop(uid, None)
        if cl:
            try:
                await cl.disconnect()
            except Exception:
                pass

    async def refund_amount(meta) -> int:
        """مبلغ دقیق پرداختی کاربر (پلن یا فعال‌سازی) برای بازگشت."""
        if meta and meta.get("amount"):
            return int(meta["amount"])
        return await db.sint("activation_cost", 15)

    def _bot():
        return getattr(cfg, "bot", None)

    # ---------- منوی فعال‌سازی ----------
    @r.callback_query(F.data == "cb_act")
    async def act(cb: CallbackQuery, state: FSMContext):
        act_row = await db.active_of(cb.from_user.id)
        if act_row:
            await cb.message.answer(
                f"✅ سلف تو همین حالا فعاله!\n🗓 اعتبار تا: {act_row['expires_at'][:16]}",
                reply_markup=K.back_menu("menu"))
            return await cb.answer()
        await cb.message.answer(T.ACT_ASK.format(name=cb.from_user.first_name or "کاربر"),
                                reply_markup=K.act_confirm())
        await cb.answer()

    @r.callback_query(F.data == "act_yes")
    async def act_yes(cb: CallbackQuery, state: FSMContext):
        uid = cb.from_user.id
        if await db.active_of(uid):
            await cb.answer("قبلاً فعال کرده‌ای!", show_alert=True)
            return
        cost = await db.sint("activation_cost", 15)
        bal = await db.balance(uid)
        if bal < cost:
            await cb.message.answer(T.NO_BALANCE.format(cost=cost, balance=bal),
                                    reply_markup=K.need_coins())
            return await cb.answer()
        await db.add_balance(uid, -cost, "activate", "خرید سلف (فعال‌سازی)")
        ok = await start_session_build(cb.message.answer, state, uid, "coin_1d",
                                       await db.sint("initial_days", 1), paid=True,
                                       amount=cost)
        if ok:
            await cb.answer(f"🪙 {cost} سکه کم شد")
        else:
            # جریان دیگری بود — سکه برگشت داده می‌شود
            await db.add_balance(uid, cost, "refund", "جریان موازی فعال‌سازی")
            await cb.answer("جریان فعال داری؛ سکه برگشت خورد", show_alert=True)

    # ---------- انتخاب روش ورود ----------
    @r.callback_query(F.data.in_({"act_phone_m", "act_phone_m2"}))
    async def act_phone_method(cb: CallbackQuery, state: FSMContext):
        uid = cb.from_user.id
        if uid not in PENDING:
            BUSY.discard(uid)
            await state.clear()
            await cb.message.answer("⛔ جریان منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.",
                                    reply_markup=K.back_menu("menu"))
            return await cb.answer()
        # اگر از وسط QR آمده — تسک و کلاینتش جمع شود (سکه‌ها هنوز نزد ماست)
        t = QR_TASKS.pop(uid, None)
        if t and not t.done():
            t.cancel()
        await cleanup(uid)
        await state.set_state(Act.phone)
        await cb.message.answer(T.SESSION_PHONE)
        await cb.answer()

    @r.callback_query(F.data.in_({"act_qr", "act_qr2"}))
    async def act_qr_start(cb: CallbackQuery, state: FSMContext):
        uid = cb.from_user.id
        if uid not in PENDING:
            BUSY.discard(uid)
            await state.clear()
            await cb.message.answer("⛔ جریان منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.",
                                    reply_markup=K.back_menu("menu"))
            return await cb.answer()
        t = QR_TASKS.pop(uid, None)
        if t and not t.done():
            t.cancel()
        await cleanup(uid)
        client = TelegramClient(StringSession(), cfg.api_id, cfg.api_hash, **DEVICE)
        try:
            await client.connect()
            CLIENTS[uid] = client
            qr = await client.qr_login()
        except errors.FloodWaitError as e:
            await cleanup(uid)
            BUSY.discard(uid)
            await state.clear()
            await _fail(cb.message, state, uid, f"محدودیت تلگرام ({e.seconds}s)")
            return await cb.answer()
        except Exception as e:
            await cleanup(uid)
            BUSY.discard(uid)
            await state.clear()
            await _fail(cb.message, state, uid, str(e)[:100])
            return await cb.answer()
        await state.set_state(Act.qr_wait)
        # QR به هیچ شماره‌ای وابسته نیست؛ اگر از مسیر شماره/کد آمده، پاک شود تا
        # در پایان، شماره‌ی واقعیِ اکانتی که اسکن کرده ذخیره شود نه شماره قدیمی
        await state.update_data(phone="", code_hash=None, attempts=0)
        png = _qr_png(qr.url)
        sent = await cb.message.answer_photo(
            BufferedInputFile(png, filename="qr.png"),
            caption=T.QR_STARTED, reply_markup=K.qr_wait_kb())
        task = asyncio.create_task(
            _qr_watch(uid, state, client, sent.chat.id, sent.message_id, qr))
        QR_TASKS[uid] = task
        await cb.answer()

    # ---------- مراحل ساخت سشن (روش شماره و کد) ----------
    @r.message(Act.method)
    async def act_method_msg(m: Message, state: FSMContext):
        uid = m.from_user.id
        if (m.text or "").strip() == "لغو":
            return await _cancel(m, state, uid)
        await m.answer("🔑 لطفاً از دکمه‌های زیر انتخاب کن:", reply_markup=K.act_method())

    @r.message(Act.phone)
    async def act_phone(m: Message, state: FSMContext):
        uid = m.from_user.id
        if (m.text or "").strip() == "لغو":
            return await _cancel(m, state, uid)
        phone = parse_phone(m.text)
        if not phone:
            return await m.answer(T.SESSION_ERR_PHONE)
        await cleanup(uid)
        try:
            client = TelegramClient(StringSession(), cfg.api_id, cfg.api_hash, **DEVICE)
            await client.connect()
            CLIENTS[uid] = client  # قبل از هر کار fail-شونده — تا leak نشود
            sent = await client.send_code_request(phone)
            await state.update_data(phone=phone, code_hash=sent.phone_code_hash,
                                    attempts=0)
            await state.set_state(Act.code)
            await m.answer(T.SESSION_CODE)
        except errors.FloodWaitError as e:
            await cleanup(uid)
            await m.answer(f"⏳ تلگرام محدودیت زمانی گذاشته؛ {e.seconds} ثانیه دیگر دوباره تلاش کن.")
        except Exception as e:
            await cleanup(uid)
            await _fail(m, state, uid, str(e)[:100])

    @r.message(Act.code)
    async def act_code(m: Message, state: FSMContext):
        uid = m.from_user.id
        if (m.text or "").strip() == "لغو":
            return await _cancel(m, state, uid)
        data = await state.get_data()
        client = CLIENTS.get(uid)
        if not client:
            meta = PENDING.pop(uid, None)
            BUSY.discard(uid)
            await state.clear()
            if meta and meta.get("paid"):
                cost = await refund_amount(meta)
                await db.add_balance(uid, cost, "refund", "انقضای جریان فعال‌سازی")
                return await m.answer(
                    f"⛔ جریان ساخت سشن منقضی شد؛ 🪙 {cost} سکه برگشت خورد. دوباره از «فعال‌سازی سلف» شروع کن.")
            return await m.answer("⛔ جریان ساخت سشن منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.")
        code = normalize_code(m.text)
        if not code:
            return await m.answer(T.SESSION_ERR_CODE)
        # شمارش تلاش‌ها: تلگرام کد share-شده را باطل می‌کند؛ ارسال بی‌نهایت کد
        # فقط هشدارهای پی‌درپی تلگرام + فلود می‌آورد. سقف: ۲ تلاش → پیشنهاد SMS/QR
        attempts = (data.get("attempts") or 0) + 1
        await state.update_data(attempts=attempts)
        try:
            await client.sign_in(phone=data["phone"], code=code,
                                 phone_code_hash=data.get("code_hash"))
            await _finish(m.answer, state, uid, client)
        except errors.SessionPasswordNeededError:
            await state.set_state(Act.password)
            await m.answer(T.SESSION_PASS)
        except (errors.PhoneCodeExpiredError, errors.PhoneCodeInvalidError):
            if attempts >= 2:
                # دیگر خودکار کد نفرست! توضیح بلاک تلگرام + راه‌حل‌ها
                await m.answer(T.CODE_BLOCKED, reply_markup=K.code_retry())
            else:
                try:
                    sent = await client.send_code_request(data["phone"])
                    await state.update_data(code_hash=sent.phone_code_hash)
                    await m.answer(
                        "⏳ کد قبلی پذیرفته نشد؛ یک کد دیگر فرستادیم.\n"
                        "⚠️ این بار کد را فوروارد/کپی نکن — فقط دستی تایپ کن.")
                except errors.FloodWaitError as e:
                    await m.answer(f"⏳ تلگرام محدودیت زمانی گذاشته؛ {e.seconds} ثانیه دیگر تلاش کن.")
                except Exception:
                    await m.answer(T.CODE_BLOCKED, reply_markup=K.code_retry())
        except Exception as e:
            await cleanup(uid)
            await _fail(m, state, uid, str(e)[:100])

    @r.message(Act.password)
    async def act_pass(m: Message, state: FSMContext):
        uid = m.from_user.id
        if (m.text or "").strip() == "لغو":
            return await _cancel(m, state, uid)
        client = CLIENTS.get(uid)
        if not client:
            meta = PENDING.pop(uid, None)
            BUSY.discard(uid)
            await state.clear()
            if meta and meta.get("paid"):
                cost = await refund_amount(meta)
                await db.add_balance(uid, cost, "refund", "انقضای جریان فعال‌سازی")
                return await m.answer(
                    f"⛔ جریان ساخت سشن منقضی شد؛ 🪙 {cost} سکه برگشت خورد. دوباره از «فعال‌سازی سلف» شروع کن.")
            return await m.answer("⛔ جریان ساخت سشن منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.")
        try:
            await client.sign_in(password=(m.text or "").strip())
            await _finish(m.answer, state, uid, client)
        except errors.PasswordHashInvalidError:
            await m.answer("❌ رمز دوم اشتباه است؛ دوباره بفرست.")
        except Exception as e:
            await cleanup(uid)
            await _fail(m, state, uid, str(e)[:100])

    # ---------- دریافت کد با SMS (وقتی کد اپ باطل می‌شود) ----------
    @r.callback_query(F.data == "act_sms")
    async def act_sms(cb: CallbackQuery, state: FSMContext):
        uid = cb.from_user.id
        client = CLIENTS.get(uid)
        data = await state.get_data()
        phone = data.get("phone")
        if not client or not phone:
            BUSY.discard(uid)
            await state.clear()
            await cb.message.answer("⛔ جریان منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.",
                                    reply_markup=K.back_menu("menu"))
            return await cb.answer()
        try:
            sent = await client.send_code_request(phone, force_sms=True)
            await state.update_data(code_hash=sent.phone_code_hash, attempts=0)
            await state.set_state(Act.code)
            await cb.message.answer(T.SMS_SENT)
            await cb.answer()
        except errors.FloodWaitError as e:
            await cb.answer(f"محدودیت تلگرام: {e.seconds} ثانیه", show_alert=True)
        except Exception as e:
            await cb.answer(str(e)[:80], show_alert=True)

    # ---------- منتظرِ اسکن QR ----------
    async def _qr_watch(uid, state, client, chat_id, msg_id, qr):
        bot = _bot()
        try:
            for rnd in range(QR_ROUNDS):
                # ۱) منتظر اسکن و تأیید در اپ کاربر (تصویر راند ۰ تازه فرستاده شده)
                if rnd:
                    try:
                        png = _qr_png(qr.url)
                        await bot.edit_message_media(
                            chat_id=chat_id, message_id=msg_id,
                            media=InputMediaPhoto(media=BufferedInputFile(png, filename="qr.png"),
                                                  caption=T.QR_RENEWED))
                    except Exception:
                        pass  # ادیت تصویر حیاتی نیست؛ منتظر اسکن بمان
                try:
                    await qr.wait(timeout=QR_WAIT)
                except asyncio.TimeoutError:
                    try:
                        await qr.recreate()  # توکن جدید برای راند بعد
                    except Exception:
                        break  # فلود/خطا — پنجره را ببند
                    continue
                except errors.SessionPasswordNeededError:
                    # رمز دوم دارد — کلاینت نگه داشته می‌شود؛ مسیر act_pass ادامه می‌دهد
                    QR_TASKS.pop(uid, None)
                    CLIENTS[uid] = client
                    await state.set_state(Act.password)
                    try:
                        await bot.send_message(chat_id, T.SESSION_PASS)
                    except Exception:
                        pass
                    return
                # ۲) موفق! سشن ساخته شد
                QR_TASKS.pop(uid, None)
                await _finish(
                    lambda text, **kw: bot.send_message(chat_id, text, **kw),
                    state, uid, client)
                return
            # پنجره تمام شد و اسکنی نشد → به منوی روش برگرد (سکه‌ها نزد ما می‌ماند)
            QR_TASKS.pop(uid, None)
            await state.set_state(Act.method)
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id, message_id=msg_id,
                    caption="⏳ زمان اسکن تمام شد؛ QR را دوباره شروع کن یا روش شماره و کد را انتخاب کن.",
                    reply_markup=K.qr_retry())
            except Exception:
                await bot.send_message(chat_id, "⏳ زمان اسکن QR تمام شد؛ دوباره تلاش کن.",
                                       reply_markup=K.qr_retry())
        except asyncio.CancelledError:
            # لغو از مسیر abort/cancel — پاک‌سازی آنجا انجام شده
            raise
        except Exception:
            log.exception("qr watch uid=%s failed", uid)
            QR_TASKS.pop(uid, None)
            try:
                await bot.send_message(
                    chat_id, "❌ خطای غیرمنتظره در ورود QR؛ دوباره تلاش کن.",
                    reply_markup=K.qr_retry())
            except Exception:
                pass

    # ---------- پایان موفق ----------
    async def _finish(responder, state: FSMContext, uid: int, client: TelegramClient):
        """responder: تابع (text, **kw) → پیام؛ یا m.answer یا bot.send_message."""
        session_str = client.session.save()
        phone = (await state.get_data()).get("phone", "")
        t = QR_TASKS.pop(uid, None)
        if t and not t.done():
            t.cancel()
        await cleanup(uid)
        await state.clear()
        BUSY.discard(uid)
        meta = PENDING.pop(uid, None) or {"plan": "coin_1d",
                                          "days": await db.sint("initial_days", 1),
                                          "paid": False}
        note = await db.sget("admin_note", "")
        # شماره هم رمزنگاری می‌شود (دیتابیس در ریپوی عمومی است — PII نباید خام باشد)
        await db.add_activation(uid, enc(session_str), enc(phone) if phone else "",
                                meta["plan"], meta["days"], note)
        # فعال‌سازی آنی: دیتابیس همین لحظه پوش می‌شود تا سلف ≤ ۲ دقیقه دیگر آنلاین شود
        fire_and_forget(push_db_snapshot(db))
        fire_and_forget(maybe_dispatch(cfg))
        plan_label = PLAN_LABELS.get(meta["plan"], meta["plan"])
        # محاسبه تاریخ انقضا برای نمایش
        from utils import now
        from datetime import timedelta
        exp = (now() + timedelta(days=meta["days"])).strftime("%Y-%m-%d %H:%M")
        await responder(T.ACTIVATED.format(expires=exp, plan=plan_label, note=note),
                        reply_markup=K.back_menu("menu"))
        bot = _bot()
        if bot and cfg.admin_id:
            async def _notify():
                try:
                    await bot.send_message(
                        cfg.admin_id,
                        T.ACT_ADMIN.format(uid=uid, plan=plan_label,
                                           expires=exp))
                except Exception:
                    pass
            fire_and_forget(_notify())
        log.info(f"activation created uid={uid} plan={meta['plan']} days={meta['days']}")

    async def _cancel(m: Message, state: FSMContext, uid: int):
        meta = PENDING.pop(uid, None)
        t = QR_TASKS.pop(uid, None)
        if t and not t.done():
            t.cancel()
        await cleanup(uid)
        await state.clear()
        BUSY.discard(uid)
        if meta and meta.get("paid"):
            cost = await refund_amount(meta)
            await db.add_balance(uid, cost, "refund", "لغو فعال‌سازی")
            await m.answer(f"❌ لغو شد؛ 🪙 {cost} سکه برگشت داده شد.",
                           reply_markup=K.back_menu("menu"))
        else:
            await m.answer("❌ لغو شد.", reply_markup=K.back_menu("menu"))

    async def _fail(m, state, uid, err: str):
        meta = PENDING.pop(uid, None)
        t = QR_TASKS.pop(uid, None)
        if t and not t.done():
            t.cancel()
        await state.clear()
        BUSY.discard(uid)
        await cleanup(uid)
        if meta and meta.get("paid"):
            cost = await refund_amount(meta)
            await db.add_balance(uid, cost, "refund", "خطای فعال‌سازی")
            await m.answer(T.SESSION_FAIL.format(err=err, cost=cost),
                           reply_markup=K.back_menu("menu"))
        else:
            await m.answer(f"❌ ساخت سشن ناموفق بود ({err})",
                           reply_markup=K.back_menu("menu"))

    return r
