from collections import defaultdict
from typing import Dict, Tuple

# Counters: (path, status) -> count
http_requests_total: Dict[Tuple[str, str], int] = defaultdict(int)

# Counters: result -> count for webhook
webhook_requests_total: Dict[str, int] = defaultdict(int)

# Simple latency buckets (in ms)
latency_buckets = [100, 500]
request_latency_ms_buckets: Dict[int, int] = defaultdict(int)
request_latency_ms_count: int = 0

def inc_http_request(path: str, status: int) -> None:
    key = (path, str(status))
    http_requests_total[key] += 1

def inc_webhook_result(result: str) -> None:
    webhook_requests_total[result] += 1

def observe_latency_ms(latency_ms: float) -> None:
    global request_latency_ms_count
    request_latency_ms_count += 1
    for b in latency_buckets:
        if latency_ms <= b:
            request_latency_ms_buckets[b] += 1
    # +Inf bucket is represented by total count
