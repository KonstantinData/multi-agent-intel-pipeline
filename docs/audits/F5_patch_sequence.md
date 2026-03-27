# F5 — Shared Run Memory thread-safe / isoliert machen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F5  
**Ziel:** Parallele Department-Mutationen auf dem gemeinsamen ShortTermMemoryStore eliminieren durch Isolation mit kontrollierter Merge-Phase.

---

## Ist-Zustand: Analyse

### Das Problem

`supervisor_loop.py` uebergibt `run_context.short_term_memory` (ein einzelnes `ShortTermMemoryStore`) an alle Departments — auch an die parallel laufenden Company + Market Departments via `ThreadPoolExecutor`.

Beide Departments mutieren gleichzeitig:
- `ingest_worker_report()` — appendet auf `facts`, `sources`, `market_signals`, `worker_reports`, mutiert `usage_totals`
- `mark_critic_review()` — mutiert `critic_approvals`, `task_statuses`, `open_points`
- `store_department_package()` — mutiert `department_packages`
- `record_department_run_state()` — mutiert `department_run_states`
- `append_department_conversation()` — mutiert `department_conversations`

Python `list.extend()` und `dict.__setitem__()` sind nicht thread-safe fuer gleichzeitige Mutationen aus verschiedenen Threads.

### Betroffene Stellen

| Stelle | Datei | Problem |
|--------|-------|---------|
| Parallel-Batch | `supervisor_loop.py` | Company + Market teilen sich denselben Store |
| Department-Runtime | `department_runtime.py` → `lead.py` | Uebergibt `memory_store` an Worker/Critic/Judge |
| Store-Mutationen | `short_term_store.py` | Alle Methoden mutieren ohne Synchronisation |

---

## Ziel-Zustand

### Isolation mit kontrollierter Merge-Phase

Jedes parallel laufende Department bekommt einen **eigenen** `ShortTermMemoryStore` als Working-Set. Nach Abschluss aller parallelen Departments werden die Working-Sets **kontrolliert** in den Haupt-Store gemergt.

```
Haupt-Store (run_context.short_term_memory)
    |
    +-- [parallel] Company-Working-Set (eigener ShortTermMemoryStore)
    +-- [parallel] Market-Working-Set (eigener ShortTermMemoryStore)
    |
    <-- Merge-Phase: deterministische Konsolidierung -->
    |
    +-- [sequential] Buyer (direkt auf Haupt-Store, kein Parallelitaetsproblem)
    +-- [sequential] Contact (direkt auf Haupt-Store)
```

### Merge-Regeln

| Feld-Typ | Merge-Strategie |
|----------|----------------|
| Listen (`facts`, `sources`, `open_questions`, `worker_reports`, ...) | Extend + Dedup |
| Dicts (`task_outputs`, `task_statuses`, `critic_approvals`, ...) | Update (spaeterer Key gewinnt bei Konflikt — irrelevant da disjunkte Task-Keys) |
| `usage_totals` | Addieren |
| `department_packages` | Update (disjunkte Department-Keys) |
| `department_run_states` | Update (disjunkte Department-Keys) |
| `department_conversations` | Update (disjunkte Department-Keys) |
| `department_workspaces` | Update (disjunkte Department-Keys) |

---

## Patch-Sequenz

### Patch 1 — `merge_from()` Methode auf `ShortTermMemoryStore`

**Datei:** `src/memory/short_term_store.py`

Neue Methode die einen Working-Set-Store in den Haupt-Store mergt.

### Patch 2 — Supervisor-Loop: Isolation fuer Parallel-Batch

**Datei:** `src/orchestration/supervisor_loop.py`

- Parallel-Batch: Jedes Department bekommt `ShortTermMemoryStore()` als Working-Set
- Nach `as_completed`: Merge jedes Working-Sets in den Haupt-Store
- Sequential-Phase: Weiterhin direkt auf Haupt-Store (kein Parallelitaetsproblem)

