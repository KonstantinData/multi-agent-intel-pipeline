"""Generate runtime_architecture.drawio from scratch with clean non-overlapping layout."""
import xml.etree.ElementTree as ET  # nosec B405
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "drawio" / "runtime_architecture.drawio"


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def rect(id_, label, x, y, w, h, fill, stroke, fc="#0f172a", fs=12, sw=1, r=1, extra=""):
    style = (
        f"rounded={r};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={sw};fontSize={fs};spacing=6;fontColor={fc};{extra}"
    )
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def txt(id_, label, x, y, w, h, fc="#0f172a", fs=13, bold=True):
    fw = "1" if bold else "0"
    style = (
        f"text;html=1;strokeColor=none;fillColor=none;align=left;"
        f"verticalAlign=middle;fontSize={fs};fontStyle={fw};fontColor={fc};"
    )
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def lane_bg(id_, x, y, w, h, fill, stroke):
    style = f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1;"
    return (
        f'<mxCell id="{id_}" value="" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def hdr(id_, label, x, y, w, h, fill, stroke, fc):
    style = (
        f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth=1;fontSize=13;fontStyle=1;fontColor={fc};align=left;spacingLeft=10;"
    )
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def edge(id_, label, src, tgt, color="#2563eb", fw=1, dashed=False, pts=None, fs=10, fc=None):
    if fc is None:
        fc = color
    dash = "dashed=1;" if dashed else ""
    s = (
        f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeWidth={fw};"
        f"strokeColor={color};fontColor={fc};fontSize={fs};endArrow=block;{dash}"
    )
    if pts:
        arr = "".join(f'<mxPoint x="{p[0]}" y="{p[1]}"/>' for p in pts)
        geom = f'<mxGeometry relative="1" as="geometry"><Array as="points">{arr}</Array></mxGeometry>'
    else:
        geom = '<mxGeometry relative="1" as="geometry"/>'
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{s}" '
        f'parent="1" source="{src}" target="{tgt}" edge="1">{geom}</mxCell>'
    )


# ── Layout constants ──────────────────────────────────────────────────────────
Y0 = 80       # top of lane area
HDR_H = 36    # header band height
C0 = Y0 + HDR_H + 14  # content start y

# 6 swim lanes
EX, EW = 20, 280        # Entry
CX, CW = 320, 460       # Control / Pipeline Orchestration
DX, DW = 800, 1960      # Departments
RX, RW = 2780, 460      # Resolution
SX, SW = 3260, 460      # Synthesis + Finalization
OX, OW = 3740, 460      # Output

PAGE_W = OX + OW + 40
LH = 3520               # lane height
PAGE_H = Y0 + LH + 200

# Dept sub-widths (Company + Market side-by-side)
PAIR_W = (DW - 20) // 2  # ~970
CO_X = DX + 5
MA_X = DX + 10 + PAIR_W

# Y-zones
Z_PH1 = C0
Z_PH1_H = 420
Z_PH2 = Z_PH1 + Z_PH1_H + 30
Z_PH2_H = 380
Z_PH3 = Z_PH2 + Z_PH2_H + 30
Z_PH3_H = 380
BYPASS_Y = Z_PH3 + Z_PH3_H + 30   # safe routing y below all depts

# Control lane y-positions
RC_Y = C0 + 620   # Resolution Controller base in Control lane

# Synthesis y-positions
Z_SYNTH = BYPASS_Y + 60
Z_REPORT = Z_SYNTH + 620

# Follow-up section
Z_FU = Z_REPORT + 200

# Security layer
Z_SEC = Y0 + LH + 40

cells = []

# ── Lane backgrounds ──────────────────────────────────────────────────────────
LANES = [
    ("bg_entry",  "hdr_entry",  "Entry + Follow-up",                    EX, EW, "#f0f9ff","#7dd3fc","#dbeafe","#0284c7","#0c4a6e"),
    ("bg_ctrl",   "hdr_ctrl",   "Pipeline Orchestration + Control Flow", CX, CW, "#eff6ff","#93c5fd","#dbeafe","#2563eb","#1e3a8a"),
    ("bg_dept",   "hdr_dept",   "Domain Departments — AG2 GroupChats",   DX, DW, "#f7fef9","#86efac","#dcfce7","#16a34a","#14532d"),
    ("bg_res",    "hdr_res",    "Resolution + Routing",                  RX, RW, "#eef2ff","#a5b4fc","#e0e7ff","#4338ca","#312e81"),
    ("bg_synth",  "hdr_synth",  "Synthesis + Finalization",              SX, SW, "#faf5ff","#c4b5fd","#ede9fe","#7c3aed","#4c1d95"),
    ("bg_out",    "hdr_out",    "Output + Delivery",                     OX, OW, "#fffbeb","#fcd34d","#fef3c7","#d97706","#78350f"),
]
for bg_id, hdr_id, label, lx, lw, bg_f, bg_s, hf, hs, hfc in LANES:
    cells.append(lane_bg(bg_id, lx, Y0, lw, LH, bg_f, bg_s))
    cells.append(hdr(hdr_id, label, lx, Y0, lw, HDR_H, hf, hs, hfc))

# ── Title ────────────────────────────────────────────────────────────────────
cells.append(txt("title", "Liquisto Runtime Architecture", EX + 5, 18, 900, 34, "#0f172a", 26))
cells.append(txt("subtitle",
    "Supervisor-managed · 4 AG2 GroupChat Departments · KB-layered · Resolution Controller · "
    "Two-Layer Admission · Synthesis + Finalization · Follow-up Mode",
    EX + 5, 52, PAGE_W - 100, 22, "#475569", 11, False))

