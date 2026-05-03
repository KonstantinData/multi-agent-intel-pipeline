# 0305 Repo-Audit ZoDo Plan

> Umsetzungsplan zum evidenzbasierten Repo-Audit vom 2026-05-03.

**Zweck:** Alle Audit-Findings in eine priorisierte, testbare Patch-Reihenfolge ueberfuehren.  
**Release-Status:** Go nach lokaler Validierung: alle P0/P1/P2-Arbeitspakete umgesetzt und CI-Gates ergänzt.  
**Prinzip:** Kein Finding gilt als erledigt, bevor Code, Tests, Doku und CI-Gate konsistent sind.

---

## Arbeitsregeln

1. **P0 vor P1 vor P2.** P1-Arbeit darf nur beginnen, wenn sie keine P0-Entscheidung vorwegnimmt.
2. **Ein Root-Cause pro Patch.** Keine Sammel-PRs, die Runtime-Reihenfolge, Security und Test-CI vermischen.
3. **Tests zuerst oder gleichzeitig.** Jedes ZoDo braucht mindestens einen Regressionstest.
4. **Keine Prompt-only-Fixes fuer Runtime-Risiken.** Tool-Guards und Contracts muessen im Code erzwungen werden.
5. **Doku folgt Code.** Wenn Code und Zielarchitektur abweichen, zuerst Code korrigieren oder Zielmodell bewusst anpassen.
6. **Release-Gate:** P0 komplett gruen, P1 mindestens geplant und nicht release-blockierend, P2 backlog-faehig.

---

## Statusuebersicht

| ZoDo | Thema | Audit-Findings | Severity | Prioritaet | Status |
|---|---|---|---:|---:|---|
| ZD-P0-1 | Runtime-Phasenordnung korrigieren | AUD-001 | High | P0 | Erledigt |
| ZD-P0-2 | Auto-Close Answer-Matrix-Mapping fixen | AUD-002 | High | P0 | Erledigt |
| ZD-P0-3 | Judge-/Artifact-Guards erzwingen | AUD-003 | High | P0 | Erledigt |
| ZD-P0-4 | `run_id` sicher auf Run-Verzeichnis mappen | AUD-004 | High | P0 | Erledigt |
| ZD-P0-5 | Long-Term-Memory Scrubbing haerten | AUD-005 | High | P0 | Erledigt |
| ZD-P0-6 | Statusvokabular hart validieren | AUD-006 | High | P0 | Erledigt |
| ZD-P0-7 | Follow-up-Evidenzprioritaet reparieren | AUD-007 | High | P0 | Erledigt |
| ZD-P0-8 | CI-Produkttests aktivieren | AUD-008 | High | P0 | Erledigt |
| ZD-P0-9 | Architecture-Test-Layer dependency-light machen | AUD-009 | High | P0 | Erledigt |
| ZD-P1-1 | Query-Override-Pfad validieren/auditieren | AUD-010 | Medium | P1 | Erledigt |
| ZD-P1-2 | Source-KB von Query-Patterns bereinigen | AUD-011 | Medium | P1 | Erledigt |
| ZD-P1-3 | KB-Parsing/Strict-Mode klaeren | AUD-012 | Medium | P1 | Erledigt |
| ZD-P1-4 | Retry-Limits als Tool-Guard erzwingen | AUD-013 | Medium | P1 | Erledigt |
| ZD-P1-5 | ReportWriter nach Finalisierung ausfuehren | AUD-014 | Medium | P1 | Erledigt |
| ZD-P1-6 | Run-Export atomar und gelockt machen | AUD-015 | Medium | P1 | Erledigt |
| ZD-P2-1 | CODEOWNERS und Review-Gates schaerfen | AUD-016 | Medium | P2 | Erledigt |

---

## P0 Release-Blocker

## ZD-P0-1 - Runtime-Phasenordnung korrigieren

**Audit-Finding:** AUD-001  
**Ziel:** Runtime-Reihenfolge entspricht Zielmodell: Domain Departments -> Resolution -> Auto-Close -> Synthesis -> ReportWriter -> Final Export.

### Betroffene Dateien

