"""Local-first ERP consulting deliverable generator.

Rules-based assistance, not independent ERP implementation or certification.
All project details must come from the customer's explicit JSON input.
No network, no credentials, no production writes, no LLM API calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

_ROLES = ["Executive sponsor", "Finance owner", "Operations owner", "IT administrator", "Data owner", "Training lead"]


def load_project(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".json" or path.stat().st_size > 262144:
        raise ValueError("Input must be an existing .json project file no larger than 256 KB")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Project file must be a JSON object")
    for key in ("project_name", "company_name", "target_system"):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            raise ValueError(f"Missing nonempty string: {key}")
    for key in ("source_systems", "workflows", "data_objects", "pain_points"):
        if key in obj and (not isinstance(obj[key], list) or any(not isinstance(x,str) or not x.strip() for x in obj[key])):
            raise ValueError(f"{key} must be a list of nonempty strings")
    if "go_live_date" in obj and obj["go_live_date"]:
        try: date.fromisoformat(obj["go_live_date"])
        except (ValueError, TypeError): raise ValueError("go_live_date must be YYYY-MM-DD")
    for key in ("users", "locations"):
        if key in obj and (type(obj[key]) is not int or obj[key] < 0):
            raise ValueError(f"{key} must be a nonnegative integer")
    if "owners" in obj and not isinstance(obj["owners"], dict):
        raise ValueError("owners must be an object")
    if "financial" in obj and not isinstance(obj["financial"], dict):
        raise ValueError("financial must be an object")
    if "cutover" in obj:
        validate_cutover(obj["cutover"])
    if "integrations" in obj:
        if not isinstance(obj["integrations"], list) or any(
            not isinstance(i,dict) or not all(isinstance(i.get(k),str) and i[k].strip() for k in ("from", "to", "data")) for i in obj["integrations"]):
            raise ValueError("integrations must be objects containing from, to, data")
    return obj


CUTOVER_OWNER_FIELDS = (
    ("cutover_owner", "Cutover lead (runs the window)"),
    ("backup_owner", "Backup owner (takes and verifies the pre-cutover backup)"),
    ("rollback_owner", "Rollback decision owner (may order a rollback)"),
    ("go_no_go_approver", "Go/no-go approver (business authority)"),
    ("business_signoff_owner", "Business owner signing off post-load reconciliation"),
)
CUTOVER_TEXT_FIELDS = ("backup_method", "rollback_trigger", "rollback_method", "timezone")
CUTOVER_TIME_FIELDS = ("window_start", "window_end", "backup_taken_by", "rollback_deadline")
_PLACEHOLDERS = {"", "to assign", "tbd", "tba", "unknown", "n/a", "na", "none", "?"}


def _named(value):
    return isinstance(value, str) and value.strip().lower() not in _PLACEHOLDERS and len(value.strip()) >= 2


def _dt(value, key):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"cutover.{key} must be an ISO date-time like 2027-04-14T18:00") from exc


def validate_cutover(c):
    if not isinstance(c, dict):
        raise ValueError("cutover must be an object")
    allowed = {k for k, _ in CUTOVER_OWNER_FIELDS} | set(CUTOVER_TEXT_FIELDS) | set(CUTOVER_TIME_FIELDS)
    if set(c) - allowed:
        raise ValueError("Unknown cutover field(s): " + ", ".join(sorted(set(c) - allowed)))
    for k, v in c.items():
        if not isinstance(v, str) or len(v) > 200:
            raise ValueError(f"cutover.{k} must be text up to 200 characters")
    times = {k: _dt(c[k], k) for k in CUTOVER_TIME_FIELDS if c.get(k)}
    def cmp(a, b):
        x, y = times[a], times[b]
        if (x.tzinfo is None) != (y.tzinfo is None):
            raise ValueError("cutover times must all include, or all omit, a UTC offset")
        return x < y
    if "window_start" in times and "window_end" in times and not cmp("window_start", "window_end"):
        raise ValueError("cutover.window_end must be after window_start")
    if "rollback_deadline" in times:
        if "window_start" in times and cmp("rollback_deadline", "window_start"):
            raise ValueError("cutover.rollback_deadline must be inside the cutover window")
        if "window_end" in times and cmp("window_end", "rollback_deadline"):
            raise ValueError("cutover.rollback_deadline must be inside the cutover window")
    if "backup_taken_by" in times and "window_start" in times and cmp("window_start", "backup_taken_by"):
        raise ValueError("cutover.backup_taken_by must be no later than window_start")
    return c


def cutover_readiness(p):
    """Which backup/rollback/cutover-window facts are still missing (named humans only)."""
    c = p.get("cutover") or {}
    missing = [label for key, label in CUTOVER_OWNER_FIELDS if not _named(c.get(key))]
    missing += [f"{k} (time)" for k in ("window_start", "window_end", "backup_taken_by", "rollback_deadline") if not c.get(k)]
    missing += [k for k in ("backup_method", "rollback_trigger", "rollback_method") if not _named(c.get(k))]
    return {"complete": not missing, "missing": missing}


def _bullets(items):
    return "\n".join("- " + str(x).replace("\n", " ") for x in items) + "\n"


def assess_project(p):
    missing = [k for k in ("source_systems", "workflows", "data_objects", "go_live_date", "owners", "financial") if not p.get(k)]
    risk = []
    controls = p.get("controls") or {}
    if not isinstance(controls,dict): controls = {}
    if len(p.get("source_systems", [])) > 2: risk.append("Multiple legacy sources increase matching and reconciliation complexity")
    if len(p.get("data_objects", [])) > 5: risk.append("Large data-object scope requires staged trial loads")
    if p.get("users", 0) > 100: risk.append("Broad end-user adoption requires role-specific UAT and training")
    if p.get("locations", 0) > 1: risk.append("Multi-location cutover and process harmonization need review")
    if controls.get("regulated_data"): risk.append("Regulated data: verify legal, retention, and security requirements with specialists")
    if controls.get("multi_currency"): risk.append("Multi-currency: independently reconcile exchange rates, base amounts, and ledgers")
    if not p.get("go_live_date"): risk.append("No confirmed go-live date; cutover schedule remains relative")
    if missing: risk.append("Discovery information missing; scope and price cannot be finalized")
    questions = []
    if "source_systems" in missing: questions.append("Which systems currently hold customers, invoices, inventory, and GL balances?")
    if "data_objects" in missing: questions.append("Which master and transaction records must be migrated?")
    if "workflows" in missing: questions.append("Which end-to-end workflows must be demonstrated in UAT?")
    if "owners" in missing: questions.append("Who owns each data source and who has approval authority?")
    if "financial" in missing: questions.append("What are current manual hours, fully loaded rate, and implementation costs?")
    questions += ["Which account-specific fields, roles, taxes, and subsidiaries must be supported?",
                  "What are the backup, rollback, and acceptable downtime requirements?",
                  "Which vendor sandbox or test tenant can be used for trial imports?"]
    return {"project": p["project_name"], "missing_discovery_fields": missing, "risk_flags": risk,
            "discovery_questions": questions, "assessment": "PRELIMINARY: no vendor configuration or production data was inspected"}


def athena(p):
    a = assess_project(p)
    sections = [f"# Athena — ERP discovery and roadmap: {p['project_name']}",
                f"Customer: {p['company_name']} | Proposed target: {p['target_system']} | Industry: {p.get('industry', 'not supplied')}\n",
                "## Systems in scope", _bullets(p.get("source_systems", []) or ["NOT PROVIDED — obtain source systems"]),
                "## Critical workflows", _bullets(p.get("workflows", []) or ["NOT PROVIDED — interview process owners"]),
                "## Discovered pain points", _bullets(p.get("pain_points", []) or ["NOT PROVIDED"]),
                "## Migration objects", _bullets(p.get("data_objects", []) or ["NOT PROVIDED"]),
                "## Risks to validate", _bullets(a["risk_flags"] or ["No risk indicators from the submitted questionnaire; not a risk clearance"]),
                "## Questions before agreeing to scope", _bullets(a["discovery_questions"]),
                "## Responsible roles", _bullets([f"{r}: {p.get('owners',{}).get(r, 'TO ASSIGN')}" for r in _ROLES]),
                "## Suggested phase gates", _bullets(["1. Approve requirements and data inventory", "2. Approve mapping spec and technical design", "3. Validate clean imports in a vendor sandbox", "4. Complete critical-workflow UAT and reconciliation", "5. Obtain written cutover, backup and rollback approval", "6. Run post-launch hypercare with an accountable owner"]),
                "This document is generated from customer-entered facts; it does not verify actual system configuration or regulatory compliance.\n"]
    return "\n".join(sections)


def daedalus(p):
    lines = [f"# Daedalus — Integration design draft: {p['project_name']}",
             "Draft only: vendor API permissions, schemas, limits, entity mappings, and idempotency must be verified in each tenant.\n",
             "| From | To | Data / business event | Implementation pattern | Approval |", "|---|---|---|---|---|"]
    integs = p.get("integrations") or []
    if not integs:
        lines.append("| Not supplied | Not supplied | DISCOVERY REQUIRED | No connector designed | Architecture owner |")
    for i in integs:
        # Structured input is not interpreted as a certified vendor integration.
        values = [i[k].replace("|", "\\|").replace("\n", " ") for k in ("from", "to", "data")]
        lines.append(f"| {values[0]} | {values[1]} | {values[2]} | Design API or approved file transfer after tenant review | Architecture owner |")
    lines += ["\n## Design review checklist", _bullets(["Read-only credential scopes during exploration", "Field ownership and system of record", "Identity, lookup keys, and duplicate treatment", "Retry, dead-letter, idempotency and rate limits", "Sensitive-data and encryption boundaries", "Audit logs and operational alert ownership", "Sandbox reconciliation before production permission request", "Documented rollback and error handling"])]
    return "\n".join(lines)


_STEP_TEMPLATES = {
    "happy path": (
        ("Prepare identified test records for {w} in the test tenant", "Test records exist and are listed in the evidence"),
        ("Execute {w} end to end as the responsible business role", "Every transaction completes without error"),
        ("Compare resulting records and ledger/data effects with the expected values", "Results match the expected values; differences recorded"),
    ),
    "invalid/missing input": (
        ("Submit {w} with a required value missing", "System rejects the entry with a clear message; no partial record"),
        ("Submit {w} with an invalid reference (unknown customer/item/account)", "Entry is rejected or routed for correction; nothing silently changed"),
    ),
    "roles and exception handling": (
        ("Complete {w} as an authorized role", "Task completes and is attributed to that user"),
        ("Attempt {w} as an unauthorized role", "Access is blocked"),
        ("Trigger a failure in {w} and resolve it", "Failure is visible, resolvable, and leaves an audit trail"),
    ),
}


def apollo(p):
    workflows = p.get("workflows") or ["UNSPECIFIED WORKFLOW — discovery needed"]
    cases = []
    for n, name in enumerate(workflows, 1):
        for j, (scenario, expected) in enumerate((
            ("happy path", "Business owner confirms expected state transitions and ledger/data effects"),
            ("invalid/missing input", "System rejects or correctly routes invalid data without silent corruption"),
            ("roles and exception handling", "Authorized roles complete task; unauthorized access blocked; failures can be resolved")), 1):
            case_id = f"UAT-{n:02}-{j}"
            steps = [{"step_id": f"{case_id}.S{k}", "action": a.format(w=name), "expected": e.format(w=name)}
                     for k, (a, e) in enumerate(_STEP_TEMPLATES[scenario], 1)]
            cases.append({"case_id": case_id, "workflow": name, "scenario": scenario,
                          "expected": expected, "steps": steps, "owner": "TO ASSIGN", "status": "NOT RUN",
                          "evidence": "NOT PROVIDED"})
    text = [f"# Apollo — User acceptance testing: {p['project_name']}",
            "Test cases are drafts. Run them against a test tenant and retain independent evidence.\n",
            "| Case | Workflow | Scenario | Expected evidence | Status |", "|---|---|---|---|---|"]
    for c in cases:
        text.append("| " + " | ".join(str(c[k]).replace("|", "\\|").replace("\n", " ") for k in ("case_id", "workflow", "scenario", "expected", "status")) + " |")
    text += ["\n## Test steps", ""]
    for c in cases:
        text += [f"### {c['case_id']} — {c['workflow']}: {c['scenario']}".replace("\n", " ").replace("|", "\\|"), "",
                 "| Step | Action | Expected result | Result | Executed at | Evidence |", "|---|---|---|---|---|---|"]
        for st in c["steps"]:
            cells = [str(st[k]).replace("|", "\\|").replace("\n", " ") for k in ("step_id", "action", "expected")]
            text.append(f"| {cells[0]} | {cells[1]} | {cells[2]} | NOT RUN | | |")
        text.append("")
    text += ["## Exit criteria", "All critical flows passed with signed business-owner evidence, zero unresolved critical defects, and documented reconciliation. An AI-generated test document is not itself proof of testing.\n"]
    return "\n".join(text), cases


def chronos(p):
    d = date.fromisoformat(p["go_live_date"]) if p.get("go_live_date") else None
    steps = [(-21, "Confirm source freeze strategy, backups, data owner and rollback decision-maker", "Data owner"),
             (-14, "Run migration rehearsals in sandbox, confirm record-count and value reconciliation", "IT administrator"),
             (-10, "Resolve critical data exceptions and confirm integrations under test", "Operations owner"),
             (-7, "Business owners execute and approve UAT; verify role-based permissions", "Operations owner"),
             (-3, "Validate backups, recovery test, communications and rollback procedures", "IT administrator"),
             (-1, "Obtain explicit human go/no-go sign-off; freeze agreed source changes", "Executive sponsor"),
             (0, "Human-led cutover: execute approved data loads, reconcile and monitor", "IT administrator"),
             (1, "Inspect failed transactions, tickets and critical workflows", "Operations owner"),
             (7, "Hypercare review and transition to managed-service ownership", "Executive sponsor")]
    txt = [f"# Chronos — Cutover runbook: {p['project_name']}",
           "No production changes are performed by this document. Dates are planning placeholders, not vendor-confirmed windows.\n",
           "| Timing | Required task | Accountable role | Status |", "|---|---|---|---|"]
    for delta, task, role in steps:
        timing = (d+timedelta(days=delta)).isoformat() if d else f"T{delta:+d} days"
        txt.append(f"| {timing} | {task} | {role} | NOT CONFIRMED |")
    c = p.get("cutover") or {}
    tz = c.get("timezone") or "timezone NOT SET"
    def val(key):
        v = c.get(key, "")
        return str(v).replace("|", "\\|").replace("\n", " ") if _named(v) or (key in CUTOVER_TIME_FIELDS and v) else "**TO ASSIGN — required**"
    ready = cutover_readiness(p)
    txt += ["\n## Backup, rollback and cutover window",
            f"All times {tz}. Owners must be named people, not roles; this document does not verify them.\n",
            "| Item | Value |", "|---|---|",
            f"| Cutover window start | {val('window_start')} |", f"| Cutover window end | {val('window_end')} |",
            f"| Backup completed and verified no later than | {val('backup_taken_by')} |",
            f"| Backup method | {val('backup_method')} |",
            f"| Rollback trigger (what forces a rollback) | {val('rollback_trigger')} |",
            f"| Rollback method | {val('rollback_method')} |",
            f"| Rollback deadline (point of no return) | {val('rollback_deadline')} |", "",
            "| Accountable owner | Name |", "|---|---|",
            *[f"| {label} | {val(key)} |" for key, label in CUTOVER_OWNER_FIELDS],
            "", ("**Cutover facts complete** (still requires human verification)." if ready["complete"]
                 else "**Incomplete — missing:** " + "; ".join(ready["missing"]))]
    txt += ["\n## Go/no-go gate", _bullets(["Approved data mapping and ownership", "Successful test import and financial reconciliation", "UAT passes with critical issues addressed", "Documented and tested rollback option", "Signed release and downtime authorization", "Named on-call support and escalation chain"]),
            "**Default: NO GO until owners independently verify evidence.**\n"]
    return "\n".join(txt)


def hestia(p):
    w = p.get("workflows") or ["Workflow discovery required"]
    return "\n".join([f"# Hestia — Role-based training plan: {p['project_name']}",
        "Curriculum draft only; final training must reflect the client's actual configured system.\n",
        "## Learning tracks", _bullets(["End users: perform daily transactions and resolve common errors", "Managers: approve exceptions and review KPI dashboards", "Finance: control periods, reconcile balances and handle reporting", "IT administrators: permissions, integrations, escalation and audit logging"]),
        "## Hands-on exercises linked to actual workflows", _bullets([f"Demonstrate {x}; process a valid example, then an exception, then a role-permission check" for x in w]),
        "## Sign-off evidence", _bullets(["Training attendance and role assignment", "Practice transactions completed in sandbox", "Accuracy check of user-facing job aids", "Human trainer/manager sign-off and support contacts"]),
        "Do not use live customer or employee data in training without authorization.\n"])


def argus(p):
    return "\n".join([f"# Argus — Post-launch support and monitoring: {p['project_name']}",
       "No telemetry connection exists in this package. Targets below must be agreed with the customer.\n",
       "## Suggested signal catalog", _bullets(["Integration failures and retries (requires instrumentation)", "New import rejects and data-quality drift", "Financial reconciliation discrepancies", "Failed workflows, permissions and login problems", "Ticket volume, response time, resolution time", "User adoption and successful critical transaction completion"]),
       "## Severity playbook", _bullets(["P1 — Financial or business operations materially blocked: page named human responder", "P2 — Significant degraded workflow: open accountable ticket with reproduction steps", "P3 — Noncritical usability/reporting problem: prioritize in improvement backlog"]),
       "## Closure evidence", _bullets(["Incident identifier and timestamps", "Customer impact and root cause", "Change approval if applicable", "Verified fix and regression test", "Customer acceptance and prevention action"]),
       "Do not treat model-generated severity or root cause as verified evidence.\n"])


def _dec(p, key):
    try:
        x = Decimal(str((p.get("financial") or {}).get(key, "")))
        if not x.is_finite() or x < 0: return None
        return x
    except (InvalidOperation, TypeError, ValueError): return None


def plutus(p):
    hours = _dec(p,"manual_hours_per_month")
    rate = _dec(p,"fully_loaded_hourly_rate")
    license_cost = _dec(p,"subscription_per_month")
    one_time = _dec(p,"setup_cost")
    if any(v is None for v in (hours, rate, license_cost, one_time)):
        return "\n".join([f"# Plutus — Savings model: {p['project_name']}",
          "MISSING INPUTS. Populate financial.manual_hours_per_month, fully_loaded_hourly_rate, subscription_per_month, and setup_cost with verified estimates.\n",
          "No savings or ROI are asserted without stated assumptions."])
    lines = [f"# Plutus — Scenario-based savings model: {p['project_name']}",
             "Planning scenarios only. These do not represent validated productivity gains or a quote.\n",
             f"Inputs: {hours} manual hours/month × ${rate}/hour, ${license_cost}/month subscription, ${one_time} setup.\n",
             "| Hypothetical work hours reduced | Monthly gross value | Monthly net after subscription | First-year net after setup |", "|---:|---:|---:|---:|"]
    for reduction in (Decimal("0.10"),Decimal("0.25"),Decimal("0.40")):
        gross = (hours*rate*reduction)
        monthly = gross - license_cost
        annual = monthly*12 - one_time
        lines.append(f"| {reduction:.0%} | ${gross:,.2f} | ${monthly:,.2f} | ${annual:,.2f} |")
    lines.append("\nMeasure actual time saved in paid pilots. Do not substitute this model for observed outcomes.")
    return "\n".join(lines)


ZEUS_NO_GO = "NO GO — NOT VERIFIED"
ZEUS_EVIDENCE_COMPLETE = "EVIDENCE COMPLETE — HUMAN GO/NO-GO DECISION REQUIRED"
# Fields in a project file that look like approvals. They are customer- or model-
# entered text, never evidence, and Zeus ignores them.
_ASSERTION_KEYS = ("go_live", "go_live_approved", "approved", "approval", "approvals", "decision", "zeus",
                   "uat_passed", "uat_complete", "reconciled", "signed_off", "signoff", "status", "ready")


def go_live_gate(p, evidence=None):
    """Zeus: conservative release gate.

    Software never outputs GO. The best possible outcome is EVIDENCE COMPLETE, and
    only when every gate is satisfied by file-backed evidence collected from the
    project folder (see project_summary.collect_evidence). Drafts, generated
    packs and any approval-looking text in the project JSON are ignored.
    """
    a = assess_project(p)
    ignored = sorted(k for k in _ASSERTION_KEYS if k in p)
    ev = evidence if isinstance(evidence, dict) and evidence.get("_source") == "files" else {}
    cut = cutover_readiness(p)
    gates = [
        ("Requirements approved by accountable owner", None, "Record outside Olympus (no identity-backed approval ledger yet)"),
        ("Mapping decisions confirmed for current source files", ev.get("mapping_confirmed"), ev.get("mapping_detail")),
        ("Mapping spec signed off (Themis)", ev.get("themis_signed_off"), ev.get("themis_detail")),
        ("Latest build has zero import-breaking errors", ev.get("build_clean"), ev.get("build_detail")),
        ("Trial load reconciled (Poseidon)", ev.get("reconciled"), ev.get("reconcile_detail")),
        ("All UAT cases PASS with current evidence (Clio)", ev.get("uat_passed"), ev.get("uat_detail")),
        ("Backup, rollback and cutover window with named owners (Chronos)", cut["complete"] if ev else None,
         "Missing: " + "; ".join(cut["missing"]) if cut["missing"] else "Complete"),
        ("No open critical/high incidents (Argus)", ev.get("no_open_critical"), ev.get("incident_detail")),
    ]
    rows = [{"gate": g, "status": "VERIFIED" if ok is True else "UNVERIFIED" if ok is None else "FAILED",
             "detail": detail or ("No file-backed evidence collected" if not ev else "")} for g, ok, detail in gates]
    # The first gate is always external, so software alone can never complete the gate list.
    software_gates = rows[1:]
    complete = bool(ev) and all(r["status"] == "VERIFIED" for r in software_gates)
    return {"project": p["project_name"],
            "decision": ZEUS_EVIDENCE_COMPLETE if complete else ZEUS_NO_GO,
            "required_evidence": rows,
            "external_gates": ["Requirements approved by accountable owner", "Human go-live authorization and staffed hypercare"],
            "ignored_assertions": ignored,
            "missing_discovery_fields": a["missing_discovery_fields"],
            "message": "This tool cannot grant release approval. Drafts and model or customer assertions are never evidence. "
                       "A named human must review the evidence and authorize production outside this software."}


def pack(p, dest):
    dest = Path(dest)
    if dest.exists():
        raise ValueError("Output directory already exists; use a new empty project pack path")
    dest.mkdir(parents=True, exist_ok=False)
    uat_text, uat_json = apollo(p)
    docs = {"01_athena_discovery.md": athena(p), "02_daedalus_integration_design.md": daedalus(p),
            "03_apollo_uat.md": uat_text, "04_chronos_cutover.md": chronos(p),
            "05_hestia_training.md": hestia(p), "06_argus_hypercare.md": argus(p),
            "07_plutus_roi.md": plutus(p), "08_zeus_go_live_gate.json": json.dumps(go_live_gate(p), indent=2),
            "09_apollo_uat_cases.json": json.dumps(uat_json, indent=2),
            "00_project_assessment.json": json.dumps(assess_project(p), indent=2)}
    for filename, contents in docs.items():
        (dest / filename).write_text(contents + "\n", encoding="utf-8")
    return {"project": p["project_name"], "output": str(dest), "files": list(docs),
            "go_live": "NO GO — NOT VERIFIED", "note": "Planning documents only; no live ERP integration performed"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="olympus-erp", description="Local draft ERP implementation agent toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assess"); a.add_argument("project")
    a = sub.add_parser("pack"); a.add_argument("project"); a.add_argument("-o", "--output", required=True)
    args = ap.parse_args(argv)
    try:
        p = load_project(args.project)
        result = assess_project(p) if args.cmd == "assess" else pack(p, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        ap.exit(2, f"olympus-erp: {exc}\n")

if __name__ == "__main__":
    raise SystemExit(main())
