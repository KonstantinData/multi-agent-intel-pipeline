# 0405 Repo-Audit Todo Plan

> Umsetzungsplan zum evidenzbasierten Repo-Audit vom 2026-05-04.

**Zweck:** Alle Audit-Findings in eine priorisierte, testbare Patch-Reihenfolge ueberfuehren.
**Release-Status:** P0/P1/P2 umgesetzt und mit Regressionstests abgesichert.
**Prinzip:** Kein Todo gilt als erledigt, bevor Code, Tests, Doku und Review-Gates konsistent sind.

---

## Arbeitsregeln

1. **P0 vor P1 vor P2.** P1-Arbeit darf nur beginnen, wenn sie keine P0-Entscheidung vorwegnimmt.
2. **Ein Architekturbruch pro Patch.** Boundary-, Selector-, Query- und Memory-Fixes nicht in Sammel-PRs vermischen.
3. **Tests gleichzeitig mit Code.** Jedes Todo braucht mindestens einen Regressionstest mit direktem Finding-Bezug.
4. **Keine Prompt-only-Fixes.** Boundary-, Query- und Evidence-Prioritaeten muessen im Code erzwungen werden.
5. **Doku folgt Code.** Architekturdocs erst aktualisieren, wenn der Runtime-Pfad korrigiert ist.
6. **Release-Gate:** P0 komplett gruen; P1 mindestens umgesetzt oder explizit als nicht release-blockierend akzeptiert; P2 geplant.

---

## Statusuebersicht

| Done | Todo | Thema | Audit-Findings | Severity | Prioritaet |
|---|---|---|---|---:|---:|
| [x] | TD-P0-1 | Synthesis-Supervisor-Boundary reparieren | AUD-HIGH-BD-001 | High | P0 |
| [x] | TD-P0-2 | Synthesis Speaker Selector guardrail-only machen | AUD-HIGH-CF-002 | High | P0 |
| [x] | TD-P0-3 | Follow-up-Evidenzprioritaet korrigieren | AUD-HIGH-MH-004 | High | P0 |
| [x] | TD-P0-4 | Query-Override-Pfad an Query-Strategy-KB binden | AUD-HIGH-KA-003 | High | P0 |
| [x] | TD-P1-1 | Hardcodierte Source-Fallbackprofile bereinigen | AUD-MED-KA-005 | Medium | P1 |
| [x] | TD-P1-2 | Architecture-Test-Layer dependency-light machen | AUD-MED-TC-006 | Medium | P1 |
| [x] | TD-P2-1 | CODEOWNERS fuer Architekturdocs und Tests schaerfen | Governance Gap | Medium | P2 |
| [x] | TD-P2-2 | Failure-Mode-Regressionen vervollstaendigen | Failure Mode Catalogue | Medium | P2 |

---

## P0 Release-Blocker

## TD-P0-1 - Synthesis-Supervisor-Boundary reparieren

**Audit-Finding:** AUD-HIGH-BD-001
**Ziel:** Synthesis Department erhaelt keine direkte `SupervisorAgent`-Instanz und kann waehrend des internen GroupChats keine Supervisor-Routingentscheidung ausloesen.

### Betroffene Dateien

- `src/agents/synthesis_department.py`
- `src/orchestration/synthesis_runtime.py`
- `src/pipeline_runner.py`
- `tests/integration/test_ag2_runtime.py`
- `tests/architecture/test_orchestration.py`
- `docs/drawio/target_runtime_architecture.md`
- `README.md`

### Umsetzung

- [x] `supervisor`-Parameter aus `SynthesisDepartmentAgent.run()` entfernen.
- [x] `supervisor`-Parameter aus `SynthesisRuntime.run()` entfernen.
- [x] `request_department_followup()` so umbauen, dass es nur ein strukturiertes BackRequest-Artefakt im Synthesis-Ergebnis erzeugt.
- [x] Routing und Ausfuehrung von BackRequests nach Chat-Ende in den aeusseren Runtime-Orchestrator verschieben.
- [x] `pipeline_runner.py` so anpassen, dass BackRequests explizit nach Synthesis verarbeitet oder als offene Gaps persistiert werden.
- [x] Architekturdocs aktualisieren, wenn der neue Codepfad feststeht.

