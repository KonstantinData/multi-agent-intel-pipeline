# app.py — Vollständige Implementierungsspezifikation

> Dieses Dokument ist die komplette Übergabe-Spezifikation für die Neuimplementierung von `ui/app.py`.
> Es enthält alle Architekturentscheidungen, Datenverträge, i18n-Integration, Branding-Regeln und
> funktionsgenaue Implementierungsanweisungen. Ziel: Ein anderer GPT kann `app.py` allein aus diesem
> Dokument + den referenzierten Dateien korrekt und vollständig schreiben.

---

## 1. Projektkontext

### 1.1 Was ist das?
Streamlit-UI für das Liquisto Department Runtime — ein Multi-Agent-Intelligence-System, das
Pre-Meeting-Briefings erstellt. Die UI zeigt Recherche-Ergebnisse, Empfehlungen, Kontakte und
ermöglicht Follow-up-Fragen.

### 1.2 Dateipfade (relativ zu Projekt-Root)
```
ui/app.py              ← ZU ERSTELLEN (diese Spec)
ui/i18n.py             ← EXISTIERT — alle UI-Strings DE/EN
ui/theme.py            ← EXISTIERT — Liquisto Brand-CSS
assets/image/liquisto_logo.png  ← EXISTIERT — 500×113px, Grayscale
.streamlit/config.toml ← EXISTIERT — Streamlit Theme
```

### 1.3 Abhängigkeiten (Imports aus dem Projekt)
```python
from src.app.use_cases import build_standard_backlog
from src.config import summarize_runtime_models
from src.exporters.pdf_report import generate_pdf
from src.orchestration.follow_up import answer_follow_up, load_run_artifact
from src.pipeline_runner import AGENT_META, PIPELINE_STEPS, run_pipeline
```

### 1.4 Externe Abhängigkeiten
- `streamlit` (bereits installiert)
- `threading`, `time`, `json`, `os`, `sys`, `pathlib`, `queue` (stdlib)

---

## 2. Architektur-Entscheidungen

### 2.1 Sprachwechsel (DE/EN)
- `st.session_state.lang` — Default `"de"`, Toggle zwischen `"de"` und `"en"`
- Toggle-Position: **Sidebar, direkt unter dem Logo**, als `st.toggle`
- Label des Toggles: `L["lang_toggle"]` (zeigt immer die *andere* Sprache: "English" wenn DE aktiv, "Deutsch" wenn EN aktiv)
- Bei Toggle-Wechsel: `st.rerun()` — die gesamte Seite rendert mit neuen Labels
- Alle UI-Strings über `L = get_labels(st.session_state.lang)` → dann `L["key"]`
- **Niemals** hardcoded deutsche oder englische Strings in Render-Funktionen

### 2.2 Branding
- `st.markdown(BRAND_CSS, unsafe_allow_html=True)` — einmal am Anfang nach `set_page_config`
- Logo: `st.image("assets/image/liquisto_logo.png", width=160)` — erstes Element in Sidebar
- Page config: `page_title="Liquisto Briefing"`, `page_icon="📋"`, `layout="wide"`
- Kein zusätzliches Inline-CSS in Render-Funktionen — alles über `theme.py`

### 2.3 Tab-Struktur (Post-Run)
```
Tab 1: L["tab_briefing"]    → "Briefing"              — Primäransicht
Tab 2: L["tab_research"]    → "Recherche-Details"      — Tiefe Recherche
Tab 3: L["tab_followup"]    → "Rückfragen"             — Follow-up Q&A
Tab 4: L["tab_quality"]     → "Qualität & Status"      — QA/Debug
Tab 5: L["tab_log"]         → "Protokoll"              — Message Feed
```

### 2.4 Sidebar-Struktur (von oben nach unten)
```
1. Logo (liquisto_logo.png, width=160)
2. Sprachwechsel-Toggle
3. ── Divider ──
4. Überschrift: L["new_run"]
5. Text-Input: L["company_name"]
6. Text-Input: L["web_domain"]
7. Button: L["start_run"]
8. ── Divider ──
9. Überschrift: L["load_run"]  (als st.subheader oder st.markdown("#### ..."))
10. Selectbox: L["select_run"]
11. Button: L["load_selected"]
12. ── Divider ──
13. Caption: L["runtime_models"]: {summarize_runtime_models()}
```

