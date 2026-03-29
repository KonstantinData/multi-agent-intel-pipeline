# Refactor Baseline & Qualitätsartefakte

Stand: **2026-03-29 (UTC)**.

Dieses Dokument definiert die Baseline-Artefakte für Regressionen im Runtime-Refactor.

## Ziel

Die Baseline verankert überprüfbare Referenzen für:

1. State-Persistenz (RunContext/Store Snapshot)
2. Answer-Matrix-Lifecycle
3. ResolutionController-Klassifikation
4. Pause/Resume-Status und Entrypoints
5. Finalization-Gate und Export-Verträge

## Baseline-Run

- Baseline-Run-ID: `baseline_run_20260329`
- Artefakt-Root: `tests/golden/runs/baseline_run_20260329/`

## Golden-Artefakte

### Run-Artefakte

- `run_context.json`: serialisierter RunContext inkl. `resolution_state`
- `memory_snapshot.json`: serialisierter ShortTermMemoryStore
- `pipeline_data.json`: validiertes Pipeline-Output-Modell
- `run_meta.json`: exportierte Metadaten inkl. Status/Unresolved

### Qualitätsreferenz

- `tests/golden/quality_reference/answer_matrix_reference.json`
- `tests/golden/quality_reference/resolution_buckets_reference.json`

Diese Referenzen sind bewusst klein gehalten und dienen als verhaltensorientierte Regression-Anker.
