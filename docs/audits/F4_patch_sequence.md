# F4 — Task-Contracts runtime-seitig erzwingen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F4  
**Ziel:** `depends_on` und `output_schema_key` von Design-Dokumentation zu echten Runtime-Bedingungen machen.

---

## Ist-Zustand: Analyse

### Luecke 1: `depends_on` ist keine Runtime-Vorbedingung

`depends_on` wird in `use_cases.py` definiert und ueber `Assignment` bis in `lead.py` transportiert, aber **nirgends wird vor Task-Ausfuehrung geprueft**, ob die Dependency-Tasks abgeschlossen sind.

**Intra-Department:** Die Reihenfolge ist implizit durch die Lead-Prompt-Sequenz gesteuert (der Lead bearbeitet Tasks in der Reihenfolge der `task_sequence`). Aber das ist ein LLM-Verhalten, keine Runtime-Garantie. Ein Lead koennte theoretisch `economic_commercial_situation` vor `company_fundamentals` aufrufen.

**Cross-Department:** Die Phase-Architektur (parallel: Company+Market → sequential: Buyer → Contact) deckt die groebsten Dependencies ab. Aber:
- `peer_companies` haengt von `market_situation` ab — beide laufen in verschiedenen Departments (Buyer vs. Market), und Market laeuft parallel, nicht vor Buyer
- `monetization_redeployment` haengt von `peer_companies` ab — beides im BuyerDepartment, Reihenfolge nur durch Lead-Prompt

**Wo es bricht:** Wenn der Lead die Reihenfolge aendert oder ein Task fehlschlaegt, gibt es keinen Runtime-Guard der verhindert, dass ein abhaengiger Task auf nicht-existierenden Inputs arbeitet.

### Luecke 2: `output_schema_key` wird nicht zur aktiven Validierung genutzt

Die Infrastruktur existiert vollstaendig:
- `SCHEMA_REGISTRY` in `src/models/registry.py` — 12 Task-Level-Schemas registriert
- `resolve_output_schema()` — loest Key zu Pydantic-Klasse auf
- Tests pruefen, dass alle Keys aufloesbar sind

Aber zur Laufzeit:
- `ResearchWorker._merge_payload()` validiert gegen das **Section-Level-Schema** (`CompanyProfile`, `IndustryAnalysis`, etc.)
- **Nicht** gegen das **Task-Level-Schema** (`CompanyFundamentals`, `EconomicSituation`, etc.)
- Das Section-Level-Schema ist breiter — es akzeptiert Felder die zum Task gar nicht gehoeren
- Feld-Leakage: Ein `company_fundamentals`-Task koennte `economic_situation`-Felder setzen, ohne dass das auffaellt

### Luecke 3: Keine Runtime-Folgen bei Contract-Verletzung

Wenn ein Task-Output das vorgesehene Schema verletzt, passiert nichts Deterministisches:
- Der Critic prueft `validation_rules` (Feld-Level-Checks), aber nicht Schema-Konformitaet
- Es gibt keinen Pfad der bei Schema-Verletzung den Task-Status auf `degraded` setzt
- Feld-Leakage zwischen Tasks wird nicht erkannt

### Betroffene Stellen

| Stelle | Datei | Problem |
|--------|-------|---------|
| Task-Ausfuehrung | `src/agents/lead.py` → `run_research()` | Keine `depends_on`-Pruefung vor Ausfuehrung |
| Output-Validierung | `src/agents/worker.py` → `_merge_payload()` | Validiert gegen Section-Schema, nicht Task-Schema |
| Contract-Durchsetzung | `src/agents/lead.py` → `finalize_package()` | Keine Schema-Validierung der Task-Outputs |
| Schema-Registry | `src/models/registry.py` | Infrastruktur vorhanden, aber nicht verdrahtet |

---

## Ziel-Zustand

### `depends_on` als Runtime-Vorbedingung

