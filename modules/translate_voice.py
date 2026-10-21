# -*- coding: utf-8 -*-
"""ماژول ترجمه و متن‌به‌وایس (TTS)."""
import os

from framework import Bot
from utils import tmp_path


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

    @bot.cmd("وایس", "tts", cat="ترجمه",
             help="وایس <متن> (یا ریپلی روی متن) — تبدیل متن به پیام صوتی")
    async def _tts(event, ctx, args):
        text = args.strip()
        lang = "fa"
        src = None
        if not text and event.is_reply:
            src = await event.get_reply_message()
            text = src.raw_text or ""
        if not text:
            return await ctx.reply(event, "❗ متن بده: وایس سلام خوبی")
        # اگر اول متن کد زبان بود: وایس en hello
        first = text.split()[0]
        if len(first) == 2 and first.isalpha():
            lang = first.lower()
            text = text[len(first):].strip()
        note = await ctx.reply(event, "🎙 در حال ساخت وایس...")
        try:
            from gtts import gTTS
            path = tmp_path("mp3")
            gTTS(text=text[:2800], lang=lang).save(path)
            await ctx.client.send_file(event.chat_id, path, voice_note=True,
                                       reply_to=src.id if (not args.strip() and event.is_reply) else None)
            os.remove(path)
            await ctx.client.delete_messages(event.chat_id, [note.id])
        except Exception as e:
            await ctx.client.edit_message(event.chat_id, note.id, f"❌ نشد: {e}")
