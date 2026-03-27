# 2703_1023 Audit TODO — finale umsetzungsreife Fassung

**Bezug:** `2703_1023-audit.md`, Run-Analyse, Review der ueberarbeiteten TODO  
**Zweck:** Verbleibende Architekturdefekte und Haertungen in eine saubere, umsetzbare Patch-Reihenfolge ueberfuehren  
**Prinzip:** Ein Ticket = ein klarer technischer Zweck. Keine doppelten Root-Causes. Keine stillen Shape- oder Contract-Annahmen.

---

## Leitplanken fuer die Umsetzung

1. **Shape zuerst, Consumer danach.** Keine Consumer-Reparatur vor Festlegung des kanonischen Datenmodells.
2. **Eine Wahrheit pro Begriff.** Derselbe Name darf nicht unterschiedliche Shapes tragen.
3. **Compat bewusst, nicht versehentlich.** Test-Fixtures, Artefaktleser und Debug-Utilities muessen aktiv migriert oder ueber Adapter abgefedert werden.
4. **Guard vor Komfort.** Bei Contract-/Payload-Risiken zuerst Verlust erkennen, erst danach ueber Merge-Strategien nachdenken.
5. **Config vor Hardcode.** Invarianten wie Phasenordnung oder erlaubte Dependencies moeglichst aus Konfiguration statt aus impliziter Logik ableiten.

---

## Statusuebersicht

| ID | Thema | Severity | Prioritaet | Status |
|---|---|---:|---:|---|
| P0-1 | Kanonisches Datenmodell fuer Department-Ergebnisse festlegen | kritisch | P0 | Offen |
| P0-2 | Consumer auf kanonische Shape migrieren | kritisch | P0 | Offen |
| P0-3 | Follow-up-Writeback und Admission-Konsum konsistent machen | hoch | P0 | Offen |
| P0-4 | Envelope-Regressionstests und Fixture-Migration | hoch | P0 | Offen |
| P0-5 | Kompatibilitaet fuer Artefaktleser / Debug-Pfade absichern | mittel-hoch | P0 | Offen |
| P1-1 | `needs_contract_review` autoritativ verdrahten | mittel | P1 | Offen |
| P1-2 | Synthesis-Rollen in Model-Defaults vervollstaendigen | mittel | P1 | Offen |
| P1-3 | `input_artifacts` entscheiden und explizites Task-Input-Modell einziehen | mittel | P1 | Offen |
| P1-4 | `current_payload` gegen stillen Datenverlust haerten | mittel | P1 | Offen |
| P1-5 | Preflight in Core-Check vs. Runtime-Readiness trennen | niedrig-mittel | P1 | Offen |
| P2-1 | `CrossDomainStrategicAnalyst` vollstaendig entfernen | niedrig-mittel | P2 | Offen |
| P2-2 | Blocked-Artifact als Modell formalisieren | niedrig | P2 | Offen |
| P2-3 | DAG-/Phase-Invarianten config-getrieben pruefen | niedrig | P2 | Offen |
| P2-4 | Synthesis-Agent-Output und persistiertes Schema angleichen | niedrig | P2 | Offen |
| P2-5 | `_synthesis_admission` nach P0 neu bewerten und ggf. entfernen | niedrig | P2 | Offen |
| P2-6 | Sammel-Haertungen (Typing, CI, Dedup, Semantik) | niedrig | P2 | Offen |

---

## P0-1 — Kanonisches Datenmodell fuer Department-Ergebnisse festlegen

**Severity:** kritisch  
**Prioritaet:** P0

### Finding

Der Begriff `department_packages` ist aktuell semantisch ueberladen. Je nach Kontext bezeichnet er entweder:

- ein **Admission-Envelope** mit Metadaten (`admission`, `raw_package`, `admitted_payload`), oder
- ein **raw department package** ohne Wrapper.

Dadurch entstehen Shape-Drift, implizite Annahmen und Consumer, die vom falschen Format ausgehen.

### Zielbild

Es gibt zwei klar getrennte Begriffe:

- `admission_envelopes`: Supervisor-/Admission-Ergebnis mit Admission-Metadaten
- `raw_department_packages`: fachliche Department-Ergebnisse ohne Admission-Wrapper

### Patch-Sequenz

