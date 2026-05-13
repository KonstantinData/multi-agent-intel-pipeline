# Runtime Step 2: First Pass + Supervisor Department Routing

Diese Datei erlaeutert den Prozess aus
`docs/drawio/runtime_step2.drawio`.

Step 2 beschreibt die erste fachliche Ausfuehrungsrunde nach dem Supervisor
Brief. Der Einstieg ist `_run_first_pass(...)` in `src/pipeline_runner.py`.
Intern startet dieser Schritt `run_supervisor_loop(...)` in
`src/orchestration/supervisor_loop.py`.

Step 2 endet nach der First-Round-Resolution und dem Checkpoint
`after_first_pass`. Die interne Arbeitsweise einer einzelnen Department-Gruppe
(Lead, Researcher, Critic, Judge, Speaker Selector) ist nicht Bestandteil von
Step 2; sie wird in Step 3 separat erklaert.

## Zweck

Step 2 uebersetzt das Supervisor Brief in konkrete Department-Aufgaben, laesst
die vier Domain Departments in der richtigen Reihenfolge arbeiten und sammelt
deren Ergebnisse in kontrollierten Runtime-Artefakten. Am Ende weiss der Run,
welche Sections bereits verwertbar sind, welche Department Packages vom
Supervisor zugelassen wurden, welche Aufgaben abgeschlossen oder uebersprungen
wurden, wie die Answer Matrix fortgeschrieben wurde und in welchem
Resolution-Bucket der First Pass landet.

Der zentrale Einstieg in `pipeline_runner.py` ist:

```python
def _run_first_pass(
    state: InitialRunState,
    *,
    brief: SupervisorBrief,
    on_message: MessageHook,
) -> FirstPassResult:
    _record_phase(state.run_context, "first_pass")
    sections, department_packages, loop_messages, completed_backlog, department_timings, first_round_resolution = run_supervisor_loop(
        brief=brief,
        run_context=state.run_context,
        agents=state.agents,
        on_message=on_message,
    )
```

## Beteiligte Lanes im Diagramm

Das Draw.io-Diagramm ist in fuenf Lanes gegliedert:

| Lane | Bedeutung |
| --- | --- |
| Step-1 Handoff | Das fertige `SupervisorBriefResult` und der vorbereitete `RunContext` |
| `pipeline_runner.py` | Oeffentlicher Phasen-Orchestrator fuer den First Pass |
| Supervisor Loop | Routing, Assignment-Erzeugung, Parallel-/Sequenzsteuerung und Resolution |
| Departments / AG2 Runtimes | Die vier Domain Departments als bounded Runtime-Aufrufe |
| Run State + Boundary | Answer Matrix, Short-Term Memory, Admission Gates, Budget, Checkpoint |

## Beteiligte Codepfade

| Datei | Rolle in Step 2 |
| --- | --- |
| `src/pipeline_runner.py` | `_run_first_pass(...)`, Budget-Erfassung, `resolution_state`, Checkpoint |
| `src/orchestration/supervisor_loop.py` | `run_supervisor_loop(...)`, Department Routing, Admission Gate, First-Round-Resolution |
| `src/orchestration/task_router.py` | baut `Assignment`-Objekte und gruppiert sie je Department |
| `src/app/use_cases.py` | Quelle des Standard-Backlogs, aus dem die Aufgaben entstehen |
| `src/orchestration/meeting_questions.py` | mapped Task-Status auf Answer-Matrix-Status |
| `src/memory/short_term_store.py` | Run Brain, Working Sets, Delta-Merge fuer parallele Departments |
| `src/orchestration/resolution_controller.py` | klassifiziert den First Pass in einen Resolution Bucket |
| `src/agents/supervisor.py` | liefert `opening_message()` und `accept_department_package(...)` |
| `src/agents/lead.py` / Department Runtime | fuehrt die jeweilige AG2 Department-Gruppe aus; Details folgen in Step 3 |

## Vollstaendiger Ablauf

### 1. Step 1 uebergibt ein fertiges Brief

