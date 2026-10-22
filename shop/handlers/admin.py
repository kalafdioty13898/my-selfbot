# -*- coding: utf-8 -*-
"""پنل ادمین: آمار، رسیدها، کاربران، سلف دستی، گیت‌واوت، کیف پول ادمین،
عضویت اجباری، پیام همگانی و تنظیمات."""
import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import keyboards as K
import texts as T
from crypto import dec
from handlers.common import (AdminAdd, AdminAmt, AdminBC, AdminFind, AdminFJ,
                             AdminSet, maybe_dispatch, fire_and_forget, log)
from utils import parse_int, fmt_tom, esc, PLAN_LABELS

PAGE_SIZE = 5


def build(cfg, db):
    r = Router()

    def is_admin(uid) -> bool:
        return uid == cfg.admin_id

    async def guard(cb: CallbackQuery) -> bool:
        if not is_admin(cb.from_user.id):
            await cb.answer("⛔ فقط ادمین", show_alert=True)
            return False
        return True

    # ---------- /panel ----------
    @r.message(Command("panel", "admin"))
    async def panel(m: Message, state: FSMContext):
        if not is_admin(m.from_user.id):
            return
        await state.clear()
        await m.answer(T.AD_WELCOME, reply_markup=K.admin_menu())

    @r.callback_query(F.data == "ad_home")
    async def ad_home(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        await state.clear()
        try:
            await cb.message.edit_text(T.AD_WELCOME, reply_markup=K.admin_menu())
        except Exception:
            await cb.message.answer(T.AD_WELCOME, reply_markup=K.admin_menu())
        await cb.answer()

    @r.callback_query(F.data == "ad_close")
    async def ad_close(cb: CallbackQuery):
        if not await guard(cb):
            return
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.answer()

    # ---------- آمار ----------
    @r.callback_query(F.data == "ad_stats")
    async def ad_stats(cb: CallbackQuery):
        if not await guard(cb):
            return
        s = await db.stats()
        await cb.message.answer(T.AD_STATS.format(**s), reply_markup=K.admin_back())
        await cb.answer()

    # ---------- رسیدها ----------
    @r.callback_query(F.data == "ad_receipts")
    async def ad_receipts(cb: CallbackQuery):
        if not await guard(cb):
            return
        rows = await db.pending_receipts()
        if not rows:
            await cb.message.answer("🧾 رسیدی در انتظار نیست.", reply_markup=K.admin_back())
            return await cb.answer()
        for x in rows[:10]:
            u = await db.user(x["user_id"])
            uname = f"@{u['username']}" if u and u["username"] else ""
            await cb.message.answer(
                f"🧾 رسید #{x['id']}\n👤 🆔 {x['user_id']} {uname}\n"
                f"🪙 {x['coins']} سکه | 💳 {fmt_tom(x['toman'])} تومان",
                reply_markup=K.receipt_kb(x["id"]))
        await cb.answer()

    @r.callback_query(F.data.startswith("rc_ok_"))
    async def rc_ok(cb: CallbackQuery):
        if not await guard(cb):
            return
        rid = parse_int(cb.data[6:])
        x = await db.receipt(rid)
        if not x or x["status"] != "pending":
            return await cb.answer("قبلاً بررسی شده", show_alert=True)
        await db.decide_receipt(rid, "approved")
        nb = await db.add_balance(x["user_id"], x["coins"], "buy", f"رسید #{rid}")
        try:
            await cfg.bot.send_message(x["user_id"], T.RECEIPT_OK.format(
                coins=x["coins"], balance=nb))
        except Exception:
            pass
        await cb.message.edit_text(f"✅ رسید #{rid} تأیید شد ({x['coins']} سکه واریز شد).")
        await cb.answer()

    @r.callback_query(F.data.startswith("rc_no_"))
    async def rc_no(cb: CallbackQuery):
        if not await guard(cb):
            return
        rid = parse_int(cb.data[6:])
        x = await db.receipt(rid)
        if not x or x["status"] != "pending":
            return await cb.answer("قبلاً بررسی شده", show_alert=True)
        await db.decide_receipt(rid, "rejected")
        try:
            await cfg.bot.send_message(x["user_id"], T.RECEIPT_NO)
        except Exception:
            pass
        await cb.message.edit_text(f"❌ رسید #{rid} رد شد.")
        await cb.answer()

    # ---------- کاربران ----------
    @r.callback_query(F.data == "ad_users")
    async def ad_users(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        await state.set_state(AdminFind.user)
        await cb.message.answer(T.AD_USERS_ASK)
        await cb.answer()

    @r.message(AdminFind.user)
    async def find_user(m: Message, state: FSMContext):
        raw = (m.text or "").strip()
        if raw.startswith("@"):
            u = await db.user_by_username(raw)
        else:
            uid = parse_int(raw)
            u = await db.user(uid) if uid else None
        if not u:
            return await m.answer(T.AD_USER_NF)
        await state.clear()
        await show_user_card(m, u)

    async def show_user_card(m: Message, u):
        act = await db.active_of(u["user_id"])
        if act:
            self_txt = f"✅ {PLAN_LABELS.get(act['plan'], act['plan'])} تا {act['expires_at'][:16]}"
        else:
            self_txt = "ندارد"
        await m.answer(T.AD_USER_CARD.format(
            uid=u["user_id"], uname=u["username"] or "-", fname=u["first_name"] or "-",
            balance=u["balance"], ban="⛔ بن" if u["banned"] else "عادی",
            self_txt=self_txt, refs=await db.ref_count(u["user_id"])),
            reply_markup=K.user_card_kb(u["user_id"]))

    @r.callback_query(F.data.startswith("adu_"))
    async def adu_actions(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        parts = cb.data.split("_")  # adu_c_uid / adu_d_uid / adu_b_uid / adu_e_uid / adu_r_uid
        action, uid = parts[1], parse_int(parts[2])
        u = await db.user(uid)
        if not u:
            return await cb.answer(T.AD_USER_NF, show_alert=True)
        if action == "c":
            await state.set_state(AdminAmt.val)
            await state.update_data(mode="charge", uid=uid)
            return await cb.message.answer("➕ چند سکه شارژ کنم؟ عدد بفرست:")
        if action == "d":
            await state.set_state(AdminAmt.val)
            await state.update_data(mode="deduct", uid=uid)
            return await cb.message.answer("➖ چند سکه کم کنم؟ عدد بفرست:")
        if action == "b":
            await db.set_ban(uid, 0 if u["banned"] else 1)
            await cb.answer("وضعیت بن تغییر کرد ✅", show_alert=True)
            return
        if action == "e":
            new_exp = await db.extend(uid, 7)
            if new_exp:
                try:
                    await cfg.bot.send_message(uid, T.AD_NOTIFY_EXTEND.format(days=7, expires=new_exp[:16]))
                except Exception:
                    pass
                return await cb.answer(f"✅ ۷ روز تمدید شد تا {new_exp[:16]}", show_alert=True)
            return await cb.answer("این کاربر سلف فعالی ندارد!", show_alert=True)
        if action == "r":
            act = await db.active_of(uid)
            if act:
                await db.revoke(act["id"])
                fire_and_forget(maybe_dispatch(cfg))
                try:
                    await cfg.bot.send_message(uid, T.AD_NOTIFY_REVOKE)
                except Exception:
                    pass
                return await cb.answer("⛔ سلف لغو شد", show_alert=True)
            return await cb.answer("سلف فعالی ندارد", show_alert=True)

    @r.message(AdminAmt.val)
    async def admin_amount(m: Message, state: FSMContext):
        val = parse_int(m.text)
        data = await state.get_data()
        if val is None or val <= 0:
            return await m.answer(T.AD_ASK_NUM)
        uid = data["uid"]
        if data["mode"] == "charge":
            nb = await db.add_balance(uid, val, "admin", "شارژ دستی ادمین")
        else:
            nb = await db.add_balance(uid, -val, "admin", "کسر دستی ادمین")
        await state.clear()
        await m.answer(f"{T.AD_DONE}\n💰 موجودی جدید {uid}: {nb} سکه")

    # ---------- سلف دستی ----------
    @r.callback_query(F.data == "ad_manual")
    async def ad_manual(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        await state.set_state(AdminAdd.uid)
        await cb.message.answer(T.AD_MANUAL)
        await cb.answer()

    @r.message(AdminAdd.uid)
    async def man_uid(m: Message, state: FSMContext):
        uid = parse_int(m.text)
        u = await db.user(uid) if uid else None
        if not u:
            return await m.answer(T.AD_MANUAL_USER_NF)
        await state.update_data(uid=uid)
        await state.set_state(AdminAdd.days)
        await m.answer(T.AD_MANUAL_DAYS)

    @r.message(AdminAdd.days)
    async def man_days(m: Message, state: FSMContext):
        days = parse_int(m.text)
        if not days or days <= 0:
            return await m.answer(T.AD_ASK_NUM)
        await state.update_data(days=days)
        await state.set_state(AdminAdd.session)
        await m.answer(T.AD_MANUAL_SESSION)

    @r.message(AdminAdd.session)
    async def man_session(m: Message, state: FSMContext):
        if (m.text or "").strip() == "لغو":
            await state.clear()
            return await m.answer("لغو شد.")
        s = (m.text or "").strip()
        if len(s) < 200 or " " in s:
            return await m.answer(T.AD_MANUAL_BAD)
        data = await state.get_data()
        uid, days = data["uid"], data["days"]
        note = await db.sget("admin_note", "")
        await db.add_activation(uid, enc_session(s), "", "manual", days, note)
        await state.clear()
        fire_and_forget(maybe_dispatch(cfg))
        from utils import now as _now
        from datetime import timedelta as _td
        exp = (_now() + _td(days=days)).strftime("%Y-%m-%d %H:%M")
        await m.answer(T.AD_MANUAL_DONE.format(uid=uid, expires=exp))
        try:
            await cfg.bot.send_message(uid, T.AD_NOTIFY_ACT.format(
                expires=exp, plan="دستی (ادمین)"))
        except Exception:
            pass

    def enc_session(s: str) -> str:
        from crypto import enc
        return enc(s)

    # ---------- گیت‌واوت ----------
    # ⚠️ ترتیب مهم: var_/vax_/vas_ باید قبل از va_ باشند وگرنه va_ آن‌ها را قورت می‌دهد
    @r.callback_query(F.data.in_({"ad_vault", "ad_vault0"}))
    async def ad_vault(cb: CallbackQuery):
        if not await guard(cb):
            return
        await show_vault(cb.message, 0)
        await cb.answer()

    @r.callback_query(F.data.startswith("vp_"))
    async def vault_page(cb: CallbackQuery):
        if not await guard(cb):
            return
        await show_vault(cb.message, parse_int(cb.data[3:]) or 0)
        await cb.answer()

    @r.callback_query(F.data.regexp(r"^var_\d+$"))
    async def vault_revoke(cb: CallbackQuery):
        if not await guard(cb):
            return
        aid = parse_int(cb.data[4:])
        row = await db.revoke(aid)
        if row:
            fire_and_forget(maybe_dispatch(cfg))
            try:
                await cfg.bot.send_message(row["user_id"], T.AD_NOTIFY_REVOKE)
            except Exception:
                pass
            await cb.answer("⛔ لغو شد", show_alert=True)
        else:
            await cb.answer("پیدا نشد", show_alert=True)

    @r.callback_query(F.data.regexp(r"^vax_\d+$"))
    async def vault_delete(cb: CallbackQuery):
        if not await guard(cb):
            return
        aid = parse_int(cb.data[4:])
        await db.revoke(aid)  # حذف منطقی
        await cb.answer("حذف (منطقی) شد", show_alert=True)

    @r.callback_query(F.data.regexp(r"^vas_\d+$"))
    async def vault_show_again(cb: CallbackQuery):
        if not await guard(cb):
            return
        await _show_item(cb, parse_int(cb.data[4:]))
        await cb.answer()

    @r.callback_query(F.data.regexp(r"^va_\d+$"))
    async def vault_item(cb: CallbackQuery):
        if not await guard(cb):
            return
        await _show_item(cb, parse_int(cb.data[3:]))
        await cb.answer()

    async def _show_item(cb: CallbackQuery, aid: int):
        cur = next((a for a in await db.all_activations() if a["id"] == aid), None)
        if not cur:
            return await cb.answer("پیدا نشد", show_alert=True)
        await cb.message.answer(T.AD_VAULT_SHOW.format(
            aid=aid, uid=cur["user_id"], phone=cur["phone"] or "—",
            plan=PLAN_LABELS.get(cur["plan"], cur["plan"]),
            expires=cur["expires_at"][:16], status=cur["status"],
            session=dec(cur["session_enc"]) or "(خطای رمزگشایی)"),
            reply_markup=K.vault_item_kb(aid))

    async def show_vault(msg, page: int):
        rows = await db.all_activations()
        n = len(rows)
        if n == 0:
            return await msg.answer(T.AD_VAULT_EMPTY, reply_markup=K.admin_back())
        pages = (n + PAGE_SIZE - 1) // PAGE_SIZE
        page = max(0, min(page, pages - 1))
        chunk = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        await msg.answer(T.AD_VAULT_HEAD.format(n=n, page=page + 1, pages=pages),
                         reply_markup=K.vault_kb(chunk, page, pages))

    # ---------- کیف پول ادمین ----------
    @r.callback_query(F.data == "ad_wallet")
    async def ad_wallet(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        bal = await db.balance(cfg.admin_id)
        await cb.message.answer(
            f"💸 کیف پول ادمین\n\n💰 موجودی: {fmt_tom(bal)} سکه\n\n"
            "برای انتقال، دکمه زیر 👇",
            reply_markup=K.kb([[("💸 انتقال سکه", "cb_transfer")], [("🔄 بازگشت", "ad_home")]]))
        await cb.answer()

    # ---------- عضویت اجباری ----------
    @r.callback_query(F.data == "ad_force")
    async def ad_force(cb: CallbackQuery):
        if not await guard(cb):
            return
        chs = await db.channels()
        lst = "\n".join(f"{i + 1}. {c['title']} ({c['id']})" for i, c in enumerate(chs)) or "—"
        await cb.message.answer(T.AD_FORCE.format(
            on="✅ روشن" if await db.force_on() else "❌ خاموش",
            n=len(chs), list=lst),
            reply_markup=K.force_admin_kb(await db.force_on(), len(chs)))
        await cb.answer()

    @r.callback_query(F.data == "fj_toggle")
    async def fj_toggle(cb: CallbackQuery):
        if not await guard(cb):
            return
        await db.sset("force_on", "0" if await db.force_on() else "1")
        await cb.answer("تغییر کرد ✅", show_alert=True)

    @r.callback_query(F.data == "fj_add")
    async def fj_add(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        await state.set_state(AdminFJ.add)
        await cb.message.answer(T.AD_FORCE_ASK)
        await cb.answer()

    @r.message(AdminFJ.add)
    async def fj_add_save(m: Message, state: FSMContext):
        raw = (m.text or "").strip()
        chs = await db.channels()
        if len(chs) >= 5:
            await state.clear()
            return await m.answer(T.AD_FORCE_FULL)
        try:
            chat = await cfg.bot.get_chat(raw)
            link = f"https://t.me/{chat.username}" if chat.username else \
                (await cfg.bot.create_chat_invite_link(chat.id)).invite_link
            chs.append({"id": chat.id, "title": chat.title or chat.first_name or str(chat.id),
                        "link": link})
            await db.set_channels(chs)
            await state.clear()
            await m.answer(f"✅ اضافه شد: {chat.title}")
        except Exception:
            await m.answer(T.AD_FORCE_BAD)

    @r.callback_query(F.data == "fj_rm")
    async def fj_rm(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        chs = await db.channels()
        if not chs:
            return await cb.answer("لیست خالی است", show_alert=True)
        await state.set_state(AdminFJ.rm)
        lst = "\n".join(f"{i + 1}. {c['title']}" for i, c in enumerate(chs))
        await cb.message.answer(T.AD_FORCE_RM_ASK.format(list=lst))
        await cb.answer()

    @r.message(AdminFJ.rm)
    async def fj_rm_save(m: Message, state: FSMContext):
        idx = parse_int(m.text)
        chs = await db.channels()
        if idx is None or not (1 <= idx <= len(chs)):
            return await m.answer(T.AD_FORCE_RM_ASK.format(
                list="\n".join(f"{i + 1}. {c['title']}" for i, c in enumerate(chs))))
        removed = chs.pop(idx - 1)
        await db.set_channels(chs)
        await state.clear()
        await m.answer(f"🗑 حذف شد: {removed['title']}")

    # ---------- پیام همگانی ----------
    @r.callback_query(F.data == "ad_bcast")
    async def ad_bcast(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        await state.set_state(AdminBC.msg)
        await cb.message.answer(T.AD_BCAST_ASK)
        await cb.answer()

    @r.message(AdminBC.msg)
    async def bcast_preview(m: Message, state: FSMContext):
        BCAST_LAST["chat"] = m.chat.id
        BCAST_LAST["mid"] = m.message_id
        n = len(await db.all_users())
        await m.answer(T.AD_BCAST_CONFIRM.format(n=n), reply_markup=K.broadcast_confirm())

    @r.callback_query(F.data == "bc_go")
    async def bcast_go(cb: CallbackQuery):
        if not await guard(cb):
            return
        if not BCAST_LAST:
            return await cb.answer("پیامی ثبت نشده", show_alert=True)
        await cb.answer("شروع ارسال...")
        ok = fail = 0
        for u in await db.all_users():
            try:
                await cfg.bot.copy_message(u["user_id"], BCAST_LAST["chat"], BCAST_LAST["mid"])
                ok += 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.04)
        await cb.message.answer(T.AD_BCAST_DONE.format(ok=ok, fail=fail))

    # ---------- تنظیمات ----------
    @r.callback_query(F.data == "ad_settings")
    async def ad_settings(cb: CallbackQuery):
        if not await guard(cb):
            return
        keys = ["coin_price", "min_buy", "activation_cost", "initial_days", "daily_renew",
                "card_number", "card_owner", "plan_2m_price", "plan_4m_price",
                "min_transfer", "max_transfer", "daily_cap", "ref_reward", "ref_gift",
                "admin_note"]
        lines = [f"• {k} = {await db.sget(k)}" for k in keys]
        await cb.message.answer(T.AD_SETTINGS_HEAD + "\n".join(lines),
                                reply_markup=K.settings_kb())
        await cb.answer()

    @r.callback_query(F.data.startswith("set_"))
    async def set_key(cb: CallbackQuery, state: FSMContext):
        if not await guard(cb):
            return
        key = cb.data[4:]
        await state.set_state(AdminSet.val)
        await state.update_data(key=key)
        await cb.message.answer(T.AD_SET_ASK.format(key=key))
        await cb.answer()

    @r.message(AdminSet.val)
    async def set_val(m: Message, state: FSMContext):
        val = (m.text or "").strip()
        data = await state.get_data()
        key = data.get("key")
        if not key or not val:
            return await m.answer("مقدار نامعتبر است.")
        await db.sset(key, val)
        await state.clear()
        await m.answer(T.AD_SET_DONE.format(key=key, val=esc(val)))

    return r


# پیام آخرِ همگانی برای کپی
BCAST_LAST = {}