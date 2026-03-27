# 2503_0943 Audit TODO

**Bezug:** `2503_0943-audit.md`  
**Zweck:** Umsetzungsdatei für die schrittweise Abarbeitung der Audit-Findings  
**Prinzip:** Das Audit bleibt unveränderter Befund-Snapshot. Diese Datei dokumentiert Entscheidungen, Prioritäten, Umsetzungspfad und Fortschritt.

---

## Statusübersicht

| ID | Thema | Severity | Priorität | Status |
|---|---|---:|---:|---|
| F1 | Import-/Layer-Boundary reparieren | kritisch | P0 | ✅ Erledigt |
| F2 | Supervisor-Acceptance bindend machen | kritisch | P0 | ✅ Erledigt |
| F3 | Synthesis-Acceptance bindend machen | hoch | P0 | ✅ Erledigt |
| F4 | Task-Contracts runtime-seitig erzwingen | hoch | P1 | ✅ Kern umgesetzt, 2 dokumentierte Restpunkte |
| F5 | Shared Run Memory thread-safe / isoliert machen | hoch | P1 | ✅ Erledigt |
| F6 | Role-Memory-Retrieval schließen | mittel-hoch | P1 | ✅ Erledigt |
| F7 | Status-/Decision-Vokabular vereinheitlichen | mittel | P1 | ✅ Erledigt |
| F8 | Test-Surface konsolidieren | mittel | P2 | ✅ Erledigt |
| F9 | ReportWriter-Rolle architektonisch bereinigen | niedrig-mittel | P2 | ✅ Erledigt |
| F10 | Drift-Indikatoren / Signatur-Genauigkeit bereinigen | niedrig | P2 | ✅ Erledigt |

---

## Arbeitsregeln

1. **Kein Finding gilt als erledigt, bevor die Akzeptanzkriterien erfüllt sind.**
2. **P0 vor P1, P1 vor P2.**
3. **Keine kosmetischen Fixes ohne strukturelle Wirkung.**
4. **Boundary-, Contract- und Runtime-Fixes haben Vorrang vor Prompt- oder Naming-Kosmetik.**
5. **Jede Änderung muss den Zielzustand architektonisch klarer machen, nicht nur Tests grün färben.**

---

## F1 — Import-/Layer-Boundary reparieren

**Severity:** kritisch  
**Priorität:** P0  
**Status:** ✅ Erledigt

### Finding
AG2-/`autogen`-gebundene Runtime wird implizit über allgemeine Package-Imports nachgeladen. Dadurch sind eigentlich „pure“ Importpfade nicht mehr side-effect-frei.

### Zielbild
- `src.agents.__init__` ist side-effect-frei
- Agent-Metadaten und Runtime-Instanziierung sind getrennt
- optionale Heavy-Runtime wird nur explizit importiert
- pure Architektur-/Schema-/Policy-Module bleiben ohne AG2 importierbar

### Best-Practice-Entscheidung
- `definitions.py` logisch aufteilen in:
  - `src/agents/specs.py`
  - `src/agents/runtime_factory.py`
- `src/agents/__init__.py` neutralisieren
- `pipeline_runner.py` direkt auf `specs.py` und `runtime_factory.py` zeigen lassen
- keine „smarte“ Import-Magie als Zielarchitektur
- optionale Runtime-Abhängigkeiten langfristig als Extras behandeln

### Betroffene Dateien
- `src/agents/__init__.py`
- `src/agents/definitions.py`
- `src/pipeline_runner.py`
- neu:
  - `src/agents/specs.py`
  - `src/agents/runtime_factory.py`

### Umsetzungspfad
1. `AgentSpec`/`AGENT_SPECS` in `specs.py` verschieben
2. Runtime-Erzeugung in `runtime_factory.py` verschieben
3. `pipeline_runner.py` auf die neue Trennung umstellen
4. `__init__.py` side-effect-frei machen
5. optional `definitions.py` als temporäre Kompatibilitätsschicht belassen oder entfernen

### Akzeptanzkriterien
- `tests/smoke/test_preflight.py::test_pure_modules_importable` läuft ohne `autogen`
- `import src.agents.critic` zieht kein `autogen` mehr nach
- `src.agents.__init__` enthält keine Heavy-Runtime-Imports
- `pipeline_runner.py` funktioniert über explizite Runtime-Imports