# ── ENTRY LANE ───────────────────────────────────────────────────────────────
cells.append(rect("user",
    "<b>Nutzer / Operator</b>\ngibt company_name + web_domain ein",
    EX+10, C0, 240, 70, "#e0f2fe","#0284c7","#0c4a6e", 12))
cells.append(rect("ui",
    "<b>Streamlit UI</b>\nstartet Run · streamt Agent-Events\nDE/EN PDF-Download",
    EX+10, C0+90, 240, 80, "#e0f2fe","#0284c7","#0c4a6e", 12))

# ── CONTROL LANE ─────────────────────────────────────────────────────────────
cy = C0
CTRL = dict(x=CX+10, w=CW-20, fill="#dbeafe", stroke="#2563eb", fc="#1e3a8a", fs=11)

cells.append(rect("runner",
    "<b>pipeline_runner.run_pipeline()</b>\n"
    "run_id · run_dir · InitialRunState\n"
    "_initialize_run → _build_supervisor_brief\n"
    "→ _run_first_pass → _run_auto_close_if_required\n"
    "→ _run_synthesis_phase → _finalize_readiness\n"
    "→ _assemble_report_and_export",
    CTRL["x"], cy, CTRL["w"], 130, CTRL["fill"], CTRL["stroke"], CTRL["fc"], CTRL["fs"]))
cy += 150

cells.append(rect("supervisor",
    "<b>Supervisor</b>\n"
    "build_intake_brief() · NormalizedDomainResult\n"
    "WebsiteSnapshot · CompanyResearchResult · SupervisorBriefMessage\n"
    "Industry Hint + Confidence · verified_company_name · Evidence Summary\n"
    "accept_department_package() — LLM-based Admission Gate\n"
    "accept_synthesis() — LLM-based Synthesis Gate",
    CTRL["x"], cy, CTRL["w"], 130, CTRL["fill"], CTRL["stroke"], CTRL["fc"], CTRL["fs"]))
cy += 150

cells.append(rect("qreg",
    "<b>Question Registry + Answer Matrix</b>\n"
    "12 MEETING_QUESTION_REGISTRY Fragen\n"
    "stabile question_id pro Registry-Key\n"
    "TASK_TO_QUESTION_IDS Mapping\n"
    "initiale Answer Matrix: pending · answer='' · notes='' · source_tasks=[]",
    CTRL["x"], cy, CTRL["w"], 110, CTRL["fill"], CTRL["stroke"], CTRL["fc"], CTRL["fs"]))
cy += 130

cells.append(rect("step1_handoff",
    "<b>Step1Handoff Contract + Gate</b>\n"
    "schema_version · run_id · intake · supervisor_message\n"
    "question_registry + answer_matrix · retrieval snapshots\n"
    "runtime_agents_snapshot · storage_snapshot · budget_snapshot\n"
    "first RuntimeEvent: event_id · sequence · timestamp · phase\n"
    "CheckpointInfo: after_supervisor_brief · hash · written\n"
    "readiness: ready_for_department_routing / ready_with_gaps / blocked_step1_handoff",
    CTRL["x"], cy, CTRL["w"], 160, "#e0e7ff","#4338ca","#312e81", CTRL["fs"], 2))
cy += 180

cells.append(rect("stm",
    "<b>ShortTermMemoryStore (Run Brain)</b>\n"
    "evidence_packets · gap_candidates · answer_matrix_updates\n"
    "task_statuses · department_run_states · worker_reports\n"
    "create_working_set() · delta_from() · merge_from()\n"
    "Parallel-Isolation: Phase 1 bekommt isolierte Working-Sets",
    CTRL["x"], cy, CTRL["w"], 110, "#fee2e2","#dc2626","#7f1d1d", CTRL["fs"]))
cy += 130

cells.append(rect("ltm_load",
    "<b>Long-Term Process Brain (Laden)</b>\n"
    "FileLongTermMemoryStore · retrieve_strategies()\n"
    "Alle RETRIEVABLE_ROLES geladen vor Department-Start\n"
    "Nur Prozessmuster — keine Zielkunden-Fakten\n"
    "Aktuell: Flat JSON (GAP-03: Vector Store angestrebt)",
    CTRL["x"], cy, CTRL["w"], 110, "#fee2e2","#dc2626","#7f1d1d", CTRL["fs"]))
cy += 130

cells.append(rect("dept_kb",
    "<b>Department Knowledge Base</b>\n"
    "knowledge/sources/*.yaml — Source-Metadaten (nicht Runtime-Queries)\n"
    "knowledge/policies/*.yaml — Required Fields, Evidence-Minima, Gate-Regeln\n"
    "knowledge/query_strategies/*.yaml — Runtime Query-Templates (single authority)\n"
    "query_resolver.py — Placeholder-Expansion · Validierung · Buyer-Expansion\n"
    "Guidance only — Department-Konversation bleibt frei",
    CTRL["x"], cy, CTRL["w"], 120, "#fff7ed","#ea580c","#7c2d12", CTRL["fs"]))
cy += 140

