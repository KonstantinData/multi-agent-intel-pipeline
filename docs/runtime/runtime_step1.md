# Runtime Step 1: Runner Init + Supervisor Brief

Diese Datei erlaeutert den Prozess aus
`docs/drawio/runtime_step1.drawio`.

Step 1 beschreibt den Start eines initialen Pipeline-Runs in
`src/pipeline_runner.py`, bevor die eigentliche Department-Routing-Phase mit
`run_supervisor_loop(...)` beginnt.

## MVP-Stand 2026-05-12 — Intake-Vertrag und SSRF-Guard

Punkt 1 der `docs/runtime/20260511_runtime_step1_todo.md` wurde so weit
umgesetzt, dass der Intake jetzt als typisierter, auditierbarer Vertrag
arbeitet:

- `NormalizedDomainResult` (`src/research/normalize.py`) liefert pro Eingabe
  einen unveraenderlichen Datensatz mit `canonical_domain`, `canonical_url`,
  `hostname`, `original_hostname`, `public_suffix`, `registrable_domain`,
  `scheme`, `is_valid`, `rejection_code`, `rejection_reason` und einem
  `normalization_steps`-Audit-Trail.
- `IntakeErrorCode` (StrEnum) gibt maschinenlesbare Fehlerklassen: leere
  Eingabe, Platzhalter, geblockte Hosts, nicht erlaubtes Scheme, Userinfo,
  ungueltige Hostnames, fehlende registrierbare Domain.
- IDN-Domains werden ueber das `idna`-Paket (IDNA 2008, UTS-46) in Punycode
  ueberfuehrt; `tldextract` liefert Public-Suffix und registrable domain;
  single-label Eingaben ohne TLD werden hart abgelehnt.
- DNS-Level-SSRF: `src/research/ssrf_guard.py` loest Hostnames vor jedem
  Fetch auf und verwirft Antworten auf private/reservierte IPs. Redirects
  werden ueber einen eigenen `HTTPRedirectHandler` re-validiert, max. 5
  Redirects pro Fetch. `fetch_website_snapshot()` nutzt diesen Guard.
- Intake-Audit: `RunContext.resolution_state["intake_validation"]` enthaelt
  bei Erfolg und Fehler alle Felder fuer UI- und Monitoring-Anzeige.
- Strukturiertes Logging via `src/orchestration/intake_logging.py` emittiert
  pro Intake einen JSON-Event mit `schema_version`, `component`, `phase`,
  `run_id`, `status`, `error_code`, `duration_ms`, `canonical_domain`,
  `registrable_domain`.
- Sub-Phase-Timings (intake_validation, agent_factory, memory_retrieval,
  supervisor_brief) liegen in
  `RunContext.resolution_state["phase_durations_ms"]`.

Offene Backlog-Punkte (Phase 2): vollstaendige OpenTelemetry-Span-Erzeugung,
Prometheus-Counter-Endpoint, IP-Pinning fuer harte DNS-Rebinding-Resistenz,
DrawIO-Diagramm-Synchronisierung mit dem neuen Vertrag.

## MVP-Stand 2026-05-12 — Runtime-Agent-Composition-Vertrag

Punkt 2 der `docs/runtime/20260511_runtime_step1_todo.md` wurde so weit
umgesetzt, dass die Runtime-Agent-Erzeugung jetzt ein typisierter, validierter
und auditierbarer Composition-Vertrag liefert:

- `RuntimeAgents` (`src/orchestration/runtime_agents.py`) ist eine Dataclass
  mit `supervisor`, `departments`, `synthesis`, `report_writer`, `search_cache`,
  `config`, `specs`. `__getitem__`/`__contains__` erhalten die Rueckwaerts-
  kompatibilitaet fuer Legacy-Aufrufe wie `agents["departments"][name]`.
- `DOMAIN_DEPARTMENT_NAMES = ("CompanyDepartment", "MarketDepartment",
  "BuyerDepartment", "ContactDepartment")` ist die einzige Quelle der erlaubten
  Department-Namen — Tippfehler wie `"CompanyDepartmnt"` werden von
  `validate_runtime_agents()` als `unexpected department` zurueckgewiesen.
- `RuntimeAgentSpec` traegt pro Rolle `role_name`, `runtime_type`,
  `required_methods`, `department_name`, `tool_policy`, `model_profile` und
  `observability_role`. Im Snapshot lesbar.
