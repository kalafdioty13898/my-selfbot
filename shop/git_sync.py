# -*- coding: utf-8 -*-
"""پوش فوری دیتابیس به گیت‌هاب — برای فعال‌سازی آنی سلف.

وقتی مشتری سلف می‌خرد، سشن رمزشده‌اش در data/star.db ذخیره می‌شود.
این ماژول همان لحظه یک اسنپ‌شات سازگار از دیتابیس می‌گیرد (اتصال read-only
جداگانه → بدون دست‌زدن به تراکنش‌های جاری) و در یک worktree جداگانه کامیت و
پوش می‌کند تا سلف‌بات (که هر ۶۰ ثانیه گیت را fetch می‌کند) حداکثر تا ~۲
دقیقه بعد سشن را بگیرد و سلفت مشتری آنلاین شود.

فعال بودن: روی GitHub Actions خودکار روشن است؛ بیرون از آن (تست محلی)
خاموش تا به ریپو کسی آسیب نزند. با SHOP_GIT_SYNC=1/0 می‌شود اجباری کرد.
"""
import asyncio
import logging
import os
import shutil
import sqlite3
import tempfile

log = logging.getLogger("star_self.gitsync")

_lock = asyncio.Lock()  # پوش‌های هم‌زمان سریالی شوند


def enabled() -> bool:
    """فقط داخل GitHub Actions (یا با SHOP_GIT_SYNC=1) روشن باشد."""
    forced = os.getenv("SHOP_GIT_SYNC", "").strip().lower()
    if forced in ("1", "true", "yes", "on"):
        return True
    if forced in ("0", "false", "no", "off"):
        return False
    return os.getenv("GITHUB_ACTIONS", "") == "true"


async def _run(cwd, *args, timeout=60):
    """اجرای دستور git؛ (ok, خروجی) برمی‌گرداند؛ تایم‌اوت → kill."""
    p = None
    try:
        p = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(p.communicate(), timeout=timeout)
        ok = p.returncode == 0
        if not ok:
            log.warning("git %s → %s", " ".join(args[:2]),
                        err.decode()[:180].replace("\n", " "))
        return ok, (out + err).decode("utf-8", "replace")
    except asyncio.TimeoutError:
        log.warning("git %s timeout (%ds) — killed", " ".join(args[:2]), timeout)
        if p:
            try:
                p.kill()
                await p.wait()
            except Exception:
                pass
        return False, "timeout"
    except Exception as e:
        log.warning("git %s failed: %s", " ".join(args[:2]), e)
        return False, str(e)


async def _snapshot(db, snap_path: str) -> bool:
    """اسنپ‌شات سازگار از دیتابیس زنده (WAL) به مسیر جدید.

    اتصال read-only جداگانه = آخرین state کامیت‌شده را می‌بیند، تراکنش
    نیمه‌کاره‌ی کسی را کامیت نمی‌کند و worker اصلی aiosqlite را سد نمی‌کند.
    """
    def _bk():
        src = sqlite3.connect(f"file:{db.path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(snap_path)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

    try:
        await asyncio.to_thread(_bk)
        return os.path.getsize(snap_path) > 0
    except Exception as e:
        log.warning("db snapshot failed: %s", e)
        return False


async def push_db_snapshot(db) -> bool:
    """دیتابیس فعلی را فوراً در ریپو کامیت و پوش می‌کند؛ True یعنی موفق."""
    if not enabled():
        return False
    async with _lock:
        root = os.getcwd()  # workflow با working-directory: shop اجرا می‌کند
        ok, out = await _run(root, "rev-parse", "--show-toplevel")
        if not ok:
            return False
        repo = (out.strip().splitlines() or [""])[-1] or os.getcwd()
        branch = (os.getenv("GITHUB_REF_NAME") or "").strip()
        if not branch:
            ok, out = await _run(repo, "rev-parse", "--abbrev-ref", "HEAD")
            branch = out.strip() if ok and out.strip() else "main"

        tmp = tempfile.mkdtemp(prefix="starsnap-")
        wt = os.path.join(tmp, "wt")
        snap = os.path.join(tmp, "star.db")
        try:
            if not await _snapshot(db, snap):
                return False

            # worktree جداگانه: فایل زنده‌ی دیتابیس هرگز دست نمی‌خورد
            ok, _ = await _run(repo, "worktree", "add", "--detach", wt, "HEAD", timeout=90)
            if not ok:
                await _run(repo, "worktree", "prune")
                return False

            db_dir = os.path.join(wt, "shop", "data")
            os.makedirs(db_dir, exist_ok=True)
            await asyncio.to_thread(shutil.copyfile, snap, os.path.join(db_dir, "star.db"))

            await _run(wt, "add", "shop/data/star.db")
            clean, _ = await _run(wt, "diff", "--cached", "--quiet")
            if clean:
                return True  # تغییری نبود
            await _run(wt, "-c", "user.name=star-shop-bot",
                       "-c", "user.email=actions@users.noreply.github.com",
                       "commit", "-m", "shop: instant session sync (activation)")

            for i in range(3):
                if i:
                    # fetch داخل خود worktree (FETCH_HEAD بین worktreeها مشترک نیست)
                    await _run(wt, "fetch", "origin", branch, timeout=90)
                    await _run(wt, "rebase", "FETCH_HEAD")
                ok, _ = await _run(wt, "push", "origin", f"HEAD:{branch}", timeout=120)
                if ok:
                    log.info("db pushed instantly → سلف مشتری تا ~۲ دقیقه دیگر آنلاین می‌شود")
                    return True
                await asyncio.sleep(3)
            log.warning("db instant push failed after 3 retries — سلف با تأخیر دوره‌ای فعال می‌شود")
            return False
        except Exception as e:
            log.warning("push_db_snapshot error: %s", e)
            return False
        finally:
            await _run(repo, "worktree", "remove", "--force", wt)
            await _run(repo, "worktree", "prune")
            await asyncio.to_thread(shutil.rmtree, tmp, True)