cells.append(rect("budget",
    "<b>PhaseBudgetTracker + Checkpoints</b>\n"
    "first_pass / closure / optional_depth Token-Budgets\n"
    "HARD_TOKEN_CAP enforced nach sequenziellen Depts\n"
    "after_supervisor_brief: atomarer JSON-Checkpoint + checkpoint_hash\n"
    "Checkpoints: after_first_pass\n"
    "after_closure · after_synthesis · after_finalization",
    CTRL["x"], cy, CTRL["w"], 120, "#fff7ed","#ea580c","#7c2d12", CTRL["fs"]))
cy += 140

# ── Resolution nodes in Control lane (gap after budget) ──────────────────────
# Make sure RC_Y >= cy + 20
RC_Y = max(cy + 20, RC_Y)

cells.append(rect("handoff",
    "<b>Department Handoff</b>\n"
    "Supervisor schreibt Admission Envelope pro Dept:\n"
    "decision: accepted / accepted_with_gaps / rejected\n"
    "raw_package (immer) · admitted_payload (wenn nicht rejected)\n"
    "downstream_visible = decision != rejected",
    CTRL["x"], RC_Y, CTRL["w"], 100, CTRL["fill"], CTRL["stroke"], CTRL["fc"], CTRL["fs"]))

cells.append(rect("rc",
    "<b>⬡ Resolution Controller</b>  (eigene Komponente)\n"
    "ResolutionController.classify() nach erstem Department-Round\n"
    "Prioritätsreihenfolge → genau ein Bucket:\n"
    "BLOCKING_FAILURE          → blockiert sofort\n"
    "AUTO_CLOSE_REQUIRED       → run_bounded_follow_up()\n"
    "USER_DECISION_REQUIRED    → Dashboard Pause\n"
    "CUSTOMER_CONFIRMATION     → accept gap, weiter\n"
    "NOT_MEETING_CRITICAL      → direkt zur Synthesis",
    CTRL["x"], RC_Y + 120, CTRL["w"], 160,
    "#e0e7ff","#4338ca","#312e81", CTRL["fs"], 2))

cells.append(rect("auto_close",
    "<b>Auto-Close Bounded Follow-Up</b>\n"
    "run_bounded_follow_up() · max 4 öffentliche Gap-Fragen\n"
    "resolved_question_ids → Answer Matrix update\n"
    "mapping_missing Flag wenn keine question_ids vorhanden",
    CTRL["x"], RC_Y + 300, CTRL["w"], 90,
    "#e0e7ff","#4338ca","#312e81", CTRL["fs"]))

cells.append(rect("dashboard",
    "<b>Dashboard Pause / Resume</b>\n"
    "run_pipeline() → needs_user_selection\n"
    "Nutzer wählt optionale Tiefe im UI\n"
    "resume_pipeline() · MeetingReadinessGate re-evaluiert",
    CTRL["x"], RC_Y + 410, CTRL["w"], 90,
    "#e0e7ff","#4338ca","#312e81", CTRL["fs"]))

cells.append(rect("blocking",
    "<b>BLOCKING_FAILURE Terminal</b>\n"
    "Finalisierung blockiert · partielle Artifacts exportiert\n"
    "Synthesis läuft NICHT · Status: blocked_not_meeting_ready\n"
    "Tritt auf: Supervisor rejected ≥1 Package\n"
    "(unabhängig vom internen Judge-Ergebnis!)",
    CTRL["x"], RC_Y + 520, CTRL["w"], 100,
    "#fee2e2","#dc2626","#7f1d1d", CTRL["fs"], 2))

cells.append(rect("two_layer",
    "<b>Zwei-Schicht-Admission</b>  (unabhängige Gates)\n"
    "1. Intern: Lead / Judge pro Task — deterministisch, KB-policy\n"
    "2. Supervisor: pro Package — LLM-basiert, Cross-Task-Kohärenz\n"
    "Ein Judge-accepted Package kann Supervisor-rejected werden.\n"
    "Divergenz → BLOCKING_FAILURE.\n"
    "Gates müssen gemeinsam kalibriert werden.",
    CTRL["x"], RC_Y + 640, CTRL["w"], 110,
    "#fff7ed","#ea580c","#7c2d12", CTRL["fs"]))

cells.append(rect("sup_rule",
    "<b>Supervisor-Grenzen (CHG-03)</b>\n"
    "Kein Eingriff in interne Department-Retry/Review-Loops.\n"
    "Supervisor sieht nur finales DepartmentPackage\n"
    "nach finalize_package() · keine request_supervisor_revision Tool",
    CTRL["x"], RC_Y + 770, CTRL["w"], 90,
    "#fff7ed","#ea580c","#7c2d12", CTRL["fs"]))

# ── DEPARTMENTS LANE ──────────────────────────────────────────────────────────

# Phase 1 parallel group
cells.append(rect("ph1_box", "",
    DX+5, Z_PH1, DW-10, Z_PH1_H, "#f0fdf4","#16a34a","#14532d", 11, 1))
cells.append(txt("ph1_lbl",
    "▶  Phase 1: Parallel Execution (ThreadPoolExecutor) — "
    "Company + Market gleichzeitig · isolierte Working-Set STM-Stores · "
    "Delta-Merge nach Completion in kanonischer Reihenfolge",
    DX+14, Z_PH1+8, DW-28, 20, "#14532d", 11))