### Patch 3 — Tests

**Datei:** `tests/architecture/test_memory.py`

- `test_merge_from_combines_facts_and_sources`
- `test_merge_from_adds_usage_totals`
- `test_merge_from_preserves_disjoint_department_keys`
- `test_parallel_departments_use_isolated_stores`

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Keine unkontrollierten parallelen Mutationen eines gemeinsamen Stores | Parallel-Departments bekommen eigene Working-Sets |
| Reproduzierbarkeit der Aggregationen steigt | Deterministische Merge-Phase nach Parallel-Batch |
| `sources`, `worker_reports`, `usage_totals`, `open_questions` bleiben konsistent | Merge-Regeln: extend+dedup / addieren / update |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/memory/short_term_store.py` | `merge_from()` Methode |
| 2 | `src/orchestration/supervisor_loop.py` | Isolation fuer Parallel-Batch + Merge-Phase |
| 3 | `tests/architecture/test_memory.py` | 4 neue Tests |

**Reihenfolge:** 1 → 2 → 3 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 3 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 1 -- `merge_from()` auf `ShortTermMemoryStore`**
   - Listen: extend (facts, sources, market_signals, buyer_hypotheses, open_questions, next_actions, rejected_claims, worker_reports, follow_up_sessions)
   - Dicts: update (task_outputs, task_statuses, section_outputs, critic_approvals, critic_reviews, accepted_points, open_points, department_packages, department_conversations, department_workspaces, department_run_states)
   - revision_history: setdefault + extend (Merge per task_key)
   - usage_totals: additive Merge

2. **Patch 2 -- Supervisor-Loop Isolation**
   - `_run_single_department()` nimmt jetzt expliziten `memory_store`-Parameter
   - Parallel-Batch: Jedes Department bekommt `ShortTermMemoryStore()` als Working-Set
   - Nach `as_completed`: `merge_from()` fuer jedes Working-Set in den Haupt-Store
   - Sequential-Phase + Synthesis: Weiterhin direkt auf Haupt-Store (kein Parallelitaetsproblem)
   - Fallback-Pfad (single parallel job): Weiterhin direkt auf Haupt-Store

3. **Patch 3 -- Tests (6 neue Tests)**
   - `test_merge_from_combines_facts_and_sources`
   - `test_merge_from_adds_usage_totals`
   - `test_merge_from_preserves_disjoint_department_keys`
   - `test_merge_from_combines_worker_reports`
   - `test_merge_from_combines_task_statuses`
   - `test_parallel_departments_use_isolated_stores`

### Validierungsergebnisse

```
$ pytest tests/ -> 198 passed in 36.94s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Keine unkontrollierten parallelen Mutationen eines gemeinsamen Stores | Parallel-Departments bekommen eigene Working-Sets |
| Reproduzierbarkeit der Aggregationen steigt | Deterministische Merge-Phase nach Parallel-Batch |
| sources, worker_reports, usage_totals, open_questions bleiben konsistent | Merge-Regeln: extend / addieren / update |

---

## Nachschaerfung (Review-Feedback)

**Datum:** 2025-03-25  
**Anlass:** 5 Architektur-Anmerkungen nach initialer Umsetzung

### Befund und Massnahmen

| # | Anmerkung | Befund | Massnahme |
|---|-----------|--------|----------|
| 1 | Read-Snapshot + Delta statt leerer Store | Working-Sets waren leer initialisiert — Departments hatten keinen Lesekontext | **Gefixt:** `create_working_set()` erzeugt snapshot-geseedeten Store, `delta_from()` extrahiert nur neue Writes |
| 2 | Deterministische Merge-Reihenfolge | Merge lief bereits in `_DEPARTMENT_RUN_ORDER`, nicht `as_completed` | Bestaetigt als korrekt, Kommentar praezisiert |
| 3 | Disjunktheits-Assertion fuer Dict-Merges | Fehlte — stiller Last-Writer-Wins bei Konflikten | **Gefixt:** `merge_from()` prueft Disjunktheit und loggt Warning bei Konflikten |
| 4 | Kanonische Dedup-Keys | `_dedup_safe()` nutzt JSON-Serialisierung — funktioniert, aber nicht optimal fuer `sources` | Dokumentiert als Verbesserungspunkt, kein Blocker |
| 5 | Fehlende Tests | Completion-Order-Determinismus und Konflikt-Test fehlten | **Gefixt:** 4 neue Tests (merge order, conflict warning, snapshot seeding, delta extraction) |