**PDF-Downloads NICHT in der Sidebar** — sie wandern in den Briefing-Tab (siehe 3.2).

### 2.5 n/v-Bereinigung
- Der interne Platzhalter `"n/v"` darf **niemals** dem Nutzer angezeigt werden
- Hilfsfunktion `_show(value)` → gibt `value` zurück wenn es nicht in `{"n/v", "n/a", "", None}` ist, sonst `None`
- Wenn `_show()` `None` zurückgibt → Feld/Zeile/Block komplett ausblenden (nicht "Nicht verfügbar" anzeigen)
- Ausnahme: Leerzustände bei Listen → dort die passende `L["no_..."]`-Meldung als `st.caption`

---

## 3. Funktions-Spezifikationen

### 3.0 Initialisierung & State

```python
_init_state()   # wie bisher — gleiche defaults
_drain_queue()  # wie bisher — gleiche Queue-Logik
```

Zusätzlicher State-Key:
```python
"lang": "de"  # NEU — Sprachauswahl
```

Alle anderen State-Keys bleiben identisch zur aktuellen app.py:
`running`, `done`, `pipeline_started`, `messages`, `pipeline_data`, `run_context`,
`usage`, `budget`, `status`, `error`, `run_id`, `input_company`, `input_domain`,
`worker_queue`, `follow_up_answer`, `loaded_notice`

### 3.1 Hilfsfunktionen (übernehmen, anpassen)

```python
def _show(value: Any) -> str | None:
    """Return value as string if meaningful, else None."""
    text = str(value or "").strip()
    return text if text and text not in {"n/v", "n/a"} else None

def _message_preview(content: str, limit: int = 140) -> str:
    # wie bisher

def _step_progress() -> tuple[int, str]:
    # wie bisher, aber Labels aus L statt hardcoded
    # "Waiting to start" → L["waiting"]
    # "Run completed" → L["run_completed"]
    # Step-Labels bleiben englisch (Agent-Namen sind technisch)

def _task_rows() -> list[dict]:
    # wie bisher

def _department_packages() -> dict[str, dict]:
    # wie bisher

def _run_dirs() -> list[Path]:
    # wie bisher

def _load_run(run_id: str) -> None:
    # wie bisher

def _start_pipeline(company_name: str, web_domain: str) -> None:
    # wie bisher

def _ranked_service_paths(synthesis: dict) -> list[dict]:
    # wie bisher — reine Datenlogik, keine Labels
```

### 3.2 _render_briefing_tab(L: Labels) → None

**Struktur:**

```
## {company_name}
Caption: {industry} · {goods_type}   {confidence_badge}
Description (max 400 chars, nur wenn vorhanden)
Info-Box: Economic Signal (nur wenn vorhanden)
── Divider ──

### L["recommendation"]
  Primary recommendation card (st.container(border=True))
    #### {icon} {service_label}
    Caption: L["primary_rec"]
    Reasoning text
    Caption: Service description
  Secondary + Third (2-column layout, nur wenn vorhanden)
  Caption: L["fallback_note"] (nur wenn generation_mode == "fallback")
── Divider ──

Zwei Spalten:
  Links: ### L["talk_about"]
    - next_steps[:4]
    - buyer_summary (wenn Platz)
    - peer_count (wenn Platz)
  Rechts: ### L["validate"]
    - key_risks[:3]
    - open_gaps[:2]
── Divider ──

### L["contacts"]
  3 Contact-Cards nebeneinander (st.columns + st.container(border=True))
    **Name**
    Caption: Rolle · Firma
    Caption: Seniorität (nur wenn vorhanden)
    Info: Outreach (nur wenn vorhanden)
  Caption: "+N L["more_contacts"]" (wenn > 3)
── Divider ──

### L["next_step"]
  st.success(next_steps[0]) oder st.info(L["default_next_step"])
── Divider ──

PDF-Downloads (NEU — hierher verschoben aus Sidebar):
  Zwei Spalten:
    st.download_button(L["download_pdf_de"], ...)
    st.download_button(L["download_pdf_en"], ...)
```

**i18n-Lookups in dieser Funktion:**
- `service_label(area, L)` für Service-Area-Namen
- `service_desc(area, L)` für Service-Beschreibungen
- `service_icon(area)` für Emojis
- `goods_label(classification, L)` für Gütertyp
- `confidence_badge(level, L)` für Konfidenz-Badge
- Alle statischen Texte über `L["key"]`