def dept_side(prefix, title, scope_lbl, lx, fill, stroke, fc):
    """Build side-by-side dept (narrow, ~PAIR_W wide)."""
    ly = Z_PH1 + 30
    lw = PAIR_W - 5
    lh = Z_PH1_H - 40
    out = []
    out.append(rect(f"{prefix}_box", "", lx, ly, lw, lh, fill, stroke, fc, 11, 2))
    out.append(txt(f"{prefix}_hdr", f"<b>{title}</b>  →  section: {scope_lbl}",
                   lx+8, ly+6, lw-16, 20, fc, 12))
    # Internal layout within narrow dept
    ry = ly + 32
    rw = 180
    gap = 8
    rx = lx + 8
    for r_id, r_name, r_tool in [
        (f"{prefix}_lead", "Lead / Analyst", "finalize_package()"),
        (f"{prefix}_res",  "Researcher",     "run_research()"),
        (f"{prefix}_crit", "Critic",         "review_research()"),
    ]:
        out.append(rect(r_id, f"<b>{r_name}</b>\n{r_tool}", rx, ry, rw, 82, fill, stroke, fc, 10))
        rx += rw + gap
    # Judge + CodingSpec stacked
    jx = lx + lw - 165
    out.append(rect(f"{prefix}_judge", "<b>Judge</b>\njudge_decision()",           jx, ry,     157, 38, fill, stroke, fc, 10))
    out.append(rect(f"{prefix}_code",  "<b>CodingSpec</b>\nsuggest_refined_queries()", jx, ry+44, 157, 38, fill, stroke, fc, 10))
    # STM / LTM / Output
    my = ry + 100
    hw = (lw - 26) // 2
    out.append(rect(f"{prefix}_stm", "<b>STM</b>\nFacts · Sources · Open Questions", lx+8, my, hw, 70, "#fee2e2","#dc2626","#7f1d1d", 10))
    out.append(rect(f"{prefix}_ltm", "<b>LTM</b>\nProcess Patterns",               lx+10+hw, my, hw, 70, "#fee2e2","#dc2626","#7f1d1d", 10))
    out.append(rect(f"{prefix}_out", f"<b>{scope_lbl}</b>",                         lx+lw-120, ly+200, 110, 60, "#dbeafe","#2563eb","#1e3a8a", 9))
    return out


def dept_wide(prefix, title, scope_lbl, ly, lh, fill, stroke, fc, dep_note=""):
    """Build full-width dept (sequential, DW-10 wide)."""
    lx = DX + 5
    lw = DW - 10
    out = []
    out.append(rect(f"{prefix}_box", "", lx, ly, lw, lh, fill, stroke, fc, 11, 2))
    out.append(txt(f"{prefix}_hdr", f"<b>{title}</b>  →  section: {scope_lbl}  {dep_note}",
                   lx+8, ly+6, lw-16, 20, fc, 12))
    ry = ly + 32
    rw = 260
    gap = 10
    rx = lx + 8
    for r_id, r_name, r_tool in [
        (f"{prefix}_lead", "Lead / Analyst", "finalize_package()"),
        (f"{prefix}_res",  "Researcher",     "run_research()"),
        (f"{prefix}_crit", "Critic",         "review_research()"),
    ]:
        out.append(rect(r_id, f"<b>{r_name}</b>\n{r_tool}", rx, ry, rw, 82, fill, stroke, fc, 11))
        rx += rw + gap
    jx = rx
    out.append(rect(f"{prefix}_judge", "<b>Judge</b>\njudge_decision()",               jx, ry,     200, 38, fill, stroke, fc, 10))
    out.append(rect(f"{prefix}_code",  "<b>CodingSpecialist</b>\nsuggest_refined_queries()", jx, ry+44, 200, 38, fill, stroke, fc, 10))
    my = ry + 100
    out.append(rect(f"{prefix}_stm", "<b>Working Memory (STM)</b>\nFacts · Sources · Open Questions · Interim Results",
                    lx+8, my, 500, 70, "#fee2e2","#dc2626","#7f1d1d", 10))
    out.append(rect(f"{prefix}_ltm", "<b>Strategy Memory (LTM)</b>\nReusable Process Patterns geladen vor Run",
                    lx+520, my, 500, 70, "#fee2e2","#dc2626","#7f1d1d", 10))
    out.append(rect(f"{prefix}_out", f"<b>{scope_lbl}</b>",
                    lx+lw-150, ly+200, 140, 70, "#dbeafe","#2563eb","#1e3a8a", 10))
    return out


cells += dept_side("co", "Company Department", "company_profile",
                   CO_X, "#f0fdf4","#16a34a","#14532d")
cells += dept_side("ma", "Market Department", "industry_analysis",
                   MA_X, "#fff7ed","#f97316","#9a3412")

# Phase 2: Buyer
cells.append(rect("ph2_box", "",
    DX+5, Z_PH2, DW-10, Z_PH2_H, "#ecfeff","#67e8f9","#155e75", 11, 1))
cells.append(txt("ph2_lbl",
    "▶  Phase 2: Sequenziell — Buyer startet nach Phase-1-Abschluss",
    DX+14, Z_PH2+8, DW-28, 20, "#155e75", 11))
cells += dept_wide("bu", "Buyer Department", "market_network",
                   Z_PH2+30, Z_PH2_H-40, "#ecfeff","#06b6d4","#155e75")

# Phase 3: Contact
cells.append(rect("ph3_box", "",
    DX+5, Z_PH3, DW-10, Z_PH3_H, "#fdf2f8","#f0abfc","#701a75", 11, 1))
cells.append(txt("ph3_lbl",
    "▶  Contact nach Buyer · liest buyer_candidates aus market_network · Fallback: Industry-scoped Discovery",
    DX+14, Z_PH3+8, DW-28, 20, "#701a75", 11))