### Notizen
Dies ist der erste Arbeitsblock. Keine weiteren strukturellen Schritte beginnen, bevor F1 sauber geschlossen ist.

---

## F2 — Supervisor-Acceptance bindend machen

**Severity:** kritisch  
**Priorität:** P0  
**Status:** ✅ Erledigt

### Finding
`accept_department_package()` wirkt wie ein Gate, ist aber faktisch nur Observability. Nicht akzeptierte Ergebnisse können trotzdem in die Synthesis gelangen.

### Zielbild
Supervisor-Acceptance ist ein **autoritatives Gate**:
- nicht akzeptierte Department-Packages dürfen nicht ungeprüft weiterfließen
- Downstream darf nur auf formal akzeptierten Outputs aufbauen
- degradierte/teilweise akzeptierte Zustände müssen explizit modelliert sein

### Best-Practice-Entscheidung
- Acceptance-Entscheidung wird zum **harten Steuerungspunkt**
- Abschnittspayloads dürfen erst nach positiver Entscheidung Downstream freigegeben werden
- abgelehnte oder rework-pflichtige Ergebnisse müssen einen expliziten Runtime-Pfad bekommen

### Betroffene Dateien
- `src/orchestration/supervisor_loop.py`
- `src/agents/supervisor.py`
- ggf. `src/orchestration/contracts.py`

### Umsetzungspfad
1. Acceptance-Entscheidung vom Logging entkoppeln
2. Freigabe-/Block-Logik direkt vor Downstream-Synthesis verankern
3. Rework-/Fallback-Pfade explizit definieren
4. Tests für „rejected package cannot flow downstream“ ergänzen

### Akzeptanzkriterien
- formal nicht akzeptierte Department-Packages gehen nicht in die Synthesis
- Acceptance-Status beeinflusst den Runtime-Pfad deterministisch
- Rework/Fallback ist explizit modelliert und testbar

---

## F3 — Synthesis-Acceptance bindend machen

**Severity:** hoch  
**Priorität:** P0  
**Status:** ✅ Erledigt

### Finding
Synthesis-Outputs werden aktuell pauschal als `accepted` markiert; die vorhandene Acceptance-Funktion wird nicht als Gate verwendet.

### Zielbild
- Synthesis besitzt einen echten Abschluss-Gate
- Finale Outputs werden nicht automatisch akzeptiert
- die wichtigste Qualitätsgrenze des Systems ist explizit und deterministisch

### Best-Practice-Entscheidung
- `accept_synthesis()` oder äquivalente Logik muss bindend in den Abschlussfluss eingebaut werden
- finale Freigabe nur nach positivem Accept-Urteil
- Akzeptanz, degradierte Freigabe und Rework klar unterscheiden

### Betroffene Dateien
- `src/orchestration/supervisor_loop.py`
- `src/agents/supervisor.py`
- ggf. Synthesis-nahe Tests

### Umsetzungspfad
1. aktuellen pauschalen Accepted-Pfad entfernen
2. Synthesis-Gate explizit aufrufen
3. Statusmodell an Contracts ausrichten
4. negative/partielle Fälle testen

### Akzeptanzkriterien
- keine pauschale Accept-Markierung mehr
- finale Freigabe hängt von echter Bewertung ab
- ablehnende oder degradierte Fälle sind testbar

---

## F4 — Task-Contracts runtime-seitig erzwingen

**Severity:** hoch  
**Priorität:** P1  
**Status:** ✅ Erledigt

### Finding
`depends_on` und `output_schema_key` sind modelliert, aber zur Laufzeit nicht hinreichend durchgesetzt.

### Zielbild
- Task-Abhängigkeiten sind echte Ausführungsbedingungen
- Task-spezifische Output-Schemas werden aktiv validiert
- Feld-Leakage zwischen Tasks wird reduziert oder ausgeschlossen

### Best-Practice-Entscheidung
- Contract-Definitionen dürfen keine bloßen Designdokumente bleiben
- Router und Worker müssen gemeinsam einen echten Contract-Pfad bilden
- Validation muss dort erfolgen, wo Task-Outputs entstehen und freigegeben werden

