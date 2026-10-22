# -*- coding: utf-8 -*-
"""فعال‌سازی سلف + ساخت سشن داخل چت ربات (شماره → کد → رمز دوم)."""
import logging

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

import keyboards as K
import texts as T
from crypto import enc
from git_sync import push_db_snapshot
from handlers.common import (Act, CLIENTS, PENDING, BUSY, maybe_dispatch,
                             fire_and_forget, log)
from utils import parse_phone, normalize_code, PLAN_LABELS


def build(cfg, db):
    r = Router()

    async def start_session_build(responder, state, uid, plan, days, paid, amount=0):
        """شروع جریان ساخت سشن؛ amount = مبلغ دقیق پرداختی برای بازگشت.
        False یعنی جریان دیگری برای همین کاربر در جریان است."""
        if uid in BUSY:
            await responder(
                "⏳ یک فعال‌سازی برای تو در جریان است؛ اول «لغو» بفرست یا صبر کن تمام شود.")
            return False
        BUSY.add(uid)
        PENDING[uid] = {"plan": plan, "days": days, "paid": paid, "amount": int(amount or 0)}
        await state.set_state(Act.phone)
        await responder(T.SESSION_PHONE)
        return True

    r.start_session_build = start_session_build

    async def cleanup(uid):
        cl = CLIENTS.pop(uid, None)
        if cl:
            try:
                await cl.disconnect()
            except Exception:
                pass

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

    # ---------- مراحل ساخت سشن ----------
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
            client = TelegramClient(StringSession(), cfg.api_id, cfg.api_hash)
            await client.connect()
            CLIENTS[uid] = client  # قبل از هر کار fail-شونده — تا leak نشود
            sent = await client.send_code_request(phone)
            await state.update_data(phone=phone, code_hash=sent.phone_code_hash)
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
                cost = await _refund_amount(meta)
                await db.add_balance(uid, cost, "refund", "انقضای جریان فعال‌سازی")
                return await m.answer(
                    f"⛔ جریان ساخت سشن منقضی شد؛ 🪙 {cost} سکه برگشت خورد. دوباره از «فعال‌سازی سلف» شروع کن.")
            return await m.answer("⛔ جریان ساخت سشن منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.")
        code = normalize_code(m.text)
        if not code:
            return await m.answer(T.SESSION_ERR_CODE)
        try:
            await client.sign_in(phone=data["phone"], code=code,
                                 phone_code_hash=data.get("code_hash"))
            await _finish(m, state, uid, client)
        except errors.SessionPasswordNeededError:
            await state.set_state(Act.password)
            await m.answer(T.SESSION_PASS)
        except errors.PhoneCodeExpiredError:
            # کد منقضی → خودکار کد جدید بفرست تا کاربر گیر نکنه
            try:
                sent = await client.send_code_request(data["phone"])
                await state.update_data(code_hash=sent.phone_code_hash)
                await m.answer("⏳ کد قبلی منقضی شده بود؛ کد جدید فرستادیم — همونو بفرست.")
            except errors.FloodWaitError as e:
                await m.answer(f"⏳ تلگرام محدودیت زمانی گذاشته؛ {e.seconds} ثانیه دیگر تلاش کن.")
            except Exception:
                await m.answer(T.SESSION_ERR_CODE)
        except errors.PhoneCodeInvalidError:
            await m.answer(T.SESSION_ERR_CODE)
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
                cost = await _refund_amount(meta)
                await db.add_balance(uid, cost, "refund", "انقضای جریان فعال‌سازی")
                return await m.answer(
                    f"⛔ جریان ساخت سشن منقضی شد؛ 🪙 {cost} سکه برگشت خورد. دوباره از «فعال‌سازی سلف» شروع کن.")
            return await m.answer("⛔ جریان ساخت سشن منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.")
        try:
            await client.sign_in(password=(m.text or "").strip())
            await _finish(m, state, uid, client)
        except errors.PasswordHashInvalidError:
            await m.answer("❌ رمز دوم اشتباه است؛ دوباره بفرست.")
        except Exception as e:
            await cleanup(uid)
            await _fail(m, state, uid, str(e)[:100])

    async def _finish(m: Message, state: FSMContext, uid: int, client: TelegramClient):
        session_str = client.session.save()
        phone = (await state.get_data()).get("phone", "")
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
        await m.answer(T.ACTIVATED.format(expires=exp, plan=plan_label, note=note),
                       reply_markup=K.back_menu("menu"))
        bot = getattr(cfg, "bot", None)
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

    async def _refund_amount(meta) -> int:
        """مبلغ دقیق پرداختی کاربر (پلن یا فعال‌سازی) برای بازگشت."""
        if meta and meta.get("amount"):
            return int(meta["amount"])
        return await db.sint("activation_cost", 15)

    async def _cancel(m: Message, state: FSMContext, uid: int):
        meta = PENDING.pop(uid, None)
        await cleanup(uid)
        await state.clear()
        BUSY.discard(uid)
        if meta and meta.get("paid"):
            cost = await _refund_amount(meta)
            await db.add_balance(uid, cost, "refund", "لغو فعال‌سازی")
            await m.answer(f"❌ لغو شد؛ 🪙 {cost} سکه برگشت داده شد.",
                           reply_markup=K.back_menu("menu"))
        else:
            await m.answer("❌ لغو شد.", reply_markup=K.back_menu("menu"))

    async def _fail(m: Message, state: FSMContext, uid: int, err: str):
        meta = PENDING.pop(uid, None)
        await state.clear()
        BUSY.discard(uid)
        await cleanup(uid)
        if meta and meta.get("paid"):
            cost = await _refund_amount(meta)
            await db.add_balance(uid, cost, "refund", "خطای فعال‌سازی")
            await m.answer(T.SESSION_FAIL.format(err=err, cost=cost),
                           reply_markup=K.back_menu("menu"))
        else:
            await m.answer(f"❌ ساخت سشن ناموفق بود ({err})",
                           reply_markup=K.back_menu("menu"))

    return r
