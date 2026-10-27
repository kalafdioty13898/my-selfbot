# -*- coding: utf-8 -*-
"""رگرسیون فیکس‌های سلف — سکوت پیوی، فیلتر پیوی، گیت خاموشی، کش آنتی‌حذف، گرم‌سازی.
اجرا: python test_pv_fixes.py
"""
import asyncio
import sys
import time

from framework import Bot, Ctx
import modules


class FakeCfg:
    sudo = ""
    prefix = "!"
    tz = "Asia/Tehran"
    storage_id = None
    enc_key = ""
    shop_poll = 60
    branch = "main"


class FakeStore:
    def __init__(self):
        self._accs = {}
        self.cfg = FakeCfg()

    def acc(self, key):
        from storage import default_account
        return self._accs.setdefault(str(key), default_account())

    def accs(self):
        return self._accs

    def save(self, *a, **kw):
        pass


class FakeMsg:
    def __init__(self, id=1, text="", out=False, sender_id=999, sender=None, media=None):
        self.id = id
        self.raw_text = text
        self.out = out
        self.sender_id = sender_id
        self.sender = sender
        self.media = media
        self.action = None
        self.mentioned = False
        self.reply_to_msg_id = None
        self.deleted = False

    async def delete(self, *a, **kw):
        self.deleted = True
        return True

    async def download_media(self, *a, **kw):
        return None


class FakeEvent:
    def __init__(self, msg, chat_id=100, private=False, group=False, chat=None):
        self.message = msg
        self.chat_id = chat_id
        self.is_private = private
        self.is_group = group
        self.chat = chat
        self.replies = []

    async def reply(self, text=None, **kw):
        m = FakeMsg(id=len(self.replies) + 100, text=text)
        self.replies.append(m)
        return m

    async def get_reply_message(self):
        return None

    async def get_chat(self):
        return self.chat


class FakeSender:
    def __init__(self, uid, bot=False):
        self.id = uid
        self.bot = bot
        self.first_name = "کاربر"
        self.last_name = ""
        self.username = None


class FakeAdmins:
    def __init__(self, ids):
        self.ids = ids

    async def is_admin(self, client, chat_id, uid):
        return uid in self.ids


class FakeClient:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat, text=None, **kw):
        self.sent.append((chat, text))
        return FakeMsg(id=len(self.sent) + 500, text=text)

    async def edit_message(self, chat, mid, text=None, **kw):
        return FakeMsg(id=mid, text=text)

    async def forward_messages(self, dest, src_chat, msg_id, **kw):
        return FakeMsg(id=1)

    async def get_entity(self, x):
        return FakeSender(1)

    async def get_input_entity(self, x):
        return x


def new_ctx(uid=777):
    client = FakeClient()
    ctx = Ctx(client, FakeStore(), FakeCfg(), "1")
    ctx.me = FakeSender(uid)
    ctx.me_id = uid
    ctx.admins = FakeAdmins(set())
    return ctx


def build():
    bot = Bot()
    for mod in modules.MODULES:
        mod(bot)
    return bot


def pv_event(text, sender_id=555, out=False, chat_id=1111):
    msg = FakeMsg(id=10, text=text, out=out, sender_id=None if out else sender_id,
                  sender=None if out else FakeSender(sender_id))
    return FakeEvent(msg, chat_id=chat_id, private=True)


PASS = []


def ok(name, cond):
    PASS.append((name, bool(cond)))
    print(("✅" if cond else "❌"), name)