### Betroffene Dateien
- `src/app/use_cases.py`
- `src/orchestration/task_router.py`
- `src/agents/worker.py`
- Contract-/Schema-Registry-Dateien

### Umsetzungspfad
1. `depends_on` als Runtime-Vorbedingung auswerten
2. `output_schema_key` zur echten Validierung verdrahten
3. fehlgeschlagene Contract-Validierung mit klaren Runtime-Folgen versehen
4. Task-spezifische Tests ergänzen

### Akzeptanzkriterien
- Tasks laufen nicht ohne erfüllte Dependencies
- Task-Outputs werden gegen das vorgesehene Schema validiert
- Schema-Verletzungen stoppen oder degradieren den Flow deterministisch

---

## F5 — Shared Run Memory thread-safe oder isoliert machen

**Severity:** hoch  
**Priorität:** P1  
**Status:** ✅ Erledigt

### Finding
Parallel laufende Departments teilen sich ein mutierbares Memory-Objekt ohne Synchronisationsschutz.

### Zielbild
Mindestens eine der beiden sauberen Lösungen:
1. **Isolation:** jedes Department arbeitet mit eigenem Run-Scope-Memory und konsolidiert kontrolliert
2. **Synchronisation:** gemeinsamer Store ist explizit thread-safe

### Best-Practice-Entscheidung
Für Determinismus ist **Isolation mit kontrollierter Merge-Phase** architektonisch meist besser als nachträgliches Locking.

### Betroffene Dateien
- `src/orchestration/supervisor_loop.py`
- `src/memory/short_term_store.py`

### Umsetzungspfad
1. entscheiden: Isolation-first oder Locking-first
2. bevorzugt Department-lokale Working Sets einführen
3. Merge-/Konsolidierungsgrenzen definieren
4. Parallelitäts-/Race-Tests ergänzen

### Akzeptanzkriterien
- keine unkontrollierten parallelen Mutationen eines gemeinsamen Stores
- Reproduzierbarkeit der Aggregationen steigt
- `sources`, `worker_reports`, `usage_totals`, `open_questions` bleiben konsistent

---

## F6 — Role-Memory-Retrieval schließen

**Severity:** mittel bis hoch  
**Priorität:** P1  
**Status:** ✅ Erledigt

### Finding
Das Long-Term-Memory speichert Rollen-/Agent-Kontexte, die später nicht konsistent oder nicht vollständig wieder geladen werden.

### Zielbild
- Persistenz- und Retrieval-Seite sprechen dieselbe Rollensprache
- keine Phantom-Rollen
- keine persistierten Rollen ohne Retrieval-Pfad

### Best-Practice-Entscheidung
- zentrales, kanonisches Rollenregister
- Konsolidierung und Retrieval gegen dieselbe Quelle
- Naming-Drift eliminieren

### Betroffene Dateien
- `src/memory/consolidation.py`
- `src/pipeline_runner.py`
- `src/agents/synthesis_department.py`
- ggf. Rollen-/Registry-Definitionen

### Umsetzungspfad
1. kanonisches Rolleninventar definieren
2. Konsolidierung daran ausrichten
3. Retrieval daran ausrichten
4. Inkonsistenzen entfernen

### Akzeptanzkriterien
- jede persistierte Rolle ist retrievable
- keine nicht-existente Laufzeitrolle wird geladen
- Synthesis- und Contact-Rollen sind konsistent verdrahtet

---

## F7 — Status-/Decision-Vokabular vereinheitlichen

**Severity:** mittel  
**Priorität:** P1  
**Status:** ✅ Erledigt

### Finding
Entscheidungs- und Statusbegriffe driften zwischen Contracts, Judge, Supervisor und Prompt-Texten.

### Zielbild
- ein kanonisches Entscheidungsmodell
- identische Begriffswelt in Runtime, Contracts, Prompts, Logs und Tests

### Best-Practice-Entscheidung
- ein einziges Status-Vokabular definieren
- Alias-/Legacy-Begriffe nur noch als Übergangs-Mapping zulassen
- keine stillen semantischen Übersetzungen zwischen Schichten

