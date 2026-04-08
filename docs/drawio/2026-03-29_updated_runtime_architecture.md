# Updated Runtime Architecture v2 — exakte Laufbeschreibung in verständlicher Sprache

Diese Datei erklärt den **wirklichen Lauf des Systems** so, dass Du die Datei
`docs/drawio/runtime_architecture.drawio` **Schritt für Schritt mitlesen** kannst.

Ziel dieser Beschreibung ist nicht nur Technik-Dokumentation, sondern echte Nachvollziehbarkeit:

- **was** passiert,
- **wann** es passiert,
- **wo** im Code es passiert,
- **wie** der Schritt arbeitet,
- **warum** dieser Schritt überhaupt existiert,
- und **welches Ergebnis** danach weitergegeben oder gespeichert wird.

Die Sprache ist bewusst so geschrieben, dass auch jemand ohne tiefen Python- oder AutoGen-Wissen den Ablauf verstehen kann.

---

## 1. Wie Du diese Datei zusammen mit der DRAWIO lesen solltest

Die DRAWIO ist in sechs große Abschnitte aufgeteilt:

1. **01 — Intake + Run Bootstrap**
2. **02 — Supervisor Backlog + Routing**
3. **03 — Department Execution**
4. **04 — Synthesis + Back-Requests**
5. **05 — Assembly + Export**
6. **06 — Existing Run Follow-up**

Diese Markdown-Datei folgt **genau derselben Reihenfolge**.

Praktisch bedeutet das:

- Wenn Du in der DRAWIO links oben startest, kannst Du diese Datei von oben nach unten lesen.
- Jeder größere Kasten in der DRAWIO hat hier einen passenden Erklärblock.
- Wenn im Diagramm ein Pfeil weitergeht, erklärt der nächste Abschnitt, **warum** dieser Pfeil jetzt genommen wird.

### 1.1 Update-Addendum (2026-04-02)

Seit dieser Fassung gilt zusätzlich:
- jedes Department hat eine eigene Knowledge Base:
  - `knowledge/sources/<department>.yaml` — Source-Metadaten: Prioritäten, Evidenztyp, Provenienzhinweise (keine Runtime-Queries)
  - `knowledge/policies/<department>.yaml` — Pflichtfelder, Mindest-Evidenz, Gate-Regeln
  - `knowledge/query_strategies/<department>.yaml` — Runtime-Query-Templates pro Task, kanonische `{placeholder}`-Syntax; einzige autoritative Quelle für Query-Konstruktion zur Laufzeit
- die Query-Auflösung erfolgt zentral über `src/research/query_resolver.py` (Placeholder-Expansion, Validierung, Buyer-Expansion)
- die GroupChat-Kommunikation bleibt frei (kein starres Skript)
- die Policy-Prüfung passiert erst bei Package-Abnahme/Finalisierung
- fehlende öffentlich auffindbare Kontakte werden explizit als `keine freien Quellen` markiert
- Readiness berücksichtigt Department-Policy-Gates zusätzlich zur bisherigen Mindestpaket-Logik

---

## 2. Das System in einem einfachen Gesamtbild

Bevor wir in die Details gehen, hier der gesamte Lauf in ganz einfacher Sprache:

1. Ein Nutzer gibt im UI Firma und Domain ein.
2. Das System startet einen neuen Lauf und vergibt dafür eine eindeutige `run_id`.
3. Es lädt frühere, dauerhaft gespeicherte Strategiemuster aus dem Long-Term-Memory.
4. Der Supervisor formuliert daraus einen Arbeitsauftrag.
5. Der Supervisor verteilt Standardaufgaben an die Fachbereiche.
6. Company und Market laufen zuerst parallel.
7. Buyer läuft danach.
8. Contact läuft nur dann sinnvoll weiter, wenn aus Buyer/Market genug verwertbare Firmenhinweise vorliegen.
9. Jedes Department arbeitet intern mit einem kleinen Agententeam: Lead, Researcher, Critic, Judge, Coding Assistant.
10. Jedes Department liefert am Ende ein offizielles Department-Paket zurück.
11. Der Supervisor entscheidet, ob dieses Paket downstream sichtbar ist, nur mit Lücken sichtbar ist oder verworfen wird.
12. Zusätzlich wird je Department ein Policy-Gate ausgewertet (Pflichtfelder, Mindest-Evidenz, Blocker).
13. Danach liest die Synthesis die freigegebenen Department-Ergebnisse und baut die Gesamtbewertung.
14. Anschließend baut die Pipeline daraus das finale `pipeline_data`-Objekt, das `report_package` und die Exportdateien.
15. Zum Schluss wird der komplette Lauf so gespeichert, dass man ihn später mit derselben `run_id` erneut laden und Folgefragen beantworten kann.

---

## 3. Die wichtigsten Laufobjekte in einfacher Sprache

Damit die späteren Schritte verständlich bleiben, hier die wichtigsten Datenbehälter.

### 3.1 `RunContext` — die Laufakte
**Datei:** `src/orchestration/run_context.py`

Der `RunContext` ist die **zentrale Akte des gesamten Laufs**.
Darin steht alles, was für genau diesen einen Run wichtig ist.

Er enthält unter anderem:

- `run_id` — die eindeutige Kennung des Laufs
- `intake` — was der Nutzer eingegeben hat
- `supervisor_brief` — die vom Supervisor formulierte Arbeitsanweisung
- `retrieved_strategies` — allgemeine geladene Langzeit-Strategien
- `retrieved_role_strategies` — rollenspezifische geladene Langzeit-Strategien
- `active_tasks` — alle registrierten Aufgaben
- `report_package` — das exportfreundliche Endergebnis
- `status` — z. B. `running`, `completed`, `failed`
- `short_term_memory` — das komplette Run-Gedächtnis

**Warum gibt es das?**
Weil das System sonst keinen sauberen Ort hätte, an dem der gesamte Fallzustand gesammelt liegt.

---

### 3.2 `ShortTermMemoryStore` — das Run-Gedächtnis
**Datei:** `src/memory/short_term_store.py`

Das `ShortTermMemoryStore` ist das **laufbezogene Arbeitsgedächtnis**.

Darin liegen nicht nur finale Ergebnisse, sondern auch Zwischenstände und Verlaufsspuren, zum Beispiel:

- `task_statuses`
- `worker_reports`
- `department_packages`
- `department_run_states`
- `department_conversations`
- `department_workspaces`
- `sources`
- `open_questions`
- `usage_totals`

**Einfach gesagt:**
Wenn der `RunContext` die Fallakte ist, dann ist `short_term_memory` die **detaillierte Ermittlungsmappe**.

**Warum ist das wichtig?**
Weil genau dieses Gedächtnis am Ende exportiert wird und später bei Follow-up-Fragen wieder geladen werden kann.

---

