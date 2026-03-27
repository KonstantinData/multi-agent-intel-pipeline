# F8 — Test-Surface konsolidieren: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F8  
**Ziel:** Eine klare Testoberflaeche. CI und lokale Runs pruefen dieselbe Wahrheit. Keine vergessenen oder stillen Testinseln.

---

## Ist-Zustand: Analyse

### Kanonische Teststruktur (`tests/`)

Korrekt aufgesetzt und funktional:

```
tests/
  architecture/   — 6 Dateien, 168 Tests (pure, kein AG2)
  integration/    — 1 Datei, 17 Tests (AG2-abhaengig)
  smoke/          — 1 Datei, 8 Tests
  conftest.py     — Root-Conftest
```

`pyproject.toml` zeigt korrekt auf `testpaths = ["tests"]`.
`pytest tests/` → 215 passed.

### Top-Level-Testdateien (ausserhalb `tests/`)

7 Dateien im Projekt-Root:

| Datei | Zeilen | Status | `pytest.skip()`? |
|-------|--------|--------|:---:|
| `test_contracts.py` | 825 | DEPRECATED — migriert nach `tests/architecture/` | ja |
| `test_integration.py` | 455 | DEPRECATED — migriert nach `tests/integration/` | ja |
| `test_optimizations.py` | 478 | DEPRECATED — migriert nach `tests/architecture/` + `tests/integration/` | ja |
| `test_preflight.py` | 62 | DEPRECATED — migriert nach `tests/smoke/` | ja |
| `test_runtime_architecture.py` | 835 | DEPRECATED — migriert nach `tests/architecture/` + `tests/integration/` | ja |
| `test_pipeline.py` | 326 | **Nicht migriert** — heavy E2E, benoetigt AG2 + OpenAI + reportlab | **nein** |
| `test_startup.py` | 149 | **Nicht migriert** — subprocess-basierter Startup-Test | **nein** |

### Probleme

1. **5 deprecated Dateien** liegen noch im Root — toter Code, Verwirrungspotenzial
2. **2 nicht-migrierte Dateien** (`test_pipeline.py`, `test_startup.py`) haben kein `pytest.skip()` — werden zwar durch `testpaths` nicht gesammelt, aber koennten bei `pytest .` oder explizitem Aufruf laufen
3. **`TESTING.md`** dokumentiert den Zustand korrekt, aber die Dateien selbst sind noch da
4. **Keine CI-Konfiguration** sichtbar — unklar ob CI `pytest tests/` oder `pytest` ausfuehrt

---

## Ziel-Zustand

### Einfache Regel

> `pytest` (ohne Argumente) fuehrt genau die Tests aus die in `tests/` liegen. Keine anderen Testdateien existieren im Projekt-Root.

### Konkret

- 5 deprecated Top-Level-Dateien: **entfernen**
- 2 nicht-migrierte Dateien: **entscheiden** (migrieren oder entfernen)
- `TESTING.md`: Legacy-Tabelle bereinigen
- `pyproject.toml`: bleibt unveraendert (bereits korrekt)

---

## Entscheidung: `test_pipeline.py` und `test_startup.py`

### `test_pipeline.py` (326 Zeilen)

Heavy E2E-Test der die gesamte Pipeline mit echtem OpenAI-Key ausfuehrt. Benoetigt AG2 + OpenAI + reportlab. Nicht fuer CI geeignet.

**Entscheidung:** Nicht migrieren, sondern entfernen. Begruendung:
- Die relevanten Architektur- und Integrationstests sind bereits in `tests/` abgedeckt
- Ein echter E2E-Test mit OpenAI-Key gehoert in eine separate CI-Stage oder ein manuelles Testskript, nicht in die Pytest-Surface
- Falls spaeter ein E2E-Test benoetigt wird, kann er als `tests/e2e/test_pipeline.py` mit eigenem Marker angelegt werden

### `test_startup.py` (149 Zeilen)

Subprocess-basierter Test der Streamlit startet und auf Port-Erreichbarkeit prueft.

**Entscheidung:** Nicht migrieren, sondern entfernen. Begruendung:
- `preflight.py` prueft Port-Erreichbarkeit bereits
- Smoke-Tests in `tests/smoke/` decken die Importierbarkeit ab
- Ein Streamlit-Startup-Test gehoert in eine separate Deployment-Validierung, nicht in die Unit-Test-Surface

---

## Patch-Sequenz

### Patch 1 — 5 deprecated Top-Level-Testdateien entfernen

**Dateien entfernen:**
- `test_contracts.py`
- `test_integration.py`
- `test_optimizations.py`
- `test_preflight.py`
- `test_runtime_architecture.py`

### Patch 2 — 2 nicht-migrierte Top-Level-Testdateien entfernen

**Dateien entfernen:**
- `test_pipeline.py`
- `test_startup.py`

