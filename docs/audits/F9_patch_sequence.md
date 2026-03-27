# F9 — ReportWriter-Rolle architektonisch bereinigen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F9  
**Ziel:** Keine Scheinkomponenten. Jede Runtime-Rolle muss entweder operational sein oder entfernt/umbenannt werden.

---

## Ist-Zustand: Analyse

### `ReportWriterAgent` ist ein Stub

```python
class ReportWriterAgent:
    name = "ReportWriter"
    def __init__(self) -> None:
        self.model_name = get_role_model_selection(self.name)[0]
        self.allowed_tools = resolve_allowed_tools(self.name, "report_writing")
```

13 Zeilen. Keine Methoden, keine Logik, keine `run()`-Funktion.

### Instanziierung ohne Nutzung

- `runtime_factory.py`: `"report_writer": ReportWriterAgent()` — wird instanziiert
- `pipeline_runner.py`: `agents["report_writer"]` wird **nie gelesen** — der Key existiert im Dict, wird aber nie aufgerufen

### Die eigentliche Report-Erzeugung

Laeuft komplett ohne den Agent:

| Funktion | Datei | Typ |
|----------|-------|-----|
| `build_report_package()` | `src/orchestration/synthesis.py` | Regelbasierte Funktion |
| `generate_pdf()` | `src/exporters/pdf_report.py` | Regelbasierte PDF-Erzeugung |

Beide werden direkt von `pipeline_runner.py` aufgerufen. Kein Agent involviert.

### Wo "ReportWriter" als Name vorkommt

| Stelle | Zweck | Braucht Agent? |
|--------|-------|:-:|
| `AGENT_SPECS` | UI-Metadaten (Icon, Farbe, Summary) | Nein — nur Metadaten |
| `PIPELINE_STEPS` | UI-Fortschrittsanzeige | Nein — nur Label |
| `emit_message(agent="ReportWriter")` | Observability-Event | Nein — nur String |
| `ROLE_MODEL_DEFAULTS` | Model-Config | Nein — wird nie fuer LLM-Calls genutzt |
| `tool_policy.py` | Leere Tool-Liste | Nein — keine Tools |
| `MEMORY_ROLE_STATUS` | `excluded` (F6) | Nein — kein Memory |
| `runtime_factory.py` | Instanziierung | **Einzige Stelle die den Agent erzeugt** |

### Fazit

`ReportWriterAgent` ist eine **Scheinkomponente**: Sie wird instanziiert, aber nie operativ genutzt. Die Report-Erzeugung ist eine regelbasierte Funktion, kein Agent-Workflow. Der Name "ReportWriter" wird nur als UI-Label und Observability-Tag benoetigt, nicht als Runtime-Agent.

---

## Ziel-Zustand

### Entscheidung: Kein Agent, sondern regelbasierte Komponente

`ReportWriterAgent` wird entfernt. Die Report-Erzeugung bleibt was sie ist: eine regelbasierte Funktion in `synthesis.py` + `pdf_report.py`.

Der Name "ReportWriter" bleibt als:
- UI-Label in `AGENT_SPECS` und `PIPELINE_STEPS`
- Observability-Tag in `emit_message()`

Aber nicht mehr als:
- Runtime-Agent-Klasse
- Instanziiertes Objekt in `agents` Dict

### Architekturdiagramm-Alignment

Das README beschreibt den ReportWriter als eigenstaendige Rolle. Nach F9:
- ReportWriter ist eine **Rendering-Komponente**, kein Agent
- Architekturdiagramm und Code stimmen ueberein

---

## Patch-Sequenz

### Patch 1 — `ReportWriterAgent` Klasse entfernen

**Datei:** `src/agents/report_writer.py`

Datei entfernen oder auf leeren Docstring reduzieren (falls Imports anderswo brechen wuerden).

### Patch 2 — `runtime_factory.py` bereinigen

**Datei:** `src/agents/runtime_factory.py`

- `from src.agents.report_writer import ReportWriterAgent` entfernen
- `"report_writer": ReportWriterAgent()` aus dem Return-Dict entfernen

### Patch 3 — `ROLE_MODEL_DEFAULTS` bereinigen

**Datei:** `src/config/settings.py`

- `"ReportWriter"` Eintraege aus `ROLE_MODEL_DEFAULTS` und `STRUCTURED_MODEL_DEFAULTS` entfernen
- Oder als Kommentar belassen falls die Model-Config spaeter fuer eine echte Rendering-Komponente gebraucht wird

### Patch 4 — `tool_policy.py` bereinigen

**Datei:** `src/orchestration/tool_policy.py`

- `"ReportWriter": ()` entfernen — keine Tools, kein Agent

### Patch 5 — Beibehalten (keine Aenderung)

Folgende Stellen bleiben unveraendert:
- `AGENT_SPECS["ReportWriter"]` — UI-Metadaten, weiterhin benoetigt fuer Fortschrittsanzeige
- `PIPELINE_STEPS` — UI-Label
- `emit_message(agent="ReportWriter")` — Observability-Tag
- `MEMORY_ROLE_STATUS["ReportWriter"] = "excluded"` — bereits korrekt (F6)

### Patch 6 — Tests

**Datei:** `tests/`

- Pruefen ob bestehende Tests `ReportWriterAgent` oder `agents["report_writer"]` referenzieren
- Guard-Test: `test_report_writer_is_not_a_runtime_agent` — prueft dass kein `ReportWriterAgent` in `runtime_factory` instanziiert wird