### 3.3 `sections` — die freigegebenen Abschnittsergebnisse
**Datei:** lokal in `src/orchestration/supervisor_loop.py`

`sections` ist das Objekt, in dem der Supervisor nur das speichert, was downstream sichtbar werden darf.

Typische Schlüssel sind:

- `company_profile`
- `industry_analysis`
- `market_network`
- `contact_intelligence`
- `synthesis`

**Wichtig:**
Hier landet **nicht** einfach alles, was ein Department intern produziert hat.
Hier landet nur das, was nach dem Supervisor-Gate tatsächlich weiterverwendet werden darf.

---

### 3.4 `department_packages` — die offiziellen Department-Ergebnisse
**Datei:** lokal in `src/orchestration/supervisor_loop.py`

Dieses Objekt speichert pro Department ein offizielles Ergebnis im Format eines **Admission Envelopes**.

Ein solcher Envelope enthält:

- `admission` — die Zulassungsentscheidung
- `raw_package` — das vollständige Department-Paket
- `admitted_payload` — der Teil, der downstream sichtbar ist

**Warum diese Trennung?**
Damit das System unterscheiden kann zwischen:

- dem vollständigen diagnostischen Department-Ergebnis
- und dem Teil, der im weiteren Lauf wirklich benutzt werden darf

---

## 4. Phase 01 — Intake + Run Bootstrap

Dieser Abschnitt entspricht in der DRAWIO dem Bereich **„01 — Intake + Run Bootstrap“**.

---

### 4.1 User enters run request
**Wo im Code:** `ui/app.py`

### Was passiert?
Der Nutzer gibt im Streamlit-Interface mindestens zwei Dinge ein:

- `company_name`
- `web_domain`

### Wie passiert das?
Die UI hält den Zustand in `st.session_state`.
Sobald der Nutzer den Start auslöst, wird der eigentliche Pipeline-Lauf angestoßen.

### Warum gibt es diesen Schritt?
Damit der Lauf einen klaren und reproduzierbaren Startpunkt hat.
Ohne definierte Eingabe gäbe es keinen sauberen Fallkontext.

### Was entsteht hier?
Noch kein Forschungsergebnis, sondern nur ein **Startsignal für den Run**.

---

### 4.2 Streamlit validates + starts run
**Wo im Code:** `ui/app.py`

### Was passiert?
Die UI prüft die Eingaben und startet dann `run_pipeline(...)`.

### Wie passiert das?
`run_pipeline(company_name=..., web_domain=..., on_message=...)` wird aufgerufen.
Zusätzlich bekommt die Pipeline einen `on_message`-Hook, damit laufende Statusmeldungen wieder im UI auftauchen können.

### Warum ist das wichtig?
Weil die UI dadurch während des Laufs sichtbar machen kann, was gerade passiert.
Der Lauf ist also nicht stumm, sondern sendet Ereignisse zurück.

### Ergebnis dieses Schritts
Der eigentliche Backend-Lauf beginnt.

---

### 4.3 `run_pipeline()` bootstraps runtime
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Jetzt baut das System die technische Laufumgebung für genau diesen einen Fall auf.

### Wie passiert das konkret?
`run_pipeline()` macht diese Schritte in dieser Reihenfolge:

1. Es misst die Laufzeit mit `perf_counter()`.
2. Es erzeugt eine neue `run_id` über `_timestamp_run_id()`.
3. Es legt den Zielordner logisch fest: `artifacts/runs/<run_id>`.
4. Es baut aus den UI-Eingaben ein `IntakeRequest`.
5. Es erstellt die Runtime-Agenten mit `create_runtime_agents()`.
6. Es öffnet den Langzeitspeicher `FileLongTermMemoryStore`.
7. Es baut den `RunContext`.

### Warum ist das wichtig?
Weil ab hier klar feststeht:

- welcher Run das ist,
- welche Agenten beteiligt sind,
- wo später gespeichert wird,
- und welcher Laufzustand offiziell gilt.

### Ergebnis dieses Schritts
Ein vollständig vorbereiteter Run-Rahmen.

---

### 4.4 Retrieve long-term strategies
**Wo im Code:** `src/pipeline_runner.py`, `src/memory/retrieval.py`

### Was passiert?
Bevor recherchiert wird, lädt das System bereits bekannte Strategiemuster aus dem Langzeitgedächtnis.

### Wie passiert das?
Es gibt zwei Arten von Retrieval:

1. **allgemeine Strategien** für die Domain
2. **rollenspezifische Strategien** für einzelne Rollen

Im Code landen sie in:

- `run_context.retrieved_strategies`
- `run_context.retrieved_role_strategies`

### Warum macht das System das so früh?
Weil Departments später nicht bei Null starten sollen.
Sie bekommen damit einen vorsortierten Erfahrungshintergrund.

### Wichtig zu verstehen
Diese Daten sind **Input für den Lauf**, aber nicht das laufende Arbeitsgedächtnis.
Sie werden gelesen, nicht live fortgeschrieben.

---

### 4.5 Build intake brief
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Der Supervisor übersetzt die rohe Nutzereingabe in einen sauber formulierten Arbeitsauftrag.

### Wie passiert das?
`agents["supervisor"].build_intake_brief(intake)` wird aufgerufen.
Das liefert zwei Dinge:

- `brief` — das strukturierte Supervisor-Briefing
- `supervisor_message` — eine darstellbare Supervisor-Nachricht

Außerdem wird `run_context.supervisor_brief` gesetzt.

### Warum ist das wichtig?
Weil alle Departments später **nicht direkt auf rohen UI-Text** schauen sollen, sondern auf einen vereinheitlichten Arbeitsauftrag.

### Ergebnis dieses Schritts
Ein standardisiertes Briefing für den Rest des Systems.

---

### 4.6 Handoff an `run_supervisor_loop()`
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
`run_pipeline()` übergibt die Kontrolle jetzt an die eigentliche Orchestrierung.

### Wie passiert das?
`run_supervisor_loop(...)` wird mit `brief`, `run_context`, `agents` und `on_message` aufgerufen.

### Warum ist das wichtig?
Ab diesem Punkt startet die echte Abarbeitung der Fachaufgaben.

---

## 5. Phase 02 — Supervisor Backlog + Routing

Dieser Abschnitt entspricht in der DRAWIO dem Bereich **„02 — Supervisor Backlog + Routing“**.

Der Supervisor ist hier die Instanz, die den Ablauf ordnet, aber nicht selbst die Fachrecherche ausführt.

---

### 5.1 Supervisor opens run + registers backlog
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Der Supervisor eröffnet den Lauf und baut die Hauptbehälter für die Orchestrierung auf.

### Konkret werden angelegt:

- `sections = {}`
- `department_packages = {}`
- `messages = []`
- `completed_backlog = []`
- `department_timings = {}`