cells += dept_wide("ct", "Contact Department", "contact_intelligence",
                   Z_PH3+30, Z_PH3_H-40, "#fdf2f8","#c026d3","#701a75")

# ── SYNTHESIS LANE ───────────────────────────────────────────────────────────
sy = Z_SYNTH
SYNTH = dict(x=SX+10, w=SW-20, fill="#ede9fe", stroke="#7c3aed", fc="#4c1d95", fs=11)

cells.append(rect("synth_dept",
    "<b>Synthesis Department (AG2 GroupChat)</b>\n"
    "SynthesisLead · Analyst · Critic · Judge\n"
    "Empfängt admitted_packages_for_synthesis() vom Supervisor\n"
    "Vergleicht Department-Findings · surfact Cross-Domain-Spannungen\n"
    "Baut Liquisto Opportunity Assessment\n"
    "BackRequests → Supervisor (neue Mechanismus)",
    SYNTH["x"], sy, SYNTH["w"], 130, SYNTH["fill"], SYNTH["stroke"], SYNTH["fc"], SYNTH["fs"], 2))
sy += 150

cells.append(rect("synth_accept",
    "<b>Supervisor Synthesis Admission Gate</b>\n"
    "accept_synthesis() — LLM-basiert\n"
    "accepted / accepted_with_gaps / rejected\n"
    "generation_mode: normal / fallback / blocked\n"
    "SynthesisEnvelope: raw_package + admitted_payload",
    SYNTH["x"], sy, SYNTH["w"], 100, "#e0e7ff","#4338ca","#312e81", SYNTH["fs"]))
sy += 120

cells.append(rect("fin_fns",
    "<b>Finalization Functions</b>  (pipeline_runner._finalize_readiness)\n"
    "build_quality_review() · harmonize_synthesis_output()\n"
    "build_playbook_assets() · assess_research_readiness()\n"
    "DepartmentGateOverview + PolicyGate-Blockers auswerten\n"
    "→ research_readiness · readiness_score · readiness_blockers",
    SYNTH["x"], sy, SYNTH["w"], 110, SYNTH["fill"], SYNTH["stroke"], SYNTH["fc"], SYNTH["fs"]))
sy += 130

cells.append(rect("readiness_gate",
    "<b>MeetingReadinessGate</b>\n"
    "evaluate() blockiert Finalisierung wenn:\n"
    "· Öffentliche Meeting-kritische Fragen unresolved\n"
    "· Required-Dashboard-Decisions fehlen\n"
    "· Evidence-Qualität unter Schwelle\n"
    "· Minimum-Package nicht erfüllt:\n"
    "  verified_decision_makers ≥1 + hard_financial_signals ≥2\n"
    "→ meeting_ready / discovery_ready / blocked_not_meeting_ready",
    SYNTH["x"], sy, SYNTH["w"], 150, SYNTH["fill"], SYNTH["stroke"], SYNTH["fc"], SYNTH["fs"]))
sy += 170

cells.append(rect("briefing",
    "<b>FinalBriefingComposer</b>\n"
    "compose() → MeetingAction-Liste (primäre Action-Ausgabe)\n"
    "Keine generischen next_steps mehr\n"
    "Deterministisch sortiert (MEETING_ACTION_TYPE_ORDER)",
    SYNTH["x"], sy, SYNTH["w"], 90, SYNTH["fill"], SYNTH["stroke"], SYNTH["fc"], SYNTH["fs"]))
sy += 110

cells.append(rect("report_writer",
    "<b>Report Writer Runtime</b>\n"
    "report_runtime.run() · ReportWriterAgent\n"
    "baut report_package aus finalisierter pipeline_data\n"
    "Emittiert ReportWriter-Telemetry-Events",
    SYNTH["x"], sy, SYNTH["w"], 90, SYNTH["fill"], SYNTH["stroke"], SYNTH["fc"], SYNTH["fs"]))
sy += 110

cells.append(rect("synth_note",
    "<b>Synthesis-Regel</b>\n"
    "Nur admitted packages. Keine Domain-Fakten erfinden.\n"
    "Finalisierung blockiert wenn Meeting-kritische Lücken\n"
    "oder PolicyGate-Blocker unresolved.\n"
    "Status-Split: meeting_ready / discovery_ready / blocked_not_meeting_ready.",
    SYNTH["x"], sy, SYNTH["w"], 100, "#fff7ed","#ea580c","#7c2d12", SYNTH["fs"]))

# ── OUTPUT LANE ───────────────────────────────────────────────────────────────
oy = C0
OUT_STYLE = dict(x=OX+10, w=OW-20, fill="#fef3c7", stroke="#d97706", fc="#78350f", fs=11)

cells.append(rect("checkpoints",
    "<b>Phase Checkpoints</b>\n"
    "after_supervisor_brief: Step1Handoff + hash\n"
    "after_first_pass\n"
    "after_closure\n"
    "after_synthesis\n"
    "after_finalization\n"
    "→ artifacts/runs/{run_id}/checkpoints/",
    OUT_STYLE["x"], oy, OUT_STYLE["w"], 150, OUT_STYLE["fill"], OUT_STYLE["stroke"], OUT_STYLE["fc"], OUT_STYLE["fs"]))
oy += 170

cells.append(rect("artifacts",
    "<b>Run Artifacts</b>\n"
    "pipeline_data.json · run_context.json\n"
    "run_meta.json · memory_snapshot.json\n"
    "chat_history.json · follow_up_history.json\n"
    "checkpoints/*.json · reports/*.pdf",
    OUT_STYLE["x"], oy, OUT_STYLE["w"], 110, OUT_STYLE["fill"], OUT_STYLE["stroke"], OUT_STYLE["fc"], OUT_STYLE["fs"]))