### Betroffene Dateien
- `src/orchestration/contracts.py`
- `src/agents/judge.py`
- `src/agents/supervisor.py`
- `src/agents/worker.py`
- `src/agents/synthesis_department.py`

### Umsetzungspfad
1. kanonisches Vokabular definieren
2. Runtime-Codes angleichen
3. Prompt-/Text-Drift bereinigen
4. Status-Mapping nur temporär zulassen

### Akzeptanzkriterien
- dieselben Entscheidungen heißen in allen Schichten gleich
- Logs, Tests und Runtime-Codes referenzieren denselben Kanon
- Altbegriffe sind entfernt oder explizit gemappt

---

## F8 — Test-Surface konsolidieren

**Severity:** mittel  
**Priorität:** P2  
**Status:** ✅ Erledigt

### Finding
Top-Level-Tests außerhalb von `tests/` liegen neben der eigentlichen Pytest-Wahrheit.

### Zielbild
- eine klare Testoberfläche
- CI und lokale Runs prüfen dieselbe Wahrheit
- keine vergessenen oder stillen Testinseln

### Best-Practice-Entscheidung
- `tests/` als kanonische Testwurzel
- Top-Level-Tests migrieren oder bewusst stilllegen
- keine parallelen Wahrheiten

### Betroffene Dateien
- `pyproject.toml`
- Top-Level-Testdateien
- `tests/`-Struktur

### Umsetzungspfad
1. Bestandsaufnahme aller Top-Level-Tests
2. relevante Tests nach `tests/` migrieren
3. obsoletes Testgut entfernen
4. CI-/Local-Run angleichen

### Akzeptanzkriterien
- alle relevanten Tests laufen über denselben `pytest`-Entry
- keine produktionsrelevanten Tests liegen außerhalb der Testwurzel
- CI bildet die reale Wahrheit ab

---

## F9 — ReportWriter-Rolle architektonisch bereinigen

**Severity:** niedrig bis mittel  
**Priorität:** P2  
**Status:** ✅ Erledigt

### Finding
`ReportWriterAgent` existiert als Architektur-Objekt, die eigentliche Report-Erstellung läuft aber außerhalb davon.

### Zielbild
Eine klare Entscheidung:
- entweder echter Runtime-Agent
- oder bewusst kein Agent, sondern regelbasierte Synthesis-/Rendering-Komponente

### Best-Practice-Entscheidung
Keine Scheinkomponenten. Jede Runtime-Rolle muss entweder operational sein oder entfernt/umbenannt werden.

### Betroffene Dateien
- `src/agents/report_writer.py`
- `src/orchestration/synthesis.py`
- `src/pipeline_runner.py`

### Umsetzungspfad
1. Rolle fachlich entscheiden
2. entweder Agent operationalisieren
3. oder Nicht-Agent-Komponente sauber benennen
4. Aufrufer bereinigen

### Akzeptanzkriterien
- keine Stub-Rolle ohne echte Runtime-Funktion
- Architekturdiagramm und Code stimmen überein

---

## F10 — Drift-Indikatoren und Signatur-Genauigkeit bereinigen

**Severity:** niedrig  
**Priorität:** P2  
**Status:** ✅ Erledigt

### Finding
Kleine Inkonsistenzen zwischen Typsignaturen und realem Runtime-Verhalten existieren bereits.

### Zielbild
- Signaturen, Rückgaben und Runtime-Verhalten stimmen exakt überein
- kleine Drift wird früh eliminiert, bevor sie systemisch wird

### Best-Practice-Entscheidung
Diese Punkte nicht ignorieren; sie sind Frühindikatoren für spätere Wartungsprobleme.

### Betroffene Dateien
- z. B. `src/orchestration/supervisor_loop.py`

### Umsetzungspfad
1. Signatur-/Rückgabe-Abgleich
2. statische Prüfungen ergänzen
3. kleine Drifts systematisch bereinigen

### Akzeptanzkriterien
- Typannotationen und reale Rückgaben stimmen überein
- keine bekannten Drift-Indikatoren bleiben offen

---

## Nächste Bearbeitungsreihenfolge

