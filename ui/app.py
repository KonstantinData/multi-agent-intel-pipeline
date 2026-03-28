"""Liquisto Briefing UI — pre-meeting preparation dashboard."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from src.app.use_cases import build_standard_backlog
from src.config import summarize_runtime_models
from src.exporters.pdf_report import generate_pdf
from src.orchestration.follow_up import answer_follow_up, load_run_artifact
from src.pipeline_runner import AGENT_META, PIPELINE_STEPS, run_pipeline
from ui.i18n import (
    confidence_badge,
    get_labels,
    goods_label,
    service_desc,
    service_icon,
    service_label,
)
from ui.theme import BRAND_CSS


RUNS_DIR = PROJECT_ROOT / "artifacts" / "runs"
BACKLOG = build_standard_backlog()
LOGO_PATH = PROJECT_ROOT / "assets" / "image" / "liquisto_logo.png"

st.set_page_config(page_title="Liquisto Briefing", page_icon="📋", layout="wide")
st.markdown(BRAND_CSS, unsafe_allow_html=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _nv(val: object, fallback: str = "") -> str:
    """Return empty string (or fallback) when val is n/v, None, or empty."""
    s = str(val or "").strip()
    return fallback if s in ("", "n/v", "N/V") else s


def _init_state() -> None:
    defaults = {
        "running": False,
        "done": False,
        "pipeline_started": False,
        "messages": [],
        "pipeline_data": {},
        "run_context": {},
        "usage": {},
        "budget": {},
        "status": None,
        "error": None,
        "run_id": None,
        "input_company": "",
        "input_domain": "",
        "worker_queue": None,
        "follow_up_answer": None,
        "loaded_notice": None,
        "lang": "de",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _drain_queue() -> None:
    worker_queue = st.session_state.worker_queue
    if worker_queue is None:
        return
    while True:
        try:
            item = worker_queue.get_nowait()
        except Empty:
            break
        event = item.get("event")
        if event == "message":
            st.session_state.messages.append(item["payload"])
        elif event == "result":
            payload = item["payload"]
            st.session_state.pipeline_data = payload["pipeline_data"]
            st.session_state.run_context = payload["run_context"]
            st.session_state.usage = payload.get("usage", {})
            st.session_state.budget = payload.get("budget", {})
            st.session_state.status = payload.get("status")
            st.session_state.run_id = payload.get("run_id")
            st.session_state.error = payload.get("error")
            st.session_state.done = True
            st.session_state.running = False
            st.session_state.pipeline_started = False
            st.session_state.worker_queue = None
        elif event == "error":
            st.session_state.error = item["payload"]
            st.session_state.done = True
            st.session_state.running = False
            st.session_state.pipeline_started = False
            st.session_state.worker_queue = None


def _run_dirs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted([p for p in RUNS_DIR.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)


def _load_run(run_id: str) -> None:
    artifact = load_run_artifact(run_id)
    history_path = artifact["run_dir"] / "chat_history.json"
    messages = []
    if history_path.exists():
        raw = json.loads(history_path.read_text(encoding="utf-8"))
        messages = [
            {"agent": item.get("name", "Agent"), "content": item.get("content", ""), "type": "agent_message"}
            for item in raw
        ]
    st.session_state.running = False
    st.session_state.done = True
    st.session_state.pipeline_started = False
    st.session_state.messages = messages
    st.session_state.pipeline_data = artifact["pipeline_data"]
    st.session_state.run_context = artifact["run_context"]
    st.session_state.run_id = run_id
    st.session_state.status = artifact["run_context"].get("status")
    st.session_state.error = None
    st.session_state.worker_queue = None
    st.session_state.loaded_notice = run_id


def _message_preview(content: str, limit: int = 140) -> str:
    text = str(content or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text or "(empty)"
    return text[:limit].rstrip() + "..."


def _step_progress() -> tuple[int, str]:
    if not st.session_state.messages:
        return 0, "Waiting to start"
    current_step, current_label = 1, "Supervisor intake and routing"
    for m in st.session_state.messages:
        agent = m.get("agent", "")
        if agent.startswith("Company"):
            current_step, current_label = 2, "Company Department active"
        elif agent.startswith("Market"):
            current_step, current_label = 3, "Market Department active"
        elif agent.startswith("Buyer"):
            current_step, current_label = 4, "Buyer Department active"
        elif agent.startswith("Contact"):
            current_step, current_label = 5, "Contact Intelligence active"
        elif agent.startswith("Synthesis") or agent == "SynthesisDepartment":
            current_step, current_label = 6, "Strategic Synthesis active"
        elif agent == "ReportWriter":
            current_step, current_label = 7, "Report packaging active"
    if st.session_state.done:
        return 7, "Run completed"
    return current_step, current_label


def _task_rows() -> list[dict]:
    statuses = st.session_state.run_context.get("short_term_memory", {}).get("task_statuses", {})
    return [
        {"label": item["label"], "assignee": item["assignee"], "status": statuses.get(item["task_key"], "pending")}
        for item in BACKLOG
    ]


def _department_packages() -> dict[str, dict]:
    return st.session_state.run_context.get("short_term_memory", {}).get("department_packages", {})


def _render_message_feed(L: dict) -> None:
    st.subheader(L["live_feed"])
    for m in reversed(st.session_state.messages[-40:]):
        agent = m.get("agent", "Agent")
        content = m.get("content", "")
        meta = AGENT_META.get(agent, {"summary": "", "icon": "[]"})
        title = f"{meta.get('icon', '[]')} {agent} — {_message_preview(content)}"
        with st.expander(title, expanded=False):
            st.code(content[:12000], language="json")


def _ranked_service_paths(synthesis: dict) -> list[dict]:
    service_relevance = synthesis.get("liquisto_service_relevance", [])
    recommended = synthesis.get("recommended_engagement_paths", [])
    positive = [item for item in service_relevance if item.get("relevance") != "unclear"]
    unclear = [item for item in service_relevance if item.get("relevance") == "unclear"]
    if recommended and recommended[0] != "further_validation_required":
        positive = sorted(
            positive,
            key=lambda x: recommended.index(x["service_area"]) if x["service_area"] in recommended else 99,
        )
    return positive + unclear


def _render_pdf_downloads(L: dict) -> None:
    if not (st.session_state.run_id and st.session_state.pipeline_data):
        return
    col_de, col_en = st.columns(2)
    with col_de:
        pdf_de = generate_pdf(st.session_state.pipeline_data, lang="de")
        st.download_button(
            L["download_pdf_de"],
            data=pdf_de,
            file_name=f"liquisto_briefing_{st.session_state.run_id}_DE.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with col_en:
        pdf_en = generate_pdf(st.session_state.pipeline_data, lang="en")
        st.download_button(
            L["download_pdf_en"],
            data=pdf_en,
            file_name=f"liquisto_briefing_{st.session_state.run_id}_EN.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def _render_briefing_tab(L: dict) -> None:
    pipeline_data = st.session_state.pipeline_data
    synthesis = pipeline_data.get("synthesis", {})
    company = pipeline_data.get("company_profile", {})
    industry = pipeline_data.get("industry_analysis", {})
    market = pipeline_data.get("market_network", {})
    contacts_section = pipeline_data.get("contact_intelligence", {})
    quality = pipeline_data.get("quality_review", {})

    company_name = _nv(company.get("company_name"), st.session_state.run_id or "")
    industry_name = _nv(company.get("industry") or industry.get("industry_name", ""))
    goods_lbl = goods_label(company.get("goods_classification", ""), L)
    confidence = synthesis.get("confidence") or quality.get("evidence_health", "low")
    description = _nv(company.get("description", ""))

    # ── Company snapshot ──────────────────────────────────────────────────────
    st.markdown(f"## {company_name}")
    tag_parts = [p for p in [industry_name, goods_lbl] if p]
    caption_parts = [" · ".join(tag_parts), confidence_badge(confidence, L)]
    caption_line = "   ".join(p for p in caption_parts if p)
    if caption_line:
        st.caption(caption_line)
    if description:
        st.write(description[:400] + ("..." if len(description) > 400 else ""))

    econ = company.get("economic_situation", {})
    econ_assessment = _nv(econ.get("assessment", "") if isinstance(econ, dict) else "")
    if econ_assessment:
        st.info(f"**{L['economic_signal']}:** {econ_assessment}")

    st.divider()

    # ── Liquisto recommendation ───────────────────────────────────────────────
    st.markdown(f"### {L['recommendation']}")
    ranked = _ranked_service_paths(synthesis)

    if not ranked:
        st.warning(L["no_recommendation"])
    else:
        primary = ranked[0]
        parea = primary.get("service_area", "")
        plabel = service_label(parea, L)
        picon = service_icon(parea)
        preasoning = _nv(primary.get("reasoning") or synthesis.get("opportunity_assessment_summary", ""))

        with st.container(border=True):
            st.markdown(f"#### {picon} {plabel}")
            st.caption(L["primary_rec"])
            if preasoning:
                st.write(preasoning)
            pdesc = service_desc(parea, L)
            if pdesc:
                st.caption(pdesc)

        if len(ranked) > 1:
            secondary = ranked[1]
            sarea = secondary.get("service_area", "")
            slabel = service_label(sarea, L)
            sicon = service_icon(sarea)
            sreasoning = _nv(secondary.get("reasoning", ""))

            has_third = len(ranked) > 2
            if has_third:
                col_sec, col_low = st.columns([2, 1])
            else:
                col_sec = st.columns(1)[0]
                col_low = None

            with col_sec:
                with st.container(border=True):
                    st.markdown(f"**{sicon} {slabel}**")
                    st.caption(L["secondary_rec"])
                    if sreasoning:
                        st.caption(sreasoning[:200])

            if has_third and col_low is not None:
                third = ranked[2]
                tarea = third.get("service_area", "")
                tlabel = service_label(tarea, L)
                with col_low:
                    with st.container(border=True):
                        st.markdown(f"**{tlabel}**")
                        st.caption(L["low_relevance"])
                        reasoning_text = _nv(third.get("reasoning", ""))
                        if reasoning_text:
                            st.caption(reasoning_text[:140])

    gen_mode = synthesis.get("generation_mode", "normal")
    if gen_mode == "fallback":
        st.caption(f"_{L['fallback_note']}_")

    st.divider()

    # ── Meeting preparation ───────────────────────────────────────────────────
    col_talk, col_validate = st.columns(2)

    with col_talk:
        st.markdown(f"### {L['talk_about']}")
        next_steps = synthesis.get("next_steps", [])
        buyer_summary = _nv(market.get("downstream_buyers", {}).get("assessment", ""))
        peer_count = len(market.get("peer_competitors", {}).get("companies", []))

        points: list[str] = []
        for step in next_steps[:4]:
            s = _nv(step)
            if s:
                points.append(s)
        if buyer_summary and len(points) < 4:
            points.append(f"{L['buyer_market']}: {buyer_summary[:200]}")
        if peer_count > 0 and len(points) < 4:
            points.append(f"{peer_count} {L['competitors_identified']}")

        if points:
            for point in points[:4]:
                st.write(f"- {point}")
        else:
            st.caption(L["no_talk_points"])

    with col_validate:
        st.markdown(f"### {L['validate']}")
        key_risks = synthesis.get("key_risks", [])
        open_gaps = quality.get("open_gaps", [])
        hypotheses: list[str] = []
        for risk in key_risks[:3]:
            r = _nv(risk)
            if r:
                hypotheses.append(r)
        for gap in open_gaps[:2]:
            g = _nv(gap)
            if g and g not in hypotheses:
                hypotheses.append(g)

        if hypotheses:
            for h in hypotheses[:4]:
                st.write(f"- {h}")
        else:
            st.caption(L["no_validation_points"])

    st.divider()

    # ── Contacts ──────────────────────────────────────────────────────────────
    st.markdown(f"### {L['contacts']}")
    prioritized = contacts_section.get("prioritized_contacts") or contacts_section.get("contacts", [])
    if prioritized:
        contact_cols = st.columns(min(len(prioritized[:3]), 3))
        for i, contact in enumerate(prioritized[:3]):
            with contact_cols[i]:
                with st.container(border=True):
                    name = _nv(contact.get("name"), "—")
                    role = _nv(contact.get("rolle_titel") or contact.get("funktion", ""))
                    firm = _nv(contact.get("firma", ""))
                    seniority = _nv(contact.get("senioritaet", ""))
                    outreach = _nv(contact.get("suggested_outreach_angle", ""))
                    st.markdown(f"**{name}**")
                    meta_parts = [p for p in [role, firm] if p]
                    if meta_parts:
                        st.caption(" · ".join(meta_parts))
                    if seniority:
                        st.caption(f"{L['seniority']}: {seniority}")
                    if outreach:
                        st.info(f"{L['outreach']}: {outreach}")
        if len(prioritized) > 3:
            st.caption(f"_+{len(prioritized) - 3} {L['more_contacts']}_")
    else:
        st.caption(L["no_contacts"])

    st.divider()

    # ── Next action ───────────────────────────────────────────────────────────
    st.markdown(f"### {L['next_step']}")
    next_steps_all = synthesis.get("next_steps", [])
    if next_steps_all:
        st.success(_nv(next_steps_all[0], L["default_next_step"]))
    else:
        readiness_reasons = pipeline_data.get("research_readiness", {}).get("reasons", [])
        if readiness_reasons:
            st.info(_nv(readiness_reasons[0], L["default_next_step"]))
        else:
            st.info(L["default_next_step"])

    st.divider()

    # ── PDF downloads ─────────────────────────────────────────────────────────
    _render_pdf_downloads(L)


def _render_research_tab(L: dict) -> None:
    pipeline_data = st.session_state.pipeline_data
    company = pipeline_data.get("company_profile", {})
    industry = pipeline_data.get("industry_analysis", {})
    market = pipeline_data.get("market_network", {})
    contacts_section = pipeline_data.get("contact_intelligence", {})

    with st.expander(L["company_profile"], expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**{L['name']}:** {_nv(company.get('company_name'), '—')}")
            website = _nv(company.get("website", ""))
            st.write(f"**{L['website']}:** {website or '—'}")
            st.write(f"**{L['industry']}:** {_nv(company.get('industry'), '—')}")
            goods_lbl = goods_label(company.get("goods_classification", ""), L)
            if goods_lbl:
                st.write(f"**{L['goods_type']}:** {goods_lbl}")
        with col2:
            products = company.get("products_and_services", [])
            if products:
                st.write(f"**{L['products']}:**")
                for p in products[:6]:
                    pv = _nv(p)
                    if pv:
                        st.write(f"- {pv}")
        desc = _nv(company.get("description", ""))
        if desc:
            st.write(desc)
        econ = company.get("economic_situation", {})
        if isinstance(econ, dict) and (_nv(econ.get("assessment")) or econ.get("recent_events")):
            st.markdown(f"**{L['economic_signals']}:**")
            assessment = _nv(econ.get("assessment", ""))
            if assessment:
                st.write(assessment)
            for evt in econ.get("recent_events", [])[:5]:
                ev = _nv(evt)
                if ev:
                    st.write(f"- {ev}")
            for sig in econ.get("inventory_signals", [])[:4]:
                sv = _nv(sig)
                if sv:
                    st.write(f"- {sv}")
        scope = company.get("product_asset_scope", [])
        if scope:
            st.markdown(f"**{L['asset_scope']}:**")
            for item in scope[:8]:
                iv = _nv(item)
                if iv:
                    st.write(f"- {iv}")

    with st.expander(L["market_industry"]):
        st.write(f"**{L['industry']}:** {_nv(industry.get('industry_name'), '—')}")
        assessment = _nv(industry.get("assessment", ""))
        if assessment:
            st.write(assessment)
        demand = _nv(industry.get("demand_outlook", ""))
        if demand:
            st.write(f"**{L['demand_outlook']}:** {demand}")
        for trend in industry.get("key_trends", [])[:5]:
            tv = _nv(trend)
            if tv:
                st.write(f"- {tv}")
        repurposing = industry.get("repurposing_signals", [])
        if repurposing:
            st.markdown(f"**{L['repurposing_signals']}:**")
            for item in repurposing[:5]:
                iv = _nv(item)
                if iv:
                    st.write(f"- {iv}")
        analytics = industry.get("analytics_signals", [])
        if analytics:
            st.markdown(f"**{L['analytics_signals']}:**")
            for item in analytics[:5]:
                iv = _nv(item)
                if iv:
                    st.write(f"- {iv}")

    with st.expander(L["buyer_network"]):
        peers = market.get("peer_competitors", {})
        if peers:
            peer_assessment = _nv(peers.get("assessment", ""))
            if peer_assessment:
                st.markdown(f"**{L['competitors']}** — {peer_assessment[:300]}")
            for company_item in peers.get("companies", [])[:10]:
                if isinstance(company_item, dict):
                    name = _nv(company_item.get("name", ""))
                    country = _nv(company_item.get("country", ""))
                    relevance = _nv(company_item.get("relevance", ""))
                    parts = [name]
                    if country:
                        parts.append(f"({country})")
                    if relevance:
                        parts.append(f"— {relevance}")
                    line = " ".join(p for p in parts if p)
                    if line.strip():
                        st.write(f"- {line}")
                elif company_item:
                    cv = _nv(str(company_item))
                    if cv:
                        st.write(f"- {cv}")
        buyers = market.get("downstream_buyers", {})
        if buyers:
            buyer_assessment = _nv(buyers.get("assessment", ""))
            if buyer_assessment:
                st.markdown(f"**{L['downstream_buyers']}** — {buyer_assessment[:300]}")
            for buyer in buyers.get("companies", [])[:10]:
                if isinstance(buyer, dict):
                    name = _nv(buyer.get("name", ""))
                    country = _nv(buyer.get("country", ""))
                    line = name + (f" ({country})" if country else "")
                    if line.strip():
                        st.write(f"- {line}")
                elif buyer:
                    bv = _nv(str(buyer))
                    if bv:
                        st.write(f"- {bv}")
        monetization = market.get("monetization_paths", [])
        if monetization:
            st.markdown(f"**{L['monetization_paths']}:**")
            for path in monetization[:5]:
                pv = _nv(path)
                if pv:
                    st.write(f"- {pv}")
        redeployment = market.get("redeployment_paths", [])
        if redeployment:
            st.markdown(f"**{L['redeployment_paths']}:**")
            for path in redeployment[:5]:
                pv = _nv(path)
                if pv:
                    st.write(f"- {pv}")

    with st.expander(L["contact_intelligence"]):
        narrative = _nv(contacts_section.get("narrative_summary", ""))
        if narrative:
            st.write(narrative)
        coverage = _nv(contacts_section.get("coverage_quality", ""), "—")
        st.caption(f"{L['coverage_quality']}: {coverage}")
        all_contacts = contacts_section.get("prioritized_contacts") or contacts_section.get("contacts", [])
        if all_contacts:
            for c in all_contacts:
                name = _nv(c.get("name"), "—")
                role = _nv(c.get("rolle_titel") or c.get("funktion", ""), "—")
                firm = _nv(c.get("firma", ""), "—")
                with st.expander(f"{name} — {role} @ {firm}"):
                    funktion = _nv(c.get("funktion", ""))
                    senioritaet = _nv(c.get("senioritaet", ""))
                    conf = _nv(c.get("confidence", ""))
                    relevance_r = _nv(c.get("relevance_reason", ""))
                    outreach = _nv(c.get("suggested_outreach_angle", ""))
                    if funktion:
                        st.write(f"**{L['function']}:** {funktion}")
                    if senioritaet:
                        st.write(f"**{L['seniority']}:** {senioritaet}")
                    if conf:
                        st.write(f"**{L['confidence']}:** {conf}")
                    if relevance_r:
                        st.write(f"**{L['relevance']}:** {relevance_r}")
                    if outreach:
                        st.info(f"**{L['outreach_angle']}:** {outreach}")
        else:
            st.caption(L["no_contacts_found"])


def _render_follow_up_panel(L: dict) -> None:
    current_run_id = st.session_state.run_id or ""
    st.markdown(L["followup_intro"])
    with st.form("follow_up_form", clear_on_submit=False):
        run_id = st.text_input(L["run_id"], value=current_run_id, help="z.B. 20250322T143012Z")
        question = st.text_area(L["followup_question"], placeholder=L["followup_placeholder"])
        submitted = st.form_submit_button(L["submit_question"], use_container_width=True)

    if submitted:
        if not run_id.strip() or not question.strip():
            st.warning(L["followup_required"])
        else:
            with st.spinner(L["followup_routing"]):
                try:
                    artifact = load_run_artifact(run_id.strip())
                    from src.agents.supervisor import SupervisorAgent
                    supervisor = SupervisorAgent()
                    route = supervisor.route_question(question=question.strip(), source="user_ui")
                    answer = answer_follow_up(
                        run_id=run_id.strip(),
                        route=route["route"],
                        question=question.strip(),
                        pipeline_data=artifact["pipeline_data"],
                        run_context=artifact["run_context"],
                    )
                    st.session_state.follow_up_answer = {**answer, "route_reason": route["reason"]}
                except FileNotFoundError:
                    st.error(f"{L['followup_not_found']}: '{run_id.strip()}'")
                except Exception as exc:
                    st.error(f"{L['followup_error']}: {exc}")

    answer = st.session_state.follow_up_answer
    if answer:
        dept_icons = {
            "CompanyDepartment": "🏢",
            "MarketDepartment": "📡",
            "BuyerDepartment": "🌐",
            "ContactDepartment": "👤",
            "SynthesisDepartment": "🧠",
        }
        routed_to = _nv(answer.get("routed_to", ""), "—")
        icon = dept_icons.get(routed_to, "🔍")
        with st.container(border=True):
            st.markdown(f"**{icon} {L['answered_by']}: {routed_to}**")
            route_reason = _nv(answer.get("route_reason", ""))
            if route_reason:
                st.caption(route_reason)
            st.write(_nv(answer.get("answer", ""), "—"))
            col_a, col_b = st.columns(2)
            with col_a:
                if answer.get("evidence_used"):
                    st.write(f"**{L['evidence_used']}**")
                    for item in answer["evidence_used"]:
                        iv = _nv(str(item or ""))
                        if iv:
                            st.write(f"- {iv[:200]}")
            with col_b:
                if answer.get("unresolved_points"):
                    st.write(f"**{L['unresolved_points']}**")
                    for item in answer["unresolved_points"]:
                        uv = _nv(str(item or ""))
                        if uv:
                            st.write(f"- {uv}")


def _render_quality_tab(L: dict) -> None:
    pipeline_data = st.session_state.pipeline_data
    quality = pipeline_data.get("quality_review", {})
    readiness = pipeline_data.get("research_readiness", {})

    with st.expander(L["research_quality"]):
        col1, col2, col3 = st.columns(3)
        col1.metric(L["readiness_score"], _nv(str(readiness.get("score", "")), "—"))
        col2.metric(L["evidence_quality"], _nv(quality.get("evidence_health", ""), "—"))
        col3.metric(L["status"], _nv(st.session_state.status or "", "—"))
        if readiness.get("reasons"):
            for r in readiness["reasons"]:
                rv = _nv(r)
                if rv:
                    st.write(f"- {rv}")
        if quality.get("open_gaps"):
            st.markdown(f"**{L['open_gaps']}:**")
            for g in quality["open_gaps"][:10]:
                gv = _nv(g)
                if gv:
                    st.write(f"- {gv}")

    with st.expander(L["task_status"]):
        status_icons = {"accepted": "✅", "degraded": "🟡", "rejected": "❌", "skipped": "⏭️", "pending": "⏳"}
        for row in _task_rows():
            icon = status_icons.get(row["status"], "·")
            st.write(f"{icon} {row['label']} — `{row['assignee']}` — `{row['status']}`")

    packages = _department_packages()
    if packages:
        with st.expander(L["department_packages"]):
            for dept_name, package in packages.items():
                st.markdown(f"**{dept_name}**")
                st.json(package)

    with st.expander(L["run_metadata"]):
        budget = st.session_state.budget
        st.json({
            "run_id": st.session_state.run_id,
            "llm_calls": budget.get("llm_calls_used"),
            "search_calls": budget.get("search_calls_used"),
            "page_fetches": budget.get("page_fetches_used"),
            "estimated_cost_usd": budget.get("estimated_cost_usd"),
            "elapsed_seconds": budget.get("elapsed_seconds"),
            "department_timings": budget.get("department_timings", {}),
        })


def _start_pipeline(company_name: str, web_domain: str) -> None:
    st.session_state.running = True
    st.session_state.done = False
    st.session_state.pipeline_started = False
    st.session_state.messages = []
    st.session_state.pipeline_data = {}
    st.session_state.run_context = {}
    st.session_state.usage = {}
    st.session_state.budget = {}
    st.session_state.status = None
    st.session_state.error = None
    st.session_state.run_id = None
    st.session_state.input_company = company_name
    st.session_state.input_domain = web_domain
    st.session_state.worker_queue = Queue()


# ─────────────────────────────────────────────────────────────────────────────
_init_state()
_drain_queue()

L = get_labels(st.session_state.lang)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)

    if st.button(L["lang_toggle"], use_container_width=True):
        st.session_state.lang = "en" if st.session_state.lang == "de" else "de"
        st.rerun()

    st.divider()

    st.markdown(f"**{L['new_run']}**")
    company_name = st.text_input(L["company_name"], value=st.session_state.get("input_company", ""))
    web_domain = st.text_input(L["web_domain"], value=st.session_state.get("input_domain", ""))
    if st.button(
        L["start_run"],
        disabled=st.session_state.running or not company_name or not web_domain,
        use_container_width=True,
    ):
        _start_pipeline(company_name, web_domain)
        st.rerun()

    st.divider()

    st.markdown(f"**{L['load_run']}**")
    run_dirs = _run_dirs()
    run_options = [p.name for p in run_dirs[:30]]
    selected_run = st.selectbox(L["select_run"], options=[""] + run_options, index=0)
    if st.button(
        L["load_selected"],
        disabled=st.session_state.running or not selected_run,
        use_container_width=True,
    ):
        _load_run(selected_run)
        st.rerun()

    st.divider()
    st.caption(f"{L['runtime_models']}: {summarize_runtime_models()}")


# ── Page header ───────────────────────────────────────────────────────────────
st.header(L["page_heading"])
st.caption(L["page_subtitle"])

# ── Live run view ─────────────────────────────────────────────────────────────
if st.session_state.running and not st.session_state.done:
    current_step, current_label = _step_progress()
    st.progress(current_step / len(PIPELINE_STEPS))
    st.write(current_label)

    cols = st.columns(len(PIPELINE_STEPS))
    for index, (agent_name, label) in enumerate(PIPELINE_STEPS):
        meta = AGENT_META.get(agent_name, {"icon": "[]", "color": "#d0d5dd"})
        active = index + 1 <= current_step
        background = meta["color"] if active else "#f2f4f7"
        text_color = "#ffffff" if active else "#101828"
        cols[index].markdown(
            f"""<div style="border:1px solid #d0d5dd;border-radius:14px;padding:12px;background:{background};min-height:110px;">
              <div style="font-size:26px;color:{text_color};">{meta['icon']}</div>
              <div style="font-weight:700;color:{text_color};margin-top:8px;">{label}</div>
              <div style="font-size:12px;color:{text_color};opacity:0.92;">{agent_name}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    worker_queue = st.session_state.worker_queue
    _company_name = st.session_state.get("input_company", "")
    _web_domain = st.session_state.get("input_domain", "")

    def _on_message(event: dict) -> None:
        worker_queue.put({"event": "message", "payload": event})

    def _run() -> None:
        try:
            result = run_pipeline(company_name=_company_name, web_domain=_web_domain, on_message=_on_message)
            worker_queue.put({"event": "result", "payload": result})
        except Exception as exc:
            worker_queue.put({"event": "error", "payload": str(exc)})

    if not st.session_state.pipeline_started:
        st.session_state.pipeline_started = True
        threading.Thread(target=_run, daemon=True).start()

    _render_message_feed(L)
    time.sleep(0.8)
    st.rerun()

