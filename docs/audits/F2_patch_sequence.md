# F2 — Supervisor-Acceptance bindend machen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F2  
**Ziel:** Supervisor-Acceptance von reinem Observability-Event zu autoritativem Downstream-Admission-Gate umbauen.

---

## Ist-Zustand: Analyse

### Das Problem

`accept_department_package()` gibt `{"accepted": True/False, ...}` zurück, aber das Ergebnis wird nur als Observability-Event emittiert. Unabhängig vom `accepted`-Wert passiert immer:

```python
sections[da.target_section] = section_payload      # ← fließt immer
department_packages[dept_name] = package            # ← fließt immer
```

### Betroffene Downstream-Pfade

Das Problem ist breiter als nur Synthesis:

1. **Synthesis** — konsumiert `sections` und `department_packages` direkt
2. **Sequenzielle Departments** — `pipeline_state["department_packages"]` wird an `evaluate_run_conditions()` übergeben; ein rejected BuyerDepartment-Package kann trotzdem ContactDepartment-Tasks freischalten
3. **Follow-up** — `department_packages` wird im Run-Brain persistiert und bei Follow-up-Fragen als Evidenzquelle genutzt
4. **Report** — `build_report_package()` liest `department_packages`

F2 ist ein **allgemeiner Downstream-Admission-Fix**, nicht nur ein Synthesis-Fix.

### Betroffene Stellen in `supervisor_loop.py`

| Stelle | Zeile(n) | Kontext |
|--------|----------|---------|
| Parallel-Batch (Company+Market) | ~135–160 | `as_completed` Loop |
| Parallel-Fallback (single) | ~162–175 | Einzellauf-Fallback |
| Sequential (Buyer, Contact) | ~255–280 | Sequenzielle Phase |

### Aktuelles Rückgabeformat von `accept_department_package()`

```python
{
    "accepted": bool,
    "reason": str,
    "open_questions_present": bool,
    "substantive_content": bool,
    "accepted_tasks": int,
    "total_tasks": int,
}
```

---

## Ziel-Zustand

### Admission-Entscheidungsmodell

`accept_department_package()` gibt eine explizite Admission-Entscheidung zurück:

```python
{
    "decision": "accepted" | "accepted_with_gaps" | "rejected",
    "reason": str,
    "substantive_content": bool,
    "open_questions_present": bool,
    "accepted_tasks": int,
    "total_tasks": int,
}
```

- `substantive_content` bleibt als **Signal**, aber die **Entscheidungsklasse** ist `decision`
- Ein Package kann substanziell sein und trotzdem `rejected` (z.B. bei Methodikfehlern)

### Admission-Regeln

| decision | Bedingung | Downstream-Wirkung |
|----------|-----------|---------------------|
| `accepted` | Payload substanziell, mindestens ein Task accepted, nicht alle rejected | Section + Package downstream sichtbar |
| `accepted_with_gaps` | Payload substanziell, nicht alle Tasks rejected, aber Lücken vorhanden | Section mit Degraded-Marker downstream sichtbar |
| `rejected` | Kein substanzieller Content ODER alle Tasks rejected ODER methodisch unzuverlässig | Blocked-Artifact downstream, raw Package nur archiviert |

### Raw vs. Admitted Package Trennung

```python
department_packages[dept] = {
    "admission": {
        "decision": "accepted" | "accepted_with_gaps" | "rejected",
        "reason": str,
        "downstream_visible": bool,
    },
    "raw_package": { ... },           # immer vorhanden — Diagnose/Observability
    "admitted_payload": { ... } | None,  # nur wenn downstream_visible
}
```

### Blocked-Section-Artifact

Rejected Sections werden nicht als `{}` belassen, sondern als typisiertes Blocked-Artifact:

```python
{
    "section_status": "blocked",
    "reason": "CompanyDepartment package rejected — all tasks failed.",
    "open_questions": [...],
    "sources": [],
}
```

---

## Patch-Sequenz

### Patch 1 — `accept_department_package()` auf `decision`-Feld umstellen

**Datei:** `src/agents/supervisor.py`

Rückgabe erweitern um `decision`-Feld. Bisheriges `accepted`-Feld bleibt temporär als Compat.

Entscheidungslogik:
- `accepted` → `has_payload and substantive and completed_tasks and not all_rejected and accepted_tasks > 0`
- `accepted_with_gaps` → `has_payload and substantive and not all_rejected` (aber nicht voll accepted)
- `rejected` → alles andere

### Patch 2 — `_apply_acceptance_gate()` Helper in `supervisor_loop.py`

**Datei:** `src/orchestration/supervisor_loop.py`

Neue Funktion, die nach `accept_department_package()` die Downstream-Admission steuert:

```
_apply_acceptance_gate(
    acceptance, dept_name, target_section, section_payload, package,
    sections, department_packages
) -> None
```

Logik:
- `accepted` → `sections[target] = payload`, Package als admitted envelope
- `accepted_with_gaps` → `sections[target] = payload` (mit Marker), Package als admitted envelope mit `downstream_visible: True`
- `rejected` → `sections[target] = blocked artifact`, Package als envelope mit `downstream_visible: False`

### Patch 3 — Alle drei Acceptance-Stellen auf Helper umstellen

**Datei:** `src/orchestration/supervisor_loop.py`

Die drei Stellen (parallel batch, parallel fallback, sequential) ersetzen das bisherige direkte `sections[...] = ...` / `department_packages[...] = ...` durch `_apply_acceptance_gate()`.

### Patch 4 — `evaluate_run_conditions()` auf Admission-Envelope anpassen

**Datei:** `src/orchestration/task_router.py`

`buyer_department_has_prioritized_firms` muss das Envelope-Format lesen:
- Nur `downstream_visible: True` Packages dürfen Conditions freischalten

### Patch 5 — Synthesis-Konsum auf Admission-Envelope anpassen

**Datei:** `src/orchestration/supervisor_loop.py`

Synthesis-Block: `department_packages` an `SynthesisRuntime.run()` übergeben — Runtime muss nur admitted Packages sehen. Filterung im Loop vor Übergabe.

### Patch 6 — Tests

**Datei:** `tests/architecture/test_orchestration.py`

Neue Tests:
- `test_accepted_package_flows_downstream` — accepted Package erscheint in sections + admitted
- `test_accepted_with_gaps_flows_as_degraded` — degraded Package fließt mit Marker
- `test_rejected_package_blocked_downstream` — rejected Package erzeugt blocked artifact, nicht in admitted
- `test_rejected_package_does_not_trigger_run_condition` — rejected BuyerDepartment schaltet Contact nicht frei
- `test_admission_envelope_has_raw_and_admitted` — Envelope-Struktur korrekt

---

## Validierung

