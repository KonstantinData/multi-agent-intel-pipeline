# F7 — Status-/Decision-Vokabular vereinheitlichen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F7  
**Ziel:** Ein kanonisches Entscheidungsmodell. Identische Begriffswelt in Runtime, Contracts, Prompts, Logs und Tests.

---

## Ist-Zustand: Vokabular-Inventar

### Drei vermischte Vokabular-Ebenen

| Ebene | Wo definiert | Begriffe |
|-------|-------------|----------|
| Task-Decision-Outcomes | `contracts.py` | `accepted, accepted_with_gaps, rework_required, escalated_to_judge, closed_unresolved, blocked_by_dependency` |
| Task-Runtime-Status | `contracts.py` OUTCOME_TO_TASK_STATUS, Judge, Loop | `accepted, degraded, pending, blocked, rejected, skipped` |
| Judge-Decision-Labels | `judge.py` | `accept, accept_degraded, reject` |

Zusaetzlich:
- `short_term_store.py`: `submitted`, `needs_revision` (Phantom-Status)
- `supervisor_loop.py`: `pending_synthesis` (Lifecycle-Status)
- `supervisor.py`: `accepted: bool` (Legacy-Shim aus F2/F3)
- `pipeline_runner.py`: Run-Level-Status `completed, completed_partial, completed_but_not_usable, failed`

### Kern-Drift

| Problem | Detail |
|---------|--------|
| Judge spricht andere Sprache als Contracts | `accept` vs `accepted`, `accept_degraded` vs `accepted_with_gaps`, `reject` vs `closed_unresolved` |
| `rejected` als Task-Status ist doppeldeutig | Wird sowohl vom Judge (task_status) als auch von finalize_package (no research) verwendet, aber auf Package-Ebene hat `rejected` eine andere Semantik (Admission) |
| Phantom-Status | `submitted` und `needs_revision` werden gesetzt aber nie gelesen |
| Legacy-Shim | `accepted: bool` neben `decision: str` |

---

## Ziel-Zustand

### Drei orthogonale Ebenen (hart getrennt)

**Ebene 1: Decision Outcome** — fachliche Entscheidung nach Review/Judge
```
accepted, accepted_with_gaps, rework_required, escalated_to_judge,
closed_unresolved, blocked_by_dependency
```
Kanonisch in `contracts.py`. Alle Schichten importieren diese Konstanten.

**Ebene 2: Lifecycle Status** — operativer Zustand eines Tasks
```
pending, accepted, degraded, blocked, skipped
```
`rejected` wird als Task-Lifecycle-Status **entfernt**. Der Sonderfall "no research at all" wird ueber `closed_unresolved` (Outcome) → `degraded` (Status) modelliert.

**Ebene 3: Admission Decision** — Department-/Synthesis-Freigabe
```
accepted, accepted_with_gaps, rejected
```
Nur auf Package-/Synthesis-Ebene. `rejected` existiert hier weiterhin als Admission-Entscheidung.

### Harte Entscheidung: `rejected` als Task-Status entfernt

| Vorher | Nachher |
|--------|---------|
| Judge: `task_status: "rejected"` | Judge: `task_status: "degraded"` (via `closed_unresolved`) |
| finalize_package "no research": `task_status: "rejected"` | finalize_package: `task_status: "degraded"` (via `closed_unresolved`) |
| OUTCOME_TO_TASK_STATUS: `closed_unresolved → "degraded"` | Unveraendert |

`rejected` bleibt **nur** auf Admission-Ebene (F2/F3 Supervisor-Entscheidung).

### Kanonische Konstanten statt freie Strings

Neues Modul oder Erweiterung von `contracts.py`:

```python
# Canonical vocabulary — all layers import from here
TASK_DECISION_OUTCOMES = frozenset({
    "accepted", "accepted_with_gaps", "rework_required",
    "escalated_to_judge", "closed_unresolved", "blocked_by_dependency",
})
TASK_LIFECYCLE_STATUSES = frozenset({
    "pending", "accepted", "degraded", "blocked", "skipped",
})
ADMISSION_DECISIONS = frozenset({
    "accepted", "accepted_with_gaps", "rejected",
})
```

---

## Patch-Sequenz

### Patch 1 — Kanonische Konstanten in `contracts.py`

**Datei:** `src/orchestration/contracts.py`

Neue frozensets als Single Source of Truth:
- `TASK_LIFECYCLE_STATUSES`
- `ADMISSION_DECISIONS`

`OUTCOME_TO_TASK_STATUS` anpassen: `closed_unresolved → "degraded"` (bereits so), aber `rejected` als Wert entfernen.

### Patch 2 — Judge auf Contract-Vokabular angleichen

**Datei:** `src/agents/judge.py`

