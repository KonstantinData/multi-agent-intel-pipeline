# F3 — Synthesis-Acceptance bindend machen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F3  
**Ziel:** Synthesis-Acceptance von pauschaler Auto-Accept-Markierung zu echtem Drei-Outcome-Gate umbauen.

---

## Ist-Zustand: Analyse

### Problem 1: Pauschale Acceptance im Supervisor-Loop

In `supervisor_loop.py` werden Synthesis-Tasks pauschal als `"accepted"` markiert:

```python
for assignment in synthesis_assignments:
    run_context.update_task_status(task_key=assignment.task_key, status="accepted")
    completed_backlog.append({..., "status": "accepted"})
```

`accept_synthesis()` wird hier **nicht aufgerufen**. Jedes Synthesis-Ergebnis wird blind durchgewunken.

### Problem 2: Implizite Qualitätsprüfung in `pipeline_runner.py`

```python
ag2_synthesis = sections.get("synthesis")
if ag2_synthesis and ag2_synthesis.get("target_company", "n/v") != "n/v":
    synthesis = {**ag2_synthesis, "generation_mode": "normal", ...}
else:
    synthesis = {**synthesis_ctx, "generation_mode": "fallback"}
```

Hier gibt es eine implizite Qualitätsprüfung (`target_company != "n/v"`), aber:
- Sie ist kein Gate — beide Pfade fließen weiter in `pipeline_data`
- Der Fallback wird nie als `rejected` oder `degraded` markiert
- Die Logik dupliziert teilweise, was `accept_synthesis()` tun sollte

### Problem 3: `accept_synthesis()` existiert, wird aber nicht genutzt

```python
def accept_synthesis(self, *, synthesis_payload: dict) -> dict[str, str | bool]:
    target_company = synthesis_payload.get("target_company", "n/v")
    accepted = target_company != "n/v"
    return {"accepted": accepted, "reason": ...}
```

- Zu schwach: nur `target_company`-Check
- Kein Drei-Outcome-Modell (analog F2)
- Wird nirgends als Gate eingesetzt

### Downstream-Wirkung

Synthesis-Output fließt direkt in:
1. `pipeline_data["synthesis"]` → Report, PDF, UI
2. `department_packages["SynthesisDepartment"]` → Run-Brain, Follow-up
3. `research_readiness` → Usability-Entscheidung
4. `report_package` → Operator-facing Report

---

## Ziel-Zustand

### Drei-Outcome-Gate (analog F2)

`accept_synthesis()` gibt zurück:

```python
{
    "decision": "accepted" | "accepted_with_gaps" | "rejected",
    "reason": str,
    "confidence": str,
    "generation_mode": str,
}
```

### Entscheidungsregeln

| decision | Bedingung | Downstream-Wirkung |
|----------|-----------|---------------------|
| `accepted` | `target_company` vorhanden + `executive_summary` substanziell + `generation_mode == "normal"` | Synthesis fließt unverändert in pipeline_data |
| `accepted_with_gaps` | `target_company` vorhanden, aber Fallback-Mode oder schwache Evidenz | Synthesis fließt mit Degraded-Marker |
| `rejected` | `target_company == "n/v"` oder kein substanzieller Content | Blocked-Artifact, Fallback-Synthesis als Minimum |

### Steuerungsfluss

1. `supervisor_loop.py`: Synthesis-Ergebnis → `accept_synthesis()` → Task-Status basiert auf `decision`
2. `pipeline_runner.py`: Liest `decision` aus dem Loop-Ergebnis statt eigene implizite Logik
3. `generation_mode` wird vom Gate **bewertet** (als Execution Fact), nicht gesetzt

---

## Patch-Sequenz

### Patch 1 — `accept_synthesis()` auf Drei-Outcome-Gate umstellen

**Datei:** `src/agents/supervisor.py`

Erweiterte Prüfung:
- `target_company` vorhanden und nicht `"n/v"`
- `executive_summary` substanziell (nicht leer, nicht `"n/v"`)
- `generation_mode` berücksichtigen (normal vs. fallback)

### Patch 2 — Supervisor-Loop: `accept_synthesis()` als Gate einsetzen

**Datei:** `src/orchestration/supervisor_loop.py`

- `accept_synthesis()` nach Synthesis-Run aufrufen
- Task-Status basiert auf `decision` statt pauschal `"accepted"`
- Synthesis-Ergebnis mit Admission-Metadata anreichern

### Patch 3 — `pipeline_runner.py`: Implizite Logik durch Gate-Ergebnis ersetzen

**Datei:** `src/pipeline_runner.py`