Dann werden erzeugt:

- `assignments = build_initial_assignments(brief)`
- `department_assignments = build_department_assignments(brief)`

Außerdem sendet der Supervisor seine `opening_message()`.

### Warum ist das wichtig?
Weil der Supervisor damit festlegt:

- welche Aufgaben es überhaupt gibt,
- welchem Department sie gehören,
- und wo ihre Ergebnisse später abgelegt werden.

---

### 5.2 Welche Standardaufgaben verteilt das System?
**Wo im Code:** `src/app/use_cases.py`, `src/orchestration/task_router.py`

Die Standardaufgaben sind aktuell im Wesentlichen so aufgeteilt:

#### CompanyDepartment
- `company_fundamentals`
- `product_asset_scope`

#### MarketDepartment
- `market_situation`
- Historisch: zusaetzliche Markt-Tasks fuer Repurposing/Circularity und Analytics/Operational Improvement

#### BuyerDepartment
- `peer_companies`
- `monetization_redeployment`

#### ContactDepartment
- `contact_discovery`
- `contact_qualification`

#### SynthesisDepartment
- `liquisto_opportunity_assessment`
- `negotiation_relevance`

### Warum ist das wichtig?
So wird die Gesamtaufgabe in klarere Fachpakete zerlegt.

---

### 5.3 Build assignments + department order
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Die Aufgaben werden nicht in beliebiger Reihenfolge abgearbeitet.
Es gibt eine feste Ablaufstruktur.

### Die Reihenfolge ist:

1. **parallel:** `CompanyDepartment` und `MarketDepartment`
2. **danach:** `BuyerDepartment`
3. **danach:** `ContactDepartment`
4. **zum Schluss:** `SynthesisDepartment`

### Warum genau so?
Weil Buyer und Contact auf frühere Ergebnisse angewiesen sind.
Zum Beispiel ist Contact erst dann sinnvoll, wenn vorher genügend belastbare Firmen- oder Käuferhinweise vorliegen.

---

### 5.4 Task registration im `RunContext`
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Alle nicht-Synthesis-Aufgaben werden im `RunContext` als aktive Tasks registriert.

### Warum macht das System das?
Damit später nachvollziehbar ist:

- welche Aufgaben geplant waren,
- welches Modell sie nutzen sollten,
- welche Tools erlaubt waren,
- und welchen Status sie bekommen haben.

### Wichtig
Die Synthesis-Aufgaben werden **nicht sofort** hier registriert, sondern später im eigenen Synthesis-Block, damit keine doppelten Task-Einträge entstehen.

---

## 6. Phase 03 — Department Execution

Dieser Abschnitt entspricht in der DRAWIO dem Bereich **„03 — Department Execution“**.

Das ist der Kern der eigentlichen Recherchearbeit.

---

### 6.1 Parallel start: Company + Market
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Die Departments `CompanyDepartment` und `MarketDepartment` können gleichzeitig laufen.

### Wie passiert das?
Der Supervisor startet sie per `ThreadPoolExecutor` parallel.

### Warum ist das möglich?
Weil diese beiden Department-Typen am Anfang noch nicht direkt voneinander abhängen.

---

### 6.2 Warum gibt es Working Sets?
**Wo im Code:** `src/memory/short_term_store.py`, `src/orchestration/supervisor_loop.py`

### Was passiert?
Jedes parallel laufende Department bekommt **nicht** direkt das gemeinsame Hauptgedächtnis zum freien Schreiben.
Stattdessen bekommt es ein eigenes isoliertes Working Set.

### Wie passiert das?
Für jedes parallele Department werden erzeugt:

- `ws = run_context.short_term_memory.create_working_set()`
- `baseline = run_context.short_term_memory.create_working_set()`

Nach dem Department-Lauf wird nur die Differenz (`delta_from`) zurückgemischt.

### Warum ist das wichtig?
Weil so parallele Läufe sich nicht gegenseitig unkontrolliert überschreiben.

**Einfach gesagt:**
Jedes Department arbeitet erst in seiner eigenen Notizmappe. Erst danach werden nur die neuen Einträge kontrolliert in die gemeinsame Fallakte zurückgeschrieben.

---

### 6.3 Supervisor emits `department_assigned`
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Bevor ein Department losläuft, sendet der Supervisor ein Ereignis, das sagt:

- welches Department gestartet wurde,
- auf welchen Zielabschnitt es arbeitet,
- und welche Tasks dazu gehören.

### Warum ist das wichtig?
Damit UI und Log nachvollziehen können, wann ein Department offiziell startet.

---

### 6.4 DepartmentRuntime startet das Department
**Wo im Code:** `src/orchestration/department_runtime.py`

### Was passiert?
Der Supervisor ruft `department_runtime.run(...)` auf.

### Was ist `DepartmentRuntime`?
Ein dünner Wrapper. Die eigentliche Logik liegt im `DepartmentLeadAgent`.

### Warum gibt es diesen Wrapper trotzdem?
Damit der Supervisor jedes Department gleichartig ansprechen kann.

---

## 7. Reusable Department Inner Loop — was innerhalb eines Departments wirklich passiert

Dieser Block ist einer der wichtigsten Teile der DRAWIO.
Er zeigt, was **innerhalb eines einzelnen Department-Laufs** geschieht.

**Hauptdatei:** `src/agents/lead.py`

Jedes Department arbeitet intern mit einer kleinen Rollenstruktur:

- `DepartmentLeadAgent` — steuert den Fachbereich
- `Researcher` — führt die eigentliche Recherche aus
- `Critic` — prüft Qualität und Vollständigkeit
- `Judge` — entscheidet Grenzfälle nach fehlgeschlagenen Versuchen
- `CodingAssistant` — hilft bei Suchverfeinerung
- `Executor` — führt registrierte Tool-Funktionen aus

---

### 7.1 Department opens workspace
**Wo im Code:** `src/agents/lead.py`, `src/memory/short_term_store.py`

### Was passiert?
Zu Beginn reserviert das Department einen eigenen Arbeitsbereich im `ShortTermMemoryStore`.

### Warum?
Damit die internen Ergebnisse dieses Departments separat nachverfolgt werden können.

---

### 7.2 Department creates `DepartmentRunState`
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Das Department legt einen `DepartmentRunState` an.

### Was steckt darin?
Zum Beispiel:

- `current_payload`
- `task_artifacts`
- `review_artifacts`
- `decision_artifacts`
- `attempts`
- `revision_requests`
- `query_overrides`
- `tool_errors`

### Warum ist das wichtig?
Das ist die **vollständige interne Ablaufakte dieses Departments**.
Nicht nur das Endergebnis, sondern auch jeder Versuch und jede Bewertung werden hier gesammelt.

---

### 7.3 Department builds investigation plan
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Aus den übergebenen Assignments baut der Lead einen internen Untersuchungsplan.

