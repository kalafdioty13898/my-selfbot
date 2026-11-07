# -*- coding: utf-8 -*-
"""ماژول نقل‌قول‌ساز: روی هر پیام ریپلی کن → کارت عکسی خوشگل با اسم و عکس گوینده ساخته می‌شود.

متن فارسی با فونت وزیرمتن + arabic_reshaper + python-bidi درست رندر می‌شود
(PIL مستقیم RTL نمی‌فهمد). کارت به شکل عکس (نه فایل) به همان پیام ریپلی می‌شود."""
import datetime
import io
import os
import re

from framework import Bot
from utils import to_jalali

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "fonts")
_fonts = {}

# کاراکترهایی که فونت متنی ندارند (ایموجی و سمبل‌ها) از رندر حذف می‌شوند؛ نیم‌فاصله می‌ماند
_STRIP_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0000200D\U00002190-\U000021FF"
    "\U00002700-\U000027BF\u2049\u203C\u2122\u2139]"
)
MAX_TEXT = 1200
MAX_LINES = 12


def _font(name, size):
    from PIL import ImageFont
    key = (name, size)
    if key not in _fonts:
        path = os.path.join(_FONT_DIR, f"Vazirmatn-{name}.ttf")
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def _clean(text):
    """ایموجی‌ها حذف؛ نیم‌فاصله و خطوط حفظ."""
    text = _STRIP_RE.sub("", text or "")
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _shape(line):
    """خط فارسی/عربی → شکل حروف + ترتیب بصری برای PIL."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(line))
    except Exception:
        return line


def _wrap(draw, text, font, max_w):
    """شکستن متن به خط‌ها با اندازه‌گیری واقعی؛ خروجی خط‌های شکل‌گرفته برای رندر."""
    out = []
    for logical in text.split("\n"):
        words = logical.split()
        if not words:
            continue
        cur = words[0]
        for w in words[1:]:
            trial = cur + " " + w
            if draw.textlength(_shape(trial), font=font) <= max_w:
                cur = trial
            else:
                out.append(_shape(cur))
                cur = w
        out.append(_shape(cur))
    if len(out) > MAX_LINES:
        out = out[:MAX_LINES]
        out[-1] = out[-1][: max(1, len(out[-1]) - 3)].rstrip() + "..."
    return out


def _gradient(w, h, top, bottom):
    from PIL import Image
    img = Image.new("RGB", (w, h), top)
    d = ImageDraw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def ImageDraw(img):  # noqa: N802 — لایه نازک روی PIL تا ایمپورت بالای فایل سنگین نشود
    from PIL import ImageDraw as _ID
    return _ID.Draw(img)


def render_quote(name, text, avatar_bytes, date_str, accent=(255, 196, 71)):
    """کارت نقل‌قول → بایت‌های PNG."""
    from PIL import Image, ImageDraw, ImageOps
    W, PAD = 1080, 70
    f_name = _font("Bold", 44)
    f_body = _font("Regular", 46)
    f_small = _font("Regular", 30)
    body = _clean(text)[:MAX_TEXT]
    nm = _clean(name).strip() or "ناشناس"

    # اندازه کارت: اول روی کارت موقت اندازه می‌گیریم
    tmp = Image.new("RGB", (10, 10))
    td = ImageDraw.Draw(tmp)
    lines = _wrap(td, body, f_body, W - PAD * 2 - 20) if body else [""]
    line_h = 68
    AV = 120
    head_h = PAD + AV + 40
    body_h = len(lines) * line_h + 30
    foot_h = 110
    H = head_h + body_h + foot_h

    img = _gradient(W, H, (24, 24, 30), (40, 40, 52))
    d = ImageDraw.Draw(img)

    # نوار رنگی بالا
    d.rounded_rectangle([0, 0, W, 14], 7, fill=accent)

    # آواتار دایره‌ای
    cx, cy = PAD, head_h - 20
    av = None
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        except Exception:
            av = None
    if av is not None:
        av = ImageOps.fit(av, (AV * 4, AV * 4))
        mask = Image.new("L", (AV * 4, AV * 4), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, AV * 4, AV * 4], fill=255)
        mask = mask.resize((AV, AV))
        av = av.resize((AV, AV))
        img.paste(av, (cx, cy - AV), mask)
    else:
        d.ellipse([cx, cy - AV, cx + AV, cy], fill=accent)
        ch = _shape(nm[:1])
        d.text((cx + AV / 2, cy - AV / 2), ch, font=_font("Bold", 56),
               fill=(30, 30, 36), anchor="mm")

    # اسم + تاریخ
    tx = cx + AV + 30
    d.text((tx, cy - AV + 26), _shape(nm), font=f_name, fill=(255, 255, 255))
    d.text((tx, cy - AV + 92), date_str, font=f_small, fill=(150, 150, 160))

    # بدنه
    y = head_h + 20
    for ln in lines:
        d.text((W - PAD, y), ln, font=f_body, fill=(232, 232, 238), anchor="ra")
        y += line_h

    # فوتر
    d.text((W - PAD, H - 52), "star self", font=f_small, fill=(120, 120, 132), anchor="rm")
    d.line([(PAD, H - 78), (W - PAD, H - 78)], fill=(70, 70, 84), width=2)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    buf.name = "quote.png"
    return buf


def _fa_date(dt):
    try:
        jy, jm, jd = to_jalali(dt.date())
        return f"{jy}/{jm:02d}/{jd:02d} — {dt.strftime('%H:%M')}"
    except Exception:
        return dt.strftime("%Y/%m/%d %H:%M")


def setup(bot: Bot):
    @bot.cmd("نقل قول", "quote", cat="مدیا",
             help="نقل قول (ریپلی) — از پیام موردنظر یک کارت عکسی خوشگل با اسم و عکس گوینده بساز")
    async def _quote(event, ctx, args):
        if not event.is_reply:
            return await ctx.reply(event, "❗ روی پیام موردنظر ریپلی کن: نقل قول")
        src = await event.get_reply_message()
        text = (src.raw_text or "").strip() if src else ""
        if not text:
            return await ctx.reply(event, "❗ این پیام متنی ندارد — نقل قول فقط متن است")
        sender = None
        name = "ناشناس"
        try:
            sender = await src.get_sender()
        except Exception:
            sender = None
        if sender is not None:
            name = " ".join(x for x in [getattr(sender, "first_name", None),
                                        getattr(sender, "last_name", None)] if x)
            if not name:
                name = getattr(sender, "title", None) or "ناشناس"
        av = None
        try:
            av = await ctx.client.download_profile_photo(
                sender or src.sender_id, file=bytes)
        except Exception:
            av = None
        note = await ctx.reply(event, "🖼 در حال ساخت کارت...")
        try:
            buf = await _render_safe(name, text, av, _fa_date(
                src.date or datetime.datetime.now(datetime.timezone.utc)))
            await ctx.client.send_file(event.chat_id, buf, force_document=False,
                                       reply_to=src.id)
            await ctx.client.delete_messages(event.chat_id, [note.id])
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ ساخت کارت نشد: {e}")


async def _render_safe(name, text, av, date_str):
    """رندر در ترد جدا تا حلقه رویداد بلاک نشود."""
    import asyncio
    return await asyncio.to_thread(render_quote, name, text, av, date_str)