### Patch 3 — `TESTING.md` bereinigen

Legacy-Tabelle entfernen oder auf "entfernt" aktualisieren.

### Patch 4 — Guard-Test: keine Testdateien ausserhalb `tests/`

**Datei:** `tests/smoke/test_preflight.py`

Neuer Test:
- `test_no_toplevel_test_files` — prueft dass keine `test_*.py` oder `*_test.py` Dateien im Projekt-Root liegen

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Alle relevanten Tests laufen ueber denselben `pytest`-Entry | `pytest tests/` ist die einzige Wahrheit |
| Keine produktionsrelevanten Tests liegen ausserhalb der Testwurzel | Top-Level-Dateien entfernt |
| CI bildet die reale Wahrheit ab | `testpaths = ["tests"]` + keine Testinseln |

---

## Zusammenfassung

| Patch | Aktion |
|-------|--------|
| 1 | 5 deprecated Top-Level-Testdateien entfernen |
| 2 | 2 nicht-migrierte Top-Level-Testdateien entfernen |
| 3 | `TESTING.md` bereinigen |
| 4 | Guard-Test gegen Top-Level-Testdateien |

**Reihenfolge:** 1 → 2 → 3 → 4 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 4 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 1 -- 5 deprecated Top-Level-Testdateien entfernt**
   - `test_contracts.py`, `test_integration.py`, `test_optimizations.py`, `test_preflight.py`, `test_runtime_architecture.py`

2. **Patch 2 -- 2 nicht-migrierte Dateien ausgelagert (nicht geloescht)**
   - `test_pipeline.py` → `scripts/manual_validation/test_pipeline.py`
   - `test_startup.py` → `scripts/manual_validation/test_startup.py`
   - `scripts/manual_validation/README.md` angelegt mit Ausfuehrungsanleitung
   - E2E-/Startup-Intention bleibt erhalten, aber ausserhalb der Default-Surface

3. **Patch 3 -- `TESTING.md` normativ umgeschrieben**
   - Kanonische Regel: `pytest tests/` ist die einzige Wahrheit
   - Klare Trennung: Default-Surface vs. manuelle Validierung
   - CI-Empfehlung: `pytest tests/` explizit ausfuehren
   - Legacy-Tabelle entfernt

4. **Patch 4 -- Guard-Test**
   - `test_no_toplevel_test_files`: prueft Root, `src/`, `ui/` auf `test_*.py` und `*_test.py`
   - Schuetzt gegen zukuenftige Drift in beide Richtungen

### Review-Feedback integriert

| # | Feedback | Umsetzung |
|---|----------|-----------|
| 1 | E2E-/Startup-Intention erhalten | `scripts/manual_validation/` statt Loeschung |
| 2 | Guard in beide Richtungen | Prueft Root + src/ + ui/ auf test_*.py und *_test.py |
| 3 | CI explizit festziehen | TESTING.md: "CI must execute pytest tests/ explicitly" |
| 4 | TESTING.md normativ | Governance-Dokument mit kanonischer Regel |
| 5 | Keine Legacy-skip-Dateien | Alle 5 deprecated Dateien entfernt, nicht nur unsichtbar |

### Validierungsergebnisse

```
$ pytest tests/ -> 216 passed in 31.19s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Alle relevanten Tests laufen ueber denselben pytest-Entry | pytest tests/ ist die einzige Wahrheit |
| Keine produktionsrelevanten Tests ausserhalb der Testwurzel | Top-Level entfernt, E2E in scripts/ |
| CI bildet die reale Wahrheit ab | TESTING.md normativ, Guard-Test aktiv |

---

## Follow-up-Punkte (kein F8-Blocker)

### 1. CI technisch explizit festziehen

**Aktueller Zustand:** `TESTING.md` formuliert die CI-Regel normativ, aber keine CI-Konfigurationsdatei ist sichtbar im Repo.

**Ziel:** Pruefen oder ergaenzen, dass die tatsaechliche CI-Pipeline `pytest tests/` explizit ausfuehrt. Nicht nur auf `testpaths` in `pyproject.toml` verlassen.

**Prioritaet:** Letzte Meile zur vollstaendigen Governance-Haertung. Kein F8-Blocker.

### 2. `scripts/manual_validation/` Konvention standardisieren

**Aktueller Zustand:** README vorhanden, aber keine formale Konvention wann etwas dort hingehoert.

**Ziel:** Spaeter definieren:
- Aufnahmekriterien (wann gehoert ein Check nach `scripts/manual_validation/`?)
- Startkonvention (einheitliches Interface, z.B. immer `pytest`-kompatibel mit eigenem Marker)
- Voraussetzungen-Dokumentation pro Skript

**Prioritaet:** Repo-Hygiene, kein Audit-Fix.
