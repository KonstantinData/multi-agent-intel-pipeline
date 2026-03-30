# Refactor Follow-up — Detaillierte Umsetzungsanweisung für den Agenten

## Zweck dieser Datei

Diese Datei ist die **operative Arbeitsanweisung** für den Implementierungs-Agenten.
Sie ergänzt:

- `refactor-architecture-final.md`
- `refactor-architecture-audit-final.md`

und übersetzt die Zielarchitektur in eine **konkrete, repo-spezifische Reihenfolge mit klaren Eingriffspunkten**.

Diese Datei beantwortet für den Agenten explizit:

- **was** umzubauen ist,
- **warum** dieser Umbau nötig ist,
- **wo** im Repo die Änderungen stattfinden müssen,
- **wie** die Änderungen technisch verdrahtet werden,
- **woran** erkannt wird, dass ein Abschnitt wirklich fertig ist.

---

## 1. Ausgangslage des aktuellen Repo-Zustands

### 1.1 Was bereits vorhanden ist

Das Repo enthält bereits:

- die bestehende Runtime-Pipeline mit Supervisor, Departments, Synthesis und Export,
- die Dateien `refactor-architecture-final.md` und `refactor-architecture-audit-final.md`,
- die bestehenden Laufzeit-Anker:
  - `src/pipeline_runner.py`
  - `src/orchestration/supervisor_loop.py`
  - `src/agents/lead.py`
  - `src/agents/worker.py`
  - `src/orchestration/follow_up.py`
  - `src/memory/short_term_store.py`
  - `src/orchestration/run_context.py`
  - `ui/app.py`
  - `src/exporters/json_export.py`
  - `src/exporters/pdf_report.py`

### 1.2 Was noch **nicht** umgesetzt ist

Die Zielarchitektur ist im Code **noch nicht** vollständig angekommen.
Insbesondere fehlen im aktuellen Stand die neuen zentralen Runtime-Bausteine oder sie sind nicht aktiv verdrahtet:

- `QuestionRegistry`
- `AnswerMatrix`
- `ResolutionController`
- `DashboardState`
- `resume_pipeline(...)`
- `MeetingReadinessAssessment`
- `FinalBriefingComposer`
- `meeting_actions`
- eine echte Closure-Phase
- eine echte `needs_user_selection` Pause/Resume-Semantik

### 1.3 Wichtigste Zielkorrektur

Das System darf nicht mehr auf **Department Completion** optimieren.
Es muss auf **Meeting Readiness** optimieren.

Das bedeutet:

- keine generischen finalen `open_questions` als Normalzustand,
- keine generischen finalen `next_steps` als Zeichen unvollständiger Recherche,
- stattdessen:
  - beantwortete Meeting-Fragen,
  - gezielte zusätzliche Recherche bei öffentlich schließbaren Lücken,
  - explizite Nutzerentscheidung bei optionaler Tiefe,
  - explizite `customer_confirmation_items` für nicht öffentlich auflösbare Punkte,
  - ein finales Briefing mit **Meeting Actions**.

---

## 2. Verbindliche Arbeitsweise des Agenten

## 2.1 Reihenfolge ist Pflicht

Der Agent arbeitet **strictly sequential** in dieser Reihenfolge:

- RA-00
- RA-01
- RA-02
- RA-03
- RA-04
- RA-05
- RA-06
- RA-07
- RA-08
- RA-09
- RA-10

Kein Überspringen. Keine Parallelisierung über mehrere RA-Sections.

## 2.2 Audit-Gate nach jeder Section

Nach **jedem** Abschnitt muss der Agent das passende Audit aus `refactor-architecture-audit-final.md` ausführen.

Regel:

- Nur wenn das Ergebnis **TRUE** ist, darf der Agent zur nächsten Section gehen.
- Bei **FALSE** muss der Agent dieselbe Section nacharbeiten.
- Kein „fast fertig“, kein „später korrigieren“.

