"""Generate docs/drawio/runtime_step2.drawio."""
import xml.etree.ElementTree as ET  # nosec B405
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "drawio" / "runtime_step2.drawio"


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def rect(id_, label, x, y, w, h, fill, stroke, fc="#0f172a", fs=12):
    style = (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"fontSize={fs};spacing=8;fontColor={fc};"
    )
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def txt(id_, label, x, y, w, h, fc="#0f172a", fs=15, bold=True):
    fw = "1" if bold else "0"
    style = (
        f"text;html=1;strokeColor=none;fillColor=none;align=left;"
        f"verticalAlign=middle;fontSize={fs};fontStyle={fw};fontColor={fc};"
    )
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def lane(id_, x, y, w, h):
    style = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f8fafc;strokeColor=#cbd5e1;"
    return (
        f'<mxCell id="{id_}" value="" style="{style}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def edge(id_, src, tgt, label="", color="#64748b", fw=2, pts=None):
    style = (
        f"endArrow=block;endFill=1;strokeColor={color};strokeWidth={fw};"
        f"edgeStyle=orthogonalEdgeStyle;fontColor={color};fontSize=11;"
    )
    if pts:
        points = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts)
        geom = f'<mxGeometry relative="1" as="geometry"><Array as="points">{points}</Array></mxGeometry>'
    else:
        geom = '<mxGeometry relative="1" as="geometry"/>'
    return (
        f'<mxCell id="{id_}" value="{esc(label)}" style="{style}" parent="1" '
        f'source="{src}" target="{tgt}" edge="1">{geom}</mxCell>'
    )


PAGE_W, PAGE_H = 2160, 2720
LANE_Y, LANE_H = 120, 2520
LX = [40, 360, 850, 1350, 1760]
LW = [290, 460, 470, 380, 360]

cells = []
cells.append(txt("title", "Liquisto Runtime - Step 2: First Pass + Supervisor Department Routing", 40, 18, 1500, 32, "#0f172a", 22))
cells.append(txt("subtitle", "Code-aligned flow in src/pipeline_runner.py::_run_first_pass() and src/orchestration/supervisor_loop.py::run_supervisor_loop()", 40, 52, 1960, 22, "#475569", 11, False))

for i, (x, w) in enumerate(zip(LX, LW, strict=False)):
    cells.append(lane(f"lane_{i}", x, LANE_Y, w, LANE_H))

labels = [
    ("lbl_0", "Step-1 Handoff", LX[0] + 20),
    ("lbl_1", "pipeline_runner.py", LX[1] + 20),
    ("lbl_2", "Supervisor Loop", LX[2] + 20),
    ("lbl_3", "Departments / AG2 Runtimes", LX[3] + 20),
    ("lbl_4", "Run State + Boundary", LX[4] + 20),
]
for id_, label, x in labels:
    cells.append(txt(id_, label, x, LANE_Y + 8, 340, 20, "#0f172a", 13))

# Input lane
cells.append(rect("step1_ready", "<b>Step 1 complete</b>\nSupervisorBriefResult\n- brief\n- supervisor_message\nRunContext already has:\n- supervisor_brief\n- question_registry\n- answer_matrix", LX[0] + 20, 170, 250, 150, "#fef9c3", "#ca8a04", "#713f12"))

