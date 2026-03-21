# Liquisto Market Intelligence Pipeline

AG2/AutoGen-native multi-agent workflow for preparing Liquisto sales conversations from a company name and web domain.

Kompatibilitätsziel dieses Repos:
- AG2 `0.11.x`
- Python `3.10` bis `3.13`

## Zweck

Dieses Repository baut aus einem einfachen Intake
- `company_name`
- `web_domain`

ein strukturiertes Vertriebsbriefing für Liquisto.

Das Ziel ist nicht ein generischer Firmenreport, sondern ein belastbarer Research-Flow für die Frage:

`Ist dieses Unternehmen für Liquisto relevant, welche Evidenz gibt es dafür, und wie sieht der potenzielle Käufermarkt für überschüssige Bestände oder verwandte Vermarktungsszenarien aus?`

Am Ende sollen fünf fachliche Ergebnisblöcke vorliegen:
- `company_profile`
- `industry_analysis`
- `market_network`
- `quality_review`
- `synthesis`

## Was das System fachlich leistet

Die Pipeline zerlegt die Aufgabe in klar getrennte Agentenrollen:

1. `Concierge`
Prüft den Intake, validiert Domain und Sprache und erstellt einen kleinen Research-Brief.

2. `CompanyIntelligence`
Ermittelt das Firmenprofil: Rechtsform, Standort, Produkte, Personen, wirtschaftliche Signale.

3. `StrategicSignals`
Analysiert Branchenlage, Überkapazität, Nachfragesignale und überschussrelevante Marktdynamik.

4. `MarketNetwork`
Sucht potenzielle Käufer in vier Tiers:
- Peer Competitors
- Downstream Buyers
- Service Providers
- Cross-Industry Buyers

5. `EvidenceQA`
Bewertet die Qualität der Evidenz, identifiziert Lücken und markiert Schwachstellen.

6. `Synthesis`
Verdichtet alles zu einem vertrieblich nutzbaren Briefing mit transparenter Pro-/Contra-Sicht.

Zu jedem Producer gibt es einen zugeordneten Critic:
- `ConciergeCritic`
- `CompanyIntelligenceCritic`
- `StrategicSignalsCritic`
- `MarketNetworkCritic`
- `EvidenceQACritic`
- `SynthesisCritic`

## Wie das Repo mit AG2 umgesetzt ist

Dieses Repo ist auf AG2 ausgerichtet. Die Orchestrierung kommt nicht aus selbst gebauter Python-Speaker-Logik, sondern aus nativen AG2-Bausteinen.

Die zentrale Umsetzung liegt in [src/agents/definitions.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/agents/definitions.py):

- `ConversableAgent`
  Alle Rollen sind als AG2-Agents definiert.

- `response_format`
  Jeder fachliche Producer und jeder Critic arbeitet mit einem Pydantic-Schema als AG2-Structured-Output-Vertrag.

- `DefaultPattern`
  Der gesamte Workflow wird als AG2-Pattern aufgebaut.

- `handoffs`
  Agenten übergeben nativ an den nächsten Agenten oder an den zugehörigen Critic.

- `OnContextCondition`
  Kontextgesteuerte Übergänge steuern z. B. den Abschluss des Workflows.

- `FunctionTarget`
  Die Review-Schleifen zwischen Producer und Critic werden über eine AG2-Handoff-Funktion geroutet.

- `GroupToolExecutor`
  Tool-Calls laufen über den nativen AG2-Gruppenmechanismus, nicht über einen separaten eigenen Executor.

Das bedeutet konkret:
- Die Agenten treiben den Ablauf.
- Die Übergänge sind als AG2-Handoffs modelliert.
- Rework-Schleifen sind Teil der AG2-Orchestrierung.
- `Admin` ist als AG2-Agent der Workflow-Einstieg und -Abschluss.

## Orchestrierungslogik

Der Workflow läuft sequentiell über Producer/Critic-Paare:

- `Admin -> Concierge`
- `Concierge -> ConciergeCritic`
- bei `approved = false` zurück an `Concierge`
- bei `approved = true` weiter an `CompanyIntelligence`
- `CompanyIntelligence -> CompanyIntelligenceCritic`
- bei `approved = false` zurück an `CompanyIntelligence`
- bei `approved = true` weiter an `StrategicSignals`
- `StrategicSignals -> StrategicSignalsCritic`
- `MarketNetwork -> MarketNetworkCritic`
- `EvidenceQA -> EvidenceQACritic`
- `Synthesis -> SynthesisCritic`
- nach finaler Freigabe zurück an `Admin`

