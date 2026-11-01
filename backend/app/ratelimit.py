import os
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request

HITS: dict[str, deque] = defaultdict(deque)


def limiter(request: Request):
    """Simple in-memory per-IP limiter (single process only)."""
    limit = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
    q = HITS[request.client.host if request.client else "?"]
    now = time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Rate limit exceeded; try again shortly")
    q.append(now)
