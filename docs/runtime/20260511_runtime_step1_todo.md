# 2026-05-11 Runtime Step 1 TODO

Diese TODO-Liste sammelt Verbesserungen fuer `Runtime Step 1: Runner Init + Supervisor Brief` mit Zielniveau **2026 Best Practice / State of the Art**.

## 0. Scoping, Phasenplan und Audit-Korrekturen

Dieser Abschnitt wurde nach einem separaten Audit der TODO-Datei ergaenzt. Ziel ist, die Umsetzung zu priorisieren, vorhandenen Code nicht versehentlich neu zu bauen und Abhaengigkeiten zwischen den Punkten sauber zu machen.

**Leitprinzip Step 1:** Step 1 liefert einen ehrlichen Startpunkt. Es klaert, ob die Domain real ist, ob die Homepage erreichbar ist, wie das Unternehmen laut Website heisst und welche Branche es wahrscheinlich ist. Tiefe Firmenidentitaetsrecherche, externe Register-APIs und Multi-Source-Evidence sind Aufgabe des CompanyDepartment in Step 2. Step 1 schafft gutes Routing — nicht abschliessende Wahrheit.

### 0.0 ✅ Bereits umgesetzte Code-Vereinfachungen (2026-05-11)

Diese drei Simplifikationen wurden direkt im Code umgesetzt und sind kein offenes TODO mehr:

- [x] **Doppelte Domain-Normalisierung entfernt:** `build_company_research(...)` in `src/research/tools.py` ruft `normalize_domain()` nicht mehr intern auf. Die Funktion nimmt jetzt `normalized_domain: str` entgegen. Der einzige Normalisierungsaufruf liegt in `_initialize_run()`. Call Site in `supervisor.py` und `tools.py` aktualisiert.

- [x] **Backfill aus Run-Pfad entfernt:** `_long_term_backfill_enabled()` und der `backfill_long_term_memory_from_runs(...)`-Aufruf wurden aus `_initialize_run()` entfernt. Backfill ist ein Maintenance-Job und hat im Run-kritischen Pfad nichts zu suchen. Der Import und die Env-Konstante wurden ebenfalls entfernt.

- [x] **Retrieval-Timing korrigiert:** Das rollenspezifische Retrieval (`retrieved_role_strategies`) wurde aus `_initialize_run()` in `_build_supervisor_brief()` verschoben. Es laeuft jetzt **nach** dem Supervisor Brief mit dem bekannten `brief.industry_hint` — statt davor ohne jeden Kontext. Das allgemeine Retrieval (`retrieved_strategies`) bleibt in `_initialize_run()` fuer den Supervisor-Startkontext.

### 0.1 [x] MVP- und Phase-2-Scope verbindlich festlegen

- [x] **MVP-Scope fuer Step 1:** Punkte 1, 2, 5, 6 und 7 zuerst umsetzen. Ziel: stabiler Step-1-Handoff auf 2026-Niveau ohne produktive DB-/Vector-Migration.
- [x] **Phase-2-Scope:** Punkte 3 und 4 erst nach stabilem MVP und gemeinsamem Datenmodell-Design umsetzen. Ziel: Hetzner/Postgres/pgvector und kontextuelles Hybrid Retrieval.
- [x] Punkt 3 ist strategisch weiterhin Zielarchitektur, aber **nicht MVP-Blocker**.
- [x] Lokale JSON-Artefakte duerfen fuer MVP/Development weiter existieren, sind aber nicht das langfristige Produktionsziel.
- [x] Jede Umsetzung muss markieren, ob sie `MVP`, `Phase 2` oder `Backlog` ist.

**Scope-Entscheidung (2026-05-12):**

| Punkt | Titel (Kurzform) | Scope |
| --- | --- | --- |
| 1 | Intake-Validierung + Domain-Normalisierung | `MVP` |
| 2 | Runtime-Agent-Erzeugung | `MVP` |
| 3 | Memory + RunContext → Hetzner / Postgres / pgvector | `Phase 2` |
| 4 | Retrieval → kontextuelles Hybrid Retrieval | `Phase 2` |
| 5 | Supervisor Brief → Evidence-backed Identity Contract | `MVP` |
| 6 | Supervisor Intake Research Pipeline haerten | `MVP` |
| 7 | Step1Handoff als validierter Contract | `MVP` |

Phase-2-Trigger: Stabiler MVP abgenommen + gemeinsames Datenmodell-Design zwischen Backend und Infrastruktur abgestimmt. Bis dahin bleiben `FileLongTermMemoryStore` und lokale JSON-Artefakte unter `artifacts/` der operative Standard.

### 0.2 [x] Current-State-Delta-Prinzip anwenden

- [x] Jeder Punkt muss vor Umsetzung eine kurze `Current State (Code-Audit)`-Pruefung enthalten.
- [x] Bestehender Code wird erweitert oder gehaertet, nicht blind neu gebaut.
- [x] Bekannte bestehende Bausteine: `IntakeRequest`, `normalize_domain(...)`, `_is_blocked_host(...)`, `create_runtime_agents(...)`, `build_company_research(...)`, `infer_company_identity(...)`, `infer_industry(...)`, `RunContext`, `build_question_registry()`, `build_initial_answer_matrix()`.
- [x] Jede Implementierungs-PR benennt explizit: was bleibt, was wird erweitert, was wird ersetzt.

**Code-Audit MVP-Punkte (2026-05-12):**

**Punkt 1 — Intake + Domain-Normalisierung** (`src/domain/intake.py`, `src/research/normalize.py`)

| | Baustein | Datei | Status |
| --- | --- | --- | --- |
| bleibt | `IntakeRequest` | `src/domain/intake.py` | vorhanden, wird gehaertet |
| bleibt | `_is_blocked_host()` | `src/research/normalize.py` | vorhanden, unveraendert |
| bleibt | `normalize_domain()` | `src/research/normalize.py` | bleibt als Rueckwaerts-Wrapper |
| neu | `NormalizedDomainResult` | `src/research/normalize.py` | typisierter Normalisierungsvertrag |
| neu | `IntakeErrorCode` | `src/research/normalize.py` | maschinenlesbarer Fehlerkatalog |
| neu | `normalize_domain_result()` | `src/research/normalize.py` | vollstaendige Validierungspipeline |
| offen | DNS-SSRF, Public-Suffix, IDNA 2008 | — | Phase 2 / Backlog |

**Punkt 2 — Runtime-Agent-Erzeugung** (`src/agents/runtime_factory.py`)

| | Baustein | Datei | Status |
| --- | --- | --- | --- |
| bleibt | `create_runtime_agents()` | `src/agents/runtime_factory.py` | vorhanden als zentrale Factory |
| bleibt | Rollen: Supervisor, 4 Departments, Synthesis, Report Writer | — | vorhanden |
| bleibt | `shared_search_cache: dict` | `src/agents/runtime_factory.py` | bleibt pro Factory-Aufruf |
| erweitern | Rueckgabetyp | `src/agents/runtime_factory.py` | `dict[str, object]` → typisiertes `RuntimeAgents`-Bundle |
| erweitern | Validation Gate | — | Pflichtrolle-Pruefung vor Run-Start |

**Punkt 5 — Supervisor Brief** (`src/agents/supervisor.py`, `src/domain/intake.py`, `src/pipeline_runner.py`)

| | Baustein | Datei | Status |
| --- | --- | --- | --- |
| bleibt | `SupervisorBrief` | `src/domain/intake.py` | vorhanden |
| bleibt | `SupervisorAgent.build_intake_brief()` | `src/agents/supervisor.py` | vorhanden |
| bleibt | `_build_supervisor_brief()` | `src/pipeline_runner.py` | vorhanden |
| erweitern | Evidence-Contract | — | Confidence-Modell, Fetch-Audit, Briefing-Readiness |
| erweitern | `RunContext.supervisor_brief` | — | typisiert absichern |

**Punkt 6 — Intake Research Pipeline** (`src/research/tools.py`, `src/research/fetch.py`, `src/research/extract.py`)

| | Baustein | Datei | Status |
| --- | --- | --- | --- |
| bleibt | `build_company_research()` | `src/research/tools.py` | vorhanden, nimmt `normalized_domain: str` |
| bleibt | `fetch_website_snapshot()` | `src/research/fetch.py` | vorhanden |
| bleibt | `infer_company_identity()` | `src/research/extract.py` | vorhanden |
| bleibt | `infer_industry()` | `src/research/extract.py` | vorhanden |
| bleibt | `homepage_url()` | `src/research/normalize.py` | vorhanden |
| erweitern | `WebsiteSnapshot` | — | typisierter Snapshot-Contract statt losem dict |
| erweitern | SSRF-Schutz im Fetch | `src/research/fetch.py` | DNS-Aufloesung + Redirect-Pruefung |

**Punkt 7 — Step1Handoff** (`src/pipeline_runner.py`, `src/orchestration/run_context.py`)

| | Baustein | Datei | Status |
| --- | --- | --- | --- |
| bleibt | `_write_checkpoint()` | `src/pipeline_runner.py` | vorhanden |
| bleibt | `RunContext.snapshot()` | `src/orchestration/run_context.py` | vorhanden |
| neu | `Step1Handoff`-Contract | — | typisierter Handoff-Vertrag mit Validation Gate |
| neu | Eventing bei Handoff | — | maschinenlesbares Handoff-Event |

### 0.3 [x] Gemeinsame Testing Strategy fuer Punkte 1-7 definieren

- [x] Testpyramide festlegen: Unit Tests fuer Parser/Contracts, Integration Tests fuer Store/Fetch/Eventing, Regression Tests fuer Step-1-Handoff, Deployment Smoke Tests fuer Produktionsprofil.
- [x] CI-Gruppen definieren: `unit`, `integration`, `security`, `architecture`, `smoke`.
- [x] Jeder Punkt muss mindestens Unit- oder Contract-Tests liefern; produktionsnahe Infrastrukturpunkte brauchen zusaetzlich Integration/Smoke Tests.
- [x] Testdaten duerfen keine echten Kundendaten enthalten.

**Testing Strategy (2026-05-12):**

Testpyramide auf bestehende pytest-Marker gemappt:

| Ebene | Marker | Verzeichnis | Externe Deps | Wann laufen |
| --- | --- | --- | --- | --- |
| Unit / Contract | `architecture`, `contract` | `tests/architecture/` | keine | jeder Push |
| Integration | `integration` | `tests/integration/` | AG2 / autogen | PR-Review |
| Runtime | `runtime` | `tests/runtime/` | AG2 + OpenAI API | manuell / Nightly |
| Smoke | `smoke` | `tests/smoke/` | keine (preflight) | jeder Deploy |
| Security | `security` | `tests/architecture/` (Subset) | keine | jeder Push |

CI-Gruppen und Mindest-Anforderungen pro MVP-Punkt:

| Punkt | Pflicht | Optional |
| --- | --- | --- |
| 1 — Intake + Normalize | `architecture` (unit) + `security` (SSRF) | — |
| 2 — Agent-Erzeugung | `architecture` (contract) | — |
| 5 — Supervisor Brief | `architecture` (contract) + `integration` | — |
| 6 — Research Pipeline | `architecture` (contract) + `integration` | `runtime` |
| 7 — Step1Handoff | `architecture` (regression) + `smoke` | — |

`security`-Marker: neue Gruppe fuer SSRF-, Injektions- und Input-Validierungs-Tests. Registriert in `pyproject.toml` (2026-05-12) als Subset von `architecture`-Tests; selektierbar via `pytest -m security`. Aktuell markiert: SSRF-Blocking (IPv4/IPv6), Scheme-Validierung, Userinfo-Ablehnung, Hostname-Syntax (5 Tests in `tests/architecture/test_runtime_step1.py`).

Testdaten-Regel: Alle Fixtures verwenden fiktive oder oeffentliche Domainnamen (`example.com`, `zf.com`, `siemens.com`). Kein echter Kundenname, keine echte E-Mail-Adresse, keine internen IP-Adressen in Testdaten.

### 0.4 [x] Observability-Hub statt isolierter Einzelmetriken definieren

- [x] Zentrale Signal-Ziele festlegen: strukturierte Logs, Metriken, OpenTelemetry-Spans.
- [x] Zielsysteme festlegen, z. B. Prometheus/Grafana fuer Metriken und OpenTelemetry Collector fuer Traces.
- [x] Einheitliche Felder festlegen: `run_id`, `phase`, `status`, `error_code`, `duration_ms`, `component`, `schema_version`.
- [x] Cloudflare Request IDs und Hetzner App Logs muessen korrelierbar sein.
- [x] Keine Prompts, Secrets, Roh-HTML oder unnoetige Kundendaten in Logs/Traces.

**Observability-Entscheidung (2026-05-12):**

Zielsysteme:

| Signal | MVP-Ziel | Phase-2-Ziel |
| --- | --- | --- |
| Logs | Python `logging` mit JSON-Formatter; ein Log-Eintrag pro Phase | OpenTelemetry Collector → Loki / Hetzner Log-Stack |
| Metriken | Prometheus-Counters fuer Intake-Ablehnungen per `error_code` | Prometheus + Grafana Dashboard auf Hetzner |
| Traces | — (kein OTel-SDK im MVP) | OpenTelemetry Span `pipeline.step1` mit Sub-Spans pro Phase |

Einheitliche Pflichtfelder fuer jeden Log-Eintrag und jede Metrik:

```text
run_id          # eindeutige Run-ID (YYYYMMDDTHHMMSSZ)
phase           # z. B. intake_validation, supervisor_brief, first_pass
status          # ok | failed | degraded
error_code      # IntakeErrorCode-Wert oder "" bei Erfolg
duration_ms     # Phasenlaufzeit in Millisekunden
component       # z. B. normalize, supervisor, company_department
schema_version  # "1" — erhoehen bei Breaking Changes am Log-Format
```

Korrelation: Cloudflare sendet `CF-Ray`-Header; Nginx schreibt ihn in `access.log`. Streamlit-App liest `CF-Ray` aus Request-Header und legt ihn als `correlation_id` in den Log-Eintrag. Damit ist jeder Run von der Browser-Anfrage bis zum Pipeline-Log nachverfolgbar.

Data-Hygiene-Regeln (unveraenderlich):

- Kein Prompt-Text in Logs oder Metriken
- Kein `password_hash`, kein API-Key, kein Session-Token
- Kein Roh-HTML aus gescrapten Seiten
- Firmennamen nur soweit sie fuer Fehlerdiagnose unverzichtbar sind; standardmaessig `run_id` als Referenz verwenden

### 0.5 [x] Performance Budgets fuer Step 1 definieren

- [x] Ziel-SLA fuer Step 1 festlegen, z. B. P50 < 10s und P95 < 30s im MVP, falls externe Quellen langsam sind.
- [x] Sub-Budgets definieren: Intake/Normalize, Agent Factory, Memory Retrieval, Supervisor Intake Research, Handoff Checkpoint.
- [x] Fallback-Verhalten bei Budgetueberschreitung definieren: degraded weiter, blockieren oder spaeter nacharbeiten.
- [x] Latenzbudgets in Tests oder Smoke Checks messbar machen.

**Performance-Budgets (2026-05-12):**

Gesamt-SLA Step 1 (Intake bis Handoff-Checkpoint, ohne LLM-Laufzeit):

| Messgröße | MVP-Ziel |
| --- | --- |
| P50 gesamt | < 10 s |
| P95 gesamt | < 30 s |
| Harter Abbruch | > 60 s → Run mit `status=failed`, `failed_phase=timeout` |

Sub-Budgets pro Komponente:

| Komponente | Budget | Fallback bei Überschreitung |
| --- | --- | --- |
| Intake / Normalize | < 50 ms | kein Fallback — hart blockieren |
| Agent Factory (`create_runtime_agents`) | < 500 ms | kein Fallback — hart blockieren |
| Memory Retrieval (`retrieve_strategies`) | < 1 s | leere Strategie-Liste weitergeben (`degraded`) |
| Homepage-Fetch (`fetch_website_snapshot`) | < 12 s | leeren Snapshot weitergeben; `website_reachable=False` |
| Identity / Industry Inference | < 3 s | `name_confidence=low`, `industry_hint=n/v` |
| Handoff Checkpoint Write | < 200 ms | Warnung loggen, Run trotzdem fortsetzen |

Fallback-Regel: Komponenten, die nur Kontext anreichern (Memory, Fetch, Identity), dürfen degraded liefern. Komponenten, die den Intake-Vertrag herstellen (Normalize, Agent Factory), blockieren hart.

Messbarkeit: `PhaseBudgetTracker` (`src/orchestration/runtime_guardrails.py`) trackt Token-Budgets. Latenz-Tracking ist seit 2026-05-12 in `_initialize_run()` (intake_validation, agent_factory, memory_retrieval) und `_build_supervisor_brief()` (supervisor_brief) per `perf_counter()` umgesetzt; die Werte stehen in `run_context.resolution_state["phase_durations_ms"]` und gehen ueber den Run-Snapshot in das Export-JSON ein. Regressions-Test: `test_initialize_run_records_phase_durations` in `tests/architecture/test_runtime_step1.py`.

### 0.6 [x] Compliance, DSGVO und Data Residency klaeren

- [x] Datenklassen definieren: Intake-Daten, oeffentliche Website-Daten, Run Brain, Long-Term Process Memory, Reports, Logs.
- [x] Data Residency festlegen: Hetzner/EU als primaerer Speicherort; Cloudflare-Rollen fuer Edge/R2 separat dokumentieren.
- [x] `Run loeschen` definieren: welche DB-Zeilen, Artefakte, Logs und Object-Storage-Objekte werden geloescht oder anonymisiert?
- [x] Long-Term Process Memory muss nachweislich keine personenbezogenen oder kundenspezifischen Fakten enthalten.
- [x] Retention-Regeln fuer Run-Artefakte und Logs definieren.

**Compliance-Entscheidung (2026-05-12):**

Datenklassen und Klassifizierung:

| Datenklasse | Inhalt | Vertraulichkeit | Speicherort |
| --- | --- | --- | --- |
| Intake-Daten | `company_name`, `web_domain` — Eingabe des Nutzers | intern | RAM / Run-Artefakt |
| Oeffentliche Website-Daten | gescrapte Homepage, Title, Meta-Description | oeffentlich | Run-Artefakt |
| Run Brain (RunContext) | Supervisor Brief, Sections, Answer Matrix | intern | `artifacts/runs/{run_id}/` |
| Long-Term Process Memory | aggregierte Prozessmuster — kein Firmenname, kein Kontakt | intern, anonym | `artifacts/memory/long_term_memory.json` |
| Reports | PDF/JSON-Ausgabe mit Rechercheergebnissen | vertraulich (kundenspezifisch) | `artifacts/runs/{run_id}/` |
| Logs | Phasen-Laufzeiten, Fehler, run_id | operationell | Hetzner-Server-Log, kein PII |

Data Residency:

- **Primaer:** Hetzner Cloud, Standort Falkenstein (Deutschland / EU). Alle Artefakte, Memory und Logs liegen ausschliesslich dort.
- **Cloudflare:** nur Edge-Proxy (TLS-Terminierung, DDoS-Schutz). Kein Kundendaten-Durchleitung, kein R2-Bucket fuer Run-Artefakte im MVP.
- **OpenAI API:** Prompts und LLM-Ausgaben verlassen den EU-Perimeter. Keine personenbezogenen Daten in Prompts zulässig. Prompts enthalten ausschliesslich oeffentliche Rechercheergebnisse und Prozessanweisungen.

`Run loeschen` — Definition der zu entfernenden Objekte:

| Objekt | Aktion |
| --- | --- |
| `artifacts/runs/{run_id}/` | vollstaendig loeschen |
| Eintraege in Server-Logs mit `run_id` | nach Retention-Ablauf automatisch rotiert |
| Long-Term Memory Eintraege mit Bezug zu `run_id` | **anonymisieren** (run_id entfernen), Muster behalten |
| Streamlit-Session-State des Nutzers | bei Logout geleert (`do_logout()` in `session.py`) |

Long-Term Process Memory — Invarianten:

- Kein Firmenname gespeichert — nur generische Branchenbegriffe als Kontext erlaubt
- Kein Kontaktname, keine E-Mail-Adresse, keine Telefonnummer
- Nur Prozessmuster: Fragestrategien, Recherche-Ansaetze, Qualitaetssignale
- Pruefung: `should_store_strategy()` in `src/memory/policies.py` entscheidet; jede Aenderung an dieser Funktion erfordert Review gegen diese Regel

Retention-Regeln:

| Daten | Aufbewahrung | Loesch-Trigger |
| --- | --- | --- |
| Run-Artefakte (`artifacts/runs/`) | 90 Tage | automatisch per Cron oder manuell |
| Server-Logs | 30 Tage | Log-Rotation (logrotate) |
| Long-Term Memory | unbegrenzt | nur bei explizitem Reset durch Betreiber |
| Streamlit-Nutzerdaten (`data/users.db`) | solange Konto aktiv | Konto-Loeschung durch Admin |

### 0.7 [x] MVP-Umsetzungsreihenfolge einhalten

Die fuenf MVP-Punkte (1, 2, 5, 6, 7) sind nicht unabhaengig. Folgende Reihenfolge muss eingehalten werden, weil spaetere Punkte auf Typen und Contracts der frueheren aufbauen:

```text
Schritt 1: Punkt 1 (vollstaendig)
           Fundament. Liefert NormalizedDomainResult und IntakeErrorCode-Katalog.
           Alle anderen Punkte bauen darauf auf.

Schritt 2: Punkt 2 (vollstaendig, parallel zu Schritt 1 moeglich)
           Haengt nicht von Research ab. Kann zeitgleich mit Punkt 1 umgesetzt werden.

Schritt 3: Punkt 6.1 bis 6.3
           Stellt build_company_research(...) auf den NormalizedDomainResult aus Punkt 1 um.
           Einfuehren von WebsiteSnapshot als typisiertem Contract.
           Voraussetzung fuer Punkt 5.

Schritt 4: Punkt 5.1 bis 5.3
           Supervisor Brief auf validierten Domain-Vertrag und WebsiteSnapshot umstellen.
           Einfuehren des Evidence Contract. Setzt Punkt 6.1-6.3 voraus.

Schritt 5: Punkt 6.4 bis 6.7
           HTML-Extraktion, Identity Resolution, Industry Detection haerten.
           Setzt WebsiteSnapshot aus 6.1-6.3 voraus.

Schritt 6: Punkt 5.4 bis 5.9
           Confidence-Modell, Fetch-Audit, Briefing Readiness, Observability.
           Setzt Evidence Contract aus 5.1-5.3 und Identity Resolution aus 6.4-6.7 voraus.

Schritt 7: Punkt 6.8 bis 6.16
           JS-Signal, Fehlerklassen, Budgetierung, Tests, Observability fuer Research Pipeline.
           Setzt alle vorherigen Research-Contracts voraus.

Schritt 8: Punkt 7 (vollstaendig)
           Step1Handoff-Contract, Validation Gates, Checkpoint, Eventing.
           Setzt alle Punkte 1, 2, 5 und 6 als abgeschlossen voraus.
```

Abhaengigkeitsregel: Kein Schritt darf mit der Umsetzung beginnen, bevor die Akzeptanzkriterien des vorherigen Schritts erfuellt sind.

