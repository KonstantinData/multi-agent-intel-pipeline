# F1 — Import-/Layer-Boundary: Patch-Sequenz

**Bezug:** `2503_0943-audit-todo.md` → F1  
**Ziel:** `definitions.py` in `specs.py` (pure) + `runtime_factory.py` (heavy) aufteilen, `__init__.py` neutralisieren.

---

## Ist-Zustand: Importgraph

```
src/agents/__init__.py
  └─ src/agents/definitions.py          ← AGENT_SPECS + create_runtime_agents()
       ├─ src/agents/registry.py         ✅ pure (AgentSpec dataclass)
       ├─ src/agents/supervisor.py       ✅ pure (kein autogen)
       ├─ src/agents/report_writer.py    ✅ pure (kein autogen)
       ├─ src/orchestration/department_runtime.py  ❌ HEAVY
       │    └─ src/agents/lead.py → autogen
       └─ src/orchestration/synthesis_runtime.py   ❌ HEAVY
            └─ src/agents/synthesis_department.py → autogen
```

**Problem:** Jeder Import von `src.agents` oder `src.agents.definitions` zieht transitiv `autogen` nach — auch wenn nur `AGENT_SPECS` (reine Metadaten) benötigt wird.

## Ziel-Zustand: Importgraph

```
src/agents/__init__.py                   ✅ side-effect-frei (leerer Re-Export oder leer)
src/agents/specs.py                      ✅ pure — AGENT_SPECS dict
  └─ src/agents/registry.py             ✅ pure — AgentSpec dataclass
src/agents/runtime_factory.py            ❌ HEAVY (bewusst, nur bei Bedarf importiert)
  ├─ src/agents/supervisor.py
  ├─ src/agents/report_writer.py
  ├─ src/orchestration/department_runtime.py → autogen
  └─ src/orchestration/synthesis_runtime.py  → autogen

src/pipeline_runner.py
  ├─ from src.agents.specs import AGENT_SPECS              ✅ pure
  └─ from src.agents.runtime_factory import create_runtime_agents  ❌ heavy (gewollt)
```

---

## Patch-Sequenz

### Patch 1 — `src/agents/specs.py` anlegen

Neue Datei. Enthält nur `AGENT_SPECS` dict + Import von `AgentSpec` aus `registry.py`.  
Kein Heavy-Import.

**Quelle:** `AGENT_SPECS`-Block aus `definitions.py` extrahieren.

```python
"""Agent metadata specs — pure, no runtime dependencies."""
from __future__ import annotations

from src.agents.registry import AgentSpec

AGENT_SPECS = {
    "Supervisor": AgentSpec("Supervisor", "🧭", "#0f4c81", "Owns intake normalization, routing, and run control."),
    "CompanyDepartment": AgentSpec("CompanyDepartment", "🏢", "#1b7f5a", "AutoGen group for company facts, asset scope, and economic signals."),
    "MarketDepartment": AgentSpec("MarketDepartment", "📡", "#cc6f16", "AutoGen group for market context, circularity, and analytics signals."),
    "BuyerDepartment": AgentSpec("BuyerDepartment", "🌐", "#167d7f", "AutoGen group for peers, buyers, and redeployment paths."),
    "ContactDepartment": AgentSpec("ContactDepartment", "👤", "#0e7490", "AutoGen group for contact discovery at prioritized buyer firms."),
    "SynthesisDepartment": AgentSpec("SynthesisDepartment", "🧠", "#7b4bc4", "AG2 group that synthesizes all domain reports into a Liquisto briefing."),
    "ReportWriter": AgentSpec("ReportWriter", "📄", "#374151", "Turns the approved analysis into an operator-facing report."),
    "CompanyLead": AgentSpec("CompanyLead", "🧩", "#1b7f5a", "Leads the Company Department group."),
    "MarketLead": AgentSpec("MarketLead", "🧩", "#cc6f16", "Leads the Market Department group."),
    "BuyerLead": AgentSpec("BuyerLead", "🧩", "#167d7f", "Leads the Buyer Department group."),
    "ContactLead": AgentSpec("ContactLead", "🧩", "#0e7490", "Leads the Contact Intelligence Department group."),
    "SynthesisLead": AgentSpec("SynthesisLead", "🧩", "#7b4bc4", "Leads the Strategic Synthesis Department group."),
    "CompanyResearcher": AgentSpec("CompanyResearcher", "🔎", "#1b7f5a", "Research specialist inside the Company Department."),
    "MarketResearcher": AgentSpec("MarketResearcher", "🔎", "#cc6f16", "Research specialist inside the Market Department."),
    "BuyerResearcher": AgentSpec("BuyerResearcher", "🔎", "#167d7f", "Research specialist inside the Buyer Department."),
    "ContactResearcher": AgentSpec("ContactResearcher", "🔎", "#0e7490", "Contact discovery specialist inside the Contact Department."),
    "CompanyCritic": AgentSpec("CompanyCritic", "🔍", "#b42318", "Reviews Company Department outputs."),
    "MarketCritic": AgentSpec("MarketCritic", "🔍", "#b42318", "Reviews Market Department outputs."),
    "BuyerCritic": AgentSpec("BuyerCritic", "🔍", "#b42318", "Reviews Buyer Department outputs."),
    "ContactCritic": AgentSpec("ContactCritic", "🔍", "#b42318", "Reviews Contact Intelligence outputs."),
    "SynthesisCritic": AgentSpec("SynthesisCritic", "🔍", "#b42318", "Reviews synthesis quality and cross-domain consistency."),
    "CompanyJudge": AgentSpec("CompanyJudge", "⚖️", "#6941c6", "Resolves unresolved Company Department conflicts."),
    "MarketJudge": AgentSpec("MarketJudge", "⚖️", "#6941c6", "Resolves unresolved Market Department conflicts."),
    "BuyerJudge": AgentSpec("BuyerJudge", "⚖️", "#6941c6", "Resolves unresolved Buyer Department conflicts."),
    "ContactJudge": AgentSpec("ContactJudge", "⚖️", "#6941c6", "Resolves unresolved Contact Intelligence conflicts."),
    "SynthesisJudge": AgentSpec("SynthesisJudge", "⚖️", "#6941c6", "Final decision-maker for synthesis edge cases."),
    "CompanyCodingSpecialist": AgentSpec("CompanyCodingSpecialist", "🧰", "#475467", "Refines blocked Company Department research paths."),
    "MarketCodingSpecialist": AgentSpec("MarketCodingSpecialist", "🧰", "#475467", "Refines blocked Market Department research paths."),
    "BuyerCodingSpecialist": AgentSpec("BuyerCodingSpecialist", "🧰", "#475467", "Refines blocked Buyer Department research paths."),
    "ContactCodingSpecialist": AgentSpec("ContactCodingSpecialist", "🧰", "#475467", "Refines blocked Contact Intelligence research paths."),
}
```

