"""
backend/rate_limit.py — shared slowapi limiter (Phase 8.5 Task 1).

Defined in its own module so both main.py (registration + error handler) and
routes/query.py (per-route decorator) can import the same Limiter instance
without a circular import.

In-memory token bucket keyed by client IP — appropriate for the single-instance
DigitalOcean deployment. Swap the storage backend to Redis if scaled to
multiple replicas.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Suggested limits per Phase 8.5: 20 requests/minute, 200 requests/hour.
QUERY_RATE_LIMITS = "20/minute;200/hour"

limiter = Limiter(key_func=get_remote_address)
