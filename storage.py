# -*- coding: utf-8 -*-
"""پایگاه داده سلف — ذخیره در کانال/storage تلگرام + کش محلی.
GitHub Actions هر چند ساعت ری‌استارت می‌شود، پس تنظیمات به صورت پیام در
چت ذخیره‌سازی (STORAGE_ID) نگه داشته می‌شود و در بوت بعدی دوباره خوانده می‌شود."""
import asyncio
import base64
import json
import os
import time
import zlib

MARK = "≡SFB-DB≡"
SAVE_DEBOUNCE = 8  # ثانیه


def default_account():
    return {
        "off": {"all": False, "chats": {}},
        "names": [], "names_on": False, "name_i": 0,
        "bios": [], "bios_on": False, "bio_i": 0,
        "sec": {"on": False, "mode": "all", "text": "", "cool": 5, "offline_min": 5, "tag": False},
        "seen": {},
        "black": [],
        "quick": {},
        "ad": {"del": True, "edit": True, "ttl": True, "relay": None},
        "autosave": {},
        "welcome": {},
        "lock": {},
        "mute": {},
        "filters": {},
        "rems": [],
        "daily": [],
        "autodel": {},
        "cloud": {},
        "clk": {"name_on": False, "name_base": "", "bio_on": False, "bio_base": ""},
    }


class Store:
    def __init__(self, cfg):
        self.cfg = cfg
        self.data = {"accounts": {}}
        self.client = None
        self.chunk_ids = []
        self.index_id = None
        self._last = 0.0
        self._dirty = False

    def acc(self, key):
        a = self.data["accounts"].setdefault(str(key), default_account())
        d = default_account()
        for k, v in d.items():
            a.setdefault(k, v)
        return a

    def accs(self):
        return self.data["accounts"]

    # ---------- load ----------
    async def load(self):
        # ۱) کش محلی
        local = self._read_local()
        # ۲) نسخه تلگرامی (منبع اصلی)
        remote = None
        if self.cfg.storage_id and self.client:
            remote = await self._load_tg()
        if remote is not None:
            self.data = remote
        elif local is not None:
            self.data = local
        if local and remote and len(json.dumps(local)) > len(json.dumps(remote)):
            # محلی جدیدتر است (مثلاً ذخیره تلگرامی موقتاً fail شده) — ادغام ساده: محلی برنده
            self.data = local

    def _read_local(self):
        try:
            with open(self.cfg.db_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_local(self):
        try:
            os.makedirs(os.path.dirname(self.cfg.db_file) or ".", exist_ok=True)
            with open(self.cfg.db_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
        except Exception:
            pass

    async def _load_tg(self):
        chat = self.cfg.storage_id
        try:
            async for m in self.client.iter_messages(chat, limit=30):
                if m.raw_text and m.raw_text.startswith(MARK):
                    meta = json.loads(m.raw_text[len(MARK):])
                    ids = meta.get("ids", [])
                    self.index_id = m.id
                    if not ids:
                        return {"accounts": {}}
                    msgs = await self.client.get_messages(chat, ids=ids)
                    by_id = {mm.id: mm for mm in msgs if mm}
                    blob = "".join((by_id[i].raw_text or "") for i in ids if i in by_id)
                    blob = blob.strip()
                    if not blob:
                        return {"accounts": {}}
                    data = json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
                    self.chunk_ids = list(ids)
                    return data
        except Exception:
            pass
        return None

    # ---------- save ----------
    def save(self, force=False):
        """ذخیره (فراخوانی از داخل هندلرهای async مجاز است)."""
        self._dirty = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # خارج از event loop: فقط کش محلی
            self._dirty = False
            self._write_local()
            return
        if force or time.time() - self._last >= SAVE_DEBOUNCE:
            self._last = time.time()
            self._dirty = False
            loop.create_task(self._save_now())
        else:
            loop.create_task(self._delayed_save())

    async def _delayed_save(self):
        await asyncio.sleep(SAVE_DEBOUNCE)
        if self._dirty:
            self._dirty = False
            self._last = time.time()
            await self._save_now()

    async def _save_now(self):
        self._write_local()
        chat = self.cfg.storage_id
        if not chat or not self.client:
            return
        blob = base64.b64encode(
            zlib.compress(json.dumps(self.data, ensure_ascii=False).encode("utf-8"), 6)
        ).decode("ascii")
        chunks = [blob[i:i + 3200] for i in range(0, len(blob), 3200)] or [""]
        new_ids = []
        try:
            for i, c in enumerate(chunks):
                if i < len(self.chunk_ids):
                    try:
                        await self.client.edit_message(chat, self.chunk_ids[i], c)
                        new_ids.append(self.chunk_ids[i])
                    except Exception:
                        m = await self.client.send_message(chat, c)
                        new_ids.append(m.id)
                else:
                    m = await self.client.send_message(chat, c)
                    new_ids.append(m.id)
            for old in self.chunk_ids[len(chunks):]:
                try:
                    await self.client.delete_messages(chat, [old])
                except Exception:
                    pass
            self.chunk_ids = new_ids
            meta = MARK + json.dumps({"ids": new_ids})
            if self.index_id:
                try:
                    await self.client.edit_message(chat, self.index_id, meta)
                except Exception:
                    m = await self.client.send_message(chat, meta)
                    self.index_id = m.id
                    try:
                        await self.client.pin_message(chat, m.id, notify=False)
                    except Exception:
                        pass
            else:
                m = await self.client.send_message(chat, meta)
                self.index_id = m.id
                try:
                    await self.client.pin_message(chat, m.id, notify=False)
                except Exception:
                    pass
        except Exception:
            self._dirty = True  # دفعه بعد دوباره تلاش کن

    async def flush(self):
        """ذخیره اجباری در پایان کار."""
        if self._dirty or True:
            self._last = 0
            await self._save_now()