async def main():
    uid = 777

    # ---------- ۱) سکوت پیوی ----------
    bot = build()
    ctx = new_ctx(uid)
    ctx.acc["mute"]["1111"] = {"on": True, "until": 0}

    ev = pv_event("سلام", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx)
    ok("سکوت پیوی: پیام طرف حذف شد", ev.message.deleted)

    ev = pv_event("سلام", sender_id=555, out=True, chat_id=1111)
    await bot.dispatch(ev, ctx)
    ok("سکوت پیوی: پیام خودت حذف نشد", not ev.message.deleted)

    ev = pv_event("سلام", sender_id=uid, chat_id=1111)
    await bot.dispatch(ev, ctx)
    ok("سکوت پیوی: پیام sudo حذف نشد", not ev.message.deleted)

    # چت دیگر — سکوت ندارد
    ev = pv_event("سلام", sender_id=555, chat_id=2222)
    await bot.dispatch(ev, ctx)
    ok("سکوت فقط همان پیوی", not ev.message.deleted)

    # منقضی‌شده
    ctx.acc["mute"]["3333"] = {"on": True, "until": time.time() - 10}
    ev = pv_event("سلام", sender_id=555, chat_id=3333)
    await bot.dispatch(ev, ctx)
    ok("سکوت موقت منقضی: حذف نشد", not ev.message.deleted)
    ok("سکوت موقت منقضی: از تنظیمات پاک شد", "3333" not in ctx.acc["mute"])

    # ---------- ۲) فیلتر در پیوی ----------
    ctx2 = new_ctx(uid)
    ctx2.acc["filters"]["1111"] = {"words": ["تبلیغ"], "allow": []}
    ev = pv_event("این یه تبلیغ است", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx2)
    ok("فیلتر پیوی: پیام حاوی کلمه حذف شد", ev.message.deleted)

    ev = pv_event("سلام خوبی", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx2)
    ok("فیلتر پیوی: پیام عادی حذف نشد", not ev.message.deleted)

    # ---------- ۳) متن/دستور سکوت در پیوی ----------
    ctx3 = new_ctx(uid)
    ev = pv_event("سکوت روشن", out=True, chat_id=4444)
    await bot.dispatch(ev, ctx3)
    ok("سکوت روشن در پیوی ثبت شد", ctx3.acc["mute"].get("4444", {}).get("on") is True)
    ok("متن جواب پیوی‌آگاه است", any("پیوی" in (r.raw_text or "") for r in ev.replies))

    ev = pv_event("سکوت خاموش", out=True, chat_id=4444)
    await bot.dispatch(ev, ctx3)
    ok("سکوت خاموش در پیوی", not ctx3.acc["mute"].get("4444"))

    # ---------- ۴) سکوت گروه (رگرسیون قدیمی) ----------
    ctx4 = new_ctx(uid)
    ctx4.acc["mute"]["-100555"] = {"on": True, "until": 0}
    ev = FakeEvent(FakeMsg(id=1, text="سلام", sender_id=555,
                           sender=FakeSender(555)), chat_id=-100555, group=True)
    await bot.dispatch(ev, ctx4)
    ok("سکوت گروه: پیام عضو عادی حذف شد", ev.message.deleted)

    ctx4.admins = FakeAdmins({555})
    ev = FakeEvent(FakeMsg(id=2, text="سلام", sender_id=555,
                           sender=FakeSender(555)), chat_id=-100555, group=True)
    await bot.dispatch(ev, ctx4)
    ok("سکوت گروه: ادمین حذف نشد", not ev.message.deleted)

    # ---------- ۵) گیت خاموشی ----------
    ctx5 = new_ctx(uid)
    ctx5.acc["off"]["all"] = True
    ev = pv_event("سلام", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx5)
    ok("سلف همگانی خاموش: منشی دیگر جواب نمی‌دهد", not ctx5.client.sent)

    # دستور غیر-always خودم (out) با خاموشی همگانی کار کند
    ev = pv_event("اسم ها", out=True, chat_id=1111)
    await bot.dispatch(ev, ctx5)
    ok("خاموشی همگانی: دستور خودم کار می‌کند", len(ev.replies) > 0)

    # دستور غیر-always سودو با خاموشی بلاک بماند
    ctx6 = new_ctx(uid)
    ctx6.cfg.sudo = "999"
    ctx6.acc["off"]["all"] = True
    ev = pv_event("اسم ها", sender_id=999, chat_id=1111)
    await bot.dispatch(ev, ctx6)
    ok("خاموشی همگانی: دستور سودو بلاک است", len(ev.replies) == 0)

    # !on حتی با خاموشی برای دیگران آزاد بماند
    ev = pv_event("!allon", sender_id=999, chat_id=1111)
    await bot.dispatch(ev, ctx6)
    ok("!allon انگلیسی همیشه آزاد", ctx6.acc["off"]["all"] is False)

    # سلف خاموش چت → منشی همان چت جواب ندهد ولی پیوی دیگر جواب بدهد
    ctx7 = new_ctx(uid)
    ctx7.acc["sec"]["on"] = True
    ctx7.acc["sec"]["text"] = "منشی هستم NAME"
    ctx7.acc["off"]["chats"]["1111"] = True
    ev = pv_event("سلام", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx7)
    ok("سلف خاموش این چت: منشی جواب نداد", not ctx7.client.sent)
    ev = pv_event("سلام", sender_id=555, chat_id=2222)
    await bot.dispatch(ev, ctx7)
    ok("سلف خاموش این چت: پیوی دیگر جواب داد", len(ctx7.client.sent) == 1)

    # ---------- ۶) پاسخ سریع + خاموشی ----------
    ctx8 = new_ctx(uid)
    ctx8.acc["quick"]["سلام"] = {"type": "text", "content": "علیکم"}
    ctx8.acc["off"]["chats"]["1111"] = True
    ev = pv_event("سلام خوبی", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx8)
    ok("پاسخ سریع با خاموشی چت جواب نمی‌دهد", not ctx8.client.sent)
    ctx8.acc["off"]["chats"].pop("1111")
    ev = pv_event("سلام خوبی", sender_id=555, chat_id=1111)
    await bot.dispatch(ev, ctx8)
    ok("پاسخ سریع بدون خاموشی جواب می‌دهد", len(ctx8.client.sent) == 1)

    # ---------- ۷) کش آنتی‌حذف: ویرایش ریپلای به پیام خودت ----------
    ctx9 = new_ctx(uid)
    orig = FakeMsg(id=50, text="پیام خودم", sender_id=uid)
    ev_in = FakeEvent(orig, chat_id=1111, private=True)
    await bot.msg_hooks[0](ev_in, ctx9)  # _cache_msg اولین هوک مدیا/کش نیست — همه را بزن
    for h in bot.msg_hooks:
        await h(ev_in, ctx9)
    edited = FakeMsg(id=50, text="پیام ویرایش‌شده", sender_id=uid,
                     sender=FakeSender(uid))
    edited.reply_to_msg_id = 50
    ev_edit = FakeEvent(edited, chat_id=1111, private=True)
    for h in bot.edit_hooks:
        await h(ev_edit, ctx9)
    ok("آنتی‌حذف: ویرایش ریپلای به خودت گزارش شد (کلید کش دوتایی)",
       any("ویرایش" in (t or "") for _, t in ctx9.client.sent))

    # ---------- ۸) گرم‌سازی کش ----------
    import bot as botmod
    ok("warm_entity_cache وجود دارد", hasattr(botmod, "warm_entity_cache"))
    try:
        await asyncio.wait_for(botmod.warm_entity_cache(FakeClient(), "t"), 5)
        ok("warm_entity_cache اجرا می‌شود", True)
    except Exception:
        ok("warm_entity_cache اجرا می‌شود", False)

    # ---------- جمع‌بندی ----------
    fails = [n for n, c in PASS if not c]
    print(f"\n{len(PASS) - len(fails)}/{len(PASS)} پاس")
    if fails:
        print("خراب:", fails)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