## 2.3 Keine kosmetischen Änderungen

Verboten sind:

- doc-only Änderungen ohne Runtime-Effekt,
- nur neue Typdefinitionen ohne aktive Verwendung,
- nur neue Felder ohne `snapshot()`-Persistenz,
- nur UI-Anzeige ohne Verhaltensänderung,
- nur Prompts ohne Code-Logik,
- nur Dead-Code-Klassen ohne Wiring.

## 2.4 Beweisprinzip

Jeder Abschnitt gilt nur dann als umgesetzt, wenn alle vier Ebenen sichtbar sind:

1. **Code-Symbol existiert**
2. **Symbol ist im Live-Run verdrahtet**
3. **State wird persistiert/exportiert**
4. **Behavior wird durch Test oder echten Run nachweisbar**

---

## 3. Qualitätsziel des Umbaus

Der Agent darf sich **nicht** an den schwächeren bisherigen Repo-Briefings orientieren.
Der primäre Qualitätsanker ist der starke Deep-Research-Bericht.

Daraus ergeben sich diese Qualitätsziele:

- stärkere Inventory-/Working-Capital-Signale,
- echte Contact Intelligence,
- klarer Opportunity Path,
- saubere Trennung von Fakt, Inferenz und Hypothese,
- konkrete Meeting Actions,
- keine Research-Reste als Success-Output.

---

## 4. Operative Gesamtstrategie für den Umbau

Der Agent soll **nicht** das Repo neu erfinden.
Er soll die bestehende Pipeline **kontrolliert umbauen**.

Die Strategie lautet:

1. Bestehende Pipeline stabilisieren und baseline-fähig machen.
2. Neue typed Meeting-Ready-State-Schicht einziehen.
3. Vor Department-Lauf die Meeting-Fragen definieren.
4. Departments auf Evidence-Produktion umstellen.
5. Danach eine echte Closure-Phase einbauen.
6. Falls nötig: Dashboard-Handoff mit Pause/Resume.
7. Erst dann ein Final Briefing komponieren.
8. Exporte, Follow-up, Tests und Doku nachziehen.

---

# 5. Detaillierte Umsetzungsanweisung pro RA-Section

# RA-00 — Baseline, Golden Traces, Qualitätsrubrik

## Warum

Bevor die Architektur verändert wird, braucht der Agent einen festen Vergleichspunkt.
Ohne Baseline ist später nicht erkennbar:

- was sich fachlich verbessert hat,
- was versehentlich kaputt ging,
- welche Exporte/Shapes gedriftet sind.

## Was zu tun ist

### 1. Baseline-Dokumentation erstellen

Neue Datei anlegen:
- `docs/refactor_baseline.md`

Inhalt:
- aktueller Run-Flow von `src/pipeline_runner.py`
- Rolle von `src/orchestration/supervisor_loop.py`
- aktueller Department-/Synthesis-/Export-Flow
- wo heute `open_questions` und `next_steps` entstehen
- was heute den Run als „erfolgreich“ gelten lässt
- warum das noch nicht meeting-ready ist

### 2. Golden Trace anlegen

Verzeichnis anlegen:
- `tests/golden/runs/<baseline_run_id>/`

Mindestens speichern:
- `run_meta.json`
- `run_context.json`
- `pipeline_data.json`
- optional gekürzte `chat_history.json`

### 3. Qualitätsanker ableiten

Verzeichnis anlegen:
- `tests/golden/quality_reference/`

Dateien anlegen:
- `deep_research_quality_excerpt.md`
- `deep_research_quality_rubric.md`

Rubrik muss mindestens bewerten:
- inventory signal quality
- contact intelligence
- opportunity prioritization
- buyer/redeployment specificity
- fact vs inference separation
- meeting action usefulness

### 4. Drift Guard Test schreiben