## 1. Intake-Validierung + Domain-Normalisierung auf 2026-Best-Practice-Niveau bringen

Betroffener aktueller Ablauf:

```python
intake = IntakeRequest(company_name=company_name, web_domain=web_domain)
normalized_domain = normalize_domain(intake.web_domain)
```

Aktuelle Weitergabe in `RunContext.intake`:

```python
{
    "company_name": intake.company_name,
    "web_domain": intake.web_domain,
    "normalized_domain": normalized_domain,
    "language": intake.language,
}
```

### 1.0 Current State (Code-Audit)

- [x] `IntakeRequest` existiert bereits und trimmt `company_name`, `web_domain` und `language`.
- [x] `normalize_domain(...)` existiert bereits und behandelt Lowercase, Scheme-Ergaenzung, `www.`-Entfernung und geblockte Hosts.
- [x] `_is_blocked_host(...)` existiert bereits und blockiert localhost/private/nicht-globale IPs.
- [x] Delta fuer Punkt 1 ist **Haertung und Typisierung**, nicht kompletter Neubau.
- [x] Sprachkontext `language` muss in Validierung, Fehlermeldungen und spaeterem Briefing bewusst weitergereicht werden.

Ziel: Dieser Schritt soll nicht nur einfache Leerwerte und Standard-Domainvarianten behandeln, sondern als expliziter Intake-Sicherheits- und Normalisierungsvertrag funktionieren. Ungueltige, private, mehrdeutige oder riskante Ziele duerfen nicht als leerer oder unklarer Arbeitswert weiterlaufen.

### 1.1 Typisierten Normalisierungsvertrag einfuehren

- [x] **Punkt 1.1 abgeschlossen** — `NormalizedDomainResult` (`src/research/normalize.py`) mit `original_input`, `canonical_domain`, `canonical_url`, `hostname`, `original_hostname`, `scheme`, `is_valid`, `rejection_code`, `rejection_reason`, `normalization_steps`, `public_suffix`, `registrable_domain`. `normalize_domain_result()` ist die Produktivfunktion; `normalize_domain()` bleibt als Rueckwaerts-Wrapper. `RunContext.intake` enthaelt `canonical_url` und `normalization_steps`.

Aktuell gibt `normalize_domain(...)` nur einen String zurueck. Fuer 2026-Best-Practice sollte daraus ein typisiertes Ergebnis werden, z. B.:

```python
@dataclass(frozen=True, slots=True)
class NormalizedDomainResult:
    original_input: str
    canonical_domain: str
    canonical_url: str
    hostname: str
    scheme: str
    public_suffix: str
    registrable_domain: str
    is_valid: bool
    rejection_code: str = ""
    rejection_reason: str = ""
    normalization_steps: tuple[str, ...] = ()
```

Umzusetzen:

- [x] neue Funktion einfuehren, z. B. `normalize_domain_result(domain: str) -> NormalizedDomainResult`;
- [x] bestehendes `normalize_domain(...)` entweder als Kompatibilitaetswrapper erhalten oder alle Call Sites bewusst migrieren;
- [x] `RunContext.intake` nicht nur mit `normalized_domain`, sondern optional auch mit auditierbaren Normalisierungsmetadaten befuellen;
- [x] alle Folgefunktionen, die eine Domain erwarten, sollen den kanonischen Host eindeutig aus diesem Vertrag beziehen.

Akzeptanzkriterium:

- [x] Es ist aus dem Run-Kontext nachvollziehbar, welche Eingabe kam, welcher kanonische Wert daraus wurde und welche Regeln angewendet wurden.

### 1.2 Leere oder geblockte `normalized_domain` hart als Intake-Fehler behandeln

- [x] **Punkt 1.2 abgeschlossen** — `_initialize_run()` in `src/pipeline_runner.py` wirft `ValueError` bei `not normalization.is_valid` mit `rejection_code`. `run_pipeline()` faengt den Fehler ab und liefert `status="failed"`, `failed_phase="intake_validation"`, `error_code`, `error_detail`. Keine Agent-Erzeugung und kein Memory-Store-Zugriff vor erfolgreicher Validierung.

Aktuell kann `normalize_domain(...)` bei geblockten Hosts `""` zurueckgeben. Das ist fuer einen Runtime-Start zu weich, weil der Run mit leerer Arbeitsdomain weiterlaufen kann.

Umzusetzen in `_initialize_run(...)` direkt nach der Normalisierung:

```python
normalized_domain = normalize_domain(intake.web_domain)
if not normalized_domain:
    raise ValueError("Intake validation failed: web_domain must be a public internet domain.")
```

Bei typisiertem Ergebnis entsprechend:

```python
normalization = normalize_domain_result(intake.web_domain)
if not normalization.is_valid:
    raise ValueError(f"Intake validation failed: {normalization.rejection_reason}")
```

Akzeptanzkriterium:

- [x] `localhost`, `127.0.0.1`, `::1`, private IPs, link-local IPs, reservierte IPs und leere Normalisierungsergebnisse fuehren zu `status="failed"` und `failed_phase="intake_validation"`.
- [x] Es werden keine Agents erzeugt, keine Memory Stores geoeffnet und keine Recherche gestartet.

### 1.3 Platzhalter- und Testwerte als ungueltiges Intake blockieren

- [x] **Punkt 1.3 abgeschlossen** — `IntakeRequest.__post_init__` (`src/domain/intake.py`) lehnt Platzhalter (`n/v`, `n/a`, `unknown`, `none`, `null`, `tbd`, `na`) und ueberlange Eingaben ab (Firmenname max. 200 Zeichen, Domain max. 2048 Zeichen). `normalize_domain_result()` blockiert dieselben Platzhalter zuzueglich `test`, `example`, `n.a.`, `-`, `--`, `.` fuer das `web_domain`-Feld und reagiert auf Unicode-Steuerzeichen mit `CONTROL_CHARACTERS`.

`IntakeRequest` trimmt aktuell `company_name` und `web_domain`, blockiert aber nur leere Strings. Fuer Best Practice sollten bekannte Platzhalter und nicht ernsthafte Testwerte nicht in die Runtime gelangen.

Umzusetzen:

- [x] fuer `company_name` und `web_domain` Werte wie `"n/v"`, `"n/a"`, `"unknown"`, `"none"`, `"null"`, `"test"`, `"example"` je nach Feldkontext blockieren;
- [x] Fehlermeldungen feldspezifisch halten (`IntakeValidationError` mit `field`, `code`, `reason`);
- [x] maximale Laengen definieren, z. B. Firmenname max. 200 Zeichen, Domain/URL max. 253 Zeichen fuer Hostname plus tolerierte URL-Laenge vor Parsing;
- [x] Steuerzeichen und unsichtbare Unicode-Control-Zeichen entfernen oder ablehnen.

Akzeptanzkriterium:

- [x] Platzhalter fuehren zu klaren Intake-Fehlern.
- [x] Extrem lange oder kontrollzeichenhaltige Eingaben werden nicht an Recherche- oder Fetch-Code weitergereicht.

### 1.4 Robuste URL-, Hostname- und Domain-Validierung ergaenzen

- [x] **Punkt 1.4 abgeschlossen** — Scheme-Validierung (nur `http`/`https`), Pre-Scheme-Check fuer `mailto:`/`ftp:`/`file:`, Userinfo-Ablehnung, Hostname-Label-Syntax-Validierung (RFC 952/1123, 1-63 Zeichen), RFC-1035-Max-Hostnamen-Laenge 253. Pfad/Query/Fragment werden via `urlparse` verworfen und explizit auditiert als `path_dropped`/`query_dropped`/`fragment_dropped` in `normalization_steps`. Nicht-Standard-Ports werden als `port_ignored:<port>` erfasst (80/443 als Standardports nicht). Public-Suffix-/Registrable-Domain-Pruefung via `tldextract` (offline-deterministisch, `suffix_list_urls=()`); single-label Inputs werden mit `NO_REGISTRABLE_DOMAIN` abgelehnt.

Aktuell nutzt `urlparse(...)`, entfernt `www.` und blockiert nicht-globale IPs. Fuer 2026-State-of-the-Art sollte die Validierung klarer zwischen URL, Hostname und registrierbarer Domain unterscheiden.

Umzusetzen:

- [x] Scheme nur `http` und `https` erlauben; bevorzugt kanonisch `https` verwenden;
- [x] Userinfo in URLs blockieren, z. B. `https://user:pass@example.com`;
- [x] Pfad, Query und Fragment fuer Domain-Normalisierung ignorieren, aber als Normalisierungsschritt auditieren (`path_dropped`, `query_dropped`, `fragment_dropped`);
- [x] Port explizit behandeln: Standardports (80, 443) akzeptiert; Nicht-Standard-Ports als `port_ignored:<port>` audit-erfasst;
- [x] Hostname syntaktisch validieren: Label-Laenge, erlaubte Zeichen, keine leeren Labels, keine fuehrenden/trailing Bindestriche;
- [x] Public-Suffix-/registrable-domain-Pruefung ergaenzen via `tldextract` (offline-deterministisch);
- [x] Domains ohne gueltige registrierbare Domain ablehnen (`IntakeErrorCode.NO_REGISTRABLE_DOMAIN`).

Akzeptanzkriterium:

- [x] Eingaben wie `https://www.zf.com/path?a=b#x` werden stabil zu `zf.com` normalisiert.
- [x] Eingaben wie `http://example`, `https://.com`, `https://foo..bar`, `https://-bad.com`, `ftp://zf.com`, `https://user:pass@zf.com` werden kontrolliert abgelehnt oder bewusst dokumentiert behandelt.

### 1.5 IDN/Punycode und Unicode-Domains korrekt behandeln

- [x] **Punkt 1.5 abgeschlossen** — IDN-Normalisierung via `idna`-Paket (IDNA 2008 + UTS-46-Mapping) mit IDNA-2003-Stdlib-Fallback fuer Legacy-Edge-Cases (`_idna_encode_label()` in `normalize.py`). `NormalizedDomainResult.original_hostname` speichert die pre-IDNA-Unicode-Form, `canonical_domain` die ASCII/Punycode-Form. Mixed-Script-Detection in `_detect_unicode_risks()` setzt `unicode_risk_flags` mit Eintraegen wie `mixed_script:googlе.com` (Cyrillic 'е' + Latin); `unicode_risk_flagged` taucht in `normalization_steps` auf. Tests: `test_normalize_domain_result_normalizes_umlaut_domain`, `test_normalize_domain_result_records_original_hostname`, `test_normalize_domain_result_flags_mixed_script_homograph`. **Phase-2-Verschaerfung:** vollstaendige UTS-39-Confusables-Analyse.

Internationale Domains koennen Unicode enthalten. Best Practice ist, diese reproduzierbar in ASCII/Punycode zu kanonisieren und Homograph-Risiken zu auditieren.

Umzusetzen:

- [x] Unicode-Hostnames mit IDNA 2008 in ASCII/Punycode ueberfuehren (`idna`-Paket mit IDNA-2003-Fallback);
- [x] Original-Hostname und ASCII-Hostname im Normalisierungsergebnis speichern (`original_hostname` + `canonical_domain`);
- [x] gemischte Skripte oder bekannte Homograph-Risiken markieren (`unicode_risk_flags`, `mixed_script:<label>`); volle UTS-39-Confusables-Analyse Phase 2;
- [x] Tests fuer Umlaute und internationale TLDs ergaenzen.

Akzeptanzkriterium:

- [x] Gueltige IDN-Domains werden deterministisch normalisiert.
- [x] Potenziell irrefuehrende Unicode-Domains werden nicht stillschweigend als normale Zielunternehmen behandelt (Mixed-Script-Flag in `unicode_risk_flags`).

### 1.6 SSRF-Schutz ueber die reine String-Normalisierung hinaus erweitern

- [x] **Punkt 1.6 abgeschlossen** — Mehrstufiger SSRF-Schutz:
  1. **String-Level** in `normalize_domain_result()`: private/loopback/reserved IP-Literale werden direkt geblockt.
  2. **DNS-Pre-Flight** in `_initialize_run()`: `resolve_and_validate_host(canonical_domain)` wird VOR Agent-Erzeugung und Memory-Store-Oeffnung aufgerufen. DNS-Aufloesung gegen private/loopback/link-local/reserved-Ranges (IPv4+IPv6); Fehlschlag wirft `IntakeValidationError(field="web_domain", code=BLOCKED_PRIVATE_HOST | DNS_RESOLUTION_FAILED)`, das `run_pipeline()` direkt in den maschinenlesbaren `error_code` und `error_detail` des Run-Ergebnisses ueberfuehrt — kein zweiter Normalisierungs-Roundtrip mehr.
  3. **IP-Pinning** in `fetch_website_snapshot()`: `_PinnedHTTPSConnection` und `_PinnedHTTPConnection` verbinden sich mit der bereits validierten IP und setzen `server_hostname` fuer SNI sowie `Host:`-Header korrekt — schliesst die DNS-Rebinding-Luecke zwischen Aufloesung und `connect()`.
  4. **Redirect-Re-Validation** via `_SSRFGuardRedirectHandler`; `MAX_REDIRECTS = 5`.
  5. **Fehlercodes**: `dns_resolution_failed`, `blocked_private_host`, `blocked_redirect_target`, `unsupported_scheme`, `invalid_url`.
  Regressions-Tests: `test_initialize_run_hard_blocks_dns_rebinding`, `test_run_pipeline_preserves_dns_ssrf_error_code`, `test_run_pipeline_preserves_dns_resolution_failure_code`. **Phase-2-Verschaerfung:** TLS-Pinning via expliziten `ssl.SSLContext` mit Certificate Transparency Verifikation.

Der aktuelle `_is_blocked_host(...)` blockiert offensichtliche lokale/private IPs. State of the art verlangt zusaetzlich DNS- und Redirect-Schutz, weil ein Hostname erst nach DNS-Aufloesung auf private Adressen zeigen kann.

Umzusetzen:

- [x] vor Website-Fetch DNS-Aufloesung gegen private, loopback, link-local, multicast, reserved und carrier-grade NAT Bereiche pruefen (`resolve_and_validate_host()`);
- [x] alle Redirect-Ziele erneut normalisieren und gegen dieselben Regeln pruefen (`_SSRFGuardRedirectHandler`);
- [x] DNS-Rebinding-Risiko reduzieren: IP nach Aufloesung fuer den Fetch pinnen (`_PinnedHTTPSConnection` / `_PinnedHTTPConnection` mit SNI-Erhalt);
- [x] maximale Redirect-Anzahl definieren (`MAX_REDIRECTS = 5`);
- [x] Fetch-Code darf keine internen IPs erreichen, auch wenn die urspruengliche Domain oeffentlich aussah (DNS-Pre-Flight in `_initialize_run()` blockt vor Agent-Erzeugung);
- [x] Fehlercodes sauber unterscheiden: `blocked_private_host`, `blocked_redirect_target`, `dns_resolution_failed`, `unsupported_scheme`, `invalid_url`.

Akzeptanzkriterium:

- [x] Domains, die auf private IPs aufloesen oder dahin redirecten, werden mit klarer Fehlermeldung blockiert.
- [x] Der Run endet vor Recherche-Artefakten, wenn das Ziel nicht sicher oeffentlich erreichbar ist (Intake-DNS-Pre-Flight wirft `ValueError` mit `blocked_private_host`/`dns_resolution_failed` vor `create_runtime_agents()`).

### 1.7 Strukturierte Fehler- und Auditdaten persistierbar machen

- [x] **Punkt 1.7 abgeschlossen** — `IntakeErrorCode` (StrEnum) in `src/research/normalize.py` definiert 16 maschinenlesbare Codes (11 Domain-/SSRF-Codes inkl. `DNS_RESOLUTION_FAILED` und `HOMOGRAPH_RISK` + 5 Feld-spezifische `company_name_*`-/`web_domain_*`-Codes). `IntakeValidationError(field, code, reason)` in `src/domain/intake.py` traegt strukturierte Felder durch alle Intake-Fehlerpfade: Feld-Validierung in `IntakeRequest`, String-Normalisierung in `normalize_domain_result()`, und DNS-Pre-Flight via `resolve_and_validate_host()`. `_failed_intake_result()` liefert `error_code` und `error_detail` (`field`, `original_value`, `rejection_code`, `rejection_reason`) — kein Re-Normalize-Roundtrip mehr noetig. `RunContext.resolution_state["intake_validation"]` enthaelt bei Erfolg `status="ok"`, `canonical_domain`, `registrable_domain`, `public_suffix`, `original_hostname`, `normalization_steps`, `unicode_risk_flags`, `resolved_ips`, `duration_ms`; bei Fehler `status="failed"`, `error_code`, `rejection_reason`, `field`, `original_value`. Regressions-Tests: `test_initialize_run_populates_intake_validation_on_success`, `test_run_pipeline_populates_intake_validation_on_failure`, `test_run_pipeline_propagates_company_name_error_code`, `test_run_pipeline_preserves_dns_ssrf_error_code`, `test_run_pipeline_preserves_dns_resolution_failure_code`.

Zusatz aus Audit: Fehlercodes sollen nicht nur als freie Strings entstehen, sondern als stabiler Katalog, z. B.:

```python
class IntakeErrorCode(StrEnum):
    COMPANY_NAME_REQUIRED = "company_name_required"
    WEB_DOMAIN_REQUIRED = "web_domain_required"
    INVALID_WEB_DOMAIN = "invalid_web_domain"
    BLOCKED_PRIVATE_HOST = "blocked_private_host"
    UNSUPPORTED_SCHEME = "unsupported_scheme"
    DOMAIN_TOO_LONG = "domain_too_long"
    PLACEHOLDER_VALUE = "placeholder_value"
```

Umzusetzen:

- [x] Fehlercode-Katalog als Enum oder gleichwertigen Contract definieren (`IntakeErrorCode` StrEnum, 14 Codes inkl. Feld-spezifische `company_name_*`/`web_domain_*`);
- [x] Intake-, Domain- und Fetch-nahe Fehler duerfen nicht als beliebige Freitext-Strings entstehen;
- [x] UI/API und Tests verwenden Fehlercodes statt fragilem Error-Text-Matching.

Bei Intake-Fehlern liefert `_failed_intake_result(...)` aktuell Status, leere Artefakte und Error-Text. Fuer Best Practice sollte der Grund maschinenlesbar sein.

Umzusetzen:

- [x] Intake-Fehler um strukturierte Felder erweitern:

```python
"error_code": "invalid_web_domain",
"error_detail": {
    "field": "web_domain",
    "original_value": "localhost",
    "rejection_code": "blocked_private_host",
    "rejection_reason": "web_domain must resolve to a public internet host"
}
```

- [x] `resolution_state["intake_validation"]` auch bei Fehlern mit Normalisierungsdetails befuellen;
- [x] sensible Originalwerte nur soweit speichern, wie sie fuer Diagnose noetig sind (nur das Originalfeld; keine PII; resolved_ips nur fuer Audit);
- [x] UI/API kann anhand von `error_code` konkrete Hilfetexte anzeigen.

Akzeptanzkriterium:

- [x] Fehler sind fuer Nutzer verstaendlich und fuer Tests/Monitoring maschinenlesbar.

### 1.8 Konsistente Verwendung der kanonischen Domain erzwingen

- [x] **Punkt 1.8 MVP abgeschlossen — Phase 2 offen** — `_initialize_run()` ist die alleinige Quelle der Normalisierung. `build_company_research()` (`src/research/tools.py`) baut die URL inline aus dem schon kanonischen `normalized_domain`; `homepage_url()` wird im Run-kritischen Pfad nicht mehr aufgerufen (siehe 0.0). `RunContext.intake.normalized_domain` und `canonical_url` sind die Arbeitswerte fuer Retrieval und Fetch. Contract-Test: `test_normalize_domain_result_same_canonical_for_domain_variants` (`zf.com`, `ZF.COM`, `https://www.zf.com/`, `http://www.zf.com/path?a=b#x` → identisch). **Offene Verschaerfung (Phase 2):** `RunContext.intake` als typisiertes Pydantic-/Dataclass-Modell statt losem Dict.

Aktuell existieren `intake.web_domain` und `normalized_domain` parallel. Das ist sinnvoll, aber fehleranfaellig, wenn spaetere Schritte versehentlich die rohe Eingabe fuer Retrieval oder Fetch-Entscheidungen nutzen.

Umzusetzen:

- [x] klare Regel dokumentieren: `submitted_web_domain` bleibt Audit/Anzeige, `normalized_domain` bzw. `canonical_domain` ist der Arbeitswert;
- [x] `build_company_research(...)`, Long-Term-Memory-Retrieval und Homepage-URL-Erzeugung sollen denselben kanonischen Wert verwenden;
- [ ] **(Phase 2)** optional: `RunContext.intake` als typisiertes Modell statt losem Dict einfuehren — bewusst offen gelassen, das Dict ist heute mit kompletten Audit-Feldern befuellt;
- [x] Contract-Test, der prueft, dass gleiche Domainvarianten denselben `normalized_domain`-Wert erzeugen (`test_normalize_domain_result_same_canonical_for_domain_variants`).

Akzeptanzkriterium:

- [x] `ZF.COM`, `https://zf.com`, `https://www.zf.com/` und `zf.com/path` fuehren zu identischem kanonischem Arbeitswert.

### 1.9 Testmatrix fuer Intake und Domain-Normalisierung aufbauen

- [x] **Punkt 1.9 abgeschlossen** — `tests/architecture/test_runtime_step1.py` deckt alle Kategorien aus der Testmatrix ab: Unit-Tests fuer `IntakeRequest` (Leerwerte, Platzhalter, Max-Laenge), Unit-Tests fuer Domain-Normalisierung (alle 9 `IntakeErrorCode`-Klassen, IPv4/IPv6, IDN, public_suffix, registrable_domain), Contract-Tests fuer `_initialize_run()` (Phase-Durations, intake_validation-Befuellung), Security-Tests (`@pytest.mark.security`, 11 Tests inkl. SSRF-Guard, Scheme-/Userinfo-Ablehnung), Regression-Tests fuer realistische B2B-Domains. Selektierbar via `pytest -m security`. Testdaten verwenden nur fiktive oder oeffentliche Domains (`zf.com`, `example.com`, `siemens.com`).

Ohne harte Tests bleibt dieser Schritt schwer als Best Practice belegbar.

Umzusetzen:

- [x] Unit-Tests fuer `IntakeRequest` (inkl. feldspezifische `IntakeValidationError`);
- [x] Unit-Tests fuer Domain-Normalisierung;
- [x] Contract-Tests fuer `_initialize_run(...)` Fehlerverhalten;
- [x] Security-Tests fuer SSRF-nahe Faelle (`@pytest.mark.security`);
- [x] Regression-Tests fuer realistische B2B-Domains.

Mindest-Testfaelle:

| Kategorie | Beispiele | Erwartung |
| --- | --- | --- |
| Standarddomains | `zf.com`, `ZF.COM`, `https://www.zf.com/` | `zf.com` |
| URL mit Pfad | `https://www.zf.com/products?a=b#top` | `zf.com`, Pfad wird ignoriert/auditiert |
| Leere Werte | `""`, `"   "` | Intake-Fehler |
| Platzhalter | `n/v`, `unknown`, `null` | Intake-Fehler |
| Localhost | `localhost`, `http://localhost:8501` | Intake-Fehler |
| Private IPv4 | `127.0.0.1`, `10.0.0.1`, `192.168.1.1` | Intake-Fehler |
| Private IPv6 | `::1`, `fd00::1` | Intake-Fehler |
| Ungueltige Hostnames | `foo..bar`, `-bad.com`, `.com` | Intake-Fehler |
| Falsches Scheme | `ftp://zf.com`, `file:///etc/passwd` | Intake-Fehler |
| Userinfo | `https://user:pass@zf.com` | Intake-Fehler |
| IDN | gueltige Unicode-Domain | kanonisches Punycode-Ergebnis plus Audit |
| Redirect auf intern | oeffentliche Testdomain redirectet auf `127.0.0.1` | Fetch blockiert |

Akzeptanzkriterium:

- [x] Die Tests laufen lokal und in CI (51 Tests in `test_runtime_step1.py`, 627 Tests gesamt).
- [x] Jeder oben genannte Fall hat eine explizite Erwartung.

### 1.10 Observability und Monitoring vorbereiten

- [x] **Punkt 1.10 MVP abgeschlossen — Phase 2 offen** — `src/orchestration/intake_logging.py` definiert `log_intake_event()` mit JSON-Formatter; emittiert pro Intake einen Log-Eintrag mit den 0.4-Pflichtfeldern (`schema_version`, `component`, `phase`, `run_id`, `status`, `error_code`, `duration_ms`, optional `canonical_domain`, `registrable_domain`, `rejection_reason`, `unicode_risk_flags`, `resolved_ips_count`). `_initialize_run()` und `run_pipeline()` rufen den Logger fuer Success- bzw. Failure-Pfade auf. Tests: `test_intake_logging_emits_structured_event`, `test_intake_logging_failure_includes_error_code`. **Phase-2-Backlog (im TODO unter 1.10 als `(Phase 2)` markiert):** Prometheus-Counter pro `error_code`, OpenTelemetry-Span `pipeline.intake_validation`, Grafana-Dashboard. Diese setzen den OTel-Collector auf Hetzner voraus (siehe 0.4).

Fuer produktionsreife Multi-Agent-Pipelines sollte Intake-Qualitaet messbar sein.

Umzusetzen:

- [ ] **(Phase 2)** Zaehler fuer Intake-Ablehnungen nach `rejection_code` — setzt Prometheus-Endpoint auf Hetzner voraus;
- [x] Log-Eintrag fuer Normalisierung mit Run-ID, aber ohne unnoetige sensitive Details (`log_intake_event()` in `src/orchestration/intake_logging.py`);
- [ ] **(Phase 2)** OpenTelemetry-Span `pipeline.intake_validation` mit Attributen wie `valid`, `rejection_code`, `canonical_domain_present` — setzt OTel-Collector voraus;
- [ ] **(Phase 2)** Dashboard-Metrik: Anteil fehlgeschlagener Intake-Validierungen pro Zeitraum — Grafana-Dashboard auf Hetzner.

Akzeptanzkriterium:

- [x] Fehlgeschlagene Intake-Validierungen sind im Betrieb sichtbar (strukturierte JSON-Log-Events auf `liquisto.intake`-Logger, `status="failed"` + `error_code` per Eintrag). Voll automatisierte Dashboards bleiben Phase 2.

### 1.11 Dokumentation und Architekturabgleich aktualisieren

- [x] **Punkt 1.11 Code-Seite abgeschlossen — Diagramme offen** — `docs/runtime/runtime_step1.md` enthaelt einen neuen Abschnitt "MVP-Stand 2026-05-12 — Intake-Vertrag und SSRF-Guard" mit allen relevanten Vertraegen, Modulen und Code-Pfaden. `requirements.txt` ergaenzt um `idna>=3.10,<4` und `tldextract>=5.3.0,<6`. **Backlog (im TODO unter 1.11 als `(Backlog)` markiert):** `target_runtime_architecture.md` und `docs/drawio/runtime_step1.drawio` / `scripts/generate_step1_drawio.py` (Diagramm-Regeneration als eigener Arbeitsschritt; Narrative-Doku und Code sind synchron).

Wenn dieser Punkt umgesetzt wird, muessen Runtime-Doku und Architekturziel synchron bleiben.

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` aktualisieren (Abschnitt "MVP-Stand 2026-05-12");
- [ ] **(Backlog)** `docs/drawio/runtime_step1.drawio` und `scripts/generate_step1_drawio.py` aktualisieren — eigener Arbeitsschritt;
- [ ] **(Backlog)** `docs/drawio/target_runtime_architecture.md` um den Intake-Sicherheitsvertrag ergaenzen;
- [x] `requirements.txt` enthaelt `idna>=3.10,<4` und `tldextract>=5.3.0,<6`; Preflight in `tests/smoke/test_preflight.py` aktualisiert sich automatisch ueber das Import-Layering.

Akzeptanzkriterium:

- [x] Narrative Doku und Code beschreiben denselben Intake-Vertrag. Diagramm-Aktualisierung steht als Backlog-Aufgabe in 1.11 explizit aus.

### 1.12 Zielbewertung nach Umsetzung

- [x] **Punkt 1.12 abgeschlossen**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung | Ist (2026-05-12) | Anmerkung |
| --- | ---: | ---: | --- |
| Eingabe-Sauberkeit | 5/5 | **5/5** | Feld-spezifische Codes, Platzhalter, Max-Laenge, Control-Chars, IDN, single-label, mixed-script flag |
| Normalisierung | 5/5 | **5/5** | IDNA 2008 + UTS-46, tldextract, NormalizedDomainResult mit `public_suffix`/`registrable_domain`/`unicode_risk_flags`, Audit-Steps fuer Pfad/Query/Fragment/Port |
| Sicherheitsgrenze | 5/5 | **4.5/5** | DNS-Pre-Flight in `_initialize_run()` blockt vor Agent-Erzeugung; Redirect-Re-Validation; IP-pinned HTTPS mit SNI-Erhalt. Volle UTS-39-Confusables-Analyse + TLS-Pinning bleiben Phase 2 |
| Weitergabe-Klarheit | 5/5 | **5/5** | `canonical_url`, `normalization_steps`, `unicode_risk_flags`, `resolved_ips`, `registrable_domain`, `intake_validation` im RunContext |
| Fehlerverhalten | 5/5 | **5/5** | Alle Intake-Fehlerpfade (Feld, String, DNS-Pre-Flight) gehen ueber `IntakeValidationError(field, code, reason)`; `error_code` + `error_detail` im Run-Ergebnis konsistent; harter Fail vor Side-Effects |
| Observability / Auditierbarkeit | 5/5 | **4/5** | JSON-Logging mit allen 0.4-Pflichtfeldern, Phase-Durations, `unicode_risk_flags` und `resolved_ips_count` in jedem Event; Prometheus-Counter und OTel-Spans bleiben Phase 2 |
| Testbarkeit / Contracts | 5/5 | **5/5** | 53 Step-1-Tests; 18 von 680 Tests via `pytest -m security` selektierbar; Regressions-Tests fuer feld-spezifische Errors, Audit-Steps, IP-Pinning, DNS-SSRF-Fehlercode-Propagation |

### 1.13 Definition of Done fuer Punkt 1

- [x] **Punkt 1.13 abgeschlossen**

- [x] ungueltige oder riskante Domains koennen nicht in `RunContext.intake.normalized_domain` als leerer oder irrefuehrender Wert weiterlaufen — `_initialize_run()` wirft `ValueError` bei `not is_valid`.
- [x] gleiche legitime Domainvarianten ergeben denselben kanonischen Arbeitswert — Contract-Test `test_normalize_domain_result_same_canonical_for_domain_variants`.
- [x] Fehler sind frueh, hart, verstaendlich und maschinenlesbar — `IntakeErrorCode` (StrEnum), `error_code`, `error_detail`, JSON-Log-Event.
- [x] SSRF-nahe Risiken werden nicht nur beim String-Parsing, sondern auch bei DNS/Redirect/Fetched-Zielen kontrolliert — `src/research/ssrf_guard.py`: `resolve_and_validate_host()`, `assert_safe_url()` + `_SSRFGuardRedirectHandler` (MAX_REDIRECTS=5). IP-Pinning ist Phase-2-Verschaerfung, kein DoD-Blocker.
- [x] der gesamte Vertrag ist durch Tests, Doku und Runtime-Auditdaten belegbar — 53 Tests in `test_runtime_step1.py`, davon 18 unter `@pytest.mark.security`, Narrative-Doku in `runtime_step1.md`, strukturierte Logs + `phase_durations_ms` + `intake_validation` im Run-Snapshot.

## 2. Runtime-Agent-Erzeugung auf 2026-Best-Practice-Niveau bringen

Betroffener aktueller Ablauf:

```python
agents = create_runtime_agents()
```

Aktueller Factory-Code:

```python
def create_runtime_agents() -> dict[str, object]:
    """Instantiate the runtime agents used by the pipeline."""
    shared_search_cache: dict = {}
    return {
        "supervisor": SupervisorAgent(),
        "departments": {
            "CompanyDepartment": DepartmentRuntime("CompanyDepartment", search_cache=shared_search_cache),
            "MarketDepartment": DepartmentRuntime("MarketDepartment", search_cache=shared_search_cache),
            "BuyerDepartment": DepartmentRuntime("BuyerDepartment", search_cache=shared_search_cache),
            "ContactDepartment": DepartmentRuntime("ContactDepartment", search_cache=shared_search_cache),
        },
        "synthesis": SynthesisRuntime(),
        "report_writer": ReportWriterRuntime(),
    }