Step 2 startet nicht direkt aus User-Input. Der vorherige Schritt hat bereits
folgende Objekte erzeugt:

- `SupervisorBriefResult.brief`
- `state.agents`
- `state.run_context`
- `state.run_context.question_registry`
- `state.run_context.answer_matrix`
- `state.messages` mit dem Supervisor-Briefing-Event

`run_pipeline(...)` ruft danach auf:

```python
first_pass = _run_first_pass(state, brief=supervisor.brief, on_message=on_message)
```

### 2. Runner markiert die Phase `first_pass`

`_run_first_pass(...)` setzt zuerst die aktuelle Runtime-Phase:

```python
_record_phase(state.run_context, "first_pass")
```

Damit kann ein spaeterer Fehler oder Checkpoint eindeutig dem First Pass
zugeordnet werden.

### 3. Runner startet den Supervisor Loop

Danach delegiert der Runner die fachliche Department-Steuerung an
`run_supervisor_loop(...)`:

```python
sections, department_packages, loop_messages, completed_backlog, department_timings, first_round_resolution = run_supervisor_loop(
    brief=brief,
    run_context=state.run_context,
    agents=state.agents,
    on_message=on_message,
)
```

Der Runner selbst fuehrt keine Department-Logik aus. Er startet die Phase,
sammelt spaeter die Rueckgabe ein und persistiert den Phasenstand.

### 4. Supervisor Loop sichert Question Registry und Answer Matrix ab

Am Anfang von `run_supervisor_loop(...)` prueft der Loop, ob die Meeting-Fragen
und die Answer Matrix vorhanden sind. Normalerweise wurden sie bereits in Step 1
gebaut. Falls nicht, werden sie hier defensiv erzeugt:

```python
if not run_context.question_registry:
    run_context.question_registry = build_question_registry()
if not run_context.answer_matrix:
    run_context.answer_matrix = build_initial_answer_matrix()
```

Das ist eine Guardrail: Step 2 kann nur sinnvoll arbeiten, wenn jedes Task-
Ergebnis spaeter auf Meeting-Fragen abbildbar ist.

### 5. Lokale Output-Sammler werden initialisiert

Der Loop erzeugt leere Sammler fuer die First-Pass-Ausgabe:

```python
sections: dict[str, Any] = {}
department_packages: dict[str, Any] = {}
messages: list[dict[str, Any]] = []
assignments = build_initial_assignments(brief)
department_assignments = build_department_assignments(brief)
completed_backlog: list[dict[str, str]] = []
department_timings: dict[str, float] = {}
```

`sections` sind die reportnahen Section-Payloads. `department_packages` sind die
formal zugelassenen oder abgelehnten Department-Umschlaege. `completed_backlog`
haelt die Status jedes Tasks fest.

### 6. Task Contracts werden aus dem Standard-Backlog gebaut

Die eigentlichen Aufgaben entstehen in `task_router.py`. Jede Aufgabe ist ein
`Assignment` mit fachlichem Ziel, Ziel-Section, Tool-Erlaubnis, Modellwahl,
Abhaengigkeiten und Meeting-Fragen:

```python
@dataclass(frozen=True, slots=True)
class Assignment:
    task_key: str
    assignee: str
    target_section: str
    label: str
    objective: str
    model_name: str
    allowed_tools: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    run_condition: str | None = None
    output_schema_key: str = ""
    industry_hint: str = "n/v"
    question_ids: tuple[str, ...] = ()
```

`build_initial_assignments(...)` fuellt diese Felder aus dem Standard-Backlog:

```python
assignments.append(
    Assignment(
        task_key=str(item["task_key"]),
        assignee=assignee,
        target_section=str(item["target_section"]),
        label=str(item["label"]),
        objective=str(item["objective_template"]).format(
            company_name=brief.company_name,
            industry_hint=industry,
        ),
        model_name=structured_model if "llm_structured" in allowed_tools else chat_model,
        allowed_tools=allowed_tools,
        depends_on=tuple(item.get("depends_on") or []),
        run_condition=item.get("run_condition"),
        output_schema_key=str(item.get("output_schema_key", "")),
        industry_hint=brief.industry_hint,
        question_ids=question_ids_for_task(str(item["task_key"])),
    )
)
```