- `generation_mode` und `confidence` aus dem Synthesis-Ergebnis lesen (vom Gate gesetzt)
- Eigene `target_company != "n/v"`-Prüfung entfernen
- Fallback-Pfad nur noch als Sicherheitsnetz, nicht als parallele Entscheidungslogik

### Patch 4 — Tests

**Datei:** `tests/architecture/test_orchestration.py`

- `test_synthesis_accepted_when_normal_and_substantive`
- `test_synthesis_accepted_with_gaps_on_fallback`
- `test_synthesis_rejected_when_no_target_company`
- `test_synthesis_task_status_reflects_decision`

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Prüfung |
|-----------|---------|
| Keine pauschale Accept-Markierung mehr | Task-Status basiert auf `accept_synthesis()` decision |
| Finale Freigabe hängt von echter Bewertung ab | Drei-Outcome-Gate mit substanzieller Prüfung |
| Ablehnende oder degradierte Fälle sind testbar | Tests für alle drei Pfade |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/agents/supervisor.py` | `accept_synthesis()` Drei-Outcome-Gate |
| 2 | `src/orchestration/supervisor_loop.py` | Gate im Synthesis-Block einsetzen |
| 3 | `src/pipeline_runner.py` | Implizite Logik durch Gate-Ergebnis ersetzen |
| 4 | `tests/architecture/test_orchestration.py` | Synthesis-Acceptance-Tests |

**Reihenfolge:** 1 → 2 → 3 → 4 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** ✅ Alle 4 Patches umgesetzt und validiert

### Durchgeführte Schritte

1. **Analyse des Ist-Zustands**
   - `accept_synthesis()` existierte, wurde aber nirgends als Gate eingesetzt
   - Supervisor-Loop markierte Synthesis-Tasks pauschal als `"accepted"`
   - `pipeline_runner.py` hatte eigene implizite Qualitätsprüfung (`target_company != "n/v"`) parallel zur ungenutzten `accept_synthesis()`
   - Fallback-Synthesis wurde nie als `degraded` klassifiziert

2. **Patch 1 — `accept_synthesis()` Drei-Outcome-Gate**
   - Prüft `target_company`, `executive_summary` (>20 Zeichen), `generation_mode`
   - `accepted`: Target + substanzieller Summary + normal mode
   - `accepted_with_gaps`: Target vorhanden, aber Fallback-Mode oder schwacher Summary
   - `rejected`: Kein Target identifiziert
   - Entscheidungsregel: `has_target` ist die harte Grenze für rejected vs. nicht-rejected; Summary-Qualität und Generation-Mode differenzieren zwischen accepted und accepted_with_gaps

3. **Patch 2 — Supervisor-Loop: Gate eingesetzt**
   - `accept_synthesis()` wird nach Synthesis-Run aufgerufen
   - `_synthesis_admission`-Marker wird ins Synthesis-Ergebnis geschrieben
   - Task-Status basiert auf Decision: `accepted → accepted`, `accepted_with_gaps → degraded`, `rejected → degraded`
   - Observability-Event `synthesis_reviewed` wird emittiert

4. **Patch 3 — `pipeline_runner.py` umgestellt**
   - Liest `_synthesis_admission` aus `sections["synthesis"]`
   - Drei Pfade: `accepted` → AG2-Output direkt, `accepted_with_gaps` → AG2 wenn Target vorhanden sonst Fallback, `rejected` → voller Fallback
   - Eigene `target_company != "n/v"`-Prüfung entfernt — Gate-Entscheidung ist autoritär
   - `generation_mode` wird aus dem Synthesis-Ergebnis gelesen, nicht mehr von pipeline_runner gesetzt

5. **Patch 4 — Tests**
   - `TestSynthesisAcceptanceGate`: 6 Tests für alle Entscheidungspfade
   - Gate-Logik-Korrektur während Testlauf: `has_target + weak_summary` ist `accepted_with_gaps`, nicht `rejected` (Target ist die harte Grenze)

### Validierungsergebnisse

```
$ pytest tests/ -v  → 175 passed in 31.43s
```

Neue Tests:
```
TestSynthesisAcceptanceGate::test_accepted_when_normal_and_substantive       PASSED
TestSynthesisAcceptanceGate::test_accepted_with_gaps_on_fallback             PASSED
TestSynthesisAcceptanceGate::test_accepted_with_gaps_when_summary_weak       PASSED
TestSynthesisAcceptanceGate::test_rejected_when_no_target_company            PASSED
TestSynthesisAcceptanceGate::test_rejected_when_empty_payload                PASSED
TestSynthesisAcceptanceGate::test_synthesis_task_status_reflects_decision     PASSED
```

### Akzeptanzkriterien — Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Keine pauschale Accept-Markierung mehr | ✅ Task-Status basiert auf `accept_synthesis()` decision |
| Finale Freigabe hängt von echter Bewertung ab | ✅ Drei-Outcome-Gate mit Target + Summary + Mode Prüfung |
| Ablehnende oder degradierte Fälle sind testbar | ✅ 6 Tests für alle Pfade |

### Architekturentscheidungen

- **`has_target` als harte Grenze:** Ohne identifiziertes Target-Unternehmen ist die Synthesis wertlos → `rejected`. Mit Target aber schwachem Summary → `accepted_with_gaps` (nutzbar, aber lückenhaft)
- **`_synthesis_admission`-Marker:** Wird ins Synthesis-Dict geschrieben, damit `pipeline_runner.py` die Gate-Entscheidung lesen kann ohne `accept_synthesis()` erneut aufzurufen
- **Kein Envelope für Synthesis:** Anders als F2 (Department-Packages) bekommt Synthesis kein Envelope-Format, weil es keinen raw/admitted-Split braucht — es gibt nur ein Synthesis-Ergebnis, nicht mehrere Departments

### Offene Punkte

- `accepted: bool` Backward-Compat-Feld in `accept_synthesis()` — Entfernung in F7 (Vokabular-Vereinheitlichung)

---

## Nachschärfung (Review-Feedback)

**Datum:** 2025-03-25  
**Anlass:** 4 Architektur-Anmerkungen + 1 fehlender Test

### Befund und Maßnahmen

| # | Anmerkung | Befund | Maßnahme |
|---|-----------|--------|----------|
| 1 | `generation_mode` darf vom Gate nur gelesen, nicht gesetzt werden | ✅ Code war bereits korrekt — Gate liest `generation_mode` als Execution Fact. `pipeline_runner.py` liest es aus dem AG2-Ergebnis. | Doku-Korrektur: „generation_mode wird vom Gate gesetzt“ → „generation_mode wird vom Gate bewertet“ |
| 2 | `accepted_with_gaps` sollte nicht nur an Fallback hängen | Gate-Logik deckt auch schwachen Summary bei Normal-Mode ab. Fehlend: dünne Quellenlage, fehlende Pflichtfelder, Cross-Domain-Konsistenz. | Dokumentiert als bekannte Einschränkung — Synthesis hat kein Critic/Judge-System wie Departments. Erweiterung möglich wenn Synthesis-Critic eingeführt wird. |
| 3 | Rejected sollte Blocked-Artifact sein, nicht Fallback-Synthesis | `pipeline_runner.py` baute im rejected-Pfad eine volle Fallback-Synthesis via `build_synthesis_context()` | **Gefixt:** Rejected-Pfad erzeugt jetzt `{"section_status": "blocked", ...}` mit `generation_mode: "blocked"` |
| 4 | Envelope-Modell für Synthesis (raw/admission/admitted) | `department_packages["SynthesisDepartment"]` war ein nacktes Dict ohne Envelope | **Gefixt:** `supervisor_loop.py` schreibt jetzt `{"admission": {...}, "raw_synthesis": ..., "admitted_synthesis": ...}` |
| 5 | Test: `pipeline_runner` darf keine zweite Entscheidungslogik ausführen | Fehlte | **Gefixt:** `test_pipeline_runner_does_not_override_synthesis_admission` prüft, dass keine `if ag2_synthesis`-Entscheidungsbranches existieren. Zusätzlich: `test_rejected_synthesis_produces_blocked_artifact` |

### Zusätzliche Code-Änderungen

- `supervisor_loop.py`: Synthesis-Envelope `{admission, raw_synthesis, admitted_synthesis}` analog zu F2 Department-Envelopes
- `pipeline_runner.py`: `accepted_with_gaps`-Pfad vereinfacht — keine zweite `target_company`-Prüfung mehr, Gate-Entscheidung ist autoritär
- `pipeline_runner.py`: Rejected-Pfad erzeugt Blocked-Artifact statt Fallback-Synthesis
- 2 neue Tests: `test_pipeline_runner_does_not_override_synthesis_admission`, `test_rejected_synthesis_produces_blocked_artifact`

### Validierung nach Nachschärfung

```
$ pytest tests/ → 177 passed in 30.70s
```

---

## Architektur-Review und Zielzustand-Festschreibungen

**Datum:** 2025-03-25  
**Anlass:** Abschliessendes Architektur-Review vor Uebergang zu F4

Die folgenden fuenf Punkte sind keine Code-Aenderungen, sondern **Architektur-Regeln und Zielzustand-Festschreibungen**, die fuer die weitere Entwicklung verbindlich gelten.

### 1. Admission-Entscheidung != Task-Runtime-Status

**Aktueller Zustand:** Das Mapping `accepted -> accepted`, `accepted_with_gaps -> degraded`, `rejected -> degraded` funktioniert operativ.

**Problem:** `rejected` und `accepted_with_gaps` teilen denselben Task-Status `degraded`. Das vermischt "nutzbar, aber lueckenhaft" mit "nicht admitted".

**Zielregel:** Admission-Decision und Task-Runtime-Status sind **konzeptionell getrennte Vokabulare**. Das Mapping ist ein expliziter, zentraler Uebersetzungsschritt -- kein implizites Gleichsetzen. Die Kanonisierung erfolgt in **F7 (Vokabular-Vereinheitlichung)**. Bis dahin gilt das aktuelle Mapping als bewusster Uebergang.

### 2. `_synthesis_admission`-Marker ist Uebergang -- Envelope ist Zielzustand

**Aktueller Zustand:** `pipeline_runner.py` liest `_synthesis_admission` aus dem Synthesis-Dict. Gleichzeitig existiert das Envelope-Modell `{admission, raw_synthesis, admitted_synthesis}` in `department_packages`.

**Zielregel:** Downstream-Konsumenten lesen **ausschliesslich aus dem Envelope**, nicht parallel aus Marker-Feldern im Payload. `_synthesis_admission` ist ein befristeter Uebergangs-Marker. Sobald `pipeline_runner.py` auf Envelope-Konsum umgestellt ist, wird der Marker entfernt. **Keine doppelten Wahrheiten als Dauerzustand.**

**Umsetzungszeitpunkt:** Kann als Teil von F7 oder als eigenstaendiger Cleanup nach F4 erfolgen.

### 3. Blocked-Artifact als kanonisches Schema

**Aktueller Zustand:** Der Rejected-Pfad erzeugt ein Blocked-Artifact mit den Feldern `section_status`, `reason`, `target_company`, `executive_summary`, `generation_mode`, `confidence`, `key_risks`, `next_steps`, `sources`.

**Zielregel:** Das Blocked-Artifact bekommt ein **formales, kanonisches Schema** mit stabilen Pflichtfeldern:

```python
{
    "section_status": "blocked",       # immer "blocked"
    "reason": str,                      # Ablehnungsgrund
    "open_questions": list[str],        # offene Punkte
    "sources": list[dict],              # leere Liste oder Diagnosequellen
    "generation_mode": "blocked",       # immer "blocked"
}
```

Optionale Felder (`target_company`, `executive_summary`, etc.) duerfen vorhanden sein, aber UI, Report und Follow-up duerfen sich **nur auf die Pflichtfelder** verlassen. Dadurch bleiben alle Downstream-Konsumenten robust gegenueber Variationen im Blocked-Artifact.

**Umsetzungszeitpunkt:** Formalisierung als Pydantic-Modell kann in F7 oder F8 erfolgen.

### 4. Follow-up / Run-Brain: nur `admitted_synthesis` konsumieren

**Aktueller Zustand:** Das Envelope-Modell trennt `raw_synthesis` und `admitted_synthesis`. Aber es gibt noch keinen expliziten Guard, der verhindert, dass Follow-up oder Run-Brain `raw_synthesis` als operative Wahrheit verwenden.

**Zielregel:**
- `raw_synthesis` ist **ausschliesslich Diagnosematerial** -- fuer Debugging, Audit-Trails, Observability
- `admitted_synthesis` ist die **einzige downstream-freigegebene Wahrheit**
- Run-Brain, Follow-up und Report-Pfade duerfen `raw_synthesis` **niemals** als operative Quelle verwenden

**Umsetzungszeitpunkt:** Guard in Follow-up-Pfad als Teil von **F6 (Role-Memory-Retrieval schliessen)**, wo `follow_up.py` ohnehin auf das Envelope-Format umgestellt wird.

### 5. `accepted: bool` Backward-Compat-Feld: befristeter Shim

**Aktueller Zustand:** `accept_synthesis()` und `accept_department_package()` geben beide `accepted: bool` als Backward-Compat neben `decision: str` zurueck.

**Zielregel:** Das `accepted: bool`-Feld ist ein **befristeter Shim**. Es wird entfernt, sobald alle Konsumenten auf `decision` umgestellt sind. Kein neuer Code darf `accepted: bool` als Entscheidungsgrundlage verwenden -- nur `decision` ist autoritativ.

**Umsetzungszeitpunkt:** Entfernung in **F7 (Vokabular-Vereinheitlichung)**.