Vor jeder `run_research(task_key)`-Ausfuehrung prueft der Runtime-Layer:
- Alle Tasks in `depends_on` muessen **dependency-satisfying** sein (nicht nur terminal)
- Fehlende Dependencies → Task wird nicht ausgefuehrt, sondern als `blocked_by_dependency` im `DepartmentRunState` erfasst — als eigener Scheduler-Zustand, nicht als Worker-Fehler

**Dependency-Satisfaction vs. Terminalitaet:**

| Outcome | Terminal? | Dependency-satisfying? |
|---------|-----------|----------------------|
| `accepted` | ja | ja |
| `accepted_with_gaps` | ja | ja |
| `closed_unresolved` | ja | **nein** (nur wenn explizit freigegeben) |
| `rework_required` | nein | nein |
| `escalated_to_judge` | nein | nein |
| `blocked_by_dependency` | ja | nein |

### `output_schema_key` als aktive Validierung

Nach jeder `run_research()`-Ausfuehrung:
- Die **`payload_updates`** (Delta, nicht akkumulierter Payload) werden gegen das task-spezifische Schema validiert
- Validierung erfolgt **vor dem Merge** in `current_payload`
- Schema-Verletzung → strukturierte `ContractViolation`-Records im `TaskArtifact`

### Contract-Verletzung mit abgestuften Runtime-Folgen

Zwei Stufen:

| Schwere | Bedingung | Runtime-Folge |
|---------|-----------|---------------|
| Leicht | Einzelne Felder fehlen oder haben falschen Typ | Violation als Critic-Signal, kein automatischer Status-Wechsel |
| Schwer | Kein einziges erwartetes Feld im Delta vorhanden | Runtime setzt `needs_contract_review` Flag, Critic muss explizit entscheiden |

Der Critic bleibt Entscheider ueber den finalen Review-Ausgang, aber die Runtime setzt bei schweren Violations bereits einen provisorischen Zustand.

---

## Patch-Sequenz

### Patch 0 — Preflight: Statischer Dependency-DAG-Linter

**Datei:** `preflight.py` oder `tests/smoke/test_preflight.py`

Statische Pruefung beim Start / in Tests:
- Jede `depends_on`-Referenz existiert als `task_key` im Backlog
- Keine Dependency zeigt auf einen Task in einem spaeter oder parallel laufenden Department ohne Phase-Garantie
- Cross-Department-Dependencies sind mit der Phase-Architektur kompatibel

```python
def validate_dependency_graph():
    """Verify all depends_on references are resolvable and phase-compatible."""
    all_keys = {t["task_key"] for t in STANDARD_TASK_BACKLOG}
    for task in STANDARD_TASK_BACKLOG:
        for dep in task["depends_on"]:
            assert dep in all_keys, f"{task['task_key']} depends on unknown {dep}"
```

**Warum als Patch 0:**
- Faengt Drift frueh ab, bevor Runtime-Guards greifen muessen
- Kein Runtime-Overhead, nur Preflight/Test-Zeit
- 2026-Best-Practice: Workflow-Graph wird statisch validiert, nicht nur zur Laufzeit

### Patch 1 — `blocked_by_dependency` als Scheduler-Zustand

**Dateien:** `src/orchestration/contracts.py`, `src/agents/lead.py`

**1a — Contracts erweitern:**

`blocked_by_dependency` als neuer Outcome in `TaskDecisionOutcome` und `TERMINAL_OUTCOMES`:

```python
TaskDecisionOutcome = Literal[
    "accepted",
    "accepted_with_gaps",
    "rework_required",
    "escalated_to_judge",
    "closed_unresolved",
    "blocked_by_dependency",   # NEU
]
```

Neuer Helper in `DepartmentRunState`:

```python
def is_dependency_satisfied(self, task_key: str) -> bool:
    """A dependency is satisfied only by accepted or accepted_with_gaps."""
    decision = self.latest_decision(task_key)
    if decision is None:
        return False
    return decision.outcome in ("accepted", "accepted_with_gaps")
```