### 7. Assignments werden je Department gruppiert

`build_department_assignments(...)` gruppiert die Aufgaben nach Department und
Ziel-Section:

```python
def build_department_assignments(brief: SupervisorBrief) -> list[DepartmentAssignment]:
    grouped: dict[tuple[str, str], list[Assignment]] = {}
    for assignment in build_initial_assignments(brief):
        if assignment.assignee not in DEPARTMENT_RESEARCHERS:
            continue
        key = (assignment.assignee, assignment.target_section)
        grouped.setdefault(key, []).append(assignment)
```

Synthesis-Aufgaben werden hier bewusst nicht als Domain-Department ausgefuehrt.
Die Synthesis Phase kommt erst spaeter.

### 8. Supervisor sendet Opening Message und Tasks werden registriert

Der Loop emittiert zuerst eine Supervisor-Nachricht:

```python
messages.append(
    emit_message(
        on_message,
        agent="Supervisor",
        content=agents["supervisor"].opening_message(),
    )
)
```

Danach werden alle Nicht-Synthesis-Tasks im `RunContext.active_tasks`
registriert:

```python
run_context.record_task(
    assignee=assignment.assignee,
    objective=assignment.objective,
    section=assignment.target_section,
    task_key=assignment.task_key,
    model_name=assignment.model_name,
    allowed_tools=assignment.allowed_tools,
)
```

Damit existiert ein nachvollziehbarer Aufgabenplan im Run Brain, bevor die
Departments tatsaechlich arbeiten.

### 9. Company und Market laufen parallel

Der Loop definiert die Ausfuehrungsreihenfolge:

```python
_DEPARTMENT_RUN_ORDER = [
    "CompanyDepartment",
    "MarketDepartment",
    "BuyerDepartment",
    "ContactDepartment",
]
```

Fuer den First-Pass-Start koennen Company und Market parallel laufen:

```python
_PARALLEL_BATCH = {"CompanyDepartment", "MarketDepartment"}
_SEQUENTIAL_AFTER = ["BuyerDepartment", "ContactDepartment"]
```

Wenn beide verfuegbar sind, startet ein `ThreadPoolExecutor`:

```python
with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as pool:
    futures = {}
    for dept_name in parallel_jobs:
        da = dept_assignment_map[dept_name]
        messages.append(
            emit_message(
                on_message,
                agent="Supervisor",
                content=json.dumps(
                    {
                        "department": da.department,
                        "status": "department_assigned",
                        "target_section": da.target_section,
                        "tasks": [{"task_key": a.task_key, "label": a.label, "objective": a.objective} for a in da.assignments],
                    },
                    ensure_ascii=False,
                ),
            )
        )
```

### 10. Parallel-Departments bekommen isolierte Working Sets

Damit Company und Market nicht gleichzeitig denselben Run Brain mutieren,
erhaelt jedes parallele Department ein eigenes Working Set und eine Baseline:

```python
ws = run_context.short_term_memory.create_working_set()
baseline = run_context.short_term_memory.create_working_set()
working_sets[dept_name] = ws
baselines[dept_name] = baseline
futures[pool.submit(_run_single_department, dept_name, da, current_section, dict(sections), ws)] = dept_name
```

`ShortTermMemoryStore.create_working_set()` erzeugt eine Kopie der relevanten
aktuellen State-Anteile:

```python
def create_working_set(self) -> ShortTermMemoryStore:
    ws = ShortTermMemoryStore()
    ws.facts = list(self.facts)
    ws.sources = list(self.sources)
    ws.market_signals = list(self.market_signals)
    ws.buyer_hypotheses = list(self.buyer_hypotheses)
```

Die beiden Departments koennen also lesen, was bisher bekannt ist, aber ihre
neuen Fakten und Reports werden erst nach Abschluss kontrolliert in den
Hauptspeicher zurueckgefuehrt.

