# Lyftr AI – Backend Assignment

Containerized FastAPI service that ingests WhatsApp-like webhook messages exactly once, exposes analytics and health endpoints, and runs via Docker Compose with SQLite storage. [file:1]

---

## How to Run

### Requirements

- Docker + Docker Compose installed
- Make available (default on macOS)

### Start the stack

From the project root:

make up


This will:

- Build the Docker image (multi-stage Dockerfile)
- Start the `api` service on `http://localhost:8000`
- Mount a Docker volume at `/data` for `sqlite:////data/app.db` [file:1]

To see logs:

make logs


To stop and clean up:

make down


---

## Environment Variables

All config is via environment variables (12-factor). [file:1]

- `DATABASE_URL`: e.g. `sqlite:////data/app.db` (set in `docker-compose.yml`) [file:1]
- `WEBHOOK_SECRET`: HMAC secret used for `/webhook` signature validation. [file:1]
- `LOG_LEVEL`: e.g. `INFO` or `DEBUG` (used by app logging, optional). [file:1]

---

## Endpoints

### 1. `POST /webhook`

Ingests inbound WhatsApp-like messages exactly once, with HMAC signature validation and idempotency. [file:1]

- **Headers**
  - `Content-Type: application/json`
  - `X-Signature`: hex HMAC-SHA256 of the raw request body bytes using `WEBHOOK_SECRET` [file:1]

- **Body example**

{
"message_id": "m1",
"from": "+919876543210",
"to": "+14155550100",
"ts": "2025-01-15T10:00:00Z",
"text": "Hello"
}


- **Behavior**
  - If signature missing/invalid → `401 {"detail":"invalid signature"}`, no DB insert. [file:1]
  - Pydantic validation:
    - `message_id`: non-empty string
    - `from`, `to`: E.164-like (`+` followed by digits)
    - `ts`: ISO-8601 UTC with `Z`
    - `text`: optional, max length 4096 [file:1]
  - On first valid `message_id`: insert row, return `200 {"status":"ok"}`. [file:1]
  - On duplicate `message_id`: do not insert, still return `200 {"status":"ok"}` (idempotent). [file:1]

### 2. `GET /messages`

Paginated, filterable list of stored messages. [file:1]

- **Query params**
  - `limit`: int, default 50, min 1, max 100
  - `offset`: int, default 0, min 0
  - `from`: filter by exact sender (`from_msisdn`)
  - `since`: ISO-8601 UTC string; only messages with `ts >= since`
  - `q`: case-insensitive substring search on `text` [file:1]

- **Ordering**
  - `ORDER BY ts ASC, message_id ASC` (newest last, deterministic). [file:1]

- **Response**

{
"data": [
{
"message_id": "m2",
"from": "+919876543210",
"to": "+14155550100",
"ts": "2025-01-15T09:00:00Z",
"text": "Earlier"
}
],
"total": 4,
"limit": 2,
"offset": 0
}


`total` is the total rows matching the filters, ignoring `limit` and `offset`. [file:1]

### 3. `GET /stats`

Simple analytics over messages. [file:1]

Returns:

{
"total_messages": 123,
"senders_count": 10,
"messages_per_sender": [
{ "from": "+919876543210", "count": 50 },
{ "from": "+911234567890", "count": 30 }
],
"first_message_ts": "2025-01-10T09:00:00Z",
"last_message_ts": "2025-01-15T10:00:00Z"
}


- `messages_per_sender`: top up to 10 senders, sorted by count desc. [file:1]
- `first_message_ts` / `last_message_ts`: min/max `ts` or `null` if no messages. [file:1]

### 4. Health probes

- `GET /health/live`
  - Always returns `200 {"status":"live"}` once app is running. [file:1]

- `GET /health/ready`
  - Returns `200 {"status":"ready"}` only if:
    - DB is reachable and `messages` table exists
    - `WEBHOOK_SECRET` is set and non-empty [file:1]
  - Otherwise returns `503 {"status":"not_ready"}`. [file:1]

### 5. `GET /metrics` (Prometheus-style)

Plain-text metrics in Prometheus exposition format. [file:1]

Includes at least:

- `http_requests_total{path="...",status="..."} <nt>`  
- `webhook_requests_total{result="created|duplicate|invalid_signature|validation_error"} <nt>`  
- Simple latency histogram:
  - `request_latency_ms_bucket{le="100"} ...`
  - `request_latency_ms_bucket{le="500"} ...`
  - `request_latency_ms_bucket{le="+Inf"} ...`
  - `request_latency_ms_count ...` [file:1]

These metric names are stable and documented here as required. [file:1]

---

## Design Decisions

### HMAC verification

- Uses `WEBHOOK_SECRET` from env. [file:1]
- Computes `hex(HMAC_SHA256(secret=WEBHOOK_SECRET, message=<raw request body bytes>))`. [file:1]
- Compares using `hmac.compare_digest` to avoid timing attacks. [file:1]
- If header is missing or mismatch → `401` and no DB insert. [file:1]

### Pagination contract (`/messages`)

- Applies filters (`from`, `since`, `q`) first, then:
  - Sorts by `ts ASC, message_id ASC`.
  - Applies `limit` and `offset`.
- Returns both:
  - `data`: current page
  - `total`: count of all rows matching filters (ignoring pagination). [file:1]

### Stats implementation

- Uses aggregate SQL queries on `messages`:
  - `COUNT(*)` for `total_messages`
  - `COUNT(DISTINCT from_msisdn)` for `senders_count`
  - `GROUP BY from_msisdn ORDER BY count DESC LIMIT 10` for `messages_per_sender`
  - `MIN(ts)` / `MAX(ts)` for first/last timestamps. [file:1]

### Metrics implementation

- In-memory counters and buckets maintained via FastAPI middleware:
  - `http_requests_total` keyed by `(path, status)`.
  - `webhook_requests_total` keyed by `result` (created/duplicate/invalid_signature/validation_error). [file:1]
  - Latency buckets at 100ms and 500ms plus +Inf count. [file:1]

---

## Logging

- One JSON log line per HTTP request. [file:1]
- Required keys:
  - `ts` (server time ISO-8601)
  - `level`
  - `request_id` (UUID per request)
  - `method`
  - `path`
  - `status`
  - `latency_ms` [file:1]
- Printed to stdout; ready for `docker compose logs` or piping through `jq`. [file:1]

---

## Setup Used

- macOS Terminal + VS Code
- Python 3.11 + FastAPI + SQLite
- Docker + Docker Compose
- GitHub for source hosting
- AI assistants (Copilot / ChatGPT / Perplexity) for code scaffolding and prompts
