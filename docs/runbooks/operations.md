# Operations and Incident Response Runbook (DEP-15)

This runbook describes operational procedures, health diagnosis, disaster recovery, and incident response for the **AI Knowledge Agent** backend.

---

## 1. System Architecture & Topology

- **FastAPI API (`backend`)**: Stateless ASGI application handling search, chat, repository queries, and evaluation triggers.
- **Celery Worker (`worker`)**: Background distributed task worker processing Git cloning, parsing, embedding generation, and Qdrant upserts.
- **PostgreSQL (`postgres`)**: Relational source of truth for users, repositories, indexing states, and audit trails.
- **Qdrant Vector DB (`qdrant`)**: Vector index for semantic code chunk embeddings.
- **Redis (`redis`)**: Task queue broker and Celery result backend with append-only persistence.

---

## 2. Startup & Deployment

### Quick Start via Docker Compose:
```bash
docker compose -f docker/docker-compose.yml up -d
```

### Applying Database Migrations:
```bash
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

### Checking Service Health:
- **Liveness Probe**: `GET /health/liveness` (returns `{"status": "alive"}`)
- **Readiness Probe**: `GET /health/readiness` (returns `{"status": "ready", "components": {...}}`)
- **Prometheus Metrics**: `GET /metrics`

---

## 3. Incident Diagnosis & Playbooks

### A. High HTTP Error Rate (`HighHttpErrorRate` Alert)
1. **Symptoms**: Spike in 500 responses or alert trigger.
2. **Immediate Actions**:
   - Check container logs:
     ```bash
     docker compose logs --tail=100 backend
     ```
   - Inspect active database connection pool in PostgreSQL:
     ```sql
     SELECT count(*), state FROM pg_stat_activity GROUP BY state;
     ```
   - Check if downstream providers (Groq LLM / Langfuse) are throwing rate limit errors or timeouts.

### B. Ingestion Job Failures or Stalled Indexing
1. **Symptoms**: Repository status remains stuck in `CLONING` or transitions to `FAILED`.
2. **Diagnosis**:
   - Query indexing status via API: `GET /api/v1/repositories/{id}/indexing-status`
   - Check worker logs:
     ```bash
     docker compose logs --tail=200 worker
     ```
3. **Recovery**:
   - If worker crashed, Celery will automatically re-queue idempotent tasks (using deterministic chunk IDs).
   - Trigger the reconciliation service:
     ```bash
     curl -X POST http://localhost:8000/api/v1/repositories/{id}/reconcile
     ```

### C. Queue Backlog & Worker Scaling
1. **Symptoms**: Tasks accumulate in `PENDING` state.
2. **Scale Workers**:
   ```bash
   docker compose -f docker/docker-compose.yml up -d --scale worker=4
   ```

---

## 4. Backup & Disaster Recovery (DEP-10)

### PostgreSQL Backup:
```bash
docker compose exec postgres pg_dump -U postgres ai_knowledge_agent | gzip > backup_pg_$(date +%Y%m%d_%H%M%S).sql.gz
```

### PostgreSQL Restore:
```bash
gunzip -c backup_pg_20261003.sql.gz | docker compose exec -T postgres psql -U postgres -d ai_knowledge_agent
```

### Qdrant Snapshot Backup:
```bash
curl -X POST "http://localhost:6333/collections/code_chunks/snapshots"
```

### BM25 Disk Index Recovery:
BM25 indexes are stored at `storage/bm25/<repo_id>.pkl`. If corrupted, delete the `.pkl` file and trigger re-indexing via the API; the BM25 index will be reconstructed automatically from stored code chunks.

---

## 5. Secret Rotation Procedure (DEP-03, SEC-07)

1. **SECRET_KEY Rotation**:
   - Update `SECRET_KEY` in environment/.env file.
   - Restart backend instances gracefully:
     ```bash
     docker compose restart backend
     ```
   - Note: Users will need to re-authenticate with `/api/v1/auth/token` as existing JWT tokens signed with the old key will expire.

2. **Groq API Key / Langfuse Keys**:
   - Update the respective environment variable and reload containers without downtime.

---

## 6. Rollback Procedure (DEP-14)

1. If a newly deployed container image fails smoke tests or healthchecks:
   ```bash
   # Revert to previous release image tag
   docker compose -f docker/docker-compose.yml stop backend worker
   docker compose -f docker/docker-compose.yml up -d --no-build
   ```
2. If database schema was modified:
   ```bash
   docker compose exec backend alembic downgrade -1
   ```