### 11. Ein einzelnes Department wird ueber `DepartmentRuntime.run(...)` ausgefuehrt

Die Hilfsfunktion `_run_single_department(...)` ruft die konkrete Department
Runtime auf:

```python
runtime = agents["departments"][dept_name]
result = runtime.run(
    brief=brief,
    assignments=list(dept_assignment.assignments),
    current_section=current_sec,
    current_sections=current_sections,
    memory_store=memory_store,
    role_memory=run_context.retrieved_role_strategies,
    on_message=on_message,
)
```

Das Department liefert drei Dinge zurueck:

- `section_payload`
- `department_messages`
- `package`

Wie dieses Package intern entsteht, ist Step 3.

### 12. Supervisor prueft jedes Department Package

Sobald ein paralleles Department fertig ist, wird sein Package vom Supervisor
zugelassen oder abgelehnt:

```python
acceptance = agents["supervisor"].accept_department_package(department=dept_name, package=package)
_apply_structured_runtime_artifacts(run_context, package)
_apply_acceptance_gate(
    acceptance,
    dept_name=dept_name,
    target_section=da.target_section,
    section_payload=section_payload,
    package=package,
    sections=sections,
    department_packages=department_packages,
)
```

Die Supervisor-Entscheidung steuert, ob der Payload downstream sichtbar wird.
Der rohe Package-Inhalt bleibt aber fuer Diagnose erhalten.

### 13. Strukturierte Runtime-Artefakte werden in den Run Brain geschrieben

`_apply_structured_runtime_artifacts(...)` validiert und uebernimmt strukturierte
Artefakte aus dem Package:

```python
updates = [
    AnswerMatrixUpdate.model_validate(item)
    for item in package.get("answer_matrix_updates", [])
]
```

Fuer jedes Answer-Matrix-Update wird der aktuelle Frageeintrag fortgeschrieben:

```python
matrix_entry["status"] = update.status
matrix_entry["answer"] = update.answer
matrix_entry["notes"] = update.notes
```

Ausserdem werden `GapCandidate` und `EvidencePacket` in die Short-Term Memory
uebernommen:

```python
gaps = [
    GapCandidate.model_validate(item)
    for item in package.get("gap_candidates", [])
]
run_context.short_term_memory.gap_candidates.extend(gaps)
packets = [
    EvidencePacket.model_validate(item)
    for item in package.get("evidence_packages", [])
]
run_context.short_term_memory.evidence_packets.extend(packets)
```

### 14. Admission Gate entscheidet ueber sichtbare Sections

`_apply_acceptance_gate(...)` baut fuer jedes Department einen Envelope:

```python
envelope: dict[str, Any] = {
    "admission": {
        "decision": decision,
        "reason": reason,
        "downstream_visible": decision != "rejected",
    },
    "raw_package": package,
}
```

Die drei Faelle sind:

```python
if decision == "accepted":
    sections[target_section] = section_payload
    envelope["admitted_payload"] = section_payload
elif decision == "accepted_with_gaps":
    sections[target_section] = {**section_payload, "_admission": "accepted_with_gaps"}
    envelope["admitted_payload"] = section_payload
else:
    sections[target_section] = _blocked_section_artifact(reason, open_questions)
    envelope["admitted_payload"] = None
```

Wichtig: `sections` enthaelt nur das, was nach Supervisor-Gate downstream
verwendet werden darf. `department_packages` speichert zusaetzlich das rohe
Package.

### 15. Task-Status und Answer Matrix werden fortgeschrieben

Nach der Package-Pruefung wird jeder Task-Status aus `completed_tasks`
uebernommen:

```python
status_by_task = {task["task_key"]: task["status"] for task in package.get("completed_tasks", [])}
for assignment in da.assignments:
    task_status = status_by_task.get(assignment.task_key, "degraded")
    run_context.update_task_status(task_key=assignment.task_key, status=task_status)
    run_context.short_term_memory.task_statuses[assignment.task_key] = task_status
    _update_answer_matrix_from_task(assignment, task_status)
```