---

### Patch 2 — `src/agents/runtime_factory.py` anlegen

Neue Datei. Enthält nur `create_runtime_agents()` + die Heavy-Imports.

```python
"""Runtime agent factory — imports AG2-dependent modules."""
from __future__ import annotations

from src.agents.report_writer import ReportWriterAgent
from src.agents.supervisor import SupervisorAgent
from src.orchestration.department_runtime import DepartmentRuntime
from src.orchestration.synthesis_runtime import SynthesisRuntime


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
        "report_writer": ReportWriterAgent(),
    }
```

---

### Patch 3 — `src/agents/__init__.py` neutralisieren

Side-effect-frei machen. Kein Re-Export von Heavy-Runtime.

```python
"""Agent package — import specs or runtime_factory explicitly."""
```

---

### Patch 4 — `src/pipeline_runner.py` umstellen

Imports von `definitions` auf `specs` + `runtime_factory` umbiegen.

```diff
-from src.agents.definitions import AGENT_SPECS, create_runtime_agents
+from src.agents.specs import AGENT_SPECS
+from src.agents.runtime_factory import create_runtime_agents
```

Keine weiteren Änderungen in `pipeline_runner.py` nötig — alle Nutzungen von `AGENT_SPECS` und `create_runtime_agents` bleiben identisch.

---

### Patch 5 — `src/agents/definitions.py` als Kompatibilitätsschicht belassen

Temporäre Brücke, damit eventuell nicht gefundene Aufrufer nicht brechen.  
Wird in einem späteren Cleanup entfernt.

```python
"""Compatibility shim — use specs.py and runtime_factory.py directly."""
from src.agents.specs import AGENT_SPECS
from src.agents.runtime_factory import create_runtime_agents

__all__ = ["AGENT_SPECS", "create_runtime_agents"]
```

**Hinweis:** Dieser Shim importiert weiterhin `runtime_factory` und ist damit NICHT pure. Das ist akzeptabel, weil kein pure-Pfad mehr über `definitions.py` läuft. Der Shim existiert nur als Sicherheitsnetz für unbekannte Aufrufer und wird nach Validierung entfernt.

---

### Patch 6 — Smoke-Test erweitern

In `tests/smoke/test_preflight.py::test_pure_modules_importable` ergänzen:

```diff
+    import src.agents.specs
+    import src.agents.registry
```

Damit wird sichergestellt, dass `src.agents.specs` ohne autogen importierbar ist.

---

## Validierung

Nach Anwendung aller Patches:

```bash
# 1. Akzeptanztest: pure Module ohne autogen importierbar
pytest tests/smoke/test_preflight.py::test_pure_modules_importable -v

# 2. Gesamte Testsuite
pytest

# 3. Manueller Importcheck
python -c "import src.agents.specs; print('specs: OK')"
python -c "import src.agents.critic; print('critic: OK')"
python -c "import src.agents; print('__init__: OK')"

# 4. Pipeline-Funktionstest (benötigt API-Key + autogen)
python -c "from src.agents.runtime_factory import create_runtime_agents; print('factory: OK')"
```

