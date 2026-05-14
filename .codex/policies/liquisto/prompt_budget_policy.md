# Prompt Budget Policy

## Profile budgets

- fast: soft 6k, hard 10k tokens
- standard: soft 14k, hard 24k tokens
- deep: soft 28k, hard 42k tokens

## Optimization rules

- retrieve top-k heuristics only (default k=3)
- include deltas, not full history
- summarize prior context before expanding
- escalate from fast/standard to deep only on risk triggers