- `src/orchestration/supervisor_loop.py`
- `src/pipeline_runner.py`
- `src/orchestration/synthesis_runtime.py`
- `src/orchestration/report_runtime.py`
- `README.md`
- `docs/target_runtime_architecture.md`
- `docs/drawio/target_runtime_architecture.md`

### Umsetzung

1. `run_supervisor_loop()` auf Domain-Round plus First-Round-Resolution begrenzen.
2. Synthesis-Aufruf aus `run_supervisor_loop()` entfernen oder hinter Auto-Close verschieben.
3. `run_pipeline()` als expliziten Phasenorchestrator strukturieren:
   Domain Round, Resolution, optional Closure, Synthesis, Readiness, ReportWriter, Export.
4. Closure-Ergebnisse vor Synthesis in `run_context.answer_matrix`, `short_term_memory` und `resolution_state` schreiben.
5. Checkpoints anpassen: `after_first_pass`, `after_closure`, `after_synthesis`, `after_finalization`.
6. README und Architekturdocs nur nach Code-Anpassung aktualisieren.

### Akzeptanzkriterien

- Synthesis liest keine First-Round-Gaps, die durch Auto-Close bereits geloest wurden.
- `department_packages["SynthesisDepartment"]` entsteht erst nach Auto-Close.
- `after_closure` existiert vor `after_synthesis`, wenn Auto-Close ausgefuehrt wurde.

### Tests

- Unit/Integration-Test mit Fake-Controller `AUTO_CLOSE_REQUIRED`.
- Spy-Reihenfolge: `run_bounded_follow_up()` wird vor `agents["synthesis"].run()` aufgerufen.
- Golden-Trace-Test prueft neue Checkpoint-Reihenfolge.

---

## ZD-P0-2 - Auto-Close Answer-Matrix-Mapping fixen

**Audit-Finding:** AUD-002  
**Ziel:** Auto-Close aktualisiert nur die konkret geloeste Frage bzw. den konkret geloesten Gap.

### Betroffene Dateien

- `src/pipeline_runner.py`
- `src/orchestration/follow_up.py`
- `src/orchestration/meeting_questions.py`
- `src/models/meeting_ready.py`

### Umsetzung

1. Gap-Kandidaten mit `gap_id`, `question_id` oder `field_key` bis `run_bounded_follow_up()` durchreichen.
2. `run_bounded_follow_up()` soll pro Attempt `resolved_question_ids` oder `resolved_gap_ids` zurueckgeben.
3. Matrix-Update in `pipeline_runner.py` nur fuer diese IDs anwenden.
4. Wenn kein Mapping existiert, keine pauschale Matrix-Aktualisierung vornehmen; stattdessen unresolved belassen und Observability-Warnung schreiben.

### Akzeptanzkriterien

- Eine geloeste Auto-Close-Frage kann keine unrelated Matrix-Frage veraendern.
- Contact- und Synthesis-Fragen werden nicht durch Company/Market/Buyer-Closure implizit teilweise beantwortet.

### Tests

- Answer-Matrix mit zwei pending Fragen; Auto-Close loest nur eine; assert nur diese wird `partially_answered`.
- Negativtest ohne Mapping: keine Matrix-Aenderung, aber `resolution_state.auto_close.mapping_missing=true`.

---

## ZD-P0-3 - Judge-/Artifact-Guards erzwingen

**Audit-Finding:** AUD-003  
**Ziel:** Kein Task kann ohne Research-Artefakt und Review-/Fallback-Kontext als accepted geschlossen werden.

### Betroffene Dateien

- `src/agents/lead.py`
- `src/agents/judge.py`
- `src/orchestration/contracts.py`
- `tests/integration/test_ag2_runtime.py`
- `tests/architecture/test_contracts.py`

### Umsetzung

1. `judge_decision()` validiert, dass `task_key` bekannt ist.
2. `judge_decision()` verlangt ein aktuelles `TaskArtifact`.
3. Wenn kein Review existiert, muss ein explizites fallback review erzeugt und als `TaskReviewArtifact` gespeichert werden, bevor der Judge entscheidet.
4. Judge ohne Artifact gibt `closed_unresolved` oder strukturierten Fehler zurueck, niemals `accepted`.
5. `finalize_package()` ignoriert oder degradiert Decisions, die keine korrespondierende Artifact-Historie haben.

