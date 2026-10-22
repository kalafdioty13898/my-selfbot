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
from handlers.common import Act, CLIENTS, PENDING, maybe_dispatch, fire_and_forget, log
from utils import parse_phone, PLAN_LABELS


def build(cfg, db):
    r = Router()

    async def start_session_build(responder, state, uid, plan, days, paid):
        """شروع جریان ساخت سشن؛ paid=True یعنی سکه کم شده و در خطا باید برگردد."""
        PENDING[uid] = {"plan": plan, "days": days, "paid": paid}
        await state.set_state(Act.phone)
        await responder(T.SESSION_PHONE)

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
        await cb.answer(f"🪙 {cost} سکه کم شد")
        await start_session_build(cb.message.answer, state, uid, "coin_1d",
                                  await db.sint("initial_days", 1), paid=True)

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
            sent = await client.send_code_request(phone)
            CLIENTS[uid] = client
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
            await state.clear()
            return await m.answer("⛔ جریان ساخت سشن منقضی شد؛ دوباره از «فعال‌سازی سلف» شروع کن.")
        code = (m.text or "").strip()
        try:
            await client.sign_in(phone=data["phone"], code=code,
                                 phone_code_hash=data.get("code_hash"))
            await _finish(m, state, uid, client)
        except errors.SessionPasswordNeededError:
            await state.set_state(Act.password)
            await m.answer(T.SESSION_PASS)
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError):
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
            await state.clear()
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
        meta = PENDING.pop(uid, None) or {"plan": "coin_1d",
                                          "days": await db.sint("initial_days", 1),
                                          "paid": False}
        note = await db.sget("admin_note", "")
        await db.add_activation(uid, enc(session_str), phone, meta["plan"], meta["days"], note)
        fire_and_forget(maybe_dispatch(cfg))
        plan_label = PLAN_LABELS.get(meta["plan"], meta["plan"])
        # محاسبه تاریخ انقضا برای نمایش
        from utils import now
        from datetime import timedelta
        exp = (now() + timedelta(days=meta["days"])).strftime("%Y-%m-%d %H:%M")
        await m.answer(T.ACTIVATED.format(expires=exp, plan=plan_label, note=note),
                       reply_markup=K.back_menu("menu"))
        log.info(f"activation created uid={uid} plan={meta['plan']} days={meta['days']}")

    async def _cancel(m: Message, state: FSMContext, uid: int):
        meta = PENDING.pop(uid, None)
        await cleanup(uid)
        await state.clear()
        if meta and meta.get("paid"):
            cost = await db.sint("activation_cost", 15)
            await db.add_balance(uid, cost, "refund", "لغو فعال‌سازی")
            await m.answer(f"❌ لغو شد؛ 🪙 {cost} سکه برگشت داده شد.",
                           reply_markup=K.back_menu("menu"))
        else:
            await m.answer("❌ لغو شد.", reply_markup=K.back_menu("menu"))

    async def _fail(m: Message, state: FSMContext, uid: int, err: str):
        meta = PENDING.pop(uid, None)
        await state.clear()
        cost = await db.sint("activation_cost", 15)
        if meta and meta.get("paid"):
            await db.add_balance(uid, cost, "refund", "خطای فعال‌سازی")
            await m.answer(T.SESSION_FAIL.format(err=err, cost=cost),
                           reply_markup=K.back_menu("menu"))
        else:
            await m.answer(f"❌ ساخت سشن ناموفق بود ({err})",
                           reply_markup=K.back_menu("menu"))

    return r