oy += 130

cells.append(rect("ltm_store",
    "<b>Long-Term Memory Store (Schreiben)</b>\n"
    "consolidate_role_patterns() nach Run\n"
    "Nur bei completed / meeting_ready\n"
    "Scrubbed Prozessmuster · domain = \"\"\n"
    "Ziel (GAP-03): Vector Store für semantisches Retrieval",
    OUT_STYLE["x"], oy, OUT_STYLE["w"], 110, "#fee2e2","#dc2626","#7f1d1d", OUT_STYLE["fs"]))
oy += 130

cells.append(rect("pdf",
    "<b>PDF Report DE + EN</b>\n"
    "generate_pdf(lang) on demand via UI\n"
    "DE: _translate_content() via LLM\n"
    "Executive Dashboard · Primary Recommendation\n"
    "Finance/Inventory · Stakeholder Map",
    OUT_STYLE["x"], oy, OUT_STYLE["w"], 110, OUT_STYLE["fill"], OUT_STYLE["stroke"], OUT_STYLE["fc"], OUT_STYLE["fs"]))
oy += 130

cells.append(rect("delivery",
    "<b>Liquisto Mitarbeiter</b>\n"
    "erhält actionable Pre-Meeting-Briefing:\n"
    "Meeting Actions · Customer Confirmation Items\n"
    "Optional Depth Areas · Evidence-backed Findings",
    OUT_STYLE["x"], Z_REPORT + 100, OUT_STYLE["w"], 100, "#e0f2fe","#0284c7","#0c4a6e", OUT_STYLE["fs"]))

# ── FOLLOW-UP SECTION ────────────────────────────────────────────────────────
FY = Z_FU + 40
cells.append(txt("fu_hdr", "Follow-up Mode (CHG-08) — Grounded in rehydrated Run Brain",
                 EX+10, FY-28, PAGE_W-100, 22, "#475569", 13))

cells.append(rect("fu_entry",
    "<b>Follow-up UI Panel</b>\nrun_id + Frage eingeben\nnach Bericht-Review",
    EX+10, FY, 240, 80, "#e0f2fe","#0284c7","#0c4a6e", 11))

cells.append(rect("fu_loader",
    "<b>load_run_artifact(run_id)</b>\nlädt pipeline_data.json + run_context.json\nRehydriert department_run_states\n(task_artifacts · review_artifacts · decision_artifacts)",
    CX+10, FY, CW-20, 90, "#dbeafe","#2563eb","#1e3a8a", 11))

cells.append(rect("fu_router",
    "<b>Follow-up Router</b>\nKeyword-Routing → Company / Market / Buyer / Contact / CrossDomain\nGAP-04 Ziel: Embedding-Similarity-Routing via MEETING_QUESTION_REGISTRY",
    CX+10, FY+110, CW-20, 80, "#dbeafe","#2563eb","#1e3a8a", 11))

cells.append(rect("fu_resolver",
    "<b>FollowUpEvidenceResolver</b>\nPriorität: task_artifacts (accepted) > pipeline_data > dept_packages\nrequires_additional_research wenn unresolved\nEvidence max 3 Facts + 2 AcceptedPoints pro Task",
    CX+10, FY+210, CW-20, 90, "#dbeafe","#2563eb","#1e3a8a", 11))

FU_DEPT_Y = FY
fu_each_w = (DW - 10 - 4*10) // 5
fu_depts = [
    ("fu_co",    "Company\nFollow-up",     "#f0fdf4","#16a34a","#14532d"),
    ("fu_ma",    "Market\nFollow-up",      "#fff7ed","#f97316","#9a3412"),
    ("fu_bu",    "Buyer\nFollow-up",       "#ecfeff","#06b6d4","#155e75"),
    ("fu_ct",    "Contact\nFollow-up",     "#fdf2f8","#c026d3","#701a75"),
    ("fu_cross", "Cross-Domain\nFollow-up","#ede9fe","#7c3aed","#4c1d95"),
]
fux = DX + 5
for fu_id, fu_lbl, fu_fill, fu_strk, fu_fc in fu_depts:
    cells.append(rect(fu_id,
        f"<b>{fu_lbl}</b>\nAnswer from stored run brain\nnew research only if gaps remain",
        fux, FU_DEPT_Y, fu_each_w, 90, fu_fill, fu_strk, fu_fc, 10))
    fux += fu_each_w + 10

cells.append(rect("fu_answer",
    "<b>Follow-up Answer / Addendum</b>\nAntwort mit Quellen aus run_context\nunresolved_points · requires_additional_research\nexportiert als follow_up_history.json",
    OX+10, FY, OW-20, 90, "#fef3c7","#d97706","#78350f", 11))

# ── SECURITY LAYER ───────────────────────────────────────────────────────────
cells.append(rect("sec_bg", "", EX, Z_SEC, PAGE_W-60, 110, "#fff1f2","#e11d48","#881337", 11, 2))
cells.append(txt("sec_lbl",
    "Operational Security + Governance Layer — Cross-cutting, kein Dept-Teilnehmer",
    EX+10, Z_SEC+6, 700, 22, "#881337", 12))