# ── Error ─────────────────────────────────────────────────────────────────────
if st.session_state.error:
    st.error(st.session_state.error)

# ── Post-run display ──────────────────────────────────────────────────────────
if st.session_state.done and st.session_state.run_id:
    status = st.session_state.status
    company_label = _nv(
        st.session_state.pipeline_data.get("company_profile", {}).get("company_name", ""),
        st.session_state.run_id,
    )
    if status == "completed":
        st.success(f"{L['briefing_ready']} — {company_label}")
    elif status == "completed_partial":
        st.warning(f"{L['briefing_partial']} — {company_label}")
    elif status == "completed_but_not_usable":
        st.error(f"{L['briefing_unusable']} ({company_label})")
    elif st.session_state.loaded_notice == st.session_state.run_id:
        st.info(f"{L['run_loaded']} — {company_label}")

    tab_briefing, tab_research, tab_followup, tab_quality, tab_log = st.tabs([
        L["tab_briefing"],
        L["tab_research"],
        L["tab_followup"],
        L["tab_quality"],
        L["tab_log"],
    ])

    with tab_briefing:
        _render_briefing_tab(L)

    with tab_research:
        _render_research_tab(L)

    with tab_followup:
        _render_follow_up_panel(L)

    with tab_quality:
        _render_quality_tab(L)

    with tab_log:
        _render_message_feed(L)
