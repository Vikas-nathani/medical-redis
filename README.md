# Medical Consultation System

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?logo=redis&logoColor=white)](https://redis.io/)

## Project Overview

Medical Consultation System is a FastAPI + Redis backend for patient and consultation records with concurrency-safe consultation writes, complaint-chain retrieval, readiness checks, request correlation IDs, and Prometheus metrics.

## 1. Project Description

The system stores patient demographics and consultation records in Redis and exposes API endpoints for:

- patient registration and lookup
- consultation creation with server-side complaint slug generation
- patient timeline retrieval with pagination
- complaint-chain retrieval and latest consultation lookup

The consultation write path uses Redis Lua for atomic consistency and per-complaint sequential numbering.

## 2. High Level Design

```text
Frontend / API Consumer
        |
        v
  FastAPI (main.py)
    - routes
    - validation
    - error mapping
    - request-id middleware
    - metrics exposition
        |
        v
 Redis (docker-compose)
    - Hashes
    - Lists
    - ZSET
    - INCR counters
    - Lua script writes
```

Core runtime additions currently implemented:

- Redis connection pool with timeouts and retry-on-timeout
- request correlation IDs in response headers and logs
- /health readiness endpoint
- /metrics endpoint with instrumentator + explicit error counter
- idempotency key support for POST consultation

## 3. Low Level Design

### 3a. Redis Data Structures

| Structure | Key Format | Purpose |
|---|---|---|
| Patient hash | patient:{patient_id} | Patient demographics and created_at |
| Consultation hash | consultation:{patient_id}:{consultation_id} | Consultation record and embedded follow_up_history |
| Patient consultations ZSET | patient:{patient_id}:consultations | Time-ordered patient timeline |
| Complaint list | patient:{patient_id}:complaint:{complaint_slug} | Complaint-specific chain oldest to newest |
| Complaint counter | counter:{patient_id}:{complaint_slug} | Atomic visit numbering via INCR |
| Idempotency key | idempotency:{key} | Consultation ID replay mapping with TTL |

### 3b. Atomic Write Pipeline

Consultation creation is executed by Lua in Redis to atomically:

1. increment complaint counter
2. generate consultation_id
3. locate previous consultation in complaint list
4. build capped follow_up_history
5. write consultation hash
6. update patient timeline ZSET
7. append complaint list

### 3c. Current Project Structure

```text
medical-redis/
├── main.py
├── requirements.txt
├── docker-compose.yml
├── README.md
├── api/
│   ├── exceptions.py
│   ├── schemas.py
│   └── routes/
│       ├── consultation.py
│       ├── health.py
│       └── patient.py
├── config/
│   └── settings.py
├── core/
│   └── logging.py
├── db/
│   └── connection.py
├── models/
│   ├── consultation.py
│   └── patient.py
├── pipeline/
│   ├── read.py
│   └── write.py
└── tests/
    ├── conftest.py
    ├── test_concurrency.py
    ├── test_endpoints.py
    ├── test_failures.py
    └── test_write.py
```

### 3d. Key Updates Implemented

- complaint_slug removed from consultation request body; backend generates slug from chief_complaint
- complaint read endpoints switched to complaint query parameter
- consultation write made atomic via Redis Lua + INCR
- follow_up_history capped to avoid unbounded embedded growth
- list APIs return total_count and support pagination
- Redis exceptions mapped to HTTP 503/504/500 centrally
- JSON structured logging added
- request_id middleware added with X-Request-ID response header
- /health endpoint added with degraded status on Redis failure
- /metrics endpoint added and explicit http_request_errors_total counter added
- Redis timeout settings enabled in connection pool
- docker-compose configured for Redis AOF persistence
- idempotency support added for POST /api/v1/consultation with 24h TTL replay key
- comprehensive pytest suite added for endpoints, failures, and concurrency

## 4. API Endpoints

### Endpoint Summary

| Method | Path | Description |
|---|---|---|
| POST | /api/v1/patient | Register patient |
| GET | /api/v1/patient/{patient_id} | Get patient |
| POST | /api/v1/consultation | Create consultation (supports Idempotency-Key header) |
| GET | /api/v1/patient/{patient_id}/consultations | Get all consultations (pagination) |
| GET | /api/v1/patient/{patient_id}/complaint | Get complaint chain by complaint query param |
| GET | /api/v1/patient/{patient_id}/complaint/latest | Get latest complaint consultation by complaint query param |
| GET | /health | Redis readiness endpoint |
| GET | /metrics | Prometheus metrics endpoint |
| GET | / | Base service status endpoint |

### Consultation API Request Contract

POST /api/v1/consultation body:

```json
{
  "patient_id": "P001",
  "chief_complaint": "High Fever",
  "visit_date": "",
  "doctor_id": "D01",
  "questions": "Since when is fever present?",
  "symptoms_observed": "Fever with chills",
  "medications": "Paracetamol 500mg",
  "follow_up_date": "2026-04-05",
  "follow_up_instruction": "Hydrate and rest"
}
```

Optional header:

- Idempotency-Key: <unique_key>

Response behavior:

- first request with key: HTTP 201
- replay with same key: HTTP 200 with same consultation_id in message

### Validation Rules

- chief_complaint must be at least 3 characters after trim
- visit_date must be YYYY-MM-DD (empty defaults to today)
- follow_up_date must be YYYY-MM-DD
- generated complaint slug must be non-empty and valid

## 5. Error Responses

| Status | Meaning | Notes |
|---|---|---|
| 404 | Patient/complaint/consultation not found | Resource does not exist |
| 409 | Duplicate patient | Patient already registered |
| 422 | Validation failure | Invalid payload fields |
| 503 | Redis unavailable | Connection-level failure |
| 504 | Redis timeout | Timeout from Redis operations |
| 500 | Internal/Redis operation failure | Unexpected server-side error |

## 6. Installation and Setup

### 6a. Prerequisites

- Python 3.10+
- Docker + Docker Compose plugin

### 6b. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

### 6c. Start Redis (AOF enabled)

```bash
docker compose up -d redis
```

Current Redis container config in docker-compose:

- appendonly yes
- appendfsync everysec
- data volume mounted at /data

### 6d. Environment Variables

| Variable | Default |
|---|---|
| REDIS_HOST | localhost |
| REDIS_PORT | 6379 |
| REDIS_DB | 0 |
| LOG_LEVEL | INFO |

### 6e. Run API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6f. API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 7. Usage Examples

### 7.1 Create Patient

```bash
curl -X POST http://localhost:8000/api/v1/patient \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "name": "Ravi Kumar",
    "dob": "1992-07-15",
    "gender": "male",
    "blood_type": "B+",
    "contact": "9999999999",
    "address": "Hyderabad"
  }'
```

### 7.2 Create Consultation With Idempotency-Key

```bash
curl -X POST http://localhost:8000/api/v1/consultation \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: consult-001" \
  -d '{
    "patient_id": "P001",
    "chief_complaint": "High Fever",
    "visit_date": "",
    "doctor_id": "D01",
    "questions": "Any chills?",
    "symptoms_observed": "Fever and chills",
    "medications": "Paracetamol",
    "follow_up_date": "2026-04-05",
    "follow_up_instruction": "Hydrate"
  }'
```

### 7.3 Get Complaint Chain (query param)

```bash
curl "http://localhost:8000/api/v1/patient/P001/complaint?complaint=High%20Fever&limit=20&offset=0"
```

### 7.4 Get Latest Consultation For Complaint

```bash
curl "http://localhost:8000/api/v1/patient/P001/complaint/latest?complaint=High%20Fever"
```

### 7.5 Health and Metrics

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## 8. Testing

Test files:

- tests/test_write.py (existing integration-style write test)
- tests/conftest.py (shared fixtures)
- tests/test_endpoints.py (endpoint success/error/idempotency/headers/metrics checks)
- tests/test_concurrency.py (20-thread consultation stress test)
- tests/test_failures.py (Redis failure simulations with mocks)

Run full suite:

```bash
python3 -m pytest -q
```

Run concurrency test only:

```bash
python3 -m pytest -q tests/test_concurrency.py
```

## 9. Roadmap

| Item | Status |
|---|---|
| Atomic consultation write | DONE |
| Query-based complaint endpoints | DONE |
| Pagination and total_count | DONE |
| Redis timeout handling | DONE |
| Structured logging + request correlation IDs | DONE |
| Health and metrics endpoints | DONE |
| Redis AOF persistence via docker compose | DONE |
| Idempotency for consultation POST | DONE |
| Authentication/authorization | PENDING |
| Production process manager + multi-worker strategy | PENDING |

## 10. Known Limitations

- idempotency lookup/set currently spans multiple operations and should be made fully atomic to eliminate replay race windows under concurrent duplicate requests
- long-term data retention and archival strategy is not implemented
- authentication and authorization are not implemented

## 11. Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Data store | Redis |
| Validation | Pydantic v2 |
| Redis client | redis-py |
| Metrics | prometheus-fastapi-instrumentator + prometheus_client |
| Logging | python-json-logger |
| Testing | pytest + FastAPI TestClient + unittest.mock + threading |

## 12. Changelog Summary

Recent updates captured in this README:

- Added request-id middleware and X-Request-ID response header
- Added explicit Prometheus error counter http_request_errors_total(method, path, status)
- Added /health readiness and /metrics observability endpoints
- Added idempotency behavior for POST /api/v1/consultation
- Added Redis timeouts in connection pool configuration
- Added docker-compose Redis AOF persistence configuration
- Reworked complaint retrieval APIs to use complaint query parameter
- Expanded automated tests with endpoint, failure, and concurrency coverage

## 13. Version History
| Date | Version | Changes |
|---|---|---|
| 2026-04-02 | v1.0.0 | Initial FastAPI + Redis consultation backend with patient and consultation APIs, Redis data model, and Lua-based atomic consultation writes. |
| 2026-04-02 | v1.1.0 | Added validation hardening, Redis exception mapping, structured logging, pagination with total_count, and capped follow_up_history. |
| 2026-04-02 | v1.2.0 | Switched complaint retrieval endpoints to complaint query params and backend slug generation flow. |
| 2026-04-02 | v1.3.0 | Added Redis timeouts, docker-compose AOF persistence, consultation idempotency support, request correlation IDs, /health endpoint, and /metrics endpoint with explicit http_request_errors_total counter. |
| 2026-04-02 | v1.4.0 | Added comprehensive pytest suite with shared fixtures, endpoint coverage, Redis failure mocks, and threading-based concurrency stress tests. |