Neuen oder bestehenden Test ergänzen, der auf Top-Level-Shape prüft:
- Export-Keys in `pipeline_data.json`
- Pflichtfelder in `run_context.json`

## Wo zu ändern ist

- `src/pipeline_runner.py`
- `src/exporters/json_export.py`
- `tests/...`
- `docs/...`

## Wie geprüft wird

Audit RA-00.

---

# RA-01 — Typed Meeting-Ready-State einführen

## Warum

Die bestehende Runtime basiert noch zu stark auf impliziten Dict-Shapes.
Für die neue Architektur braucht das System maschinenlesbare, persistierbare Hauptobjekte.

## Was zu tun ist

### 1. Neue Modelle anlegen

Neue Datei:
- `src/models/meeting_ready.py`

Dort definieren:
- `MeetingQuestion`
- `QuestionRegistry`
- `AnswerStatus`
- `AnswerCell`
- `AnswerMatrix`
- `EvidenceItem`
- `EvidencePacket`
- `GapSeverity`
- `GapResolutionClass`
- `GapCandidate`
- `UserDepthOption`
- `DashboardState`
- `ResolutionDecision`
- `ResolutionPlan`
- `ResolutionEvent`
- `MeetingReadinessStatus`
- `MeetingReadinessAssessment`
- `CustomerConfirmationItem`
- `MeetingAction`
- `FinalBriefing`

### 2. RunContext erweitern

Datei:
- `src/orchestration/run_context.py`

Neue Felder aufnehmen:
- `question_registry`
- `answer_matrix`
- `evidence_packets`
- `gap_candidates`
- `resolution_plan`
- `dashboard_state`
- `customer_confirmation_items`
- `meeting_actions`
- `meeting_readiness_assessment`
- `phase`

`RunContext.snapshot()` muss diese Felder exportieren.

### 3. ShortTermMemoryStore erweitern

Datei:
- `src/memory/short_term_store.py`

Neue persistierte Felder:
- `question_registry_snapshot`
- `answer_matrix_snapshot`
- `evidence_packets`
- `gap_candidates`
- `resolution_events`
- `user_depth_selections`
- `customer_confirmation_items`
- `meeting_actions`
- `meeting_readiness_history`

`snapshot()` muss diese Felder exportieren.

### 4. Legacy-Compat nur kontrolliert

Wenn `open_questions` und `next_actions` im aktiven Pfad noch verwendet werden:
- neue Datei `src/orchestration/compat_legacy.py`
- deterministic converter functions erstellen
- klar als temporär markieren

## Wie der Agent vorgeht

- zuerst Typen definieren,
- dann RunContext,
- dann ShortTermMemory,
- dann Snapshot-Wiring,
- dann Compat.

Nicht umgekehrt.

## Wie geprüft wird

Audit RA-01.

---

# RA-02 — Question Registry + Answer Matrix vor dem Department-Run bauen

## Warum

Das System muss **vor** der Recherche wissen, welche Fragen für Meeting Readiness beantwortet werden müssen.
Sonst bleibt die Architektur department-zentriert statt frage-zentriert.

## Was zu tun ist

### 1. Single Source of Truth für Meeting Questions anlegen

Datei:
- `src/app/use_cases.py`

Ergänzen:
- `MEETING_QUESTIONS_V1`
- oder Builder-Funktion `build_meeting_questions()`

### 2. Tasks mit Question IDs verbinden

Bestehende Backlog-Items erweitern um:
- `question_ids`
- `question_weight` oder gleichwertige Priorisierung

Dateien:
- `src/app/use_cases.py`
- ggf. `src/orchestration/task_router.py`

### 3. Planner bauen

Neue Dateien:
- `src/orchestration/question_planner.py`
- `src/orchestration/answer_matrix.py`

Funktionen:
- `build_question_registry(...)`
- `init_answer_matrix(...)`

### 4. Vor dem Supervisor-Loop verdrahten