### Warum?
Weil das Department nicht chaotisch arbeiten soll, sondern in einer definierten Aufgabenfolge.

---

### 7.4 Department creates GroupChat agents
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Für den Department-Lauf werden mehrere AG2-Agenten erstellt:

- Lead
- Researcher
- Critic
- Judge
- Coding Assistant
- Executor

### Warum?
Weil der Department-Lauf als kontrollierter Mini-Dialog organisiert ist.
Jede Rolle hat eine klarere Verantwortung als ein einzelner großer Agent.

---

### 7.5 Welche Tools kann der Department-Lead benutzen?
**Wo im Code:** `src/agents/lead.py`

Der Lead kann über registrierte Funktionen indirekt diese Aktionen auslösen:

- `run_research(task_key)`
- `review_research(task_key)`
- `suggest_refined_queries(task_key)`
- `judge_decision(task_key)`
- `finalize_package(summary)`

Diese Tool-Funktionen sind extrem wichtig, weil der sichtbare Chattext allein nicht das System verändert — die eigentlichen Zustandsänderungen passieren in diesen Funktionen.

---

### 7.6 `run_research(task_key)`
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Der Lead lässt für eine konkrete Aufgabe recherchieren.

### Exakter Ablauf
1. Es wird geprüft, ob die Aufgabe überhaupt bekannt ist.
2. Es wird geprüft, ob interne Abhängigkeiten erfüllt sind.
3. Falls eine lokale Abhängigkeit fehlt, wird ein blockiertes Artefakt erzeugt.
4. Sonst erhöht das System den Attempt-Zähler.
5. Dann ruft es `self.worker.run(...)` auf.
6. Das Worker-Ergebnis wird als `TaskArtifact` gespeichert.
7. Das Payload des Workers wird gegen das erwartete Task-Schema geprüft.
8. Falls es grobe Vertragsverletzungen gibt, wird `needs_contract_review = True` gesetzt.
9. Das Payload wird in `run_state.current_payload` übernommen.
10. Der Worker-Report wird in das Memory ingestiert.

### Warum so viele Schritte?
Weil das System nicht einfach nur „etwas Text“ will, sondern:

- nachvollziehbare Fakten,
- strukturierte Daten,
- prüfbare Schema-Treue,
- und reproduzierbare Zwischenstände.

### Wichtiger Spezialfall: Payload loss guard
Wenn ein neuer Worker-Output weniger Felder enthält als vorher schon vorhanden waren, versucht das System Datenverlust zu vermeiden.
Nicht-leere Altwerte werden dann konservativ erhalten.

---

### 7.7 `review_research(task_key)`
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Der Critic prüft den aktuellen Forschungsstand einer Aufgabe.

### Wie?
Er bewertet unter anderem:

- ob die Aufgabe inhaltlich erfüllt wurde,
- welche Punkte akzeptiert werden können,
- welche Punkte fehlen oder schwach sind,
- welche Probleme offen bleiben.

Das Ergebnis wird als `TaskReviewArtifact` gespeichert und zusätzlich ins Memory geschrieben.

### Warum ist das wichtig?
Weil das Department nicht schon nach dem ersten Rechercheversuch automatisch „fertig“ ist.
Zwischen „gefunden“ und „verwendbar“ liegt noch ein Prüfprozess.

---

### 7.8 Wann wird der Judge benutzt?
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Wenn ein Task nicht sauber zu Ende kommt oder Vertragsprobleme bleiben, kann der Judge eine Abschlussentscheidung treffen.

### Typische Situation
- der Critic lehnt ab,
- oder zu viele Versuche wurden gebraucht,
- oder das Artefakt hat `needs_contract_review = True`.

Dann ruft der Lead `judge_decision(task_key)` auf.

### Warum ist das wichtig?
Damit der Department-Lauf nicht in endlosen Schleifen hängen bleibt.
Es braucht eine Instanz, die Grenzfälle beendet.

---

### 7.9 Welche Endzustände kann ein Task bekommen?
**Wo im Code:** `src/agents/lead.py`, `src/orchestration/supervisor_loop.py`

Im Lauf tauchen mehrere Statusbegriffe auf. Für das Verständnis hilfreich ist diese einfache Lesart:

- `accepted` — fachlich nutzbar
- `degraded` — verwendbar, aber mit Lücken oder Vorsicht
- `blocked` — konnte wegen Abhängigkeiten nicht sinnvoll laufen
- `skipped` — wurde bewusst nicht ausgeführt

Zusätzlich gibt es im Envelope später Entscheidungen wie:

- `accepted`
- `accepted_with_gaps`
- `rejected`

**Wichtig:**
Task-Status und Supervisor-Admission sind nicht exakt dasselbe. Ein Task kann intern als „degraded“ enden, und das Department-Paket kann trotzdem als „accepted_with_gaps“ downstream sichtbar werden.

---

### 7.10 `finalize_package(summary)`
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Der Lead baut aus allen gespeicherten Task-Artefakten, Reviews und Entscheidungen das offizielle Department-Paket.

### Wie passiert das?
Für jede Assignment-Aufgabe wird geschaut:

- gibt es schon eine finale Entscheidung?
- gibt es Review + Artefakt, aber noch keine Entscheidung?
- gab es Vertragsprobleme?
- gab es überhaupt belastbare Forschung?

Dann sammelt das System:

- `accepted_points`
- `open_questions`
- `sources`
- Task-Zusammenfassungen
- eine Department-Confidence
- einen `report_segment`

Am Ende wird ein `DepartmentPackage` gebaut.

### Warum ist das wichtig?
Das Department-Paket ist das **offizielle Produkt des Fachbereichs**.
Nicht der interne Chat, nicht ein einzelner Worker-Report, sondern dieses Paket geht später in die Supervisor-Prüfung.

---

### 7.11 Was passiert, wenn `finalize_package()` nie erreicht wird?
**Wo im Code:** `src/agents/lead.py`

### Was passiert?
Falls der interne GroupChat sein `max_round` erreicht, ohne sauber zu finalisieren, baut das System ein Fallback-Paket.

### Warum ist das wichtig?
Damit ein Department-Lauf nicht einfach spurlos scheitert.
Auch ein unvollständiger Lauf soll als diagnostisch verwertbares Ergebnis enden.

---

### 7.12 Was wird nach Department-Ende gespeichert?
**Wo im Code:** `src/agents/lead.py`, `src/memory/short_term_store.py`

Nach Abschluss speichert das System unter anderem:

- das Department-Paket
- den vollständigen `DepartmentRunState`
- die Department-Konversation

### Warum ist das wichtig?
Weil genau diese Daten später für run-basierte Follow-up-Fragen wiederverwendet werden können.

---

## 8. Zurück im Supervisor — Department review + acceptance gate