- `SearchCache` (`src/orchestration/runtime_agents.py`) wrappt das geteilte
  Suchcache-Dict; Namespaces sind dict-kompatible, per `RLock` geschuetzte
  `SearchCacheNamespace`-Objekte. Pro `create_runtime_agents()`-Aufruf entsteht
  ein neuer Cache → keine Cache-Vermischung zwischen Runs.
- `RuntimeFactoryConfig` macht die Factory konfigurierbar (Strict-Validation,
  Shared-Cache, Factory-Version, Cache-Strategie, Tool-Policy-Modus,
  Runtime-/Model-Profil, Observability-Flag) ohne Secrets in den RunContext zu
  schreiben.
- `validate_runtime_agents()` prueft Rollenvollstaendigkeit (Supervisor +
  Synthesis + Report-Writer + 4 Departments), Methoden-Praesenz
  (`build_intake_brief`, `accept_department_package`, `accept_synthesis`,
  `opening_message` am Supervisor, `run` an Departments/Synthesis/Report-Writer)
  und fehlende/unerwartete Departments. Strict-Mode wirft
  `RuntimeAgentFactoryError(code, reason, errors)`.
- `RuntimeAgentFactoryError`-Pfad in `run_pipeline()` setzt
  `failed_phase="runtime_agent_factory"`, `error_code` und `error_detail.errors`
  — getrennt vom Intake-Fehlerpfad.
- `RunContext.resolution_state["runtime_agents"]` enthaelt einen non-sensitiven
  Composition-Snapshot (Rollenanzahl, Department-Namen, Cache-Strategie,
  Factory-Version) — keine Prompts, keine Modellparameter, keine Secrets.
- `runtime_agents_healthcheck()` (side-effect-frei, keine LLM-/Web-Calls)
  liefert `{status, errors, snapshot}` und ist in `preflight.py` als
  "Runtime agent composition"-Check integriert.
- Strukturiertes Logging via `src/orchestration/factory_logging.py` emittiert
  pro Factory-Aufruf einen JSON-Event mit `schema_version, component, phase,
  run_id, status, error_code, duration_ms, factory_version, role_count`.

Architektur-Layering: `runtime_agents.py` liegt in `src/orchestration/` und
ist AG2-frei; nur `runtime_factory.py` zieht die schweren Agent-Klassen.
Damit koennen Architecture-Tests den Composition-Vertrag exerzieren, ohne AG2
zu laden.

Offene Backlog-Punkte (Phase 2): Diagramm-Regeneration in
`runtime_step1.drawio`, OpenTelemetry-Span `pipeline.runtime_agent_factory`,
Prometheus-Counter fuer Factory-Fehler.

## Phase-2-Zielbild 2026-05-12 — Storage Boundary

Punkt 3 der `docs/runtime/20260511_runtime_step1_todo.md` wurde lokal als
Storage-Backbone vorbereitet, ohne das MVP von Postgres abhaengig zu machen:

- `src/storage/contracts.py` definiert `LongTermMemoryStore`,
  `RunStateStore`, `RuntimeStorageConfig`, `RuntimeStores` und
  `StorageHealthcheckError`.
- `src/storage/runtime_stores.py` waehlt explizit zwischen `local_dev` und
  `production`. `local_dev` nutzt weiter lokale Artefakte; `production`
  verlangt Postgres/pgvector und scheitert fail-fast, solange kein migriertes
  DSN-Backend aktiviert ist.
- `_initialize_run(...)` erzeugt Stores ueber `create_runtime_stores(...)`,
  fuehrt `stores.healthcheck_required()` vor fachlicher Recherche aus und
  speichert einen non-sensitiven Storage-Snapshot in
  `RunContext.resolution_state["storage"]`.
- Storage-Fehler werden in `run_pipeline(...)` als
  `failed_phase="storage_init"` mit maschinenlesbarem `error_code` gemeldet.
- `sql/20260512_phase2_storage.sql` beschreibt das Ziel-Schema fuer
  `runs`, `run_checkpoints`, `run_events`, `run_artifacts`, `run_locks`,
  `memory_patterns`, `memory_retrieval_events` und `memory_backfill_jobs`.
- `docs/runtime/phase2_storage_architecture.md` dokumentiert die Rollen von
  Hetzner, PostgreSQL/pgvector, Cloudflare Edge/Tunnel/Access und optional R2.

