# -*- coding: utf-8 -*-
"""API سبک aiohttp برای اتصال سلف (GitHub Actions) به ربات فروش.

  GET  /api/active_sessions?key=SHOP_KEY → سشن‌های فعال و غیرمنقضی (رمزگشایی‌شده)
  POST /api/heartbeat  {key, user_id}    → ثبت پینگ سلامت سلف
  GET  /health                           → چک سلامت
"""
import logging

from aiohttp import web

from crypto import dec
from utils import now, FMT

log = logging.getLogger("star_self.api")


def build_api(cfg, db) -> web.Application:
    routes = web.RouteTableDef()

    @routes.get("/health")
    async def health(request):
        return web.json_response({"ok": True, "service": "star_self"})

    @routes.get("/api/active_sessions")
    async def active_sessions(request):
        if request.query.get("key", "") != cfg.shop_key:
            return web.json_response({"error": "forbidden"}, status=403)
        rows = await db.all_active()
        out = []
        for r in rows:
            s = dec(r["session_enc"]) if r["session_enc"] else ""
            if not s:
                continue
            out.append({
                "user_id": r["user_id"],
                "session": s,
                "plan": r["plan"],
                "expires_at": r["expires_at"],
                "note": r["note"],
            })
        return web.json_response(out)

    @routes.post("/api/heartbeat")
    async def heartbeat(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "bad json"}, status=400)
        if data.get("key", "") != cfg.shop_key:
            return web.json_response({"error": "forbidden"}, status=403)
        uid = int(data.get("user_id", 0) or 0)
        if not uid:
            return web.json_response({"error": "no user_id"}, status=400)
        await db.set_ping(uid, now().strftime(FMT))
        return web.json_response({"ok": True})

    app = web.Application()
    app.add_routes(routes)
    return app
