# Memory Topology (Local vs Cloud)

## Target architecture

Use hybrid memory:
- local-first for hot retrieval
- cloud-authoritative for consolidation, sharing, and recovery

## Local-first scope

- retrieval index
- latest active heuristics
- anti-pattern shortlist

Reason: lowest latency and best token-efficiency during active task execution.

## Cloud-authoritative scope

- consolidated history
- promotion/demotion audit history
- replay/eval-linked memory snapshots

Reason: team-level consistency, backup, and auditability.

## Sync strategy

- write-behind sync after task completion
- read-through cloud on local cache miss
- conflict resolution by recency + validation confidence

## Safety gates before cloud sync

- secret/PII scrub
- schema validation
- disallowed-content rejection
