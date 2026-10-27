# -*- coding: utf-8 -*-
"""رگرسیون قابلیت‌های جدید: قفل مدیا پیوی/گروه، زمان‌دار، روتر، منشی افلاین،
شیفت کاری، تایپ جادویی، پروفایل، هشدار ورود 777000، ارز، بازی گروهی.
اجرا: python test_new_features.py
"""
import asyncio
import datetime
import sys
import time

import modules
from framework import Bot, Ctx
from modules.games_mod import _kind_emoji
from modules.msg_mod import kind_match, msg_kind, parse_when
from modules.tools_mod import _toman, WMO
from utils import parse_shift


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


class FakeFull:
    def __init__(self):
        self.about = "بیو تست"
        self.common_chats_count = 2


class FakeFullResp:
    def __init__(self):
        self.full_user = FakeFull()


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
        self.sticker = self.voice = self.gif = self.video = None
        self.video_note = self.audio = self.photo = self.document = None
        self._fwd = None

    async def delete(self, *a, **kw):
        self.deleted = True
        return True

    async def download_media(self, *a, **kw):
        return "/tmp/fake.jpg"

    async def forward_to(self, dest, *a, **kw):
        self._fwd = dest
        return self


class FakeDice:
    def __init__(self, emoticon, value):
        self.emoticon = emoticon
        self.value = value


class FakeChat:
    def __init__(self, cid, title="چت"):
        self.id = cid
        self.title = title
        self.username = None


class FakeEvent:
    def __init__(self, msg, chat_id=100, private=False, group=False, chat=None):
        self.message = msg
        self.chat_id = chat_id
        self.is_private = private
        self.is_group = group
        self.is_reply = False
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
        self.first_name = "بازیکن"
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
        self.fwd = []
        self.files = []
        self.calls = []

    async def __call__(self, *a, **kw):
        self.calls.append(a)
        return FakeFullResp()

    async def send_message(self, chat, text=None, **kw):
        self.sent.append((chat, text))
        return FakeMsg(id=len(self.sent) + 500, text=text)

    async def send_file(self, chat, f, **kw):
        self.files.append((chat, f, kw))
        return FakeMsg(id=len(self.files) + 800)

    async def forward_messages(self, dest, src_chat, msg_id, **kw):
        self.fwd.append((dest, src_chat, msg_id))
        return FakeMsg(id=1)

    async def edit_message(self, chat, mid, text=None, **kw):
        return FakeMsg(id=mid, text=text)

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


def pv(msg, sender_id=555, out=False, chat_id=1111):
    return FakeEvent(FakeMsg(id=10, text=msg, out=out,
                             sender_id=None if out else sender_id,
                             sender=None if out else FakeSender(sender_id)),
                     chat_id=chat_id, private=True)


PASS = []


def ok(name, cond):
    PASS.append((name, bool(cond)))
    print(("✅" if cond else "❌"), name)


def media_msg(kind, sender_id=555, chat_id=1111, id=10, group=False):
    m = FakeMsg(id=id, text="", sender_id=sender_id, sender=FakeSender(sender_id))
    setattr(m, kind, True)
    return FakeEvent(m, chat_id=chat_id, private=not group, group=group)