sec_items = [
    ("sec_secrets",   "Secret Resolution\nprocess env → OS keyring\nkein .env für API-Keys"),
    ("sec_preflight", "Preflight Gate\npreflight.py · Packages · Imports\nQuery-Strategy · Credentials · Port"),
    ("sec_ci",        "CI / Review Gates\nCODEOWNERS · Secret Scan\nWorkflow Hardening · Release Attestation"),
    ("sec_hooks",     "Pre-commit Hooks\nRuff --fix · Bandit\nbei jedem git commit"),
    ("sec_guardrails","Runtime Guardrails\nsafe run_id path resolution\nAtomic JSON writes · Audit Min."),
]
sx_pos = EX + 10
sec_w = (PAGE_W - 80) // 5 - 8
for s_id, s_lbl in sec_items:
    cells.append(rect(s_id, s_lbl, sx_pos, Z_SEC+32, sec_w, 68, "#ffe4e6","#e11d48","#881337", 10))
    sx_pos += sec_w + 10

# ── EDGES ────────────────────────────────────────────────────────────────────
# Entry flow
cells.append(edge("e_user_ui",    "",                    "user",       "ui",           "#0284c7"))
cells.append(edge("e_ui_runner",  "startet run_pipeline", "ui",         "runner",        "#2563eb"))
# Runner → components
cells.append(edge("e_run_sup",    "build_intake_brief",  "runner",     "supervisor",    "#2563eb"))
cells.append(edge("e_run_stm",    "initialisiert",       "runner",     "stm",           "#dc2626", 1, True))
cells.append(edge("e_run_ltm",    "retrieve_strategies", "runner",     "ltm_load",      "#dc2626", 1, True))
cells.append(edge("e_run_qreg",   "build_question_registry", "supervisor", "qreg",      "#2563eb"))
cells.append(edge("e_qreg_handoff", "validate Step 1", "qreg", "step1_handoff", "#4338ca", 2))
cells.append(edge("e_run_budget", "PhaseBudget init",   "runner",     "budget",        "#ea580c", 1, True))

# Supervisor → Departments (Phase 1 parallel, cross-lane routing)
PH1_MID = Z_PH1 + Z_PH1_H // 2
cells.append(edge("e_sup_co", "validated handoff (Phase 1 parallel)", "step1_handoff", "co_lead", "#16a34a", 2,
                  pts=[(CX+CW, PH1_MID-20), (DX, PH1_MID-20)]))
cells.append(edge("e_sup_ma", "validated handoff (Phase 1 parallel)", "step1_handoff", "ma_lead", "#f97316", 2,
                  pts=[(CX+CW, PH1_MID+20), (DX, PH1_MID+20)]))