Die Status-Abbildung kommt aus `meeting_questions.py`:

```python
def matrix_status_for_task_status(task_status: str) -> str:
    if task_status == "accepted":
        return "answered"
    if task_status in {"degraded", "blocked"}:
        return "partially_answered"
    if task_status == "skipped":
        return "blocked"
    return "pending"
```

Dadurch wird nicht nur dokumentiert, dass ein Department fertig ist. Es wird
auch sichtbar, welche Meeting-Fragen jetzt beantwortet, teilweise beantwortet
oder blockiert sind.

### 16. Parallel-Deltas werden deterministisch gemerged

Nach Abschluss von Company und Market werden nur die neuen Writes in den
Hauptspeicher uebernommen:

```python
for dept_name in parallel_jobs:
    ws = working_sets.get(dept_name)
    baseline = baselines.get(dept_name)
    if ws and baseline:
        delta = ws.delta_from(baseline)
        run_context.short_term_memory.merge_from(delta)
```

Die Reihenfolge ist die kanonische Department-Reihenfolge, nicht die zufaellige
`as_completed(...)`-Reihenfolge. Das macht den Merge reproduzierbarer.

### 17. Buyer laeuft nach Company und Market

Nach der parallelen Phase beginnt die sequenzielle Phase:

```python
for department_name in _SEQUENTIAL_AFTER:
    department_assignment = dept_assignment_map.get(department_name)
    if department_assignment is None:
        continue
```

`BuyerDepartment` laeuft zuerst. Es bekommt die bis dahin zugelassenen Sections
als `current_sections=dict(sections)` und kann damit auf Company- und
Market-Ergebnisse aufbauen.

### 18. Run Conditions koennen Tasks ueberspringen

Vor jedem sequenziellen Department prueft der Loop generische
`run_condition`-Regeln:

```python
pipeline_state = {
    "department_packages": department_packages,
    "task_statuses": dict(run_context.short_term_memory.task_statuses),
}
runnable, skipped_tasks = evaluate_run_conditions(
    list(department_assignment.assignments),
    pipeline_state=pipeline_state,
)
```

Ein Beispiel aus `task_router.py`:

```python
_CONDITION_EVALUATORS: dict[str, Any] = {
    "buyer_department_has_prioritized_firms": lambda state: _is_admitted_with_points(
        state.get("department_packages", {}), "BuyerDepartment",
    ),
    "contact_discovery_completed": lambda state: (
        state.get("task_statuses", {}).get("contact_discovery") in ("accepted", "degraded")
    ),
}
```

Nicht erfuellte Bedingungen erzeugen `skipped`-Eintraege. Diese werden ebenfalls
in Task-Status, Short-Term Memory und Answer Matrix geschrieben.

### 19. Contact bekommt Buyer-Kandidaten aus dem Upstream-Kontext

`ContactDepartment` laeuft nach Buyer. Vor dem Runtime-Aufruf wird der aktuelle
Contact-Kontext mit Buyer-Kandidaten angereichert, falls solche im
`market_network` stehen:

```python
if department_name == "ContactDepartment":
    market_payload = sections.get("market_network", {})
    buyer_candidates: list[str] = []
    for tier_key in ("downstream_buyers", "service_providers", "cross_industry_buyers"):
        for company in market_payload.get(tier_key, {}).get("companies", []):
```

Wenn echte Namen gefunden werden, landen sie in `current_section`:

```python
if buyer_candidates:
    current_section = {**current_section, "buyer_candidates": buyer_candidates}
```

So arbeitet Contact nicht blind, sondern auf Basis der vorher priorisierten
Buyer- oder Redeployment-Routen.

### 20. Token Guardrails werden im sequenziellen Teil geprueft

Nach jedem sequenziellen Department prueft der Loop die bereits verbrauchten
Tokens aus der Short-Term Memory:

```python
snapshot = run_context.short_term_memory.snapshot()
totals = snapshot.get("usage_totals", {})
total_tokens = int(totals.get("total_tokens", 0) or 0)
if total_tokens >= HARD_TOKEN_CAP:
    logging.warning(
        "HARD token cap reached (%d >= %d) after %s — aborting remaining departments.",
        total_tokens, HARD_TOKEN_CAP, department_name,
    )
    break
```

Bei Soft Budget wird nur gewarnt; bei Hard Cap werden restliche Departments
abgebrochen.

### 21. First-Round-Resolution wird klassifiziert

Wenn die Department-Runde beendet ist, ruft der Loop den
`ResolutionController` auf:

```python
controller = ResolutionController()
first_round_resolution = controller.classify(
    sections=sections,
    department_packages=department_packages,
    answer_matrix=run_context.answer_matrix,
    task_statuses=dict(run_context.short_term_memory.task_statuses),
)
```

Das Ergebnis wird als Runtime-Event emittiert:

```python
messages.append(
    emit_message(
        on_message,
        agent="Supervisor",
        content=json.dumps({"status": "first_round_resolution", **first_round_resolution}, ensure_ascii=False),
    )
)
```

Der moegliche Bucket wird in Step 4 genauer erklaert. In Step 2 ist wichtig:
Die Klassifikation passiert nach der ersten Department-Runde, aber bevor
Synthesis laeuft.

### 22. Synthesis wird bewusst noch nicht gestartet

Der Code markiert diese Grenze explizit:

```python
# Strategic Synthesis Department is intentionally not run here.  The public
# pipeline orchestrator runs it after first-round resolution and optional
# auto-close so synthesis sees the final answer matrix for the domain round.
```

Step 2 erzeugt also die Grundlage fuer Auto-Close und Synthesis, fuehrt aber
keinen finalen Gesamtbericht zusammen.

### 23. Supervisor Loop gibt ein typisiertes Result zurueck

Der Loop gibt ein `SupervisorLoopResult` zurueck:

```python
return SupervisorLoopResult(sections, department_packages, messages, completed_backlog, department_timings, first_round_resolution)
```

Dieses Result geht zurueck an `_run_first_pass(...)`.

### 24. Runner uebernimmt Messages und Backlog-Status

Zurueck in `pipeline_runner.py` werden die Loop-Messages in die globale
Run-Message-Liste uebernommen:

```python
state.messages.extend(loop_messages)
```

Der `completed_backlog` wird in die Short-Term Memory gespiegelt:

```python
state.run_context.short_term_memory.task_statuses.update(
    {item["task_key"]: item["status"] for item in completed_backlog}
)
```

### 25. Runner erfasst First-Pass-Tokenverbrauch

Der Runner liest den Memory-Snapshot und erfasst den Tokenverbrauch fuer die
Phase:

```python
first_pass_snapshot = state.run_context.short_term_memory.snapshot()
first_pass_tokens = int(first_pass_snapshot.get("usage_totals", {}).get("total_tokens", 0) or 0)
state.budget_tracker.record_phase_tokens("first_pass", first_pass_tokens)
if not state.budget_tracker.check_budget("first_pass"):
    state.budget_tracker.record_stop("first_pass", "token_budget_exceeded")
```

Hinweis aus der Zielarchitektur: Aktuell werden vor allem Researcher-Reports in
`worker_reports` und `usage_totals` erfasst. Lead-, Critic-, Judge- und Coding-
Specialist-LLM-Kosten sind laut `target_runtime_architecture.md` noch ein
bekannter Tracking Gap.

### 26. Runner schreibt First-Pass-Resolution und Auto-Close-Default

Danach wird der `resolution_state` ergaenzt:

```python
state.run_context.resolution_state = {
    **state.run_context.resolution_state,
    "first_round_resolution": first_round_resolution,
    "auto_close": {
        "triggered": False,
        "max_questions": 4,
        "attempted_questions": 0,
        "stop_reason": "not_required",
        "remaining_public_gaps": [],
    },
}
```

Auch wenn Auto-Close erst in Step 4 laeuft, legt Step 2 den Default-Zustand
bereits an.