### Akzeptanzkriterien

- [x] `inspect.signature(SynthesisRuntime.run)` enthaelt keinen `supervisor`-Parameter.
- [x] `inspect.signature(SynthesisDepartmentAgent.run)` enthaelt keinen `supervisor`-Parameter.
- [x] Synthesis kann BackRequests erzeugen, aber nicht direkt ueber `SupervisorAgent.route_question()` routen.
- [x] Supervisor sieht Synthesis-Ergebnis und BackRequest-Artefakte erst nach Abschluss des Synthesis GroupChats.

### Tests

- [x] Neuer Architekturtest: `test_synthesis_runtime_has_no_supervisor_param`.
- [x] Neuer Integrationstest: `test_synthesis_exports_back_requests_without_supervisor_reference`.
- [x] Bestehende Synthesis-Tests an neue Signatur anpassen.

### Review-Gate

- [x] Reviewer: `@KonstantinData`, `@liquisto/runtime-review`.
- [x] Gate: Kein `supervisor=` in Synthesis-Runtime-Aufrufen.

---

## TD-P0-2 - Synthesis Speaker Selector guardrail-only machen

**Audit-Finding:** AUD-HIGH-CF-002
**Ziel:** Der Synthesis Speaker Selector ist wie der Department Selector nur Guardrail-Logik und keine State-Machine.

### Betroffene Dateien

- `src/orchestration/speaker_selector.py`
- `src/agents/synthesis_department.py`
- `tests/architecture/test_selector.py`
- `tests/integration/test_ag2_runtime.py`
- `docs/drawio/target_runtime_architecture.md`

### Umsetzung

- [x] Ausfuehrbare Nutzung von `run_state["synthesis_step"]` aus `build_synthesis_selector()` entfernen.
- [x] Selector auf Guardrails begrenzen:
  - [x] Tool Calls zum Executor routen.
  - [x] Executor-Ergebnis an Lead zurueckgeben.
  - [x] Text-only-Loops brechen.
  - [x] Termination erkennen.
- [x] Lead-gesteuertes Addressing fuer Analyst, Critic und Judge einfuehren.
- [x] Synthesis Lead Prompt so aktualisieren, dass die erwartete interne Reihenfolge explizit vom Lead gesteuert wird.
- [x] Tests fuer verbotene Selector-State-Machine ergaenzen.

### Akzeptanzkriterien

- [x] `build_synthesis_selector()` mutiert keinen Workflow-State.
- [x] Im Selector existiert kein ausfuehrbarer Zugriff auf `synthesis_step`.
- [x] Der Synthesis GroupChat bleibt lauffaehig und kann `read_report_segment`, Critique und `finalize_synthesis` erreichen.

### Tests

- [x] Neuer Architekturtest: `test_synthesis_selector_has_no_synthesis_step_state_machine`.
- [x] Neuer Architekturtest: `test_synthesis_selector_routes_lead_addressed_agents`.
- [x] Integrationstest mit gemocktem AG2-Chat fuer erfolgreichen Synthesis-Abschluss.

### Review-Gate

- [x] Reviewer: `@KonstantinData`, `@liquisto/runtime-review`.
- [x] Gate: Keine Workflow-State-Mutation in `src/orchestration/speaker_selector.py`.

---

## TD-P0-3 - Follow-up-Evidenzprioritaet korrigieren

**Audit-Finding:** AUD-HIGH-MH-004
**Ziel:** Follow-up-Antworten priorisieren Evidenz deterministisch: `department_run_states` zuerst, dann `pipeline_data`, dann Department Packages.

### Betroffene Dateien

- `src/orchestration/follow_up.py`
- `tests/architecture/test_follow_up.py`
- `tests/golden/test_golden_traces.py`
- `README.md`
- `docs/drawio/target_runtime_architecture.md`

### Umsetzung

- [x] `FollowUpEvidenceResolver.resolve()` zur einzigen Evidence-Priority-Funktion machen.
- [x] Antwortfunktionen `_company_answer`, `_market_answer`, `_buyer_answer`, `_contact_answer` so umbauen, dass sie keine `answer_matrix`- oder `evidence_packets`-Evidenz vor Artifact-Evidenz stellen.
- [x] Reihenfolge explizit im Payload auditierbar machen, z. B. ueber `evidence_used` mit Quelle oder Prioritaetsstufe.
- [x] `requires_additional_research` weiter aus unresolved Artefakten und Package-Gaps ableiten.
- [x] Doku-Kommentar in `follow_up.py` an Codepfad angleichen.