Datei:
- `src/pipeline_runner.py`

Vor `run_supervisor_loop(...)`:
- registry bauen
- matrix bauen
- in RunContext speichern
- in ShortTermMemory spiegeln

### 5. Supervisor-Updates ergänzen

Datei:
- `src/orchestration/supervisor_loop.py`

Nach Department-Ausgang:
- `accepted` → answered
- `degraded` → partial
- `rejected` → unanswered + GapCandidate

Wichtig:
Die Matrix darf nicht nur initialisiert, sondern muss im echten Run aktualisiert werden.

## Wie geprüft wird

Audit RA-02.

---

# RA-03 — Departments zu Evidence-Producern umbauen

## Warum

Heute produzieren Departments zu stark lokale Mini-Ergebnisse.
Künftig müssen sie vor allem **Evidence**, **Gap Candidates** und **Answer Updates** liefern.

## Was zu tun ist

### 1. Department Output Contract erweitern

Datei:
- `src/models/schemas.py`

DepartmentPackage erweitern um:
- `evidence_packets`
- `gap_candidates`
- `answer_matrix_updates`
- `source_register`
- optional `confidence_breakdown`

### 2. Worker erzeugt EvidencePackets

Datei:
- `src/agents/worker.py`

Pro Task mindestens ein `EvidencePacket` erzeugen mit:
- `task_key`
- `question_ids`
- `claims`
- `evidence_items`
- `counter_signals`
- `confidence`

### 3. Lead persistiert typed outputs

Datei:
- `src/agents/lead.py`

Pflichten:
- EvidencePackets sammeln und persistieren
- typed GapCandidates persistieren
- AnswerMatrixUpdates aus Department-Outputs ableiten

### 4. Department-Rolle explizit umdefinieren

In Code-Kommentaren, Modul-Docstrings und ggf. Contracts klarstellen:
- Departments sind **question-coverage contributors**
- nicht finale Briefing-Eigentümer

### 5. Legacy Narrative degradieren

Narrative Summaries dürfen noch existieren,
aber Closure und Meeting Readiness dürfen **nicht** mehr davon abhängen.

## Wie geprüft wird

Audit RA-03.

---

# RA-04 — Resolution Controller + Closure Loop

## Warum

Hier passiert der eigentliche Wandel.
Nicht beantwortete öffentlich recherchierbare meeting-kritische Punkte dürfen nicht im Bericht landen, sondern müssen aktiv weiterrecherchiert werden.

## Was zu tun ist

### 1. ResolutionController anlegen

Neue Datei:
- `src/orchestration/resolution_controller.py`

Public API:
- `build_resolution_plan(...)`
- `run_closure_pass(...)`
- `assess_meeting_readiness(...)` oder delegierter Hook

### 2. Klassifikationsregeln implementieren

Neue Datei:
- `src/orchestration/closure_rules.py`

Jeder GapCandidate muss genau einer Klasse zugeordnet werden:
- `AUTO_CLOSE_REQUIRED`
- `USER_DECISION_REQUIRED`
- `CUSTOMER_CONFIRMATION_REQUIRED`
- `NOT_MEETING_CRITICAL`
- `BLOCKING_FAILURE`

### 3. Targeted Follow-up Research verdrahten

Bestehende Follow-up-Mechanik nutzen:
- `src/orchestration/department_runtime.py`
- `src/orchestration/follow_up.py`

Für `AUTO_CLOSE_REQUIRED`:
- automatisch bounded follow-up research starten
- EvidencePackets aktualisieren
- Answer Matrix aktualisieren
- Gap status aktualisieren

### 4. Bounds erzwingen

Persistierte Limits einführen:
- max closure passes
- max followups per pass
- elapsed/time budget
- token/usage budget
- stop reason

### 5. Finalization blockieren

Wenn öffentlich recherchierbare meeting-kritische Gaps offen bleiben:
- keine Success-Finalisierung erlauben

