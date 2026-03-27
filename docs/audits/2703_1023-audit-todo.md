# 2703_1023 Audit TODO

**Bezug:** Restpunkte aus `2503_0943-audit-todo.md` + Findings aus Run-Analyse 20260325T160316Z–20260325T171010Z  
**Zweck:** Umsetzungsdatei fuer verbleibende Haertungen und neue Findings nach Abschluss des Erst-Audits  
**Prinzip:** Jedes Finding hat eine klare Patch-Sequenz. Keine Umsetzung ohne Review.

---

## Statusuebersicht

| ID | Thema | Severity | Prioritaet | Status |
|---|---|---:|---:|---|
| R1 | `_synthesis_admission` Marker durch Envelope-Konsum ersetzen | mittel | P1 | Offen |
| R2 | `needs_contract_review` Judge-Eskalation verdrahten | mittel | P1 | Offen |
| R3 | DAG-Linter Phase-Kompatibilitaet pruefen | niedrig-mittel | P1 | Offen |
| R4 | Follow-up-Pfad auf Envelope-Format umstellen | mittel | P1 | Offen |
| R5 | Blocked-Artifact als Pydantic-Modell formalisieren | niedrig-mittel | P2 | Offen |
| R6 | Kanonische Dedup-Keys pro Sammlung | niedrig | P2 | Offen |
| R7 | Merge-Konflikt-Policy (fail-fast vs. warn) | niedrig | P2 | Offen |
| R8 | Kanonische Vokabular-Mengen als StrEnum | niedrig | P2 | Offen |
| R9 | Statische Typpruefung (mypy/pyright) einfuehren | niedrig | P2 | Offen |
| R10 | CI-Pipeline technisch explizit festziehen | niedrig | P2 | Offen |
| R11 | AGENT_SPECS semantisch rahmen / aufteilen | niedrig | P2 | Offen |
| R12 | Drawio-Architekturdiagramm aktualisieren | niedrig | P3 | Offen |
| R13 | `definitions.py` Kompatibilitaets-Shim entfernen | niedrig | P3 | Offen |

---

## R1 — `_synthesis_admission` Marker durch Envelope-Konsum ersetzen

**Herkunft:** F3 Architektur-Review Punkt 2  
**Severity:** mittel  
**Prioritaet:** P1

### Finding
`pipeline_runner.py` liest `_synthesis_admission` aus dem Synthesis-Dict. Gleichzeitig existiert das Envelope-Modell `{admission, raw_synthesis, admitted_synthesis}` in `department_packages`. Doppelte Wahrheit.

### Patch-Sequenz
1. `pipeline_runner.py`: Synthesis-Admission aus `department_packages["SynthesisDepartment"]["admission"]["decision"]` lesen statt aus `sections["synthesis"]["_synthesis_admission"]`
2. `supervisor_loop.py`: `_synthesis_admission` Marker-Injection entfernen
3. Test: `test_pipeline_runner_reads_synthesis_from_envelope`

### Akzeptanzkriterien
- `_synthesis_admission` existiert nicht mehr als Payload-Feld
- Downstream liest ausschliesslich aus dem Envelope

---

## R2 — `needs_contract_review` Judge-Eskalation verdrahten

**Herkunft:** F4 Restpunkt 1  
**Severity:** mittel  
**Prioritaet:** P1

### Finding
`needs_contract_review` Flag wird auf `TaskArtifact` gesetzt, aber die automatische Judge-Eskalation bei Critic-Approval ist nicht verdrahtet.

### Patch-Sequenz
1. `src/agents/lead.py` → `review_research()` Closure: Nach Critic-Approval pruefen ob `artifact.needs_contract_review == True`
2. Wenn ja: automatisch `judge_decision(task_key)` aufrufen statt direkt als accepted weiterzuleiten
3. Test: `test_needs_contract_review_triggers_judge_escalation`

### Akzeptanzkriterien
- Critic-Approval bei `needs_contract_review=True` fuehrt automatisch zu Judge-Eskalation
- Judge-Entscheidung ist final (wie bei normaler Eskalation)

---

## R3 — DAG-Linter Phase-Kompatibilitaet pruefen

**Herkunft:** F4 Restpunkt 2  
**Severity:** niedrig-mittel  
**Prioritaet:** P1

### Finding
Der statische DAG-Linter prueft Existenz und Zyklenfreiheit, aber nicht ob Cross-Department-Dependencies mit der Phase-Architektur (parallel/sequential) kompatibel sind.

### Patch-Sequenz
1. `tests/smoke/test_preflight.py`: Neuer Test `test_cross_department_dependencies_are_phase_compatible`
2. Definiere Phase-Ordnung: `{Company, Market}` parallel → `Buyer` sequential → `Contact` sequential
3. Pruefe: Jede Cross-Department-Dependency zeigt nur auf ein Department das in einer frueheren oder gleichen Phase laeuft
4. Pruefe: Keine Dependency von einem parallelen Department auf das andere parallele Department