Dieser Teil entspricht in der DRAWIO dem Schritt nach dem Department-Lauf.

---

### 8.1 Supervisor reviews department package
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Nachdem ein Department fertig ist, entscheidet der Supervisor, wie mit dem Paket weiter umgegangen wird.

Er ruft auf:
`agents["supervisor"].accept_department_package(...)`

### Warum ist das wichtig?
Weil nicht jedes Department-Ergebnis automatisch downstream sichtbar werden soll.

---

### 8.2 `_apply_acceptance_gate(...)`
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Die Entscheidung des Supervisors wird in die offiziellen Laufobjekte geschrieben.

### Vereinfacht gibt es drei Fälle

#### Fall A — `accepted`
- das Paket wird zugelassen
- der Abschnitt kommt in `sections`
- das Department bekommt einen Envelope mit zugelassenem Payload

#### Fall B — `accepted_with_gaps`
- das Paket ist benutzbar, aber nicht perfekt
- der Abschnitt ist downstream sichtbar
- die Lücken bleiben dokumentiert

#### Fall C — `rejected`
- das Paket bleibt diagnostisch erhalten
- aber es wird nicht als regulärer, freigegebener Abschnitt weitergegeben

### Warum diese drei Fälle?
Damit das System nicht nur zwischen „perfekt“ und „unbrauchbar“ unterscheiden muss.
Gerade in realer Research-Arbeit gibt es oft brauchbare Ergebnisse mit Unsicherheiten.

---

### 8.3 Task statuses werden aktualisiert
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Für jede Aufgabe des Departments werden Task-Statuswerte in:

- `run_context.active_tasks`
- `run_context.short_term_memory.task_statuses`
- `completed_backlog`

aktualisiert.

### Warum?
Damit der Rest des Systems weiß, was erledigt, degradiert oder übersprungen wurde.

---

### 8.4 Delta merge nach parallelen Departments
**Wo im Code:** `src/orchestration/supervisor_loop.py`, `src/memory/short_term_store.py`

### Was passiert?
Nach Company und Market werden die Änderungen aus den isolierten Working Sets in fester Reihenfolge zurückgemischt.

### Warum ist die Reihenfolge wichtig?
Weil das System deterministischer werden soll.
Es wird also **nicht** in der Reihenfolge des zufälligen Fertigwerdens gemischt, sondern in einer festeren kanonischen Reihenfolge.

---

### 8.5 BuyerDepartment läuft sequenziell
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Nach dem parallelen Start folgt Buyer.

### Warum jetzt erst?
Weil Buyer auf vorher erzeugte Markt- und Unternehmenssignale aufsetzt.

---

### 8.6 ContactDepartment bekommt zusätzliche Buyer-Kandidaten
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Bevor Contact läuft, erweitert das System bei Bedarf `current_section` um `buyer_candidates`, die aus `market_network` abgeleitet wurden.

### Wie?
Es liest Firmen aus:

- `peer_competitors.companies`
- `downstream_buyers.companies`

und hängt deren Namen als Kandidaten an.

### Warum ist das wichtig?
Damit Contact nicht im luftleeren Raum sucht, sondern auf vorher identifizierte relevante Firmen zugreifen kann.

---

### 8.7 Generische Run Conditions
**Wo im Code:** `src/orchestration/task_router.py`

### Was passiert?
Nicht jede Aufgabe läuft immer. Manche haben Bedingungen.

### Beispiele
- `contact_discovery` läuft nur, wenn Buyer genug priorisierte Firmen geliefert hat.
- `contact_qualification` läuft nur, wenn `contact_discovery` bereits sinnvoll abgeschlossen wurde.

### Warum ist das wichtig?
Damit das System keine Folgeaufgaben startet, wenn die Grundlage dafür fehlt.

---

### 8.8 Token budget enforcement
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Nach sequenziellen Departments schaut der Supervisor auf das bisher verbrauchte Token-Budget.

### Es gibt zwei Schwellen
- Soft Budget
- Hard Cap

### Was passiert bei Überschreitung?
- Beim Soft Budget läuft das System weiter, protokolliert aber die knappe Lage.
- Beim Hard Cap wird der restliche Department-Lauf abgebrochen.

### Warum ist das wichtig?
Damit der Lauf nicht unkontrolliert teuer oder endlos wird.

---

## 9. Phase 04 — Synthesis + Back-Requests

Dieser Abschnitt entspricht in der DRAWIO dem Bereich **„04 — Synthesis + Back-Requests“**.

Die Synthesis macht **keine neue Grundrecherche**, sondern baut aus den Department-Ergebnissen die Gesamtbewertung.

---

### 9.1 Synthesis tasks werden registriert
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Jetzt werden die Synthesis-Aufgaben offiziell in den `RunContext` eingetragen.

### Warum erst jetzt?
Damit sie nicht doppelt auftauchen und klar ist: Synthesis startet erst nach den Fachbereichen.

---

### 9.2 Build `quality_review`
**Wo im Code:** `src/pipeline_runner.py`, `src/orchestration/supervisor_loop.py`, `src/orchestration/synthesis.py`

### Was passiert?
Bevor die Synthesis startet, wird aus dem Memory-Snapshot ein Qualitätsbild gebaut.

### Warum?
Damit die Synthesis nicht nur Fachinhalte sieht, sondern auch ein Signal darüber bekommt, wie belastbar die bisherige Recherche insgesamt wirkt.

---

### 9.3 Build `synthesis_context`
**Wo im Code:** `src/orchestration/supervisor_loop.py`, `src/orchestration/synthesis.py`

### Was passiert?
Zusätzlich zu den Department-Paketen baut das System einen vorverdichteten Kontext für die Synthesis.

Darin stecken unter anderem:

- vorbereitete Service-Relevanzen
- empfohlene Engagement-Pfade
- Risiken
- zusammengefasste Markt-/Buyer-Signale

### Warum ist das wichtig?
Damit die Synthesis auf einer strukturierten Basis startet und nicht alles erst selbst zusammensammeln muss.

---

### 9.4 Start der `SynthesisRuntime`
**Wo im Code:** `src/orchestration/synthesis_runtime.py`, `src/agents/synthesis_department.py`

### Was passiert?
Die Synthesis bekommt:

- das Briefing
- die Department-Packages
- den Supervisor
- die Department-Runtimes
- das Memory
- den `synthesis_context`

### Warum bekommt sie auch Supervisor und Departments?
Weil sie bei Bedarf Rückfragen auslösen kann.

---

## 10. Reusable Synthesis Runtime — was innerhalb der Synthesis passiert

---

### 10.1 Welche Rollen gibt es in der Synthesis?
**Wo im Code:** `src/agents/synthesis_department.py`

Die Synthesis arbeitet mit:

- `SynthesisLead`
- `SynthesisAnalyst`
- `SynthesisCritic`
- `SynthesisJudge`
- `SynthesisExecutor`