### Akzeptanzkriterien

- `accepted` ist nur moeglich, wenn mindestens ein `TaskArtifact` existiert.
- Jede Judge-Decision hat eine nachvollziehbare Grundlage: Review oder expliziter fallback review.
- Run Brain enthaelt fuer jeden finalisierten Task eine konsistente Artifact-Kette.

### Tests

- Gepatchter AG2-Chat ruft `judge_decision()` vor `run_research()`; assert kein accepted.
- Finalize mit Decision ohne Artifact; assert `degraded` oder `closed_unresolved`.
- Contract-Test prueft Referential Integrity zwischen `decision_artifacts` und `task_artifacts`.

---

## ZD-P0-4 - `run_id` sicher auf Run-Verzeichnis mappen

**Audit-Finding:** AUD-004  
**Ziel:** `run_id` kann keine Pfade ausserhalb von `artifacts/runs` lesen oder schreiben.

### Betroffene Dateien

- `src/orchestration/follow_up.py`
- `src/pipeline_runner.py`
- `src/exporters/json_export.py`
- `ui/app.py`

### Umsetzung

1. Zentrale Funktion `resolve_run_dir(run_id: str) -> Path` einfuehren.
2. Erlaubtes Format definieren, z. B. `YYYYMMDDTHHMMSSZ` plus optional bekannte Test-IDs.
3. `Path.resolve()` verwenden und `relative_to(RUNS_DIR.resolve())` erzwingen.
4. `load_run_artifact()`, `answer_follow_up()`, `resume_pipeline()` und UI-Aufrufe auf diese Funktion umstellen.
5. Fehlermeldung ohne Pfadleak zurueckgeben.

### Akzeptanzkriterien

- `../`, `..\\`, absolute Pfade und gemischte Separatoren werden abgelehnt.
- Alle Run-Lese-/Schreibpfade laufen ueber denselben Resolver.

### Tests

- Parametrisierter Unit-Test fuer `../outside`, `..\\outside`, `/tmp/x`, `C:\\temp\\x`.
- Positivtest fuer echte Timestamp-Run-ID und fuer definierte Test-Fixture-ID.

---

## ZD-P0-5 - Long-Term-Memory Scrubbing haerten

**Audit-Finding:** AUD-005  
**Ziel:** Long-Term Memory enthaelt nur prozessuale Patterns ohne firmenspezifische Namen, Domains, Kontakte oder Run-Fakten.

### Betroffene Dateien

- `src/memory/consolidation.py`
- `src/memory/long_term_store.py`
- `src/memory/policies.py`
- `tests/architecture/test_memory.py`

### Umsetzung

1. Scrubber um Run-Kontext erweitern: submitted company, verified company, legal name, normalized domain, domain tokens.
2. Unquoted target names und tokenisierte Namensvarianten ersetzen.
3. Kontakt-/Personennamen und URLs in pattern fields verbieten.
4. `FileLongTermMemoryStore.upsert_strategy()` um defensive final validation erweitern.
5. Bestehenden LTM-Backfill nur ueber neuen Scrubber laufen lassen.

### Akzeptanzkriterien

- Keine Target-Namen, Domains, URLs oder Kontaktpersonen in `long_term_memory.json`.
- Store lehnt unsichere Patterns ab, auch wenn Consolidation fehlerhaft ist.

### Tests

- Parametrisierter Scrub-Test mit `Tesla`, `Siemens`, `ACME GmbH`, Domains und URLs.
- Upsert-Negativtest: Pattern mit `domain` oder Firmenname wird nicht gespeichert.

---

## ZD-P0-6 - Statusvokabular hart validieren

**Audit-Finding:** AUD-006  
**Ziel:** Task-Status, Decision Outcome und Admission Decision sind strikt getrennt und runtime-weit kanonisch.

### Betroffene Dateien