### Akzeptanzkriterien
- Test schlaegt wenn eine Cross-Department-Dependency die Phase-Architektur verletzt
- Bestehende Dependencies sind alle kompatibel

---

## R4 — Follow-up-Pfad auf Envelope-Format umstellen

**Herkunft:** F2 offener Punkt, F3 Architektur-Review Punkt 4  
**Severity:** mittel  
**Prioritaet:** P1

### Finding
`follow_up.py` liest `department_packages` aus dem Run-Brain. Nach F2 sind diese im Envelope-Format `{admission, raw_package, admitted_payload}`. Der Follow-up-Pfad muss das Envelope korrekt aufloesen.

### Patch-Sequenz
1. `src/orchestration/follow_up.py`: Alle Stellen die `department_packages[dept]` lesen auf Envelope-Aufloesung umstellen: `pkg.get("raw_package", pkg)` als Fallback
2. Fuer Synthesis: `admitted_synthesis` statt `raw_synthesis` verwenden
3. Test: `test_follow_up_reads_from_envelope_format`
4. Test: `test_follow_up_never_uses_raw_synthesis_as_operative_source`

### Akzeptanzkriterien
- Follow-up-Antworten basieren auf admitted Payloads, nicht auf raw Packages
- Legacy-Format (pre-F2) wird als Fallback unterstuetzt

---

## R5 — Blocked-Artifact als Pydantic-Modell formalisieren

**Herkunft:** F3 Architektur-Review Punkt 3  
**Severity:** niedrig-mittel  
**Prioritaet:** P2

### Finding
Blocked-Artifacts werden als ad-hoc Dicts erzeugt. Pflichtfelder (`section_status`, `reason`, `open_questions`, `sources`, `generation_mode`) sind nicht formal definiert.

### Patch-Sequenz
1. `src/orchestration/contracts.py` oder `src/models/schemas.py`: `BlockedSectionArtifact` Pydantic-Modell
2. `src/orchestration/supervisor_loop.py`: `_blocked_section_artifact()` gibt Pydantic-Instanz zurueck
3. `src/pipeline_runner.py`: Rejected-Synthesis-Pfad nutzt dasselbe Modell
4. Test: `test_blocked_artifact_has_canonical_schema`

### Akzeptanzkriterien
- Alle Blocked-Artifacts sind Pydantic-validiert
- UI/Report/Follow-up koennen sich auf stabile Pflichtfelder verlassen

---

## R6 — Kanonische Dedup-Keys pro Sammlung

**Herkunft:** F5 Follow-up 1  
**Severity:** niedrig  
**Prioritaet:** P2

### Finding
`_dedup_safe()` nutzt JSON-Serialisierung als universellen Dedup-Key. Nicht optimal fuer Sammlungen mit natuerlichen Identifiern.

### Patch-Sequenz
1. `src/memory/short_term_store.py`: `_dedup_sources(items)` mit URL als Key
2. `_dedup_worker_reports(items)` mit `(department, task_key, attempt)` als Key
3. `snapshot()` nutzt spezialisierte Dedup-Funktionen statt `_dedup_safe()` fuer Sources und Worker-Reports
4. Test: `test_source_dedup_by_url`

### Akzeptanzkriterien
- Sources werden nach normalisierter URL dedupliziert
- Worker-Reports nach (department, task_key, attempt)

---

## R7 — Merge-Konflikt-Policy (fail-fast vs. warn)

**Herkunft:** F5 Follow-up 2  
**Severity:** niedrig  
**Prioritaet:** P2

### Finding
`merge_from()` loggt Warning bei Konflikten. Fuer Tests/Preflight waere fail-fast besser.

### Patch-Sequenz
1. `src/memory/short_term_store.py`: `merge_from(other, *, strict=False)` Parameter
2. `strict=True`: raise ValueError bei Konflikten
3. `strict=False`: Warning + Last-Writer-Wins (aktuelles Verhalten)
4. Tests koennen `strict=True` nutzen
5. Test: `test_merge_strict_raises_on_conflict`

### Akzeptanzkriterien
- `strict=True` in Tests faengt unerwartete Konflikte sofort ab
- Production-Code nutzt weiterhin `strict=False`

---

## R8 — Kanonische Vokabular-Mengen als StrEnum

**Herkunft:** F7 Follow-up  
**Severity:** niedrig  
**Prioritaet:** P2

### Finding
`TASK_LIFECYCLE_STATUSES`, `ADMISSION_DECISIONS`, `TaskDecisionOutcome` sind `frozenset[str]` / `Literal`. StrEnum waere typsicherer.

### Patch-Sequenz
1. `src/orchestration/contracts.py`: `TaskDecisionOutcome` als `StrEnum`
2. `TaskLifecycleStatus` als `StrEnum`
3. `AdmissionDecision` als `StrEnum`
4. Alle Konsumenten auf Enum-Vergleich umstellen
5. Tests anpassen

