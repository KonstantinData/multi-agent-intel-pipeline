# Runtime Step 1: Runner Init + Supervisor Brief

Diese Datei erlaeutert den Prozess aus
`docs/drawio/runtime_step1.drawio`.

Step 1 beschreibt den Start eines initialen Pipeline-Runs in
`src/pipeline_runner.py`, bevor die eigentliche Department-Routing-Phase mit
`run_supervisor_loop(...)` beginnt.

## Zweck

Aus den minimalen Eingaben `company_name` und `web_domain` wird ein
ausfuehrbarer Runtime-Zustand aufgebaut. Am Ende dieses Schritts kennt der
Runtime-Context die Intake-Daten, die initiale Supervisor-Briefing-Struktur,
die geladenen Prozessmuster, die Meeting-Fragen und die initiale Answer
Matrix. Erst danach startet die Supervisor-gesteuerte Department-Ausfuehrung.

Step 1 endet unmittelbar vor diesem Aufruf:

```python
first_pass = _run_first_pass(state, brief=supervisor.brief, on_message=on_message)
# _run_first_pass ruft intern auf:
run_supervisor_loop(
    brief=brief,
    run_context=state.run_context,
    agents=state.agents,
    on_message=on_message,
)
```

## Beteiligte Lanes im Diagramm

Das Draw.io-Diagramm ist in vier Lanes gegliedert:

| Lane | Bedeutung |
| --- | --- |
| Input | UI- oder Caller-Eingaben fuer den neuen Run |
| `pipeline_runner.py` | oeffentlicher Runtime-Einstieg und Initialisierung |
| Supervisor Intake Research | Recherche-Helfer, die der Supervisor beim Briefing-Aufbau nutzt |
| Seeded Runtime State + Handoff | befuellter `RunContext`, erstes Runtime-Event und Uebergabe an Step 2 |

## Beteiligte Codepfade

| Datei | Rolle in Step 1 |
| --- | --- |
| `src/pipeline_runner.py` | startet `run_pipeline(...)`, initialisiert State und baut das Supervisor Brief |
| `src/domain/intake.py` | definiert `IntakeRequest` und `SupervisorBrief` |
| `src/agents/runtime_factory.py` | erzeugt Supervisor, Departments, Synthesis und Report Writer |
| `src/agents/supervisor.py` | baut `SupervisorBrief` und serialisierbare Supervisor-Message |
| `src/research/tools.py` | `build_company_research(...)` fuer Homepage- und Identitaetsdaten |
| `src/research/normalize.py` | normalisiert Domain und erzeugt Homepage-URL |
| `src/research/fetch.py` | laedt den Website-Snapshot |
| `src/research/extract.py` | extrahiert Identitaet, Summary und Industry Hint |
| `src/memory/long_term_store.py` | oeffnet den Long-Term Process Brain Store |
| `src/memory/retrieval.py` | laedt wiederverwendbare Prozessstrategien |
| `src/orchestration/run_context.py` | haelt den run-spezifischen Runtime-Zustand |
| `src/orchestration/meeting_questions.py` | erzeugt Question Registry und Answer Matrix |
| `src/orchestration/supervisor_loop.py` | liefert `emit_message(...)` und startet in Step 2 das Department Routing |

## Vollstaendiger Ablauf

### 1. User- oder UI-Input kommt an

Der Caller ruft `run_pipeline(...)` mit diesen Mindestdaten auf:

- `company_name`
- `web_domain`
- optional `on_message`

`on_message` ist ein Hook fuer UI- oder Streaming-Events. Step 1 funktioniert
auch ohne diesen Hook; dann werden Events nur in der lokalen `messages`-Liste
gesammelt.

### 2. `run_pipeline(...)` startet den Run

Direkt am Anfang von `run_pipeline(...)` werden technische Run-Metadaten
erzeugt:

- `start_time = perf_counter()`
- `run_id = _timestamp_run_id()`
- `run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR)`

`run_id` ist die spaetere Persistenz- und Follow-up-Klammer. `run_dir` ist der
Zielpfad fuer Run-Artefakte, Checkpoints und Exporte.