1. **Kanonische Terminologie festlegen** und in Code, Tests und Doku durchziehen.
2. `supervisor_loop.py`: Rueckgabemodell und lokale Variablen auf `admission_envelopes` umstellen.
3. `pipeline_runner.py`: beide Collections explizit fuehren statt einen ueberladenen Namen weiterzureichen.
4. Kleine Typ-/Schema-Helfer definieren, damit Envelope vs. Raw bereits an Funktionsgrenzen lesbar ist.
5. Alle Funktionssignaturen, die heute `department_packages` konsumieren, auf die neue Terminologie umstellen.

### Akzeptanzkriterien

- Kein produktiver Pfad verwendet denselben Namen fuer unterschiedliche Shapes.
- Alle zentralen Consumer deklarieren explizit, ob sie `admission_envelopes` oder `raw_department_packages` erwarten.
- Die Benennung ist in Runtime, Tests und Doku konsistent.

---

## P0-2 — Consumer auf kanonische Shape migrieren

**Severity:** kritisch  
**Prioritaet:** P0

### Finding

Mehrere Consumer lesen aktuell Raw-Felder direkt aus Envelope-Objekten. Das betrifft insbesondere Synthesis sowie nachgelagerte Report-Bausteine.

### Betroffene Pfade

- `synthesis_department.py`
- `src/orchestration/synthesis.py` / `build_report_package()`
- `pipeline_runner.py` an den Stellen, an denen Admission-Status oder Department-Payloads ausgelesen werden

### Patch-Sequenz

1. **Zentralen Shape-Resolver einfuehren**, z. B.:
   - `resolve_raw_department_package(pkg)`
   - `resolve_admitted_payload(pkg)`
   - `resolve_admission(pkg)`
2. `synthesis_department.py`: alle direkten Zugriffe auf `package.get("report_segment")`, `confidence`, `visual_focus` etc. auf Resolver umstellen.
3. `build_report_package()`: `visual_focus` und andere Department-Felder nur noch ueber Resolver lesen.
4. `pipeline_runner.py`: Admission-Entscheidungen nicht aus impliziten Marker-Feldern oder rohen Dict-Annahmen ableiten, sondern aus dem kanonischen Envelope-Zugriff.
5. Keine verteilte `pkg.get("raw_package", pkg)`-Logik an vielen Stellen hinterlassen; stattdessen zentrale Helper nutzen.

### Akzeptanzkriterien

- Kein produktiver Consumer liest Envelope und Raw unspezifisch gemischt.
- Alle relevanten Department-Felder werden aus dem korrekten Layer gelesen.
- Ein einzelner Resolver bildet die Kompatibilitaetsgrenze fuer Envelope/Raw.

---

## P0-3 — Follow-up-Writeback und Admission-Konsum konsistent machen

**Severity:** hoch  
**Prioritaet:** P0

### Finding

Im Synthesis-Follow-up-Pfad werden Updates teilweise direkt auf das Envelope-Root geschrieben. Dadurch entstehen gemischte Strukturen, bei denen Envelope-Metadaten und fachliche Payload-Felder auf derselben Ebene landen.

Zusaetzlich existiert mit `_synthesis_admission` mindestens ein Marker-Pfad, der parallel zur Envelope-Semantik laeuft.

### Patch-Sequenz

1. `request_department_followup()`: Follow-up-Resultate ausschliesslich in `raw_package` oder in einem bewusst definierten Nachfolgeobjekt aktualisieren.
2. Sicherstellen, dass Admission-Metadaten und fachliche Payload strukturell getrennt bleiben.
3. `pipeline_runner.py`: Admission-Konsum auf den kanonischen Envelope-Zugriff umstellen.
4. `_synthesis_admission` nicht sofort separat bereinigen, sondern nach der Umstellung nur noch als temporaren Kompatibilitaetsmarker behandeln.

### Akzeptanzkriterien

- Follow-up-Updates verschmieren die Envelope-Struktur nicht.
- Admission wird ueber den kanonischen Zugriff gelesen.
- Es entsteht kein Zustand, in dem Root und `raw_package` widerspruechliche fachliche Felder tragen.

---

## P0-4 — Envelope-Regressionstests und Fixture-Migration

**Severity:** hoch  
**Prioritaet:** P0

### Finding

Bestehende Tests und Fixtures bauen zentrale Synthesis-/Runtime-Szenarien teilweise noch im Legacy-/Raw-Format auf. Dadurch bleibt der reale Envelope-Bug unentdeckt.

### Patch-Sequenz