- `src/orchestration/contracts.py`
- `src/models/schemas.py`
- `src/orchestration/meeting_questions.py`
- `src/agents/lead.py`
- `src/agents/supervisor.py`
- `tests/architecture/test_contracts.py`
- `tests/golden/test_golden_traces.py`

### Umsetzung

1. `TaskStatus` als Literal aus `TASK_LIFECYCLE_STATUSES` definieren.
2. `DepartmentTaskResult.status` nicht mehr als freier `str`.
3. `rejected` ausschliesslich in `ADMISSION_DECISIONS` zulassen, nicht als Task-Status.
4. `matrix_status_for_task_status()` fuer alle kanonischen Task-Statuswerte explizit testen.
5. Golden Fixtures migrieren.

### Akzeptanzkriterien

- Pydantic lehnt unbekannte Task-Statuswerte ab.
- `blocked` ist erlaubt, wenn Runtime es weiterhin verwendet.
- `rejected` als Task-Status schlaegt fehl.

### Tests

- `DepartmentPackage.model_validate()` Negativtest fuer `rejected` und `unknown`.
- Positivtest fuer `pending`, `accepted`, `degraded`, `blocked`, `skipped`, `pending_synthesis`.

---

## ZD-P0-7 - Follow-up-Evidenzprioritaet reparieren

**Audit-Finding:** AUD-007  
**Ziel:** Follow-up antwortet nach dokumentierter Prioritaet: Run-Brain-Artefakte zuerst, dann `pipeline_data`, dann Department Packages.

### Betroffene Dateien

- `src/orchestration/follow_up.py`
- `src/orchestration/envelope.py`
- `src/memory/short_term_store.py`
- `tests/architecture/test_follow_up.py`

### Umsetzung

1. Zentralen `FollowUpEvidenceResolver` oder Helper einfuehren.
2. Evidence aus `task_artifacts` nur verwenden, wenn Decision/Review sie akzeptiert oder zumindest nicht blockiert.
3. `decision_artifacts.open_questions` als unresolved priorisieren.
4. `pipeline_data` nur als sekundare, abgeleitete Quelle nutzen.
5. DepartmentPackage-Fallback ueber Envelope-Resolver implementieren.

### Akzeptanzkriterien

- Widerspruch zwischen `answer_matrix` und `task_artifacts` wird zugunsten Run-Brain-Artefakte geloest.
- Facts aus `closed_unresolved` oder `blocked_by_dependency` landen nicht in `evidence_used`.
- DepartmentPackage-Gaps bleiben im Follow-up sichtbar.

### Tests

- Widerspruchstest `answer_matrix.answer` vs. `task_artifacts.facts`.
- Test mit `closed_unresolved` latest decision: Fact wird unresolved, nicht evidence.
- Fallback-Test: keine Run-State-Artefakte, aber DepartmentPackage open questions.

---

## ZD-P0-8 - CI-Produkttests aktivieren

**Audit-Finding:** AUD-008  
**Ziel:** CI blockiert relevante Runtime-, Architektur-, Readiness- und Query-Regressionen.

### Betroffene Dateien

- `.github/workflows/compliance-security-ai.yml`
- `requirements.txt`
- `requirements.lock`
- `pyproject.toml`

### Umsetzung

1. CI-Job `architecture-tests`: `pytest -q tests/architecture`.
2. CI-Job `runtime-contract-tests`: `pytest -q tests/meeting_readiness tests/golden tests/test_query_*.py tests/smoke`.
3. Integrationstests separieren: `pytest -q -m integration`, optional nur bei Runtime-Deps.
4. Test-Dependencies explizit installieren.
5. CI-Artefakte fuer Testberichte hochladen.

### Akzeptanzkriterien

- Ein brechender Architekturtest macht PR rot.
- Query-, Readiness- und Golden-Tests laufen in CI.
- Integration ist markiert und nicht mit dependency-light Tests vermischt.

### Tests

- Workflow-Hardening-Test aktualisieren.
- CI lokal per `pytest -q tests/test_scripts_contracts.py` absichern.

---

## ZD-P0-9 - Architecture-Test-Layer dependency-light machen

