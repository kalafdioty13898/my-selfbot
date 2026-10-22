# -*- coding: utf-8 -*-
"""رمزنگاری سشن‌های ۳۶۰ حرفی مشتریان با Fernet.

کلید از ENCRYPTION_KEY در .env خوانده می‌شود؛ اگر نبود، یک کلید تصادفی
ساخته و در data/.secret.key ذخیره می‌شود (این فایل را از دست نده!).
"""
import os
from cryptography.fernet import Fernet, InvalidToken


def _load_key() -> bytes:
    env = os.getenv("ENCRYPTION_KEY", "").strip()
    if env:
        try:
            Fernet(env.encode())
            return env.encode()
        except Exception:
            pass  # کلید نامعتبر → کلید فایل ساخته می‌شود
    path = os.getenv("KEY_FILE", "data/.secret.key")
    try:
        with open(path, "rb") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(key)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return key


_f = Fernet(_load_key())


def enc(text: str) -> str:
    """رمز کردن سشن برای ذخیره در دیتابیس."""
    return _f.encrypt(text.encode()).decode()


def dec(token: str) -> str:
    """رمزگشایی سشن؛ در صورت خرابی رشته خالی برمی‌گردد."""
    try:
        return _f.decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return ""
