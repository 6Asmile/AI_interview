# Agent durability and resilience

PostgreSQL is the only business source of truth. Redis accelerates cache and
realtime delivery, but losing Redis must not lose an accepted answer, an Agent
run, the current question, an evaluation, or a completed reference answer.

## Durable turn lifecycle

An asynchronous answer follows this order:

1. Claim the `Idempotency-Key` in PostgreSQL.
2. Lock `User -> InterviewSession -> InterviewQuestion -> MediaArtifact` in a
   short transaction.
3. Persist the answer, `InterviewAgentExecution`, generation job and dispatch
   outbox atomically.
4. Return `202` with `run_id`, `events_url` and `resume_url`.
5. Celery evaluates and generates without holding a database row lock.
6. Each durable transition uses the Execution version as a fencing token.
7. Persist the generated question before publishing the terminal Redis event.

The lifecycle is `accepted -> answer_persisted -> evaluating -> evaluated ->
generating -> completed`. Failures are `failed_retryable`, `failed_terminal` or
`canceled`.

`GET /api/v1/interviews/{session_id}/resume-state/` rebuilds the user-visible
state from PostgreSQL. When an Agent Redis Stream no longer exists, the events
endpoint emits a `state.snapshot` generated from the durable Execution and
generation job.

## Redis fault domains

Local development uses one Redis instance with separate databases. The
production override uses:

- `redis-cache`: `allkeys-lfu`, no persistence, safe to evict and rebuild.
- `redis-realtime`: `noeviction`, AOF `everysec`, persistent volume for Streams,
  WebSocket tickets, channel delivery and coordination locks.

Start the production topology with:

```powershell
docker compose -f docker-compose.yml -f docker-compose.production-resilience.yml up -d
```

The override removes the inherited local Redis service. Celery results use the
cache Redis and are never treated as durable business state.

## Cache policy

`core.cache_policy` centralizes soft TTL, hard TTL, negative TTL, jitter and
single-flight behavior. Hot public data can return a stale value while one
request rebuilds it. Private object authorization remains a PostgreSQL query and
is never shared through a cross-tenant negative cache.

## Capacity exercise

The k6 scenario uses existing authorized test sessions and real answer text; it
does not create mock business content. Supplying one session tests 100 duplicate
submissions against the same idempotency key. Supplying 100 distinct cases tests
100 accepted Agent tasks. In both modes, 500 concurrent resume-state reads run
after submission starts.

Create a local, untracked JSON file:

```json
[
  {"session_id":"session-uuid","question_id":123}
]
```

Run against an isolated environment because the answers are actually persisted:

```powershell
$env:BASE_URL='http://127.0.0.1:8000/api/v1'
$env:ACCESS_TOKEN='<short-lived-test-token>'
$env:AGENT_CASES_FILE='E:\\tmp\\ifaceoff-agent-cases.json'
$env:ANSWER_TEXT='<real anonymized test answer>'
$env:RUN_TAG=(Get-Date -Format 'yyyyMMddHHmmss')
# Optional: hold/reconnect 500 SSE clients against one authorized Agent run.
$env:EVENTS_URL='/interviews/<session-id>/agent-executions/<run-id>/events/'
k6 run scripts/load/agent-resilience.k6.js
```

For the 100-task acceptance target, the cases file must contain 100 distinct
running sessions and unanswered question IDs. Thresholds are submit p95 below
300 ms, resume-state p95 below 500 ms and server error rate below 1 percent.
Model generation latency is intentionally excluded from the acceptance latency.
