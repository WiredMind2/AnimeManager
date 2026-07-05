"""Session token signing and verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid


class SessionTokenStore:
    def __init__(self, secret: str | bytes | None = None) -> None:
        if isinstance(secret, bytes):
            self._secret = secret
        elif isinstance(secret, str) and secret:
            self._secret = secret.encode("utf-8")
        else:
            self._secret = uuid.uuid4().hex.encode("ascii")

    def build(self, *, session_id: str, expires_at: float) -> str:
        exp = str(int(expires_at))
        payload = f"{session_id}.{exp}"
        digest = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).digest()
        signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return f"{exp}.{signature}"

    def verify(self, session_id: str, token: str) -> bool:
        if not token or "." not in token:
            return False
        exp_raw, sig = token.split(".", 1)
        try:
            exp = int(exp_raw)
        except ValueError:
            return False
        if time.time() > exp:
            return False
        expected = self.build(session_id=session_id, expires_at=float(exp))
        expected_sig = expected.split(".", 1)[1]
        return hmac.compare_digest(sig, expected_sig)


__all__ = ["SessionTokenStore"]