**1b — Guard in `run_research()`:**

Vor der Worker-Invocation — kein Worker-Call bei unerfuellter Dependency:

```python
for dep_key in assignment.depends_on:
    if not run_state.is_dependency_satisfied(dep_key):
        # Scheduler-Zustand, nicht Worker-Fehler
        blocked_artifact = TaskArtifact(
            task_key=task_key,
            attempt=run_state.attempts.get(task_key, 0) + 1,
            worker=self.researcher_name,
            facts=[],
            open_questions=[f"Blocked: dependency {dep_key} not satisfied"],
        )
        run_state.record_task_artifact(blocked_artifact)
        blocked_decision = TaskDecisionArtifact(
            task_key=task_key,
            attempt=blocked_artifact.attempt,
            outcome="blocked_by_dependency",
            task_status="blocked",
            decided_by="runtime",
            reason=f"Dependency {dep_key} not satisfied",
        )
        run_state.record_decision_artifact(blocked_decision)
        return json.dumps({
            "task_key": task_key,
            "status": "blocked_by_dependency",
            "blocked_by": dep_key,
        })
```

**Warum kein JSON-Fehler-Return:**
Ein Dependency-Block ist ein Scheduler-/Orchestrator-Zustand, kein Worker-Fehler. Er wird als eigener `TaskArtifact` + `TaskDecisionArtifact` erfasst, nicht als Error-String aus der Worker-Schnittstelle.

### Patch 2 — Task-Level-Schema-Validierung gegen `payload_updates`

**Dateien:** `src/agents/lead.py`, `src/orchestration/contracts.py`

**2a — Strukturierte `ContractViolation` in Contracts:**

```python
@dataclass
class ContractViolation:
    field_path: str
    violation_type: str   # "missing_required_field" | "type_mismatch" | "unexpected_field" | "empty_required_value"
    severity: str         # "low" | "medium" | "high"
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field_path": self.field_path,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "message": self.message,
        }
```

Neues Feld in `TaskArtifact`:

```python
contract_violations: list[ContractViolation] = field(default_factory=list)
```

**2b — Validierung in `run_research()` nach Worker-Run:**

```python
# Validate payload_updates against task-specific schema (Delta, not accumulated)
from src.models.registry import resolve_output_schema
schema_cls = resolve_output_schema(assignment.output_schema_key)
raw_updates = report.get("payload_updates", report.get("payload", {}))
violations = _validate_against_task_schema(schema_cls, raw_updates)
artifact.contract_violations = violations

# Severity escalation: if no expected field present at all → needs_contract_review
if violations and all(v.severity == "high" for v in violations):
    artifact.needs_contract_review = True
```

**Warum `payload_updates` und nicht `report["payload"]`:**
- `report["payload"]` ist der akkumulierte Section-Zustand nach Merge
- `payload_updates` ist der natuerliche Delta — das was dieser Task tatsaechlich produziert hat
- Validierung gegen den Delta vermeidet false positives durch Felder anderer Tasks

### Patch 3 — Contract-Violation-Signal im Critic + Runtime-Mindestfolgen

**Datei:** `src/agents/critic.py`

Der Critic erhaelt strukturierte `contract_violations` und beruecksichtigt sie:

```python
contract_violations = report.get("contract_violations", [])
for cv in contract_violations:
    if cv.get("severity") == "high":
        issues.append(f"Contract violation ({cv['violation_type']}): {cv['message']}")
        # Schwere Violation zaehlt als Core-Failure
    elif cv.get("severity") in ("medium", "low"):
        issues.append(f"Contract note ({cv['violation_type']}): {cv['message']}")
```

**Runtime-Mindestfolgen (nicht nur Critic):**
- Leichte Violations → nur Critic-Signal
- Schwere Violations → Runtime setzt `needs_contract_review` Flag im Artifact
- Wenn `needs_contract_review` und Critic trotzdem approved → Judge wird automatisch eskaliert

