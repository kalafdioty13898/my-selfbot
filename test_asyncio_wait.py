# -*- coding: utf-8 -*-
"""تست رگرسیون: asyncio.wait روی پایتون ۳.۱۱+ coroutine خام را نمی‌پذیرد.

بازتولید کرش Actions:
    TypeError: Passing coroutines is forbidden, use tasks explicitly.

الگوی درست (فیکس bot.py): هر coroutine باید asyncio.create_task شود.
"""
import asyncio


class FakeClient:
    """شبیه‌سازی Telethon client.run_until_disconnected (هرگز تمیز تمام نمی‌شود)."""

    async def run_until_disconnected(self):
        await asyncio.sleep(3600)


async def fake_ticker():
    while True:
        await asyncio.sleep(3600)


async def main():
    client = FakeClient()

    # ── الگوی قدیمی (باگ‌دار) ──
    old_tasks = [asyncio.create_task(fake_ticker()),
                 client.run_until_disconnected()]  # coroutine خام!
    try:
        await asyncio.wait(old_tasks, return_when=asyncio.FIRST_COMPLETED)
        raise AssertionError("الگوی قدیمی نباید روی ۳.۱۱+ کار کند")
    except TypeError:
        for t in old_tasks[:1]:
            t.cancel()
        print("OK   الگوی قدیمی همان TypeError معروف را داد (بازتولید شد)")

    # ── الگوی جدید (فیکس bot.py خط ۲۲۷-۲۲۹) ──
    tasks = []
    tasks.append(asyncio.create_task(fake_ticker()))
    tasks.append(asyncio.create_task(client.run_until_disconnected()))
    stop = asyncio.create_task(asyncio.sleep(0.05))  # شبیه SIGTERM
    tasks.append(stop)

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    assert stop in done, "stop باید اول تمام شود"
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    print("OK   الگوی جدید: FIRST_COMPLETED + cancel + gather سالم")
    print("PASS 2/2")


asyncio.run(main())