### Akzeptanzkriterien

- [x] Bei widerspruechlichen Daten gewinnt `task_artifacts`/`decision_artifacts` vor `pipeline_data`.
- [x] `pipeline_data` gewinnt vor Department Package Fallback.
- [x] `answer_matrix` wird nicht als primaere Evidence-Prioritaet vor Run-Brain-Artefakten verwendet.
- [x] Follow-up wird weiter als Artifact persistiert.

### Tests

- [x] Neuer Test: `test_follow_up_evidence_priority_prefers_task_artifacts_over_answer_matrix`.
- [x] Neuer Test: `test_follow_up_evidence_priority_falls_back_to_pipeline_data_then_package`.
- [x] Golden-Trace-Test fuer `follow_up_history.json`, falls vorhandene Fixture erweitert wird.

### Review-Gate

- [x] Reviewer: `@KonstantinData`, `@liquisto/security-governance`.
- [x] Gate: Memory-Boundary und Evidence-Priority muessen im Test sichtbar sein.

---

## TD-P0-4 - Query-Override-Pfad an Query-Strategy-KB binden

**Audit-Finding:** AUD-HIGH-KA-003
**Ziel:** Runtime Query Templates stammen ausschliesslich aus `knowledge/query_strategies/*.yaml`; Coding Support darf keine freien Runtime-Query-Templates erzeugen.

### Betroffene Dateien

- `src/agents/coding_assistant.py`
- `src/agents/lead.py`
- `src/agents/worker.py`
- `src/research/query_resolver.py`
- `knowledge/query_strategies/*.yaml`
- `tests/test_query_consistency.py`
- `tests/test_query_migration.py`
- `tests/architecture/test_worker_search_runtime.py`

### Umsetzung

- [x] `CodingAssistantAgent.suggest_queries()` von freien Query-Strings auf strukturierte Strategy-Intents umstellen.
- [x] Eine KB-gebundene Override-API im Query Resolver einfuehren, z. B. `resolve_query_variant(task_key, variant_key, brief, current_section)`.
- [x] `suggest_refined_queries()` nur noch validierte KB-Varianten oder Query-Template-IDs akzeptieren lassen.
- [x] `ResearchWorker.run()` so anpassen, dass `query_overrides` nicht mehr als freie Suchstrings direkt ausgefuehrt werden.
- [x] Legacy-Verify-Pfad klar als nicht-runtime-authoritative markieren und keine neuen Templates dort ergaenzen.
- [x] Query Strategy YAMLs um benoetigte Retry-/Refinement-Varianten erweitern.

### Akzeptanzkriterien

- [x] Kein Coding-Support-Pfad liefert freie f-String-Query-Templates an `_search_queries()`.
- [x] Alle Runtime Queries lassen sich auf `knowledge/query_strategies/<department>.yaml` zurueckfuehren.
- [x] `validate_query_overrides()` akzeptiert keine freien Runtime-Queries ohne KB-Herkunft.
- [x] Migration-/Parity-Tests bleiben gruen oder werden auf die neue KB-Variantensemantik angepasst.

### Tests

- [x] Neuer Test: `test_coding_specialist_query_overrides_must_resolve_via_strategy_kb`.
- [x] Neuer Test: `test_runtime_query_templates_have_strategy_file_origin`.
- [x] Erweiterung von `test_query_consistency.py` um Retry-/Refinement-Varianten.

### Review-Gate

- [x] Reviewer: `@KonstantinData`, `@liquisto/runtime-review`.
- [x] Gate: Suche nach neuen Runtime-Query-Templates ausserhalb `knowledge/query_strategies` muss failen.

---

## P1 Strukturkorrekturen

## TD-P1-1 - Hardcodierte Source-Fallbackprofile bereinigen

**Audit-Finding:** AUD-MED-KA-005
**Ziel:** Source Registry Metadata enthaelt keine Runtime Query Patterns, auch nicht in hardcodierten Fallbacks.