So wird Contract-Enforcement nicht rein promptbasiert.

### Patch 4 — `finalize_package()` prueft Contract-Konsistenz

**Datei:** `src/agents/lead.py`

In `finalize_package()` vor Package-Assembly:

```python
for assignment in assignments:
    artifact = run_state.latest_artifact(assignment.task_key)
    if artifact and artifact.contract_violations:
        high_count = sum(1 for v in artifact.contract_violations if v.severity == "high")
        if high_count:
            open_questions.append(
                f"Contract violation in {assignment.task_key}: "
                f"{high_count} high-severity schema mismatches"
            )
```

### Patch 5 — Tests

**Datei:** `tests/architecture/test_orchestration.py` und `tests/smoke/test_preflight.py`

Neue Tests:

| Test | Prueft |
|------|--------|
| `test_dependency_graph_is_valid` | Statischer DAG-Linter: alle `depends_on` existieren |
| `test_depends_on_blocks_premature_execution` | Task mit unerfuellter Dependency erzeugt `blocked_by_dependency` Artifact |
| `test_depends_on_allows_after_satisfied` | Task laeuft nach `accepted` Dependency |
| `test_dependency_satisfied_is_not_equal_to_terminal` | `closed_unresolved` ist terminal aber nicht dependency-satisfying |
| `test_output_schema_validation_catches_wrong_fields` | Schema-Violation wird als strukturierte `ContractViolation` erkannt |
| `test_contract_violation_surfaces_in_critic_review` | Critic sieht die Violation |
| `test_severe_violation_triggers_needs_contract_review` | Schwere Violation setzt Flag |
| `test_finalize_records_contract_violations` | Package enthaelt Violation-Hinweise |

---

## Design-Entscheidungen

### Signalgebend mit abgestuften Mindestfolgen

Die Task-Level-Schema-Validierung ist **signalgebend mit Runtime-Mindestfolgen**, nicht rein blockierend und nicht rein informativ:

1. **Leichte Violations** → Critic-Signal, kein automatischer Status-Wechsel
2. **Schwere Violations** → Runtime setzt `needs_contract_review`, Critic muss explizit entscheiden, bei Critic-Approval wird Judge eskaliert
3. **Kein einziges Feld** → Task wird als `degraded` vormarkiert

So wird Contract-Enforcement deterministisch, ohne dass der Critic umgangen wird.

### `blocked_by_dependency` als eigener Zustand

Ein Dependency-Block ist kein Worker-Fehler und kein Critic-Reject. Er ist ein **Scheduler-Zustand** mit eigener Semantik:
- Eigener `TaskDecisionArtifact` mit `decided_by="runtime"`
- Eigener Outcome `blocked_by_dependency`
- Terminal, aber nicht dependency-satisfying (verhindert Kaskaden)

### `is_dependency_satisfied()` != `is_task_terminal()`

Zentrale Architektur-Regel:

| Funktion | Semantik |
|----------|----------|
| `is_task_terminal()` | Keine weitere Arbeit erwartet |
| `is_dependency_satisfied()` | Abhaengiger Task darf starten |

`closed_unresolved` ist terminal (keine Retries mehr), aber **nicht** dependency-satisfying (der abhaengige Task wuerde auf unbrauchbaren Inputs arbeiten). Diese Trennung verhindert, dass Terminalitaet und Verwendbarkeit gleichgesetzt werden.

### Delta-Validierung gegen `payload_updates`

Verbindliche Umsetzung: Validierung gegen `payload_updates` (Worker-Delta), nicht gegen `report["payload"]` (akkumulierter Section-Zustand). Das ist die sauberste Contract-Grenze und vermeidet false positives durch Felder anderer Tasks.

### Strukturierte `ContractViolation` statt `list[str]`