Offen fuer echte Phase-2-Deployment-Arbeit: DSN-gestuetzter
`PostgresLongTermMemoryStore`, transaktionaler `RunStateStore`, reale
Migrationen, Cloudflare-Konfiguration, Draw.io-Regeneration und
Deployment-Smoke-Tests gegen Test-Postgres mit pgvector.

## Phase-2-Zielbild 2026-05-12 — Kontextuelles Retrieval

Punkt 4 der `docs/runtime/20260511_runtime_step1_todo.md` wurde lokal als
Retrieval-Contract umgesetzt:

- `RetrievalContext` (`src/memory/retrieval.py`) transportiert Run-Kontext
  strukturiert: `run_id`, `company_name`, `normalized_domain`, `language`,
  `industry_hint`, `phase`, `target_scope`, `role`, `department`,
  `question_ids`. `company_name` und `normalized_domain` sind explizit
  nicht-persistierbarer Kontext und geben keinen Ranking-Bonus.
- Retrieval laeuft zweistufig: ein minimaler generischer Snapshot in
  `_initialize_run(...)`, danach ein industry-aware Refresh in
  `_build_supervisor_brief(...)`, bevor `run_supervisor_loop(...)` startet.
- Rollen erhalten eigene Scopes (`researcher_strategy`, `critic_heuristics`,
  `judge_principles`, `coding_methods`, `lead_delegation`, `orchestration`)
  und zentrale Limits (`DEFAULT_GENERAL_RETRIEVAL_LIMIT`,
  `DEFAULT_ROLE_RETRIEVAL_LIMIT`).
- `retrieve_strategy_batch(...)` liefert Patterns plus non-sensitiven
  Audit-Snapshot: Query Summary, Trefferzahl, Kandidatenzahl, Rejections,
  Dauer, Fallback-Grund und Policy-Version.
- Das lokale MVP nutzt deterministic score fallback; echte Embedding-/pgvector-
  Aehnlichkeit bleibt an den produktiven Postgres-Store aus Punkt 3 gekoppelt.
- Policy-Gates blockieren unsichere Patterns vor Rueckgabe in den Run Brain:
  Domains, URLs, E-Mails, Personen-/Kontaktfelder, Legal Names und konkrete
  Finanzzahlen.

## MVP-Stand 2026-05-12 — Evidence-Backed Supervisor Brief

Punkt 5 der `docs/runtime/20260511_runtime_step1_todo.md` wurde als
evidence-backed Identity- und Briefing-Contract umgesetzt:

- `src/domain/briefing.py` definiert die Contract-Erweiterungen:
  `EvidenceItem`, `MissingEvidence`, `BriefingFetchAudit`,
  `IdentityConfidence`, `IndustryConfidence`, `BriefingReadiness`,
  `SupervisorBriefMessage` und `validate_supervisor_brief_message(...)`.
- `SupervisorBrief` bleibt rueckwaerts kompatibel, fuehrt aber jetzt
  `schema_version`, `evidence_items`, `missing_evidence`, `fetch_audit`,
  `name_confidence_reason`, `industry_confidence_reason`,
  `briefing_readiness`, `routing_gaps` und `identity_conflict`.
- `build_intake_brief(...)` nutzt den bereits validierten
  `normalized_domain` aus `_initialize_run(...)`; rohe Domain-Varianten werden
  nicht erneut als Briefing-Quelle normalisiert.
- Identity Confidence basiert im MVP auf Homepage-Signalen:
  `high`, `medium`, `low`, `unverified`. Konflikte zwischen Submitted Name und
  Homepage-Titel werden als `identity_conflict` markiert und koennen Routing
  blockieren.
- Industry Confidence ist getrennt: `high`, `low`, `unknown`. Bei nicht
  erreichbarer Homepage bleibt die Industry Confidence `unknown`.
- `fetch_audit` speichert Reachability, final URL, Redirect Chain, HTTP-Status,
  Content-Type, Content-Length, Content-Language, Fetch-Zeitpunkt und
  Fehler-/Blockiergrund.
- Final-URL-Domain-Mismatch wird als `redirect_domain_mismatch` in
  `routing_gaps` und `missing_evidence` sichtbar, statt fremde Homepages still
  als Zielkunden-Evidence zu akzeptieren.