## Wie geprüft wird

Audit RA-04.

---

# RA-05 — Resolution Dashboard + Pause/Resume

## Warum

Es gibt Punkte, die optional tiefer gemacht werden können oder Nutzerpräferenzen brauchen.
Diese dürfen nicht still ignoriert werden.

## Was zu tun ist

### 1. Run-Status `needs_user_selection` einführen

Datei:
- `src/pipeline_runner.py`

Wenn Dashboard erforderlich ist:
- Run pausieren
- RunContext persistieren
- `dashboard_state` + `resolution_plan` exportieren

### 2. Resume-Funktion bauen

Neue oder erweiterte Funktion:
- `resume_pipeline(...)`

Ort:
- `src/pipeline_runner.py`
- oder `src/orchestration/dashboard_runtime.py`

Pflichten:
- Run laden
- Nutzerentscheidungen persistieren
- optionale Depth-Follow-ups ausführen
- deterministisch fortsetzen

### 3. UI-Dashboard bauen

Datei:
- `ui/app.py`

Dashboard anzeigen mit:
- beantworteten Kernfragen
- optionaler Tiefe
- customer confirmation items
- Auswahl / Skip / Resume

### 4. Silent Bypass verhindern

Ohne notwendige Dashboard-Entscheidung:
- keine Finalisierung

## Wie geprüft wird

Audit RA-05.

---

# RA-06 — MeetingReadinessGate + FinalBriefingComposer

## Warum

Erst hier entsteht der eigentliche neue Success-Output.
Nicht mehr Research-Reste, sondern ein meeting-taugliches Briefing.

## Was zu tun ist

### 1. Gate bauen

Neue Datei:
- `src/orchestration/meeting_readiness.py`

Regeln:
- keine offenen öffentlich recherchierbaren meeting-kritischen Fragen
- keine fehlenden Dashboard-Entscheidungen
- Mindestqualität für Evidence auf kritischen Fragen

### 2. Composer bauen

Neue Datei:
- `src/orchestration/final_briefing_composer.py`

Output:
- `management_snapshot`
- `answer_matrix_summary`
- `meeting_actions`
- `customer_confirmation_items`
- `evidence_appendix`

### 3. Success Path umstellen

Datei:
- `src/pipeline_runner.py`

Vor finalem Export:
- readiness evaluieren
- bei fail → blockierter Status
- bei pass → composer ausführen

### 4. UI und PDF anpassen

Dateien:
- `ui/app.py`
- `src/exporters/pdf_report.py`

Primär anzeigen:
- `meeting_actions`

Nicht mehr success-normal:
- generische `open_questions`
- generische `next_steps`

## Wie geprüft wird

Audit RA-06.

---

# RA-07 — Exporte, Checkpoints, Follow-up Grounding

## Warum

Die neue Architektur ist wertlos, wenn sie nicht persistiert und später wieder geladen werden kann.

## Was zu tun ist

### 1. Exporte erweitern

Datei:
- `src/exporters/json_export.py`

Exportieren:
- question registry
- answer matrix
- evidence packets
- gap candidates
- resolution plan / events
- dashboard state / selections
- customer confirmation items
- meeting actions
- meeting-readiness assessment
- phase / stop reasons

### 2. Follow-up umstellen

Datei:
- `src/orchestration/follow_up.py`

Follow-up muss primär nutzen:
- answer matrix
- evidence packets

Nicht mehr primär:
- nur narrative Legacy-Strukturen

### 3. Phase-aware checkpointing

Nach jeder Hauptphase checkpointen:
- first pass
- closure
- dashboard pause
- dashboard resume
- finalization

## Wie geprüft wird

Audit RA-07.

---

# RA-08 — Runtime Guardrails

## Warum

Die neue Architektur braucht harte Laufzeitbegrenzungen und schema-erzwungene Artefakte.

## Was zu tun ist