**Audit-Finding:** AUD-009  
**Ziel:** `tests/architecture` kann ohne AG2/autogen, OpenAI SDK und PDF-Runtime-Deps collected und ausgefuehrt werden.

### Betroffene Dateien

- `tests/architecture/**`
- `src/agents/lead.py`
- `src/agents/worker.py`
- `src/exporters/pdf_report.py`
- `pyproject.toml`

### Umsetzung

1. Tests identifizieren, die `autogen`, `openai`, `pypdf`, `reportlab` indirekt importieren.
2. PDF-/OpenAI-/AG2-nahe Tests nach `tests/integration` oder `tests/runtime` verschieben.
3. Dependency-light Helper aus Runtime-heavy Modulen extrahieren.
4. `tests/architecture/conftest.py` um Import-Guard ergaenzen.

### Akzeptanzkriterien

- `pytest -q tests/architecture --collect-only` funktioniert in Minimal-Env.
- Architecture-Tests importieren keine Runtime-Agenten mit top-level AG2/OpenAI.

### Tests

- Neuer Import-Guard-Test, der verbotene Module in `sys.modules` nach Collection prueft.
- CI-Minimaljob ohne Runtime-Deps.

---

## P1 Struktur- und Robustheitsarbeit

## ZD-P1-1 - Query-Override-Pfad validieren/auditieren

**Audit-Finding:** AUD-010  
**Ziel:** Query-Overrides sind entweder validierte Query-Strategy-Ausnahmen oder explizit auditierte adaptive Strategien.

### Umsetzung

1. `query_overrides` durch Placeholder-/Legacy-Syntax-Validator schicken.
2. Override-Metadaten speichern: Agent, Grund, Task, Review-Issue, Timestamp.
3. Ungueltige Overrides ablehnen.
4. Tests fuer `<firma>`, `{unknown}` und leere Overrides.

### Akzeptanzkriterien

- Keine unvalidierten Runtime-Queries.
- Jeder Override ist im Run Brain nachvollziehbar.

---

## ZD-P1-2 - Source-KB von Query-Patterns bereinigen

**Audit-Finding:** AUD-011  
**Ziel:** `knowledge/sources` enthaelt nur Source-Metadaten, keine Runtime-Query-Patterns.

### Umsetzung

1. `search_patterns_*` aus `knowledge/sources/*.yaml` entfernen oder migrieren.
2. Falls Patterns historisch nuetzlich sind, nach `knowledge/query_strategies` ueberfuehren.
3. Schema-Test fuer Source-KB einfuehren.
4. Doku angleichen.

### Akzeptanzkriterien

- Source-KB enthaelt keine Keys `search_patterns_*`, `queries*`, `template*`.
- Query-Strategies bleiben alleinige Query-Template-Quelle.

---

## ZD-P1-3 - KB-Parsing/Strict-Mode klaeren

**Audit-Finding:** AUD-012  
**Ziel:** KB-Dateiformat ist eindeutig und Parsefehler fallen in CI/Runtime sichtbar auf.

### Umsetzung

1. Entscheidung: echte YAML-Unterstuetzung oder Umbenennung nach `.json`.
2. Strict loading im CI-Pfad erzwingen.
3. Non-strict Defaults nur fuer lokale Development-Fallbacks dokumentieren.
4. Parsefehler mit Dateipfad und Department melden.

### Akzeptanzkriterien

- Eine syntaktisch nicht unterstuetzte KB-Datei kann nicht still ignoriert werden.
- CI testet alle KB-Dateien im strict mode.

---

## ZD-P1-4 - Retry-Limits als Tool-Guard erzwingen

**Audit-Finding:** AUD-013  
**Ziel:** `MAX_TASK_RETRIES` ist ein harter Runtime-Guard, keine reine Prompt-Regel.

### Umsetzung

1. In `run_research()` vor Retry pruefen: `attempt >= MAX_TASK_RETRIES`.
2. Bei Limit erreicht: `next_required_action=judge_decision` oder `closed_unresolved`.
3. Duplicate Research darf Attempt-Zaehler nicht erhoehen.
4. Revision Context aus Critic Review an Worker uebergeben.