async def main():
    uid = 777

    # ============ ۱) قفل مدیا پیوی ============
    bot = build()
    ctx = new_ctx(uid)
    ctx.acc["mlock"]["pv"] = {"استیکر": True}
    ev = media_msg("sticker")
    await bot.dispatch(ev, ctx)
    ok("قفل استیکر پیوی: حذف شد", ev.message.deleted)

    ev = media_msg("voice")
    await bot.dispatch(ev, ctx)
    ok("قفل استیکر پیوی: وویس آزاد", not ev.message.deleted)

    ctx.acc["mlock"]["pv"] = {"استیکر": True, "وویس": True, "گیف": True,
                              "فیلم": True, "موزیک": True}
    for kind in ["voice", "gif", "video", "video_note", "audio"]:
        ev = media_msg(kind)
        await bot.dispatch(ev, ctx)
        ok(f"قفل همه مدیا پیوی: {kind} حذف شد", ev.message.deleted)

    # پیام متنی در پیوی قفل نداریم
    ev = pv("سلام", chat_id=2222)
    await bot.dispatch(ev, ctx)
    ok("قفل مدیا: متن آزاد", not ev.message.deleted)

    # ============ ۲) قفل مدیا گروه ============
    ctxg = new_ctx(uid)
    ctxg.acc["mlock"]["-1000"] = {"استیکر": True}
    ev = media_msg("sticker", chat_id=-1000, id=3, group=True)
    await bot.dispatch(ev, ctxg)
    ok("قفل استیکر گروه: عضو عادی حذف شد", ev.message.deleted)

    ctxg.admins = FakeAdmins({555})
    ev = media_msg("sticker", chat_id=-1000, id=4, group=True)
    await bot.dispatch(ev, ctxg)
    ok("قفل استیکر گروه: ادمین آزاد", not ev.message.deleted)

    # دستور قفل در پیوی → تنظیم سراسری پیوی
    ctxm = new_ctx(uid)
    ev = pv("قفل گیف روشن", out=True)
    await bot.dispatch(ev, ctxm)
    ok("دستور قفل گیف در پیوی → mlock.pv", ctxm.acc["mlock"]["pv"].get("گیف") is True)

    ev = pv("قفل گیف خاموش", out=True)
    await bot.dispatch(ev, ctxm)
    ok("قفل گیف خاموش", ctxm.acc["mlock"]["pv"].get("گیف") is False)

    # ============ ۳) زمان‌دار ============
    ts, human, rest = parse_when("3 ساعت و 20 دقیقه یادت نره")
    ok("زمان‌دار مدت مرکب", ts and 11990 < ts - time.time() < 12010 and rest == "یادت نره")
    ts, human, rest = parse_when("21:30 پیام شب")
    ok("زمان‌دار ساعت HH:MM", ts is not None and rest == "پیام شب")
    ts, human, rest = parse_when("0 ساعت متن")
    ok("زمان‌دار رد زمان صفر", ts is None)
    ts, human, rest = parse_when("فقط متن بدون زمان")
    ok("زمان‌دار بدون زمان → خطا", ts is None)
    ts, human, rest = parse_when("5")
    ok("زمان‌دار بدون متن → خطا", ts is None)

    # ============ ۴) فیلتر روتر ============
    class M:
        pass
    m = M()
    m.sticker = m.voice = m.gif = m.video = m.video_note = None
    m.audio = m.photo = m.document = m.media = None
    m.raw_text = "سلام"
    ok("msg_kind متن", msg_kind(m) == "text")
    m.photo = True
    ok("msg_kind عکس", msg_kind(m) == "photo")
    ok("kind_match همه", kind_match(m, ["all"]))
    ok("kind_match فیلتر متن جلوی عکس", not kind_match(m, ["text"]))
    ok("kind_match عکس قبول", kind_match(m, ["text", "photo"]))
    m.photo = None
    m.media = object()
    ok("msg_kind ناشناخته", msg_kind(m) == "other")
    ok("ناشناخته فقط با همه", not kind_match(m, ["text"]) and kind_match(m, ["all"]))

    # ============ ۵) روتر ============
    ctxr = new_ctx(uid)
    ev = pv("روتر جدید @ک analizar", out=True, chat_id=-100999)
    ev.chat = FakeChat(-100999, "گروه من")
    await bot.dispatch(ev, ctxr)
    rts = ctxr.acc["routers"]
    ok("روتر جدید ثبت شد", len(rts) == 1 and rts[0]["src"] == "-100999")
    ok("روتر فیلتر پیش‌فرض همه", rts[0]["kinds"] == ["all"])

    # فوروارد متن با فیلتر متن
    ctxr.acc["routers"][0]["kinds"] = ["text"]
    r = ctxr.acc["routers"][0]
    ev = pv("سلام روتر", sender_id=555, chat_id=-100999, )
    await bot.dispatch(ev, ctxr)
    ok("روتر: متن فوروارد شد", ev.message._fwd == r["dst"])

    ev = media_msg("sticker", chat_id=-100999, id=77)
    await bot.dispatch(ev, ctxr)
    ok("روتر: استیکر با فیلتر متن فوروارد نشد", ev.message._fwd is None)

    # پیام خودت فوروارد نشود (ضد حلقه)
    ev = pv("سلام من", out=True, chat_id=-100999)
    await bot.dispatch(ev, ctxr)
    ok("روتر: پیام خودت فوروارد نشد", ev.message._fwd is None)

    # ============ ۶) منشی افلاین ============
    ctxo = new_ctx(uid)
    s = ctxo.acc["sec"]
    s["off_on"] = True
    s["off_msg"] = {"type": "text", "content": "فعلا نیستم"}
    s["cool"] = 5
    ctxo.last_activity = time.time() - 1000  # ده‌ها دقیقه بی‌فعال
    ev = pv("سلام", chat_id=3333)
    await bot.dispatch(ev, ctxo)
    ok("منشی افلاین: پیام ذخیره‌شده ارسال شد",
       any("فعلا نیستم" in (t or "") for _, t in ctxo.client.sent))

    # کولداون: پیام دوم فوری دوباره جواب نمی‌گیرد
    ev = pv("دوباره سلام", chat_id=3333)
    await bot.dispatch(ev, ctxo)
    ok("منشی افلاین: کولداون کاربر", len(ctxo.client.sent) == 1)

    # کاربر فعال (تازه پیام داده) → پاسخ افلاین نمی‌آید
    ctxa = new_ctx(uid)
    ctxa.acc["sec"]["off_on"] = True
    ctxa.acc["sec"]["off_msg"] = {"type": "text", "content": "فعلا نیستم"}
    ev = pv("سلام", chat_id=4444)  # last_activity همان لحظه است
    await bot.dispatch(ev, ctxa)
    ok("منشی افلاین: کاربر فعال جواب نمی‌گیرد", not ctxa.client.sent)

    # پاسخ افلاین مدیایی (فرستنده متمایز — last_reply ماژول مشترک است)
    ctxf = new_ctx(uid)
    ctxf.last_activity = time.time() - 1000
    ctxf.acc["sec"]["off_on"] = True
    ctxf.acc["sec"]["off_msg"] = {"type": "media", "chat": "me", "msg": 42}
    ev = pv("سلام", sender_id=561, chat_id=5555)
    await bot.dispatch(ev, ctxf)
    ok("منشی افلاین: مدیا فوروارد شد",
       ctxf.client.fwd and ctxf.client.fwd[0][0] == 561 and ctxf.client.fwd[0][2] == 42)

    # تنظیم با ریپلی (متن)
    ctxs = new_ctx(uid)
    evs = FakeEvent(FakeMsg(id=9, text="پیام هدف", out=True, sender_id=uid,
                            sender=FakeSender(uid)), chat_id=1, private=True)
    await bot.dispatch(evs, ctxs)

    # مهاجرت حالت قدیمی offline
    from storage import default_account, norm_sec
    old = default_account()
    old["sec"]["mode"] = "offline"
    old["sec"]["text"] = "پیام قدیمی"
    norm_sec(old["sec"])
    ok("مهاجرت منشی افلاین قدیمی", old["sec"]["mode"] == "all"
       and old["sec"]["off_on"] is True
       and old["sec"]["off_msg"]["content"] == "پیام قدیمی")

    # ============ ۷) شیفت کاری ============
    ok("شیفت 9 تا 18", parse_shift("9 تا 18") == (540, 1080))
    ok("شیفت 9:30 تا 21:30", parse_shift("9:30 تا 21:30") == (570, 1290))
    ok("شیفت نامعتبر", parse_shift("25 تا 30") is None)
    ok("شیفت بی‌فرمت", parse_shift("هرچی") is None)

    import utils as _u
    real_now = _u.now
    _u.now = lambda tz=None: datetime.datetime(2026, 1, 1, 23, 30)
    ok("شیفت شب: 22 تا 6 در 23:30 روشن",
       _u.in_shift({"from": 22 * 60, "to": 6 * 60}))
    ok("شیفت روز: 9 تا 18 در 23:30 خاموش",
       not _u.in_shift({"from": 9 * 60, "to": 18 * 60}))
    _u.now = lambda tz=None: datetime.datetime(2026, 1, 1, 10, 0)
    ok("شیفت روز: 9 تا 18 در 10:00 روشن",
       _u.in_shift({"from": 9 * 60, "to": 18 * 60}))
    _u.now = real_now

    # بیرون شیفت → پیام «خارج از ساعت کاری»
    import modules.secretary as secmod
    real_in_shift = secmod.in_shift
    secmod.in_shift = lambda sh, tz=None: False
    ctxh = new_ctx(uid)
    s = ctxh.acc["sec"]
    s["on"] = True
    s["text"] = "جواب منشی"
    s["shift"] = {"from": 540, "to": 1080}
    ev = pv("سلام", sender_id=571, chat_id=6666)
    await bot.dispatch(ev, ctxh)
    ok("شیفت: بیرون شیفت پیام ساعت کاری",
       any("خارج از ساعت کاری" in (t or "") for _, t in ctxh.client.sent))
    ok("شیفت: جواب عادی منشی نیامد",
       not any("جواب منشی" in (t or "") for _, t in ctxh.client.sent))
    secmod.in_shift = real_in_shift

    # ============ ۸) تایپ جادویی ============
    from utils import typing_then
    ctxt = new_ctx(uid)
    res = await typing_then(ctxt, 1, lambda: ctxt.client.send_message(1, "سلام"))
    ok("تایپ جادویی: بدون client.action هم ارسال می‌شود", res is not None)
    ctxt.acc["sec"]["typing"] = False
    res = await typing_then(ctxt, 1, lambda: ctxt.client.send_message(1, "سلام۲"))
    ok("تایپ جادویی خاموش: مستقیم ارسال", res is not None)

    # ============ ۹) پروفایل ============
    ctxp = new_ctx(uid)
    ev = FakeEvent(FakeMsg(id=5, text="پروفایل @ali", out=True, sender_id=uid,
                           sender=FakeSender(uid)), chat_id=1, private=True)
    await bot.dispatch(ev, ctxp)
    ok("پروفایل: کارت مشخصات (بدون عکس)",
       any("آخرین بازدید" in (r.raw_text or "") and "بیو تست" in (r.raw_text or "")
           for r in ev.replies))

    # ============ ۱۰) هشدار ورود 777000 ============
    ctxl = new_ctx(uid)
    ev = FakeEvent(FakeMsg(id=6, text="New login from Windows",
                           sender_id=777000, sender=FakeSender(777000)),
                   chat_id=777000, private=True)
    await bot.dispatch(ev, ctxl)
    ok("هشدار ورود جدید به لاگ رفت",
       any("هشدار امنیتی" in (t or "") for _, t in ctxl.client.sent))
    # منشی به 777000 جواب ندهد (هشدار امنیتی core_mod ارسال می‌شود ولی منشی نه)
    ctxm2 = new_ctx(uid)
    ctxm2.acc["sec"]["on"] = True
    ctxm2.acc["sec"]["text"] = "منشی"
    ctxm2.acc["sec"]["mode"] = "all"
    ev = FakeEvent(FakeMsg(id=7, text="هرچی", sender_id=777000,
                           sender=FakeSender(777000)), chat_id=777000, private=True)
    await bot.dispatch(ev, ctxm2)
    ok("منشی به تلگرام رسمی جواب نمی‌دهد",
       not any("منشی" in (t or "") for _, t in ctxm2.client.sent))

    # ============ ۱۱) ارز ============
    ok("تومان دلار", _toman("2,705,650") == "270,565")
    ok("تومان گرم طلا", _toman("262429000") == "26,242,900")
    ok("WMO صاف", "صاف" in WMO[0])
    ok("WMO رعد و برق", any("رعد" in v for v in WMO.values()))

    # ============ ۱۲) بازی گروهی ============
    ok("کد بازی سکه", _kind_emoji("سکه") == "🪙")
    ok("کد بازی با پسوند ها", _kind_emoji("تاس ها") == "🎲")
    ok("کد بازی نامعتبر", _kind_emoji("چیزی") is None)

    ctxg2 = new_ctx(uid)
    ev = FakeEvent(FakeMsg(id=8, text="بازی تاس", out=True, sender_id=uid,
                           sender=FakeSender(uid)), chat_id=-100777, group=True)
    await bot.dispatch(ev, ctxg2)
    ok("بازی گروهی: شروع شد",
       len(ctxg2.client.files) == 1 and len(ev.replies) >= 1)

    # ۱۰ بازیکن → پایان خودکار + رتبه‌بندی
    for i in range(1, 11):
        m = FakeMsg(id=100 + i, text="", sender_id=5000 + i,
                    sender=FakeSender(5000 + i))
        m.media = FakeDice("🎲", i % 6 + 1)
        evd = FakeEvent(m, chat_id=-100777, group=True)
        for h in bot.msg_hooks:
            await h(evd, ctxg2)
    ok("بازی گروهی: نتیجه بعد از ۱۰ نفر اعلام شد",
       any("نتیجه بازی" in (t or "") for _, t in ctxg2.client.sent))
    ok("بازی گروهی: اعلام برنده",
       any("برنده" in (t or "") for _, t in ctxg2.client.sent))

    # لغو بازی وقتی بازی نیست
    ev = FakeEvent(FakeMsg(id=99, text="لغو بازی", out=True, sender_id=uid,
                           sender=FakeSender(uid)), chat_id=-100777, group=True)
    await bot.dispatch(ev, ctxg2)
    ok("لغو بازی بدون بازی", any("فعالی نیست" in (r.raw_text or "") for r in ev.replies))

    # ============ ۱۳) وضعیت جدید ============
    ctxst = new_ctx(uid)
    ev = pv("وضعیت", out=True, chat_id=1)
    await bot.dispatch(ev, ctxst)
    st = "\n".join(r.raw_text or "" for r in ev.replies)
    ok("وضعیت: خط روتر/قفل مدیا", "روتر" in st and "قفل مدیا" in st)
    ok("وضعیت: خط منشی جدید", "پاسخ افلاین" in st and "شیفت" in st)

    fails = [n for n, c in PASS if not c]
    print(f"\n{len(PASS) - len(fails)}/{len(PASS)} پاس")
    if fails:
        print("خراب:", fails)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
