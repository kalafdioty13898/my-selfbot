# -*- coding: utf-8 -*-
"""ماژول پروفایل‌گردان: چرخش خودکار اسم و بیو با متغیرهای زمان/تاریخ + ساعت زنده."""
from telethon.tl import functions, types

from framework import Bot
from utils import now, render_vars

ROTATE_MIN = 5  # هر چند دقیقه یک‌بار بچرخد


def setup(bot: Bot):
    state = {"last": 0}

    async def _list_items(event, ctx, key, title):
        items = ctx.acc[key]
        if not items:
            return await ctx.reply(event, f"ℹ️ هیچ {title}ای ثبت نشده")
        lines = [f"{i + 1}. {t}" for i, t in enumerate(items)]
        on = ctx.acc[key.replace("names", "names_on").replace("bios", "bios_on")]
        await ctx.reply(event, f"📌 {title}‌ها ({'🟢 فعال' if on else '🔴 خاموش'}):\n" + "\n".join(lines))

    async def _toggle(event, ctx, key, on, title):
        items = ctx.acc[key]
        if on and not items:
            return await ctx.reply(event, f"❗ اول یک {title} اضافه کن: {title} جدید متن")
        ctx.acc[key.replace("names", "names_on").replace("bios", "bios_on")] = on
        ctx.store.save()
        await ctx.reply(event, f"{'🟢' if on else '🔴'} چرخش {title} {'روشن' if on else 'خاموش'} شد")

    # ---------- اسم ----------
    @bot.cmd("اسم جدید", "nameadd", cat="پروفایل",
             help="اسم جدید <متن> — افزودن اسم به چرخه (با متغیر مثل: Time: TIME)")
    async def _name_add(event, ctx, args):
        if not args.strip():
            return await ctx.reply(event, "❗ مثال: اسم جدید Me time")
        ctx.acc["names"].append(args.strip())
        ctx.store.save()
        await ctx.reply(event, f"✅ اسم {len(ctx.acc['names'])} ذخیره شد")

    @bot.cmd("حذف اسم", "namedel", cat="پروفایل",
             help="حذف اسم <شماره> — حذف اسم از چرخه")
    async def _name_del(event, ctx, args):
        try:
            i = int(args.strip()) - 1
            ctx.acc["names"].pop(i)
            ctx.acc["name_i"] = 0
            ctx.store.save()
            await ctx.reply(event, "✅ حذف شد")
        except Exception:
            await ctx.reply(event, "❗ شماره معتبر بده (لیست: اسم ها)")

    bot.cmd("اسم ها", "names", cat="پروفایل",
            help="اسم ها — لیست اسم‌های چرخشی")(
        lambda e, c, a: _list_items(e, c, "names", "اسم"))
    bot.cmd("اسم روشن", "nameon", cat="پروفایل",
            help="اسم روشن — چرخش خودکار اسم فعال شود")(
        lambda e, c, a: _toggle(e, c, "names", True, "اسم"))
    bot.cmd("اسم خاموش", "nameoff", cat="پروفایل",
            help="اسم خاموش — چرخش خودکار اسم متوقف شود")(
        lambda e, c, a: _toggle(e, c, "names", False, "اسم"))

    # ---------- بیو ----------
    @bot.cmd("بیو جدید", "bioadd", cat="پروفایل",
             help="بیو جدید <متن> — افزودن بیو به چرخه")
    async def _bio_add(event, ctx, args):
        if not args.strip():
            return await ctx.reply(event, "❗ مثال: بیو جدید Time: TIME")
        ctx.acc["bios"].append(args.strip())
        ctx.store.save()
        await ctx.reply(event, f"✅ بیو {len(ctx.acc['bios'])} ذخیره شد")

    @bot.cmd("حذف بیو", "biodel", cat="پروفایل",
             help="حذف بیو <شماره> — حذف بیو از چرخه")
    async def _bio_del(event, ctx, args):
        try:
            i = int(args.strip()) - 1
            ctx.acc["bios"].pop(i)
            ctx.acc["bio_i"] = 0
            ctx.store.save()
            await ctx.reply(event, "✅ حذف شد")
        except Exception:
            await ctx.reply(event, "❗ شماره معتبر بده (لیست: بیو ها)")

    bot.cmd("بیو ها", "bios", cat="پروفایل",
            help="بیو ها — لیست بیوهای چرخشی")(
        lambda e, c, a: _list_items(e, c, "bios", "بیو"))
    bot.cmd("بیو روشن", "bioon", cat="پروفایل",
            help="بیو روشن — چرخش خودکار بیو فعال شود")(
        lambda e, c, a: _toggle(e, c, "bios", True, "بیو"))
    bot.cmd("بیو خاموش", "biooff", cat="پروفایل",
            help="بیو خاموش — چرخش خودکار بیو متوقف شود")(
        lambda e, c, a: _toggle(e, c, "bios", False, "بیو"))

    # ---------- ساعت زنده در اسم و بیو ----------
    async def _apply_clock(ctx):
        """نوشتن ساعت فعلی کنار اسم/بیو اصلی (پایه ذخیره‌شده)."""
        clk = ctx.acc["clk"]
        suffix = now(ctx.cfg.tz).strftime(" | ⌚ %H:%M")
        try:
            if clk["name_on"]:
                await ctx.client(functions.account.UpdateProfileRequest(
                    first_name=((clk["name_base"] or "") + suffix)[:64]))
            if clk["bio_on"]:
                await ctx.client(functions.account.UpdateProfileRequest(
                    about=((clk["bio_base"] or "") + suffix)[:70]))
        except Exception:
            pass

    @bot.cmd("ساعت اسم روشن", "clkname", cat="پروفایل",
             help="ساعت اسم روشن — ساعت زنده کنار اسمت (هر دقیقه آپدیت؛ تا وقتی روشنه چرخش اسم متوقفه)")
    async def _clk_name_on(event, ctx, args):
        clk = ctx.acc["clk"]
        if not clk["name_on"]:
            me = await ctx.client.get_me()
            clk["name_base"] = me.first_name or ""
            clk["name_on"] = True
            await _apply_clock(ctx)
        ctx.store.save()
        await ctx.reply(event, "⌚ ساعت زنده به اسم اضافه شد\n🔴 خاموش: ساعت اسم خاموش")

    @bot.cmd("ساعت اسم خاموش", "clknameoff", cat="پروفایل",
             help="ساعت اسم خاموش — حذف ساعت از اسم و برگشت اسم اصلی")
    async def _clk_name_off(event, ctx, args):
        clk = ctx.acc["clk"]
        if clk["name_on"]:
            clk["name_on"] = False
            try:
                await ctx.client(functions.account.UpdateProfileRequest(
                    first_name=clk["name_base"] or " "))
            except Exception:
                pass
            clk["name_base"] = ""
            ctx.store.save()
        await ctx.reply(event, "🔴 ساعت از اسم حذف شد و اسم اصلی برگشت")

    @bot.cmd("ساعت بیو روشن", "clkbio", cat="پروفایل",
             help="ساعت بیو روشن — ساعت زنده ته بیوت (هر دقیقه آپدیت؛ تا وقتی روشنه چرخش بیو متوقفه)")
    async def _clk_bio_on(event, ctx, args):
        clk = ctx.acc["clk"]
        if not clk["bio_on"]:
            try:
                full = await ctx.client(functions.users.GetFullUserRequest(ctx.me_id))
                clk["bio_base"] = (full.full_user.about or "").strip()
            except Exception:
                clk["bio_base"] = ""
            clk["bio_on"] = True
            await _apply_clock(ctx)
        ctx.store.save()
        await ctx.reply(event, "⌚ ساعت زنده به بیو اضافه شد\n🔴 خاموش: ساعت بیو خاموش")

    @bot.cmd("ساعت بیو خاموش", "clkbiooff", cat="پروفایل",
             help="ساعت بیو خاموش — حذف ساعت از بیو و برگشت بیو اصلی")
    async def _clk_bio_off(event, ctx, args):
        clk = ctx.acc["clk"]
        if clk["bio_on"]:
            clk["bio_on"] = False
            try:
                await ctx.client(functions.account.UpdateProfileRequest(
                    about=clk["bio_base"] or " "))
            except Exception:
                pass
            clk["bio_base"] = ""
            ctx.store.save()
        await ctx.reply(event, "🔴 ساعت از بیو حذف شد و بیو اصلی برگشت")

    clk_state = {"min": ""}

    @bot.tick_hook
    async def _clock_tick(ctx):
        """هر دقیقه یک‌بار ساعت اسم/بیو را آپدیت کند."""
        clk = ctx.acc["clk"]
        if not (clk["name_on"] or clk["bio_on"]):
            return
        m = now(ctx.cfg.tz).strftime("%H:%M")
        if m == clk_state["min"]:
            return
        clk_state["min"] = m
        await _apply_clock(ctx)

    # ---------- تیک چرخش ----------
    @bot.tick_hook
    async def _rotate(ctx):
        import time as t
        if t.time() - state["last"] < ROTATE_MIN * 60:
            return
        state["last"] = t.time()
        acc = ctx.acc
        clk = acc.get("clk", {})
        try:
            if acc["names_on"] and acc["names"] and not clk.get("name_on"):
                name = render_vars(acc["names"][acc["name_i"] % len(acc["names"])],
                                   ctx.cfg.tz)[:64]
                acc["name_i"] = (acc["name_i"] + 1) % max(1, len(acc["names"]))
                await ctx.client(functions.account.UpdateProfileRequest(first_name=name))
            if acc["bios_on"] and acc["bios"] and not clk.get("bio_on"):
                bio = render_vars(acc["bios"][acc["bio_i"] % len(acc["bios"])],
                                  ctx.cfg.tz)[:70]
                acc["bio_i"] = (acc["bio_i"] + 1) % max(1, len(acc["bios"]))
                await ctx.client(functions.account.UpdateProfileRequest(about=bio))
            ctx.store.save()
        except Exception:
            pass
