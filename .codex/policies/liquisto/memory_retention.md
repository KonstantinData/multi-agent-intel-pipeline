# Memory Retention Policy

## Raw operational logs

- retain short-term only (default 14 days)
- delete or compact after consolidation

## Consolidated procedural memory

- retain while validated and non-conflicting
- mark stale if not validated for 90 days
- prune if superseded or low-confidence

## Snapshots

- weekly snapshot retention: 12 weeks
- monthly snapshot retention: 12 months