**Datenquellen (aus `st.session_state.pipeline_data`):**
```python
synthesis = pipeline_data.get("synthesis", {})
company = pipeline_data.get("company_profile", {})
industry = pipeline_data.get("industry_analysis", {})
market = pipeline_data.get("market_network", {})
contacts_section = pipeline_data.get("contact_intelligence", {})
quality = pipeline_data.get("quality_review", {})
```

### 3.3 _render_research_tab(L: Labels) → None

**Struktur:**

```
Expander: L["company_profile"] (expanded=True)
  2 Spalten:
    Links: Name, Website, Branche, Gütertyp
    Rechts: Produkte (max 6)
  Description
  Economic Signals (assessment, recent_events, inventory_signals)
  Asset-Scope (max 8)

Expander: L["market_industry"]
  Branche, Assessment, Demand Outlook, Key Trends
  Repurposing-Signale, Analytics-Signale

Expander: L["buyer_network"]
  Peer Competitors (assessment + companies)
  Downstream Buyers (assessment + companies)
  Monetization Paths, Redeployment Paths

Expander: L["contact_intelligence"]
  Narrative Summary, Coverage Quality
  Kontakt-Liste als verschachtelte Expander:
    "{name} — {rolle} @ {firma}"
    Funktion, Seniorität, Confidence, Relevanz, Outreach
```

**Alle Feld-Labels über L["key"]** — keine hardcoded Strings.
**Alle Werte durch `_show()` filtern** — Felder mit n/v ausblenden.

### 3.4 _render_follow_up_panel(L: Labels) → None

**Struktur:**
```
L["followup_intro"] als st.markdown
Form "follow_up_form":
  Text-Input: L["run_id"] (prefilled mit aktuellem run_id)
  Text-Area: L["followup_question"] mit L["followup_placeholder"]
  Submit-Button: L["submit_question"]

Ergebnis-Anzeige (wenn follow_up_answer vorhanden):
  Container(border=True):
    **{icon} L["answered_by"]: {routed_to}**
    Caption: route_reason
    Answer text
    2 Spalten:
      Links: L["evidence_used"] + Bullet-Liste
      Rechts: L["unresolved_points"] + Bullet-Liste
```

**Fehlerbehandlung:**
- Leere Felder → `st.warning(L["followup_required"])`
- Run nicht gefunden → `st.error(L["followup_not_found"])`
- Exception → `st.error(f"{L['followup_error']}: {exc}")`

### 3.5 _render_quality_tab(L: Labels) → None

**Entspricht dem bisherigen `_render_pipeline_tab`**, aber mit i18n:

```
Expander: L["research_quality"]
  3 Metriken: L["readiness_score"], L["evidence_quality"], L["status"]
  Readiness Reasons
  Open Gaps: L["open_gaps"]

Expander: L["task_status"]
  Status-Icons: ✅ accepted, 🟡 degraded, ❌ rejected, ⏭️ skipped, ⏳ pending
  Format: "{icon} {label} — {assignee} — {status}"

Expander: L["department_packages"] (nur wenn vorhanden)
  st.json pro Department

Expander: L["run_metadata"]
  st.json mit run_id, llm_calls, search_calls, page_fetches,
  estimated_cost_usd, elapsed_seconds, department_timings
```

### 3.6 _render_message_feed() → None

**Identisch zur aktuellen Implementierung** — keine i18n nötig (technische Agent-Namen).

```python
def _render_message_feed() -> None:
    for m in reversed(st.session_state.messages[-40:]):
        agent = m.get("agent", "Agent")
        content = m.get("content", "")
        meta = AGENT_META.get(agent, {"summary": "", "icon": "[]"})
        title = f"{meta.get('icon', '[]')} {agent} - {_message_preview(content)}"
        with st.expander(title, expanded=False):
            st.code(content[:12000], language="json")
```

### 3.7 Live-Run-View (im Main-Body)

**Bedingung:** `st.session_state.running and not st.session_state.done`

```
Progress-Bar: current_step / len(PIPELINE_STEPS)
Current step label

Pipeline-Step-Cards (st.columns):
  Für jeden Step:
    HTML-Div mit CSS-Klasse "pipeline-step active" oder "pipeline-step inactive"
    (CSS kommt aus theme.py — KEIN Inline-Background/Color mehr)
    Inhalt: Icon, Label, Agent-Name

Thread-Start (wie bisher)
Message Feed
time.sleep(0.8) + st.rerun()
```