- `"decision": "accept"` → `"decision": "accepted"`
- `"decision": "accept_degraded"` → `"decision": "accepted_with_gaps"`
- `"decision": "reject"` → `"decision": "closed_unresolved"`
- `"task_status": "rejected"` → `"task_status": "degraded"` (fuer reject-Fall)

### Patch 3 — `from_judge_result()` vereinfachen

**Datei:** `src/orchestration/contracts.py`

Judge gibt jetzt direkt Contract-Outcomes zurueck. Das `outcome_map` wird trivial:
- `decision`-Feld direkt als Outcome verwenden
- `task_status` weiterhin aus Judge-Result lesen

### Patch 4 — `finalize_package()` "no research" Fall bereinigen

**Datei:** `src/agents/lead.py`

Der Fall "No research at all" aendert sich:
- Vorher: `task_status = "rejected"`
- Nachher: `task_status = "degraded"` mit implizitem `closed_unresolved` Outcome

### Patch 5 — Phantom-Status in `ShortTermMemoryStore` bereinigen

**Datei:** `src/memory/short_term_store.py`

- `"submitted"` → `"pending"`
- `"needs_revision"` → `"pending"`

Die Review-/Rework-Semantik bleibt erhalten ueber `rework_required` (Decision Outcome) und `needs_contract_review` (F4 Runtime-Flag).

### Patch 6 — `accepted: bool` Legacy-Shim entfernen

**Datei:** `src/agents/supervisor.py`

- `accept_department_package()`: `"accepted": decision != "rejected"` entfernen
- `accept_synthesis()`: `"accepted": decision != "rejected"` entfernen

Pruefen ob Konsumenten auf `["accepted"]` statt `["decision"]` zugreifen.

### Patch 7 — Tests anpassen + neue Konsistenz-Tests

**Dateien:** `tests/architecture/test_orchestration.py`, `tests/architecture/test_contracts.py`

Bestehende Tests anpassen:
- Judge-Tests: `"accept"` → `"accepted"`, `"accept_degraded"` → `"accepted_with_gaps"`, `"reject"` → `"closed_unresolved"`
- Judge reject: `task_status` von `"rejected"` auf `"degraded"` aendern

Neue Tests:
- `test_judge_uses_contract_vocabulary` — Judge-Decisions sind direkt Contract-Outcomes
- `test_no_phantom_status_in_short_term_store` — `submitted` und `needs_revision` nicht mehr vorhanden
- `test_no_accepted_bool_in_supervisor_acceptance` — Legacy-Shim entfernt
- `test_vocabulary_consistency_across_layers` — alle Status-Strings in kanonischen Sets
- `test_no_legacy_judge_labels_in_codebase` — `accept`, `accept_degraded`, `reject` als Decision-Labels nicht mehr vorhanden (ausser in Tests/Kommentaren)

---

## Design-Entscheidungen

### `rejected` nur noch auf Admission-Ebene

`rejected` als Task-Lifecycle-Status wird entfernt. Begruendung:
- Ein Task der "no research at all" hat ist `closed_unresolved` → `degraded`, nicht `rejected`
- `rejected` auf Task-Ebene war semantisch doppeldeutig mit `rejected` auf Admission-Ebene
- Klare Trennung: Tasks werden `degraded` (mit dokumentiertem Grund), Packages werden `rejected` (Admission-Entscheidung)

### Judge gibt Contract-Outcomes zurueck

Der Judge ist ein einzelner Agent. Die Contracts sind die autoritative Schicht. Es ist einfacher, den Judge anzugleichen als alle Konsumenten des Judge-Outputs.

### `needs_revision` → `pending` ist sicher

Die Review-/Rework-Semantik bleibt erhalten ueber:
- `rework_required` als Decision Outcome (in `contracts.py`)
- `needs_contract_review` als Runtime-Flag (F4)
- Critic-Review-Artifacts mit `approved: false`