- `supervisor_message` ist versioniert und validiert. Top-Level-Felder:
  `schema_version`, `status`, `briefing_readiness`, `identity_confidence`,
  `industry_confidence`, `routing_gaps`, `evidence_summary`.
- `_build_supervisor_brief(...)` persistiert eine non-sensitive Diagnose in
  `RunContext.resolution_state["supervisor_brief"]` und loggt ein strukturiertes
  `liquisto.supervisor_brief` Event.

## MVP-Stand 2026-05-12 — Step-1-Handoff Contract

Punkt 7 wurde lokal als versionierter Handoff-Contract vorbereitet:

- `src/orchestration/step1_handoff.py` definiert `Step1Handoff`,
  `RuntimeEvent`, `CheckpointInfo`, `Step1ValidationError` und
  `build_step1_handoff(...)`.
- `build_question_registry()` liefert 12 Meeting-Fragen und schreibt pro
  Registry-Eintrag eine stabile `question_id`, die dem Dict-Key entspricht.
- `validate_question_contracts(...)` prueft Registry, Answer Matrix und
  `TASK_TO_QUESTION_IDS`: gleiche Keys, stabile IDs, Pflichtfelder,
  initiale `pending`-Antworten, leere `source_tasks` und passende
  `target_section`.
- Das erste Supervisor Event ist versioniert und sequenziert:
  `event_id`, `run_id`, `sequence`, `timestamp`, `agent`, `type`,
  `schema_version`, `content`, `content_type`, `phase`.
- `_write_checkpoint(...)` schreibt den lokalen JSON-Checkpoint atomar ueber
  `.tmp` + Replace, versieht ihn mit `schema_version` und `checkpoint_hash`
  und liefert `CheckpointInfo`.
- `_build_supervisor_brief(...)` speichert
  `RunContext.resolution_state["step1_handoff"]` mit Intake, Brief,
  Supervisor Message, Registry, Answer Matrix, Retrieval-Snapshots,
  Runtime-Agent-Snapshot, Storage-Snapshot, Budget-Snapshot, erstem Event,
  Checkpoint und Gate-Readiness.
- `run_pipeline(...)` startet `_run_first_pass(...)` nur, wenn
  `handoff_allows_department_routing(...)` den Handoff freigibt.

Bewusst offen fuer Phase 2: transaktionale DB-Checkpoint-Schreibung gegen den
Postgres-Run-State aus Punkt 3, echte OTel-Spans, Alerting und Retry-Policy
fuer produktive DB-/Event-Store-Schreibfehler.

## MVP-Stand 2026-05-12 — Supervisor Intake Research Pipeline

Punkt 6 der `docs/runtime/20260511_runtime_step1_todo.md` wurde lokal als
sichere, evidence-basierte Intake-Research-Pipeline umgesetzt:

- `src/research/contracts.py` definiert versionierte Contracts:
  `WebsiteSnapshot`, `IdentityResolutionResult`, `IndustryInferenceResult`,
  `CompanyResearchResult`, `ResearchIssue` und die MVP-`IDENTITY_SOURCE_REGISTRY`.
- Der reale Runtime-Pfad uebergibt `NormalizedDomainResult` aus
  `_initialize_run(...)` an `build_company_research(...)`. Der String-Pfad ist
  nur noch Legacy-Kompatibilitaet und wird als deprecated markiert.
- `fetch_website_snapshot(...)` nutzt DNS-/Redirect-SSRF-Guards, max. 5
  Redirects, IP-Pinning, kontrollierte Header, Content-Type-Allowlist,
  Response-Groessenlimit, strukturierte Timeout-/TLS-/HTTP-Blockiercodes,
  Content-Hash und non-sensitive Fetch-Diagnosen.
- Der Snapshot extrahiert Title, Meta/OpenGraph, H1/H2, About-/Impressum-Link,
  Sprache, deduplizierten sichtbaren Text, `extraction_quality` und
  `js_content_detected`, ohne Roh-HTML in den RunContext zu schreiben.
- Identity Resolution ist typisiert und trennt Submitted Name, Brand Name,
  `verified_company_name`, leeren MVP-`verified_legal_name`,
  `homepage_name_match`, Confidence und Source-Gaps fuer Phase-2-Quellen.
- Industry Inference ist typisiert, confidence-aware und enthaelt
  Evidence-Felder sowie Alternativen. Der Industry Hint bleibt Startsignal,
  keine verifizierte Department-Wahrheit.