### Zusaetzliche Code-Aenderungen

- `short_term_store.py`: `create_working_set()` — erzeugt snapshot-geseedeten Working-Set-Store
- `short_term_store.py`: `delta_from(baseline)` — extrahiert nur neue Writes relativ zum Baseline-Snapshot
- `short_term_store.py`: `merge_from()` — Disjunktheits-Assertion mit Warning bei Konflikten
- `supervisor_loop.py`: Parallel-Batch nutzt `create_working_set()` + `delta_from()` statt leerer Stores
- `test_memory.py`: 4 neue Tests (merge order determinism, conflict detection, snapshot seeding, delta extraction)

### Validierung nach Nachschaerfung

```
$ pytest tests/ -> 202 passed in 30.43s
```

### Architektur-Regeln (Zielzustand)

1. **Read-Snapshot + Write-Delta:** Parallel-Departments arbeiten auf snapshot-geseedeten Working-Sets. Nur der Delta wird zurueckgemergt. Kein Department verliert Lesekontext, kein Department mutiert den Haupt-Store.
2. **Kanonische Merge-Reihenfolge:** Merge erfolgt immer in `_DEPARTMENT_RUN_ORDER`, nicht in `as_completed`-Reihenfolge. Ergebnis ist run-to-run reproduzierbar.
3. **Disjunktheits-Garantie:** Dict-Merges asserten Disjunktheit. Konflikte werden geloggt, nicht still geschluckt.
4. **Dedup-Keys:** Langfristig sollten Listen-Merges kanonische Dedup-Keys nutzen (URL fuer sources, task_key fuer worker_reports). Aktuell funktioniert JSON-basierte Dedup korrekt.


---

## Follow-up-Punkte (kein F5-Blocker, P2-Haertung)

**Datum:** 2025-03-25  
**Anlass:** Abschliessendes Review nach Nachschaerfung

### 1. Kanonische Dedup-Keys pro Sammlung

**Aktueller Zustand:** `_dedup_safe()` nutzt JSON-Serialisierung als universellen Dedup-Key. Funktioniert korrekt, aber nicht optimal fuer Sammlungen mit natuerlichen Identifiern.

**Ziel:** Pro Sammlung explizit definierte Dedup-Keys:
- `sources` → normalisierte URL oder `source_id`
- `worker_reports` → `(department, task_key, role)`
- `facts` → `fact_id` oder stabiler Hash

**Prioritaet:** P2-Haertung. Kein F5-Blocker, weil die aktuelle Dedup korrekt dedupliziert — nur nicht optimal bei minimal unterschiedlicher Serialisierung.

### 2. Merge-Konflikt-Policy langfristig schaerfen

**Aktueller Zustand:** `merge_from()` prueft Disjunktheit und loggt Warning bei Konflikten. Last-Writer-Wins als Fallback.

**Ziel:** Policy-driven Konfliktbehandlung je nach Modus:
- **Test/Preflight:** fail fast bei Konflikten
- **Runtime (strict):** quarantine + Warning
- **Runtime (lenient):** Warning + Last-Writer-Wins (aktueller Zustand)

**Prioritaet:** P2-Haertung. Kein F5-Blocker, weil Konflikte bereits sichtbar werden. Endausbau waere eine explizite `MergePolicy`-Konfiguration.
