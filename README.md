# Medical Consultation System

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?logo=redis&logoColor=white)](https://redis.io/) 

## Project Overview

Medical Consultation System is a FastAPI + Redis backend for patient and consultation records with concurrency-safe consultation writes, complaint-chain retrieval, readiness checks, request correlation IDs, and Prometheus metrics.

## 1. Project Description

The system stores patient demographics and consultation records in Redis and exposes API endpoints for:

- patient registration and lookup
- consultation creation with frontend-provided complaint chain slug
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
- backend-generated idempotency for POST consultation (no client header required)

## 3. Low Level Design

### 3a. Redis Data Structures

| Structure | Key Format | Purpose |
|---|---|---|
| Patient hash | patient:{patient_id} | Patient demographics and created_at |
| Consultation hash | consultation:{patient_id}:{consultation_id} | Consultation record and embedded follow_up_history |
| Patient consultations ZSET | patient:{patient_id}:consultations | Time-ordered patient timeline |
| Complaint list | patient:{patient_id}:complaint:{complaint_slug} | Complaint-specific chain oldest to newest |
| Complaint counter | counter:{patient_id}:{complaint_slug} | Atomic visit numbering via INCR |
| Idempotency key | idempotency:{key} | Consultation ID replay mapping (no expiry) |

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

- complaint_chain added to consultation request body; backend uses it as the Redis complaint chain slug
- complaint read endpoints switched to complaint query parameter
- consultation write made atomic via Redis Lua + INCR
- follow_up_history capped to avoid unbounded embedded growth
- consultation APIs now use rich nested schema (vitals, key questions, diagnoses, investigations, medications, procedures, notes)
- list APIs support pagination via limit/offset query params and return consultation arrays
- Redis exceptions mapped to HTTP 503/504/500 centrally
- JSON structured logging added
- request_id middleware added with X-Request-ID response header
- /health endpoint added with degraded status on Redis failure
- /metrics endpoint added and explicit http_request_errors_total counter added
- Redis timeout settings enabled in connection pool
- docker-compose configured for Redis AOF persistence
- idempotency key generated on backend using sha256(patient_id:complaint_slug:visit_date)
- idempotency key persistence has no TTL (stored until manually deleted)
- replay-path normalization added to coerce malformed empty list fields ({} -> [])
- comprehensive pytest suite added for endpoints, failures, and concurrency

## 4. API Endpoints

### Endpoint Summary

| Method | Path | Description |
|---|---|---|
| POST | /api/v1/patient | Register patient |
| GET | /api/v1/patient/{patient_id} | Get patient |
| POST | /api/v1/consultation | Create consultation (backend idempotency, no header) |
| GET | /api/v1/patient/{patient_id}/consultations | Get all consultations (limit/offset pagination) |
| GET | /api/v1/patient/{patient_id}/complaints | Get all complaint chains for dropdown (chain_slug, display_name, visit_count) |
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
  "complaint_chain": "fever",
  "visit_date": "2026-04-03",
  "chief_complaints": ["High Fever"],
  "vitals": {
    "height_cm": 170,
    "weight_kg": 65,
    "head_circ_cm": 54,
    "temp_celsius": 101,
    "bp_mmhg": "120/80"
  },
  "key_questions": [
    {"question": "Fever since?", "answer": "3 days"}
  ],
  "key_questions_ai_notes": "Gradual onset fever",
  "diagnoses": [
    {"name": "Viral URI", "selected": true, "is_custom": false}
  ],
  "diagnoses_ai_notes": "Likely viral",
  "investigations": [],
  "investigations_ai_notes": "",
  "medications": [
    {"name": "Paracetamol", "selected": true, "is_custom": false}
  ],
  "medications_ai_notes": "Symptomatic treatment",
  "procedures": [],
  "procedures_ai_notes": "",
  "advice": "Rest and hydration",
  "follow_up_date": "2026-04-10",
  "advice_ai_notes": "Review in 7 days"
}
```

Response behavior:

- first request for a computed idempotency key: HTTP 201
- replay of same payload dimensions (patient_id + complaint_chain + visit_date): HTTP 200
- both responses return full ConsultationResponse payload

### Validation Rules

- chief_complaints must contain at least one complaint, each at least 3 characters
- complaint_chain must be non-empty, lowercased, and slug-style (no spaces)
- visit_date must be YYYY-MM-DD if provided
- follow_up_date must be YYYY-MM-DD if provided

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

### 7.2 Create Consultation (No Idempotency Header Needed)

```bash
curl -X POST http://localhost:8000/api/v1/consultation \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "complaint_chain": "fever",
    "visit_date": "2026-04-03",
    "chief_complaints": ["High Fever"],
    "vitals": null,
    "key_questions": [],
    "key_questions_ai_notes": "",
    "diagnoses": [],
    "diagnoses_ai_notes": "",
    "investigations": [],
    "investigations_ai_notes": "",
    "medications": [],
    "medications_ai_notes": "",
    "procedures": [],
    "procedures_ai_notes": "",
    "advice": "Hydrate",
    "follow_up_date": "2026-04-05",
    "advice_ai_notes": ""
  }'
```

### 7.3 Get Complaint Chain (query param)

```bash
curl "http://localhost:8000/api/v1/patient/P001/complaint?complaint=High%20Fever&limit=20&offset=0"
```

### 7.4 Get Complaint Chains For Patient

```bash
curl "http://localhost:8000/api/v1/patient/P001/complaints"
```

### 7.5 Get Latest Consultation For Complaint

```bash
curl "http://localhost:8000/api/v1/patient/P001/complaint/latest?complaint=High%20Fever"
```

### 7.6 Health and Metrics

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## 8. Testing

Test files:

- tests/test_write.py (existing integration-style write test)
- tests/conftest.py (shared fixtures)
- tests/test_endpoints.py (endpoint success/error/idempotency/metrics checks)
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
| Pagination via limit/offset | DONE |
| Redis timeout handling | DONE |
| Structured logging + request correlation IDs | DONE |
| Health and metrics endpoints | DONE |
| Redis AOF persistence via docker compose | DONE |
| Backend-generated idempotency for consultation POST | DONE |
| Replay list-field normalization ({} -> []) | DONE |
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
- Added backend-generated idempotency behavior for POST /api/v1/consultation (no request header)
- Changed idempotency mapping persistence to no TTL
- Hardened consultation/follow_up_history list normalization for malformed empty values
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
| 2026-04-03 | v1.5.0 | Migrated to rich nested consultation payloads and responses, moved idempotency key generation to backend with no TTL, removed client Idempotency-Key header requirement, and added replay/list-field normalization safeguards for empty JSON list fields. |