### 3. Intake wird validiert

Die Initialisierung laeuft ueber `_initialize_run(...)`.

Dort wird zuerst das Intake-Modell erzeugt:

```python
intake = IntakeRequest(company_name=company_name, web_domain=web_domain)
```

`IntakeRequest` trimmt die Eingaben und setzt `language` standardmaessig auf
`"de"`. Wenn `company_name` oder `web_domain` leer sind, wird ein
`ValueError` ausgeloest.

Bei ungueltigem Intake endet Step 1 sofort mit einem Fehlerresultat:

- `status = "failed"`
- leere `messages`
- leere `pipeline_data`
- minimaler `run_context.intake`
- `failed_phase = "intake_validation"`

Es findet dann keine Agent-Erzeugung, keine Recherche und kein Department
Routing statt.

### 4. Domain wird normalisiert

Nach erfolgreicher Intake-Validierung normalisiert der Runner die Domain:

```python
normalized_domain = normalize_domain(intake.web_domain)
```

Diese normalisierte Domain wird im `RunContext.intake` abgelegt und spaeter
fuer Long-Term-Memory-Retrieval, Supervisor Brief und Department-Aufgaben
weiterverwendet.

### 5. Runtime Agents werden erzeugt

Danach erzeugt der Runner die Runtime-Agenten:

```python
agents = create_runtime_agents()
```

Die Agent-Map enthaelt die Runtime-Rollen fuer:

- Supervisor
- Company Department
- Market Department
- Buyer Department
- Contact Department
- Synthesis
- Report Writer

In Step 1 werden diese Agenten nur bereitgestellt. Die Domain Departments
arbeiten noch nicht.

### 6. Long-Term Process Brain wird geoeffnet

Der Runner initialisiert den prozessbezogenen Langzeitspeicher:

```python
memory_store = FileLongTermMemoryStore(LONG_TERM_MEMORY_PATH)
```

Dieser Store ist nicht fuer run-spezifische Unternehmensfakten gedacht. Er
enthaelt nur scrubbed process patterns, zum Beispiel Recherche- oder
Kritikmuster.

Optional kann vor dem Retrieval ein Backfill aus vorhandenen Run-Artefakten
laufen. Das ist durch `LIQUISTO_BACKFILL_LONG_TERM_MEMORY` gesteuert. Das
Diagramm zeigt diesen Schritt als optionalen Backfill ueber Environment Flag.

### 7. `RunContext` wird angelegt

Anschliessend erzeugt `_initialize_run(...)` den run-spezifischen Context:

```python
run_context = RunContext(
    run_id=run_id,
    intake={
        "company_name": intake.company_name,
        "web_domain": intake.web_domain,
        "normalized_domain": normalized_domain,
        "language": intake.language,
    },
)
```

Direkt danach markiert der Runner die aktuelle Phase und schreibt den
Backfill-Status in den Resolution State:

```python
_record_phase(run_context, "initialized")
run_context.resolution_state["long_term_memory"] = {
    "backfill_enabled": backfill_enabled,
    "backfilled_patterns": backfilled_patterns,
}
```

`_record_phase()` setzt `resolution_state["current_phase"]` und stellt
damit sicher, dass ein etwaiger Fehler spaeter dem richtigen Pipeline-Schritt
zugeordnet werden kann. Der `long_term_memory`-Eintrag dokumentiert, ob
der optionale Backfill ausgefuehrt wurde und wie viele Patterns dabei
konsolidiert wurden.

Zu diesem Zeitpunkt existiert der Run Brain als leere, aber strukturierte
Arbeitsflaeche. Department-Artefakte, Packages, Meeting Readiness und Report
Package sind noch leer.

### 8. Prozessstrategien werden geladen

Danach ruft der Runner Prozessmuster aus dem Long-Term Process Brain ab:

```python
run_context.retrieved_strategies = retrieve_strategies(
    memory_store,
    domain=normalized_domain,
    limit=5,
)
```

Zusaetzlich werden rollenspezifische Strategien geladen:

```python
run_context.retrieved_role_strategies = {
    role: retrieve_strategies(
        memory_store,
        domain=normalized_domain,
        role=role,
        limit=3,
    )
    for role in RETRIEVABLE_ROLE_ORDER
}
```

Wichtig: Diese Strategien sind Prozesswissen, keine Zielkunden-Fakten. Die
case-spezifischen Fakten des aktuellen Runs gehoeren spaeter in den Run Brain
und die Department-Artefakte.

### 9. Initialer Runtime State wird zurueckgegeben

`_initialize_run(...)` gibt ein `InitialRunState`-Objekt zurueck. Es enthaelt:

- `start_time`
- `run_id`
- `run_dir`
- validiertes `intake`
- `agents`
- `memory_store`
- `run_context`
- leere `messages`
- `budget_tracker = PhaseBudgetTracker()`
- `normalized_domain`

Damit ist der Runner technisch startklar, hat aber noch kein fachliches
Supervisor Brief erzeugt.

### 10. Supervisor Brief Phase beginnt

Zurueck in `run_pipeline(...)` wird Step 1 fachlich fortgesetzt:

```python
supervisor = _build_supervisor_brief(state, on_message=on_message)
```

`_build_supervisor_brief(...)` setzt zuerst die Runtime-Phase:

```python
_record_phase(state.run_context, "supervisor_brief")
```

Danach ruft der Runner den Supervisor auf:

```python
brief, supervisor_message = state.agents["supervisor"].build_intake_brief(state.intake)
```

### 11. Supervisor fuehrt Intake Research aus

Der Supervisor interpretiert in Step 1 keine Department-Fakten. Er baut nur ein
initiales Intake Brief. Dafuer nutzt er:

```python
research = build_company_research(intake.web_domain, intake.company_name)
```

`build_company_research(...)` laeuft in dieser Reihenfolge:

1. `normalize_domain(domain)`
2. `homepage_url(normalized_domain)`
3. `fetch_website_snapshot(url)`
4. `infer_company_identity(...)`
5. `summarize_visible_text(...)`

Das Ergebnis enthaelt:

- normalisierte Domain
- Homepage-URL
- Website-Snapshot
- sichtbaren Text als Kurzsummary
- verifizierten Unternehmensnamen
- verifizierten Legal Name, falls ableitbar
- Name Confidence

### 12. Supervisor leitet einen Industry Hint ab

Aus dem Website-Snapshot und der Summary erzeugt der Supervisor einen
branchenbezogenen Hinweis:

```python
industry_hint = infer_industry(
    title=str(snapshot.get("title", "")),
    description=str(snapshot.get("meta_description", "")),
    text=str(research.get("summary", "")),
)
```

Dieser `industry_hint` ist nur ein Startsignal fuer die nachfolgende
Department-Arbeit. Die spaetere domain-level Interpretation gehoert nicht in
Step 1, sondern in die Departments und Synthesis.

### 13. `SupervisorBrief` wird gebaut

Der Supervisor erstellt ein typisiertes `SupervisorBrief` mit:

- submitted company name
- submitted web domain
- verified company name
- verified legal name
- name confidence
- website reachability
- homepage URL
- page title
- meta description
- raw homepage excerpt
- normalized domain
- industry hint
- observations
- owned source entry fuer die Homepage
- fetch error type und fetch error message

Das Brief ist das fachliche Startartefakt fuer die Supervisor-kontrollierte
Department-Zuweisung.

### 14. Supervisor Message wird erzeugt

Zusammen mit dem Brief erzeugt der Supervisor eine serialisierbare Message:

```python
{
    "section": "supervisor_brief",
    "payload": asdict(brief),
    "status": "ready_for_department_routing",
}
```

Das Diagramm zeigt diesen Status als erstes Runtime-Signal vor dem Handoff.

### 15. `RunContext` wird mit Step-1-Daten befuellt

Nach dem Supervisor-Aufruf schreibt der Runner die Briefing-Daten in den
Runtime Context:

```python
state.run_context.supervisor_brief = supervisor_message["payload"]
state.run_context.question_registry = build_question_registry()
state.run_context.answer_matrix = build_initial_answer_matrix()
```