### Rollen in einfacher Sprache
- **Lead:** steuert die Gesamtarbeit
- **Analyst:** liest und verbindet Department-Ergebnisse
- **Critic:** prüft Widersprüche und Lücken
- **Judge:** entscheidet den Grenzfall
- **Executor:** führt registrierte Funktionen aus

---

### 10.2 `read_report_segment(department)`
**Wo im Code:** `src/agents/synthesis_department.py`

### Was passiert?
Der Analyst liest das offizielle Report-Segment eines Departments.

### Wie?
Der Code nutzt Resolver-Funktionen, damit er sauber aus dem Envelope lesen kann.

### Warum ist das wichtig?
Weil die Synthesis nicht auf irgendein Rohobjekt zugreifen soll, sondern kontrolliert auf den offiziell freigegebenen Department-Auszug.

---

### 10.3 Welche Segmente stehen der Synthesis zur Verfügung?
**Wo im Code:** `src/agents/synthesis_department.py`

Vor dem Start wird `available_segments` gebildet.
Ein Department zählt nur dann als verfügbar, wenn sein `report_segment` sinnvoll vorhanden ist.

### Warum?
Damit die Synthesis weiß, welche Fachbereiche tatsächlich lesbar sind.

---

### 10.4 `request_department_followup(...)`
**Wo im Code:** `src/agents/synthesis_department.py`

### Was passiert?
Wenn die Synthesis merkt, dass ein Fachbereich noch etwas nachschärfen muss, kann sie ein Follow-up anfordern.

### Exakter Ablauf
1. Die Synthesis legt einen `BackRequest` an.
2. Der Supervisor routet die Frage.
3. Das passende Department-Runtime wird ausgewählt.
4. Dann läuft `dept_runtime.run_followup(...)`.
5. Das aktualisierte `report_segment` wird in das `raw_package` dieses Departments zurückgeschrieben.

### Warum ist das wichtig?
Die Synthesis kann damit gezielt nachschärfen, statt die ganze Pipeline neu zu starten.

### Wichtiger Präzisionshinweis
Im Synthesis-Prompt ist die Regel formuliert, **maximal ein Follow-up pro Department** zu nutzen. Diese Begrenzung ist in der sichtbaren Prompt-Logik klar kommuniziert. Der hier sichtbare Laufcode speichert und verarbeitet Back-Requests, erzwingt diese Obergrenze aber nicht als harte technische Schranke.

---

### 10.5 Department Follow-up Mini-Runtime
**Wo im Code:** `src/agents/lead.py` (`run_followup`)

### Was passiert?
Ein Department beantwortet eine gezielte Rückfrage in einem kleineren Speziallauf.

### Wie läuft dieser Mini-Prozess?
1. Es wird ein kleiner neuer `DepartmentRunState` für den Follow-up-Lauf gebaut.
2. Ein einzelnes Follow-up-Assignment wird erstellt.
3. Ein kleiner GroupChat mit Lead, Researcher und Critic startet.
4. `run_research("followup_question")` wird ausgeführt.
5. `finalize_followup(summary)` erzeugt ein neues `report_segment`.
6. Dieses Segment geht zurück an die Synthesis.

### Warum ist das wichtig?
Weil eine kleine Rückfrage oft viel günstiger ist als ein kompletter Neu-Lauf des Departments.

---

### 10.6 `finalize_synthesis(...)`
**Wo im Code:** `src/agents/synthesis_department.py`

### Was passiert?
Wenn die Synthesis genug Informationen hat, baut sie das finale Synthesis-Ergebnis.

### Dabei werden unter anderem gesammelt:

- `executive_summary`
- `opportunity_assessment`
- `opportunity_assessment_summary`
- `negotiation_relevance`
- `recommended_engagement_paths`
- `key_risks`
- `next_steps`
- `sources`
- `department_confidences`
- `back_requests`
- `generation_mode`
- `confidence`

### Warum ist das wichtig?
Das ist die Stelle, an der aus mehreren Fachsegmenten eine Gesamtgeschichte für den Zielcase gebaut wird.

---

### 10.7 Was passiert, wenn die Synthesis nicht sauber finalisiert?
**Wo im Code:** `src/agents/synthesis_department.py`

### Was passiert?
Wenn `max_round=20` erreicht wird und keine saubere Finalisierung erfolgt, baut die Synthesis ein konservatives Fallback-Ergebnis.

### Warum?
Damit der Lauf nicht ohne Endprodukt endet.

---

## 11. Supervisor review der Synthesis

### 11.1 Supervisor akzeptiert oder verwirft die Synthesis
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Nach der Synthesis entscheidet der Supervisor erneut über die Zulassung.

Er ruft auf:
`agents["supervisor"].accept_synthesis(...)`

### Ergebnis
Es entsteht wieder ein offizieller Envelope für `SynthesisDepartment` mit:

- `admission`
- `raw_package`
- optional `admitted_payload`

### Warum?
Weil auch die Synthesis nicht automatisch als gültig gelten soll.

---

### 11.2 Statusabbildung der Synthesis-Tasks
**Wo im Code:** `src/orchestration/supervisor_loop.py`

### Was passiert?
Die Synthesis-Entscheidung wird in Task-Statuswerte übersetzt.

Vereinfacht:
- `accepted` bleibt `accepted`
- `accepted_with_gaps` wird als `degraded` geführt
- `rejected` wird ebenfalls als `degraded` weitergeführt

### Warum ist das nützlich?
Weil dadurch auch die Synthesis in die normale Task-Status-Logik des Laufs passt.

---

## 12. Phase 05 — Assembly + Export

Dieser Abschnitt entspricht in der DRAWIO dem Bereich **„05 — Assembly + Export“**.

Hier werden die bisherigen Zwischenergebnisse in die endgültigen Exportobjekte umgewandelt.

---

### 12.1 Rückkehr von `run_supervisor_loop()` nach `run_pipeline()`
**Wo im Code:** `src/pipeline_runner.py`

### Was kommt zurück?
`run_supervisor_loop()` liefert:

- `sections`
- `department_packages`
- `loop_messages`
- `completed_backlog`
- `department_timings`

### Warum ist das wichtig?
Ab hier ist die eigentliche Facharbeit abgeschlossen. Jetzt beginnt das Zusammenbauen der finalen Exportstruktur.

---

### 12.2 `quality_review` wird endgültig erzeugt
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Aus dem finalen Memory-Snapshot wird die `quality_review`-Sektion gebaut.

### Warum?
Sie gehört zum finalen Pipeline-Ergebnis und gibt einen Überblick über Beleglage und offene Lücken.

---

### 12.3 Aus der Synthesis-Admission wird das finale `synthesis`-Objekt gebaut
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Jetzt schaut die Pipeline auf den offiziellen Synthesis-Envelope und baut daraus das finale Synthesis-Objekt.