Violations werden als typisierte Records erfasst:

| Feld | Zweck |
|------|-------|
| `field_path` | Welches Feld betroffen ist |
| `violation_type` | `missing_required_field`, `type_mismatch`, `unexpected_field`, `empty_required_value` |
| `severity` | `low`, `medium`, `high` |
| `message` | Menschenlesbare Beschreibung |

Vorteile gegenueber `list[str]`: testbar, filterbar, severity-basierte Eskalation, robust fuer Critic/UI/Logging.

### Statischer DAG-Linter

Nicht nur Runtime-Guards, sondern auch Preflight-Validierung des Workflow-Graphs:
- Jede `depends_on`-Referenz existiert
- Keine Zyklen
- Cross-Department-Dependencies sind mit der Phase-Architektur kompatibel

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Tasks laufen nicht ohne erfuellte Dependencies | `depends_on`-Guard mit `is_dependency_satisfied()` in `run_research()` |
| Task-Outputs werden gegen das vorgesehene Schema validiert | `resolve_output_schema()` gegen `payload_updates` nach Worker-Run |
| Schema-Verletzungen stoppen oder degradieren den Flow deterministisch | Abgestufte Folgen: Critic-Signal + `needs_contract_review` + Judge-Eskalation |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 0 | `tests/smoke/test_preflight.py` | Statischer Dependency-DAG-Linter |
| 1 | `src/orchestration/contracts.py` + `src/agents/lead.py` | `blocked_by_dependency` Zustand + `is_dependency_satisfied()` + Guard |
| 2 | `src/orchestration/contracts.py` + `src/agents/lead.py` | `ContractViolation` Dataclass + Delta-Validierung gegen Task-Schema |
| 3 | `src/agents/critic.py` | Strukturierte Violation-Signale + Runtime-Mindestfolgen |
| 4 | `src/agents/lead.py` | Contract-Konsistenz-Check in `finalize_package()` |
| 5 | `tests/architecture/test_orchestration.py` | 8 neue Tests |

**Reihenfolge:** 0 → 1 → 2 → 3 → 4 → 5 → Validierung.

---

## Risiken und Abwaegungen

- **False Positives bei Schema-Validierung:** Delta-Validierung gegen `payload_updates` minimiert das Risiko. Falls `payload_updates` manchmal nur Teilfelder enthaelt, koennen Pydantic-Defaults die Validierung passieren lassen — das ist akzeptabel, weil der Critic die Feld-Level-Rules separat prueft.
- **Lead-Prompt-Abhaengigkeit:** Der `depends_on`-Guard faengt Reihenfolge-Fehler ab, aber der Lead-Prompt bleibt die primaere Steuerung. Der Guard ist ein Sicherheitsnetz, kein Ersatz.
- **Performance:** Schema-Validierung + Dependency-Check pro `run_research()` sind zwei zusaetzliche Pydantic-Calls. Bei 12 Tasks pro Run vernachlaessigbar.
- **`closed_unresolved` als nicht-dependency-satisfying:** Kann dazu fuehren, dass abhaengige Tasks geblockt werden, obwohl der Upstream-Task "gut genug" war. Das ist beabsichtigt — lieber explizit blocken als auf unbrauchbaren Inputs arbeiten. Falls noetig, kann der Lead den Upstream-Task als `accepted_with_gaps` statt `closed_unresolved` markieren.
- **Kaskaden-Blockierung:** Wenn ein frueherer Task `blocked_by_dependency` ist, werden alle abhaengigen Tasks ebenfalls geblockt. Das ist korrekt — die Kaskade stoppt sauber statt auf Phantom-Inputs zu arbeiten.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 6 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 0 -- Statischer DAG-Linter**
   - `test_dependency_graph_is_valid`: prueft dass alle `depends_on`-Referenzen existieren
   - `test_dependency_graph_has_no_cycles`: prueft Zyklenfreiheit via DFS
   - Beide in `tests/smoke/test_preflight.py`

