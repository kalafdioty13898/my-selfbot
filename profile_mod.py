# -*- coding: utf-8 -*-
"""ماژول پروفایل‌گردان: چرخش خودکار اسم و بیو با متغیرهای زمان/تاریخ."""
from telethon.tl import functions, types

from framework import Bot
from utils import render_vars

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

    # ---------- تیک چرخش ----------
    @bot.tick_hook
    async def _rotate(ctx):
        import time as t
        if t.time() - state["last"] < ROTATE_MIN * 60:
            return
        state["last"] = t.time()
        acc = ctx.acc
        try:
            if acc["names_on"] and acc["names"]:
                name = render_vars(acc["names"][acc["name_i"] % len(acc["names"])],
                                   ctx.cfg.tz)[:64]
                acc["name_i"] = (acc["name_i"] + 1) % max(1, len(acc["names"]))
                await ctx.client(functions.account.UpdateProfileRequest(first_name=name))
            if acc["bios_on"] and acc["bios"]:
                bio = render_vars(acc["bios"][acc["bio_i"] % len(acc["bios"])],
                                  ctx.cfg.tz)[:70]
                acc["bio_i"] = (acc["bio_i"] + 1) % max(1, len(acc["bios"]))
                await ctx.client(functions.account.UpdateProfileRequest(about=bio))
            ctx.store.save()
        except Exception:
            pass