1. Alle relevanten Synthesis- und Runtime-Tests identifizieren, die heute Raw-Packages direkt einspeisen.
2. Fixtures auf die neue kanonische Shape migrieren.
3. Regressionstests ergaenzen fuer:
   - Lesen von `report_segment` aus Envelope
   - Lesen von `visual_focus` aus Envelope
   - korrekte Segmentzaehlung / Confidence-Ermittlung
   - Follow-up-Writeback ohne Shape-Verschmierung
4. Negativtests ergaenzen: Falsche Shape muss frueh und lesbar fehlschlagen.

### Akzeptanzkriterien

- Reale Runtime-Shapes sind in den Tests abgebildet.
- Ein Envelope/Raw-Mismatch fuehrt zu einem testbaren Fehler.
- Keine kritische Synthesis-Strecke ist nur noch ueber Legacy-Fixtures abgedeckt.

---

## P0-5 — Kompatibilitaet fuer Artefaktleser / Debug-Pfade absichern

**Severity:** mittel-hoch  
**Prioritaet:** P0

### Finding

Eine Shape-Umstellung betrifft nicht nur Runtime-Code, sondern sehr wahrscheinlich auch:

- serialisierte Run-Artefakte
- Debug-/Inspektionsskripte
- Hilfsfunktionen fuer Snapshot-/Report-Lesen
- eventuell manuelle Analysepfade

Wenn diese Pfade still auf Alt-Shape bleiben, entsteht Friktion trotz korrekter Runtime-Reparatur.

### Patch-Sequenz

1. Alle Artefaktleser und Debug-Helfer auf Shape-Annahmen pruefen.
2. Falls noetig, einen **kleinen Kompatibilitaetsadapter** einfuehren, der Altartefakte lesbar haelt, ohne neue produktive Schreibpfade auf Legacy-Shape zu lassen.
3. Klar dokumentieren, welche Shapes ab welchem Patchstand geschrieben bzw. nur noch gelesen werden.
4. Optional: Migrationsskript fuer Test-Fixtures oder Beispielartefakte.

### Akzeptanzkriterien

- Wichtige Analyse-/Debug-Pfade brechen nach P0 nicht unerwartet.
- Legacy-Lesepfade sind explizit und lokal begrenzt.
- Neue Writes erzeugen nur noch kanonische Shape.

---

## P1-1 — `needs_contract_review` autoritativ verdrahten

**Severity:** mittel  
**Prioritaet:** P1

### Finding

`needs_contract_review` wird gesetzt, erzwingt aber noch keinen autoritativen Kontrollfluss. Ein Critic-Approval kann den Pfad aktuell zu frueh als akzeptiert markieren.

### Patch-Sequenz

1. `lead.py` / Review-Pfad: Nach Critic-Approval explizit auf `artifact.needs_contract_review` pruefen.
2. Wenn `True`: nicht direkt akzeptieren, sondern Judge-Eskalation erzwingen.
3. Tests fuer den Eskalationspfad ergaenzen.

### Akzeptanzkriterien

- `needs_contract_review=True` kann nicht still als accepted durchlaufen.
- Judge-Eskalation ist deterministisch testbar.

---

## P1-2 — Synthesis-Rollen in Model-Defaults vervollstaendigen

**Severity:** mittel  
**Prioritaet:** P1

### Finding

Die Synthesis-Rollen sind in den Model-Defaults nicht vollstaendig hinterlegt. Gemeint sind mindestens:

- `SynthesisLead`
- `SynthesisAnalyst`
- `SynthesisCritic`
- `SynthesisJudge`

### Patch-Sequenz

1. `ROLE_MODEL_DEFAULTS` und `ROLE_STRUCTURED_MODEL_DEFAULTS` vervollstaendigen.
2. Test: Jede Rolle in `AGENT_SPECS` muss in beiden Default-Mappings sauber aufloesbar sein.

### Akzeptanzkriterien

- Kein Agent-Spec bleibt ohne Model-Default.
- Synthesis-Rollen sind symmetrisch zu den anderen Runtime-Rollen modelliert.

---

## P1-3 — `input_artifacts` entscheiden und explizites Task-Input-Modell einziehen

**Severity:** mittel  
**Prioritaet:** P1

### Finding

`input_artifacts` existiert im Contract, ist aber operativ nicht autoritativ. Das Feld suggeriert Input-Disziplin, ohne sie technisch durchzusetzen.

### Ziel

Nicht nur entscheiden, ob das Feld bleibt oder verschwindet, sondern ein **explizites Input-Modell pro Task** schaffen.