2. **Patch 1 -- `blocked_by_dependency` als Scheduler-Zustand**
   - `blocked_by_dependency` als neuer Outcome in `TaskDecisionOutcome`
   - `TERMINAL_OUTCOMES` erweitert (blocked ist terminal)
   - `DEPENDENCY_SATISFYING_OUTCOMES` als neue frozenset (nur accepted + accepted_with_gaps)
   - `OUTCOME_TO_TASK_STATUS` erweitert: `blocked_by_dependency -> "blocked"`
   - `is_dependency_satisfied()` auf `DepartmentRunState` -- prueft gegen `DEPENDENCY_SATISFYING_OUTCOMES`
   - Guard in `run_research()`: vor Worker-Invocation, erzeugt `TaskArtifact` + `TaskDecisionArtifact` mit `decided_by="runtime"`

3. **Patch 2 -- Task-Level-Schema-Validierung**
   - `ContractViolation` Dataclass mit `field_path`, `violation_type`, `severity`, `message`
   - `contract_violations` und `needs_contract_review` Felder auf `TaskArtifact`
   - `_validate_payload_against_task_schema()` Helper in `lead.py`
   - Validiert `payload_updates` (Delta) gegen `resolve_output_schema()`
   - Severity-Eskalation: wenn kein erwartetes Feld gefuellt -> alle Violations auf "high"

4. **Patch 3 -- Contract-Violation-Signal im Critic**
   - Critic liest `contract_violations` aus dem Report
   - High-severity -> `issues.append("Contract violation ...")`
   - Medium/low -> `issues.append("Contract note ...")`

5. **Patch 4 -- Contract-Konsistenz in `finalize_package()`**
   - Prueft alle Task-Artifacts auf high-severity Contract-Violations
   - Fuegt Hinweise in `open_questions` des Packages ein

6. **Patch 5 -- Tests (15 neue Tests)**
   - `TestDependencySatisfaction`: 6 Tests (accepted/gaps/closed/blocked/none/subset)
   - `TestContractViolation`: 3 Tests (to_dict/carries/flag)
   - `TestSchemaValidationHelper`: 4 Tests (valid/empty_key/unknown/defaults)
   - `test_dependency_graph_is_valid` + `test_dependency_graph_has_no_cycles`: 2 Smoke-Tests

### Validierungsergebnisse