---

## Design-Entscheidungen

### Warum nicht zum echten Agent machen?

Die Report-Erzeugung ist deterministisch und regelbasiert:
- `build_report_package()` assembliert Metadaten aus Pipeline-Daten
- `generate_pdf()` rendert ein Template

Dafuer braucht man keinen LLM-Agent, keinen Critic, keinen Judge. Ein Agent wuerde Komplexitaet hinzufuegen ohne Mehrwert.

### Warum den Namen behalten?

"ReportWriter" ist ein sinnvolles UI-Label fuer den letzten Pipeline-Schritt. Die Fortschrittsanzeige und das Observability-Log profitieren davon. Der Name muss nur nicht an eine Agent-Klasse gebunden sein.

### Warum `AGENT_SPECS` behalten?

`AGENT_SPECS` ist ein UI-Metadaten-Register, kein Runtime-Agent-Register. Es enthaelt Icons, Farben und Summaries fuer die Streamlit-Anzeige. "ReportWriter" dort zu behalten ist korrekt — es ist ein sichtbarer Pipeline-Schritt, nur kein Agent.

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Keine Stub-Rolle ohne echte Runtime-Funktion | `ReportWriterAgent` entfernt |
| Architekturdiagramm und Code stimmen ueberein | ReportWriter = Rendering-Komponente, kein Agent |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/agents/report_writer.py` | Datei entfernen |
| 2 | `src/agents/runtime_factory.py` | Import + Instanziierung entfernen |
| 3 | `src/config/settings.py` | Model-Defaults bereinigen |
| 4 | `src/orchestration/tool_policy.py` | Leere Tool-Liste entfernen |
| 5 | (keine Aenderung) | AGENT_SPECS, PIPELINE_STEPS, emit_message bleiben |
| 6 | `tests/` | Guard-Test |

**Reihenfolge:** 1 → 2 → 3 → 4 → 6 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 6 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 1** -- `src/agents/report_writer.py` entfernt
2. **Patch 2** -- `runtime_factory.py`: Import + `"report_writer": ReportWriterAgent()` entfernt
3. **Patch 3** -- `settings.py`: `"ReportWriter"` aus `ROLE_MODEL_DEFAULTS`, `ROLE_STRUCTURED_MODEL_DEFAULTS` und `summarize_runtime_models()` entfernt
4. **Patch 4** -- `tool_policy.py`: `"ReportWriter": ()` entfernt
5. **Patch 5** -- Beibehalten: `AGENT_SPECS`, `PIPELINE_STEPS`, `emit_message(agent="ReportWriter")`, `MEMORY_ROLE_STATUS`
6. **Patch 6** -- 2 Guard-Tests: `test_report_writer_is_not_a_runtime_agent`, `test_pipeline_runner_does_not_require_report_writer_agent`

### Validierungsergebnisse

```
$ pytest tests/ -> 218 passed in 31.85s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Keine Stub-Rolle ohne echte Runtime-Funktion | ReportWriterAgent entfernt |
| Architekturdiagramm und Code stimmen ueberein | ReportWriter = Rendering-Komponente, kein Agent |

### Review-Feedback integriert

| # | Feedback | Umsetzung |
|---|----------|-----------|
| 1 | AGENT_SPECS semantisch rahmen | Dokumentiert als Follow-up |
| 2 | emit_message agent → component | Dokumentiert als Follow-up |
| 3 | README/Architektur mitziehen | Dokumentiert als Follow-up |
| 4 | MEMORY_ROLE_STATUS spaeter ganz entfernen | Dokumentiert als Follow-up |
| 5 | Zweiter Guard-Test | test_pipeline_runner_does_not_require_report_writer_agent |

---

## Follow-up-Punkte (kein F9-Blocker)

### 1. AGENT_SPECS semantisch umbenennen oder rahmen

**Aktueller Zustand:** `AGENT_SPECS` enthaelt jetzt sowohl echte Runtime-Agenten als auch UI-Schritte ohne Agent-Runtime (ReportWriter).

**Ziel:** Entweder dokumentieren als "pipeline step / UI role registry" oder spaeter aufteilen in `RUNTIME_AGENT_SPECS` + `PIPELINE_STEP_SPECS`.

### 2. `emit_message(agent=...)` auf neutraleres Feld

**Aktueller Zustand:** `agent="ReportWriter"` in Observability-Events.

**Ziel:** Langfristig `component=` oder `step=` statt `agent=` fuer Nicht-Agent-Schritte.

### 3. README aktualisiert (nicht mehr Follow-up)

**Umgesetzt:** README.md angepasst:
- "Report Writer" → "Report rendering" (Synthesis Plane)
- "Report Writer produces" → "Report rendering produces" (Initial briefing)
- Key Files: `report_writer.py` entfernt, `specs.py` + `runtime_factory.py` + `synthesis.py` aktualisiert
- Akzeptanzkriterium "Architekturdiagramm und Code stimmen ueberein" ist damit fuer README erfuellt
- Drawio-Diagramm bleibt als separater Follow-up (binaeres Format, nicht in diesem Audit-Scope)

### 4. `MEMORY_ROLE_STATUS["ReportWriter"]` spaeter entfernen

**Aktueller Zustand:** `"excluded"` — korrekt fuer F6.

**Ziel:** Wenn ReportWriter definitiv kein Agent mehr ist, komplett aus rollenbezogenen Registern entfernen statt als excluded mitzuschleppen.