### Patch-Sequenz

**Option A — Feld bleibt und wird wirksam:**
1. Pro Task einen expliziten Input-Container definieren:
   - deklarierte fachliche Inputs
   - benoetigte Metadaten
   - minimaler Laufkontext
2. Worker erhalten nicht den gesamten Section-State, sondern den expliziten Task-Input.
3. `input_artifacts` wird validiert und zur Laufzeit erzwungen.

**Option B — Feld entfällt:**
1. `input_artifacts` aus Use-Case-/Assignment-Contracts entfernen.
2. Signaturen und Tests bereinigen.
3. In Doku klar festhalten, dass Inputs anderweitig modelliert werden.

### Akzeptanzkriterien

- Kein Contract-Feld suggeriert Verbindlichkeit ohne technische Wirkung.
- Falls das Feld bleibt, ist die Input-Disziplin zur Laufzeit sichtbar und testbar.

---

## P1-4 — `current_payload` gegen stillen Datenverlust haerten

**Severity:** mittel  
**Prioritaet:** P1

### Finding

`current_payload` wird nach Worker-Runs ersetzt. Solange Worker vollstaendig zurueckliefern, funktioniert das. Bei regressiven oder unvollstaendigen Rueckgaben droht stiller Datenverlust.

### Patch-Sequenz

1. Vor Payload-Ersatz einen **Verlust-Guard** einziehen:
   - mindestens Vergleich relevanter vorhandener Felder
   - bei Verlust Warnung oder Fehler statt stiller Ueberschreibung
2. Erst danach entscheiden, ob zusaetzlich eine Merge-Strategie benoetigt wird.
3. `deep_merge` nur dann einfuehren, wenn fachlich sauber begruendet; nicht als pauschaler Problemverstecker.
4. Regressionstest fuer Feldverlust auf spaeteren Task-Runs.

### Akzeptanzkriterien

- Ein spaeterer Task kann frueher gesetzte Felder nicht still verlieren.
- Datenverlust ist sichtbar und testbar.

---

## P1-5 — Preflight in Core-Check vs. Runtime-Readiness trennen

**Severity:** niedrig-mittel  
**Prioritaet:** P1

### Finding

Das aktuelle Preflight-Verhalten vermischt einen leichten Architektur-/Core-Check mit einem echten Runtime-Readiness-Check.

### Patch-Sequenz

1. Zwei Modi oder Stufen definieren:
   - **Core-Check:** Packages, `.env`, API-Key, pure Imports, strukturale Basispruefungen
   - **Runtime-Readiness:** AG2/AutoGen importierbar, Streamlit-/Runtime-nahe Imports, volle Laufumgebung
2. CLI und Fehlermeldungen so gestalten, dass klar ist, welcher Modus fehlgeschlagen ist.
3. Dokumentation und Smoke-Tests anpassen.

### Akzeptanzkriterien

- Ein leichter Core-Check ist ohne volle Runtime-Installation moeglich.
- Ein voller Readiness-Check prueft bewusst die komplette Runtime.

---

## P2-1 — `CrossDomainStrategicAnalyst` vollstaendig entfernen

**Severity:** niedrig-mittel  
**Prioritaet:** P2

### Finding

Die Rolle ist nicht nur Altlast im Code, sondern erzeugt semantische Drift ueber Defaults, Tool-Policy, Memory-Registry und Summary-/Config-Pfade.

### Patch-Sequenz

1. Alle Referenzen in Defaults, Tool-Policy, Memory-Konfiguration und Summary-Ausgaben entfernen.
2. Guard-Test einziehen, der verbleibende Referenzen findet.

### Akzeptanzkriterien

- Keine produktive Referenz auf `CrossDomainStrategicAnalyst` mehr im Codebestand.

---

## P2-2 — Blocked-Artifact als Modell formalisieren

**Severity:** niedrig  
**Prioritaet:** P2

### Patch-Sequenz

1. Pydantic-Modell fuer Blocked-Artifact definieren.
2. Supervisor-/Pipeline-Pfade auf das Modell heben.
3. Canonical-Schema-Test ergaenzen.

### Akzeptanzkriterien

- Blocked-Artefakte haben eine explizite, testbare Struktur.

---

## P2-3 — DAG-/Phase-Invarianten config-getrieben pruefen

**Severity:** niedrig  
**Prioritaet:** P2

### Finding

Phase- und Department-Abhaengigkeiten sollten nicht als implizites Wissen im Test oder in zufaelligen Helfern stecken.