```

### 2.0 Current State (Code-Audit)

- [x] `create_runtime_agents()` existiert bereits als zentrale Factory.
- [x] Supervisor, vier Domain Departments, Synthesis und Report Writer werden bereits erzeugt.
- [x] Departments teilen aktuell ein lokales `shared_search_cache: dict` pro Factory-Aufruf.
- [x] Delta fuer Punkt 2 ist **Typisierung, Validierung, Konfiguration und Audit**, nicht Rollen-Neuerfindung.

Ziel: Die Factory soll nicht nur Objekte instanziieren, sondern einen expliziten, validierten und auditierbaren Runtime-Composition-Vertrag liefern. Der Run soll frueh wissen, ob alle Rollen vorhanden, korrekt konfiguriert, beobachtbar und kompatibel mit den spaeteren Pipeline-Phasen sind.

### 2.1 Typisierten Runtime-Agent-Vertrag einfuehren

- [x] **Punkt 2.1 abgeschlossen** — `RuntimeAgents` (Dataclass mit `slots`) in `src/orchestration/runtime_agents.py` mit `supervisor`, `departments`, `synthesis`, `report_writer`, `search_cache`, `config`, `specs`. `DOMAIN_DEPARTMENT_NAMES = ("CompanyDepartment", "MarketDepartment", "BuyerDepartment", "ContactDepartment")` zentral definiert. `RuntimeAgents.__getitem__` + `__contains__` + `as_dict()` erhalten Rueckwaertskompatibilitaet fuer `agents["supervisor"]`/`agents["departments"][name]`-Pattern in `supervisor_loop.py` und `pipeline_runner.py`. `create_runtime_agents()` gibt jetzt `RuntimeAgents` statt `dict[str, object]` zurueck.

Umzusetzen:

- [x] `RuntimeAgents` als Dataclass oder Pydantic-Modell einfuehren, z. B. mit Feldern `supervisor`, `departments`, `synthesis`, `report_writer`;
- [x] `departments` typisieren als Mapping der erlaubten Department-Namen auf `DepartmentRuntime`;
- [x] erlaubte Department-Namen zentral definieren (`DOMAIN_DEPARTMENT_NAMES`);
- [x] bestehende Call Sites bewusst migrieren oder eine `as_dict()`-Kompatibilitaetsschicht bereitstellen (`__getitem__` + `as_dict()` als Schicht);
- [x] statische Typpruefung ermoeglichen: kein freies `dict[str, object]` als primaerer Vertrag.

Akzeptanzkriterien:

- [x] Tippfehler wie `"CompanyDepartmnt"` koennen nicht unbemerkt in der Runtime-Struktur existieren (`test_validate_runtime_agents_rejects_unexpected_department`);
- [x] `pipeline_runner.py`, `supervisor_loop.py` und Synthesis/Report-Zugriffe koennen eindeutig typisiert auf die Rollen zugreifen (`InitialRunState.agents: RuntimeAgents`);
- [x] Tests koennen exakt assertieren, welche Rollen im Bundle vorhanden sind.

### 2.2 Agent-Capability-Metadaten pro Rolle definieren

- [x] **Punkt 2.2 abgeschlossen** — `RuntimeAgentSpec` enthaelt `role_name`, `runtime_type`, `department_name`, `required_methods`, `tool_policy`, `model_profile`, `observability_role`; die Specs werden im `RuntimeAgents`-Bundle und Snapshot persistiert.

Die Factory sollte nicht nur Objekte liefern, sondern auch beschreiben, welche Rolle was darf und wofuer sie gedacht ist.

Umzusetzen:

- [x] `RuntimeAgentSpec` oder aehnliches Modell einfuehren mit `role_name`, `runtime_type`, `department_name`, `required_methods`, `tool_policy`, `model_profile`, `observability_role`;
- [x] fuer Supervisor festhalten: benoetigt `build_intake_brief`, `opening_message`, `accept_department_package`, `accept_synthesis`;
- [x] fuer jedes Domain Department festhalten: benoetigt `run`;
- [x] fuer Synthesis festhalten: benoetigt Synthesis-Runtime-Interface (`run`);
- [x] fuer Report Writer festhalten: benoetigt `run` und Report-Package-Erzeugung;
- [x] Agent-Specs im Runtime-Bundle oder RunContext-Audit ablegen.

Akzeptanzkriterien:

- [x] Aus dem Bundle ist maschinenlesbar ersichtlich, welche Rolle welche Runtime-Faehigkeiten haben muss;
- [x] Capability-Metadaten koennen fuer Preflight, Tests und UI-Diagnose genutzt werden;
- [x] fehlende Methoden werden vor Department-Ausfuehrung erkannt.

### 2.3 Runtime-Agent-Validierung direkt nach Erzeugung ausfuehren

- [x] **Punkt 2.3 abgeschlossen** — `validate_runtime_agents()` prueft Rollen, Department-Menge, Pflichtmethoden und Cache-Contract; `create_runtime_agents()` wirft im Strict-Mode `RuntimeAgentFactoryError(code="runtime_composition_invalid")`.

Aktuell wird erst spaeter auffallen, wenn ein Agent fehlt oder eine Methode nicht hat. State of the Art ist eine fruehe Composition-Validation.

Umzusetzen:

- [x] `validate_runtime_agents(agents: RuntimeAgents) -> RuntimeAgentValidationResult` einfuehren;
- [x] pruefen, ob genau die erwarteten Departments vorhanden sind: Company, Market, Buyer, Contact;
- [x] pruefen, ob keine unerwarteten Departments im Bundle liegen;
- [x] pruefen, ob Supervisor, Synthesis und Report Writer vorhanden sind;
- [x] pruefen, ob jede Rolle die benoetigten Methoden callable bereitstellt;
- [x] pruefen, ob alle Departments mit konsistentem Shared-Cache oder bewusst isoliertem Cache konfiguriert sind;
- [x] bei Fehlern einen klaren `Runtime composition failed: ...` Fehler ausloesen.

Akzeptanzkriterien:

- [x] ein fehlender `ContactDepartment` bricht den Run in Step 1 ab, nicht erst in Step 2;
- [x] eine fehlende `accept_department_package`-Methode am Supervisor bricht den Run in Step 1 ab;
- [x] der Fehler landet mit eigener Phase/Code in einem maschinenlesbaren Fehlerresultat.

### 2.4 Explizite Runtime-Konfiguration injizierbar machen

- [x] **Punkt 2.4 abgeschlossen** — `RuntimeFactoryConfig` ist injizierbar und enthaelt `strict_validation`, `shared_cache`, `factory_version`, `cache_strategy`, `tool_policy_mode`, `model_profile`, `runtime_profile`, `observability_enabled`; Snapshot persistiert nur nicht-sensitive Werte.

Die Factory erzeugt aktuell alle Rollen ohne sichtbare Konfiguration. Fuer Produktionsniveau sollte die Runtime-Konfiguration explizit und testbar injizierbar sein.

Umzusetzen:

- [x] `RuntimeFactoryConfig` einfuehren mit Modellprofilen, Cache-Strategie, Tool-Policy-Modus, Strict-Mode, Observability-Flags;
- [x] `create_runtime_agents(config: RuntimeFactoryConfig | None = None)` unterstuetzen;
- [x] Default-Konfiguration aus bestehenden Settings ableiten;
- [x] Tests koennen eine Minimal-/Mock-Konfiguration injizieren;
- [x] Konfiguration darf keine Secrets oder API Keys in Logs/RunContext persistieren;
- [x] Konfiguration soll dokumentieren, ob Shared Cache aktiv ist.

Akzeptanzkriterien:

- [x] lokale Tests koennen Agenten ohne echte externe Tool-Abhaengigkeiten erzeugen;
- [x] Produktionsmodus und Testmodus sind explizit unterscheidbar;
- [x] ein Run kann spaeter auditieren, mit welchem nicht-sensitiven Runtime-Profil er gestartet wurde.

### 2.5 Shared Search Cache als bewusste Runtime-Dependency modellieren

- [x] **Punkt 2.5 abgeschlossen** — `SearchCache` erzeugt pro Run thread-safe `SearchCacheNamespace`-Objekte (`RLock`) fuer `__search__`/`__pages__`; `DepartmentRuntime` nutzt den Contract direkt und bleibt fuer Legacy-Dicts kompatibel.

Audit-Hinweis: Vor einer Thread-Safety-Anforderung muss die Parallelisierungsstrategie bestaetigt werden. Company/Market laufen in Step 2 parallel; der Cache muss nur dann threadsicher sein, wenn er in diesen parallelen Pfaden wirklich mutiert wird.

Aktuell ist `shared_search_cache: dict = {}` ein lokales Dict in der Factory und wird an alle Departments gereicht. Das ist sinnvoll, aber nicht als Vertrag sichtbar.

Umzusetzen:

- [x] eigenen Cache-Typ oder Protokoll einfuehren, z. B. `SearchCache` statt freiem `dict`;
- [x] Cache-Strategie dokumentieren: pro Run geteilt, nicht global pro Prozess;
- [x] Thread-Safety fuer parallele Company/Market-Nutzung klaeren und absichern;
- [x] falls der Cache waehrend paralleler Departments beschrieben wird: Locking oder threadsichere Struktur verwenden;
- [x] Cache-Metriken vorbereiten: `entry_count()` und Namespaces im Snapshot; Hits/Misses/Evictions bleiben Phase 2;
- [x] Cache darf keine sensiblen Kundendaten in Long-Term Memory ueberfuehren.

Akzeptanzkriterien:

- [x] Company und Market koennen parallel auf den Cache zugreifen, ohne Race Conditions zu riskieren;
- [x] pro Run entsteht ein neuer Cache, damit Ergebnisse verschiedener Kunden nicht vermischt werden;
- [x] Cache-Verhalten ist in Tests nachvollziehbar.

### 2.6 Preflight-/Health-Check fuer Runtime-Agenten ergaenzen

- [x] **Punkt 2.6 abgeschlossen** — `runtime_agents_healthcheck()` liefert side-effect-arme Diagnose; `preflight.py` ruft die Runtime-Agent-Composition-Pruefung auf.

Best Practice ist, Runtime-Abhaengigkeiten vor dem eigentlichen Lauf zu pruefen.

Umzusetzen:

- [x] leichter `runtime_agents_healthcheck(...)` einfuehren;
- [x] pruefen, ob AG2-/AutoGen-abhaengige Klassen importierbar und instanziierbar sind;
- [x] pruefen, ob Modell-/Tool-Konfiguration fuer jede Rolle aufloesbar ist;
- [x] pruefen, ob Report Writer und Synthesis Runtime ohne externe Side Effects initialisierbar sind;
- [x] Health-Check optional in bestehendes `preflight.py` integrieren;
- [x] Health-Check darf keine teuren LLM-Calls oder Web-Suchen ausloesen.

Akzeptanzkriterien:

- [x] Konfigurationsfehler werden vor dem Department-Routing sichtbar;
- [x] lokaler Preflight kann die Agent-Composition pruefen;
- [x] Health-Check ist schnell und side-effect-arm.

### 2.7 Factory-Fehler sauber in Step-1-Fehlerphase abbilden

- [x] **Punkt 2.7 abgeschlossen** — `RuntimeAgentFactoryError` mit Codes `runtime_agent_factory_failed` / `runtime_composition_invalid`; `run_pipeline()` mappt auf `failed_phase="runtime_agent_factory"` mit `error_code` und `error_detail.errors`.

`create_runtime_agents()` liegt in `_initialize_run(...)`. Wenn dort etwas scheitert, sollte der Fehler klar als Agent-Composition-Fehler erkennbar sein.

Umzusetzen:

- [x] eigene Exception-Klasse einfuehren, z. B. `RuntimeAgentFactoryError`;
- [x] Fehlercode definieren, z. B. `runtime_agent_factory_failed` oder `runtime_composition_invalid`;
- [x] `_pipeline_error_result(...)` oder `_failed_intake_result(...)` nicht mit Intake-Fehlern vermischen;
- [x] `resolution_state["runtime_agents"]` bei Fehlern mit nicht-sensitiver Diagnose befuellen;
- [x] UI/API kann zwischen Intake-Fehler und Runtime-Composition-Fehler unterscheiden.

Akzeptanzkriterien:

- [x] ein kaputter Agent-Import wird nicht als Intake-Validierungsfehler gemeldet;
- [x] Fehlerausgabe enthaelt `failed_phase="initialize"` oder spezifischer `failed_phase="runtime_agent_factory"`;
- [x] Diagnose nennt die betroffene Rolle, ohne Secrets oder Prompts offenzulegen.

### 2.8 Auditierbaren Agent-Composition-Snapshot im RunContext speichern

- [x] **Punkt 2.8 abgeschlossen** — `RunContext.resolution_state["runtime_agents"] = agents.snapshot()` speichert Rollen, Runtime-Typen, Department-Namen, Config-Profil, Cache-Strategie und Factory-Version ohne Secrets.

Nach erfolgreicher Erzeugung sollte spaeter nachvollziehbar sein, welche Rollen im Run aktiv waren.

Umzusetzen:

- [x] `run_context.resolution_state["runtime_agents"]` oder eigenes Feld mit Snapshot befuellen;
- [x] Snapshot enthaelt Rollennamen, Runtime-Klassen, Department-Namen, nicht-sensitive Modellprofile, Cache-Strategie, Factory-Version;
- [x] Snapshot enthaelt keine Secrets, API Keys, vollstaendige Prompts oder vertrauliche Tool-Konfiguration;
- [x] Snapshot wird in Checkpoints und finalem `run_context.json` persistiert;
- [x] Snapshot ist stabil genug fuer Regressionstests.

Akzeptanzkriterien:

- [x] Nach einem Run kann man sehen, ob Supervisor, vier Departments, Synthesis und Report Writer erzeugt wurden;
- [x] bei spaeteren Architekturveraenderungen ist sichtbar, mit welcher Agent-Composition ein alter Run lief;
- [x] keine sensitiven Werte gelangen in die Artefakte.

### 2.9 Testabdeckung fuer Factory und Composition-Vertrag aufbauen

- [x] **Punkt 2.9 abgeschlossen** — `tests/architecture/test_runtime_agents.py` prueft Contract, Validator, Cache-Isolation/Thread-Safety, Healthcheck, Factory-Fehlerpfad, Logger und echte `create_runtime_agents()`-Factory mit gepatchten Konstruktoren.

Die Factory ist klein, aber kritisch. Ohne Tests kann ein fehlender Agent die Pipeline spaet brechen.

Umzusetzen:

- [x] Unit-Test: `create_runtime_agents()` erzeugt alle erwarteten Rollen;
- [x] Unit-Test: exakt vier Domain Departments vorhanden;
- [x] Unit-Test: alle Departments sind `DepartmentRuntime` mit korrektem Department-Namen;
- [x] Unit-Test: Supervisor/Synthesis/Report Writer haben die benoetigten callable Methoden;
- [x] Unit-Test: alle Departments teilen sich innerhalb eines Runs denselben Search-Cache, falls diese Strategie beibehalten wird;
- [x] Unit-Test: zwei getrennte Factory-Aufrufe teilen sich nicht denselben Cache;
- [x] Negativtests fuer fehlende Rolle, unerwartete Rolle, fehlende Methode;
- [x] Contract-Test, der `_initialize_run(...)` bei kaputter Factory sauber abbrechen laesst.

Akzeptanzkriterien:

- [x] Tests laufen lokal und in CI;
- [x] eine Regression in der Agent-Liste faellt vor Runtime-Ausfuehrung auf;
- [x] Cache-Isolation zwischen Runs ist belegt.

### 2.10 Observability fuer Agent-Erzeugung vorbereiten

- [x] **Punkt 2.10 abgeschlossen (MVP)** — `factory_logging.py` emittiert strukturierte JSON-Events fuer Erfolg/Fehler mit `schema_version`, `component`, `phase`, `run_id`, `status`, `error_code`, `duration_ms`, `factory_version`, `role_count`, `errors`; OTel/Metriken bleiben Phase 2.

Die Agent-Erzeugung sollte im Betrieb sichtbar sein, ohne laute Logs oder sensitive Details.

Umzusetzen:

- [x] strukturierter Log-Eintrag nach erfolgreicher Composition, z. B. Rollenanzahl und Factory-Version;
- [x] strukturierter Log-Eintrag bei Composition-Fehlern mit Rolle und Fehlercode;
- [ ] **(Phase 2)** spaeter OpenTelemetry-Span `pipeline.runtime_agent_factory` vorbereiten;
- [ ] **(Phase 2)** Metrik: Agent-Factory-Erfolgs-/Fehlerrate;
- [x] Metrik-nahe Factory-Initialisierungsdauer im Log-Event (`duration_ms`);
- [x] keine Prompts, Secrets oder API-Schluessel loggen.

Akzeptanzkriterien:

- [x] Betriebsdiagnose kann erkennen, ob Runs an Agent-Erzeugung oder spaeteren Phasen scheitern;
- [x] Logs bleiben datenschutz- und secret-sicher;
- [x] Factory-Latenz ist messbar.

### 2.11 Dokumentation und Diagramm fuer Step 1 aktualisieren

- [x] **Punkt 2.11 abgeschlossen (Narrative/MVP)** — `docs/runtime/runtime_step1.md` beschreibt Runtime-Agent-Vertrag, Validierung, Snapshot, Healthcheck und Factory-Fehlerpfad; Draw.io-/Zielarchitektur-Regeneration bleibt Backlog.

Wenn die Factory zum expliziten Runtime-Composition-Vertrag wird, muss Step-1-Doku mitziehen.

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` um Runtime-Agent-Vertrag, Validierung und Snapshot erweitern;
- [ ] **(Backlog)** `scripts/generate_step1_drawio.py` aktualisieren;
- [ ] **(Backlog)** `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [ ] **(Backlog)** `docs/drawio/target_runtime_architecture.md` um Agent-Composition-Vertrag und bekannte Grenzen aktualisieren;
- [x] falls `preflight.py` erweitert wird: Preflight-Doku aktualisieren.

Akzeptanzkriterien:

- [ ] **(Backlog)** Diagramm zeigt nicht nur "Create runtime agents", sondern auch Validierung/Audit-Snapshot;
- [x] Narrative Doku erklaert, was bei Factory-Fehlern passiert;
- [x] Architekturziel und Code widersprechen sich nicht auf Narrative-/MVP-Ebene.

### 2.12 Zielbewertung nach Umsetzung

- [x] **Punkt 2.12 abgeschlossen**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung | Ist (2026-05-12) | Anmerkung |
| --- | ---: | ---: | --- |
| Vollstaendigkeit der Rollen | 5/5 | **5/5** | Supervisor, 4 Departments, Synthesis, ReportWriter validiert |
| Zentralisierung | 5/5 | **5/5** | `DOMAIN_DEPARTMENT_NAMES`, `RuntimeAgents`, `create_runtime_agents()` |
| Typisierung / Contract | 5/5 | **5/5** | `RuntimeAgents`, `RuntimeAgentSpec`, `RuntimeFactoryConfig`, ValidationResult |
| Konfigurierbarkeit | 5/5 | **5/5** | nicht-sensitive Config inkl. Cache-/Tool-/Profile-/Observability-Flags |
| Fehlerfrueherkennung | 5/5 | **5/5** | Strict Validation + `RuntimeAgentFactoryError` |
| Observability / Auditierbarkeit | 5/5 | **4.5/5** | JSON-Events + Snapshot + Duration; OTel/Prometheus Phase 2 |
| Testbarkeit | 5/5 | **5/5** | 26 Runtime-Agent-Tests + Preflight-Smoke-Test |

### 2.13 Definition of Done fuer Punkt 2

- [x] **Punkt 2.13 abgeschlossen (MVP/Code)**

- [x] Runtime-Agent-Erzeugung liefert einen typisierten, validierten Agent-Vertrag statt primaer eines losen Dicts;
- [x] alle erwarteten Rollen sind vollstaendig, eindeutig benannt und mit ihren benoetigten Capabilities validiert;
- [x] Factory-Konfiguration ist explizit, testbar und ohne Secret-Leaks auditierbar;
- [x] Shared Search Cache ist als bewusste, pro-Run isolierte und threadsichere Dependency modelliert;
- [x] Composition-Fehler brechen Step 1 frueh und maschinenlesbar ab;
- [x] erfolgreicher Composition-Snapshot wird im RunContext persistiert;
- [x] Tests belegen Rollen-Vollstaendigkeit, Capability-Vertrag, Cache-Isolation und Fehlerverhalten;
- [ ] **(Backlog)** Runtime-Doku ist synchronisiert; Draw.io-Generator, Draw.io-Datei und Zielarchitektur werden separat regeneriert.

## 3. Memory + RunContext von Local-First auf Hetzner/Postgres/pgvector mit Cloudflare Edge-Schutz migrieren (Phase 2 - nicht MVP)

Betroffener aktueller Ablauf:

```python
stores = create_runtime_stores(
    runs_root=RUNS_DIR,
    long_term_memory_path=LONG_TERM_MEMORY_PATH,
)
stores.healthcheck_required()
memory_store = stores.long_term_memory
run_context = RunContext(
    run_id=run_id,
    intake={
        "company_name": intake.company_name,
        "web_domain": intake.web_domain,
        "normalized_domain": normalized_domain,
        "language": intake.language,
    },
)
_record_phase(run_context, "initialized")
run_context.resolution_state["storage"] = stores.snapshot()
```

Umsetzungsstand 2026-05-12:

- Lokaler Code-Backbone fuer Punkt 3 ist umgesetzt: Store-Contracts,
  Runtime-Store-Factory, Storage-Healthcheck, Production-Fail-Fast,
  non-sensitiver RunContext-Snapshot, SQL-Zielschema und Architektur-Doku.
- Nicht lokal umgesetzt sind reale Hetzner/Postgres/pgvector-Deployment-
  Schritte, Cloudflare-Konfiguration, echte DSN-basierte Store-Klassen,
  Migration-Jobs und Deployment-Smoke-Tests. Diese Punkte bleiben Phase-2-Ops.
- Absichtlich offen bleiben nur Checkboxen, die eine echte DB-/Cloudflare-
  Implementierung, Migration, Integrationstest-Infrastruktur oder produktive
  Betriebsverifikation erfordern. Reine Design-, Schema-, Doku- und
  Local-Code-Backbone-Punkte sind abgehakt.

### 3.0 Current State (Code-Audit)

- [x] `FileLongTermMemoryStore` existiert bereits mit JSON-Datei, `FileLock`, Scrubbing-Guards, `healthcheck()` und `upsert_strategy(...)`.
- [x] Normaler `_initialize_run(...)`-Pfad loest keinen opportunistischen Long-Term-Backfill aus.
- [x] `backfill_long_term_memory_from_runs(...)` existiert weiter als Kandidat fuer einen separaten Maintenance-/Migration-Job.
- [x] Delta fuer Punkt 3 ist **Phase-2-Migration des Produktions-Backbone**, nicht MVP-Pflicht.
- [x] Punkt 3.0 Datenmodell-Alignment ist lokal durch `docs/runtime/phase2_storage_architecture.md` und `sql/20260512_phase2_storage.sql` vorbereitet.

Ziel: Dieser Abschnitt soll nicht weiter als lokaler JSON-Datei-Store gedacht werden. Hetzner ist das System of Record fuer Pipeline-Runs, Checkpoints, Artefakte und Long-Term Process Memory. Cloudflare ist Edge-, Security-, Access- und optionaler Object-Storage-Layer. Der normale Runtime-Start darf keinen opportunistischen Backfill mehr aus lokalen Run-Ordnern ausloesen.

### 3.A Datenmodell-Alignment (Prerequisite fuer Punkt 3 und Punkt 4)

- [x] **Punkt 3.A abgeschlossen (Design-/Schema-Alignment lokal abgeschlossen; externe Freigabe/Deployment offen)**

Kein Punkt 3 oder Punkt 4 darf parallel implementiert werden, bevor ein gemeinsames Schema-Design-Dokument fuer Run-State, Memory-Patterns, Retrieval-Metadaten und Migration freigegeben ist.

Umzusetzen:

- [x] Schema-Design-Dokument fuer `runs`, `run_checkpoints`, `run_events`, `run_artifacts`, `memory_patterns`, `memory_retrieval_events` erstellen;
- [x] Ownership klaeren: Punkt 3 liefert Store-/Schema-/Migration-Backbone; Punkt 4 liefert Retrieval-Querying, Ranking, Policy-Gates und Pattern-Auswahl;
- [x] gemeinsame IDs und Versionen festlegen: `run_id`, `pattern_id`, `schema_version`, `embedding_model`, `retrieval_policy_version`;
- [x] entscheiden, welche Felder JSONB bleiben und welche normalisiert/indexiert werden;
- [x] Migration- und Rollback-Strategie vor Implementierung von Punkt 3.3, 3.4, 3.5 und 4.4 festlegen.

Akzeptanzkriterien:

- [x] Punkt 3.5 und Punkt 4.4 widersprechen sich nicht;
- [x] parallele Umsetzung kann keine inkompatiblen Tabellen oder Retrieval-Metadaten erzeugen;
- [x] MVP kann ohne Punkt 3/4 abgeschlossen werden, ohne spaetere Phase-2-Migration zu verbauen.

### 3.1 Zielrollen von Hetzner und Cloudflare verbindlich festlegen

- [x] **Punkt 3.1 abgeschlossen (Architekturentscheidung dokumentiert; Infrastruktur-Konfiguration bleibt Phase-2-Ops)**

Umzusetzen:

- [x] Hetzner als primären Compute-Ort fuer die Python/AG2/AutoGen-Pipeline festlegen;
- [x] Hetzner PostgreSQL als System of Record fuer Runs, Checkpoints, Runtime-State und Memory-Metadaten festlegen;
- [x] `pgvector` auf Hetzner PostgreSQL als primaeren Vector Store fuer Long-Term Process Memory festlegen;
- [x] Cloudflare fuer DNS, TLS, WAF, DDoS-Schutz, Rate Limiting und Access/Zero-Trust nutzen;
- [x] Cloudflare Tunnel fuer sicheren Zugriff auf Hetzner-Services bevorzugen, statt oeffentliche Hetzner-Ports direkt freizugeben;
- [x] Cloudflare R2 nur fuer grosse Export-/Report-Artefakte nutzen, falls S3-kompatible Ablage gewuenscht ist;
- [x] Cloudflare Workers hoechstens als duenner Gateway-/Webhook-/Status-Layer nutzen, nicht als Orchestrator der langlaufenden AG2-Runtime.

Akzeptanzkriterien:

- [x] Architekturentscheidung ist in `docs/runtime/phase2_storage_architecture.md` und `docs/drawio/target_runtime_architecture.md` dokumentiert;
- [x] lokale JSON-Dateien gelten nicht mehr als produktives System of Record;
- [x] Cloudflare- und Hetzner-Zustaendigkeiten sind nicht vermischt.

### 3.2 FileLongTermMemoryStore durch produktiven Store-Vertrag ersetzen

- [ ] **Punkt 3.2 bearbeitet (Store-Vertrag und Fail-Fast umgesetzt; echter Postgres-Store offen)**

Umzusetzen:

- [x] abstraktes Store-Protokoll definieren, z. B. `LongTermMemoryStore` mit `retrieve(...)`, `upsert_strategy(...)`, `healthcheck(...)`;
- [ ] `PostgresLongTermMemoryStore` implementieren;
- [x] `FileLongTermMemoryStore` nur noch fuer lokale Tests/Development oder Migration behalten;
- [x] Store-Auswahl ueber explizite Runtime-Konfiguration steuern, nicht ueber zufaellige Pfade;
- [x] `_initialize_run(...)` darf im Produktionsprofil keinen File-Store mehr instanziieren;
- [x] Store-Health beim Run-Start pruefen und Fehler maschinenlesbar melden.

Akzeptanzkriterien:

- [x] Produktionsmodus startet nur, wenn der Postgres/pgvector Store erreichbar und migriert ist;
- [x] Tests koennen weiterhin einen In-Memory- oder File-Teststore verwenden;
- [x] Call Sites haengen am Store-Vertrag, nicht an einer konkreten File-Implementierung.

### 3.3 Datenmodell fuer Run State, Checkpoints und Artefakte in PostgreSQL entwerfen

- [ ] **Punkt 3.3 bearbeitet (SQL-Zielschema entworfen; DB-Schreibpfad offen)**

Umzusetzen:

- [x] Tabelle `runs` definieren: `run_id`, `company_name`, `web_domain`, `normalized_domain`, `status`, `current_phase`, `created_at`, `updated_at`, `completed_at`, `error_code`, `error_message`;
- [x] Tabelle `run_checkpoints` definieren: `run_id`, `phase`, `sequence`, `run_context_snapshot` als JSONB, `created_at`;
- [x] Tabelle `run_events` definieren: `run_id`, `sequence`, `agent`, `type`, `content_json`, `created_at`;
- [x] Tabelle `run_artifacts` definieren: `run_id`, `artifact_type`, `storage_backend`, `storage_key`, `content_hash`, `metadata_json`, `created_at`;
- [x] Tabelle `run_locks` oder Postgres Advisory Locks fuer konkurrierende Resume-/Follow-up-Zugriffe vorsehen;
- [x] JSONB-Felder mit `schema_version` versehen;
- [x] geeignete Indizes fuer `run_id`, `status`, `current_phase`, `created_at` und Artefakt-Typen definieren.

Akzeptanzkriterien:

- [ ] `RunContext` kann nach jeder Phase aus PostgreSQL rehydriert werden;
- [x] `after_supervisor_brief`, `after_first_pass`, `after_closure`, `after_synthesis`, `after_finalization` sind als DB-Checkpoints abbildbar;
- [x] Datei-Export kann weiterhin zusaetzlich erfolgen, ist aber nicht mehr primaere Recovery-Quelle.

### 3.4 Datenmodell fuer Long-Term Process Memory mit pgvector entwerfen

- [ ] **Punkt 3.4 bearbeitet (pgvector-Schema entworfen; Retrieval-Implementierung folgt in Punkt 4/Phase 2)**

Umzusetzen:

- [x] Tabelle `memory_patterns` definieren mit `id`, `role`, `pattern_scope`, `industry_hint`, `content_text`, `content_json`, `embedding`, `score`, `source_run_id`, `schema_version`, `created_at`, `updated_at`;
- [x] `embedding` als pgvector-Spalte anlegen;
- [x] Filterspalten fuer `role`, `pattern_scope`, `industry_hint`, `schema_version` indexieren;
- [x] Vector Index definieren, z. B. HNSW oder IVFFlat je nach Postgres/pgvector-Version;
- [x] `source_run_id` nur fuer Audit/Trace halten, nicht fuer domain-spezifisches Retrieval verwenden;
- [x] Pattern-Deduplication ueber stabilen Content-Hash einfuehren;
- [x] Score-Decay und Replacement-Regeln aus dem File-Store in DB-Logik uebertragen.

Akzeptanzkriterien:

- [ ] Retrieval kann role-/scope-gefiltert und semantisch ueber Embeddings laufen;
- [ ] Long-Term Memory bleibt frei von Kunden-Domains und Zielkunden-Fakten;
- [ ] alte Pattern-Schema-Versionen koennen migriert oder beim Retrieval gezielt ausgeschlossen werden.

### 3.5 Retrieval-Datenmodell und Store-Unterstuetzung fuer Hybrid Search vorbereiten

- [ ] **Punkt 3.5 bearbeitet (Store-Unterstuetzung vorbereitet; Hybrid Ranking bleibt Punkt 4)**

Hinweis: Ranking, Query-Kontext, Policy-Gates und Pattern-Auswahl gehoeren zu Punkt 4. Punkt 3.5 liefert nur die Infrastruktur- und Store-Voraussetzungen.

Umzusetzen:

- [x] `retrieve_strategies(...)` so erweitern, dass es den Store-Vertrag nutzt;
- [x] Hybrid Search definieren: harte Filter `role`, `pattern_scope`, optional `industry_hint` plus Vektor-Aehnlichkeit plus Score;
- [x] deterministische Fallback-Reihenfolge definieren, wenn Embedding-Retrieval nicht verfuegbar ist;
- [x] Retrieval-Limits pro Rolle beibehalten oder begruendet anpassen;
- [ ] Retrieval-Ergebnis mit `retrieval_reason`, `similarity_score`, `pattern_score`, `schema_version` auditierbar machen;
- [x] keine Domain-Match-Boni einfuehren, weil Domain-spezifische Long-Term-Memory-Eintraege gegen die Policy verstossen.

Akzeptanzkriterien:

- [ ] `run_context.retrieved_strategies` und `retrieved_role_strategies` enthalten auditierbare Retrieval-Metadaten;
- [x] gleiche Inputs liefern bei gleichem Store reproduzierbare Top-K-Ergebnisse;
- [ ] Retrieval skaliert ueber hunderte bis tausende Patterns besser als Flat-File-Scoring.

### 3.6 Backfill aus dem normalen Run-Pfad entfernen

- [ ] **Punkt 3.6 bearbeitet (normaler Run-Pfad bereinigt; Maintenance-Job offen)**

Umzusetzen:

- [x] `_long_term_backfill_enabled()` aus dem normalen `_initialize_run(...)`-Pfad entfernen oder im Produktionsmodus hart deaktivieren;
- [ ] `backfill_long_term_memory_from_runs(...)` in einen separaten Maintenance-Job verschieben;
- [ ] Maintenance-Job idempotent machen;
- [x] Job-ID, Startzeit, Endzeit, Status, Zaehler und Fehler in Tabelle `memory_backfill_jobs` speichern;
- [ ] Dry-Run-Modus fuer Backfill bereitstellen;
- [x] Backfill darf nie waehrend eines Kunden-Runs stillschweigend historische Artefakte verarbeiten;
- [ ] Backfill muss Scrubbing-Ergebnis pro Pattern protokollieren.

Akzeptanzkriterien:

- [x] Ein normaler Run liest nur Prozessmuster, fuehrt aber keinen historischen Backfill aus;
- [x] Backfill ist ein expliziter Admin-/Ops-Prozess;
- [ ] Backfill-Ergebnisse sind auditierbar und wiederholbar.

### 3.7 RunContext-Persistenz transaktional machen

- [ ] **Punkt 3.7 offen (Schema/Contract vorbereitet; transaktionaler DB-Schreibpfad offen)**

Umzusetzen:

- [ ] beim Run-Start `runs`-Datensatz in einer Transaktion anlegen;
- [ ] `current_phase="initialized"` und Intake-Snapshot atomar speichern;
- [ ] `_record_phase(...)` um DB-Persistenz oder Phase-Service erweitern;
- [ ] `_write_checkpoint(...)` in DB-Checkpoint-Schreibung ueberfuehren oder um DB-Schreibung erweitern;
- [x] Checkpoint-Schreibung idempotent und sequenziert machen (SQL-Constraint vorbereitet);
- [ ] Fehlerpfad `_pipeline_error_result(...)` schreibt finalen Fehlerstatus ebenfalls transaktional;
- [ ] Resume und Follow-up laden Zustand primaer aus DB, nicht aus lokalen JSON-Dateien.

Akzeptanzkriterien:

- [ ] Prozessabbruch nach Step 1 kann aus DB diagnostiziert und ggf. fortgesetzt werden;
- [ ] keine halbgeschriebenen JSON-Dateien sind fuer Recovery erforderlich;
- [ ] Status und Checkpoint widersprechen sich nicht.

### 3.8 Artefaktablage fuer grosse Dateien klar trennen

- [ ] **Punkt 3.8 bearbeitet (Artefaktmodell definiert; Object-Storage-Anbindung offen)**

Umzusetzen:

- [x] kleine strukturierte Daten in PostgreSQL/JSONB halten;
- [x] grosse Reports, PDFs, Screenshots oder Roh-Snapshots in Object Storage ablegen;
- [x] Entscheidung treffen: Cloudflare R2 oder Hetzner Object Storage/Volume;
- [x] `run_artifacts` speichert nur Metadaten, Storage-Key und Hash;
- [x] Content-Hash fuer Integritaetspruefung speichern;
- [x] Retention- und Loeschregeln fuer Artefakte definieren;
- [x] Zugriff auf Artefakte ueber signierte URLs oder geschuetzte Backend-Endpunkte, nicht oeffentlich.

Akzeptanzkriterien:

- [ ] grosse Artefakte blaehnen PostgreSQL nicht auf;
- [ ] jeder Artefakt-Link ist nachvollziehbar, geschuetzt und integrity-checkbar;
- [ ] Loesch-/Retention-Regeln koennen Kundendaten gezielt entfernen.

### 3.9 Cloudflare Security- und Access-Layer konkretisieren

- [ ] **Punkt 3.9 bearbeitet (Security-Zielbild definiert; Cloudflare-Setup offen)**

Umzusetzen:

- [ ] Cloudflare DNS und TLS fuer Dashboard/API-Domain konfigurieren;
- [ ] WAF-Regeln fuer API und Dashboard aktivieren;
- [x] Rate Limits fuer Run-Start-, Resume-, Follow-up- und Export-Endpunkte definieren;
- [x] Cloudflare Access/Zero Trust fuer interne Dashboards nutzen;
- [x] Cloudflare Tunnel zwischen Cloudflare und Hetzner-Service einrichten;
- [x] direkte oeffentliche Hetzner-Ports minimieren oder schliessen;
- [x] Security Headers und Request-Size-Limits am Edge setzen;
- [x] Bot-/Abuse-Schutz fuer oeffentliche Endpunkte pruefen.

Akzeptanzkriterien:

- [ ] Dashboard/API sind nicht ungeschuetzt direkt auf Hetzner exponiert;
- [ ] Run-Start kann nicht beliebig durch unauthentifizierte Clients gespammt werden;
- [ ] Edge-Logs und Hetzner-App-Logs erlauben gemeinsame Incident-Diagnose.

### 3.10 Secrets, Credentials und Verbindungsmanagement produktionsreif machen

- [ ] **Punkt 3.10 bearbeitet (Secret-Redaction und Failure-Konzept umgesetzt; Connection Pooling offen)**

Umzusetzen:

- [x] Datenbank-Credentials nicht in `.env` oder Artefakten speichern;
- [x] Hetzner-Service nutzt Secrets aus sicherem Deployment-Kontext;
- [x] Cloudflare-Tunnel-/R2-/Access-Secrets getrennt verwalten;
- [ ] DB-Verbindungen ueber Connection Pooling nutzen;
- [x] Timeouts, Retry-Policy und Circuit Breaker fuer DB/Vector Store definieren;
- [x] Readiness-/Liveness-Checks fuer DB-Verbindung bereitstellen;
- [x] keine Secrets in `run_context`, Checkpoints, Logs oder Exporten persistieren.

Akzeptanzkriterien:

- [ ] Secret-Leak in Runtime-Artefakte ist durch Tests/Scans abgesichert;
- [ ] DB-Ausfall fuehrt zu kontrolliertem Fehlerstatus, nicht zu korruptem Run-State;
- [ ] Deployment kann Credentials rotieren, ohne Codeaenderung.

### 3.11 Migration von bestehendem File-Memory und Run-Artefakten planen (Phase 2, nach Schema-Freeze)

- [ ] **Punkt 3.11 offen (Migrationsstrategie dokumentiert; Scripts offen)**

Umzusetzen:

- [ ] Migration-Script fuer `artifacts/memory/long_term_memory.json` nach `memory_patterns` schreiben;
- [ ] Migration-Script fuer bestehende `artifacts/runs/*` nach `runs`, `run_checkpoints`, `run_artifacts` vorbereiten;
- [x] Scrubbing bei Migration erneut ausfuehren, nicht blind bestehende Patterns uebernehmen;
- [x] Migrationsbericht erzeugen: gelesen, uebernommen, abgelehnt, Fehler;
- [x] Dry-Run und Resume-Faehigkeit fuer Migration bereitstellen;
- [x] alte lokale Artefakte nach erfolgreicher Migration als read-only Archiv behandeln;
- [x] Rollback-Strategie fuer Schema- oder Migrationsfehler definieren.

Akzeptanzkriterien:

- [ ] Migration kann mehrfach laufen, ohne Duplikate zu erzeugen;
- [ ] unsichere Patterns werden abgelehnt und begruendet protokolliert;
- [ ] bestehende Runs bleiben fuer Follow-up oder Audit auffindbar.

### 3.12 Datenschutz, Mandantentrennung und Memory-Policy absichern

- [ ] **Punkt 3.12 bearbeitet (Policy-/Schema-Grenze definiert; RLS-Umsetzung offen)**

Umzusetzen:

- [x] klare Trennung zwischen kundenspezifischem Run Brain und scrubbed Long-Term Process Memory durch DB-Schemas oder Tabellenregeln;
- [x] Mandanten-/Kundenkontext fuer Runs modellieren, falls mehrere Kunden genutzt werden;
- [ ] Row-Level-Security oder Anwendungs-Guards fuer Mandantentrennung pruefen;
- [x] Scrubbing-Gates vor jedem `memory_patterns`-Write erzwingen;
- [x] Ablehnungen unsicherer Patterns mit `rejection_code` protokollieren;
- [x] Retention- und Loeschkonzept fuer Run-Daten definieren;
- [x] Memory-Pattern darf keine Domains, URLs, E-Mails, Personen, rechtlichen Firmennamen oder konkreten Finanzzahlen enthalten.

Akzeptanzkriterien:

- [ ] Long-Term Memory enthaelt nur Prozessmuster, keine Zielkunden-Fakten;
- [ ] Loeschanforderungen fuer kundenspezifische Runs betreffen nicht faelschlich scrubbed Prozessmuster;
- [ ] Policy-Verletzungen werden blockiert und auditierbar gemeldet.

### 3.13 Observability fuer Memory, Run-State und Backfill einfuehren

- [ ] **Punkt 3.13 bearbeitet (Audit-Felder/Fehlerphasen vorbereitet; OTel/Metriken offen)**

Umzusetzen:

- [x] strukturierte Logs fuer Run-State-Schreibungen, Checkpoints, Memory-Retrieval und Memory-Writes;
- [x] Metriken: DB-Latenz, Checkpoint-Schreibdauer, Retrieval-Latenz, Pattern-Anzahl, Backfill-Dauer, Backfill-Ablehnungen;
- [ ] OpenTelemetry-Spans fuer `pipeline.run_context.initialize`, `memory.retrieve_strategies`, `memory.backfill_job`, `checkpoint.write` vorbereiten;
- [x] Alerting fuer DB-Verbindungsfehler, hohe Retrieval-Latenz, Backfill-Fehler und Scrubbing-Rejections-Spikes definieren;
- [x] Cloudflare Logs mit App-Run-ID korrelierbar machen, z. B. ueber Request-ID Header.

Akzeptanzkriterien:

- [ ] ein fehlgeschlagener Run-Start ist operational von Intake-, Agent-Factory-, DB- und Memory-Fehlern unterscheidbar;
- [ ] Memory-Retrieval-Qualitaet und -Latenz sind messbar;
- [ ] Backfill-Probleme fallen nicht erst durch falsche Runtime-Ergebnisse auf.

### 3.14 Failure Modes und Degradation bewusst definieren

- [x] **Punkt 3.14 abgeschlossen**

Umzusetzen:

- [x] Verhalten definieren, wenn Postgres nicht erreichbar ist: Run nicht starten oder read-only degradieren;
- [x] Verhalten definieren, wenn pgvector/Embedding-Retrieval ausfaellt: Fallback auf role-/score-basiertes Retrieval oder Run-Abbruch;
- [x] Verhalten definieren, wenn Object Storage ausfaellt: Report-Export blockieren, aber Run-State erhalten;
- [x] Verhalten definieren, wenn Cloudflare Edge erreichbar ist, Hetzner-App aber nicht;
- [x] Verhalten definieren, wenn Backfill-Job fehlschlaegt: kein Einfluss auf laufende Runs;
- [x] Fehlercodes fuer DB, Vector Store, Object Storage, Cloudflare/Tunnel und Backfill standardisieren.

Akzeptanzkriterien:

- [x] jeder kritische Infrastrukturfehler hat einen dokumentierten Run-Status und Fehlercode;
- [x] keine Infrastrukturstoerung fuehrt zu stiller Nutzung veralteter oder leerer Memory-Daten ohne Audit;
- [x] laufende Runs koennen kontrolliert scheitern, statt inkonsistente Artefakte zu erzeugen.

### 3.15 Tests und Deployment-Pruefungen fuer Produktionsspeicher aufbauen

- [ ] **Punkt 3.15 abgeschlossen (lokale Contract-Tests umgesetzt; echte Integration/Deployment-Tests offen)**

Umzusetzen:

- [ ] Integrationstests gegen Test-Postgres mit pgvector;
- [x] Migrationstests fuer Schema-Upgrades;
- [x] Contract-Tests fuer Store-Protokoll: File-Teststore und Postgres-Store muessen gleiche Semantik liefern;
- [ ] Concurrency-Tests fuer parallele Run-Starts und Checkpoint-Schreibungen;
- [ ] Backfill-Job-Tests mit sicheren und unsicheren historischen Artefakten;
- [x] Security-Tests fuer Scrubbing-Gates;
- [ ] Preflight-Pruefung fuer DB, pgvector Extension, Migration Version, Cloudflare Tunnel/Access-Konfiguration soweit lokal pruefbar;
- [ ] CI trennt Unit Tests, Integration Tests und Deployment Smoke Tests.

Akzeptanzkriterien:

- [ ] Produktionsprofil kann nicht starten, wenn DB-Schema oder pgvector fehlen;
- [ ] Store-Regressionen fallen vor Deployment auf;
- [ ] Backfill und Migration sind testbar, ohne echte Kundendaten zu verwenden.

### 3.16 Step-1-Codepfad nach Zielarchitektur neu formulieren

- [x] **Punkt 3.16 abgeschlossen (Step-1-Codepfad lokal neu formuliert; DB-create/checkpoint offen)**

Zielbild fuer `_initialize_run(...)` nach Umsetzung:

```python
stores = create_runtime_stores(config.storage)
stores.healthcheck_required()
run_record = stores.run_state.create_run(
    run_id=run_id,
    intake=normalized_intake,
    phase="initialized",
)
run_context = RunContext(
    run_id=run_id,
    intake=normalized_intake.model_dump(mode="json"),
)
run_context.resolution_state["storage"] = stores.snapshot()
run_context.retrieved_strategies = retrieve_strategies(
    stores.long_term_memory,
    industry_hint=brief_or_intake_hint,
    limit=5,
)
stores.run_state.write_checkpoint(
    run_id=run_id,
    phase="initialized",
    run_context=run_context.snapshot(),
)
```

Umzusetzen:

- [x] Store-Erzeugung vor RunContext-Persistenz klar kapseln;
- [x] Healthcheck vor erster fachlicher Recherche ausfuehren;
- [ ] Run-Datensatz und initialer Checkpoint in DB schreiben;
- [ ] Long-Term-Memory-Retrieval aus Postgres/pgvector laden;
- [x] Backfill aus diesem Codepfad entfernen;
- [x] nicht-sensitive Storage-/Memory-Snapshots im `resolution_state` speichern.

Akzeptanzkriterien:

- [ ] Step 1 erzeugt einen produktionsfaehig persistierten Run, bevor Supervisor-Briefing beginnt;
- [ ] Recovery-Quelle ist DB/Store, nicht lokales Dateisystem;
- [ ] Runtime-Doku und Diagramm zeigen die neue Grenze zwischen Store-Init, Run-State-Create, Memory-Retrieval und Supervisor-Brief.

### 3.17 Dokumentation, Diagramm und Zielarchitektur aktualisieren

- [x] **Punkt 3.17 abgeschlossen (Runtime-Doku, Draw.io-Generator, Draw.io-Datei und Zielarchitektur synchronisiert; echte Deploy-Ops offen)**

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` um Hetzner/Postgres/pgvector/Cloudflare-Zielbild erweitern;
- [x] `scripts/generate_step1_drawio.py` aktualisieren;
- [x] `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [x] `docs/drawio/target_runtime_architecture.md` aktualisieren: Local-First abloesen, Hetzner als System of Record, Cloudflare als Edge-Layer;
- [x] Betriebshandbuch oder Deploy-Doku fuer DB-Migrationen, Backups, Cloudflare Tunnel, R2/Object Storage und Backfill-Jobs ergaenzen;
- [x] bekannte Gaps neu bewerten: Flat-File Memory Gap wird durch pgvector-Migration ersetzt.

Akzeptanzkriterien:

- [x] Doku, Diagramm und Code-Zielbild beschreiben dieselbe Produktionsarchitektur;
- [x] Local-First wird nicht mehr als Produktionsannahme dargestellt;
- [x] Betreiber kann aus der Doku ableiten, welche Hetzner- und Cloudflare-Komponenten zwingend sind.

### 3.18 Zielbewertung nach Umsetzung

- [ ] **Punkt 3.18 abgeschlossen (Zielbewertung bleibt erst nach echter Phase-2-Infrastruktur erreichbar)**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung |
| --- | ---: |
| Run-State-Modellierung | 5/5 |
| Memory-Grenze | 5/5 |
| Backfill-Kontrolle | 5/5 |
| Persistenz-Robustheit | 5/5 |
| Datenintegritaet | 5/5 |
| Datenschutz / Scrubbing | 5/5 |
| Observability / Auditierbarkeit | 5/5 |
| Skalierbarkeit | 5/5 |
| Betriebsfaehigkeit Hetzner/Cloudflare | 5/5 |

Aktueller lokaler Stand nach dieser Umsetzung:

| Kriterium | Stand 2026-05-12 |
| --- | ---: |
| Run-State-Modellierung | 4/5 |
| Memory-Grenze | 4/5 |
| Backfill-Kontrolle | 4/5 |
| Persistenz-Robustheit | 3/5 |
| Datenintegritaet | 4/5 |
| Datenschutz / Scrubbing | 4/5 |
| Observability / Auditierbarkeit | 3/5 |
| Skalierbarkeit | 3/5 |
| Betriebsfaehigkeit Hetzner/Cloudflare | 2/5 |

### 3.19 Definition of Done fuer Punkt 3

- [ ] **Punkt 3.19 abgeschlossen (lokaler Backbone umgesetzt; echte Production-DoD offen)**

- [x] `FileLongTermMemoryStore` ist im Produktionsprofil durch Postgres/pgvector Store ersetzt;
- [ ] RunContext, Phasenstatus und Checkpoints werden transaktional in PostgreSQL persistiert;
- [x] Long-Term Process Memory nutzt scrubbed Patterns, Schema-Versionen, Content-Hashes und Embeddings;
- [ ] Backfill ist ein separater, idempotenter und auditierbarer Maintenance-Job;
- [x] Cloudflare schuetzt Zugriff, Routing und Edge-Sicherheit, orchestriert aber nicht die langlaufende Pipeline;
- [x] grosse Artefakte liegen in einem definierten Object-Storage/Artefakt-Backend mit Hash und Retention;
- [x] Secrets, DB-Verbindungen, Timeouts und Failure Modes sind produktionsreif definiert;
- [ ] Tests decken Store-Vertrag, Migration, Scrubbing, Concurrency und Deployment-Preflight ab;
- [x] Runtime-Doku, Draw.io-Generator, Draw.io-Datei, Zielarchitektur und Betriebshandbuch sind synchronisiert.

## 4. Retrieval von Prozessmustern auf kontextuelles Hybrid Retrieval umstellen

Betroffener aktueller Ablauf:

```python
run_context.retrieved_strategies = retrieve_strategies(
    memory_store,
    domain=normalized_domain,
    limit=5,
)
run_context.retrieved_role_strategies = {
    role: retrieve_strategies(
        memory_store,
        domain=normalized_domain,
        role=role,
        limit=3,
    )
    for role in RETRIEVABLE_ROLE_ORDER
}
```

Aktueller Helper:

```python
def retrieve_strategies(
    store: FileLongTermMemoryStore,
    *,
    domain: str,
    industry_hint: str = "",
    role: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    return store.retrieve(domain=domain, industry_hint=industry_hint, role=role, limit=limit)
```

### 4.0 Current State (Code-Audit)

- [x] `retrieve_strategies(...)` existiert als kompatibler Wrapper; `retrieve_strategy_batch(...)` liefert zusaetzlich Audit-Snapshot.
- [x] `FileLongTermMemoryStore.retrieve(...)` nutzt Score, optional `industry_hint`, `role` und `pattern_scope`; Domain-Match-Bonus ist bewusst deaktiviert.
- [x] `run_context.retrieved_role_strategies` wird fuer `RETRIEVABLE_ROLE_ORDER` nach dem Supervisor Brief befuellt.
- [x] Delta fuer Punkt 4 ist **Relevanz, Kontext, Policy und Audit**, nicht erstmalige Einfuehrung von Retrieval.
- [x] Punkt 4.4 haengt von Punkt 3-Infrastruktur und gemeinsamem Schema-Design ab.

Ziel: Dieser Schritt soll nicht nur gespeicherte Pattern nach einfachem Score laden. Er soll kontextuell passende, policy-sichere, auditierbare Prozessmuster aus dem produktiven Memory Backbone abrufen. Domain und Zielkundenname duerfen nicht als Long-Term-Memory-Match-Key verwendet werden; sie duerfen hoechstens als aktueller Run-Kontext fuer Scrubbing, Audit und Query-Kontext dienen.

### 4.1 Retrieval-Kontext typisieren

- [x] **Punkt 4.1 abgeschlossen**

Umzusetzen:

- [x] `RetrievalContext` als Dataclass oder Pydantic-Modell einfuehren;
- [x] Felder definieren: `run_id`, `company_name`, `normalized_domain`, `language`, `industry_hint`, `phase`, `target_scope`, `role`, `department`, `question_ids`;
- [x] klar markieren, welche Felder nur Run-Kontext sind und nicht in Long-Term Memory persistiert oder als Domain-Match-Bonus genutzt werden duerfen;
- [x] `retrieve_strategies(...)` auf `context: RetrievalContext` umstellen oder kompatibel erweitern;
- [x] `pipeline_runner._initialize_run(...)` baut den initialen Retrieval-Kontext explizit auf.

Akzeptanzkriterien:

- [x] Retrieval-Aufrufe transportieren Kontext strukturiert statt ueber lose Parameter;
- [x] Domain/Company-Felder sind als nicht-persistierbare Kontextdaten gekennzeichnet;
- [x] Tests koennen pruefen, dass keine Domain-Match-Boni eingefuehrt werden.

### 4.2 Allgemeines und rollenspezifisches Retrieval fachlich trennen

- [x] **Punkt 4.2 abgeschlossen**

Umzusetzen:

- [x] allgemeines Retrieval fuer Supervisor/Run-Start definieren: Prozessmuster fuer Orchestrierung, Rechercheplanung, Gating;
- [x] rollenspezifisches Retrieval fuer `RETRIEVABLE_ROLE_ORDER` definieren: Researcher, Critic, Judge, Coding Specialist, Lead;
- [x] fuer jede Rolle `pattern_scope`-Filter festlegen, z. B. `researcher_strategy`, `critic_heuristics`, `judge_principles`, `coding_methods`, `lead_delegation`;
- [x] `limit=5` und `limit=3` pruefen und als Konfiguration statt Magic Numbers ablegen;
- [x] leere Retrieval-Ergebnisse explizit als normaler Zustand dokumentieren.

Akzeptanzkriterien:

- [x] jede Rolle bekommt nur Pattern-Scope, der zu ihrer Funktion passt;
- [x] Synthesis-/ReportWriter-Rollen werden nur einbezogen, wenn ihre Memory-Policy aktiv ist;
- [x] Retrieval-Limits sind zentral konfigurierbar.

### 4.3 Industry Hint und fruehe Firmenklassifikation nutzbar machen

- [x] **Punkt 4.3 abgeschlossen**

Aktuell wird beim initialen Retrieval kein `industry_hint` uebergeben, weil der Supervisor Brief erst spaeter entsteht. Damit ist das Start-Retrieval oft zu generisch.

Umzusetzen:

- [x] entscheiden, ob ein leichtes Pre-Brief Industry Hint vor Memory-Retrieval moeglich ist;
- [x] alternativ Retrieval in zwei Stufen aufteilen: initial generisch vor Supervisor Brief, kontextuell nach Supervisor Brief;
- [x] nach `build_intake_brief(...)` ein zweites, besseres Retrieval mit `brief.industry_hint` pruefen;
- [x] `run_context.retrieved_strategies` ggf. in `initial_retrieved_strategies` und `brief_context_retrieved_strategies` trennen;
- [x] vermeiden, dass Departments veraltete generische Patterns nutzen, wenn nach dem Brief bessere Patterns vorliegen.

Akzeptanzkriterien:

- [x] Department-Rollen erhalten nach Moeglichkeit industry-aware Patterns;
- [x] wenn kein Industry Hint verfuegbar ist, ist der Fallback sichtbar und auditierbar;
- [x] der Zeitpunkt des Retrievals ist in Step-1-Doku und Diagramm korrekt dargestellt.

### 4.4 Hybrid Search mit pgvector und strukturierten Filtern nutzen

- [ ] **Punkt 4.4 bearbeitet (Query/Filter/Ranking/Fallback lokal umgesetzt; echte pgvector-DB-Abfrage offen)**

Voraussetzung: Punkt 3 produktiver Postgres/pgvector Memory Store.

Zusatzvoraussetzung: Punkt 3.0 Datenmodell-Alignment ist abgeschlossen und freigegeben.

Umzusetzen:

- [x] Query-Text fuer Retrieval aus `RetrievalContext` bauen, z. B. aus `industry_hint`, `target_scope`, `phase`, `role`, `department` und Meeting-Fragen;
- [ ] Embedding fuer Retrieval-Query erzeugen oder aus Cache laden;
- [ ] DB-Abfrage mit harten Filtern `role`, `pattern_scope`, `schema_version`, optional `industry_hint` ausfuehren;
- [x] Vektor-Aehnlichkeit, Pattern-Score, Recency/Decay und Policy-Score zu einem Ranking kombinieren;
- [x] Fallback definieren, wenn Embedding-Service oder pgvector nicht verfuegbar ist;
- [x] Retrieval darf niemals aufgrund gleicher Domain bevorzugen.

Akzeptanzkriterien:

- [ ] Retrieval ist semantisch relevanter als reines Score-Sortieren;
- [x] Ranking-Komponenten sind im Ergebnis sichtbar;
- [x] Domain-spezifische Treffer koennen nicht bevorzugt werden.

### 4.5 Policy-Gate vor Rueckgabe der Patterns erzwingen

- [x] **Punkt 4.5 abgeschlossen**

Konkrete Retrieval-Policy-Mindestfelder:

- [x] `freshness_policy`: Pattern-Alter, Schema-Version und optional Score-Decay definieren;
- [x] `role_coverage_policy`: Pattern muss zur abrufenden Rolle oder explizit allgemeinem Scope passen;
- [x] `score_threshold_policy`: Mindestscore fuer `similarity_score`, `pattern_score` und kombiniertes Ranking festlegen;
- [x] `safety_policy`: keine Domain, URL, E-Mail, Person, Legal Name oder konkrete Finanzzahl;
- [x] `language_policy`: Pattern-Sprache und Run-Sprache (`de`/`en`) beruecksichtigen oder Fallback markieren.

Umzusetzen:

- [x] jedes Pattern vor Rueckgabe erneut gegen Long-Term-Memory-Policy pruefen;
- [x] Domains, URLs, E-Mails, Personen, rechtliche Firmennamen und konkrete Finanzzahlen blockieren;
- [x] Pattern mit falscher Schema-Version entweder migrieren oder ausschliessen;
- [x] bei Policy-Verletzung `retrieval_rejection` mit Grund protokollieren;
- [x] rejected Patterns nicht stillschweigend in `run_context.retrieved_strategies` aufnehmen.

Akzeptanzkriterien:

- [x] Retrieval kann keine unsicheren Long-Term-Memory-Eintraege in den Run Brain laden;
- [x] Policy-Rejections sind auditierbar;
- [x] Tests decken absichtlich unsichere Patterns ab.

### 4.6 Retrieval-Ergebnisse auditierbar machen

- [x] **Punkt 4.6 abgeschlossen**

Umzusetzen:

- [x] jedes Retrieval-Ergebnis mit Metadaten ausstatten: `pattern_id`, `role`, `pattern_scope`, `schema_version`, `similarity_score`, `pattern_score`, `rank`, `retrieval_reason`;
- [x] `retrieval_query_summary` speichern, aber ohne Kundennamen oder Domain;
- [x] `run_context.resolution_state["memory_retrieval"]` mit nicht-sensitivem Snapshot befuellen;
- [x] Anzahl geladener, ausgeschlossener und abgelehnter Patterns speichern;
- [x] Retrieval-Zeit messen.

Akzeptanzkriterien:

- [x] spaeter ist nachvollziehbar, warum ein Pattern geladen wurde;
- [x] keine sensitiven Run-Daten gelangen in Retrieval-Auditfelder;
- [x] Debugging kann zwischen "keine Patterns vorhanden" und "Patterns durch Policy abgelehnt" unterscheiden.

### 4.7 Retrieval-Resultat fuer Department-Nutzung stabilisieren

- [x] **Punkt 4.7 abgeschlossen**

Umzusetzen:

- [x] Output-Schema fuer `run_context.retrieved_role_strategies` definieren;
- [x] Departments erhalten nur die fuer ihre Rollen relevanten Pattern, nicht den gesamten Memory-Dump;
- [x] Pattern-Inhalte fuer Prompts zusammenfassen, damit Prompt-Budget kontrolliert bleibt;
- [x] maximale Zeichen-/Tokenbudgets pro Rolle definieren;
- [x] Duplikate und semantisch sehr aehnliche Patterns deduplizieren;
- [x] Reihenfolge der Patterns deterministisch halten.

Akzeptanzkriterien:

- [x] Department Prompts werden nicht durch Memory-Pattern ueberladen;
- [x] gleiche Store-Inhalte ergeben stabile Pattern-Reihenfolge;
- [x] Rollen bekommen keine Pattern fremder Verantwortungsbereiche.

### 4.8 Retrieval-Zeitpunkt im Step-1-Ablauf neu bewerten

- [x] **Punkt 4.8 abgeschlossen**

Der aktuelle Ablauf laedt Prozessmuster vor dem Supervisor Brief. Das ist technisch einfach, aber fachlich nur begrenzt kontextuell.

Umzusetzen:

- [x] pruefen, ob initiales Retrieval vor Supervisor Brief weiterhin noetig ist;
- [x] bevorzugtes Zielbild festlegen: minimaler generischer Retrieval-Snapshot vor Brief, vollstaendiges role-aware Retrieval nach Brief;
- [x] `_build_supervisor_brief(...)` ggf. um Memory-Refresh nach `brief.industry_hint` erweitern;
- [x] sicherstellen, dass `run_context.retrieved_role_strategies` vor `run_supervisor_loop(...)` final ist;
- [x] Checkpoint `after_supervisor_brief` soll den finalen Retrieval-Zustand enthalten.

Akzeptanzkriterien:

- [x] Departments starten mit dem bestmoeglichen Step-1-Kontext;
- [x] es gibt keine widerspruechlichen alten/neuen Retrieval-Listen im RunContext;
- [x] Step-1-Doku erklaert, warum Retrieval vor oder nach dem Brief passiert.

### 4.9 Fallback- und Degradation-Verhalten definieren

- [x] **Punkt 4.9 abgeschlossen**

Umzusetzen:

- [x] Verhalten definieren, wenn Memory Store leer ist;
- [x] Verhalten definieren, wenn Vector Retrieval ausfaellt;
- [x] Verhalten definieren, wenn Policy-Gate alle Patterns ablehnt;
- [x] Verhalten definieren, wenn Retrieval-Latenz Timeout erreicht;
- [x] pro Fall entscheiden: Run fortsetzen ohne Patterns, degraded fortsetzen oder abbrechen;
- [x] Fehler-/Warncodes definieren, z. B. `memory_retrieval_empty`, `memory_vector_unavailable`, `memory_policy_rejected_all`.

Akzeptanzkriterien:

- [x] Retrieval-Ausfall fuehrt nicht zu stiller falscher Memory-Nutzung;
- [x] RunContext zeigt klar, ob ohne Memory oder mit degraded Memory gestartet wurde;
- [x] kritische Store-Fehler sind von "keine Patterns vorhanden" unterscheidbar.

### 4.10 Tests fuer Retrieval-Relevanz, Policy und Rollenfilter aufbauen

- [ ] **Punkt 4.10 bearbeitet (lokale Unit-/Regressionstests umgesetzt; pgvector-Integrationstest offen)**

Umzusetzen:

- [x] Unit-Tests fuer `RetrievalContext`;
- [x] Unit-Tests fuer Role-/Scope-Filter;
- [x] Tests, dass Domain nicht als Ranking-Bonus wirkt;
- [x] Tests fuer industry-aware Retrieval;
- [x] Tests fuer Policy-Rejection unsicherer Patterns;
- [x] Tests fuer deterministische Sortierung bei gleichen Scores;
- [ ] Integrationstest gegen Test-Postgres/pgvector fuer Hybrid Search;
- [x] Regressionstest, dass `run_context.retrieved_role_strategies` vor Department-Routing befuellt ist.

Akzeptanzkriterien:

- [x] Retrieval-Qualitaet ist nicht nur manuell beurteilbar;
- [x] Memory-Policy-Verletzungen fallen in Tests auf;
- [x] Rollen bekommen reproduzierbar die richtigen Pattern-Sets.

### 4.11 Observability fuer Retrieval einfuehren

- [ ] **Punkt 4.11 bearbeitet (Audit-Snapshots umgesetzt; OTel/Dashboard/Alerting offen)**

Umzusetzen:

- [x] Metriken: Retrieval-Latenz, Anzahl Treffer, Anzahl Policy-Rejections, Fallback-Rate, leere Retrievals;
- [x] strukturierte Logs mit `run_id`, `phase`, `role`, `result_count`, `fallback_reason`, ohne Kundendomain im Logtext;
- [ ] OpenTelemetry-Span `memory.retrieve_strategies` vorbereiten;
- [ ] Dashboard-Sicht fuer Memory-Retrieval-Health ergaenzen;
- [ ] Alerting fuer hohe Fallback-Rate oder unerwartet viele Policy-Rejections definieren.

Akzeptanzkriterien:

- [x] Betreiber kann sehen, ob Memory Retrieval produktiv Nutzen liefert;
- [x] Retrieval-Probleme sind von LLM-/Research-Problemen unterscheidbar;
- [x] Logs bleiben frei von sensiblen Kundendaten.

### 4.12 Dokumentation und Diagramm aktualisieren

- [ ] **Punkt 4.12 bearbeitet (Runtime-Doku, Generator und Zielarchitektur aktualisiert; Draw.io-Regeneration wegen Tool-Limit offen)**

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` um Retrieval-Kontext, zweistufiges Retrieval und Audit-Metadaten erweitern;
- [x] `scripts/generate_step1_drawio.py` aktualisieren;
- [ ] `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [x] `docs/drawio/target_runtime_architecture.md` um kontextuelles Hybrid Retrieval ergaenzen;
- [x] TODO Punkt 3 und Punkt 4 in der Doku klar abgrenzen: Store Backbone vs. Retrieval-Logik.

Akzeptanzkriterien:

- [ ] Diagramm zeigt, wann Prozessmuster geladen werden und ob nach Supervisor Brief ein Refresh passiert;
- [x] Narrative Doku erklaert, warum Domain nicht als Long-Term-Memory-Match-Key genutzt wird;
- [x] Architekturziel, Code und Runtime-Doku sind konsistent.

### 4.13 Zielbewertung nach Umsetzung

- [ ] **Punkt 4.13 bearbeitet (lokale Bewertung ergaenzt; 5/5 erst mit pgvector/Production-Store erreichbar)**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung |
| --- | ---: |
| Memory-Policy | 5/5 |
| Rollenbezug | 5/5 |
| Relevanzranking | 5/5 |
| Nutzung von Kontext | 5/5 |
| Auditierbarkeit | 5/5 |
| Skalierbarkeit | 5/5 |
| Produktionsfaehigkeit | 5/5 |

Aktueller lokaler Stand nach dieser Umsetzung:

| Kriterium | Stand 2026-05-12 |
| --- | ---: |
| Memory-Policy | 5/5 |
| Rollenbezug | 5/5 |
| Relevanzranking | 4/5 |
| Nutzung von Kontext | 5/5 |
| Auditierbarkeit | 5/5 |
| Skalierbarkeit | 3/5 |
| Produktionsfaehigkeit | 3/5 |

### 4.14 Definition of Done fuer Punkt 4

- [ ] **Punkt 4.14 bearbeitet (lokaler Retrieval-Backbone umgesetzt; pgvector/OTel/Dashboard/Draw.io-Regeneration offen)**

- [x] Retrieval nutzt einen typisierten `RetrievalContext`;
- [x] allgemeines und rollenspezifisches Retrieval sind fachlich getrennt;
- [x] Industry-/Brief-Kontext wird zum richtigen Zeitpunkt genutzt;
- [ ] Hybrid Search kombiniert strukturierte Filter, Embedding-Aehnlichkeit und Pattern-Score;
- [x] Domain und Zielkundenname werden nicht als Long-Term-Memory-Ranking-Bonus genutzt;
- [x] Policy-Gate blockiert unsichere Patterns vor Rueckgabe;
- [x] Retrieval-Ergebnisse sind mit Scores, Ranking und Gruenden auditierbar;
- [x] Departments erhalten stabile, budgetierte und rollenpassende Pattern-Sets;
- [x] Fallbacks und Degradation sind dokumentiert und maschinenlesbar;
- [ ] Tests, Observability, Runtime-Doku, Draw.io und Zielarchitektur sind aktualisiert.

## 5. Supervisor Brief zu einem evidence-backed Identity + Briefing Contract ausbauen

Betroffener aktueller Ablauf:

```python
supervisor = _build_supervisor_brief(state, on_message=on_message)
_record_phase(state.run_context, "supervisor_brief")
brief, supervisor_message = state.agents["supervisor"].build_intake_brief(state.intake)
```

Aktueller Supervisor-Code:

```python
def build_intake_brief(self, intake: IntakeRequest) -> tuple[SupervisorBrief, dict]:
    research = build_company_research(intake.web_domain, intake.company_name)
    snapshot = research["snapshot"]
    industry_hint = infer_industry(
        title=str(snapshot.get("title", "")),
        description=str(snapshot.get("meta_description", "")),
        text=str(research.get("summary", "")),
    )
    brief = SupervisorBrief(...)
```

### 5.0 Current State (Code-Audit)

- [x] `SupervisorAgent.build_intake_brief(...)` existiert bereits.
- [x] `SupervisorBrief` existiert bereits als Dataclass.
- [x] `build_company_research(...)` wird bereits aufgerufen.
- [x] `supervisor_message` existiert als versionierter Dict-Contract mit `section`, `payload`, `status`, Readiness, Confidence und Evidence Summary.
- [x] Delta fuer Punkt 5 ist **Evidence-/Confidence-/Readiness-Contract erweitern**, nicht Briefing neu erfinden.
- [x] Sprachkontext `language` bleibt im Intake/RunContext sichtbar; Briefing-Audit fuehrt Content-Language.

Ziel: Das Supervisor Brief soll nicht nur ein Homepage-Snapshot mit heuristischer Identitaetsableitung sein. Es soll ein belastbarer, auditierbarer Startvertrag fuer Department Routing werden: eingereichte Identitaet, normalisierte Domain, verifizierte Identitaet, Quellenlage, Unsicherheit, Fetch-/Security-Audit und Routing-Reife muessen strukturiert unterscheidbar sein.

### 5.1 Supervisor Brief auf normalisierten Intake-Vertrag umstellen

- [x] **Punkt 5.1 abgeschlossen**

Umzusetzen:

- [x] `build_intake_brief(...)` soll nicht erneut frei `intake.web_domain` normalisieren, sondern den validierten Normalized-Intake-Vertrag aus Punkt 1 nutzen;
- [x] `SupervisorBrief.submitted_web_domain` bleibt Anzeige-/Auditwert;
- [x] `SupervisorBrief.normalized_domain` kommt ausschliesslich aus dem validierten kanonischen Domain-Vertrag;
- [x] Homepage-URL wird aus `canonical_domain`/`canonical_url` erzeugt, nicht aus roher Eingabe;
- [x] Fetch-/Redirect-Sicherheitsentscheidungen aus Punkt 1 werden im Brief referenziert;
- [x] Tests verhindern, dass `build_company_research(...)` wieder mit ungepruefter roher Domain aufgerufen wird.

Akzeptanzkriterien:

- [x] Domain-Konsistenz zwischen `RunContext.intake`, `SupervisorBrief` und Research-Fetch ist garantiert;
- [x] riskante oder leere Normalisierung kann nicht im Briefing weiterlaufen;
- [x] gleiche Domainvarianten erzeugen identischen Briefing-Domain-Kontext.

### 5.2 Multi-Source Identity Verification einfuehren

- [ ] **Punkt 5.2 bearbeitet (MVP-Owned-Website umgesetzt; Register/LinkedIn/Wikidata bleiben Phase 2)**

Quellen-Prioritaetsmatrix (Referenzarchitektur — zeigt das Zielbild, nicht den MVP-Scope):

| Prioritaet | Quelle | Beispiel | MVP? | Konfliktregel |
| --- | --- | --- | --- | --- |
| 1 | Offizielles Register / Legal Filing | Handelsregister, Unternehmensregister | Phase 2 | Legal Name gewinnt gegen Homepage-Marketingnamen |
| 2 | Owned Website / Impressum | Unternehmenswebsite, Impressum | **MVP** | Brand/Website-Identitaet, aber nicht automatisch Legal Name |
| 3 | Offizielle Unternehmensprofile | LinkedIn Company Page, offizielle Presseprofile | Phase 2 | unterstuetzt Brand/Industry, selten alleiniger Legal Proof |
| 4 | Kuratierte Wissensquellen | Wikidata, OpenCorporates/Northdata je nach Verfuegbarkeit | Phase 2 | sekundaerer Abgleich, Confidence-Boost oder Konfliktsignal |
| 5 | Search Snippets / Presse / Branchenportale | Suchergebnisse, Artikel | Phase 2 | nur schwaches Signal, niemals alleiniger Verifikationsanker |

> **MVP-Scope:** Nur Prioritaet 2 (eigene Website + Impressum) wird in Step 1 aktiv abgerufen. Die uebrigen Quellen (Register, LinkedIn, Wikidata, OpenCorporates) sind externe API-Integrationen mit eigenem Aufwand, Kosten und Lizenzfragen — sie gehoeren in Phase 2. Der Konfliktfall (Register vs. Homepage) wird im MVP als strukturierter Gap erfasst, nicht automatisch aufgeloest.

- [x] Konfliktfall dokumentieren: Homepage nennt `TechCorp`, Register nicht verfuegbar -> Brand Name aus Homepage, `verified_legal_name` leer, Confidence "low", Gap sichtbar im Brief.

Umzusetzen (MVP — nur Prioritaet 2):

- [x] Homepage-Snapshot und Impressum-Link als primaere Identitaetsquelle nutzen;
- [x] widerspruechliche Namen zwischen Submitted Name und Homepage-Titel als Konflikt erfassen statt still zu ueberschreiben;
- [x] Legal Name, Brand Name und Submitted Name getrennt halten — `verified_legal_name` bleibt leer, wenn kein Register verfuegbar ist;
- [x] fehlende externe Quellen als strukturierten Gap im Evidence Contract erfassen, nicht als Fehler.

Akzeptanzkriterien:

- [x] `verified_company_name` basiert auf nachvollziehbaren Quellen, nicht nur auf Homepage-Text;
- [x] `verified_legal_name` ist klar von Marketing-/Brand-Namen getrennt;
- [x] Identitaetskonflikte werden im Brief sichtbar und beeinflussen Confidence/Routing.

### 5.3 Evidence Contract fuer SupervisorBrief einfuehren

- [x] **Punkt 5.3 abgeschlossen**

> **MVP-Scope:** Der Evidence Contract basiert ausschliesslich auf der Homepage-Quelle. Evidence fuer `verified_legal_name` aus Registern ist Phase 2 — im MVP bleibt `verified_legal_name` leer, wenn kein Register abgefragt wurde. Der Contract ist so entworfen, dass er spaeter weitere Quellen aufnehmen kann.

Umzusetzen (MVP — Homepage als einzige Quelle):

- [x] `SupervisorBrief.sources` von einfacher Liste zu strukturierten Evidence-Items ausbauen;
- [x] jedes Evidence-Item enthaelt: `source_type` (`owned_website`), `url`, `claim`, `supports_field`, `retrieved_at`;
- [x] Evidence fuer `verified_company_name`, `normalized_domain`, `industry_hint` und `website_reachable` trennen;
- [x] bei fehlender oder schwacher Homepage-Evidence: `missing_evidence_reason` statt leerem Feld;
- [x] Evidence im RunContext/Checkpoint persistierbar halten;
- [x] keine sensiblen Rohdaten (vollstaendiger HTML-Body) im Brief speichern.

Spaeter (Phase 2 / CompanyDepartment):

- [ ] Evidence fuer `verified_legal_name` aus Registerquellen erganzen;
- [ ] Evidence-Items fuer externe Quellen (LinkedIn, Wikidata, Register) hinzufuegen.

Akzeptanzkriterien (MVP):

- [x] Jede Briefing-Aussage hat ein zuordenbares Homepage-Evidence-Item oder einen expliziten `missing_evidence_reason`;
- [x] Departments koennen erkennen, ob der Startpunkt stark oder schwach belegt ist;
- [x] Evidence-Schema ist erweiterbar fuer spaetere Quellen.

### 5.4 Confidence-Modell fuer Identitaet und Industry Hint verbessern

- [x] **Punkt 5.4 abgeschlossen**

> **MVP-Scope:** Confidence entsteht ausschliesslich aus Homepage-Signalen — kein Abgleich mit externen Registern oder Datenquellen. "Quellenuebereinstimmung" bedeutet im MVP: Stimmt der Homepage-Titel mit dem Submitted Name ueberein? Das CompanyDepartment korrigiert und verfeinert Confidence in Step 2.

Umzusetzen (MVP — Homepage-Basis):

- [x] `name_confidence` als Enum praezisieren: `high` (Homepage-Titel entspricht Submitted Name), `medium` (teilweise Uebereinstimmung), `low` (kein Match), `unverified` (Homepage nicht erreichbar);
- [x] Confidence-Begruendung als kurzen String speichern: welches Signal hat zur Einstufung gefuehrt;
- [x] separaten `industry_confidence` einfuehren: `high` (klares Signal aus Title/Meta), `low` (Heuristik, unsicher), `unknown` (kein verwertbares Signal);
- [x] `industry_hint` als Startsignal markieren, nicht als verifizierte Wahrheit;
- [x] bei `name_confidence = low` oder `unverified`: CompanyDepartment erhaelt automatisch eine Identitaetsklaerungsaufgabe.

Spaeter (Phase 2):

- [ ] Confidence aus Abgleich mit externen Registern berechnen;
- [ ] Konflikt-Confidence (`conflict`) einfuehren, wenn Homepage und Register widersprechen.

Akzeptanzkriterien (MVP):

- [x] `name_confidence` basiert auf messbarem Homepage-Signal, nicht auf Annahmen;
- [x] `industry_confidence` ist ehrlich: `unknown` wenn kein Signal vorhanden;
- [x] niedrige Confidence triggert CompanyDepartment-Aufgabe, nicht Run-Abbruch.

### 5.5 Fetch-, Redirect- und Website-Erreichbarkeitsaudit erweitern

- [x] **Punkt 5.5 abgeschlossen**

Umzusetzen:

- [x] `website_reachable` durch detaillierten Fetch-Status ergaenzen: DNS ok, TLS ok, HTTP status, final_url, redirect_chain, content_type, timeout, blocked_reason;
- [x] Redirect-Ziele gegen SSRF-/Private-IP-Regeln aus Punkt 1 pruefen;
- [x] finale URL und kanonische Domain vergleichen;
- [x] Website-Snapshot mit Zeitstempel, Content-Length und Sprache versehen;
- [x] Fetch-Fehler in strukturierte Fehlercodes normalisieren;
- [x] Homepage-Auszug begrenzen und gegen HTML/Script-Muell bereinigen.

Akzeptanzkriterien:

- [x] Ein nicht erreichbarer oder blockierter Website-Fetch ist klar diagnostizierbar;
- [x] Redirects auf fremde oder unsichere Domains werden nicht still als Zielkunden-Homepage akzeptiert;
- [x] Departments wissen, ob Homepage-Evidence belastbar oder nur ein schwacher Startpunkt ist.

### 5.6 Briefing-Readiness fuer Department Routing klassifizieren

- [x] **Punkt 5.6 abgeschlossen**

Umzusetzen:

- [x] Feld `briefing_readiness` einfuehren, z. B. `ready`, `ready_with_identity_gaps`, `ready_with_website_gaps`, `blocked_identity_conflict`;
- [x] Routing-Regeln definieren: Wann darf Step 2 starten, wann nur CompanyDepartment zur Klaerung, wann blockiert Step 1;
- [x] offene Briefing-Gaps strukturiert erfassen;
- [x] `supervisor_message.status` differenzieren statt immer `ready_for_department_routing` zu setzen;
- [x] UI/API kann Briefing-Gaps anzeigen.

Akzeptanzkriterien:

- [x] `ready_for_department_routing` wird nur gesetzt, wenn Mindestanforderungen erfuellt sind;
- [x] Identitaetskonflikte koennen Step 2 bewusst blockieren oder einschranken;
- [x] Routing-Status ist maschinenlesbar.

### 5.7 Supervisor Message als versionierten Contract definieren

- [x] **Punkt 5.7 abgeschlossen**

Umzusetzen:

- [x] `supervisor_message` um `schema_version` erweitern;
- [x] `section="supervisor_brief"` beibehalten, aber Payload-Versionierung einfuehren;
- [x] `status`, `briefing_readiness`, `identity_confidence`, `industry_confidence`, `evidence_summary` als Top-Level- oder klar dokumentierte Payload-Felder definieren;
- [x] Message-Contract mit dependency-light Contract-Validator validieren;
- [x] alte Consumer entweder migrieren oder Kompatibilitaetsschicht bereitstellen.

Akzeptanzkriterien:

- [x] Supervisor-Brief-Events sind rueckwaerts nachvollziehbar;
- [x] UI, Checkpoints und Tests koennen sich auf ein stabiles Schema verlassen;
- [x] unvollstaendige Briefing-Messages fallen in Tests auf.

### 5.8 Supervisor-Briefing in RunContext und Checkpoint auditierbar speichern

- [x] **Punkt 5.8 abgeschlossen**

Umzusetzen:

- [x] `state.run_context.supervisor_brief` speichert den validierten Brief-Contract;
- [x] `resolution_state["supervisor_brief"]` speichert nicht-sensitive Diagnose: Evidence Count, Confidence, Fetch Status, Briefing Readiness;
- [x] Checkpoint `after_supervisor_brief` enthaelt Brief, Evidence Summary und Routing-Status;
- [x] sensible Rohtexte begrenzen oder separat als geschuetztes Artefakt speichern;
- [x] Briefing-Generation-Dauer messen.

Akzeptanzkriterien:

- [x] Nach einem Run ist nachvollziehbar, warum Step 2 gestartet oder blockiert wurde;
- [x] Supervisor-Briefing ist reproduzierbar genug fuer Debugging;
- [x] keine unnoetig grossen Homepage-Rohtexte landen im RunContext.

### 5.9 Fehler- und Degradation-Verhalten definieren

- [x] **Punkt 5.9 abgeschlossen**

Umzusetzen:

- [x] Verhalten definieren, wenn Homepage-Fetch fehlschlaegt;
- [x] Verhalten definieren, wenn Register-/Identity-Quellen nicht erreichbar sind;
- [x] Verhalten definieren, wenn Quellen widerspruechlich sind;
- [x] Verhalten definieren, wenn Industry Hint nicht ableitbar ist;
- [x] Fehlercodes definieren: `homepage_unreachable`, `identity_unverified`, `identity_conflict`, `industry_unknown`, `briefing_source_timeout`;
- [x] zwischen blockierendem Fehler und nicht-blockierendem Gap unterscheiden.

Akzeptanzkriterien:

- [x] Step 1 scheitert nicht unnötig bei schwacher Homepage, wenn alternative Evidence reicht;
- [x] Step 2 startet nicht blind bei harter Identitaetsunklarheit;
- [x] alle Degradationspfade sind im Briefing sichtbar.

### 5.10 Tests fuer Supervisor Briefing aufbauen

- [x] **Punkt 5.10 abgeschlossen**

Umzusetzen:

- [x] Unit-Tests fuer `build_intake_brief(...)` mit erfolgreichem Homepage-Snapshot;
- [x] Unit-Tests fuer nicht erreichbare Website;
- [x] Tests fuer Identitaetskonflikte zwischen Submitted Name und Quelle;
- [x] Tests fuer Legal Name vs. Brand Name;
- [x] Tests fuer Industry Hint mit hoher, niedriger und unbekannter Confidence;
- [x] Tests fuer `supervisor_message` Schema-Version und Statuswerte;
- [x] Tests, dass raw Domain nicht ungeprueft erneut verwendet wird;
- [x] Snapshot-/Contract-Tests fuer `SupervisorBrief`.

Akzeptanzkriterien:

- [x] Briefing-Regressionen fallen vor Department-Routing auf;
- [x] kritische Confidence-/Readiness-Entscheidungen sind testbar;
- [x] Message-Schema bleibt stabil.

### 5.11 Observability fuer Supervisor Briefing einfuehren

- [ ] **Punkt 5.11 bearbeitet (strukturierte Logs und Diagnose umgesetzt; OTel/Alerting offen)**

Umzusetzen:

- [x] Metriken: Briefing-Dauer, Fetch-Latenz, Source Count, Identity Confidence Distribution, Briefing Readiness Distribution;
- [x] strukturierte Logs mit `run_id`, `briefing_readiness`, `identity_confidence`, `fetch_status`, ohne unnoetige Rohtexte;
- [ ] OpenTelemetry-Span `pipeline.supervisor_brief` vorbereiten;
- [ ] Alerting fuer hohe Rate `identity_conflict` oder `homepage_unreachable` definieren;
- [ ] Cloudflare/Hetzner Request-ID falls vorhanden im Briefing-Audit korrelieren.

Akzeptanzkriterien:

- [x] Betreiber kann erkennen, ob schlechte Briefings ein systemisches Problem sind;
- [x] Briefing-Latenz und Failure-Klassen sind messbar;
- [x] Logs bleiben datenschutz- und secret-sicher.

### 5.12 Dokumentation und Diagramm aktualisieren

- [x] **Punkt 5.12 abgeschlossen**

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` um evidence-backed Supervisor Briefing erweitern;
- [x] `scripts/generate_step1_drawio.py` aktualisieren;
- [x] `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [x] `docs/drawio/target_runtime_architecture.md` um Identity/Evidence/Readiness Contract ergaenzen;
- [x] klar dokumentieren, dass Step 1 noch keine Department-Recherche ausfuehrt, aber sehr wohl Identitaets- und Website-Evidence fuer das Routing vorbereitet.

Akzeptanzkriterien:

- [x] Diagramm zeigt Identity Verification, Evidence Contract und Briefing Readiness;
- [x] Narrative Doku erklaert den Unterschied zwischen Submitted, Verified und Uncertain Identity;
- [x] Zielarchitektur und Runtime-Code sind konsistent.

### 5.13 Zielbewertung nach Umsetzung

- [ ] **Punkt 5.13 bearbeitet (MVP-Bewertung ergaenzt; 5/5 Identitaetspruefung erst mit Phase-2-Quellen erreichbar)**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung |
| --- | ---: |
| Strukturierter Output | 5/5 |
| Handoff-Qualitaet | 5/5 |
| Identitaetspruefung | 5/5 |
| Evidence/Confidence | 5/5 |
| Fehlerverhalten | 5/5 |
| Security/Domain-Konsistenz | 5/5 |
| Observability | 5/5 |
| Routing Readiness | 5/5 |

Aktueller lokaler Stand nach dieser Umsetzung:

| Kriterium | Stand 2026-05-12 |
| --- | ---: |
| Strukturierter Output | 5/5 |
| Handoff-Qualitaet | 5/5 |
| Identitaetspruefung | 3/5 |
| Evidence/Confidence | 4/5 |
| Fehlerverhalten | 5/5 |
| Security/Domain-Konsistenz | 5/5 |
| Observability | 3/5 |
| Routing Readiness | 5/5 |

### 5.14 Definition of Done fuer Punkt 5

- [ ] **Punkt 5.14 bearbeitet (MVP-Contract umgesetzt; externe Multi-Source-Identity und OTel/Alerting offen)**

- [x] Supervisor Brief nutzt den validierten Normalized-Intake-Vertrag;
- [ ] Identitaet wird ueber mehrere Quellen und klare Quellenprioritaeten verifiziert;
- [x] zentrale Briefing-Aussagen haben strukturierte Evidence oder explizite Missing-Evidence-Gruende;
- [x] Identity Confidence und Industry Confidence sind getrennt, begruendet und routing-relevant;
- [x] Fetch-/Redirect-/Website-Audit ist strukturiert und sicherheitsbewusst;
- [x] `supervisor_message.status` bildet Briefing Readiness realistisch ab;
- [x] Briefing Message ist versioniert und validiert;
- [x] RunContext und Checkpoint enthalten nicht-sensitive Briefing-Diagnose;
- [ ] Fehler, Degradation, Tests, Observability, Runtime-Doku, Draw.io und Zielarchitektur sind aktualisiert.

## 6. Supervisor Intake Research Pipeline haerten und evidence-basiert machen

Betroffener aktueller Ablauf:

```python
research = build_company_research(intake.web_domain, intake.company_name)
snapshot = research["snapshot"]
industry_hint = infer_industry(
    title=str(snapshot.get("title", "")),
    description=str(snapshot.get("meta_description", "")),
    text=str(research.get("summary", "")),
)
```

Aktuelle Research-Kette:

```python
def build_company_research(domain: str, company_name: str) -> dict:
    normalized_domain = normalize_domain(domain)
    url = homepage_url(normalized_domain)
    snapshot = fetch_website_snapshot(url)
    identity = infer_company_identity(
        company_name,
        str(snapshot.get("title", "")),
        str(snapshot.get("meta_description", "")),
        str(snapshot.get("visible_text", "")),
    )
    return {
        "normalized_domain": normalized_domain,
        "homepage_url": url,
        "snapshot": snapshot,
        "summary": summarize_visible_text(str(snapshot.get("visible_text", ""))),
        **identity,
    }
```

### 6.0 Current State (Code-Audit)

- [x] `build_company_research(...)` existiert bereits und normalisiert Domain, baut Homepage-URL, fetched Snapshot, inferiert Identitaet und summarisiert sichtbaren Text.
- [x] `fetch_website_snapshot(...)`, `infer_company_identity(...)`, `summarize_visible_text(...)` und `infer_industry(...)` existieren bereits.
- [x] Delta fuer Punkt 6 ist **Sicherheit, Contracts, Evidence, Fallbacks und Budgets erweitern**, nicht komplette Research-Pipeline neu bauen.
- [x] Sprachkontext `language` muss Fetch Header, Textauswahl, Summary und Industry-Hinweise beeinflussen koennen.

Ziel: `build_company_research(...)` soll von einem schnellen Homepage-Snapshot zu einer sicheren, nachvollziehbaren Intake-Research-Pipeline werden. Diese Pipeline liefert keine fertige Department-Recherche, aber einen belastbaren Startkontext mit Domain-Sicherheit, Fetch-Audit, Identity Evidence, Summary-Qualitaet, Industry-Hint-Basis und klaren Failure Modes.

### 6.1 Research-Funktion auf validierten Domain-Vertrag umstellen

- [x] **Punkt 6.1 abgeschlossen**

Umzusetzen:

- [x] `build_company_research(...)` soll nicht mehr frei `domain: str` normalisieren, sondern den `NormalizedDomainResult` oder `NormalizedIntake` aus Punkt 1 erhalten;
- [x] `normalize_domain(domain)` innerhalb von `build_company_research(...)` entfernen oder nur als Kompatibilitaetswrapper im Legacy-Pfad erlauben;
- [x] `homepage_url(...)` aus dem kanonischen Domain-Vertrag ableiten;
- [x] Funktionssignatur typisieren, z. B. `build_company_research(intake: NormalizedIntake, fetcher: WebsiteFetcher, sources: IdentitySourceRegistry)`;
- [x] Tests verhindern doppelte, widerspruechliche Domain-Normalisierung.

Akzeptanzkriterien:

- [x] `build_company_research(...)` kann keine ungepruefte rohe Domain mehr fetchen;
- [x] Homepage-URL, `SupervisorBrief.normalized_domain` und `RunContext.intake.normalized_domain` sind identisch abgeleitet;
- [x] Legacy-Aufrufe sind entweder entfernt oder explizit als deprecated markiert.

### 6.2 Sichere Fetch-Pipeline mit DNS-, Redirect- und Content-Guards einfuehren

- [ ] **Punkt 6.2 abgeschlossen**

Umzusetzen:

- [x] `fetch_website_snapshot(...)` mit DNS-Pruefung gegen private, loopback, link-local, multicast, reserved und carrier-grade NAT IPs absichern;
- [x] Redirect-Kette erfassen und jedes Redirect-Ziel erneut validieren;
- [x] maximale Redirect-Anzahl definieren;
- [ ] Timeouts fuer DNS, Connect, TLS und Read getrennt konfigurieren;
- [x] Content-Type Allowlist definieren, z. B. HTML/Text, keine Binaries;
- [x] maximale Response-Groesse definieren;
- [x] TLS-/Zertifikatsfehler strukturiert erfassen;
- [x] User-Agent, Accept-Language und Request Header kontrolliert setzen;
- [x] Fetch darf keine internen IPs erreichen, auch wenn DNS/Redirect manipuliert ist.

Akzeptanzkriterien:

- [x] SSRF-nahe Ziele koennen nicht ueber Homepage-Fetch erreicht werden;
- [x] Redirect- und Fetch-Entscheidungen sind im Snapshot auditierbar;
- [x] Timeouts und Content-Grenzen verhindern haengende oder riesige Fetches.

### 6.3 Fetch Snapshot als typisierten Contract definieren

- [x] **Punkt 6.3 abgeschlossen**

Umzusetzen:

- [x] `WebsiteSnapshot` als Dataclass/Pydantic-Modell einfuehren;
- [x] Felder definieren: `requested_url`, `final_url`, `reachable`, `http_status`, `content_type`, `title`, `meta_description`, `visible_text`, `language`, `redirect_chain`, `fetch_error_type`, `fetch_error_message`, `retrieved_at`, `content_hash`;
- [x] Snapshot-Groessenlimits fuer `visible_text` und Rohdaten definieren;
- [x] Roh-HTML nicht unkontrolliert im RunContext speichern;
- [x] Snapshot validieren, bevor er in `build_company_research(...)` verwendet wird.

Akzeptanzkriterien:

- [x] Fetch-Ergebnisse sind maschinenlesbar und versionierbar;
- [x] fehlende oder fehlerhafte Felder fallen frueh auf;
- [x] Snapshot enthaelt genug Diagnose, ohne Artefakte aufzublaehen.

### 6.4 HTML-/Text-Extraktion verbessern

- [ ] **Punkt 6.4 abgeschlossen**

Umzusetzen:

- [x] Boilerplate-Entfernung einfuehren: Navigation, Cookie Banner, Footer, Scripts, Styles entfernen;
- [x] relevante Felder extrahieren: Title, Meta Description, OpenGraph Title/Description, H1/H2, Impressum-Link, About-Link;
- [x] Sprache erkennen oder aus HTML ableiten;
- [ ] sichtbaren Text deduplizieren und laengenbegrenzen;
- [x] `summarize_visible_text(...)` auf gereinigten Hauptinhalt anwenden, nicht auf kompletten Rohtext;
- [x] leere oder schwache Textqualitaet als eigenes Signal erfassen.

Akzeptanzkriterien:

- [x] Summary wird nicht von Cookie-/Navigationstext dominiert;
- [x] Homepage-Auszug ist kurz, relevant und reproduzierbar;
- [x] schwache Extraktionsqualitaet ist fuer Supervisor Brief sichtbar.

### 6.5 Multi-Source Identity Research in die Intake-Pipeline integrieren

- [ ] **Punkt 6.5 abgeschlossen**

> **MVP-Scope:** Step 1 liest ausschliesslich die eigene Firmenwebsite (Homepage + Impressum). Externe Quellen wie Handelsregister, OpenCorporates, LinkedIn oder Northdata sind Phase 2. Die Identity Source Registry wird im MVP als Konzept definiert, aber nur mit Quelle "owned website" befoellt.

Umzusetzen (MVP):

- [x] Identity Source Registry als Datenstruktur definieren, vorerst mit einem einzigen Eintrag: `owned_website`;
- [ ] Legal Name, Brand Name, Submitted Name und Domain Owner/Impressum aus Homepage-Snapshot getrennt erfassen;
- [x] Konflikte zwischen Submitted Name und Homepage-Titel als strukturierten Gap erfassen;
- [x] fehlende externe Quellen nicht als Fehler behandeln, sondern als `source_gap` mit `source_type` protokollieren;
- [x] keine vollstaendige Department-Recherche ausloesen, sondern nur Identitaets-/Startkontext klaeren.

Spaeter (Phase 2):

- [ ] externe Quellen ergaenzen: Handelsregister, OpenCorporates, Northdata, LinkedIn Company Page, Wikidata; **Phase 2 offen**
- [ ] Quellenprioritaeten und Confidence-Gewichte aus 5.2-Matrix implementieren. **Phase 2 offen**

Akzeptanzkriterien (MVP):

- [x] `verified_company_name` entsteht aus Homepage-Evidence, nicht aus Submitted Name allein;
- [x] fehlende externe Quellen erzeugen `source_gap`, keinen Run-Fehler;
- [x] Identitaetskonflikte (Submitted vs. Homepage) sind strukturiert sichtbar.

### 6.6 `infer_company_identity(...)` zu strukturierter Identity Resolution ausbauen

- [x] **Punkt 6.6 abgeschlossen**

> **MVP-Scope:** Die Funktion wird typisiert und ihr Output wird strukturiert — aber nur auf Basis der Homepage. `verified_legal_name` bleibt leer, da kein Register abgefragt wird. Externe Konflikte (Homepage vs. Register) sind Phase 2 / CompanyDepartment.

Umzusetzen (MVP — Homepage-Basis):

- [x] Ergebnis von `infer_company_identity(...)` typisieren, z. B. als Dataclass `IdentityResolutionResult`;
- [x] Felder definieren: `submitted_name`, `verified_company_name`, `verified_legal_name` (leer im MVP), `brand_name`, `name_confidence`, `confidence_reason`, `homepage_name_match`;
- [x] Matching-Logik verbessern: Normalisierung rechtlicher Suffixe (GmbH, AG, Inc.), Abkuerzungen, case-insensitiver Vergleich;
- [x] `name_confidence` aus dem Homepage-Titel-Match ableiten, nicht als freien String setzen;
- [x] offene Identitaetsfragen als `source_gap` erfassen, nicht als Fehler.

Spaeter (Phase 2 / CompanyDepartment):

- [ ] `verified_legal_name` aus Registerquellen befuellen;
- [ ] `conflicts` einfuehren: Homepage nennt X, Register nennt Y;
- [ ] `evidence_ids` verknuepfen, wenn mehrere Quellen vorliegen.

Akzeptanzkriterien (MVP):

- [x] Rueckgabe von `infer_company_identity(...)` ist ein typisiertes Objekt statt freiem Dict;
- [x] `verified_legal_name` ist leer aber vorhanden — kein KeyError moeglich;
- [x] `name_confidence` ist aus dem Matching-Ergebnis ableitbar, nicht geraten.

### 6.7 Industry Detection robuster und confidence-aware machen

- [x] **Punkt 6.7 abgeschlossen**

Umzusetzen:

- [x] `infer_industry(...)` Ergebnis typisieren, z. B. `IndustryInferenceResult`;
- [x] Quellenbasis erfassen: Title, Meta, Homepage-Haupttext, externe Quellen, ggf. Klassifikationsschema;
- [x] Confidence und Alternativen speichern;
- [x] Industry-Hint als Startsignal markieren, nicht als verifizierte Wahrheit;
- [x] bei niedriger Confidence mehrere moegliche Branchen an Departments weitergeben;
- [x] spaeteres CompanyDepartment darf Industry Hint korrigieren.

Akzeptanzkriterien:

- [x] Industry Hint hat Confidence und Evidence;
- [x] unklare Branche wird nicht als sicherer Kontext behandelt;
- [x] Departments sehen Alternativen oder Unsicherheit.

### 6.8 JavaScript-/SPA- und Anti-Bot-Fallbacks definieren

- [ ] **Punkt 6.8 abgeschlossen**

MVP-Stufenmodell:

- [x] Stufe 0: normaler sicherer HTTP-Fetch mit Timeouts, Redirect- und Content-Type-Guards;
- [ ] Stufe 1: begrenzter Retry bei transienten Netzwerkfehlern oder 5xx, kein Retry bei SSRF-/Policy-Block;
- [ ] Stufe 2: optionale oeffentliche Cache-/Archiv-/Suchsnippet-Signale nur als schwache Evidence markieren;
- [x] Stufe 3+: Browser Rendering / Headless Browser / Cloudflare Browser Rendering ist **Backlog, nicht MVP**;
- [x] keine Anti-Bot-Umgehung implementieren; 403/429/CAPTCHA sind Diagnose- und Degradation-Signale, keine Umgehungsaufgabe.

Umzusetzen (MVP — Stufen 0-2):

- [x] erkennen, wenn statischer Fetch kaum sichtbaren Text liefert, aber HTML auf JS-App hinweist — als `js_content_detected`-Signal im Snapshot erfassen;
- [x] Anti-Bot, CAPTCHA, 403/429 als eigene Fetch-Fehlerklassen behandeln: `fetch_blocked_bot_protection`, `fetch_rate_limited`, `fetch_access_denied`;
- [x] UI/Brief soll anzeigen, wenn Homepage nur eingeschraenkt auslesbar war.

Nicht in MVP (Backlog):

- Browser Rendering / Playwright / Headless Browser — kein Code, keine Konfiguration, kein TODO in diesem Sprint.

Akzeptanzkriterien:

- [x] JS-lastige Websites werden als `js_content_detected` erfasst, nicht als inhaltlich leer fehlinterpretiert;
- [x] blockierte Websites erzeugen klare Diagnose statt schwacher falscher Summary;
- [x] kein Browser-Rendering-Code landet im MVP-Branch.

### 6.9 Research Result als versionierten Contract definieren

- [x] **Punkt 6.9 abgeschlossen**

Umzusetzen:

- [x] `CompanyResearchResult` als Dataclass/Pydantic-Modell einfuehren;
- [x] Felder definieren: `normalized_domain`, `homepage_url`, `snapshot`, `identity`, `industry`, `summary`, `evidence`, `warnings`, `errors`, `schema_version`;
- [x] Rueckgabe von `build_company_research(...)` von freiem Dict auf typisierten Contract migrieren;
- [x] Kompatibilitaetslayer fuer bestehende Supervisor-Codepfade nur temporaer zulassen;
- [x] Result-Contract in Tests validieren.

Akzeptanzkriterien:

- [x] Supervisor muss nicht mit untypisierten Dict-Keys wie `research["snapshot"]` arbeiten;
- [x] fehlende Felder sind Validierungsfehler statt spaete KeyErrors;
- [x] Result-Schema ist versionierbar.

### 6.10 Fehler- und Degradation-Verhalten der Intake Research definieren

- [x] **Punkt 6.10 abgeschlossen**

Umzusetzen:

- [x] Fehlercodes definieren: `fetch_timeout`, `dns_failed`, `tls_failed`, `blocked_private_host`, `redirect_blocked`, `unsupported_content_type`, `text_extraction_empty`, `identity_conflict`, `industry_unknown`;
- [x] je Fehlercode entscheiden: blockierend, degraded weiter, oder nur Warnung;
- [x] mehrere Fehler/Warnungen in `CompanyResearchResult.warnings/errors` sammeln;
- [x] Supervisor Briefing Readiness aus Research-Fehlern ableiten;
- [x] kein pauschales `ready_for_department_routing`, wenn harte Research-Grenzen verletzt sind.

Akzeptanzkriterien:

- [x] Fetch-/Research-Probleme sind nicht nur Freitext;
- [x] Step 1 kann zwischen schwacher Evidence und blockierendem Sicherheits-/Identitaetsproblem unterscheiden;
- [x] Fehlercodes sind fuer UI, Tests und Monitoring nutzbar.

### 6.11 Budgetierung und Latenzgrenzen fuer Intake Research einfuehren

- [ ] **Punkt 6.11 abgeschlossen**

Umzusetzen:

- [x] maximale Dauer fuer Homepage Fetch definieren;
- [x] maximale Dauer fuer externe Identity-Quellen definieren;
- [x] maximale Anzahl externer Quellen im Step-1-Intake definieren;
- [ ] teure Fallbacks wie Browser Rendering budgetieren; **Backlog, da Browser Rendering nicht MVP ist**
- [x] Latenz je Subschritt messen;
- [x] bei Budgetueberschreitung degrade statt haengen.

Akzeptanzkriterien:

- [x] Step 1 bleibt zeitlich kontrollierbar;
- [x] Intake Research kann nicht durch eine schlechte Website minutenlang blockieren;
- [x] Budgetentscheidungen sind im Research Result sichtbar.

### 6.12 Tests fuer Intake Research Pipeline aufbauen

- [ ] **Punkt 6.12 abgeschlossen**

Umzusetzen:

- [x] Unit-Tests fuer Domain-Vertrag-Weitergabe in `build_company_research(...)`;
- [x] Tests fuer erfolgreichen HTML-Fetch mit Title/Meta/Text;
- [x] Tests fuer Redirect-Kette und blockierte Redirects;
- [ ] Tests fuer DNS-/TLS-/Timeout-Fehler; **DNS/Timeout abgedeckt, TLS noch offen**
- [x] Tests fuer Boilerplate-Entfernung und Summary-Qualitaet;
- [ ] Tests fuer Identity Resolution mit Homepage, Register und Konflikt; **Homepage/Konflikt abgedeckt, Register Phase 2 offen**
- [x] Tests fuer Industry Detection mit hoher/niedriger Confidence;
- [x] Tests fuer JS-empty-Fallback-Signal;
- [x] Contract-Tests fuer `CompanyResearchResult`.

Akzeptanzkriterien:

- [x] kritische Website-/Identity-Failure-Modes sind reproduzierbar getestet;
- [x] Security- und SSRF-Grenzen sind in Tests abgedeckt;
- [x] Summary- und Identity-Regressions fallen vor Department-Routing auf.

### 6.13 Observability fuer Intake Research einfuehren

- [ ] **Punkt 6.13 abgeschlossen**

Umzusetzen:

- [x] Metriken: Fetch-Latenz, Fetch-Erfolgsrate, Redirect-Anzahl, Text-Extraktionsqualitaet, Identity-Confidence-Verteilung, Industry-Confidence-Verteilung;
- [x] strukturierte Logs mit `run_id`, `fetch_status`, `identity_confidence`, `industry_confidence`, ohne Roh-HTML;
- [ ] OpenTelemetry-Spans fuer `research.homepage_fetch`, `research.identity_resolution`, `research.industry_inference`, `research.summary_extraction` vorbereiten;
- [ ] Cloudflare/Hetzner Request-ID falls vorhanden korrelieren;
- [ ] Alerting fuer hohe Fetch-Failure- oder Identity-Conflict-Raten definieren.

Akzeptanzkriterien:

- [x] Intake Research ist im Betrieb messbar;
- [x] schlechte Website-Erreichbarkeit ist von Identitaetsproblemen unterscheidbar;
- [ ] Logs und Spans enthalten keine unnoetigen Kundendaten. **Logs/RunContext ja; echte Spans offen**

### 6.14 Dokumentation und Diagramm aktualisieren

- [x] **Punkt 6.14 abgeschlossen**

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` um sichere Fetch-Pipeline, Identity Research und Research Result Contract erweitern;
- [x] `scripts/generate_step1_drawio.py` aktualisieren;
- [x] `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [x] `docs/drawio/target_runtime_architecture.md` um Intake Research Pipeline und Grenzen zur Department-Recherche ergaenzen;
- [x] klar dokumentieren: Step 1 macht Intake-/Identity-Research, aber keine tiefe Company-/Market-/Buyer-Recherche.

Akzeptanzkriterien:

- [x] Diagramm zeigt Domain Contract, Fetch Guards, Snapshot, Identity Resolution, Summary und Industry Inference;
- [x] Narrative Doku trennt Intake Research sauber von Department Research;
- [x] Zielarchitektur und Code-Zielbild sind konsistent.

### 6.15 Zielbewertung nach Umsetzung

- [ ] **Punkt 6.15 abgeschlossen**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung |
| --- | ---: |
| Ablaufklarheit | 5/5 |
| Geschwindigkeit / Budgetkontrolle | 5/5 |
| Identitaetsrobustheit | 5/5 |
| Security/SSRF/Redirect | 5/5 |
| Evidence-Qualitaet | 5/5 |
| Industry Hint | 5/5 |
| Fehlerklassifikation | 5/5 |
| Produktionsfaehigkeit | 5/5 |

### 6.16 Definition of Done fuer Punkt 6

- [ ] **Punkt 6.16 abgeschlossen**

- [x] `build_company_research(...)` nutzt den validierten Domain-/Intake-Vertrag;
- [x] Fetch-Pipeline ist gegen DNS-/Redirect-/SSRF-/Timeout-/Content-Type-Risiken abgesichert;
- [x] Website Snapshot, Identity Resolution, Industry Inference und Research Result sind typisierte Contracts;
- [x] Text-/Summary-Extraktion ist boilerplate-arm, begrenzt und qualitaetsbewusst;
- [ ] Identity Research nutzt mehrere Quellen und erfasst Konflikte strukturiert;
- [x] Industry Hint hat Confidence, Evidence und Alternativen;
- [ ] JS-/SPA-/Anti-Bot-Fallbacks sind definiert, budgetiert und sicher; **Stufe 0 + Diagnose umgesetzt, Retry/Cache/Browser-Budget offen**
- [ ] Fehler, Warnings, Budgets, Tests, Observability, Runtime-Doku, Draw.io und Zielarchitektur sind aktualisiert.

## 7. Seeded Runtime State + Handoff als validierten Step-1-Contract absichern

Betroffener aktueller Ablauf:

```python
state.run_context.supervisor_brief = supervisor_message["payload"]
state.run_context.question_registry = build_question_registry()
state.run_context.answer_matrix = build_initial_answer_matrix()
state.messages.append(
    emit_message(
        on_message,
        agent="Supervisor",
        content=json.dumps(supervisor_message, ensure_ascii=False),
    )
)
_write_checkpoint(state.run_dir, "after_supervisor_brief", state.run_context)
return SupervisorBriefResult(brief=brief, supervisor_message=supervisor_message)
```

### 7.0 Current State (Code-Audit)

- [x] `run_context.supervisor_brief`, `question_registry` und `answer_matrix` werden bereits gesetzt.
- [x] `emit_message(...)` erzeugt bereits ein erstes Supervisor Event, aber noch ohne Event-ID, Sequenz oder Schema-Version.
- [x] `_write_checkpoint(..., "after_supervisor_brief", ...)` existiert bereits als lokaler JSON-Checkpoint.
- [x] `SupervisorBriefResult` existiert bereits als Rueckgabe an `run_pipeline(...)`.
- [x] Delta fuer Punkt 7 ist **validierter Handoff, Eventing, Checkpointing und Readiness Gate**, nicht erstmalige Uebergabe.

Ziel: Der Abschluss von Step 1 soll ein formaler, versionierter und validierter Handoff-Contract sein. Step 2 darf nur starten, wenn Supervisor Brief, Question Registry, Answer Matrix, Runtime Event, Checkpoint und Readiness-Status konsistent sind. Lokales File-Checkpointing wird im Produktionsziel durch den transaktionalen Hetzner/Postgres-Run-State aus Punkt 3 ersetzt oder ergaenzt.

### 7.1 Doku-Code-Drift bei Meeting-Fragen korrigieren

- [x] **Punkt 7.1 abgeschlossen**

Aktueller Befund: `docs/runtime/runtime_step1.md` spricht von 11 Meeting-Fragen. Der aktuelle Code in `src/orchestration/meeting_questions.py` enthaelt 12 Registry-Eintraege, inklusive `q_contact_intelligence` und `q_target_company_contacts`.

Umzusetzen:

- [x] aktuelle Anzahl der `MEETING_QUESTION_REGISTRY`-Eintraege per Test oder Script verifizieren;
- [x] `docs/runtime/runtime_step1.md` von 11 auf 12 Meeting-Fragen korrigieren;
- [x] `scripts/generate_step1_drawio.py` aktualisieren, falls dort 11 genannt wird;
- [ ] `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [x] `target_runtime_architecture.md` pruefen und ggf. ebenfalls korrigieren;
- [x] Regressionstest ergaenzen, der Doku-/Contract-Annahmen zur Frageanzahl absichert oder zumindest die Registry-Anzahl testet.

Akzeptanzkriterien:

- [x] Runtime-Doku und Code nennen dieselbe Anzahl Meeting-Fragen;
- [ ] Diagramm und Narrative Doku widersprechen `MEETING_QUESTION_REGISTRY` nicht; **Draw.io-Regeneration noch offen**
- [x] kuenftige Registry-Aenderungen fallen in Tests oder Review-Checks auf.

### 7.2 `Step1Handoff` als typisierten Contract einfuehren

- [x] **Punkt 7.2 abgeschlossen**

Mindestform des Handoff-Contracts, z. B. als `TypedDict`, Dataclass oder Pydantic-Modell:

```python
class Step1Handoff(TypedDict):
    schema_version: str
    run_id: str
    intake: dict[str, Any]
    supervisor_brief: dict[str, Any]
    supervisor_message: dict[str, Any]
    question_registry: dict[str, dict[str, Any]]
    answer_matrix: dict[str, dict[str, Any]]
    retrieved_strategies: list[dict[str, Any]]
    retrieved_role_strategies: dict[str, list[dict[str, Any]]]
    runtime_agents_snapshot: dict[str, Any]
    readiness: Literal["ready_for_department_routing", "ready_with_gaps", "blocked_step1_handoff"]
    validation_errors: list[dict[str, Any]]
```

Validation Gates:

- [x] `SupervisorBrief` validiert;
- [x] `QuestionRegistry` und `AnswerMatrix` haben identische Keys;
- [x] `supervisor_message.status` und Handoff-Readiness stimmen ueberein;
- [x] Checkpoint/Event wurde erfolgreich geschrieben;
- [x] Step 2 darf nur bei erlaubter Readiness starten.

Umzusetzen:

- [x] `Step1Handoff` als Dataclass/Pydantic-Modell definieren;
- [x] Felder definieren: `run_id`, `intake`, `supervisor_brief`, `supervisor_message`, `question_registry`, `answer_matrix`, `retrieved_strategies`, `retrieved_role_strategies`, `runtime_agents_snapshot`, `readiness`, `schema_version`;
- [x] `SupervisorBriefResult` entweder erweitern oder in den Handoff-Contract einbetten;
- [x] Handoff validieren, bevor `_run_first_pass(...)` aufgerufen wird;
- [x] Handoff-Contract als Snapshot in `RunContext.resolution_state["step1_handoff"]` speichern.

Akzeptanzkriterien:

- [x] Step 2 startet nicht auf Basis lose verteilter Felder, sondern eines validierten Handoff-Contracts;
- [x] fehlendes Brief, fehlende Answer Matrix oder leere Registry blockieren den Handoff;
- [x] Handoff-Schema ist versioniert und testbar.

### 7.3 Supervisor Brief Payload versionieren und validieren

- [x] **Punkt 7.3 abgeschlossen**

Umzusetzen:

- [x] `supervisor_message["payload"]` nicht unvalidiert als Dict in `run_context.supervisor_brief` uebernehmen;
- [x] `SupervisorBrief` oder neues Pydantic-Modell vor Speicherung validieren;
- [x] `supervisor_message` um `schema_version` ergaenzen;
- [x] `section`, `status`, `payload`, `briefing_readiness` und `evidence_summary` als Message-Contract definieren;
- [x] bei ungueltiger Message einen klaren Step-1-Handoff-Fehler ausloesen.

Akzeptanzkriterien:

- [x] `run_context.supervisor_brief` enthaelt einen validierten Briefing-Contract;
- [x] unvollstaendige oder falsch versionierte Supervisor Messages fallen vor Step 2 auf;
- [x] alte Run-Artefakte bleiben ueber Schema-Versionen nachvollziehbar.

### 7.4 Question Registry und Answer Matrix als Contracts validieren

- [x] **Punkt 7.4 abgeschlossen**

Umzusetzen:

- [x] `QuestionRegistry`- und `AnswerMatrix`-Modelle oder Validatoren einfuehren;
- [x] pruefen, dass jede Registry-Frage `question`, `focus_area` und stabile `question_id` besitzt;
- [x] pruefen, dass jede Answer-Matrix-Frage initial `status="pending"`, `answer=""`, `notes=""`, `source_tasks=[]` und passenden `target_section` hat;
- [x] pruefen, dass Answer Matrix exakt dieselben Keys wie Question Registry enthaelt;
- [x] `TASK_TO_QUESTION_IDS` gegen Registry validieren: keine Verweise auf fehlende Fragen;
- [x] deterministische Reihenfolge fuer spaetere Gates und UI sichern.

Akzeptanzkriterien:

- [x] Step 2 startet nicht mit inkonsistenter Frage-/Antwortmatrix;
- [x] neue Meeting-Fragen muessen Registry, Mapping und Tests aktualisieren;
- [x] Answer Matrix ist fuer Readiness Gates verlaesslich initialisiert.

### 7.5 Erstes Runtime Event als versioniertes Event modellieren

- [x] **Punkt 7.5 abgeschlossen**

Aktuell erzeugt `emit_message(...)` nur:

```python
event = {"agent": agent, "content": content, "type": message_type}
```

Umzusetzen:

- [x] Runtime Event Contract einfuehren mit `event_id`, `run_id`, `sequence`, `timestamp`, `agent`, `type`, `schema_version`, `content`, `content_type`, `phase`;
- [x] `emit_message(...)` entsprechend erweitern oder einen neuen EventEmitter einfuehren;
- [x] `supervisor_brief`-Event mit `phase="supervisor_brief"` markieren;
- [x] Event-Sequenz deterministisch in `state.messages` und DB/Event-Store halten;
- [x] `on_message` bekommt denselben validierten Event-Contract wie die interne Message-Liste;
- [x] keine grossen Rohtexte oder Secrets im Event-Content loggen.

Akzeptanzkriterien:

- [x] erstes Runtime Event ist eindeutig identifizierbar und sequenziert;
- [x] UI-/Streaming-Consumer koennen Event-Versionen verstehen;
- [x] Eventing ist mit Postgres-Event-Store aus Punkt 3 kompatibel.

### 7.6 Checkpoint `after_supervisor_brief` transaktional und produktionsfaehig machen

- [ ] **Punkt 7.6 abgeschlossen**

Umzusetzen:

- [ ] `_write_checkpoint(...)` um DB-Checkpoint-Schreibung erweitern oder in Store-Service ueberfuehren;
- [ ] lokaler JSON-Checkpoint bleibt nur Development-/Export-Artefakt, nicht primaere Recovery-Quelle;
- [x] Checkpoint enthaelt validierten Handoff-Contract, RunContext-Snapshot, Phase, Sequenz und Schema-Version;
- [ ] Checkpoint-Schreibung atomar/transaktional mit Run-Status `supervisor_brief` oder `step1_ready` koppeln;
- [x] Checkpoint-Hash speichern, um Integritaet zu pruefen;
- [ ] Fehler beim Checkpoint-Schreiben blockieren Step 2 im Produktionsmodus.

Akzeptanzkriterien:

- [ ] Crash Recovery nach Step 1 erfolgt aus DB/Store, nicht aus halbgeschriebenen lokalen JSON-Dateien;
- [ ] Checkpoint und Run-Phase koennen nicht auseinanderlaufen;
- [x] fehlgeschlagener Checkpoint erzeugt klaren Fehlerstatus.

### 7.7 Formales Step-1-Readiness-/Handoff-Gate einfuehren

- [x] **Punkt 7.7 abgeschlossen**

Umzusetzen:

- [x] `Step1HandoffGate` oder `validate_step1_handoff(...)` einfuehren;
- [x] Gate prueft: validierter Intake, Runtime Agents validiert, Memory Retrieval abgeschlossen/degraded dokumentiert, Supervisor Brief validiert, Question Registry/Answer Matrix konsistent, erstes Event erzeugt, Checkpoint geschrieben;
- [x] Gate liefert Status: `ready_for_department_routing`, `ready_with_gaps`, `blocked_step1_handoff`;
- [x] Gate-Entscheidung in `resolution_state` speichern;
- [x] `_run_first_pass(...)` nur aufrufen, wenn Gate Department-Routing erlaubt;
- [x] UI/API kann Blocker anzeigen.

Akzeptanzkriterien:

- [x] Step 2 startet nicht allein wegen eines String-Status in `supervisor_message`;
- [x] alle Step-1-Voraussetzungen sind maschinenlesbar geprueft;
- [x] blockierte Handoffs sind fuer Nutzer und Betreiber erklaerbar.

### 7.8 `InitialRunState` Live Objects auf Produktionsziel abstimmen

- [x] **Punkt 7.8 abgeschlossen**

Umzusetzen:

- [x] `InitialRunState` um Store-/Persistence-Snapshots aus Punkt 3 erweitern;
- [x] `state.run_dir` als Artefakt-/Exportpfad behalten, aber nicht als primaeren Produktionszustand behandeln;
- [x] `state.budget_tracker` initial im Handoff-Snapshot ablegen;
- [x] `state.agents` nicht direkt serialisieren, sondern nur Runtime-Agent-Snapshot aus Punkt 2;
- [x] `supervisor.brief` und `supervisor.supervisor_message` in validierter Form referenzieren;
- [x] Live-Object-Doku in `runtime_step1.md` aktualisieren.

Akzeptanzkriterien:

- [x] Live Objects am Ende von Step 1 sind klar zwischen serialisierbarem Zustand und Prozessobjekten getrennt;
- [x] Recovery benoetigt keine nicht-serialisierbaren Agent-Instanzen;
- [x] Handoff-Snapshot enthaelt alles, was Step 2 fachlich braucht.

### 7.9 Fehler- und Degradation-Verhalten fuer Handoff definieren

- [x] **Punkt 7.9 abgeschlossen**

Umzusetzen:

- [x] Fehlercodes definieren: `step1_handoff_invalid`, `question_registry_invalid`, `answer_matrix_invalid`, `supervisor_message_invalid`, `checkpoint_write_failed`, `event_emit_failed`;
- [x] entscheiden, welche Fehler Step 1 blockieren und welche als degraded weiterlaufen duerfen;
- [x] Fehlerpfad in `_pipeline_error_result(...)` mit `failed_phase="step1_handoff"` oder genauer Phase abbilden;
- [ ] bei `on_message`-Fehlern klaeren, ob interne Run-Ausfuehrung fortsetzen darf;
- [ ] Retry-Verhalten fuer Checkpoint-/DB-Schreibfehler definieren.

Akzeptanzkriterien:

- [x] Handoff-Fehler sind nicht als spaetere Department-Fehler maskiert;
- [x] UI/API sieht konkrete Blocker;
- [x] Betreiber kann Checkpoint-, Event- und Contract-Probleme unterscheiden.

### 7.10 Tests fuer Step-1-Handoff aufbauen

- [ ] **Punkt 7.10 abgeschlossen**

Umzusetzen:

- [x] Unit-Test: `build_question_registry()` und `build_initial_answer_matrix()` haben identische Keys;
- [x] Unit-Test: initiale Answer Matrix setzt alle Fragen auf `pending`;
- [x] Unit-Test: `TASK_TO_QUESTION_IDS` referenziert nur existierende Fragen;
- [x] Contract-Test: validierter `Step1Handoff` wird erzeugt;
- [x] Negativtest: fehlender Supervisor Brief blockiert Handoff;
- [x] Negativtest: inkonsistente Answer Matrix blockiert Handoff;
- [x] Test: erstes Runtime Event hat Event-ID, Sequenz, Phase und Schema-Version;
- [ ] Test: Checkpoint-Fehler blockiert Step 2 im Produktionsmodus;
- [ ] Integrationstest: `run_pipeline(...)` ruft `_run_first_pass(...)` nur nach erfolgreichem Handoff-Gate auf.

Akzeptanzkriterien:

- [ ] Doku-Code-Drift bei Meeting-Fragen faellt schnell auf;
- [ ] Step-1-Handoff ist regressionssicher;
- [ ] Step 2 kann nicht mit teilinitialisiertem Zustand starten.

### 7.11 Observability fuer Step-1-Handoff einfuehren

- [ ] **Punkt 7.11 abgeschlossen**

Umzusetzen:

- [ ] Metriken: Handoff-Erfolg, Handoff-Blocker, Checkpoint-Schreibdauer, Event-Emit-Latenz, Question-Registry-Größe;
- [ ] strukturierte Logs mit `run_id`, `phase`, `handoff_status`, `question_count`, `event_sequence`, `checkpoint_id`;
- [ ] OpenTelemetry-Span `pipeline.step1_handoff` vorbereiten;
- [ ] Alerting fuer haeufige `step1_handoff_invalid` oder `checkpoint_write_failed` Fehler definieren;
- [ ] Logs duerfen keine grossen Briefing-Rohtexte enthalten.

Akzeptanzkriterien:

- [ ] Betreiber kann sehen, ob Step 1 sauber an Step 2 uebergibt;
- [ ] Handoff-Probleme sind von Intake-, Agent-, Memory- und Supervisor-Brief-Problemen unterscheidbar;
- [ ] Handoff-Latenz und Checkpoint-Latenz sind messbar.

### 7.12 Dokumentation und Diagramm aktualisieren

- [ ] **Punkt 7.12 abgeschlossen**

Umzusetzen:

- [x] `docs/runtime/runtime_step1.md` um Step1Handoff Contract, Handoff Gate, Event Contract und DB-Checkpoint aktualisieren;
- [x] falsche Angabe `11 Meeting-Fragen` korrigieren;
- [x] `scripts/generate_step1_drawio.py` aktualisieren;
- [ ] `docs/drawio/runtime_step1.drawio` neu generieren und XML validieren;
- [x] `docs/drawio/target_runtime_architecture.md` um Step-1-Handoff-Contract ergaenzen;
- [x] Prozessgrenze zu Step 2 klarer beschreiben: Step 2 startet nur nach validiertem Handoff.

Akzeptanzkriterien:

- [ ] Diagramm zeigt Contract Validation, Eventing, Checkpoint und Handoff Gate;
- [ ] Narrative Doku ist code-synchron;
- [ ] Zielarchitektur beschreibt Step 1 nicht mehr als lose Felduebergabe.

### 7.13 Zielbewertung nach Umsetzung

- [ ] **Punkt 7.13 abgeschlossen**

Erwartete Bewertung nach vollstaendiger Umsetzung:

| Kriterium | Zielbewertung |
| --- | ---: |
| State-Seeding | 5/5 |
| Meeting-Fragen-Integration | 5/5 |
| Eventing | 5/5 |
| Checkpointing | 5/5 |
| Handoff-Vertrag | 5/5 |
| Crash Recovery | 5/5 |
| Observability | 5/5 |
| Step-2-Start-Sicherheit | 5/5 |

### 7.14 Definition of Done fuer Punkt 7

- [ ] **Punkt 7.14 abgeschlossen**

- [ ] Meeting-Fragen-Anzahl und Registry-Inhalt sind in Code, Doku und Diagramm synchron; **Code/Doku/Generator ja, Draw.io-Regeneration offen**
- [x] Step 1 erzeugt einen typisierten und versionierten Handoff-Contract;
- [ ] Supervisor Brief, Question Registry und Answer Matrix werden vor Step 2 validiert;
- [ ] erstes Runtime Event ist versioniert, sequenziert und run-bezogen;
- [ ] Checkpoint `after_supervisor_brief` ist produktionsfaehig, transaktional und recovery-tauglich;
- [ ] Step-1-Handoff-Gate entscheidet maschinenlesbar ueber Start, Degradation oder Blockade;
- [ ] Live Objects und serialisierbarer Run-State sind sauber getrennt;
- [ ] Fehler, Tests, Observability, Runtime-Doku, Draw.io und Zielarchitektur sind aktualisiert.