- `CompanyResearchResult` sammelt Warnings/Errors mit Codes wie
  `fetch_timeout`, `blocked_private_host`, `redirect_blocked`,
  `unsupported_content_type`, `text_extraction_empty`, `js_content_detected`,
  `industry_unknown` und `source_gap`.
- `_build_supervisor_brief(...)` persistiert
  `RunContext.resolution_state["intake_research"]` mit Schema-Version,
  Timings, Snapshot-Diagnose, Identity-/Industry-Diagnose, Warnings und Errors.

Bewusst offen: echte externe Identity-Quellen (Handelsregister,
OpenCorporates/Northdata, LinkedIn, Wikidata), Browser Rendering/Playwright,
Anti-Bot-Umgehung, echte OpenTelemetry-Spans, Dashboards und Alerting.

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
| `src/research/contracts.py` | versionierte Intake-Research-Contracts fuer Snapshot, Identity, Industry und Result |
| `src/research/normalize.py` | normalisiert Domain und erzeugt Homepage-URL |
| `src/research/fetch.py` | laedt den Website-Snapshot |
| `src/research/extract.py` | extrahiert Identitaet, Summary und Industry Hint |
| `src/storage/contracts.py` | definiert Store-Vertraege, Healthchecks und non-sensitive Storage-Konfiguration |
| `src/storage/runtime_stores.py` | waehlt Local-Dev- oder Production-Storage-Backend |
| `src/memory/long_term_store.py` | lokaler Long-Term Process Brain Store fuer Development/Tests |
| `src/memory/retrieval.py` | laedt wiederverwendbare Prozessstrategien |
| `src/orchestration/run_context.py` | haelt den run-spezifischen Runtime-Zustand |
| `src/orchestration/meeting_questions.py` | erzeugt Question Registry und Answer Matrix |
| `src/orchestration/step1_handoff.py` | validiert den versionierten Step-1-Handoff, Runtime Event und Checkpoint-Status |
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

### 6. Storage Boundary und Long-Term Process Brain werden geoeffnet

Der Runner initialisiert die explizite Storage-Grenze:

```python
stores = create_runtime_stores(
    runs_root=RUNS_DIR,
    long_term_memory_path=LONG_TERM_MEMORY_PATH,
)
stores.healthcheck_required()
memory_store = stores.long_term_memory
```

Im lokalen Profil ist das weiterhin der dateibasierte
`FileLongTermMemoryStore`. Im Produktionsprofil darf kein File-Store
opportunistisch genutzt werden: fehlendes oder nicht migriertes
Postgres/pgvector fuehrt zu `failed_phase="storage_init"`.

Dieser Store ist nicht fuer run-spezifische Unternehmensfakten gedacht. Er
enthaelt nur scrubbed process patterns, zum Beispiel Recherche- oder
Kritikmuster. Ein historischer Backfill laeuft nicht im normalen
Run-Start-Pfad; er gehoert in Phase 2 in einen expliziten Maintenance-Job.

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
Storage-Status in den Resolution State:

```python
_record_phase(run_context, "initialized")
run_context.resolution_state["storage"] = stores.snapshot()
```

`_record_phase()` setzt `resolution_state["current_phase"]` und stellt
damit sicher, dass ein etwaiger Fehler spaeter dem richtigen Pipeline-Schritt
zugeordnet werden kann. Der `storage`-Eintrag dokumentiert Profil, Backends,
Schema-Version und Health-Ergebnis ohne DSN, Credentials oder andere Secrets.

Zu diesem Zeitpunkt existiert der Run Brain als leere, aber strukturierte
Arbeitsflaeche. Department-Artefakte, Packages, Meeting Readiness und Report
Package sind noch leer.

### 8. Prozessstrategien werden initial generisch geladen

Danach ruft der Runner einen minimalen, generischen Prozessmuster-Snapshot aus
dem Long-Term Process Brain ab:

```python
initial_retrieval_context = RetrievalContext(
    run_id=run_id,
    company_name=intake.company_name,
    normalized_domain=normalized_domain,
    language=intake.language,
    phase="memory_retrieval",
    target_scope="run_start",
)
initial_retrieval = retrieve_strategy_batch(
    memory_store,
    context=initial_retrieval_context,
    limit=DEFAULT_GENERAL_RETRIEVAL_LIMIT,
)
run_context.retrieved_strategies = initial_retrieval.patterns
run_context.resolution_state["memory_retrieval"] = {
    "initial": initial_retrieval.snapshot,
    "final_source": "initial",
}
```