### Drei Fälle

#### Fall A — Synthesis `accepted`
Das AG2-Ergebnis wird übernommen und mit Confidence/Evidence-Kontext ergänzt.

#### Fall B — Synthesis `accepted_with_gaps`
Das Ergebnis bleibt nutzbar, wird aber als lückenbehaftet markiert.

#### Fall C — Synthesis `rejected`
Dann baut die Pipeline **kein normales Erfolgsergebnis**, sondern ein blockiertes Maschinenartefakt mit z. B.:

- `section_status = "blocked"`
- `reason`
- `executive_summary` mit Block-Hinweis
- `generation_mode = "blocked"`
- `key_risks`
- `next_steps`

### Warum ist das wichtig?
Damit auch bei abgelehnter Synthesis ein sauberer maschinenlesbarer Endzustand entsteht.

---

### 12.4 `assess_research_readiness(...)`
**Wo im Code:** `src/pipeline_runner.py`, `src/orchestration/synthesis.py`

### Was passiert?
Das System bewertet, wie nutzbar der gesamte Lauf insgesamt ist.

### Typische Ergebnisse
- `usable = true`
- `partial = true`
- oder nicht ausreichend nutzbar

### Warum?
Weil am Ende nicht nur Inhalte zählen, sondern auch die Frage: Ist das Resultat überhaupt verwendbar?

---

### 12.5 `validate_pipeline_data(...)`
**Wo im Code:** `src/pipeline_runner.py`, `src/models/schemas.py`, `src/models/registry.py`

### Was passiert?
Jetzt werden alle Hauptsektionen zu einem finalen `pipeline_data`-Objekt zusammengesetzt und validiert:

- `company_profile`
- `industry_analysis`
- `market_network`
- `contact_intelligence`
- `quality_review`
- `synthesis`
- `research_readiness`
- `validation_errors`

### Warum ist das wichtig?
Das ist die Stelle, an der aus vielen Einzelteilen ein **kanonisches Gesamtergebnis** wird.

---

### 12.6 `report_writer.run(...)`
**Wo im Code:** `src/pipeline_runner.py`, `src/orchestration/report_runtime.py`, `src/agents/report_writer.py`

### Was passiert?
Zusätzlich zum maschinenfreundlichen `pipeline_data` läuft jetzt ein eigener
Runtime-Schritt `report_writer`.

Dieser ruft `ReportWriterAgent.build_report_package(...)` auf und erzeugt ein
stabil strukturiertes `report_package`.

### Warum?
Damit es eine Struktur gibt, die sich leichter für UI, Bericht oder Präsentation weiterverwenden lässt.
Außerdem ist die Report-Erstellung damit als echter Runtime-Knoten sichtbar
(inklusive eigener `ReportWriter`-Message im Event-Stream).

### Ergebnis
`run_context.report_package` wird gesetzt.

---

### 12.7 Finaler Laufstatus
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Der Lauf bekommt einen finalen Status:

- `completed`
- `completed_partial`
- `completed_but_not_usable`
- oder im Fehlerfall `failed`

### Warum?
Weil spätere Auswertung, UI und Export wissen müssen, wie der Lauf offiziell zu bewerten ist.

---

### 12.8 Usage, Budget, Laufzeit
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Das System sammelt:

- geschätzte Kosten
- LLM-Calls
- Suchaufrufe
- Page-Fetches
- Department-Timings
- Gesamtlaufzeit

### Warum?
Das ist wichtig für Nachvollziehbarkeit und Betriebssteuerung.

---

### 12.9 Long-term memory upsert
**Wo im Code:** `src/pipeline_runner.py`, `src/memory/consolidation.py`, `src/memory/long_term_store.py`

### Was passiert?
Aus dem Run werden konsolidierte Rollenmuster extrahiert.
Nur wenn bestimmte Bedingungen erfüllt sind, werden sie in den Langzeitspeicher geschrieben.

### Warum ist das wichtig?
Das System soll aus guten Läufen lernen, aber nicht jedes fallbezogene Detail blind in Langzeitwissen verwandeln.

---

### 12.10 `export_run(...)`
**Wo im Code:** `src/exporters/json_export.py`

### Was passiert?
Am Ende werden die Laufartefakte auf die Festplatte geschrieben.

### Welche Dateien entstehen?
Im Ordner `artifacts/runs/<run_id>/` entstehen mindestens:

- `run_meta.json`
- `chat_history.json`
- `pipeline_data.json`
- `run_context.json`
- `memory_snapshot.json`

### Warum ist das wichtig?
Weil genau diese Dateien den Lauf später nachvollziehbar, prüfbar und wieder ladbar machen.

---

### 12.11 Fehlerfall in `run_pipeline()`
**Wo im Code:** `src/pipeline_runner.py`

### Was passiert?
Wenn während des Laufs eine Exception auftritt:

- wird `run_context.status = "failed"` gesetzt,
- der Fehlertext gespeichert,
- und trotzdem ein Fehler-Export geschrieben.

### Warum ist das wichtig?
Auch ein fehlgeschlagener Lauf soll diagnostisch sichtbar bleiben.

---

## 13. Phase 06 — Existing Run Follow-up

Dieser Abschnitt entspricht in der DRAWIO dem Bereich **„06 — Existing Run Follow-up“**.

Ganz wichtig: Hier gibt es zwei unterschiedliche Arten von „Follow-up“.

### Art A — Synthesis-internes Follow-up
Das passiert **während des ursprünglichen Laufs**, wenn die Synthesis eine Rückfrage an ein Department schickt.

### Art B — Run-basiertes Follow-up nach dem Lauf
Das passiert **später**, wenn ein Nutzer zu einem bereits abgeschlossenen Run eine neue Frage stellt.

Der Abschnitt hier beschreibt **Art B**.

---

### 13.1 `load_run_artifact(run_id)`
**Wo im Code:** `src/orchestration/follow_up.py`

### Was passiert?
Das System lädt einen früher gespeicherten Run wieder ein.

### Welche Dateien liest es?
- `pipeline_data.json`
- `run_context.json`

### Warum ist das wichtig?
So kann eine neue Frage auf dem alten Lauf aufsetzen, ohne alles neu rechnen zu müssen.

---

### 13.2 Was wird beim Follow-up wiederhergestellt?
**Wo im Code:** `src/orchestration/follow_up.py`

Geladen werden unter anderem:

- die finalen Sektionen aus `pipeline_data`
- die Department-Pakete
- die Department-Run-States
- offene Fragen und Belege aus dem Run-Gedächtnis

### Warum?
Damit eine Folgeantwort nicht bloß aus dem Endbericht geraten wird, sondern sich auf die gespeicherte Laufakte stützen kann.

---

