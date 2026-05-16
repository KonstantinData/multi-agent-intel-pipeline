# Compliance Learning Loop

## Ziel

Der Compliance Learning Loop prüft jede neu erstellte oder geänderte Datei
kontextabhängig nach Dateityp, Zweck und Risikoklasse gegen Governance-,
Sicherheits-, Datenschutz-, Format- und Qualitätsregeln.

## Komponenten

1. Policy-Datei: `.codex/compliance/policies/file_compliance_policy.json`
2. Checker: `.codex/compliance/src/compliance/checker.py`
3. Learning: `.codex/compliance/src/compliance/learning.py`
4. Vorschlags-Validator und Voting: `.codex/compliance/src/compliance/validator.py`
5. Run-Brain-Anbindung: `.codex/compliance/src/compliance/run_brain.py`
6. Hook-Skripte:
   - `.codex/compliance/scripts/hooks/pre_tool_use.py`
   - `.codex/compliance/scripts/hooks/post_tool_use.py`
   - `.codex/compliance/scripts/hooks/error_occurred.py`
   - `.codex/compliance/scripts/hooks/session_end.py`
7. Integrierte Standard-Checks im zentralen Hook:
   - `ruff check --fix` für Python-Dateien
   - `bandit -q -x tests` für sicherheitsrelevante Python-Dateien
8. Workspace-Watcher für sofortige Prüfung ohne Commit:
   - `.codex/compliance/scripts/watch_workspace_compliance.py`

## Ablauf

1. `pre_tool_use` prüft die Datei gegen aktive Regeln.
2. Das Ergebnis wird als strukturiertes Compliance-Artifact erzeugt.
3. Artifacts werden im Run Brain gespeichert.
4. Learning bildet Prozessmuster (Fehlerraten, Wiederholungen, Fix-Quoten).
5. Vorschläge entstehen nur, wenn derselbe Fehlertyp häufiger als dreimal auftritt.
6. Jeder Vorschlag wird validiert.
7. Bei unklarer Lage entscheidet ein zusätzliches Voting-Team.
8. Erst der Freigabeprozess entscheidet über die produktive Übernahme.
9. Der zentrale Hook schlägt fehl, wenn Regelverstöße, Ruff-Fehler oder Bandit-Funde vorhanden sind.
10. Mit `--changed-only` werden relevante Änderungen aus dem Working Tree geprüft, inklusive ignorierter Dateien unter `.codex/compliance`.

## Schwellwerte

1. Optimierungsvorschläge erst ab `min_repeat_failures_for_optimizer = 4`.
2. Validator lehnt Vorschläge mit hoher Fehlalarmquote ab.
3. Bei kleiner Datenbasis oder gemischter Evidenz wird Voting ausgelöst.

## Schnellstart

```powershell
python .codex/compliance/scripts/check_compliance_policies.py `
  --strict `
  --changed-only `
  --purpose runtime_code `
  --risk-level high `
```

```powershell
python .codex/compliance/scripts/watch_workspace_compliance.py `
  --strict `
  --interval-sec 5 `
  --purpose runtime_code `
  --risk-level high
```

## Hinweis

Das Long-Term Process Brain speichert Prozessmuster und Frequenzen
regelorientiert. Fallbezogene Inhalte bleiben im Run Brain.