**Wichtig:** Die Step-Cards nutzen jetzt die CSS-Klassen aus `theme.py` statt Inline-Styles:
```html
<div class="pipeline-step {'active' if active else 'inactive'}">
  <div class="step-icon">{icon}</div>
  <div class="step-label">{label}</div>
  <div class="step-agent">{agent_name}</div>
</div>
```

### 3.8 Post-Run Status-Banner

**Bedingung:** `st.session_state.done and st.session_state.run_id`

```python
company_label = pipeline_data.get("company_profile", {}).get("company_name", run_id)
if status == "completed":
    st.success(f"{L['briefing_ready']} — {company_label}")
elif status == "completed_partial":
    st.warning(f"{L['briefing_partial']} — {company_label}")
elif status == "completed_but_not_usable":
    st.error(f"{L['briefing_unusable']} ({company_label})")
elif loaded_notice == run_id:
    st.info(f"{L['run_loaded']} — {company_label}")
```

### 3.9 Page Header

```python
st.title(L["page_title"])
st.caption(L["page_subtitle"])
```

---

## 4. Datenverträge

### 4.1 pipeline_data Struktur
```python
{
    "company_profile": {
        "company_name": str,
        "legal_form": str,
        "founded": str,
        "headquarters": str,
        "website": str,
        "industry": str,
        "employees": str,
        "revenue": str,
        "products_and_services": list[str],
        "product_asset_scope": list[str],
        "goods_classification": str,  # manufacturer|distributor|held_in_stock|mixed|unclear
        "key_people": list[{"name": str, "role": str}],
        "description": str,
        "economic_situation": {
            "revenue_trend": str,
            "profitability": str,
            "recent_events": list[str],
            "inventory_signals": list[str],
            "financial_pressure": str,
            "assessment": str
        },
        "sources": list[{"title": str, "url": str, "source_type": str, "summary": str}]
    },
    "industry_analysis": {
        "industry_name": str,
        "market_size": str,
        "trend_direction": str,
        "growth_rate": str,
        "key_trends": list[str],
        "overcapacity_signals": list[str],
        "excess_stock_indicators": str,
        "demand_outlook": str,
        "repurposing_signals": list[str],
        "analytics_signals": list[str],
        "assessment": str,
        "sources": list[...]
    },
    "market_network": {
        "target_company": str,
        "peer_competitors": {"companies": list[{"name": str, "city": str, "country": str, "relevance": str}], "assessment": str},
        "downstream_buyers": {"companies": list[...], "assessment": str},
        "service_providers": {"companies": list[...], "assessment": str},
        "cross_industry_buyers": {"companies": list[...], "assessment": str},
        "monetization_paths": list[str],
        "redeployment_paths": list[str]
    },
    "contact_intelligence": {
        "contacts": list[ContactPerson],
        "prioritized_contacts": list[ContactPerson],
        "firms_searched": int,
        "contacts_found": int,
        "coverage_quality": str,
        "narrative_summary": str,
        "open_questions": list[str],
        "sources": list[...]
    },
    "quality_review": {
        "validated_agents": list[str],
        "evidence_health": str,
        "open_gaps": list[str],
        "recommendations": list[str],
        "gap_details": list[...]
    },
    "synthesis": {
        "target_company": str,
        "executive_summary": str,
        "liquisto_service_relevance": list[{"service_area": str, "relevance": str, "reasoning": str}],
        "opportunity_assessment_summary": str,
        "recommended_engagement_paths": list[str],
        "buyer_market_summary": str,
        "key_risks": list[str],
        "next_steps": list[str],
        "sources": list[...],
        "generation_mode": str,  # normal|fallback|blocked
        "confidence": str        # high|medium|low
    },
    "research_readiness": {
        "usable": bool,
        "score": int,
        "reasons": list[str]
    }
}
```

### 4.2 ContactPerson Felder
```python
{
    "name": str,
    "firma": str,
    "rolle_titel": str,
    "funktion": str,
    "senioritaet": str,
    "standort": str,
    "quelle": str,
    "confidence": str,
    "relevance_reason": str,
    "suggested_outreach_angle": str
}
```

