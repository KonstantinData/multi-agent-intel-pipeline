# Data Governance

## Allowed in long-term memory

- procedural patterns
- anti-patterns
- decision heuristics
- aggregate metrics

## Disallowed in long-term memory

- company-specific factual content
- customer-specific evidence
- run-specific conclusions treated as universal truth
- raw secret-like strings

## Enforcement

- scrub before persistence
- validate schema before write
- reject entries violating disallowed classes
