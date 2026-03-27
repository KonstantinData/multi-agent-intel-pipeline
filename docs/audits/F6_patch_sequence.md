# F6 — Role-Memory-Retrieval schliessen: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F6  
**Ziel:** Persistenz- und Retrieval-Seite sprechen dieselbe Rollensprache. Keine Phantom-Rollen, keine persistierten Rollen ohne Retrieval-Pfad.

---

## Ist-Zustand: Analyse

### Retrieval-Rollen (`pipeline_runner.py`)

Rollen fuer die beim Run-Start Strategien aus dem Long-Term-Memory geladen werden:

```
Supervisor, CompanyLead, CompanyResearcher, CompanyCritic,
MarketLead, MarketResearcher, MarketCritic,
BuyerLead, BuyerResearcher, BuyerCritic,
CrossDomainStrategicAnalyst, ReportWriter
```

### Konsolidierungs-Rollen (`ROLE_MEMORY_CATEGORIES` in `consolidation.py`)

Rollen fuer die nach einem erfolgreichen Run Patterns ins Long-Term-Memory geschrieben werden:

```
Supervisor,
CompanyLead, MarketLead, BuyerLead, ContactLead,
CompanyResearcher, MarketResearcher, BuyerResearcher, ContactResearcher,
CompanyCritic, MarketCritic, BuyerCritic, ContactCritic,
CompanyJudge, MarketJudge, BuyerJudge, ContactJudge,
CompanyCodingSpecialist, MarketCodingSpecialist, BuyerCodingSpecialist, ContactCodingSpecialist
```

### Agent-Specs (`AGENT_SPECS` in `specs.py`)

Zusaetzlich definiert aber weder konsolidiert noch retrieved:

```
SynthesisLead, SynthesisCritic, SynthesisJudge
```

### Drift-Tabelle

| Rolle | Konsolidiert? | Retrieved? | Problem |
|-------|:---:|:---:|---------|
| `Supervisor` | ja | ja | OK |
| `CompanyLead` | ja | ja | OK |
| `CompanyResearcher` | ja | ja | OK |
| `CompanyCritic` | ja | ja | OK |
| `MarketLead` | ja | ja | OK |
| `MarketResearcher` | ja | ja | OK |
| `MarketCritic` | ja | ja | OK |
| `BuyerLead` | ja | ja | OK |
| `BuyerResearcher` | ja | ja | OK |
| `BuyerCritic` | ja | ja | OK |
| `ContactLead` | ja | **nein** | Konsolidiert aber nie retrieved |
| `ContactResearcher` | ja | **nein** | Konsolidiert aber nie retrieved |
| `ContactCritic` | ja | **nein** | Konsolidiert aber nie retrieved |
| `CompanyJudge` | ja | **nein** | Konsolidiert aber nie retrieved |
| `MarketJudge` | ja | **nein** | Konsolidiert aber nie retrieved |
| `BuyerJudge` | ja | **nein** | Konsolidiert aber nie retrieved |
| `ContactJudge` | ja | **nein** | Konsolidiert aber nie retrieved |
| `CompanyCodingSpecialist` | ja | **nein** | Konsolidiert aber nie retrieved |
| `MarketCodingSpecialist` | ja | **nein** | Konsolidiert aber nie retrieved |
| `BuyerCodingSpecialist` | ja | **nein** | Konsolidiert aber nie retrieved |
| `ContactCodingSpecialist` | ja | **nein** | Konsolidiert aber nie retrieved |
| `CrossDomainStrategicAnalyst` | **nein** | ja | Phantom: retrieved aber nie konsolidiert |
| `ReportWriter` | **nein** | ja | Phantom: retrieved aber nie konsolidiert |
| `SynthesisLead` | **nein** | **nein** | Existiert in AGENT_SPECS, nirgends verdrahtet |
| `SynthesisCritic` | **nein** | **nein** | Existiert in AGENT_SPECS, nirgends verdrahtet |
| `SynthesisJudge` | **nein** | **nein** | Existiert in AGENT_SPECS, nirgends verdrahtet |

### Zusammenfassung der Probleme