```
$ pytest tests/ -> 192 passed in 40.31s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Tasks laufen nicht ohne erfuellte Dependencies | Guard in run_research() mit is_dependency_satisfied() |
| Task-Outputs werden gegen das vorgesehene Schema validiert | _validate_payload_against_task_schema() gegen payload_updates |
| Schema-Verletzungen stoppen oder degradieren den Flow deterministisch | Abgestufte Folgen: Critic-Signal + needs_contract_review + Package-Annotation |

### Architekturentscheidungen

- **is_dependency_satisfied() != is_task_terminal()**: Zentrale Trennung umgesetzt
- **blocked_by_dependency als Scheduler-Zustand**: Eigener TaskArtifact + TaskDecisionArtifact, kein JSON-Fehler
- **Delta-Validierung**: Gegen payload_updates, nicht akkumulierten Payload
- **Strukturierte ContractViolation**: Dataclass statt list[str]
- **Abgestufte Mindestfolgen**: Leicht -> Critic, schwer -> needs_contract_review Flag

### Offene Punkte

- `needs_contract_review` Flag wird gesetzt, aber die automatische Judge-Eskalation bei Critic-Approval ist noch nicht verdrahtet (erfordert Aenderung im Lead-Prompt oder in der review_research-Closure)
- Cross-Department-Dependency-Validierung im DAG-Linter prueft noch nicht Phase-Kompatibilitaet (nur Existenz + Zyklenfreiheit)

**Hinweis zu den Akzeptanzkriterien:** Das Zielbild nennt "Critic-Signal + needs_contract_review + Judge-Eskalation" als vollstaendige Kette. Die Judge-Eskalation ist noch nicht implementiert. Das Akzeptanzkriterium "Schema-Verletzungen stoppen oder degradieren den Flow deterministisch" ist durch das needs_contract_review-Flag und die Critic-Signale teilweise erfuellt, aber die automatische Eskalation fehlt als letztes Glied.

---

## Architektur-Review und Zielzustand-Festschreibungen

**Datum:** 2025-03-25  
**Anlass:** Abschliessendes Review nach Umsetzung

### 1. `blocked_by_dependency`-Rueckgabe ist Transportform, kein Worker-Fehler

**Aktueller Zustand:** `run_research()` gibt bei Dependency-Block ein `json.dumps({"status": "blocked_by_dependency", ...})` zurueck. Gleichzeitig werden `TaskArtifact` + `TaskDecisionArtifact` mit `decided_by="runtime"` erzeugt.

**Zielregel:** Die JSON-Rueckgabe ist **ausschliesslich Transportform** fuer die AG2-GroupChat-Kommunikation. Die autoritativen Zustaende sind die Artifacts im `DepartmentRunState`. Kein Downstream-Code darf die JSON-Rueckgabe als Worker-Fehler interpretieren oder daraus Entscheidungen ableiten.

### 2. `blocked_by_dependency`, `ContractViolation` und `needs_contract_review` als kanonische Contracts

**Zielregel:**
- `blocked_by_dependency` ist ein **kanonischer Runtime-Status** im Outcome-Vokabular, nicht ein temporaerer Workaround
- `ContractViolation` ist ein **kanonisches Contract-Modell** mit festem Enum-Vokabular:
  - `violation_type`: `missing_required_field | type_mismatch | unexpected_field | empty_required_value`
  - `severity`: `low | medium | high`
- `needs_contract_review` ist ein **kanonisches Runtime-Flag** auf `TaskArtifact` mit folgender Semantik:
  - **Wann gesetzt:** Ausschliesslich durch die Runtime-Schicht (`_validate_payload_against_task_schema`), wenn alle Contract-Violations severity `high` haben (= kein einziges erwartetes Feld im Delta gefuellt)
  - **Wer konsumiert:** Der Critic sieht die zugehoerigen `contract_violations` als Issues. Die Lead-/Review-Schicht soll das Flag als Eskalations-Trigger nutzen: wenn Critic trotz `needs_contract_review=True` approved, wird automatisch der Judge eskaliert
  - **Deterministische Folge:** `needs_contract_review=True` bedeutet: "dieses Artifact darf nicht ohne explizite Zweitbewertung als accepted gelten". Es ist kein weiches Signal, sondern ein harter Eskalations-Trigger
  - **Wer darf es aendern:** Nur die Runtime-Schicht darf das Flag setzen. Weder Critic noch Lead noch Judge duerfen es zuruecksetzen. Es bleibt als Audit-Trail auf dem Artifact bestehen
- Alle drei Typen sind dauerhaft stabil und duerfen nicht ad-hoc erweitert werden ohne Audit-Dokumentation

### 3. Restpunkte fuer vollstaendige Closure

| Restpunkt | Beschreibung | Empfohlener Zeitpunkt |
|-----------|-------------|----------------------|
| Judge-Eskalation bei `needs_contract_review` | Wenn Critic trotz `needs_contract_review=True` approved, soll automatisch Judge eskaliert werden | Kann als Erweiterung in F4 oder als Teil von F7 erfolgen |
| DAG-Linter Phase-Kompatibilitaet | Pruefung ob Cross-Department-Dependencies mit der Phase-Architektur (parallel/sequential) kompatibel sind | Kann als Erweiterung in F4 oder als Teil von F8 erfolgen |

F4 gilt als **Kern umgesetzt** mit diesen zwei dokumentierten Restpunkten.