### Betroffene Dateien

- `src/orchestration/department_knowledge.py`
- `knowledge/sources/*.yaml`
- `knowledge/query_strategies/*.yaml`
- `tests/test_query_consistency.py`
- `tests/architecture/test_department_knowledge.py`

### Umsetzung

- [x] `search_patterns_de` und `search_patterns_en` aus `_DEFAULT_SOURCE_PROFILES` entfernen.
- [x] Falls benoetigte Patterns fachlich relevant sind, in `knowledge/query_strategies/*.yaml` migrieren.
- [x] Strict-Mode-Verhalten pruefen: Fallback darf keine Query-relevanten Felder enthalten.
- [x] Test auf Source-YAMLs und Default-Fallbackprofile ausweiten.

### Akzeptanzkriterien

- [x] `_DEFAULT_SOURCE_PROFILES` enthaelt keine Keys mit Praefix `search_patterns`, `queries`, `template`.
- [x] Source YAMLs bleiben reine Source Registry.
- [x] Query Strategy YAMLs bleiben einzige Template-Quelle.

### Tests

- [x] Neuer Test: `test_default_source_profiles_contain_no_runtime_query_patterns`.
- [x] Erweiterung: `test_source_kb_contains_no_runtime_query_patterns` prueft auch Fallbackprofile.

### Review-Gate

- [x] Reviewer: `@KonstantinData`, `@liquisto/runtime-review`.

---

## TD-P1-2 - Architecture-Test-Layer dependency-light machen

**Audit-Finding:** AUD-MED-TC-006
**Ziel:** `tests/architecture` bleibt frei von runtime-heavy Optionaldeps und Export-/OpenAI-Pfaden.

### Betroffene Dateien

- `tests/architecture/test_dashboard.py`
- `tests/architecture/test_worker_search_runtime.py`
- `tests/architecture/test_000_import_layering.py`
- `tests/integration/`
- `tests/smoke/`

### Umsetzung

- [x] PDF-/ReportLab-/pypdf-bezogene Tests aus `tests/architecture/test_dashboard.py` nach `tests/integration` oder `tests/smoke` verschieben.
- [x] OpenAI-/ResearchWorker-runtime-heavy Tests aus `tests/architecture/test_worker_search_runtime.py` verschieben oder dependency-light isolieren.
- [x] `test_000_import_layering.py` um statische Scan-Regel erweitern.
- [x] CI-Kommandos fuer architecture und integration getrennt dokumentieren.

### Akzeptanzkriterien

- [x] `pytest -q tests/architecture` laedt keine `openai`, `autogen`, `pypdf`, `reportlab` oder `src.exporters.pdf_report`.
- [x] Runtime-heavy Tests liegen unter `tests/integration` oder `tests/smoke` und sind korrekt markiert.
- [x] Architecture-Testlauf bleibt dependency-light.

### Tests

- [x] Erweiterung: `test_dependency_light_architecture_modules_do_not_import_runtime_heavy_modules`.
- [x] Neuer statischer Test: `test_architecture_tests_do_not_import_runtime_heavy_modules`.

### Review-Gate

- [x] Reviewer: `@KonstantinData`, `@liquisto/security-governance`.

---

## P2 Governance und Haertung

## TD-P2-1 - CODEOWNERS fuer Architekturdocs und Tests schaerfen

**Audit-Bezug:** Ownership-/Review-Gap aus Audit-Sektion F.
**Ziel:** Architekturdocs und Tests haben explizite Ownership statt nur Global-Fallback.

### Betroffene Dateien

- `.github/CODEOWNERS`
- `docs/drawio/target_runtime_architecture.md`
- `docs/target_runtime_architecture.md`
- `tests/**`
- `docs/review-gates.md`

### Umsetzung

- [x] CODEOWNERS-Regeln fuer `/docs/drawio/`, `/docs/target_runtime_architecture.md` und `/tests/` ergaenzen.
- [x] Runtime-Architekturdocs Runtime-Review zuordnen.
- [x] Architekturtests Security-Governance plus Runtime-Review zuordnen.
- [x] Review-Gates in `docs/review-gates.md` spiegeln.

### Akzeptanzkriterien