1. **11 Rollen werden konsolidiert aber nie retrieved** — verschwendete Persistenz, toter Code-Pfad
2. **2 Phantom-Rollen werden retrieved aber nie konsolidiert** — `CrossDomainStrategicAnalyst` und `ReportWriter` erzeugen leere Retrieval-Ergebnisse
3. **3 Synthesis-Rollen existieren in AGENT_SPECS aber sind weder konsolidiert noch retrieved** — Naming-Drift zwischen Spec und Runtime

---

## Ziel-Zustand

### Kanonisches Rollenregister

Eine einzige Quelle der Wahrheit fuer alle Rollen die Memory-Patterns erzeugen und konsumieren duerfen. Definiert in `consolidation.py` als `ROLE_MEMORY_CATEGORIES`.

### Retrieval = Konsolidierung

`pipeline_runner.py` retrieved genau die Rollen die in `ROLE_MEMORY_CATEGORIES` definiert sind. Keine handgepflegte Parallelliste.

### Phantom-Rollen entfernt

- `CrossDomainStrategicAnalyst` → existiert nicht als Runtime-Rolle, wird entfernt
- `ReportWriter` → hat keine Memory-Patterns (F9 klaert die Rolle architektonisch), wird aus Retrieval entfernt

### Synthesis-Rollen

`SynthesisLead`, `SynthesisCritic`, `SynthesisJudge` werden in `ROLE_MEMORY_CATEGORIES` aufgenommen, sobald die Synthesis-Runtime eigene Patterns erzeugt. Bis dahin bleiben sie in AGENT_SPECS als UI-Metadaten, aber nicht im Memory-System.

---

## Patch-Sequenz

### Patch 1 — Kanonisches Rollenregister als Single Source of Truth

**Datei:** `src/memory/consolidation.py`

Neuer Export: `RETRIEVABLE_ROLES` — abgeleitet aus `ROLE_MEMORY_CATEGORIES`.

```python
RETRIEVABLE_ROLES: frozenset[str] = frozenset(ROLE_MEMORY_CATEGORIES.keys())
```

### Patch 2 — `pipeline_runner.py` auf kanonisches Register umstellen

**Datei:** `src/pipeline_runner.py`

Ersetze die handgepflegte Rollenliste durch Import aus dem kanonischen Register:

```python
from src.memory.consolidation import RETRIEVABLE_ROLES

run_context.retrieved_role_strategies = {
    role: retrieve_strategies(
        memory_store,
        domain=normalize_domain(web_domain),
        role=role,
        limit=3,
    )
    for role in RETRIEVABLE_ROLES
}
```

Damit entfallen:
- `CrossDomainStrategicAnalyst` (Phantom)
- `ReportWriter` (Phantom)

Und es kommen hinzu:
- `ContactLead`, `ContactResearcher`, `ContactCritic`
- Alle Judge-Rollen
- Alle CodingSpecialist-Rollen

### Patch 3 — Tests

**Datei:** `tests/architecture/test_memory.py` oder `tests/smoke/test_preflight.py`

Neue Tests:
- `test_retrievable_roles_equals_consolidation_roles` — RETRIEVABLE_ROLES == ROLE_MEMORY_CATEGORIES.keys()
- `test_no_phantom_roles_in_retrieval` — pipeline_runner verwendet nur RETRIEVABLE_ROLES
- `test_all_consolidated_roles_are_retrievable` — jede konsolidierte Rolle hat einen Retrieval-Pfad

---

## Design-Entscheidungen

### Warum nicht alle AGENT_SPECS-Rollen?

`AGENT_SPECS` enthaelt UI-Metadaten (Icons, Farben, Summaries) fuer alle sichtbaren Agenten. Nicht alle davon erzeugen oder konsumieren Memory-Patterns. Das Memory-System soll nur Rollen bedienen die tatsaechlich Patterns produzieren.

### Warum `CrossDomainStrategicAnalyst` entfernen?

Diese Rolle existiert nicht als Runtime-Agent. Sie war ein Naming-Artefakt aus einer frueheren Architektur. Die Synthesis-Rollen heissen `SynthesisLead`, `SynthesisCritic`, `SynthesisJudge`.

### Warum `ReportWriter` entfernen?

`ReportWriter` erzeugt keine Memory-Patterns (es gibt keinen Researcher/Critic/Judge-Zyklus fuer Reports). Die architektonische Klaerung der ReportWriter-Rolle ist Gegenstand von F9.