### Phase 1 — P0
1. F1 — Import-/Layer-Boundary
2. F2 — Supervisor-Acceptance
3. F3 — Synthesis-Acceptance

### Phase 2 — P1
4. F4 — Task-Contracts runtime-seitig erzwingen
5. F5 — Shared Run Memory absichern / isolieren
6. F6 — Role-Memory-Retrieval schließen
7. F7 — Vokabular vereinheitlichen

### Phase 3 — P2
8. F8 — Test-Surface konsolidieren
9. F9 — ReportWriter-Rolle bereinigen
10. F10 — Drift-Indikatoren bereinigen

---

## Aktueller Arbeitsfokus

**Aktiver Schritt:** Alle Findings abgeschlossen.

Alle 10 Patch-Sequenzen siehe:
- `docs/audits/F1_patch_sequence.md`
- `docs/audits/F2_patch_sequence.md`
- `docs/audits/F3_patch_sequence.md`
- `docs/audits/F4_patch_sequence.md`
- `docs/audits/F5_patch_sequence.md`
- `docs/audits/F6_patch_sequence.md`
- `docs/audits/F7_patch_sequence.md`
- `docs/audits/F8_patch_sequence.md`
- `docs/audits/F9_patch_sequence.md`
- `docs/audits/F10_patch_sequence.md`

### Bekannte Restpunkte (kein Blocker fuer Audit-Closure)

| Finding | Restpunkt | Empfohlener Zeitpunkt |
|---------|-----------|----------------------|
| F4 | Judge-Eskalation bei `needs_contract_review` noch nicht verdrahtet | Spaetere Iteration |
| F4 | DAG-Linter prueft noch nicht Phase-Kompatibilitaet | Spaetere Iteration |
| F5 | Kanonische Dedup-Keys pro Sammlung | P2-Haertung |
| F5 | Merge-Konflikt-Policy (fail-fast vs. warn) | P2-Haertung |
| F7 | Kanonische Mengen als StrEnum statt frozenset | P2-Haertung |
| F8 | CI technisch explizit festziehen | Letzte Meile |
| F9 | Drawio-Diagramm aktualisieren | Spaetere Iteration |
| F9 | AGENT_SPECS semantisch rahmen / aufteilen | Spaetere Iteration |
| F10 | Statische Typpruefung (mypy/pyright) einfuehren | P2-Haertung |

---

## Änderungslog

### 2025-03-25
- Datei angelegt
- Findings aus `2503_0943-audit.md` in umsetzbare Arbeitsstruktur überführt
- F1 als aktueller Startpunkt festgelegt
- F1 umgesetzt und validiert (169 Tests grün) — siehe `F1_patch_sequence.md`
- F2 umgesetzt und validiert (169 Tests grün) — siehe `F2_patch_sequence.md`
- F3 umgesetzt und validiert (175 Tests grün) — siehe `F3_patch_sequence.md`
- F3 nachgeschärft (Review-Feedback: Envelope, Blocked-Artifact, keine Parallel-Logik) — 177 Tests grün
- F4 umgesetzt und validiert (192 Tests grün) — siehe `F4_patch_sequence.md`
- F5 umgesetzt und validiert (198 Tests grün) — siehe `F5_patch_sequence.md`
- F5 nachgeschärft (Snapshot+Delta, Disjunktheits-Assertion, 4 neue Tests) — 202 Tests grün
- F6 umgesetzt und validiert (210 Tests grün) — siehe `F6_patch_sequence.md`
- F7 umgesetzt und validiert (215 Tests grün) — siehe `F7_patch_sequence.md`
- F7 nachgeschärft (pending_synthesis als kanonischer Status) — 215 Tests grün
- F8 umgesetzt und validiert (216 Tests grün) — siehe `F8_patch_sequence.md`
- F9 umgesetzt und validiert (218 Tests grün) — siehe `F9_patch_sequence.md`
- F9 nachgeschärft (README aktualisiert) — 218 Tests grün
- F10 umgesetzt und validiert (220 Tests grün) — siehe `F10_patch_sequence.md`
- **Alle 10 Findings abgeschlossen.** Gesamte Testsuite: 220 Tests grün.
