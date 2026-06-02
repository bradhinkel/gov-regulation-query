"""
backend/rate_limit.py — shared slowapi limiter (Phase 8.5 Task 1).

Defined in its own module so both main.py (registration + error handler) and
routes/query.py (per-route decorator) can import the same Limiter instance
without a circular import.

In-memory token bucket keyed by client IP — appropriate for the single-instance
DigitalOcean deployment. Swap the storage backend to Redis if scaled to
multiple replicas.

Behind the nginx reverse proxy, the socket peer is always 127.0.0.1, which would
collapse every visitor into one shared bucket. nginx is configured to set
X-Real-IP to the real connecting address ($remote_addr) — which the client
cannot spoof, since nginx overwrites it — so we key the limiter off that header
and fall back to the socket peer for local/dev requests that bypass nginx.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# Suggested limits per Phase 8.5: 20 requests/minute, 200 requests/hour.
QUERY_RATE_LIMITS = "20/minute;200/hour"


def client_ip(request: Request) -> str:
    """Real client IP from nginx's X-Real-IP, falling back to the socket peer."""
    return request.headers.get("x-real-ip") or get_remote_address(request)


limiter = Limiter(key_func=client_ip)