### 27. Checkpoint `after_first_pass` wird geschrieben

Zum Schluss persistiert der Runner den Run-Kontext:

```python
_write_checkpoint(state.run_dir, "after_first_pass", state.run_context)
```

Damit gibt es einen Crash-Recovery-Punkt direkt nach der ersten Department-
Runde und vor Auto-Close, Synthesis, Readiness und Report Writer.

### 28. Step 2 gibt `FirstPassResult` zurueck

Der Rueckgabewert enthaelt:

```python
return FirstPassResult(
    sections=sections,
    department_packages=department_packages,
    completed_backlog=completed_backlog,
    department_timings=department_timings,
    first_round_resolution=first_round_resolution,
    first_pass_tokens=first_pass_tokens,
)
```

Der naechste Pipeline-Schritt ist `_run_auto_close_if_required(...)`.

## Live Objects am Ende von Step 2

Direkt nach `_run_first_pass(...)` existieren diese Objekte:

| Objekt | Inhalt |
| --- | --- |
| `first_pass.sections` | admission-kontrollierte Section-Payloads oder Blocked Artifacts |
| `first_pass.department_packages` | Supervisor-Envelopes mit `admission`, `raw_package`, optional `admitted_payload` |
| `first_pass.completed_backlog` | Task-Liste mit `task_key`, `label`, `target_section`, `status` |
| `first_pass.department_timings` | Laufzeiten je Department in Sekunden |
| `first_pass.first_round_resolution` | ResolutionController-Klassifikation des First Pass |
| `first_pass.first_pass_tokens` | Tokenverbrauch laut Short-Term-Memory-Snapshot |
| `state.run_context.active_tasks` | registrierte Nicht-Synthesis-Tasks mit aktualisierten Statuswerten |
| `state.run_context.answer_matrix` | Meeting-Fragen mit Status, Notizen und Quellenverweisen |
| `state.run_context.short_term_memory` | Run Brain mit Task-Status, Evidence Packets, Gap Candidates, Department Run States und Usage Totals |
| `state.run_context.resolution_state.first_round_resolution` | persistierte First-Pass-Klassifikation |
| `state.run_context.resolution_state.auto_close` | Default-Zustand fuer den naechsten Schritt |
| `checkpoints/after_first_pass.json` | Checkpoint direkt nach Step 2 |

## Was Step 2 noch nicht tut

Step 2 fuehrt ausdruecklich keine interne Department-Erklaerung und keine
spaetere Finalisierung aus.

Nicht Bestandteil von Step 2:

- keine Detail-Erklaerung der AG2 GroupChat-Turns innerhalb eines Departments
- keine Speaker-Selector-Guardrail-Erklaerung
- keine interne Lead/Researcher/Critic/Judge-Retry-Logik
- kein Auto-Close-Follow-up
- keine User-Selection-Resume-Logik
- keine Synthesis Department-Ausfuehrung
- kein Meeting-Readiness Gate
- kein Final Briefing
- kein Report Writer
- kein finaler JSON-/PDF-Export

Diese Themen folgen in Step 3 bis Step 7.

## Prozessgrenze

Die wichtigste Grenze in Step 2 ist die Trennung zwischen Routing und interner
Department-Arbeit:

- Step 2 entscheidet, welche Departments wann laufen, welche Aufgaben sie
  bekommen, wie ihre Ergebnisse zugelassen werden und wie der Run State danach
  aussieht.
- Step 3 erklaert, wie ein einzelnes Department intern arbeitet, also wie aus
  einem Assignment ein geprueftes `DepartmentPackage` entsteht.

Eine gute Alltagsanalogie: Step 2 ist die Einsatzleitung in einer Redaktion.
Sie verteilt Rechercheauftraege an Ressorts, nimmt die fertigen Dossiers
entgegen, entscheidet, welche Dossiers in die Ausgabe duerfen, markiert offene
Fragen und legt den Zwischenstand ab. Wie ein einzelnes Ressort intern
recherchiert, prueft und nacharbeitet, ist der naechste Schritt.