Zu diesem Zeitpunkt gibt es noch keinen verlaesslichen `industry_hint`; deshalb
ist dieser Snapshot bewusst generisch. Er wird nicht als finaler Department-
Kontext behandelt, wenn nach dem Supervisor Brief bessere Patterns verfuegbar
sind.

Wichtig: Domain und Zielkundenname sind aktueller Run-Kontext, aber kein
Long-Term-Memory-Match-Key. Sie werden weder in `retrieval_query_summary`
geschrieben noch als Ranking-Bonus verwendet.

### 8a. Prozessstrategien werden nach dem Supervisor Brief aktualisiert

Sobald der Supervisor den Brief inklusive `industry_hint` gebaut hat, laeuft
ein zweites, kontextreicheres Retrieval:

```python
brief_retrieval_context = RetrievalContext(
    run_id=state.run_id,
    company_name=state.intake.company_name,
    normalized_domain=state.normalized_domain,
    language=state.intake.language,
    industry_hint=brief.industry_hint,
    phase="supervisor_brief",
    target_scope="brief_context",
    question_ids=tuple(state.run_context.question_registry.keys()),
)
brief_retrieval = retrieve_strategy_batch(...)
role_batches = {
    role: retrieve_strategy_batch(
        state.memory_store,
        context=brief_retrieval_context.role_context(role),
        limit=DEFAULT_ROLE_RETRIEVAL_LIMIT,
    )
    for role in RETRIEVABLE_ROLE_ORDER
}
```

`run_context.retrieved_role_strategies` enthaelt danach nur rollenpassende,
deduplizierte und policy-gepruefte Patterns. Der Audit-Status liegt unter
`resolution_state["memory_retrieval"]` mit `initial`, `brief_context`,
`roles`, `final_source` und Zaehlern fuer geladene/abgelehnte Patterns.

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

`build_company_research(...)` erhaelt im realen Runtime-Pfad den bereits
validierten `NormalizedDomainResult` und laeuft in dieser Reihenfolge:

1. Homepage-URL aus `NormalizedDomainResult.canonical_url` ableiten
2. `fetch_website_snapshot(url)` mit SSRF-, Redirect-, Content- und
   Groessen-Guards ausfuehren
3. `infer_company_identity(...)` als `IdentityResolutionResult`
4. `summarize_visible_text(...)` auf begrenztem, boilerplate-armem Text
5. `infer_industry_result(...)` als `IndustryInferenceResult`
6. `CompanyResearchResult` mit Evidence, Warnings, Errors und Timings bauen

Das Ergebnis enthaelt:

- normalisierte Domain
- Homepage-URL
- typisierten Website-Snapshot
- sichtbaren Text als Kurzsummary
- verifizierten Unternehmens-/Brand-Namen aus Homepage-Evidence
- leeren `verified_legal_name` im MVP plus Source-Gap fuer Registerquellen
- Name Confidence mit Begruendung
- Industry Hint mit Confidence und Alternativen
- Fehler-/Warncodes und Substep-Timings

### 12. Supervisor leitet einen Industry Hint ab

Aus dem Website-Snapshot und der Summary nutzt der Supervisor den
typisierten branchenbezogenen Hinweis:

```python
industry = infer_industry_result(
    title=str(snapshot.get("title", "")),
    description=str(snapshot.get("meta_description", "")),
    text=str(research.get("summary", "")),
)
```

Dieser `industry_hint` ist nur ein Startsignal fuer die nachfolgende
Department-Arbeit. Confidence, Evidence-Felder und Alternativen werden
mitgegeben; die spaetere domain-level Interpretation gehoert nicht in Step 1,
sondern in die Departments und Synthesis.

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

Zusammen mit dem Brief erzeugt der Supervisor eine versionierte,
validierbare Message:

```python
{
    "schema_version": BRIEFING_SCHEMA_VERSION,
    "section": "supervisor_brief",
    "status": "ready_for_department_routing",
    "briefing_readiness": "ready",
    "identity_confidence": "high",
    "industry_confidence": "high",
    "routing_gaps": [],
    "evidence_summary": {...},
    "payload": {...},
}
```

Der Message-Contract wird mit `validate_supervisor_brief_message(...)`
validiert, bevor er Teil des Step-1-Handoffs wird.

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

