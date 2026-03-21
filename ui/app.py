"""Liquisto Market Intelligence Pipeline – Streamlit UI."""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so 'src' is importable
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

import threading
import time
from queue import Empty, Queue

import streamlit as st

# Must be first Streamlit call
st.set_page_config(
    page_title="Liquisto Market Intelligence",
    page_icon="🔍",
    layout="wide",
)

from src.config import get_model_selection
from src.pipeline_runner import run_pipeline, AGENT_META, PIPELINE_STEPS, _extract_pipeline_data
from src.exporters.pdf_report import generate_pdf

_RUNS_DIR = Path(_PROJECT_ROOT) / "artifacts" / "runs"


# --- Session State Init ---

def _init_state():
    defaults = {
        "running": False,
        "done": False,
        "pipeline_started": False,
        "messages": [],
        "current_agent": None,
        "pipeline_data": {},
        "usage": {},
        "budget": {},
        "run_id": None,
        "status": None,
        "error": None,
        "worker_queue": None,
        "loaded_run_notice": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _drain_worker_queue() -> None:
    """Apply thread-produced events to session state from the main Streamlit run."""
    worker_queue = st.session_state.worker_queue
    if worker_queue is None:
        return

    while True:
        try:
            item = worker_queue.get_nowait()
        except Empty:
            break

        event_type = item.get("event")
        if event_type == "message":
            payload = item["payload"]
            st.session_state.messages.append(payload)
            st.session_state.current_agent = payload.get("agent")
        elif event_type == "result":
            payload = item["payload"]
            st.session_state.pipeline_data = payload["pipeline_data"]
            st.session_state.usage = payload.get("usage", {})
            st.session_state.budget = payload.get("budget", {})
            st.session_state.run_id = payload["run_id"]
            st.session_state.status = payload.get("status")
            st.session_state.error = payload.get("error")
            st.session_state.done = True
            st.session_state.running = False
            st.session_state.pipeline_started = False
            st.session_state.worker_queue = None
        elif event_type == "error":
            st.session_state.error = item["payload"]
            st.session_state.done = True
            st.session_state.running = False
            st.session_state.pipeline_started = False
            st.session_state.worker_queue = None


_drain_worker_queue()


def _message_preview(content: str, limit: int = 140) -> str:
    text = (content or "").replace("\n", " ").strip()
    if not text:
        return "(leer)"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _render_message_feed(messages: list[dict], *, live: bool) -> None:
    ordered_messages = list(reversed(messages)) if live else messages

    for msg in ordered_messages:
        agent = msg.get("agent", "?")
        meta = msg.get("meta", {})
        content = msg.get("content", "") or ""
        ts = msg.get("timestamp", "")[:19]
        msg_type = msg.get("type", "agent_message")

        if msg_type == "debug":
            badge = "🔧 Debug"
        elif msg_type == "error":
            badge = "❌ Fehler"
        else:
            badge = f"{meta.get('icon', '❓')} {agent}"

        title = f"{badge} · {ts} · {_message_preview(content)}"
        with st.expander(title, expanded=live and msg_type == "error"):
            if live:
                st.caption(f"Agent: {agent}")
            st.code(content[:12000] if len(content) > 12000 else content, language="json")


def _progress_agent(agent: str | None) -> str | None:
    if not agent:
        return None
    if agent.endswith("Critic"):
        return agent.removesuffix("Critic")
    return agent


def _latest_run_dir() -> Path | None:
    if not _RUNS_DIR.exists():
        return None
    runs = [path for path in _RUNS_DIR.iterdir() if path.is_dir()]
    if not runs:
        return None
    return max(runs, key=lambda path: path.stat().st_mtime)


def _load_artifact_run(run_dir: Path) -> dict:
    run_meta_path = run_dir / "run_meta.json"
    chat_history_path = run_dir / "chat_history.json"
    pipeline_data_path = run_dir / "pipeline_data.json"

    run_meta = json.loads(run_meta_path.read_text(encoding="utf-8")) if run_meta_path.exists() else {}
    raw_messages = json.loads(chat_history_path.read_text(encoding="utf-8"))

    timestamp = run_meta.get("timestamp", "")
    normalized_messages = []
    ui_messages = []
    for msg in raw_messages:
        agent = msg.get("name", msg.get("role", "unknown"))
        content = msg.get("content", "") or ""
        normalized_messages.append({"agent": agent, "content": content})
        ui_messages.append(
            {
                "type": "agent_message",
                "agent": agent,
                "content": content,
                "timestamp": timestamp,
                "meta": AGENT_META.get(agent, {"icon": "⚙️", "color": "#adb5bd"}),
            }
        )

    if pipeline_data_path.exists():
        pipeline_data = json.loads(pipeline_data_path.read_text(encoding="utf-8"))
    else:
        pipeline_data = _extract_pipeline_data(normalized_messages)
    if "research_readiness" not in pipeline_data:
        pipeline_data = _extract_pipeline_data(normalized_messages)
    target_company = (
        pipeline_data.get("company_profile", {}).get("company_name")
        or pipeline_data.get("synthesis", {}).get("target_company")
        or ""
    )

    return {
        "run_id": run_meta.get("run_id", run_dir.name),
        "messages": ui_messages,
        "pipeline_data": pipeline_data,
        "usage": run_meta.get("usage", {}),
        "budget": run_meta.get("budget", {}),
        "input_company": target_company,
        "error": run_meta.get("error"),
        "status": run_meta.get("status", "completed"),
    }


def _ui_model_hint() -> str:
    preferred_model, structured_model = get_model_selection()
    if preferred_model == structured_model:
        return preferred_model
    return f"{preferred_model} / {structured_model}"


# --- Sidebar ---

with st.sidebar:
    st.image("https://www.liquisto.com/hubfs/Logos/liquisto-logo.svg", width=180)
    st.markdown("---")
    st.markdown("### Neue Recherche")
    company_name = st.text_input("Firmenname", placeholder="z.B. Lenze SE")
    web_domain = st.text_input("Web Domain", placeholder="z.B. lenze.com")

    start_disabled = st.session_state.running or not company_name or not web_domain
    start_btn = st.button(
        "🚀 Pipeline starten",
        disabled=start_disabled,
        use_container_width=True,
        type="primary",
    )

    latest_run = _latest_run_dir()
    if latest_run is not None:
        st.markdown("---")
        st.markdown("### Vorhandene Artefakte")
        st.caption(f"Letzter Run: `{latest_run.name}`")
        load_latest_btn = st.button(
            "🗂️ Letzten Run laden",
            disabled=st.session_state.running,
            use_container_width=True,
        )
    else:
        load_latest_btn = False

    if st.session_state.done and st.session_state.status in {"completed", "completed_but_not_usable"}:
        st.markdown("---")
        st.markdown("### 📥 Report Download")

        pdf_de = generate_pdf(st.session_state.pipeline_data, lang="de")
        st.download_button(
            "📄 PDF Deutsch",
            data=pdf_de,
            file_name=f"liquisto_briefing_{st.session_state.get('input_company', company_name).replace(' ', '_')}_DE.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

        pdf_en = generate_pdf(st.session_state.pipeline_data, lang="en")
        st.download_button(
            "📄 PDF English",
            data=pdf_en,
            file_name=f"liquisto_briefing_{st.session_state.get('input_company', company_name).replace(' ', '_')}_EN.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown("---")
    st.markdown(
        f"<small>Powered by AG2 + OpenAI · Models: {_ui_model_hint()}</small>",
        unsafe_allow_html=True,
    )


# --- Main Area ---

st.title("🔍 Liquisto Market Intelligence")
st.caption("Multi-Agent Pipeline für B2B Sales Meeting Vorbereitung")

if start_btn:
    # Reset state and store input values
    st.session_state.running = True
    st.session_state.done = False
    st.session_state.pipeline_started = False
    st.session_state.messages = []
    st.session_state.current_agent = None
    st.session_state.pipeline_data = {}
    st.session_state.usage = {}
    st.session_state.budget = {}
    st.session_state.status = None
    st.session_state.error = None
    st.session_state.input_company = company_name
    st.session_state.input_domain = web_domain
    st.session_state.worker_queue = Queue()
    st.session_state.loaded_run_notice = None
    st.rerun()

if load_latest_btn and latest_run is not None:
    try:
        loaded_run = _load_artifact_run(latest_run)
        st.session_state.running = False
        st.session_state.done = True
        st.session_state.pipeline_started = False
        st.session_state.messages = loaded_run["messages"]
        st.session_state.current_agent = loaded_run["messages"][-1]["agent"] if loaded_run["messages"] else None
        st.session_state.pipeline_data = loaded_run["pipeline_data"]
        st.session_state.usage = loaded_run.get("usage", {})
        st.session_state.budget = loaded_run.get("budget", {})
        st.session_state.run_id = loaded_run["run_id"]
        st.session_state.status = loaded_run.get("status")
        st.session_state.error = loaded_run.get("error")
        st.session_state.worker_queue = None
        if loaded_run["input_company"]:
            st.session_state.input_company = loaded_run["input_company"]
        st.session_state.loaded_run_notice = loaded_run["run_id"]
        st.rerun()
    except Exception as exc:
        st.session_state.error = f"Artifact-Run konnte nicht geladen werden: {exc}"
        st.session_state.done = True
        st.session_state.running = False
        st.session_state.pipeline_started = False
        st.session_state.worker_queue = None
        st.rerun()

if st.session_state.running and not st.session_state.done:
    # --- Progress Section ---
    st.markdown("## Pipeline Fortschritt")

    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step indicators
    step_cols = st.columns(len(PIPELINE_STEPS))
    step_placeholders = []
    for i, (agent_name, label) in enumerate(PIPELINE_STEPS):
        with step_cols[i]:
            meta = AGENT_META.get(agent_name, {})
            step_placeholders.append(st.empty())
            step_placeholders[i].markdown(
                f"<div style='text-align:center;padding:8px;border-radius:8px;"
                f"background:#f0f0f0;'>"
                f"<div style='font-size:24px'>{meta.get('icon', '⚙️')}</div>"
                f"<div style='font-size:11px;color:#666'>{label}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("## 💬 Agent-Kommunikation (Live)")
    chat_container = st.container(height=500)

    # Run pipeline in background
    worker_queue = st.session_state.worker_queue

    def _on_message(event):
        worker_queue.put({"event": "message", "payload": event})

    _company = st.session_state.input_company
    _domain = st.session_state.input_domain

    def _run():
        try:
            result = run_pipeline(
                company_name=_company,
                web_domain=_domain,
                on_message=_on_message,
            )
            worker_queue.put({"event": "result", "payload": result})
        except Exception as e:
            worker_queue.put({"event": "error", "payload": str(e)})

    # Start pipeline thread ONCE
    if not st.session_state.pipeline_started:
        st.session_state.pipeline_started = True
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    _drain_worker_queue()

    # Show current progress snapshot
    agent_order = [name for name, _ in PIPELINE_STEPS]
    msgs = st.session_state.messages
    current = _progress_agent(st.session_state.current_agent)

    if st.session_state.done:
        st.rerun()

    if current and current in agent_order:
        idx = agent_order.index(current)
        progress_bar.progress(min((idx + 1) / len(PIPELINE_STEPS), 1.0))
        status_text.markdown(f"**Aktiver Agent:** {AGENT_META.get(current, {}).get('icon', '')} {current}")

        for i, (agent_name, label) in enumerate(PIPELINE_STEPS):
            meta = AGENT_META.get(agent_name, {})
            if i < idx:
                bg, border = "#d4edda", f"2px solid {meta.get('color', '#198754')}"
                icon_suffix = " ✅"
            elif i == idx:
                bg, border = "#fff3cd", f"2px solid {meta.get('color', '#fd7e14')}"
                icon_suffix = " ⏳"
            else:
                bg, border = "#f0f0f0", "1px solid #ddd"
                icon_suffix = ""
            step_placeholders[i].markdown(
                f"<div style='text-align:center;padding:8px;border-radius:8px;"
                f"background:{bg};border:{border}'>"
                f"<div style='font-size:24px'>{meta.get('icon', '⚙️')}{icon_suffix}</div>"
                f"<div style='font-size:11px'>{label}</div></div>",
                unsafe_allow_html=True,
            )
    else:
        status_text.markdown("**Aktiver Agent:** Initialisierung...")

    # Render all messages so far
    st.caption(f"Live-Feed aktiv · {len(msgs)} Nachrichten")
    with chat_container:
        _render_message_feed(msgs, live=True)

    # Auto-refresh while running so the feed advances without user input.
    time.sleep(1)
    st.rerun()

elif st.session_state.done:
    # --- Results View ---
    if st.session_state.error:
        st.error(f"Pipeline fehlgeschlagen: {st.session_state.error}")
        st.caption("Der Lauf wurde nicht als erfolgreich markiert. Unten steht der Chat-Log zur Diagnose.")

        validation_errors = st.session_state.pipeline_data.get("validation_errors", [])
        if validation_errors:
            st.markdown("### Validierungsfehler")
            for item in validation_errors:
                st.warning(f"{item.get('agent', '?')} / {item.get('section', '?')}: {item.get('details', 'n/v')}")

        st.markdown("### Chat-Log")
        _render_message_feed(st.session_state.messages, live=False)
    else:
        if st.session_state.status == "completed_but_not_usable":
            st.warning(f"Pipeline technisch abgeschlossen, aber fachlich noch nicht meeting-tauglich – Run ID: {st.session_state.run_id}")
        else:
            st.success(f"✅ Pipeline abgeschlossen – Run ID: {st.session_state.run_id}")
        if st.session_state.loaded_run_notice == st.session_state.run_id:
            st.info("Diese Ansicht wurde aus dem zuletzt gespeicherten Artifact-Run geladen.")

        data = st.session_state.pipeline_data
        usage = st.session_state.usage if isinstance(st.session_state.usage, dict) else {}
        usage_total = usage.get("total", {}) if isinstance(usage, dict) else {}
        budget = st.session_state.budget if isinstance(st.session_state.budget, dict) else {}
        readiness = data.get("research_readiness", {})
        if st.session_state.status == "completed_but_not_usable":
            reasons = readiness.get("reasons", []) if isinstance(readiness, dict) else []
            if reasons:
                st.caption("Hauptgruende:")
                for reason in reasons:
                    st.warning(reason)
        validation_errors = data.get("validation_errors", [])
        if validation_errors:
            st.warning("Einige Agentenantworten konnten nicht gegen die Schemas validiert werden. Die betroffenen Abschnitte wurden verworfen.")

        if usage_total:
            col_cost, col_prompt, col_completion, col_total = st.columns(4)
            col_cost.metric("Kosten", f"${usage_total.get('total_cost', 0.0):.4f}")
            col_prompt.metric("Prompt-Tokens", f"{usage_total.get('prompt_tokens', 0):,}")
            col_completion.metric("Completion-Tokens", f"{usage_total.get('completion_tokens', 0):,}")
            col_total.metric("Total Tokens", f"{usage_total.get('total_tokens', 0):,}")
            if budget:
                st.caption(
                    "Budgetverbrauch: "
                    f"{budget.get('groupchat_rounds_used', 0)}/{budget.get('max_groupchat_rounds', 0)} GroupChat-Runden, "
                    f"{budget.get('tool_calls_used', 0)}/{budget.get('max_tool_calls', 0)} Tool-Calls, "
                    f"{budget.get('max_stage_attempts', 0)} max. Versuche je Stage, "
                    f"{budget.get('elapsed_seconds', 0)}s Laufzeit."
                )

        tab_summary, tab_company, tab_industry, tab_buyers, tab_qa, tab_chat = st.tabs([
            "📋 Briefing", "🏢 Firmenprofil", "📡 Branche", "🌐 Käufer", "🔍 Evidenz", "💬 Chat-Log"
        ])

        with tab_summary:
            synthesis = data.get("synthesis", {})
            st.markdown("### Executive Summary")
            st.write(synthesis.get("executive_summary", "Keine Daten"))

            st.markdown("### Liquisto Service-Relevanz")
            for item in synthesis.get("liquisto_service_relevance", []):
                if isinstance(item, dict):
                    rel = item.get("relevance", "?")
                    color_map = {"hoch": "🟢", "mittel": "🟡", "niedrig": "🔴", "unklar": "⚪"}
                    dot = color_map.get(rel.lower(), "⚪")
                    st.markdown(f"**{dot} {item.get('service_area', '?')}** – {rel}")
                    st.caption(item.get("reasoning", ""))

            st.markdown("### Einschätzung je Option")
            for case in synthesis.get("case_assessments", []):
                if isinstance(case, dict):
                    with st.expander(f"**{case.get('option', '?').upper()}** – {case.get('summary', '')}"):
                        for arg in case.get("arguments", []):
                            if isinstance(arg, dict):
                                d = arg.get("direction", "").upper()
                                icon = "✅" if d == "PRO" else "❌"
                                st.markdown(f"{icon} **{d}:** {arg.get('argument', '')}")
                                st.caption(f"Basierend auf: {arg.get('based_on', 'n/v')}")

        with tab_company:
            profile = data.get("company_profile", {})
            if profile:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Unternehmen:** {profile.get('company_name', 'n/v')}")
                    st.markdown(f"**Rechtsform:** {profile.get('legal_form', 'n/v')}")
                    st.markdown(f"**Gegründet:** {profile.get('founded', 'n/v')}")
                    st.markdown(f"**Hauptsitz:** {profile.get('headquarters', 'n/v')}")
                with col2:
                    st.markdown(f"**Branche:** {profile.get('industry', 'n/v')}")
                    st.markdown(f"**Mitarbeiter:** {profile.get('employees', 'n/v')}")
                    st.markdown(f"**Umsatz:** {profile.get('revenue', 'n/v')}")
                    st.markdown(f"**Website:** {profile.get('website', 'n/v')}")

                products = profile.get("products_and_services", [])
                if products:
                    st.markdown("**Produkte & Dienstleistungen:**")
                    for p in products:
                        st.markdown(f"- {p}")
            else:
                st.info("Keine Profildaten verfügbar")

        with tab_industry:
            industry = data.get("industry_analysis", {})
            if industry:
                st.markdown(f"**Branche:** {industry.get('industry_name', 'n/v')}")
                st.markdown(f"**Marktgröße:** {industry.get('market_size', 'n/v')}")
                st.markdown(f"**Trend:** {industry.get('trend_direction', 'n/v')}")
                st.markdown(f"**Wachstum:** {industry.get('growth_rate', 'n/v')}")
                st.markdown(f"**Einschätzung:** {industry.get('assessment', 'n/v')}")
            else:
                st.info("Keine Branchendaten verfügbar")

        with tab_buyers:
            market = data.get("market_network", {})
            for tier_key, tier_label in [
                ("peer_competitors", "🏭 Peer-Konkurrenten"),
                ("downstream_buyers", "📦 Abnehmer"),
                ("service_providers", "🔧 Service-Anbieter"),
                ("cross_industry_buyers", "🔀 Cross-Industry Käufer"),
            ]:
                tier = market.get(tier_key, {})
                if isinstance(tier, dict):
                    companies = tier.get("companies", [])
                    with st.expander(f"{tier_label} ({len(companies)})"):
                        if tier.get("assessment"):
                            st.caption(tier["assessment"])
                        for buyer in companies:
                            if isinstance(buyer, dict):
                                st.markdown(
                                    f"- **{buyer.get('name', '?')}** "
                                    f"({buyer.get('city', '')}, {buyer.get('country', '')}) – "
                                    f"{buyer.get('relevance', '')}"
                                )

        with tab_qa:
            qa = data.get("quality_review", {})
            if qa:
                st.markdown(f"**Evidenzqualität:** {qa.get('evidence_health', 'n/v')}")
                gaps = qa.get("open_gaps", [])
                if gaps:
                    st.markdown("**Offene Lücken:**")
                    for g in gaps:
                        st.warning(g)
                gap_details = qa.get("gap_details", [])
                if gap_details:
                    st.markdown("**QA-Details:**")
                    for detail in gap_details:
                        if not isinstance(detail, dict):
                            continue
                        severity = str(detail.get("severity", "n/v")).upper()
                        agent = detail.get("agent", "QA")
                        field_path = detail.get("field_path", "")
                        label = f"{severity} · {agent}"
                        if field_path and field_path != "*":
                            label += f" · {field_path}"
                        with st.expander(label):
                            st.write(detail.get("summary", "n/v"))
                            recommendation = detail.get("recommendation", "")
                            if recommendation:
                                st.caption(f"Empfehlung: {recommendation}")
            else:
                st.info("Keine QA-Daten verfügbar")

            if validation_errors:
                st.markdown("**Schema-Validierungsfehler:**")
                for item in validation_errors:
                    st.warning(f"{item.get('agent', '?')} / {item.get('section', '?')}: {item.get('details', 'n/v')}")

        with tab_chat:
            _render_message_feed(st.session_state.messages, live=False)

else:
    # Landing page
    st.markdown(
        """
        ### So funktioniert's

        1. **Firmenname + Domain** in der Sidebar eingeben
        2. **Pipeline starten** – 6 Agenten recherchieren automatisch
        3. **Live verfolgen** wie die Agenten kommunizieren
        4. **PDF herunterladen** (Deutsch + Englisch)

        ---

        #### Pipeline-Schritte

        | Schritt | Agent | Aufgabe |
        |---------|-------|---------|
        | 1 | 🛎️ Concierge | Intake validieren |
        | 2 | 🏢 CompanyIntelligence | Firmenprofil erstellen |
        | 3 | 📡 StrategicSignals | Branchenanalyse |
        | 4 | 🌐 MarketNetwork | 4-stufiges Käufernetzwerk |
        | 5 | 🔍 EvidenceQA | Evidenz prüfen |
        | 6 | 📋 Synthesis | Briefing mit Pro/Contra |
        """
    )