# Runner lane
cells.append(rect("first_pass_entry", "<b>_run_first_pass(...)</b>\n_record_phase(run_context, 'first_pass')\n\nCalls run_supervisor_loop(\n  brief, run_context, agents, on_message\n)", LX[1] + 20, 170, 420, 130, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("runner_collect", "<b>Collect loop result</b>\nsections\ndepartment_packages\nloop_messages\ncompleted_backlog\ndepartment_timings\nfirst_round_resolution\n\nstate.messages.extend(loop_messages)", LX[1] + 20, 2130, 420, 150, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("runner_budget", "<b>First-pass budget accounting</b>\nfirst_pass_snapshot = short_term_memory.snapshot()\nfirst_pass_tokens = usage_totals.total_tokens\nbudget_tracker.record_phase_tokens('first_pass', first_pass_tokens)\nif budget exceeded:\n  record_stop('first_pass', 'token_budget_exceeded')", LX[1] + 20, 2300, 420, 170, "#dbeafe", "#2563eb", "#1e3a8a"))

# Supervisor loop lane
cells.append(rect("loop_init", "<b>run_supervisor_loop(...)</b>\nEnsure question_registry + answer_matrix exist\nInitialize local outputs:\nsections, department_packages, messages, completed_backlog, department_timings", LX[2] + 20, 160, 430, 130, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("assignments", "<b>Build task contracts</b>\nassignments = build_initial_assignments(brief)\ndepartment_assignments = build_department_assignments(brief)\n\nEach Assignment carries:\ntask_key, assignee, target_section, objective, model_name, allowed_tools, depends_on, run_condition, question_ids", LX[2] + 20, 320, 430, 170, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("opening", "<b>Supervisor opening + active tasks</b>\nemit Supervisor opening_message()\nFor every non-synthesis task:\nrun_context.record_task(... status='assigned' ...)", LX[2] + 20, 520, 430, 120, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("parallel_assign", "<b>Phase 1: parallel batch</b>\n_PARALLEL_BATCH = {CompanyDepartment, MarketDepartment}\nFor each department:\n- emit department_assigned\n- create isolated working_set + baseline\n- submit _run_single_department(...) to ThreadPoolExecutor", LX[2] + 20, 700, 430, 170, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("parallel_review", "<b>As each parallel future completes</b>\nsection_payload, department_messages, package = future.result()\nSupervisor accept_department_package(...)\n_apply_structured_runtime_artifacts(...)\n_apply_acceptance_gate(...)\nemit department_package_reviewed\nupdate task statuses + answer matrix", LX[2] + 20, 1110, 430, 190, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("merge", "<b>Merge parallel memory deltas</b>\nFor dept in canonical order:\n  delta = working_set.delta_from(baseline)\n  main short_term_memory.merge_from(delta)\n\nPrevents concurrent writes and duplicate seeded data.", LX[2] + 20, 1330, 430, 150, "#fef9c3", "#ca8a04", "#713f12"))
cells.append(rect("sequential", "<b>Phase 2: sequential departments</b>\n_SEQUENTIAL_AFTER = [BuyerDepartment, ContactDepartment]\nFor each department:\n- emit department_assigned\n- evaluate_run_conditions(...)\n- skipped tasks become status='skipped'\n- runnable tasks execute in order", LX[2] + 20, 1540, 430, 180, "#dbeafe", "#2563eb", "#1e3a8a"))
cells.append(rect("contact_enrich", "<b>Contact dependency handling</b>\nWhen department == ContactDepartment:\nread sections['market_network']\nextract buyer_candidates from downstream_buyers, service_providers, cross_industry_buyers\nadd buyer_candidates to current_section when available", LX[2] + 20, 1750, 430, 160, "#f0fdf4", "#16a34a", "#14532d"))
cells.append(rect("resolution", "<b>First-round resolution</b>\nResolutionController().classify(\n  sections, department_packages, answer_matrix, task_statuses\n)\n\nemit {status: 'first_round_resolution', ...}\nSynthesis intentionally not run here.", LX[2] + 20, 1960, 430, 150, "#fee2e2", "#dc2626", "#7f1d1d"))

# Department lane
cells.append(rect("dept_company", "<b>CompanyDepartment</b>\nAG2 DepartmentRuntime.run(...)\nReceives isolated working-set memory in parallel phase\nReturns section_payload, messages, package", LX[3] + 20, 720, 340, 130, "#dcfce7", "#16a34a", "#14532d"))
cells.append(rect("dept_market", "<b>MarketDepartment</b>\nAG2 DepartmentRuntime.run(...)\nRuns concurrently with CompanyDepartment\nReturns industry_analysis / market evidence package", LX[3] + 20, 880, 340, 130, "#dcfce7", "#16a34a", "#14532d"))
cells.append(rect("dept_buyer", "<b>BuyerDepartment</b>\nRuns after Company + Market admission\nUses current_sections snapshot\nBuilds peer/buyer/redeployment package", LX[3] + 20, 1540, 340, 130, "#dcfce7", "#16a34a", "#14532d"))
cells.append(rect("dept_contact", "<b>ContactDepartment</b>\nRuns after BuyerDepartment\nMay receive buyer_candidates from admitted market_network\nBuilds contact_intelligence package", LX[3] + 20, 1740, 340, 140, "#dcfce7", "#16a34a", "#14532d"))

# State lane
cells.append(rect("active_tasks", "<b>RunContext.active_tasks</b>\nEvery non-synthesis assignment is recorded as assigned. Later status updates overwrite matching task_key.", LX[4] + 20, 520, 320, 120, "#fef9c3", "#ca8a04", "#713f12"))
cells.append(rect("structured_state", "<b>Structured runtime artifacts</b>\nAnswerMatrixUpdate\nGapCandidate\nEvidencePacket\nare validated and appended to short_term_memory.\nanswer_matrix entries receive status, answer, notes, source_tasks.", LX[4] + 20, 1110, 320, 170, "#fef9c3", "#ca8a04", "#713f12"))
cells.append(rect("sections_state", "<b>Admission-controlled outputs</b>\naccepted -> section payload visible\naccepted_with_gaps -> section payload with _admission marker\nrejected -> BlockedArtifact section\nRaw package is always preserved in department_packages.", LX[4] + 20, 1310, 320, 170, "#fef9c3", "#ca8a04", "#713f12"))
cells.append(rect("answer_matrix", "<b>Task status -> answer matrix</b>\naccepted -> answered\ndegraded/blocked -> partially_answered\nskipped -> blocked\n\ncompleted_backlog records task_key, label, target_section, status.", LX[4] + 20, 1540, 320, 160, "#fef9c3", "#ca8a04", "#713f12"))
cells.append(rect("token_guard", "<b>Token guardrails inside loop</b>\nAfter sequential departments, usage_totals.total_tokens is checked against HARD_TOKEN_CAP and SOFT_TOKEN_BUDGET.\nHard cap breaks remaining departments.", LX[4] + 20, 1740, 320, 150, "#fee2e2", "#dc2626", "#7f1d1d"))
cells.append(rect("first_pass_state", "<b>Runner writes first-pass state</b>\nresolution_state['first_round_resolution'] = first_round_resolution\nresolution_state['auto_close'] = {triggered: False, max_questions: 4, attempted_questions: 0, stop_reason: 'not_required', remaining_public_gaps: []}", LX[4] + 20, 2130, 320, 190, "#fef9c3", "#ca8a04", "#713f12"))
cells.append(rect("checkpoint", "<b>Checkpoint: after_first_pass</b>\n_write_checkpoint(run_dir, 'after_first_pass', run_context)\n\nStep 2 boundary: returns FirstPassResult.\nNext step is auto-close decision / closure.", LX[4] + 20, 2350, 320, 160, "#fee2e2", "#dc2626", "#7f1d1d"))

# Edges
cells += [
    edge("e1", "step1_ready", "first_pass_entry"),
    edge("e2", "first_pass_entry", "loop_init"),
    edge("e3", "loop_init", "assignments"),
    edge("e4", "assignments", "opening"),
    edge("e5", "opening", "active_tasks", "records"),
    edge("e6", "opening", "parallel_assign"),
    edge("e7", "parallel_assign", "dept_company", "submit", "#16a34a", pts=[(1300, 765)]),
    edge("e8", "parallel_assign", "dept_market", "submit", "#16a34a", pts=[(1300, 945)]),
    edge("e9", "dept_company", "parallel_review", "package", "#16a34a", pts=[(1320, 785), (1320, 1200)]),
    edge("e10", "dept_market", "parallel_review", "package", "#16a34a", pts=[(1320, 945), (1320, 1200)]),
    edge("e11", "parallel_review", "structured_state", "validates"),
    edge("e12", "parallel_review", "sections_state", "admission"),
    edge("e13", "parallel_review", "merge"),
    edge("e14", "merge", "sequential"),
    edge("e15", "sequential", "dept_buyer", "run", "#16a34a"),
    edge("e16", "dept_buyer", "contact_enrich", "market_network available", "#16a34a", pts=[(1320, 1605), (1320, 1830)]),
    edge("e17", "contact_enrich", "dept_contact", "buyer_candidates", "#16a34a"),
    edge("e18", "sequential", "answer_matrix", "skips/statuses"),
    edge("e19", "dept_contact", "resolution", "final dept package", "#16a34a", pts=[(1320, 1810), (1320, 2025)]),
    edge("e20", "resolution", "runner_collect", "loop result"),
    edge("e21", "runner_collect", "runner_budget"),
    edge("e22", "runner_budget", "first_pass_state"),
    edge("e23", "first_pass_state", "checkpoint"),
    edge("e24", "sequential", "token_guard", "checks"),
]

xml_cells = "\n        ".join(cells)
xml = f"""<mxfile host=\"65bd71144e\">
  <diagram id=\"runtime-step2\" name=\"Runtime Step 2 - First Pass\">
    <mxGraphModel dx=\"1400\" dy=\"1000\" grid=\"1\" gridSize=\"10\" guides=\"1\" tooltips=\"1\" connect=\"1\" arrows=\"1\" fold=\"1\" page=\"1\" pageScale=\"1\" pageWidth=\"{PAGE_W}\" pageHeight=\"{PAGE_H}\" math=\"0\" shadow=\"0\">
      <root>
        <mxCell id=\"0\"/>
        <mxCell id=\"1\" parent=\"0\"/>
        {xml_cells}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""

root = ET.fromstring(xml)  # nosec B314
ids = {cell.attrib["id"] for cell in root.iter("mxCell") if "id" in cell.attrib}
for cell in root.iter("mxCell"):
    if cell.attrib.get("edge") == "1":
        src = cell.attrib.get("source")
        tgt = cell.attrib.get("target")
        if src not in ids or tgt not in ids:
            raise ValueError(f"Invalid edge {cell.attrib.get('id')}: {src} -> {tgt}")
OUT.write_text(xml, encoding="utf-8")
print("XML valid")
print(f"Written to {OUT}")
print(f"Page: {PAGE_W} x {PAGE_H} px")
print(f"Nodes: {xml.count('vertex=')}; Edges: {xml.count('edge=')}")