### 4.3 AGENT_META (aus pipeline_runner.py)
```python
{
    "Supervisor": {"icon": "🧭", "color": "#0f4c81", "summary": "..."},
    "CompanyDepartment": {"icon": "🏢", "color": "#1b7f5a", "summary": "..."},
    "MarketDepartment": {"icon": "📡", "color": "#cc6f16", "summary": "..."},
    "BuyerDepartment": {"icon": "🌐", "color": "#167d7f", "summary": "..."},
    "ContactDepartment": {"icon": "👤", "color": "#0e7490", "summary": "..."},
    "SynthesisDepartment": {"icon": "🧠", "color": "#7b4bc4", "summary": "..."},
    "ReportWriter": {"icon": "📄", "color": "#374151", "summary": "..."},
    ...
}
```

### 4.4 PIPELINE_STEPS (aus pipeline_runner.py)
```python
[
    ("Supervisor", "Intake + Routing"),
    ("CompanyDepartment", "Company"),
    ("MarketDepartment", "Market"),
    ("BuyerDepartment", "Buyer"),
    ("ContactDepartment", "Contact Intelligence"),
    ("SynthesisDepartment", "Strategic Synthesis"),
    ("ReportWriter", "Report"),
]
```

### 4.5 BACKLOG (aus use_cases.py)
```python
build_standard_backlog()  # → list[dict] mit keys: task_key, label, assignee
```

### 4.6 Follow-up Datenfluss
```python
# Input
load_run_artifact(run_id) → {"run_dir": Path, "pipeline_data": dict, "run_context": dict}
SupervisorAgent().route_question(question, source) → {"route": str, "reason": str}
answer_follow_up(run_id, route, question, pipeline_data, run_context) → {
    "routed_to": str,       # "CompanyDepartment" | "MarketDepartment" | ...
    "answer": str,
    "evidence_used": list[str],
    "unresolved_points": list[str],
}
```

---

## 5. i18n-Integration

### 5.1 Import
```python
from ui.i18n import get_labels, service_label, service_desc, service_icon, goods_label, confidence_badge
from ui.theme import BRAND_CSS
```

### 5.2 Label-Auflösung
```python
# Am Anfang jeder Render-Funktion (oder als Parameter):
L = get_labels(st.session_state.lang)

# Verwendung:
st.markdown(f"### {L['recommendation']}")
st.caption(L["primary_rec"])

# Service-Area-Lookups:
label = service_label("excess_inventory", L)   # → "Überschuss-Inventar-Verwertung" (DE)
desc = service_desc("excess_inventory", L)      # → "Wiederverkauf, Redeployment..."
icon = service_icon("excess_inventory")          # → "📦"

# Goods:
gt = goods_label("manufacturer", L)             # → "Hersteller" (DE) / "Manufacturer" (EN)

# Confidence:
badge = confidence_badge("high", L)             # → "🟢 Hohe Konfidenz" (DE)
```

### 5.3 Sprachwechsel-Mechanik
```python
# In Sidebar, nach Logo:
lang = st.session_state.get("lang", "de")
L = get_labels(lang)
toggled = st.toggle(L["lang_toggle"], value=(lang == "en"), key="lang_toggle")
new_lang = "en" if toggled else "de"
if new_lang != lang:
    st.session_state.lang = new_lang
    st.rerun()
```

---

## 6. Branding-Integration

### 6.1 CSS-Injection
```python
st.set_page_config(page_title="Liquisto Briefing", page_icon="📋", layout="wide")
st.markdown(BRAND_CSS, unsafe_allow_html=True)
```

### 6.2 Logo
```python
# Erstes Element in Sidebar:
with st.sidebar:
    st.image("assets/image/liquisto_logo.png", width=160)
```

### 6.3 Pipeline-Step-Cards (Live Run)
Ersetze die bisherigen Inline-Styles durch CSS-Klassen:
```python
state_class = "active" if active else "inactive"
cols[index].markdown(
    f"""<div class="pipeline-step {state_class}">
      <div class="step-icon">{meta['icon']}</div>
      <div class="step-label">{label}</div>
      <div class="step-agent">{agent_name}</div>
    </div>""",
    unsafe_allow_html=True,
)
```

---

## 7. Gesamtstruktur der app.py

