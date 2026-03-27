# F10 — Drift-Indikatoren / Signatur-Genauigkeit bereinigen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F10  
**Ziel:** Signaturen, Rueckgaben und Runtime-Verhalten stimmen exakt ueberein. Kleine Drifts werden frueh eliminiert.

---

## Ist-Zustand: Analyse

### Drift 1: `run_supervisor_loop` Return-Signatur

**Datei:** `src/orchestration/supervisor_loop.py`

```python
def run_supervisor_loop(...) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
```

Deklariert 4-Tuple, gibt aber 5 Werte zurueck:
```python
return sections, department_packages, messages, completed_backlog, department_timings
```

`department_timings: dict[str, float]` fehlt in der Signatur. Der Caller in `pipeline_runner.py` entpackt korrekt 5 Werte.

### Drift 2: `accept_department_package` Return-Typ

**Datei:** `src/agents/supervisor.py`

```python
def accept_department_package(self, ...) -> dict[str, str | bool]:
```

Nach F7 enthaelt die Rueckgabe keine `bool`-Werte mehr (`accepted: bool` wurde entfernt). Tatsaechliche Rueckgabe:
```python
{"decision": str, "reason": str, "open_questions_present": bool, "substantive_content": bool, "accepted_tasks": int, "total_tasks": int}
```

Korrekter Typ waere `dict[str, str | bool | int]` oder besser ein TypedDict.

### Drift 3: `accept_synthesis` Return-Typ

**Datei:** `src/agents/supervisor.py`

```python
def accept_synthesis(self, ...) -> dict[str, str | bool]:
```

Tatsaechliche Rueckgabe nach F7:
```python
{"decision": str, "reason": str, "generation_mode": str}
```

Nur `str`-Werte. `bool` ist falsch.

### Drift 4: `decide_revision` Return-Typ

```python
def decide_revision(self, ...) -> dict[str, str | bool]:
```

Tatsaechliche Rueckgabe enthaelt `bool` (`retry`, `same_department`, `authorize_coding_specialist`) — Annotation ist **korrekt**.

### Zusammenfassung

| Stelle | Deklariert | Tatsaechlich | Drift? |
|--------|-----------|-------------|:---:|
| `run_supervisor_loop` | 4-tuple | 5-tuple | **ja** |
| `accept_department_package` | `dict[str, str \| bool]` | `dict[str, str \| bool \| int]` | **ja** |
| `accept_synthesis` | `dict[str, str \| bool]` | `dict[str, str]` | **ja** |
| `decide_revision` | `dict[str, str \| bool]` | `dict[str, str \| bool]` | nein |

---

## Patch-Sequenz

### Patch 1 — `run_supervisor_loop` Signatur korrigieren

**Datei:** `src/orchestration/supervisor_loop.py`

```python
# Vorher:
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:

# Nachher:
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, str]], dict[str, float]]:
```

### Patch 2 — `accept_department_package` Signatur korrigieren

**Datei:** `src/agents/supervisor.py`

```python
# Vorher:
def accept_department_package(self, ...) -> dict[str, str | bool]:

# Nachher:
def accept_department_package(self, ...) -> dict[str, str | bool | int]:
```

### Patch 3 — `accept_synthesis` Signatur korrigieren

**Datei:** `src/agents/supervisor.py`

```python
# Vorher:
def accept_synthesis(self, ...) -> dict[str, str | bool]:

# Nachher:
def accept_synthesis(self, ...) -> dict[str, str]:
```

### Patch 4 — Statische Pruefung als Guard-Test

**Datei:** `tests/smoke/test_preflight.py`

Neuer Test der prueft, dass die deklarierten Return-Typen mit den tatsaechlichen Rueckgaben konsistent sind (Source-Inspection-basiert).

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Typannotationen und reale Rueckgaben stimmen ueberein | 3 Signaturen korrigiert |
| Keine bekannten Drift-Indikatoren bleiben offen | Alle identifizierten Drifts behoben |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/orchestration/supervisor_loop.py` | Return-Signatur 4-tuple → 5-tuple |
| 2 | `src/agents/supervisor.py` | `accept_department_package` Return-Typ |
| 3 | `src/agents/supervisor.py` | `accept_synthesis` Return-Typ |
| 4 | `tests/smoke/test_preflight.py` | Guard-Test |

**Reihenfolge:** 1 → 2 → 3 → 4 → Validierung.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 4 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 1** -- `run_supervisor_loop` Return als `SupervisorLoopResult` NamedTuple
   - 5 benannte Felder: `sections`, `department_packages`, `messages`, `completed_backlog`, `department_timings`
   - Kein unbenanntes Tuple mehr

2. **Patch 2** -- `accept_department_package` Return als `DepartmentAcceptanceResult` TypedDict
   - Felder: `decision`, `reason`, `open_questions_present`, `substantive_content`, `accepted_tasks`, `total_tasks`

3. **Patch 3** -- `accept_synthesis` Return als `SynthesisAcceptanceResult` TypedDict
   - Felder: `decision`, `reason`, `generation_mode`

4. **Patch 4** -- 2 Guard-Tests
   - `test_supervisor_loop_returns_named_tuple`
   - `test_acceptance_methods_return_typed_dicts`

### Review-Feedback integriert

| # | Feedback | Umsetzung |
|---|----------|-----------|
| 1 | TypedDicts statt lose dict-Unionen | DepartmentAcceptanceResult + SynthesisAcceptanceResult |
| 2 | Statische Typpruefung | Dokumentiert als Follow-up |
| 3 | NamedTuple statt unbenanntes Tuple | SupervisorLoopResult |

### Validierungsergebnisse

```
$ pytest tests/ -> 220 passed in 31.34s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Typannotationen und reale Rueckgaben stimmen ueberein | 3 Signaturen korrigiert mit TypedDict/NamedTuple |
| Keine bekannten Drift-Indikatoren bleiben offen | Alle identifizierten Drifts behoben |

---

## Follow-up (kein F10-Blocker)

### Statische Typpruefung (mypy/pyright)

**Ziel:** Langfristig einen statischen Type-Check-Step einfuehren der Signatur-Drift automatisch erkennt. Die TypedDicts und NamedTuples aus F10 sind dafuer die Basis.

**Prioritaet:** P2-Haertung.
