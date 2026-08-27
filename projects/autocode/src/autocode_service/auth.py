"""Small HMAC device-token authority used by the optional service adapter."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid


def _encode(value: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, sort_keys=True).encode()).decode().rstrip("=")


class TokenAuthority:
    def __init__(self, secret: str) -> None:
        self.secret = secret.encode()
        self.revoked: set[str] = set()

    def issue(self, device_id: str, *, ttl: int = 3600) -> str:
        payload = {"device_id": device_id, "jti": str(uuid.uuid4()), "exp": int(time.time()) + ttl}
        body = _encode(payload)
        signature = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def verify(self, token: str) -> dict[str, object]:
        try:
            body, signature = token.split(".", 1)
            expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PermissionError("malformed token") from exc
        if not hmac.compare_digest(signature, expected) or payload["jti"] in self.revoked:
            raise PermissionError("invalid or revoked token")
        if int(payload["exp"]) < int(time.time()):
            raise PermissionError("expired token")
        return payload

    def revoke(self, token: str) -> None:
        body = token.split(".", 1)[0]
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        self.revoked.add(payload["jti"])