Die Review-Entscheidung wird dabei in [src/agents/definitions.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/agents/definitions.py) über `_route_stage_review(...)` umgesetzt.

Wichtig:
- Der Critic soll keine neuen Fakten erfinden.
- Bei schwacher Evidenz soll der Producer auf `n/v`, leere Listen oder konservative Aussagen zurückgehen.
- Eine leere, ehrliche Antwort ist besser als eine spekulative.

## Was AG2 übernimmt und was bewusst außerhalb von AG2 bleibt

### Innerhalb von AG2

- Agent-Definitionen
- Structured Outputs
- Handoffs
- Context-basierte Übergänge
- Tool-Ausführung
- Producer/Critic-Feedback-Loops

### Außerhalb von AG2

Ein kleiner Teil bleibt bewusst deterministisch im Python-Code:

- Start des Runs und Live-Monitoring in [src/pipeline_runner.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/pipeline_runner.py)
- ein schmaler Wrapper um `prepare_group_chat(...)`, damit die AG2-Rückgabestruktur nur an einer Stelle im Repo gekapselt ist
- Extraktion der finalen Artefakte aus der `chat_history`
- Pydantic-Validierung der extrahierten Ergebnisse
- Guardrails für Evidenzqualität und Käuferstärke
- Export nach JSON/PDF
- UI-State und Streamlit-Darstellung

Das ist absichtlich so getrennt:
- AG2 steuert die agentische Zusammenarbeit.
- Python übernimmt Export, UI und deterministische Nachverarbeitung.

## Schemata und Datenverträge

Die strukturierten Datenmodelle liegen in [src/models/schemas.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/models/schemas.py).

Wichtige Modelle:
- `ConciergeOutput`
- `CompanyProfile`
- `IndustryAnalysis`
- `MarketNetwork`
- `QualityReview`
- `SynthesisReport`
- `ReviewFeedback`

Diese Schemata sind der harte Vertrag zwischen:
- Producer-Agent
- Critic-Agent
- Pipeline-Parsing
- UI
- Exportern

Ohne schema-konformes Ergebnis gilt ein Abschnitt als nicht belastbar. Legacy- oder Alternativformate werden nicht in das erwartete Schema umgeschrieben.

## Recherche-Tools

Die Research-Tools liegen in [src/tools/research.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/tools/research.py).

Verfügbare Tool-Typen:
- `check_domain`
- `fetch_page`
- `web_search`
- `company_source_pack`
- `industry_source_pack`
- `buyer_source_pack`

Die Tools sind absichtlich stagespezifisch registriert:
- `Concierge`: nur Intake-nahe Tools
- `CompanyIntelligence`: Firmenquellen
- `StrategicSignals`: Branchenquellen
- `MarketNetwork`: Käufer- und Marktquellen

Dadurch sieht nicht jeder Agent den gesamten Werkzeugkasten. Das reduziert Streuverluste, Kosten und unnötige Suchschleifen.

## Kosten- und Budgetsteuerung

Das Repo erfasst Usage- und Kostendaten pro Run.

Gespeichert werden unter anderem:
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `total_cost`

Zusätzlich gibt es Budgetgrenzen:
- `PIPELINE_MAX_STAGE_ATTEMPTS`
- `PIPELINE_MAX_TOOL_CALLS`
- `PIPELINE_MAX_RUN_SECONDS`
- `LLM_MAX_TOKENS`

Standardmäßig gibt es keinen expliziten Dollar-Hardcap pro Run. Die in der UI angezeigten Kosten sind primär beobachtend; die eigentlichen Schutzgrenzen sind Attempts, Tool-Calls, Laufzeit und Modell-`max_tokens`.

Die Budgetdaten landen mit im Run-Meta-Export und werden in der UI angezeigt. Das Laufzeitbudget wird vom Runner überwacht; überschreitet ein Run die Grenze, wird der Workflow nach dem aktuellen AG2-Zug abgebrochen und als Fehler beendet.

## Projektstruktur

