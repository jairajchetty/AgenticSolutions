"""HMAC-signed approval tokens shared by the mock ERP server and the Studio.

Format: base64url(canonical JSON claims) + "." + base64url(HMAC-SHA256(secret, payload part)),
both without padding.
"""

import base64
import binascii
import hashlib
import hmac
import json
import time

TOKEN_TTL_S = 900

REQUIRED_CLAIMS = (
    "req_id",
    "version",
    "content_hash",
    "tenant",
    "approver",
    "requested_by",
    "reason",
)


class TokenError(Exception):
    """Raised by verify(); str(error) is the reason."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise TokenError("malformed token") from None


def _sign(payload: str, secret: bytes) -> str:
    return _b64(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())


def issue(claims: dict, secret: bytes, *, ttl_s: int = TOKEN_TTL_S, now: float | None = None) -> str:
    missing = [k for k in REQUIRED_CLAIMS if k not in claims]
    if missing:
        raise ValueError(f"missing claims: {', '.join(missing)}")
    now = time.time() if now is None else now
    body = {**claims, "exp": now + ttl_s}
    payload = _b64(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload, secret)}"


def verify(token: str, secret: bytes, *, now: float | None = None) -> dict:
    if not isinstance(token, str) or token.count(".") != 1:
        raise TokenError("malformed token")
    payload, sig = token.split(".")
    if not payload or not sig or not token.isascii():
        raise TokenError("malformed token")
    sig_bytes = _unb64(sig)
    expected = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(sig_bytes, expected):
        raise TokenError("bad signature")
    try:
        claims = json.loads(_unb64(payload))
    except ValueError:
        raise TokenError("malformed token") from None
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), (int, float)):
        raise TokenError("malformed token")
    now = time.time() if now is None else now
    if now >= claims["exp"]:
        raise TokenError("token expired")
    return claims