---

## Zusammenfassung

| Patch | Datei | Aktion | Pure? |
|-------|-------|--------|-------|
| 1 | `src/agents/specs.py` | Neu — AGENT_SPECS | ✅ |
| 2 | `src/agents/runtime_factory.py` | Neu — create_runtime_agents | ❌ (gewollt) |
| 3 | `src/agents/__init__.py` | Neutralisieren | ✅ |
| 4 | `src/pipeline_runner.py` | Import umbiegen | — |
| 5 | `src/agents/definitions.py` | Kompatibilitäts-Shim | ❌ (temporär) |
| 6 | `tests/smoke/test_preflight.py` | Testabdeckung erweitern | — |

**Reihenfolge ist strikt:** 1 → 2 → 3 → 4 → 5 → 6 → Validierung.  
Patches 1+2 sind unabhängig voneinander, aber beide müssen vor 3+4 existieren.

---

## Umsetzungsprotokoll

**Datum:** 2025-03-25  
**Status:** ✅ Alle 6 Patches umgesetzt und validiert

### Durchgeführte Schritte

1. **Analyse des Ist-Importgraphen**
   - `definitions.py` importierte `DepartmentRuntime` → `lead.py` → `autogen` und `SynthesisRuntime` → `synthesis_department.py` → `autogen`
   - `__init__.py` re-exportierte beides → jeder `import src.agents` zog autogen nach
   - Einzige Konsumenten von `AGENT_SPECS` / `create_runtime_agents`: `pipeline_runner.py` und `__init__.py`
   - `ui/app.py` importiert nur `SupervisorAgent` direkt (nicht betroffen)

2. **Patch 1 — `src/agents/specs.py` angelegt**
   - `AGENT_SPECS`-Dict 1:1 aus `definitions.py` extrahiert
   - Einziger Import: `AgentSpec` aus `registry.py` (pure dataclass)

3. **Patch 2 — `src/agents/runtime_factory.py` angelegt**
   - `create_runtime_agents()` 1:1 aus `definitions.py` extrahiert
   - Heavy-Imports (`DepartmentRuntime`, `SynthesisRuntime`) bewusst hier gebündelt

4. **Patch 3 — `src/agents/__init__.py` neutralisiert**
   - Inhalt auf einzeiligen Docstring reduziert
   - Kein Re-Export, kein Side-Effect

5. **Patch 4 — `src/pipeline_runner.py` umgestellt**
   - `from src.agents.definitions import …` → `from src.agents.specs import AGENT_SPECS` + `from src.agents.runtime_factory import create_runtime_agents`
   - Keine weiteren Änderungen nötig — alle Nutzungsstellen blieben identisch

6. **Patch 5 — `src/agents/definitions.py` als Kompatibilitäts-Shim**
   - Re-exportiert aus `specs` + `runtime_factory`
   - Fängt unbekannte Aufrufer ab, ist aber selbst nicht mehr im kritischen Pfad
   - Zur Entfernung vorgemerkt nach Bestätigung, dass keine weiteren Konsumenten existieren

7. **Patch 6 — Smoke-Test erweitert**
   - `src.agents.specs` und `src.agents.registry` in `test_pure_modules_importable` aufgenommen

### Validierungsergebnisse

```
$ python -c "import src.agents.specs; print('specs: OK')"                    → OK
$ python -c "import src.agents.registry; print('registry: OK')"              → OK
$ python -c "import src.agents; print('__init__: OK')"                       → OK
$ python -c "import src.agents.critic; print('critic: OK')"                  → OK
$ python -c "import src.agents.critic; import sys; print('autogen loaded:', 'autogen' in sys.modules)"  → False
$ python -c "import src.agents.specs; import sys; print('autogen loaded:', 'autogen' in sys.modules)"   → False
$ pytest tests/smoke/test_preflight.py::test_pure_modules_importable -v       → PASSED
$ pytest tests/                                                               → 157 passed in 32.97s
```

### Akzeptanzkriterien — Abgleich

| Kriterium | Ergebnis |
|-----------|----------|
| `test_pure_modules_importable` läuft ohne `autogen` | ✅ PASSED |
| `import src.agents.critic` zieht kein `autogen` nach | ✅ `autogen in sys.modules` → `False` |
| `src.agents.__init__` enthält keine Heavy-Runtime-Imports | ✅ Nur Docstring |
| `pipeline_runner.py` funktioniert über explizite Runtime-Imports | ✅ 157/157 Tests grün |

### Offene Punkte

- `definitions.py` Kompatibilitäts-Shim kann entfernt werden, sobald bestätigt ist, dass kein externer Aufrufer mehr darauf zugreift (aktuell: keiner gefunden außer dem neutralisierten `__init__.py`)