```python
"""Liquisto Briefing UI — pre-meeting preparation dashboard."""
# Imports: stdlib, streamlit, project modules, ui.i18n, ui.theme

# Constants: PROJECT_ROOT, RUNS_DIR, BACKLOG

# Page config + CSS injection

# ── Helper functions ──────────────────────────────────────────────────
# _show(value) → str | None
# _init_state()
# _drain_queue()
# _run_dirs()
# _load_run(run_id)
# _message_preview(content, limit)
# _step_progress()
# _task_rows()
# _department_packages()
# _ranked_service_paths(synthesis)
# _start_pipeline(company_name, web_domain)

# ── Render functions ──────────────────────────────────────────────────
# _render_briefing_tab(L)
# _render_research_tab(L)
# _render_follow_up_panel(L)
# _render_quality_tab(L)
# _render_message_feed()

# ── Main execution ────────────────────────────────────────────────────
# _init_state()
# _drain_queue()
# L = get_labels(st.session_state.lang)

# Sidebar:
#   Logo → Lang Toggle → Divider → New Run → Divider → Load Run → Divider → Models Caption

# Page Header:
#   Title + Subtitle

# Live Run View (if running):
#   Progress → Step Cards → Thread Start → Message Feed → sleep → rerun

# Error display

# Post-Run View (if done):
#   Status Banner
#   Tabs: Briefing | Research | Follow-up | Quality | Log
```

---

## 8. Kritische Regeln

1. **Keine hardcoded Strings** — alles über `L["key"]` aus `i18n.py`
2. **Kein `n/v` in der UI** — alles durch `_show()` filtern, Felder ausblenden wenn None
3. **Kein Inline-CSS** — alles über `theme.py` BRAND_CSS
4. **PDF-Downloads im Briefing-Tab**, nicht in der Sidebar
5. **Sidebar dunkel** (Teal-900) — CSS kommt aus theme.py, keine eigenen Sidebar-Styles
6. **Logo immer sichtbar** — erstes Element in Sidebar
7. **Sprachwechsel löst `st.rerun()` aus** — kein partielles Re-Rendering
8. **Thread-Logik unverändert** — Queue-basierte Pipeline-Ausführung bleibt identisch
9. **Alle Render-Funktionen erhalten `L` als Parameter** (außer `_render_message_feed`)
10. **Follow-up Import von SupervisorAgent bleibt lazy** (innerhalb der Submit-Logik)

---

## 9. Referenz: Bestehende app.py

Die aktuelle `ui/app.py` (≈550 Zeilen) enthält die vollständige funktionierende Logik.
Die Neuimplementierung **behält alle Datenflüsse und State-Mechaniken bei** und ändert nur:

| Aspekt | Alt | Neu |
|--------|-----|-----|
| Strings | Hardcoded DE | `L["key"]` aus i18n.py |
| CSS | Inline-Styles + eigener `<style>`-Block | `BRAND_CSS` aus theme.py |
| Logo | Nicht vorhanden | `st.image(...)` in Sidebar |
| Sprachwechsel | Nicht vorhanden | `st.toggle` + `st.session_state.lang` |
| Tab-Namen | Briefing, Recherche, Follow-up, Pipeline, Messages | L["tab_briefing"], L["tab_research"], L["tab_followup"], L["tab_quality"], L["tab_log"] |
| Tab "Pipeline" | Heißt "Pipeline" | Heißt "Qualität & Status" |
| Tab "Messages" | Heißt "Messages" | Heißt "Protokoll" |
| PDF-Downloads | In Sidebar | Im Briefing-Tab unten |
| n/v-Anzeige | Wird angezeigt | Wird ausgeblendet |
| Step-Cards | Inline background/color | CSS-Klassen aus theme.py |
| Sidebar-Style | Eigener `<style>`-Block | Kommt aus BRAND_CSS |

---

## 10. Testkriterien

Nach Implementierung muss gelten:

- [ ] `streamlit run ui/app.py` startet ohne Fehler
- [ ] Logo sichtbar in Sidebar
- [ ] Sprachwechsel-Toggle wechselt alle sichtbaren Texte
- [ ] Kein `n/v` sichtbar in der UI (bei geladenem Run)
- [ ] Pipeline-Step-Cards nutzen CSS-Klassen statt Inline-Styles
- [ ] PDF-Download-Buttons erscheinen im Briefing-Tab
- [ ] Sidebar ist dunkel (Teal-900)
- [ ] Tabs heißen korrekt in beiden Sprachen
- [ ] Follow-up funktioniert mit i18n-Labels
- [ ] Live-Run-View funktioniert (Thread + Queue + rerun)
