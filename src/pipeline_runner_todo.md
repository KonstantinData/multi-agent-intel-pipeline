# pipeline_runner.py TODO

Diese Checkliste sammelt empfohlene Verbesserungen fuer `src/pipeline_runner.py`.
Sie dient als Arbeitsliste, um erledigte Punkte nachvollziehbar abhaken zu koennen.

## Struktur und Verantwortlichkeiten

- [x] UI-Metadaten aus `pipeline_runner.py` auslagern
  - `AGENT_META` und `PIPELINE_STEPS` liegen jetzt in `src/app/pipeline_metadata.py`.
  - `ui/app.py` importiert die UI-Metadaten direkt aus diesem Modul.
  - Warum: UI-Darstellung und Runtime-Orchestrierung bleiben getrennt.

- [x] `run_pipeline(...)` in private Phasenfunktionen zerlegen
  - Umgesetzt mit:
    - `_initialize_run(...)`
    - `_build_supervisor_brief(...)`
    - `_run_first_pass(...)`
    - `_run_auto_close_if_required(...)`
    - `_run_synthesis_phase(...)`
    - `_finalize_readiness(...)`
    - `_assemble_report_and_export(...)`
  - Warum: Der Ablauf wird leichter testbar, dokumentierbar und wartbar.

- [x] Phasen-Ergebnisse typisieren
  - Umgesetzt mit:
    - `InitialRunState`
    - `SupervisorBriefResult`
    - `FirstPassResult`
    - `AutoCloseResult`
    - `SynthesisPhaseResult`
    - `FinalizationResult`
  - Warum: Weniger lose `dict[str, Any]` und große Tupel, klarere Contracts zwischen Phasen.

## Runtime-Verhalten

- [x] Long-Term-Memory-Backfill aus dem heißen Request-Pfad prüfen
  - Backfill läuft nicht mehr automatisch bei jedem `run_pipeline(...)`.
  - Er ist explizit über `LIQUISTO_BACKFILL_LONG_TERM_MEMORY=1` aktivierbar.
  - Der Run schreibt `backfill_enabled` und `backfilled_patterns` in `resolution_state["long_term_memory"]`.
  - Warum: Globaler Seiteneffekt und potenziell teure Arbeit sollten nicht ungeprüft in jedem Run passieren.

- [x] Domain-Normalisierung zentralisieren
  - `normalized_domain = normalize_domain(intake.web_domain)` wird in `_initialize_run(...)` einmal bestimmt.
  - Der Wert steht in `run_context.intake["normalized_domain"]` und wird fuer Strategy Retrieval genutzt.
  - Warum: Verhindert Drift und doppelte Normalisierungslogik.

- [x] Fruehen Checkpoint nach Step 1 einfuehren
  - Neuer Checkpoint: `after_supervisor_brief`.
  - Zeitpunkt: direkt nach `supervisor_brief`, `question_registry`, `answer_matrix` und erster Supervisor-Nachricht.
  - Warum: Step 1 erzeugt bereits wichtige wiederherstellbare Artefakte vor dem Department Loop.

- [x] Fehlerbehandlung phasenbewusster machen
  - `resolution_state["current_phase"]` und `resolution_state["last_checkpoint"]` werden gepflegt.
  - Fehlerexporte enthalten `failed_phase`, `last_checkpoint` und `resolution_state["failure"]`.
  - Warum: Lange Agent-Runs brauchen bessere Fehlerlokalisierung als nur einen Error-String.

## Leitlinie

- [x] Reihenfolge der Runtime-Phasen beibehalten, solange keine Architekturentscheidung dagegen spricht
  - Bestehender sinnvoller Ablauf:
    - Intake
    - Runtime-Agenten
    - Memory Retrieval
    - Supervisor Brief
    - Department Loop
    - Auto-Close
    - Synthesis
    - Readiness
    - Report
    - Export
  - Warum: Der Ablauf passt zur aktuellen Supervisor-/Department-Architektur; das Hauptproblem ist die Konzentration zu vieler Verantwortlichkeiten in einer Datei.