```text
src/
  agents/
    definitions.py      AG2-Agents, Handoffs, Pattern
  config/
    settings.py         LLM-Auswahl und Structured-Output-Modellwahl
  exporters/
    json_export.py      Artifact-Export
    pdf_report.py       PDF-Erzeugung
  models/
    schemas.py          Pydantic-Datenverträge
  tools/
    research.py         AG2-Research-Tools
  pipeline.py           CLI-Einstieg
  pipeline_runner.py    Run-Steuerung, Live-Monitoring, Parsing, Export
ui/
  app.py                Streamlit-Oberfläche
artifacts/
  runs/                 Persistierte Run-Artefakte
```

## Laufzeitfluss im Repo

1. [src/pipeline.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/pipeline.py) oder [ui/app.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/ui/app.py) ruft `run_pipeline(...)` auf.
2. [src/pipeline_runner.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/pipeline_runner.py) lädt das LLM-Setup aus [src/config/settings.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/config/settings.py).
3. Die Agents werden in [src/agents/definitions.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/agents/definitions.py) erstellt.
4. Das AG2-Pattern wird vorbereitet und gestartet.
5. Die Pipeline beobachtet nur noch den Chat-Verlauf und streamt neue Nachrichten an die UI.
6. Nach Abschluss werden die Outputs extrahiert, validiert, normalisiert und exportiert.
7. Artefakte landen in `artifacts/runs/<run_id>/`.

## Modelle

Die Modellwahl kommt aus [src/config/settings.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/config/settings.py).

Wichtig:
- `LLM_MODEL` ist das bevorzugte Modell.
- Für Structured Outputs wird bei Bedarf automatisch auf `STRUCTURED_LLM_MODEL` gewechselt.

Standardmäßig bedeutet das:
- freies bevorzugtes Modell: `gpt-4.1-mini`
- strukturiertes Fallback-Modell: `gpt-4.1-mini`

Das ist relevant, weil AG2-`response_format` nur mit Modellen funktioniert, die Structured Outputs sauber unterstützen.

## Ausführung

### Vorbereitung

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.lock
python3 preflight.py
```

Hinweise:
- `requirements.txt` enthält die unterstützten Versionsbereiche.
- `requirements.lock` pinnt die freigegebenen Top-Level-Runtime-Versionen für reproduzierbare lokale Setups.

In `.env` muss mindestens gesetzt sein:

```bash
OPENAI_API_KEY=...
```

### Start über Launcher

```bash
python3 launcher.py
```

### Direkt über Streamlit

```bash
python3 -m streamlit run ui/app.py
```

### Direkt über CLI

```bash
python3 -m src.pipeline
```

## Artefakte

Jeder Run exportiert nach `artifacts/runs/<run_id>/`.

Typische Inhalte:
- `chat_history.json`
- `pipeline_data.json`
- `run_meta.json`

Optional je nach Lauf:
- generierte PDF-Datei

Diese Artefakte sind die wichtigste Grundlage für:
- Debugging
- fachliche Review
- Kostenanalyse
- erneutes Laden des letzten Runs in der UI

## Aktueller technischer Stand

Architektonisch ist das Repo auf AG2-Handoffs und Structured Outputs umgestellt.

Das bedeutet:
- keine eigene Speaker-Selection-Logik mehr
- keine manuell verdrahteten Stage-Loops im Runner
- echte AG2-Tool-Ausführung
- echte Producer/Critic-Rework-Schleifen

Versions- und Laufzeitannahmen:
- das Repo ist auf AG2 `0.11.x` ausgerichtet
- [src/pipeline_runner.py](/Users/konstantinmac/Documents/repositories/multi-agent-group-chat/src/pipeline_runner.py) kapselt die dokumentierte `prepare_group_chat(...)`-Rückgabeform von AG2 `0.11.x` bewusst an genau einer Stelle
- wenn sich diese AG2-Rückgabeform ändert, soll der Runner früh und laut fehlschlagen statt stillschweigend falsche Zustände weiterzureichen

Offen bleibt weiter die fachliche Qualität einzelner Runs:
- öffentliche Quellen können dünn sein
- Websuche kann 403/Leerlauf liefern
- schwache Evidenz führt bewusst zu konservativen oder leeren Feldern

Das ist kein Widerspruch zur Architektur, sondern die beabsichtigte Konsequenz: lieber ehrliche Lücken als erfundene Sicherheit.