Damit sind die Meeting-Fragen und die initiale Antwortmatrix vor dem Department
Routing verfuegbar. Das ist wichtig, weil Department-Ergebnisse spaeter nicht
nur Sections befuellen, sondern Frageabdeckung und Meeting Readiness
fortschreiben.

### 16. Erstes Runtime Event wird emittiert

Der Runner serialisiert die Supervisor Message und emittiert sie:

```python
state.messages.append(
    emit_message(
        on_message,
        agent="Supervisor",
        content=json.dumps(supervisor_message, ensure_ascii=False),
    )
)
```

`emit_message(...)` erzeugt ein Event mit:

- `agent = "Supervisor"`
- `content = <JSON supervisor_message>`
- `type = "agent_message"`

Wenn `on_message` gesetzt ist, wird das Event auch sofort an den Hook
weitergegeben. Unabhaengig davon landet es in `state.messages`.

### 17. Checkpoint nach dem Supervisor Brief

Der aktuelle Code schreibt nach dem Briefing einen Checkpoint:

```python
_write_checkpoint(state.run_dir, "after_supervisor_brief", state.run_context)
```

Dieser Checkpoint ist eine konkrete Code-Ergaenzung zum im Diagramm gezeigten
Handoff-Zustand. Er persistiert den `RunContext` nach Step 1, bevor die erste
Department-Runde startet.

### 18. Uebergabe an Step 2

Step 1 endet mit dem Rueckgabewert von `_build_supervisor_brief(...)`:

```python
return SupervisorBriefResult(
    brief=brief,
    supervisor_message=supervisor_message,
)
```

Der naechste Pipeline-Schritt ist:

```python
first_pass = _run_first_pass(state, brief=supervisor.brief, on_message=on_message)
```

Innerhalb von `_run_first_pass(...)` startet dann:

```python
run_supervisor_loop(...)
```

Ab diesem Punkt beginnt die Supervisor-kontrollierte Department-Routing-Phase.

## Live Objects am Ende von Step 1

Direkt vor `run_supervisor_loop(...)` existieren diese Objekte:

| Objekt | Inhalt |
| --- | --- |
| `brief` | typisiertes `SupervisorBrief` |
| `supervisor_message` | serialisierbares Briefing-Event mit Status `ready_for_department_routing` |
| `state.agents` | alle Runtime-Agenten |
| `state.run_context` | Run Brain mit Intake, Supervisor Brief, Strategien, Question Registry und Answer Matrix |
| `state.messages[0]` | erstes Supervisor Runtime Event |
| `state.budget_tracker` | Budget Tracker, noch ohne First-Pass-Verbrauch |
| `state.run_dir` | Zielordner fuer Checkpoints und Run-Artefakte |

## Was Step 1 noch nicht tut

Step 1 fuehrt ausdruecklich keine Department-Arbeit aus.

Nicht Bestandteil von Step 1:

- keine Department Assignments
- keine AG2 GroupChats
- keine Research-, Review- oder Judge-Artefakte
- keine Department Packages
- keine Package Acceptance Gates
- keine First-Pass-Resolution
- kein Auto-Close
- keine Synthesis
- keine Meeting-Readiness-Finalisierung
- kein Report Writer Runtime Node
- kein finaler JSON- oder PDF-Export

Diese Schritte beginnen erst nach dem Handoff an `run_supervisor_loop(...)`.

## Prozessgrenze

Die wichtigste Grenze des Diagramms ist die Trennung zwischen Vorbereitung und
Ausfuehrung:

- Step 1 bereitet den Run vor und erzeugt das Supervisor Brief.
- Step 2 routet Department-Aufgaben und laesst die bounded AG2 Department
  Groups arbeiten.

Der Supervisor ist in Step 1 Intake- und Control-Plane-Akteur. Er normalisiert,
strukturiert und uebergibt. Die fachliche Domain-Recherche, Evidenzpruefung und
Retry-Logik bleiben ausserhalb dieses Schritts und gehoeren in die Department
Runtime.