### Akzeptanzkriterien

- Kein Task kann ueber Max-Retry hinaus weiterforschen.
- Attempt-Zaehler bildet echte Research-Versuche ab.
- Rejected Critic Feedback erreicht den naechsten Worker-Run.

---

## ZD-P1-5 - ReportWriter nach Finalisierung ausfuehren

**Audit-Finding:** AUD-014  
**Ziel:** `report_package` enthaelt finalen Status, Meeting Actions und Final Briefing.

### Umsetzung

1. ReportWriter-Aufruf hinter `_sync_finalization_artifacts()` verschieben.
2. Alternativ ReportWriter nach Finalisierung erneut ausfuehren und altes Paket ersetzen.
3. `report_package` in Export und Dashboard aus finalisiertem `pipeline_data` bauen.

### Akzeptanzkriterien

- Report enthaelt `run_status`, `meeting_readiness_assessment`, `meeting_actions`, `final_briefing`.
- Keine `n/v`-Statuswerte im erfolgreichen Finalreport.

---

## ZD-P1-6 - Run-Export atomar und gelockt machen

**Audit-Finding:** AUD-015  
**Ziel:** Run-Artefakte und Follow-up-History bleiben bei Crash und Parallelzugriff konsistent.

### Umsetzung

1. Helper `atomic_write_json(path, payload)` mit Tempfile und `replace()`.
2. `export_run()` auf atomare Writes umstellen.
3. `export_follow_up()` mit per-run `FileLock` schuetzen.
4. Optional Manifest schreiben, das vollstaendige Export-Sets markiert.

### Akzeptanzkriterien

- Parallel-Follow-ups verlieren keine Eintraege.
- Crash waehrend Export hinterlaesst keine halb geschriebenen JSON-Dateien.

---

## P2 Governance

## ZD-P2-1 - CODEOWNERS und Review-Gates schaerfen

**Audit-Finding:** AUD-016  
**Ziel:** High-impact-Aenderungen brauchen sichtbare unabhaengige Review-Zuordnung.

### Umsetzung

1. CODEOWNERS nach technischen Bereichen aufteilen:
   `src/orchestration/**`, `src/agents/**`, `src/memory/**`, `knowledge/**`, `.github/**`, `requirements*`.
2. Mindestens zweiten Owner oder Team fuer Security/Governance-Pfade eintragen.
3. Branch Protection dokumentieren: Code Owner Review required, mindestens zwei Approvals fuer High-impact Paths.
4. CODEOWNERS-Lint-Test ergaenzen.

### Akzeptanzkriterien

- Kein High-impact-Pfad hat nur Einzelowner ohne zweiten Review-Pfad.
- Branch-Protection-Anforderungen sind dokumentiert.

---

## Definition of Done fuer den gesamten ZoDo Plan

- Alle P0-ZoDos sind umgesetzt.
- Alle P0-Regressionstests laufen lokal und in CI.
- `pytest -q tests/architecture --collect-only` funktioniert in Minimal-Env.
- CI fuehrt mindestens Architecture-, Query-, Readiness-, Golden- und Smoke-Tests aus.
- Keine offenen High-Findings aus dem Audit bleiben ohne dokumentierte Risikoakzeptanz.
- README und Architekturdocs beschreiben den tatsaechlichen Runtime-Ablauf.
- CODEOWNERS/Review-Gates sind fuer High-impact-Pfade aktualisiert oder explizit als organisatorisches Restrisiko dokumentiert.

---

## Empfohlene Patch-Reihenfolge

1. ZD-P0-4 `run_id` Safety.
2. ZD-P0-6 Statusvokabular.
3. ZD-P0-3 Artifact-/Judge-Guards.
4. ZD-P0-1 Runtime-Phasenordnung.
5. ZD-P0-2 Auto-Close Mapping.
6. ZD-P0-7 Follow-up-Evidence-Resolver.
7. ZD-P0-5 LTM Scrubbing.
8. ZD-P0-9 Architecture-Test-Layer.
9. ZD-P0-8 CI-Produkttests.
10. ZD-P1-1 bis ZD-P1-6.
11. ZD-P2-1.