### Akzeptanzkriterien
- Typchecker erkennt falsche Status-Strings zur Entwicklungszeit
- Keine frei eingetippten Strings mehr in Runtime-Code

---

## R9 — Statische Typpruefung (mypy/pyright) einfuehren

**Herkunft:** F10 Follow-up  
**Severity:** niedrig  
**Prioritaet:** P2

### Finding
TypedDicts und NamedTuples aus F10 sind die Basis, aber kein statischer Type-Check-Step existiert.

### Patch-Sequenz
1. `pyproject.toml`: mypy oder pyright Konfiguration
2. Mindestens `src/orchestration/contracts.py`, `src/agents/supervisor.py`, `src/orchestration/supervisor_loop.py` muessen clean durchlaufen
3. CI-Integration (optional)
4. Bekannte Typ-Fehler als `# type: ignore` mit Ticket-Referenz markieren

### Akzeptanzkriterien
- `mypy src/orchestration/contracts.py` laeuft ohne Fehler
- Signatur-Drift wird automatisch erkannt

---

## R10 — CI-Pipeline technisch explizit festziehen

**Herkunft:** F8 Follow-up 1  
**Severity:** niedrig  
**Prioritaet:** P2

### Finding
`TESTING.md` formuliert die CI-Regel normativ, aber keine CI-Konfigurationsdatei ist sichtbar.

### Patch-Sequenz
1. `.github/workflows/test.yml` oder aequivalent: `pytest tests/` explizit
2. Optional: Separate Stage fuer `scripts/manual_validation/`
3. Test: CI-Config referenziert `tests/` als einzige Testwurzel

### Akzeptanzkriterien
- CI fuehrt `pytest tests/` aus, nicht bare `pytest`
- Dokumentation und CI stimmen ueberein

---

## R11 — AGENT_SPECS semantisch rahmen / aufteilen

**Herkunft:** F9 Follow-up 1  
**Severity:** niedrig  
**Prioritaet:** P2

### Finding
`AGENT_SPECS` enthaelt sowohl echte Runtime-Agenten als auch UI-Schritte ohne Agent-Runtime (ReportWriter).

### Patch-Sequenz
1. Entweder: `AGENT_SPECS` dokumentieren als "pipeline step / UI role registry"
2. Oder: Aufteilen in `RUNTIME_AGENT_SPECS` + `PIPELINE_STEP_SPECS`
3. `emit_message(agent=...)` langfristig auf `component=` oder `step=` fuer Nicht-Agenten

### Akzeptanzkriterien
- Klar dokumentiert was ein Agent ist und was ein Pipeline-Schritt
- Keine Verwechslung zwischen Runtime-Agent und UI-Label

---

## R12 — Drawio-Architekturdiagramm aktualisieren

**Herkunft:** F9 Follow-up  
**Severity:** niedrig  
**Prioritaet:** P3

### Finding
Das Drawio-Diagramm zeigt noch ReportWriter als Agent. Nach F9 ist es eine Rendering-Komponente.

### Patch-Sequenz
1. `docs/updated_runtime_architecture.drawio`: ReportWriter als "Report Rendering" statt Agent
2. Admission-Gates (F2/F3) im Diagramm darstellen
3. Memory-Isolation (F5) im Diagramm darstellen

### Akzeptanzkriterien
- Diagramm und Code stimmen ueberein

---

## R13 — `definitions.py` Kompatibilitaets-Shim entfernen

**Herkunft:** F1 offener Punkt  
**Severity:** niedrig  
**Prioritaet:** P3

### Finding
`src/agents/definitions.py` existiert als Kompatibilitaets-Shim der auf `specs.py` + `runtime_factory.py` weiterleitet. Keine bekannten Konsumenten mehr.

### Patch-Sequenz
1. Pruefen: `findstr /s "definitions" src/ ui/ tests/` — keine aktiven Imports
2. Datei entfernen
3. Test: `test_no_definitions_import` Guard

### Akzeptanzkriterien
- `definitions.py` existiert nicht mehr
- Kein Import bricht

---

## Bearbeitungsreihenfolge

### Phase 1 — P1
1. R1 — Synthesis Envelope-Konsum
2. R2 — Judge-Eskalation verdrahten
3. R3 — DAG-Linter Phase-Kompatibilitaet
4. R4 — Follow-up Envelope-Format

### Phase 2 — P2
5. R5 — Blocked-Artifact Pydantic-Modell
6. R6 — Kanonische Dedup-Keys
7. R7 — Merge-Konflikt-Policy
8. R8 — StrEnum Vokabular
9. R9 — Statische Typpruefung
10. R10 — CI-Pipeline
11. R11 — AGENT_SPECS Semantik

### Phase 3 — P3
12. R12 — Drawio-Diagramm
13. R13 — definitions.py Shim entfernen