### 13.3 Follow-up-Routing
**Wo im Code:** `src/orchestration/follow_up.py`

### Was passiert?
Die Folgefrage wird einer Route zugeordnet, etwa:

- Company
- Market
- Buyer
- Contact
- Synthesis
- Cross-domain

### Warum?
Weil jede Frage aus einem anderen Teil der Run-Akte am besten beantwortet werden kann.

---

### 13.4 Antworten aus der Run-Akte, nicht aus neuer Web-Recherche
**Wo im Code:** `src/orchestration/follow_up.py`

### Was passiert?
Die Standard-Follow-up-Antworten werden primär aus bereits gespeicherten Daten gebaut.

### Priorität der Belege
1. `task_artifacts` und `decision_artifacts`
2. `review_artifacts`
3. finale Sektionen aus `pipeline_data`
4. offene Fragen aus `department_packages`

### Warum ist das wichtig?
Weil das System hier zuerst versucht, **aus dem bereits bekannten Laufwissen** zu antworten.

---

### 13.5 Was passiert, wenn wirklich neue Forschung nötig wäre?
**Wo im Code:** konzeptionell in `follow_up.py`, operativ über `DepartmentRuntime.run_followup()`

### Was bedeutet das?
Das Modul `follow_up.py` beantwortet Standardfragen aus der gespeicherten Run-Akte.
Wenn eine Frage zusätzliche Recherche braucht, ist das ein anderer Pfad: dann muss wieder ein Department-Follow-up-Lauf gestartet werden.

### Warum ist diese Trennung wichtig?
Weil „eine gespeicherte Antwort formulieren“ und „neue Web-Recherche starten“ zwei grundsätzlich verschiedene Dinge sind.

---

### 13.6 `export_follow_up(...)`
**Wo im Code:** `src/exporters/json_export.py`

### Was passiert?
Follow-up-Antworten werden in `follow_up_history.json` angehängt.

### Warum?
Damit auch spätere Folgefragen selbst wieder nachvollziehbar gespeichert werden.

---

## 14. Was genau ist wann gespeichert?

Für die Nachvollziehbarkeit der DRAWIO ist diese Frage besonders wichtig.

### Während eines Department-Laufs
Gespeichert werden unter anderem:

- Worker-Reports
- Task-Artefakte
- Review-Artefakte
- Decision-Artefakte
- offene Fragen
- Department-Konversation
- Department-Workspace

### Nach Supervisor-Review
Zusätzlich entstehen:

- freigegebene `sections`
- `department_packages` mit Admission-Envelope
- aktualisierte Task-Statuswerte

### Nach Synthesis
Zusätzlich entstehen:

- Synthesis-Envelope
- Synthesis-Sektion
- Quality-Review
- Research-Readiness
- Report-Package

### Am Run-Ende
Auf Platte exportiert werden:

- `run_meta.json`
- `chat_history.json`
- `pipeline_data.json`
- `run_context.json`
- `memory_snapshot.json`

### Bei späteren Follow-ups
Zusätzlich:
- `follow_up_history.json`

---

## 15. Die wichtigsten Entscheidungsstellen im gesamten Lauf

Wenn Du die DRAWIO liest, sind das die wichtigsten „Wenn-dann“-Stellen:

### Entscheidung 1 — Department kann parallel oder nicht parallel laufen
- Company + Market: parallel
- Buyer + Contact: sequenziell

### Entscheidung 2 — Task darf überhaupt laufen?
- Abhängigkeiten erfüllt?
- Run condition erfüllt?
- sonst blockiert oder skipped

### Entscheidung 3 — Research ausreichend?
- Critic akzeptiert?
- braucht Revision?
- braucht Judge?

### Entscheidung 4 — Department-Paket downstream sichtbar?
- `accepted`
- `accepted_with_gaps`
- `rejected`

### Entscheidung 5 — Synthesis braucht Back-Request?
- ja: gezielte Department-Rückfrage
- nein: direkt finalisieren

### Entscheidung 6 — Synthesis wird akzeptiert?
- `accepted`
- `accepted_with_gaps`
- `rejected`

### Entscheidung 7 — Gesamtlauf nutzbar?
- `completed`
- `completed_partial`
- `completed_but_not_usable`
- `failed`

---

## 16. Was die DRAWIO bewusst zeigt — und was nicht

### Die DRAWIO zeigt bewusst
- den echten Hauptlauf
- die wichtigsten Zustandsobjekte
- die Entscheidungspunkte
- die Datenweitergabe
- die Trennung zwischen Department-Läufen, Synthesis und späterem Run-Follow-up

### Die DRAWIO zeigt bewusst nicht jedes Detail
Zum Beispiel nicht:
- jede einzelne Zeile aus den Prompt-Texten
- jede interne Hilfsfunktion
- jeden einzelnen Modellparameter
- jede einzelne Feldtransformation in allen Schemas

### Warum nicht?
Weil die DRAWIO sonst unlesbar würde.
Die Aufgabe der DRAWIO ist **Ablaufklarheit**, nicht Quelltext-Vollständigkeit.
Diese Markdown-Datei ergänzt deshalb den Detailgrad.

---

## 17. Kurzfassung für Nicht-Entwickler

Wenn Du den Lauf in einem Satz erklären willst, dann so:

> Das System startet aus einer Firmeneingabe einen neuen Fall, lässt mehrere Fachbereiche in kontrollierter Reihenfolge recherchieren und prüfen, verdichtet deren Ergebnisse in einer Synthesis, baut daraus ein kanonisches Endergebnis und speichert alles so ab, dass man den gesamten Fall später wieder laden und weiter befragen kann.

Noch einfacher:

> Erst werden Fachinformationen gesammelt, dann geprüft, dann zusammengeführt, dann gespeichert.

---

## 18. Code-Dateien, auf die sich diese Beschreibung hauptsächlich stützt

- `ui/app.py`
- `src/pipeline_runner.py`
- `src/orchestration/supervisor_loop.py`
- `src/orchestration/department_runtime.py`
- `src/agents/lead.py`
- `src/agents/synthesis_department.py`
- `src/orchestration/synthesis_runtime.py`
- `src/orchestration/synthesis.py`
- `src/orchestration/follow_up.py`
- `src/orchestration/task_router.py`
- `src/memory/short_term_store.py`
- `src/exporters/json_export.py`
- `src/models/schemas.py`

---

## 19. Fazit

Wenn Du die DRAWIO zusammen mit dieser Datei liest, solltest Du jeden Hauptpfeil beantworten können mit:

- **Was startet hier?**
- **Welche Datei übernimmt jetzt?**
- **Welches Objekt wird geschrieben oder gelesen?**
- **Warum geht der Flow an dieser Stelle weiter?**
- **Was ist das offizielle Ergebnis dieses Schritts?**

Genau dafür ist diese Datei gedacht.