- [x] Aenderungen an Architekturdocs fordern `@liquisto/runtime-review`.
- [x] Aenderungen an Tests fordern mindestens `@KonstantinData` und relevante Review-Gruppe.
- [x] Global-Fallback ist nicht die einzige nachweisbare Ownership fuer Audit-relevante Docs/Tests.

### Tests

- [x] Optionaler Governance-Test: `test_codeowners_contains_architecture_docs_and_tests_rules`.

---

## TD-P2-2 - Failure-Mode-Regressionen vervollstaendigen

**Audit-Bezug:** Failure Mode Catalogue.
**Ziel:** Alle acht kritischen Audit-Pfade haben mindestens einen negativen oder Boundary-Test.

### Betroffene Module

- `src/pipeline_runner.py`
- `src/orchestration/supervisor_loop.py`
- `src/agents/lead.py`
- `src/orchestration/follow_up.py`
- `src/memory/consolidation.py`
- `src/research/query_resolver.py`
- `tests/architecture/**`
- `tests/integration/**`

### Umsetzung

- [x] Failure Mode 1: Intake/Routing mit leerem oder schwachem Intake absichern.
- [x] Failure Mode 2: Department Finalization ohne alle Tasks weiter negativ testen.
- [x] Failure Mode 3: Inline-Fallback-Aeste fuer Review/Decision gezielt testen.
- [x] Failure Mode 4: Query-Resolver/KB-Herkunft negativ testen.
- [x] Failure Mode 5: Synthesis/ReportWriter-Separation testen.
- [x] Failure Mode 6: Follow-up-Prioritaet und Persistenz testen.
- [x] Failure Mode 7: Long-Term-Memory Reject-Pfade fuer unsichere Patterns erweitern.
- [x] Failure Mode 8: Test-Layering statisch pruefen.

### Akzeptanzkriterien

- [x] Jeder kritische Pfad hat einen Test mit negativem oder Boundary-Case.
- [x] Tests referenzieren Finding-ID oder Failure-Mode-ID im Namen oder Kommentar.
- [x] `pytest -q tests/architecture` bleibt gruen.

---

## Validierungskommandos

Nach Umsetzung der jeweiligen Pakete:

```powershell
pytest -q tests\architecture
pytest -q tests\test_query_consistency.py tests\test_query_migration.py
pytest -q tests\integration
```

Wenn Integrationstests wegen fehlender AG2/autogen-Installation skippen, muss der Skip im CI-Kontext explizit akzeptiert oder ein runtime-faehiger CI-Job bereitgestellt werden.

---

## 30-60-90 Plan

### 30 Tage - Critical/High Fixes

- [x] TD-P0-1 abschliessen.
- [x] TD-P0-2 abschliessen.
- [x] TD-P0-3 abschliessen.
- [x] TD-P0-4 abschliessen.
- [x] Alle P0-Regressionstests in CI-Gate aufnehmen.

### 60 Tage - Strukturelle Korrekturen

- [x] TD-P1-1 abschliessen.
- [x] TD-P1-2 abschliessen.
- [x] Query-/KB-Origin-Governance in Tests erzwingen.
- [x] Architecture-/Integration-Testkommandos sauber trennen.

### 90 Tage - Haertung und Governance

- [x] TD-P2-1 abschliessen.
- [x] TD-P2-2 abschliessen.
- [x] Failure-Mode-Regressionen in Release-Checkliste aufnehmen.
- [x] Review-Gates mit CODEOWNERS und Audit-Dokumentation synchronisieren.

---

## Definition of Done

Ein Todo ist erledigt, wenn:

- [x] Code angepasst ist.
- [x] Regressionstest existiert und lokal gruen ist.
- [x] Betroffene Architektur- oder README-Dokumentation konsistent ist.
- [x] CODEOWNERS-/Review-Gate eingehalten wurde.
- [x] Kein neues verbotenes Muster entsteht:
  - [x] versteckte Orchestrierung ausserhalb des Supervisors,
  - [x] direkte Agent-zu-Agent-Kommunikation ohne Department Boundary,
  - [x] Speicherung von Rohdaten im Long-Term Memory,
  - [x] Query Templates ausserhalb der Query Strategy KB.
