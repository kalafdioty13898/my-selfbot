# -*- coding: utf-8 -*-
"""هوش مصنوعی (Gemini) داخل سلف — پرسش/پاسخ.

کلید رایگان: aistudio.google.com/apikey → Create API key (نیاز به تحریم‌شکن).
ست کردن:   کلید هوش مصنوعی AIza...
پرسش:      هوش مصنوعی بهترین رستوران تهران؟   |   ai hello
مدل:       مدل هوش مصنوعی gemini-2.0-flash   (پیش‌فرض: gemini-2.5-flash)

کلید در دیتابیس خود اکانت ذخیره می‌شود و در جواب‌ها فقط ماسک‌شده نمایش
داده می‌شود؛ ست‌کردنش فقط از خودِ صاحب اکانت (out) قبول است.
"""
import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

from framework import Bot

log = logging.getLogger("selfbot")

DEFAULT_MODEL = "gemini-2.5-flash"
URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
       "{model}:generateContent?key={key}")
MAX_OUT = 3500
MAX_Q = 4000


def mask_key(k: str) -> str:
    k = (k or "").strip()
    if len(k) < 12:
        return "…"
    return k[:6] + "…" + k[-4:]


def _post_json(url: str, body: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


async def ask(key: str, model: str, text: str) -> str:
    """پرسش از Gemini — خطا: RuntimeError با پیام قابل‌فهم (تست: جایگزین می‌شود)."""
    url = URL.format(model=(model or "").strip() or DEFAULT_MODEL, key=key)
    body = {"contents": [{"parts": [{"text": text[:MAX_Q]}]}]}
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(None, _post_json, url, body)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        if e.code == 429:
            raise RuntimeError("سقف رایگان Gemini پر شد — کمی بعد دوباره امتحان کن")
        if e.code in (400, 403):
            raise RuntimeError("کلید یا درخواست رد شد: " + (detail or f"HTTP {e.code}"))
        raise RuntimeError(f"Gemini HTTP {e.code}: {detail[:200]}")
    except Exception as e:
        raise RuntimeError(f"اتصال به Gemini نشد: {e.__class__.__name__}")
    out = ""
    try:
        parts = data["candidates"][0]["content"]["parts"]
        out = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        pass
    if not out:
        reason = ""
        try:
            reason = data["candidates"][0].get("finishReason", "")
        except Exception:
            pass
        raise RuntimeError("جوابی نیامد" + (f" ({reason})" if reason else ""))
    return out


def setup(bot: Bot):
    def _ai(ctx):
        return ctx.acc.setdefault("ai", {})

    def _key(ctx):
        return str(_ai(ctx).get("key")
                   or os.environ.get("GEMINI_API_KEY") or "").strip()

    @bot.cmd("کلید هوش مصنوعی", "aikey", "ست جیمینای", cat="ابزار",
             help="کلید هوش مصنوعی <AIza...> — ست کلید رایگان Gemini "
                  "(aistudio.google.com/apikey) | بدون متن = وضعیت کلید")
    async def _set_key(event, ctx, args):
        if not getattr(getattr(event, "message", None), "out", False):
            return await ctx.reply(event, "❗ فقط خودِ صاحب اکانت می‌تواند کلید ست کند")
        parts = (args or "").split()
        key = parts[0] if parts else ""
        if not key:
            k = _key(ctx)
            if k:
                m = str(_ai(ctx).get("model") or "")
                return await ctx.reply(
                    event, f"🔑 کلید ست شده ({mask_key(k)})"
                           f"{f' | مدل: {m}' if m else ''}")
            return await ctx.reply(
                event, "❗ کلیدی ست نشده\n"
                       "۱) برو به aistudio.google.com/apikey (با تحریم‌شکن)\n"
                       "۲) Create API key\n"
                       "۳) بفرست: کلید هوش مصنوعی AIza...")
        _ai(ctx)["key"] = key
        try:
            ctx.store.save()
        except Exception:
            pass
        await ctx.reply(event, f"✅ کلید هوش مصنوعی ذخیره شد ({mask_key(key)})\n"
                               f"امتحان: «هوش مصنوعی سلام»")

    @bot.cmd("مدل هوش مصنوعی", "aimodel", cat="ابزار",
             help="مدل هوش مصنوعی <اسم> — مثلا gemini-2.0-flash | بدون متن = مدل فعلی")
    async def _set_model(event, ctx, args):
        m = (args or "").split()[0] if (args or "").split() else ""
        if not m:
            cur = str(_ai(ctx).get("model") or f"پیش‌فرض ({DEFAULT_MODEL})")
            return await ctx.reply(event, f"🧠 مدل فعلی: {cur}")
        _ai(ctx)["model"] = m
        try:
            ctx.store.save()
        except Exception:
            pass
        await ctx.reply(event, f"✅ مدل روی {m} ست شد")

    @bot.cmd("هوش مصنوعی", "ai", "جیمینای", cat="ابزار",
             help="هوش مصنوعی <سوال> — پرسش از Gemini | ریپلی روی یک پیام = تحلیل همان پیام")
    async def _ask(event, ctx, args):
        q = (args or "").strip()
        if not q:
            try:
                rep = await event.get_reply_message()
            except Exception:
                rep = None
            if rep is not None and rep.raw_text:
                q = rep.raw_text
        if not q:
            return await ctx.reply(event, "❗ فرمت: هوش مصنوعی <سوال>")
        key = _key(ctx)
        if not key:
            return await ctx.reply(
                event, "❗ اول کلید را ست کن: «کلید هوش مصنوعی AIza...»\n"
                       "کلید رایگان: aistudio.google.com/apikey")
        model = str(_ai(ctx).get("model") or "")
        try:
            out = await ask(key, model, q)
        except RuntimeError as e:
            return await ctx.reply(event, f"⚠️ {e}")
        except Exception:
            log.exception("ai ask failed")
            return await ctx.reply(event, "⚠️ خطای غیرمنتظره — جزئیات در لاگ")
        if len(out) > MAX_OUT:
            out = out[:MAX_OUT] + "\n…(ادامه دارد)"
        await ctx.reply(event, out)