Der Store-Status `needs_revision` war redundant zu diesen Mechanismen.

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Dieselben Entscheidungen heissen in allen Schichten gleich | Judge gibt Contract-Outcomes zurueck, kein Mapping mehr |
| Logs, Tests und Runtime-Codes referenzieren denselben Kanon | Kanonische frozensets, Phantom-Status entfernt |
| Altbegriffe sind entfernt oder explizit gemappt | `submitted` → `pending`, `needs_revision` → `pending`, `accepted: bool` → entfernt, Judge-Labels → Contract-Outcomes |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/orchestration/contracts.py` | Kanonische Konstanten: `TASK_LIFECYCLE_STATUSES`, `ADMISSION_DECISIONS` |
| 2 | `src/agents/judge.py` | Judge-Labels → Contract-Outcomes |
| 3 | `src/orchestration/contracts.py` | `from_judge_result()` vereinfachen |
| 4 | `src/agents/lead.py` | "no research" Fall: `rejected` → `degraded` |
| 5 | `src/memory/short_term_store.py` | Phantom-Status bereinigen |
| 6 | `src/agents/supervisor.py` | `accepted: bool` Shim entfernen |
| 7 | `tests/` | Bestehende Tests anpassen + 5 neue Konsistenz-Tests |

**Reihenfolge:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 7 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 1 -- Kanonische Konstanten** in `contracts.py`
   - `TASK_LIFECYCLE_STATUSES`: `pending, accepted, degraded, blocked, skipped`
   - `ADMISSION_DECISIONS`: `accepted, accepted_with_gaps, rejected`
   - `OUTCOME_TO_TASK_STATUS`: `rejected` als Wert entfernt

2. **Patch 2 -- Judge auf Contract-Vokabular** in `judge.py`
   - `accept` → `accepted`, `accept_degraded` → `accepted_with_gaps`, `reject` → `closed_unresolved`
   - `task_status: "rejected"` → `task_status: "degraded"` (fuer reject-Fall)
   - Alle 6 Return-Pfade aktualisiert (legacy, no-core, reject, partial, no-supporting, full-pass)

3. **Patch 3 -- `from_judge_result()` vereinfacht** in `contracts.py`
   - `outcome_map` entfernt — Judge gibt jetzt direkt Contract-Outcomes zurueck
   - `decision`-Feld wird direkt als Outcome verwendet

4. **Patch 4 -- "no research" Fall bereinigt** in `lead.py`
   - `finalize_package()`: `task_status = "rejected"` → `"degraded"`
   - `_build_fallback_package()`: `task_status = "rejected"` → `"degraded"`

5. **Patch 5 -- Phantom-Status bereinigt** in `short_term_store.py`
   - `"submitted"` → `"pending"` (4 Stellen: main + workspace, ingest + review)
   - `"needs_revision"` → `"pending"` (2 Stellen: main + workspace)

6. **Patch 6 -- `accepted: bool` Shim entfernt** in `supervisor.py`
   - `accept_department_package()`: `"accepted": decision != "rejected"` entfernt
   - `accept_synthesis()`: `"accepted": decision != "rejected"` entfernt

7. **Patch 7 -- Tests angepasst + 5 neue Konsistenz-Tests**
   - Judge-Tests: `"accept"` → `"accepted"`, `"accept_degraded"` → `"accepted_with_gaps"`, `"reject"` → `"closed_unresolved"`, `"rejected"` → `"degraded"`
   - `accepted: bool` Assertions entfernt (5 Stellen)
   - Integration-Test: `"rejected"` → `"degraded"`, Confidence-Assertion angepasst
   - Neue Tests: `test_judge_uses_contract_vocabulary`, `test_no_phantom_status_in_short_term_store`, `test_no_accepted_bool_in_supervisor_acceptance`, `test_task_lifecycle_statuses_are_canonical`, `test_no_legacy_judge_labels_in_judge_module`

### Validierungsergebnisse

```
$ pytest tests/ -> 215 passed in 31.21s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Dieselben Entscheidungen heissen in allen Schichten gleich | Judge gibt Contract-Outcomes zurueck, kein Mapping mehr |
| Logs, Tests und Runtime-Codes referenzieren denselben Kanon | Kanonische frozensets, Phantom-Status entfernt |
| Altbegriffe entfernt oder explizit gemappt | submitted/needs_revision → pending, accepted:bool → entfernt, Judge-Labels → Contract-Outcomes |

---

## Nachschaerfung (Review-Feedback)

**Datum:** 2025-03-25  
**Anlass:** Abschliessendes Review — 2 Restpunkte

### 1. `pending_synthesis` als kanonischer Lifecycle-Status

**Entscheidung:** `pending_synthesis` wird in `TASK_LIFECYCLE_STATUSES` aufgenommen.

**Begruendung:** Es ist ein realer Scheduling-Zustand der sich von `pending` semantisch unterscheidet:
- `pending` = Task wartet auf Ausfuehrung innerhalb eines Departments (kann jederzeit starten)
- `pending_synthesis` = Task wartet auf Abschluss aller Department-Phasen bevor Synthesis beginnt

Das ist eine echte Unterscheidung, kein Phantom-Status.

**Umsetzung:** `TASK_LIFECYCLE_STATUSES` in `contracts.py` erweitert um `pending_synthesis`.

### 2. Kanonische Mengen langfristig als typisierte Literals/Enums

**Aktueller Zustand:** Kanonische Mengen sind `frozenset[str]`. Das ist fuer F7 ausreichend.

**Zielregel:** Naechste Reifestufe waere `Literal`-Types oder `StrEnum` statt `frozenset`, damit der Typchecker frei eingetippte Strings zur Entwicklungszeit erkennt. Das ist kein F7-Blocker, aber die logische Haertung fuer spaetere Iterationen.

**Prioritaet:** P2-Haertung. Basis ist durch die frozensets bereits gelegt.

### Validierung

```
$ pytest tests/ -> 215 passed in 30.92s
```
