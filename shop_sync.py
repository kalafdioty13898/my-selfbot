# -*- coding: utf-8 -*-
"""اتصال سلف‌بات به فروشگاه star self — سشن‌های مشتری‌ها را زنده اجرا می‌کند.

جریان: مشتری در ربات فروش سلف می‌خرد → فروشگاه همان لحظه star.db را پوش
می‌کند → این ماژول هر SHOP_POLL ثانیه گیت را fetch می‌کند، سشن‌های فعال جدید
را می‌یابد، با کلید SHOP_ENCRYPTION_KEY رمزگشایی و به‌صورت کلاینت زنده استارت
می‌کند. یعنی سلف مشتری حداکثر ~۲ دقیقه بعد از خرید آنلاین می‌شود (نه ۵ ساعت).

قواعد:
- بدون SHOP_ENCRYPTION_KEY این ماژول غیرفعال است (فقط اکانت‌های خودت).
- سشن منقضی/لغوشده/حذف‌شده از فروشگاه → کلاینتش بلافاصله قطع می‌شود.
- خطای موقت خواندن دیتابیس → آن راند skip می‌شود (هیچ‌کس بی‌جهت قطع نمی‌شود).
- سشن خراب → با فاصله ۱۰ دقیقه دوباره امتحان می‌شود، نه اسپم.
"""
import asyncio
import hashlib
import logging
import os
import sqlite3
import subprocess  # فقط برای ساخت آرگومان‌ها؛ اجرا با asyncio انجام می‌شود
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("selfbot.shop")

DB_IN_REPO = os.path.join("shop", "data", "star.db")
# دیتابیس فروشگاه همیشه به وقت تهران ذخیره می‌کند (shop/utils.TEHRAN)
SHOP_TZ = ZoneInfo("Asia/Tehran")