cells.append(edge("e_sup_bu", "validated handoff (Phase 2 sequential)", "step1_handoff", "bu_lead", "#06b6d4", 2,
                  pts=[(CX+CW, Z_PH2+Z_PH2_H//2), (DX, Z_PH2+Z_PH2_H//2)]))
cells.append(edge("e_sup_ct", "validated handoff + buyer_candidates", "step1_handoff", "ct_lead", "#c026d3", 2,
                  pts=[(CX+CW, Z_PH3+Z_PH3_H//2), (DX, Z_PH3+Z_PH3_H//2)]))

# KB → Depts (dashed, from control lane to departments)
KB_MID = C0 + 620 - 60  # approx y of dept_kb center
cells.append(edge("e_kb_co", "KB guidance", "dept_kb", "co_lead", "#ea580c", 1, True,
                  pts=[(CX+CW, KB_MID), (DX, KB_MID), (DX, Z_PH1+130), (CO_X+80, Z_PH1+130)]))
cells.append(edge("e_kb_ma", "", "dept_kb", "ma_lead", "#ea580c", 1, True,
                  pts=[(CX+CW, KB_MID+15), (DX, KB_MID+15), (DX, Z_PH1+145), (MA_X+80, Z_PH1+145)]))
cells.append(edge("e_kb_bu", "", "dept_kb", "bu_lead", "#ea580c", 1, True,
                  pts=[(CX+CW, KB_MID+30), (DX, KB_MID+30), (DX, Z_PH2+80), (DX+20, Z_PH2+80)]))
cells.append(edge("e_kb_ct", "", "dept_kb", "ct_lead", "#ea580c", 1, True,
                  pts=[(CX+CW, KB_MID+45), (DX, KB_MID+45), (DX, Z_PH3+80), (DX+20, Z_PH3+80)]))

# Dept internal flows
for prefix, clr in [("co","#16a34a"),("ma","#f97316"),("bu","#06b6d4"),("ct","#c026d3")]:
    cells.append(edge(f"e_{prefix}_lr", "", f"{prefix}_lead", f"{prefix}_res",  clr))
    cells.append(edge(f"e_{prefix}_rc", "", f"{prefix}_res",  f"{prefix}_crit", clr))
    cells.append(edge(f"e_{prefix}_cj", "escalate", f"{prefix}_crit", f"{prefix}_judge", clr, 1, True))
    cells.append(edge(f"e_{prefix}_jl", "decision", f"{prefix}_judge", f"{prefix}_lead", clr, 1, True))

# Dept output → Handoff (route through Resolution lane avoiding Synthesis)
PKG_BYPASS_X = RX - 20
for prefix, y_mid in [
    ("co", Z_PH1 + Z_PH1_H // 2 - 40),
    ("ma", Z_PH1 + Z_PH1_H // 2 + 40),
    ("bu", Z_PH2 + Z_PH2_H // 2),
    ("ct", Z_PH3 + Z_PH3_H // 2),
]:
    cells.append(edge(f"e_{prefix}_pkg", "dept package (accepted / accepted_with_gaps / rejected)",
                      f"{prefix}_out", "handoff", "#2563eb", 2,
                      pts=[(DX+DW, y_mid), (PKG_BYPASS_X, y_mid), (PKG_BYPASS_X, RC_Y+50), (CX+CW, RC_Y+50)]))

# Handoff → RC
cells.append(edge("e_handoff_rc", "classify()", "handoff", "rc", "#4338ca", 2))

# RC → paths
cells.append(edge("e_rc_ac", "AUTO_CLOSE_REQUIRED",      "rc", "auto_close", "#4338ca"))
cells.append(edge("e_rc_db", "USER_DECISION_REQUIRED",   "rc", "dashboard",  "#4338ca", 1, False, None, 10))
cells.append(edge("e_rc_bl", "BLOCKING_FAILURE",         "rc", "blocking",   "#dc2626", 2))

# RC / Auto-Close / Dashboard → Synthesis
# Route: go right into Resolution lane, then down BELOW all depts, then right to Synthesis
# BYPASS_Y is already below Z_PH3 + Z_PH3_H
RES_RIGHT = RX + RW + 10
SY_TOP = Z_SYNTH + 65

cells.append(edge("e_rc_sy",
    "NOT_MEETING_CRITICAL / CUSTOMER_CONFIRMATION",
    "rc", "synth_dept", "#7c3aed", 1,
    pts=[(RES_RIGHT, RC_Y+200), (RES_RIGHT, BYPASS_Y), (SX+220, BYPASS_Y), (SX+220, SY_TOP)]))
cells.append(edge("e_ac_sy", "after closure",
    "auto_close", "synth_dept", "#7c3aed", 1,
    pts=[(RES_RIGHT+8, RC_Y+345), (RES_RIGHT+8, BYPASS_Y+12), (SX+232, BYPASS_Y+12), (SX+232, SY_TOP)]))
cells.append(edge("e_db_sy", "after resume",
    "dashboard", "synth_dept", "#7c3aed", 1,
    pts=[(RES_RIGHT+16, RC_Y+455), (RES_RIGHT+16, BYPASS_Y+24), (SX+244, BYPASS_Y+24), (SX+244, SY_TOP)]))

# Synthesis internal flow
cells.append(edge("e_sy_acc",  "",                    "synth_dept",    "synth_accept",   "#7c3aed"))
cells.append(edge("e_acc_fin", "",                    "synth_accept",  "fin_fns",        "#7c3aed"))
cells.append(edge("e_fin_rg",  "",                    "fin_fns",       "readiness_gate", "#7c3aed"))
cells.append(edge("e_rg_brief","",                    "readiness_gate","briefing",       "#7c3aed"))
cells.append(edge("e_brief_rw","",                    "briefing",      "report_writer",  "#7c3aed"))

# Report Writer → Output
cells.append(edge("e_rw_art",  "report_package",  "report_writer", "artifacts", "#d97706", 2,
                  pts=[(SX+SW, Z_REPORT+45), (OX+10, Z_REPORT+45)]))
cells.append(edge("e_art_ltm", "consolidate_role_patterns()", "artifacts", "ltm_store", "#dc2626", 1, True))
cells.append(edge("e_rw_del",  "Briefing output", "report_writer", "delivery",  "#0284c7", 2,
                  pts=[(SX+SW, Z_REPORT+90), (OX+OW//2, Z_REPORT+90), (OX+OW//2, Z_REPORT+150)]))

# Follow-up
cells.append(edge("e_fu_eu",   "run_id + Frage",     "fu_entry",    "fu_loader",   "#2563eb"))
cells.append(edge("e_fu_lr",   "",                   "fu_loader",   "fu_router",   "#2563eb"))
cells.append(edge("e_fu_rr",   "",                   "fu_router",   "fu_resolver", "#2563eb"))
cells.append(edge("e_fu_ans",  "follow-up artifact", "fu_resolver", "fu_answer",   "#d97706",
                  pts=[(CX+CW, FY+255), (OX+10, FY+255)]))
# Resolver → dept paths (fan out in dept lane)
for fu_id, fy_offset in [("fu_co",0),("fu_ma",15),("fu_bu",30),("fu_ct",45),("fu_cross",60)]:
    cells.append(edge(f"e_fu_to_{fu_id}", "", "fu_resolver", fu_id, "#6366f1", 1, True,
                      pts=[(CX+CW, FY+300+fy_offset), (DX, FY+300+fy_offset), (DX, FY+45)]))

# ── ASSEMBLE XML ─────────────────────────────────────────────────────────────
xml_cells = "\n                ".join(cells)
xml = f"""<mxfile host="65bd71144e">
    <diagram id="runtime-architecture-v2" name="Runtime Architecture">
        <mxGraphModel dx="1200" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{PAGE_W}" pageHeight="{PAGE_H}" math="0" shadow="0">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
                {xml_cells}
            </root>
        </mxGraphModel>
    </diagram>
</mxfile>"""

# Validate
try:
    ET.fromstring(xml)  # nosec B314
    print("XML valid ✓")
except ET.ParseError as e:
    print(f"XML ERROR: {e}")
    raise

OUT.write_text(xml, encoding="utf-8")
print(f"Written to {OUT}")
print(f"Page: {PAGE_W} × {PAGE_H} px")
print(f"Total cells: {len(cells)}")
print(f"File size: {len(xml):,} chars, {xml.count(chr(10))} lines")
