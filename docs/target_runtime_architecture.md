# Target Runtime Architecture

Canonical runtime architecture document:

- [docs/drawio/target_runtime_architecture.md](drawio/target_runtime_architecture.md)

This compatibility file exists because several repo documents and checklists
reference `docs/target_runtime_architecture.md` directly.

Current canonical architecture includes:
- department-specific source/policy knowledge base (`knowledge/sources`, `knowledge/policies`)
- runtime query strategy layer (`knowledge/query_strategies`) — single authority for task-level query construction, decoupled from source metadata
- central query resolver (`src/research/query_resolver.py`) — placeholder expansion, validation, buyer-candidate expansion, verify mode
- acceptance-time policy gates per department
- unchanged conversational autonomy inside department AG2 GroupChats