### 1. Structured Outputs real verdrahten

Schema-erzwingen für:
- `EvidencePacket`
- `GapCandidate`
- `AnswerMatrixUpdate`
- `ResolutionDecision`
- `FinalBriefing` (wenn modellgeneriert)

### 2. Budgets einführen

Phase-aware budgets:
- `first_pass_budget`
- `closure_budget`
- `optional_depth_budget`

Persistieren:
- Verbrauch
- exhaustion
- stop reason

### 3. Determinismus erhöhen

- stabile Sortierreihenfolgen
- seed-enabled mode, wo möglich
- persistierte resolution timeline

### 4. Guardrail-Telemetrie sichtbar machen

- Budgetstatus
- stop reason
- closure events
- ordering rules

## Wie geprüft wird

Audit RA-08.

---

# RA-09 — Tests und Golden Regression

## Warum

Ohne starke Verhaltenstests kann der Umbau nicht stabil bleiben.

## Was zu tun ist

Neue Tests anlegen für:
- question registry
- answer matrix
- resolution controller
- dashboard pause/resume
- final briefing composer
- meeting-readiness gate

Negative-Path-Tests:
- unresolved public meeting-critical gaps block finalization
- missing dashboard decision blocks finalization
- schema parse failure blocks success

Golden Regression:
- contract-level drift guards

## Wie geprüft wird

Audit RA-09.

---

# RA-10 — Doku, Diagramme, Cleanup

## Warum

Am Ende dürfen Code und Dokumentation nicht auseinanderlaufen.

## Was zu tun ist

### 1. Docs aktualisieren

Anpassen:
- `docs/target_runtime_architecture.md`
- `docs/drawio/2026-03-29_updated_runtime_architecture.md`
- `docs/drawio/runtime_architecture.drawio`
- `README.md`

Flow muss jetzt zeigen:
- question planning
- first-pass department evidence
- closure loop
- dashboard pause/resume
- readiness gate
- final briefing composer
- export

### 2. Compat reduzieren

Nur noch minimale, explizit dokumentierte Legacy-Kompatibilität behalten.

### 3. Success-Wording bereinigen

Kein Success-Path darf generische `open_questions` als Normalzustand beschreiben.

## Wie geprüft wird

Audit RA-10.

---

## 6. Arbeitsregel für den Agenten bei Unsicherheit

Wenn der Agent auf eine unklare Architekturentscheidung stößt, gilt:

1. Bevorzuge die Variante, die **Meeting Readiness** stärker schützt.
2. Bevorzuge **typed runtime state** vor impliziten Dicts.
3. Bevorzuge **code-governed transitions** vor Prompt-Heuristik.
4. Bevorzuge **Pause/Resume** vor stiller Ignorierung.
5. Bevorzuge **korrekt blockierte Finalisierung** vor schwachem Success-Output.

---

## 7. Verbotene Fehlmuster

Der Agent darf diese Fehlmuster nicht produzieren:

- neue Klassen anlegen, aber nicht importieren oder aufrufen
- `meeting_actions` nur kosmetisch einführen, während `next_steps` weiter die eigentliche Wahrheit bleibt
- Question Registry nur als Doku-Konstante anlegen
- Dashboard nur anzeigen, ohne Runtime-Effekt
- Closure nur als Prompt formulieren, aber nicht im Code ausführen
- Audit-Datei aktualisieren, ohne die Runtime zu ändern
- generische finale `open_questions` in Success-Outputs stehen lassen

---

## 8. Finaler Erfolgsmaßstab

Der Agent ist **nicht** fertig, wenn „viele Dateien geändert“ wurden.
Der Agent ist erst fertig, wenn:

- alle RA-Sections `TRUE` auditiert sind,
- das Repo tatsächlich meeting-ready finalisieren kann,
- und Success-Outputs keine generischen Research-Reste mehr enthalten.

Das ist der Maßstab.