```bash
# 1. Neue Tests
pytest tests/architecture/test_orchestration.py -v -k "acceptance_gate"

# 2. Bestehende Tests (Regression)
pytest tests/

# 3. Manueller Check: Supervisor-Entscheidung im Log
python -c "
from src.agents.supervisor import SupervisorAgent
s = SupervisorAgent()
# Rejected case
r = s.accept_department_package(department='Test', package={'completed_tasks': [{'task_key': 't1', 'status': 'rejected'}], 'section_payload': {}})
print('rejected:', r)
# Accepted case
r = s.accept_department_package(department='Test', package={'completed_tasks': [{'task_key': 't1', 'status': 'accepted'}], 'section_payload': {'company_name': 'Acme'}})
print('accepted:', r)
"
```

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Prüfung |
|-----------|---------|
| Formal nicht akzeptierte Department-Packages gehen nicht in die Synthesis | `test_rejected_package_blocked_downstream` |
| Acceptance-Status beeinflusst den Runtime-Pfad deterministisch | `_apply_acceptance_gate()` steuert sections + packages |
| Rework/Fallback ist explizit modelliert und testbar | Blocked-Artifact + Envelope-Trennung |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/agents/supervisor.py` | `decision`-Feld in Acceptance-Rückgabe |
| 2 | `src/orchestration/supervisor_loop.py` | `_apply_acceptance_gate()` Helper |
| 3 | `src/orchestration/supervisor_loop.py` | Alle 3 Stellen auf Helper umstellen |
| 4 | `src/orchestration/task_router.py` | `evaluate_run_conditions()` Envelope-aware |
| 5 | `src/orchestration/supervisor_loop.py` | Synthesis-Konsum filtern |
| 6 | `tests/architecture/test_orchestration.py` | Acceptance-Gate-Tests |

**Reihenfolge:** 1 → 2+3 → 4 → 5 → 6 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** ✅ Alle 6 Patches umgesetzt und validiert

### Durchgeführte Schritte

1. **Analyse des Ist-Zustands**
   - `accept_department_package()` gab `{"accepted": bool, ...}` zurück — rein informativ
   - Alle drei Acceptance-Stellen in `supervisor_loop.py` schrieben `sections` und `department_packages` unabhängig vom Ergebnis
   - `evaluate_run_conditions()` las `department_packages` direkt — rejected Packages konnten Folge-Departments freischalten
   - Synthesis erhielt alle Packages ungefiltert

2. **Patch 1 — `accept_department_package()` auf `decision`-Feld umgestellt**
   - Rückgabe enthält jetzt `decision: "accepted" | "accepted_with_gaps" | "rejected"`
   - `accepted: bool` bleibt als Backward-Compat
   - Entscheidungslogik: `accepted` nur bei substanziellem Content + mindestens ein Task accepted; `accepted_with_gaps` bei substanziellem Content ohne voll akzeptierte Tasks; `rejected` bei fehlendem Content oder allen Tasks rejected

3. **Patch 2+3 — `_apply_acceptance_gate()` + alle drei Stellen umgestellt**
   - Neuer Helper steuert Downstream-Admission deterministisch
   - `accepted` → Section + Envelope mit `admitted_payload`
   - `accepted_with_gaps` → Section mit `_admission`-Marker + Envelope
   - `rejected` → Blocked-Section-Artifact (`section_status: "blocked"`) + Envelope mit `admitted_payload: None`
   - Envelope-Struktur: `{admission, raw_package, admitted_payload}`
   - Alle drei Stellen (parallel batch, parallel fallback, sequential) auf Helper umgestellt

4. **Patch 4 — `evaluate_run_conditions()` Envelope-aware**
   - `_is_admitted_with_points()` prüft Envelope-Format: nur `downstream_visible: True` Packages schalten Conditions frei
   - Legacy-Format (pre-F2) bleibt als Fallback unterstützt

5. **Patch 5 — Synthesis-Konsum gefiltert**
   - `_admitted_packages_for_synthesis()` filtert `department_packages` auf `downstream_visible: True`
   - Synthesis-Runtime erhält nur admitted Packages

6. **Patch 6 — Tests**
   - `TestSupervisorAcceptanceDecision`: 5 Tests für die drei Entscheidungspfade
   - `TestAcceptanceGate`: 5 Tests für Gate-Mechanik, Envelope-Struktur, Synthesis-Filterung
   - `TestRunConditionEvaluation`: 2 neue Tests für Envelope-Format (admitted + rejected)
   - Bestehende Tests unverändert und weiterhin grün

### Validierungsergebnisse

```
$ pytest tests/ -v  → 169 passed in 47.14s
```

Neue Tests:
```
TestSupervisorAcceptanceDecision::test_accepted_when_substantive_and_tasks_pass       PASSED
TestSupervisorAcceptanceDecision::test_accepted_with_gaps_when_no_task_accepted        PASSED
TestSupervisorAcceptanceDecision::test_rejected_when_all_tasks_failed                  PASSED
TestSupervisorAcceptanceDecision::test_rejected_when_no_substantive_content             PASSED
TestSupervisorAcceptanceDecision::test_rejected_when_empty_payload                     PASSED
TestAcceptanceGate::test_accepted_package_flows_downstream                             PASSED
TestAcceptanceGate::test_accepted_with_gaps_flows_with_marker                          PASSED
TestAcceptanceGate::test_rejected_package_blocked_downstream                           PASSED
TestAcceptanceGate::test_admitted_packages_for_synthesis_filters_rejected               PASSED
TestAcceptanceGate::test_admission_envelope_has_raw_and_admitted                        PASSED
TestRunConditionEvaluation::test_runs_when_buyer_envelope_admitted                      PASSED
TestRunConditionEvaluation::test_skips_when_buyer_envelope_rejected                     PASSED
```

### Akzeptanzkriterien — Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Formal nicht akzeptierte Department-Packages gehen nicht in die Synthesis | ✅ `_admitted_packages_for_synthesis()` filtert rejected |
| Acceptance-Status beeinflusst den Runtime-Pfad deterministisch | ✅ `_apply_acceptance_gate()` steuert sections + packages |
| Rework/Fallback ist explizit modelliert und testbar | ✅ Blocked-Artifact + Envelope-Trennung (raw vs. admitted) |

### Architekturentscheidungen

- **Drei-Outcome-Modell:** `accepted | accepted_with_gaps | rejected` statt binärem `accepted: bool`
- **Envelope statt Mutation:** `{admission, raw_package, admitted_payload}` trennt Diagnose von Downstream-Nutzung
- **Blocked-Artifact statt leer:** Rejected Sections sind typisiert (`section_status: "blocked"`) statt `{}`
- **Legacy-Compat:** `evaluate_run_conditions()` unterstützt sowohl Envelope- als auch Legacy-Format

### Offene Punkte

- Follow-up-Pfad (`follow_up.py`) liest `department_packages` aus dem Run-Brain — muss bei Rehydration das Envelope-Format verstehen (betrifft F6/Follow-up-Konsolidierung)
- `accepted: bool` Backward-Compat-Feld in `accept_department_package()` kann entfernt werden, sobald alle Konsumenten auf `decision` umgestellt sind
