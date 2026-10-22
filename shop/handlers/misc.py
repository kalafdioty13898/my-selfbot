# -*- coding: utf-8 -*-
"""راهنما (ویرایش منو)، قوانین، سلف چیست، سلامت سلف، پشتیبانی."""
from datetime import timedelta

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import keyboards as K
import texts as T
from handlers.common import Support
from utils import naive_now, parse_dt, fmt_tom, PLAN_LABELS


def build(cfg, db):
    r = Router()

    # ---------- راهنمای پنل (روی خود منو ویرایش می‌شود) ----------
    @r.callback_query(F.data == "cb_guide")
    async def guide(cb: CallbackQuery):
        try:
            await cb.message.edit_text(T.GUIDE, reply_markup=K.back_menu("menu"))
        except Exception:
            await cb.message.answer(T.GUIDE, reply_markup=K.back_menu("menu"))
        await cb.answer()

    @r.callback_query(F.data == "cb_rules")
    async def rules(cb: CallbackQuery):
        await cb.message.answer(T.RULES, reply_markup=K.back_menu("cb_wallet_home"))
        await cb.answer()

    @r.callback_query(F.data == "cb_whatis")
    async def whatis(cb: CallbackQuery):
        await cb.message.answer(T.WHatIS, reply_markup=K.back_menu("menu"))
        await cb.answer()

    # ---------- سلامت و وضعیت سلف ----------
    @r.callback_query(F.data == "cb_health")
    async def health(cb: CallbackQuery):
        act = await db.active_of(cb.from_user.id)
        if not act:
            await cb.message.answer(T.HEALTH_NO, reply_markup=K.back_menu("menu"))
            return await cb.answer()
        ping = act["last_ping"] or ""
        if ping:
            p = parse_dt(ping)
            if p:
                diff = (naive_now() - p).total_seconds()
                if diff <= 900:
                    status = "✅ آنلاین"
                elif diff <= 19000:
                    status = "⏳ به‌زودی آنلاین می‌شود"
                else:
                    status = "⚠️ بی‌خبر (احتمالاً در انتظار ران بعدی)"
                ping_txt = f"{int(diff // 60)} دقیقه پیش"
            else:
                status, ping_txt = "⏳ نامشخص", ping[:16]
        else:
            status, ping_txt = "⏳ هنوز پینگی ثبت نشده", "—"
        await cb.message.answer(T.HEALTH_OK.format(
            status=status, expires=act["expires_at"][:16],
            plan=PLAN_LABELS.get(act["plan"], act["plan"]),
            ping=ping_txt), reply_markup=K.back_menu("menu"))
        await cb.answer()

    # ---------- پشتیبانی ----------
    @r.callback_query(F.data == "cb_support")
    async def support(cb: CallbackQuery, state: FSMContext):
        await state.set_state(Support.wait)
        await cb.message.answer(T.SUPPORT, reply_markup=K.support_kb())
        await cb.answer()

    @r.message(Support.wait)
    async def support_msg(m: Message, state: FSMContext):
        header = T.ADMIN_NOTIFY_SUPPORT.format(
            name=m.from_user.first_name or "", uid=m.from_user.id,
            username=m.from_user.username or "")
        try:
            await cfg.bot.send_message(cfg.admin_id, header)
            await m.copy_to(cfg.admin_id)
            await m.answer(T.SUPPORT_SENT)
        except Exception:
            await m.answer("⚠️ ارسال نشد؛ دوباره تلاش کن.")
        # در حالت پشتیبانی می‌ماند تا «لغو» بزند

    return r
