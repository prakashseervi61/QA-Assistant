"""Authentication infrastructure: JWT-style tokens and password hashing.

Both are implemented with the standard library only (``hmac`` + ``hashlib``)
and are gated by ``settings.ENABLE_AUTH``, which is OFF by default.
"""