### Patch-Sequenz

1. Invarianten aus Konfiguration oder explizitem Mapping ableiten.
2. Linter-/Smoke-Test gegen diese Invarianten laufen lassen.
3. Nur dort hardcoden, wo es bewusst ein dauerhaftes Business-Gesetz ist.

### Akzeptanzkriterien

- Phase-/Dependency-Regeln sind nachvollziehbar, testbar und nicht ueber implizite Reihenfolgen verteilt.

---

## P2-4 — Synthesis-Agent-Output und persistiertes Schema angleichen

**Severity:** niedrig  
**Prioritaet:** P2

### Finding

Synthesis produziert Felder, die das persistierte Schema nicht traegt. Pydantic verwirft sie still. Damit weicht das Arbeitsmodell der Agents vom Systemmodell ab.

### Patch-Sequenz

1. Entscheiden: Schema erweitern **oder** Agent-Output verschlanken.
2. Keine stillen Extras in der finalen Persistenz.
3. Test einfuehren, der Agent-Output gegen das finale Synthesis-Schema prueft.

### Akzeptanzkriterien

- Persistierter Output entspricht dem beabsichtigten Schema.
- Keine relevanten Synthesis-Felder gehen still verloren.

---

## P2-5 — `_synthesis_admission` nach P0 neu bewerten und ggf. entfernen

**Severity:** niedrig  
**Prioritaet:** P2

### Finding

Der Marker ist sehr wahrscheinlich nur ein Kompatibilitaetsrest. Vor P0 waere eine isolierte Bereinigung riskant, nach P0 ist sie sauber neu beurteilbar.

### Patch-Sequenz

1. Erst nach Abschluss von P0-1 bis P0-3 pruefen, ob der Marker noch irgendeinen produktiven Zweck erfuellt.
2. Wenn nein: Marker-Injection und Marker-Konsum entfernen.
3. Falls noch benoetigt: explizit als temporaeren Compat-Pfad dokumentieren.

### Akzeptanzkriterien

- Der Marker existiert nicht mehr ohne nachweisbaren Zweck.
- Kein produktiver Admission-Pfad haengt an impliziten Legacy-Markern.

---

## P2-6 — Sammel-Haertungen

**Severity:** niedrig  
**Prioritaet:** P2

### Einzelpunkte

- kanonische Dedup-Keys pro Sammlung und klarere Merge-Policy
- striktere Typisierung (`StrEnum`, mypy/pyright)
- CI-Haertung
- semantische Rahmung von `AGENT_SPECS`
- Doku-/Diagramm-Refresh
- verbleibende Shims/Altpfade bereinigen

---

## Bearbeitungsreihenfolge

### Phase 1 — P0 (Shape und Runtime-Konsistenz)
1. P0-1 — kanonisches Datenmodell festlegen
2. P0-2 — Consumer migrieren
3. P0-3 — Follow-up-Writeback / Admission-Konsum konsistent machen
4. P0-4 — Regressionstests und Fixture-Migration
5. P0-5 — Kompatibilitaet fuer Artefaktleser / Debug-Pfade absichern

### Phase 2 — P1 (Contract- und Runtime-Haertung)
6. P1-1 — `needs_contract_review` verdrahten
7. P1-2 — Synthesis-Rollen vervollstaendigen
8. P1-3 — `input_artifacts` + Task-Input-Modell entscheiden
9. P1-4 — `current_payload` Verlust-Guard
10. P1-5 — Preflight trennen

### Phase 3 — P2 (Bereinigung und Governance)
11. P2-1 — Geisterrolle entfernen
12. P2-2 — Blocked-Artifact modellieren
13. P2-3 — DAG-/Phase-Invarianten pruefen
14. P2-4 — Synthesis-Schema angleichen
15. P2-5 — `_synthesis_admission` neu bewerten / entfernen
16. P2-6 — Sammel-Haertungen

---

## Definition of Done fuer diese TODO-Datei

Diese TODO ist erst dann abgearbeitet, wenn:

- der Root-Cause `department_packages` / Envelope-vs.-Raw nachhaltig beseitigt ist,
- die produktive Runtime nicht mehr auf impliziten Shape-Annahmen basiert,
- Tests die reale Runtime-Shape abbilden,
- Compat-Pfade explizit begrenzt sind,
- und kein Contract-Feld oder Marker mehr Verbindlichkeit nur vortaeuscht.