class ShopSync:
    def __init__(self, cfg, on_start, on_stop, dead_queue=None):
        self.cfg = cfg
        self.on_start = on_start    # async fn(uid: str, session: str) -> bool
        self.on_stop = on_stop      # async fn(uid: str) -> None
        self.dead_queue = dead_queue  # asyncio.Queue: uid های کلاینتِ مرده
        self.running = {}           # uid -> fingerprint
        self._failed = {}           # uid -> (fingerprint, ts) برای بک‌آف
        self._tmp = os.path.join("data", ".shop_snapshot.db")

    # ---------- رمزگشایی ----------
    def _fernet(self):
        from cryptography.fernet import Fernet
        return Fernet(self.cfg.enc_key.encode())

    # ---------- گرفتن نسخه جدید دیتابیس (غیربلاک‌کننده) ----------
    async def _git(self, *args, timeout=45):
        p = await asyncio.create_subprocess_exec(
            "git", *args, cwd=os.getcwd(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
            return p.returncode, out
        except asyncio.TimeoutError:
            try:
                p.kill()
                await p.wait()
            except Exception:
                pass
            return -1, b""

    async def _fetch(self):
        """فچ گیت + استخراج star.db.

        خروجی: مسیر فایل دیتابیس، یا None اگر این راند نباید اعتماد کرد.
        فچِ ناموفق (بدون شبکه) → فال‌بک به کپی لحظه چک‌اوت؛
        فچِ موفق ولی show ناموفق → None (از نسخه کهنه استفاده نشود).
        """
        branch = self.cfg.branch
        rc_fetch, _ = await self._git("fetch", "origin", branch)
        if rc_fetch == 0:
            rc_show, out = await self._git("show", f"FETCH_HEAD:{DB_IN_REPO}")
            if rc_show == 0 and out:
                try:
                    os.makedirs("data", exist_ok=True)
                    with open(self._tmp, "wb") as f:
                        f.write(out)
                    return self._tmp
                except Exception as e:
                    log.warning("snapshot write failed: %s", e)
                    return None
            return None  # فچ بود ولی فایل در ریپو نیست → این راند نه
        # فچ اصلاً انجام نشد (آفلاین/غیره) → فال‌بک به کپی چک‌اوت
        if os.path.exists(DB_IN_REPO):
            return DB_IN_REPO
        return None

    # ---------- خواندن سشن‌های فعال ----------
    def _active_rows(self, db_path: str):
        """dict(uid -> session_enc) یا None در خطا (هیچ‌کس حذف فرض نشود)."""
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                cur = conn.execute(
                    "SELECT user_id, session_enc, expires_at FROM activations "
                    "WHERE status='active' AND session_enc != ''")
                rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            log.warning("shop db read failed: %s", e)
            return None
        out = {}
        now_naive = datetime.now(SHOP_TZ).replace(tzinfo=None)
        for uid, enc_s, exp in rows:
            if not exp:
                continue
            try:
                exp_dt = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue
            if exp_dt <= now_naive:  # فروشگاه هنوز منقضی نکرده بود
                continue
            out[str(uid)] = enc_s
        return out

    # ---------- حلقه اصلی ----------
    async def run(self):
        try:
            f = self._fernet()
        except Exception as e:
            log.warning("shop sync off — bad SHOP_ENCRYPTION_KEY: %s", e)
            return
        try:
            poll = max(15, int(self.cfg.shop_poll or 60))
        except (TypeError, ValueError):
            poll = 60
        log.info("🛒 اتصال به فروشگاه فعال شد (poll=%ds)", poll)
        first = True
        while True:
            try:
                await self._once(f, first)
                first = False
            except Exception:
                log.exception("shop sync round failed")
            await asyncio.sleep(poll)

    async def _once(self, f, first: bool):
        # ۰) کلاینت‌های مرده را از رجیستری بیرون بکش تا دوباره استارت شوند
        if self.dead_queue:
            while True:
                try:
                    dead = self.dead_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self.running.pop(dead, None)
                self._failed.pop(dead, None)

        path = await self._fetch()
        if not path:
            if first:
                log.info("shop db هنوز در ریپو نیست — بعداً دوباره چک می‌شود")
            return
        rows = self._active_rows(path)
        if rows is None:
            return  # خطای خواندن → این راند هیچ‌کس قطع/استارت نشود
        if not rows and not self.running:
            return

        # ۱) حذف شده‌ها (منقضی/لغو/بن) → قطع کن
        for uid in list(self.running.keys()):
            if uid not in rows:
                log.info("سلف %s از فروشگاه حذف شد — قطع می‌کنم", uid)
                self.running.pop(uid, None)
                try:
                    await self.on_stop(uid)
                except Exception:
                    log.exception("on_stop failed")

        # ۲) جدیدها / تغییرکرده‌ها
        import time as _t
        for uid, enc_s in rows.items():
            try:
                session = f.decrypt(enc_s.encode()).decode()
            except Exception:
                log.warning("سشن %s رمزگشایی نشد (کلید اشتباه؟)", uid)
                continue
            if not session:
                continue
            fp = hashlib.sha1(session.encode()).hexdigest()[:16]
            if self.running.get(uid) == fp:
                continue
            if uid in self.running:
                # سشن همین uid عوض شده (فعال‌سازی مجدد) → قدیمی قطع شود
                log.info("سشن %s عوض شد — کلاینت قبلی قطع و جدید استارت می‌شود", uid)
                self.running.pop(uid, None)
                try:
                    await self.on_stop(uid)
                except Exception:
                    log.exception("on_stop (rotate) failed")
            fail = self._failed.get(uid)
            if fail and fail[0] == fp and _t.time() - fail[1] < 600:
                continue  # همین سشن اخیراً شکست خورد — ۱۰ دقیقه صبر
            ok = False
            try:
                ok = await self.on_start(uid, session)
            except Exception:
                log.exception("on_start failed")
            if ok:
                self.running[uid] = fp
                self._failed.pop(uid, None)
                log.info("🟢 سلف مشتری %s آنلاین شد", uid)
            else:
                self._failed[uid] = (fp, _t.time())
                log.warning("سلف مشتری %s استارت نشد (سشن نامعتبر/بن)", uid)
