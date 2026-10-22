# -*- coding: utf-8 -*-
"""ماژول ترجمه و وایس (TTS) — وایس فارسی و ده‌ها زبان با صدای طبیعی (edge-tts)."""
import asyncio
import os
import subprocess
import shutil

from telethon.tl import types

from framework import Bot
from utils import tmp_path

# صداهای طبیعی مایکروسافت (edge-tts) — فارسی ساپورت کامل دارد
VOICES = {
    "fa": "fa-IR-DilaraNeural",
    "en": "en-US-JennyNeural",
    "ar": "ar-SA-ZariyahNeural",
    "tr": "tr-TR-EmelNeural",
    "de": "de-DE-KatjaNeural",
    "fr": "fr-FR-DeniseNeural",
    "es": "es-ES-ElviraNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "it": "it-IT-ElsaNeural",
    "hi": "hi-IN-SwaraNeural",
    "ur": "ur-PK-UzmaNeural",
    "az": "az-AZ-BanuNeural",
    "ps": "ps-AF-LatifaNeural",
}


def setup(bot: Bot):
    @bot.cmd("ترجمه", "tr", cat="ترجمه",
             help="ترجمه <زبان> (ریپلی) — ترجمه پیام، مثال: ترجمه en")
    async def _tr(event, ctx, args):
        lang = (args or "en").strip().lower()[:5]
        if not event.is_reply:
            return await ctx.reply(event, "❗ روی پیام ریپلی کن: ترجمه en")
        src = await event.get_reply_message()
        text = src.raw_text or ""
        if not text:
            return await ctx.reply(event, "❗ این پیام متن نداره")
        note = await ctx.reply(event, "🌐 در حال ترجمه...")
        try:
            from deep_translator import GoogleTranslator
            out = GoogleTranslator(source="auto", target=lang).translate(text[:4500])
            await ctx.client.edit_message(event.chat_id, note.id,
                                          f"🌐 <b>ترجمه [{lang}]:</b>\n{out}",
                                          parse_mode="html")
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ ترجمه نشد: {e}")

    # ---------- ابزار وایس ----------
    def _to_ogg(src):
        """تبدیل به اویگ/اوپس تا تلگرام به شکل وایس واقعی پخشش کند."""
        if not shutil.which("ffmpeg"):
            return None
        out = tmp_path("ogg")
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                 "-c:a", "libopus", "-b:a", "48k", "-vbr", "on", "-ar", "48000", out],
                capture_output=True, timeout=120)
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
                return out
        except Exception:
            pass
        return None

    def _dur(fp):
        """طول صدا به ثانیه (برای نمایش درست وایس)."""
        if not shutil.which("ffprobe"):
            return 0
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", fp],
                capture_output=True, timeout=30)
            return max(1, int(float(r.stdout.decode().strip() or 0)))
        except Exception:
            return 0

    @bot.cmd("وایس", "tts", cat="ترجمه",
             help="وایس <متن> (یا ریپلی روی متن) — تبدیل متن به وایس؛ فارسی پیش‌فرض، مثال: وایس en hello")
    async def _tts(event, ctx, args):
        text = args.strip()
        lang = "fa"
        src = None
        if not text and event.is_reply:
            src = await event.get_reply_message()
            text = src.raw_text or ""
        if not text:
            return await ctx.reply(event, "❗ متن بده: وایس سلام خوبی")
        # اگر اول متن کد زبان بود: وایس en hello — یا اسم کامل صدا: وایس fa-IR-FaridNeural سلام
        first = text.split()[0]
        voice = None
        if "Neural" in first:
            voice = first
            text = text[len(first):].strip()
        elif len(first) == 2 and first.isalpha():
            lang = first.lower()
            text = text[len(first):].strip()
        if not text:
            return await ctx.reply(event, "❗ متن بعد از کد زبان بنویس: وایس en hello")
        note = await ctx.reply(event, "🎙 در حال ساخت وایس...")
        mp3 = tmp_path("mp3")
        ogg = None
        try:
            made = False
            try:
                import edge_tts
                v = voice or VOICES.get(lang)
                if v:
                    await asyncio.wait_for(
                        edge_tts.Communicate(text[:2500], v).save(mp3), timeout=120)
                    made = True
            except Exception:
                made = False
            if not made:
                # جایگزین: gTTS برای زبان‌هایی که edge ندارد (در ترد جدا تا حلقه بلاک نشود)
                from gtts import gTTS
                await asyncio.to_thread(lambda: gTTS(text=text[:2800], lang=lang).save(mp3))
            ogg = await asyncio.to_thread(_to_ogg, mp3)
            if ogg:
                await ctx.client.send_file(
                    event.chat_id, ogg,
                    attributes=[types.DocumentAttributeAudio(await asyncio.to_thread(_dur, ogg), voice=True)],
                    reply_to=src.id if (not args.strip() and event.is_reply) else None)
            else:
                await ctx.client.send_file(
                    event.chat_id, mp3, voice_note=True,
                    reply_to=src.id if (not args.strip() and event.is_reply) else None)
            await ctx.client.delete_messages(event.chat_id, [note.id])
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ نشد: {e}")
        finally:
            for p in (mp3, ogg):
                if p:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
