"""Generate docs/drawio/runtime_step1.drawio — corrected layout.

Fixes vs. previous version:
- normalize_domain shown in intake step (not in retrieve step)
- Supervisor Research nodes moved to align with brief_call (edges go forward/right, not backward/up)
- memory node: shows create_runtime_stores(), healthcheck, storage snapshot, no run-path backfill
- retrieve node: removes normalize_domain (already done earlier)
- Step1Handoff node added: RuntimeEvent, checkpoint hash, validation gate
- outputs node: adds budget_tracker + run_dir from InitialRunState
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "drawio" / "runtime_step1.drawio"


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def rect(id_, label, x, y, w, h, fill, stroke, fc="#0f172a", fs=12):
    s = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
         f"fontSize={fs};spacing=8;fontColor={fc};")
    return (f'<mxCell id="{id_}" value="{esc(label)}" style="{s}" parent="1" vertex="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def txt(id_, label, x, y, w, h, fc="#0f172a", fs=15, bold=True):
    fw = "1" if bold else "0"
    s = (f"text;html=1;strokeColor=none;fillColor=none;align=left;"
         f"verticalAlign=middle;fontSize={fs};fontStyle={fw};fontColor={fc};")
    return (f'<mxCell id="{id_}" value="{esc(label)}" style="{s}" parent="1" vertex="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def lane(id_, x, y, w, h):
    s = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f8fafc;strokeColor=#cbd5e1;"
    return (f'<mxCell id="{id_}" value="" style="{s}" parent="1" vertex="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def edge(id_, src, tgt, label="", color="#64748b", fw=2, pts=None):
    s = (f"endArrow=block;endFill=1;strokeColor={color};strokeWidth={fw};"
         f"edgeStyle=orthogonalEdgeStyle;fontColor={color};fontSize=11;")
    if pts:
        arr = "".join(f'<mxPoint x="{p[0]}" y="{p[1]}"/>' for p in pts)
        geom = f'<mxGeometry relative="1" as="geometry"><Array as="points">{arr}</Array></mxGeometry>'
    else:
        geom = '<mxGeometry relative="1" as="geometry"/>'
    return (f'<mxCell id="{id_}" value="{esc(label)}" style="{s}" '
            f'parent="1" source="{src}" target="{tgt}" edge="1">{geom}</mxCell>')


# ── Layout ────────────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = 1960, 2820
LANE_Y, LANE_H = 120, 2660

# 4 lanes
LX = [40, 340, 820, 1270]
LW = [280, 460, 430, 650]

C0 = LANE_Y + 20   # content start y

cells = []

# ── Page frame elements ───────────────────────────────────────────────────────
cells.append(txt("title",
    "Liquisto Runtime — Step 1: Runner Init + Supervisor Brief",
    40, 18, 1200, 32, "#0f172a", 22))
cells.append(txt("subtitle",
    "Code-aligned flow in src/pipeline_runner.py — "
    "endet unmittelbar vor run_supervisor_loop() / _run_first_pass()",
    40, 52, 1860, 22, "#475569", 11, False))

# Lanes
for i, (lx, lw) in enumerate(zip(LX, LW)):
    cells.append(lane(f"lane_{i}", lx, LANE_Y, lw, LANE_H))

# Lane labels
LANE_LABELS = [
    ("lbl_0", "Input",                      LX[0]+20,  LANE_Y+8),
    ("lbl_1", "pipeline_runner.py",         LX[1]+20,  LANE_Y+8),
    ("lbl_2", "Supervisor Intake Research", LX[2]+20,  LANE_Y+8),
    ("lbl_3", "Seeded Runtime State + Handoff", LX[3]+20, LANE_Y+8),
]
for id_, label, x, y in LANE_LABELS:
    cells.append(txt(id_, label, x, y, 360, 20, "#0f172a", 13))

# ── INPUT LANE ────────────────────────────────────────────────────────────────
cells.append(rect("user_input",
    "<b>User / UI Input</b>\n"
    "company_name\n"
    "web_domain\n"
    "optional on_message hook\n"
    "(Streamlit oder direkter Caller)",
    LX[0]+20, C0+40, 230, 130,
    "#e0f2fe","#0284c7","#0c4a6e", 12))

# ── RUNNER LANE ───────────────────────────────────────────────────────────────
RY = C0 + 10   # runner y-start

cells.append(rect("run_start",
    "<b>run_pipeline(...) starts</b>\n"
    "start_time = perf_counter()\n"
    "run_id = _timestamp_run_id()  ← UTC sortable\n"
    "run_dir = resolve_run_dir(run_id, runs_root=RUNS_DIR)",
    LX[1]+20, RY, LW[1]-40, 110,
    "#dbeafe","#2563eb","#1e3a8a", 12))
RY += 130

cells.append(rect("intake",
    "<b>Validate intake + normalize domain</b>\n"
    "intake = IntakeRequest(company_name, web_domain)\n"
    "  → trimmt Felder · setzt language='de'\n"
    "  → ValueError bei leerem Input → _failed_intake_result()\n"
    "     failed_phase = 'intake_validation'\n"
    "normalized_domain = normalize_domain(intake.web_domain)\n"
    "  ← wird an RunContext.intake + Retrieval weitergereicht",
    LX[1]+20, RY, LW[1]-40, 150,
    "#eff6ff","#3b82f6","#1e3a8a", 12))
RY += 170

cells.append(rect("agents",
    "<b>Create runtime agents</b>\n"
    "agents = create_runtime_agents()\n"
    "→ Supervisor · Company/Market/Buyer/Contact Dept\n"
    "→ Synthesis · ReportWriter",
    LX[1]+20, RY, LW[1]-40, 100,
    "#eff6ff","#3b82f6","#1e3a8a", 12))
RY += 120

cells.append(rect("memory",
    "<b>Initialize storage boundary + run context</b>\n"
    "stores = create_runtime_stores(\n"
    "  runs_root=RUNS_DIR,\n"
    "  long_term_memory_path=LONG_TERM_MEMORY_PATH\n"
    ")\n"
    "stores.healthcheck_required()\n"
    "memory_store = stores.long_term_memory\n"
    "  local_dev → FileLongTermMemoryStore\n"
    "  production → Postgres/pgvector required, no file fallback\n"
    "run_context = RunContext(\n"
    "  run_id=run_id,\n"
    "  intake={company_name, web_domain, normalized_domain,\n"
    "          canonical_url, language, resolved_ips, suffix metadata}\n"
    ")\n"
    "_record_phase(run_context, 'initialized')\n"
    "run_context.resolution_state['storage'] = stores.snapshot()\n"
    "← no opportunistic historical backfill in normal run path",
    LX[1]+20, RY, LW[1]-40, 230,
    "#eff6ff","#3b82f6","#1e3a8a", 12))
RY += 250

cells.append(rect("retrieve",
    "<b>Initial process-memory retrieval</b>\n"
    "context = RetrievalContext(\n"
    "  run_id, company_name, normalized_domain,\n"
    "  phase='memory_retrieval', target_scope='run_start'\n"
    ")\n"
    "initial_retrieval = retrieve_strategy_batch(\n"
    "  memory_store, context, DEFAULT_GENERAL_RETRIEVAL_LIMIT\n"
    ")\n"
    "run_context.retrieved_strategies = initial_retrieval.patterns\n"
    "resolution_state['memory_retrieval']['initial'] = snapshot\n"
    "← generic, no industry hint yet; no domain/company ranking bonus",
    LX[1]+20, RY, LW[1]-40, 150,
    "#eff6ff","#3b82f6","#1e3a8a", 12))
RY += 170

BRIEF_Y = RY
cells.append(rect("brief_call",
    "<b>Build supervisor brief</b>\n"
    "supervisor = _build_supervisor_brief(state, on_message)\n"
    "_record_phase(run_context, 'supervisor_brief')\n"
    "brief, supervisor_message =\n"
    "  state.agents['supervisor'].build_intake_brief(state.intake)\n"
    "← Step 1, noch vor Department-Routing",
    LX[1]+20, RY, LW[1]-40, 130,
    "#dbeafe","#2563eb","#1e3a8a", 12))

# ── SUPERVISOR RESEARCH LANE (aligned with brief_call) ───────────────────────
SR_Y = BRIEF_Y + 10   # align with brief_call

cells.append(rect("research_tool",
    "<b>src/research/tools.py</b>\n"
    "build_company_research(NormalizedDomainResult, company_name)\n"
    "→ CompanyResearchResult schema_version\n"
    "← string domain only as deprecated legacy path",
    LX[2]+20, SR_Y, LW[2]-40, 100,
    "#dcfce7","#16a34a","#14532d", 12))
SR_Y += 120

cells.append(rect("research_steps",
    "<b>Research helper sequence</b>\n"
    "homepage_url = normalized.canonical_url\n"
    "fetch_website_snapshot(url)\n"
    "→ WebsiteSnapshot contract\n"
    "DNS/redirect SSRF guard · IP pinning · max redirects\n"
    "content-type allowlist · response size limit · content_hash\n"
    "title/meta/OG/H1/H2/about/imprint/language",
    LX[2]+20, SR_Y, LW[2]-40, 120,
    "#f0fdf4","#16a34a","#14532d", 12))
SR_Y += 140

cells.append(rect("identity",
    "<b>Identity + summary</b>\n"
    "infer_company_identity(snapshot)\n"
    "→ IdentityResolutionResult\n"
    "  submitted_name · brand_name · verified_company_name\n"
    "  verified_legal_name='' in MVP + source_gap(register/linkedin/wiki)\n"
    "summarize_visible_text(snapshot.visible_text)\n"
    "→ bounded homepage_excerpt + extraction_quality",
    LX[2]+20, SR_Y, LW[2]-40, 120,
    "#f0fdf4","#16a34a","#14532d", 12))
SR_Y += 140

cells.append(rect("industry",
    "<b>Supervisor evidence + readiness contract</b>\n"
    "infer_industry_result(title, description, summary)\n"
    "→ IndustryInferenceResult: hint, confidence, evidence_fields, alternatives\n"
    "CompanyResearchResult warnings/errors:\n"
    "  fetch_timeout · tls_failed · redirect_blocked · unsupported_content_type\n"
    "  text_extraction_empty/weak · js_content_detected · industry_unknown\n"
    "classify_identity_confidence(...) + detect_identity_conflict(...)\n"
    "BriefingFetchAudit: final_url, redirects, status, content length/lang\n"
    "EvidenceItem / MissingEvidence per supported field\n"
    "classify_briefing_readiness(...)\n"
    "SupervisorBriefMessage:\n"
    "  schema_version, status, readiness, confidence,\n"
    "  routing_gaps, evidence_summary, payload\n"
    "validate_supervisor_brief_message(...)",
    LX[2]+20, SR_Y, LW[2]-40, 210,
    "#f0fdf4","#16a34a","#14532d", 12))

# ── STATE LANE ────────────────────────────────────────────────────────────────
# Starts after research completes → SR_Y + 150 + gap
STATE_Y = SR_Y + 230

RUNTIME_STATE_Y = STATE_Y   # save before incrementing — needed for edge11 routing
cells.append(rect("runtime_state",
    "<b>Seed RunContext with Step-1-Data</b>\n"
    "state.run_context.supervisor_brief = supervisor_message['payload']\n"
    "state.run_context.question_registry = build_question_registry()\n"
    "  → 12 MEETING_QUESTION_REGISTRY Einträge\n"
    "state.run_context.answer_matrix = build_initial_answer_matrix()\n"
    "  → alle Fragen auf status='pending'\n"
    "brief_context = RetrievalContext(\n"
    "  industry_hint=brief.industry_hint,\n"
    "  phase='supervisor_brief', question_ids=registry.keys()\n"
    ")\n"
    "role_batches = retrieve_strategy_batch(..., role_context(role))\n"
    "→ retrieved_role_strategies final before Step 2\n"
    "→ memory_retrieval audit snapshots: initial, brief_context, roles\n"
    "resolution_state['supervisor_brief'] = non-sensitive diagnosis:\n"
    "  readiness, confidence, fetch_status, evidence_count,\n"
    "  routing_gaps, duration_ms\n"
    "resolution_state['intake_research'] = non-sensitive research diagnostics:\n"
    "  timings, snapshot audit, warnings/errors, identity + industry",
    LX[3]+20, STATE_Y, LW[3]-40, 200,
    "#fef9c3","#ca8a04","#713f12", 12))
STATE_Y += 220

cells.append(rect("message",
    "<b>Emit first RuntimeEvent</b>\n"
    "first_event = emit_message(\n"
    "  on_message,\n"
    "  agent='Supervisor',\n"
    "  content=json.dumps(supervisor_message),\n"
    "  run_id=state.run_id,\n"
    "  sequence=len(state.messages)+1,\n"
    "  phase='supervisor_brief',\n"
    "  content_type='application/json'\n"
    ")\n"
    "→ event_id · sequence · timestamp · schema_version",
    LX[3]+20, STATE_Y, LW[3]-40, 150,
    "#fef9c3","#ca8a04","#713f12", 12))
STATE_Y += 170

cells.append(rect("checkpoint",
    "<b>Checkpoint: after_supervisor_brief</b>\n"
    "_write_checkpoint(\n"
    "  state.run_dir,\n"
    "  'after_supervisor_brief',\n"
    "  state.run_context\n"
    ")\n"
    "→ CheckpointInfo: checkpoint_id, phase, path, written\n"
    "→ checkpoint_hash im JSON-Payload\n"
    "→ atomarer Write via .tmp + replace",
    LX[3]+20, STATE_Y, LW[3]-40, 140,
    "#fef9c3","#ca8a04","#713f12", 12))
STATE_Y += 160

cells.append(rect("handoff_gate",
    "<b>Step1Handoff Contract + Gate</b>\n"
    "build_step1_handoff(...)\n"
    "schema_version · run_id · intake · supervisor_message\n"
    "question_registry + answer_matrix\n"
    "retrieval snapshots · runtime_agents_snapshot\n"
    "storage_snapshot · budget_snapshot\n"
    "first_event + checkpoint\n"
    "readiness: ready_for_department_routing / ready_with_gaps / blocked_step1_handoff\n"
    "handoff_allows_department_routing(...) gates Step 2",
    LX[3]+20, STATE_Y, LW[3]-40, 170,
    "#e0e7ff","#4338ca","#312e81", 12))
STATE_Y += 190

cells.append(rect("handoff",
    "<b>Step 1 Boundary — Handoff an Step 2</b>\n"
    "returns SupervisorBriefResult(\n"
    "  brief, supervisor_message, step1_handoff\n"
    ")\n"
    "\n"
    "Nächster Aufruf in run_pipeline():\n"
    "if handoff_allows_department_routing(...):\n"
    "  first_pass = _run_first_pass(state, brief=supervisor.brief)\n"
    "  → run_supervisor_loop(brief, run_context, agents, on_message)\n"
    "else: failed_phase='step1_handoff'",
    LX[3]+20, STATE_Y, LW[3]-40, 140,
    "#fee2e2","#dc2626","#7f1d1d", 12))
STATE_Y += 160

cells.append(rect("outputs",
    "<b>Step 1 live objects (InitialRunState)</b>\n"
    "state.run_context  ← Run Brain: Intake + Strategies\n"
    "  + supervisor_brief + question_registry + answer_matrix\n"
    "  + resolution_state[initialized, storage]\n"
    "state.agents       ← alle Runtime-Agents bereit\n"
    "state.messages[0]  ← erstes Supervisor-Event\n"
    "resolution_state['step1_handoff'] ← validated snapshot\n"
    "state.budget_tracker  ← PhaseBudgetTracker (leer)\n"
    "state.run_dir      ← Artefakt-Zielpfad\n"
    "supervisor.brief   ← SupervisorBrief Dataclass\n"
    "supervisor.supervisor_message",
    LX[3]+20, STATE_Y, LW[3]-40, 180,
    "#fef3c7","#d97706","#78350f", 12))

# ── EDGES ─────────────────────────────────────────────────────────────────────
# Runner flow (top-down)
cells.append(edge("e1", "user_input", "run_start"))
cells.append(edge("e2", "run_start",  "intake"))
cells.append(edge("e3", "intake",     "agents"))
cells.append(edge("e4", "agents",     "memory"))
cells.append(edge("e5", "memory",     "retrieve"))
cells.append(edge("e6", "retrieve",   "brief_call"))

# brief_call → research_tool (now goes RIGHT, same y-level)
cells.append(edge("e7", "brief_call", "research_tool", "calls", "#16a34a"))

# Research internal flow (top-down, forward)
cells.append(edge("e8",  "research_tool",  "research_steps", "", "#16a34a"))
cells.append(edge("e9",  "research_steps", "identity",       "", "#16a34a"))
cells.append(edge("e10", "identity",       "industry",       "", "#16a34a"))

# industry → runtime_state (goes right then down — forward direction, no backtracking)
IND_RIGHT_X   = LX[2] + LW[2]       # 820+430 = 1250
RT_LEFT_X     = LX[3]               # 1270
IND_MID_Y     = SR_Y + 75           # center y of industry node
RT_CENTER_Y   = RUNTIME_STATE_Y + 70  # center y of runtime_state node
BRIDGE_X      = RT_LEFT_X - 10      # routing corridor between lanes (x=1260)
cells.append(edge("e11", "industry", "runtime_state", "brief fertig",
                  "#64748b", 2,
                  pts=[(BRIDGE_X, IND_MID_Y), (BRIDGE_X, RT_CENTER_Y)]))

# State internal flow (top-down)
cells.append(edge("e12", "runtime_state", "message",    "", "#64748b"))
cells.append(edge("e13", "message",       "checkpoint", "", "#ca8a04", 2))
cells.append(edge("e14", "checkpoint",    "handoff_gate", "CheckpointInfo", "#4338ca", 2))
cells.append(edge("e15", "handoff_gate",  "handoff",    "validated", "#4338ca", 2))
cells.append(edge("e16", "handoff",       "outputs",    "", "#64748b"))

# ── ASSEMBLE XML ──────────────────────────────────────────────────────────────
xml_cells = "\n        ".join(cells)
xml = f"""<mxfile host="65bd71144e">
  <diagram id="runtime-step1" name="Runtime Step 1 - Runner Init">
    <mxGraphModel dx="1400" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{PAGE_W}" pageHeight="{PAGE_H}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        {xml_cells}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""

# Validate
import xml.etree.ElementTree as ET
try:
    ET.fromstring(xml)
    print("XML valid ✓")
except ET.ParseError as e:
    print(f"XML ERROR: {e}")
    raise

OUT.write_text(xml, encoding="utf-8")
nodes = xml.count('vertex="1"')
edges_ = xml.count('edge="1"')
print(f"Written to {OUT}")
print(f"Page: {PAGE_W} × {PAGE_H} px")
print(f"Nodes: {nodes} | Edges: {edges_}")