---

## Akzeptanzkriterien (aus Audit-TODO)

| Kriterium | Pruefung |
|-----------|---------|
| Jede persistierte Rolle ist retrievable | `RETRIEVABLE_ROLES == ROLE_MEMORY_CATEGORIES.keys()` |
| Keine nicht-existente Laufzeitrolle wird geladen | Phantom-Rollen entfernt |
| Synthesis- und Contact-Rollen sind konsistent verdrahtet | Contact-Rollen im Retrieval, Synthesis-Rollen dokumentiert als pending |

---

## Zusammenfassung

| Patch | Datei | Aktion |
|-------|-------|--------|
| 1 | `src/memory/consolidation.py` | `RETRIEVABLE_ROLES` frozenset |
| 2 | `src/pipeline_runner.py` | Handgepflegte Liste → Import aus kanonischem Register |
| 3 | `tests/` | 3 neue Tests |

**Reihenfolge:** 1 → 2 → 3 → Validierung.

---

## Offene Punkte fuer spaetere Findings

- Synthesis-Rollen (`SynthesisLead`, `SynthesisCritic`, `SynthesisJudge`) in `ROLE_MEMORY_CATEGORIES` aufnehmen, sobald Synthesis eigene Patterns erzeugt
- Follow-up-Pfad (`follow_up.py`) muss F2-Envelope-Format fuer `department_packages` verstehen (bereits in F2 als offener Punkt dokumentiert)
- `ReportWriter`-Rolle architektonisch klaeren (F9)

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** Alle 3 Patches umgesetzt und validiert

### Durchgefuehrte Schritte

1. **Patch 1 -- Kanonisches Rollenregister**
   - `MEMORY_ROLE_STATUS` dict mit `active | pending | excluded` pro Rolle
   - `RETRIEVABLE_ROLES` frozenset -- explizite Policy-Schicht, nicht nur Alias von ROLE_MEMORY_CATEGORIES
   - `RETRIEVABLE_ROLE_ORDER` tuple -- deterministisch sortiert fuer reproduzierbare Iteration
   - Synthesis-Rollen als `pending`, ReportWriter und CrossDomainStrategicAnalyst als `excluded`

2. **Patch 2 -- pipeline_runner.py umgestellt**
   - Handgepflegte 12-Rollen-Liste entfernt
   - Import von `RETRIEVABLE_ROLE_ORDER` aus `consolidation.py`
   - Phantom-Rollen `CrossDomainStrategicAnalyst` und `ReportWriter` eliminiert
   - 11 bisher fehlende Rollen (Contact*, Judge*, CodingSpecialist*) jetzt im Retrieval

3. **Patch 3 -- Tests (8 neue Tests)**
   - `test_retrievable_roles_equals_active_consolidation_roles`
   - `test_retrievable_roles_subset_of_consolidation_categories`
   - `test_no_phantom_roles_in_retrieval`
   - `test_all_consolidated_roles_are_retrievable`
   - `test_retrievable_role_order_is_sorted`
   - `test_synthesis_roles_are_pending`
   - `test_excluded_roles_not_in_retrievable`
   - `test_pipeline_runner_uses_canonical_registry`

### Validierungsergebnisse

```
$ pytest tests/ -> 210 passed in 30.34s
```

### Akzeptanzkriterien -- Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| Jede persistierte Rolle ist retrievable | RETRIEVABLE_ROLES == active roles in MEMORY_ROLE_STATUS |
| Keine nicht-existente Laufzeitrolle wird geladen | Phantom-Rollen entfernt, Test prueft Abwesenheit |
| Synthesis- und Contact-Rollen konsistent verdrahtet | Contact: active, Synthesis: pending (dokumentiert) |

### Review-Feedback integriert

| # | Feedback | Umsetzung |
|---|----------|-----------|
| 1 | Retrieval als explizite Policy-Schicht | RETRIEVABLE_ROLES ist eigene Policy, nicht nur Alias |
| 2 | Deterministische Rolleniteration | RETRIEVABLE_ROLE_ORDER als sortiertes Tuple |
| 3 | Drift-Test | test_pipeline_runner_uses_canonical_registry |
| 4 | Synthesis-Rollen als pending policy | MEMORY_ROLE_STATUS mit active/pending/excluded |
