"""Request protection for a public deployment: admin token, per-client rate limits, security headers."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def client_ip(request: Request) -> str:
    # Behind Vercel and Render the left-most X-Forwarded-For entry is the visitor.
    # It can be spoofed by a caller who hits the backend directly, so limits keyed on
    # it are a cost brake, not an access control; the admin token is the access control.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def require_admin(request: Request) -> None:
    """Gate for endpoints that change the corpus or burn CPU.

    With ADMIN_TOKEN set, the caller must send it in X-Admin-Token. Without it, only
    direct local requests are allowed, so a fresh deployment is closed by default.
    """
    token = config.ADMIN_TOKEN
    if token:
        sent = request.headers.get("x-admin-token", "")
        if not hmac.compare_digest(sent.encode(), token.encode()):
            raise HTTPException(401, "This action needs the admin token.")
        return
    proxied = "x-forwarded-for" in request.headers
    if proxied or not request.client or request.client.host not in LOOPBACK:
        raise HTTPException(403, "Uploads and evaluation are turned off here. Set ADMIN_TOKEN on the server to enable them.")


class RateLimiter:
    """Sliding-window limit per client and bucket, kept in memory (one process)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, request: Request, bucket: str, limit: int, window: float = 60.0) -> None:
        if limit <= 0:
            return
        key = (bucket, client_ip(request))
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(window - (now - hits[0])) + 1
                raise HTTPException(429, f"Too many requests. Try again in {retry} s.", headers={"Retry-After": str(retry)})
            hits.append(now)
            if len(self._hits) > 10_000:   # forget idle clients so memory stays bounded
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > window]:
                    del self._hits[stale]


limiter = RateLimiter()

# Tailwind's CDN build and Stitch's markup need inline scripts and styles, so the CSP
# allows 'unsafe-inline' but pins every origin the pages load from.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://lh3.googleusercontent.com",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])
HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}