`build_question_registry()` liefert aktuell 12 Fragen. Jeder Registry-Eintrag
enthaelt eine stabile `question_id`, die dem Dict-Key entspricht. Die initiale
Answer Matrix besitzt dieselben Keys und startet pro Frage mit
`status="pending"`, leerer Antwort, leeren Notes und `source_tasks=[]`.

### 16. Erstes Runtime Event wird emittiert

Der Runner serialisiert die Supervisor Message und emittiert das erste
versionierte Runtime Event:

```python
first_event = emit_message(
    on_message,
    agent="Supervisor",
    content=json.dumps(supervisor_message, ensure_ascii=False, default=str),
    run_id=state.run_id,
    sequence=len(state.messages) + 1,
    phase="supervisor_brief",
    content_type="application/json",
)
state.messages.append(first_event)
```

`emit_message(...)` erzeugt ein Event mit:

- `event_id`
- `run_id`
- `sequence`
- `timestamp`
- `agent = "Supervisor"`
- `type = "agent_message"`
- `schema_version`
- `content = <JSON supervisor_message>`
- `content_type = "application/json"`
- `phase = "supervisor_brief"`

Wenn `on_message` gesetzt ist, wird das Event auch sofort an den Hook
weitergegeben. Unabhaengig davon landet es in `state.messages`.

### 17. Checkpoint nach dem Supervisor Brief

Der aktuelle Code schreibt nach dem Briefing einen Checkpoint:

```python
checkpoint_info = _write_checkpoint(
    state.run_dir,
    "after_supervisor_brief",
    state.run_context,
)
```

Der lokale JSON-Checkpoint wird atomar geschrieben (`.tmp` + Replace), enthaelt
`schema_version` und `checkpoint_hash` und liefert `CheckpointInfo` mit
`checkpoint_id`, `phase`, `path`, `content_hash`, `written` und Fehlerfeldern.
Im Produktionsziel ist dieser lokale Checkpoint ein Export-/Development-
Artefakt; die autoritative Recovery gehoert in den transaktionalen Run-State-
Store aus Punkt 3.

### 18. Step1Handoff wird validiert

Nach Event und Checkpoint baut der Runner den formalen Handoff-Contract:

```python
handoff = build_step1_handoff(
    run_context=state.run_context,
    supervisor_message=supervisor_message,
    first_event=first_event,
    checkpoint=checkpoint_info,
    runtime_agents_snapshot=state.agents.snapshot(),
    budget_snapshot={...},
)
state.run_context.resolution_state["step1_handoff"] = handoff.as_dict()
```

Der Gate-Validator prueft:

- Supervisor Message Contract und Payload;
- vorhandenes `run_context.supervisor_brief`;
- Question Registry und Answer Matrix mit identischen Keys;
- `TASK_TO_QUESTION_IDS` ohne fehlende Registry-Referenzen;
- Runtime Event mit Event-ID, Sequenz, Phase und Schema-Version;
- erfolgreichen Checkpoint-Write.

Das Ergebnis ist eine Readiness:

- `ready_for_department_routing`
- `ready_with_gaps`
- `blocked_step1_handoff`

### 19. Uebergabe an Step 2

Step 1 endet mit dem Rueckgabewert von `_build_supervisor_brief(...)`:

```python
return SupervisorBriefResult(
    brief=brief,
    supervisor_message=supervisor_message,
    step1_handoff=state.run_context.resolution_state["step1_handoff"],
)
```

Der naechste Pipeline-Schritt startet nur nach erfolgreichem Gate:

```python
if handoff_allows_department_routing(state.run_context.resolution_state["step1_handoff"]):
    first_pass = _run_first_pass(state, brief=supervisor.brief, on_message=on_message)
else:
    return _pipeline_error_result(
        failed_phase="step1_handoff",
        error_code="step1_handoff_invalid",
        ...
    )
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
| `supervisor_message` | versionierte und validierte SupervisorBriefMessage |
| `step1_handoff` | versionierter Handoff-Snapshot mit Readiness, Event, Checkpoint und Validation Errors |
| `state.agents` | alle Runtime-Agenten |
| `state.run_context` | Run Brain mit Intake, Supervisor Brief, Strategien, Question Registry, Answer Matrix und `resolution_state["step1_handoff"]` |
| `state.messages[0]` | erstes versioniertes Supervisor Runtime Event |
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
