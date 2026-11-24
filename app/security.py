"""Request protection for a public deployment: per-client rate limits and security headers.

There is no login and no admin token: every endpoint is open, and the limits below are the only brake."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config


def client_ip(request: Request) -> str:
    """Find out which visitor a request came from (their IP address)."""
    # Behind Vercel and Render the left-most X-Forwarded-For entry is the visitor.
    # It can be spoofed by a caller who hits the backend directly, so limits keyed on
    # it are a cost brake, not an access control.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limit per client and bucket, kept in memory (one process).

    A rate limiter stops one visitor from flooding the server (or running up the bill
    of a paid language-model API) by allowing only N requests per minute.
    """

    def __init__(self) -> None:
        """Start with an empty record: (bucket, visitor) -> times of their recent requests."""
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, request: Request, bucket: str, limit: int, window: float = 60.0) -> None:
        """Allow the request, or refuse it with error 429 "Too many requests".

        It forgets requests older than the window (60 s), counts the rest, and refuses
        when the visitor has already made `limit` requests. `bucket` keeps separate
        counts for separate actions ("chat", "write", "feedback").
        """
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

# CSP (Content-Security-Policy) is a list of the places the browser may load scripts,
# styles, fonts and images from. Anything from another place is blocked by the browser.
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
