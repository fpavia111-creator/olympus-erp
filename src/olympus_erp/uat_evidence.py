"""Apollo/Clio: local UAT execution evidence register (scenario steps + manual results).

A receipt means a *person claimed* a result, when it was executed, and attached a
file and/or an evidence link. It does not verify identity, vendor execution, link
contents or content quality. Records are bound to the project file (the UAT spec),
to the exact case definition including its steps, and to the evidence file bytes;
any change marks the record stale and forces review.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .erp_agents import load_project, apollo

RESULTS = {"PASS", "FAIL", "BLOCKED"}
STEP_RESULTS = RESULTS | {"NOT RUN"}
_LINK = re.compile(r"https?://[^\s<>\"']{3,490}")


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case_fingerprint(case):
    core = {k: case[k] for k in ("case_id", "workflow", "scenario", "expected", "steps")}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


def _target(project_path):
    p = Path(project_path).resolve()
    return p.with_suffix(".uat-evidence.json")


def _load(project_path):
    path = _target(project_path)
    if not path.exists():
        return {"project_sha256": fingerprint(project_path), "results": {}}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("results"), dict):
        raise ValueError("Invalid UAT register")
    return obj


def _parse_time(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("executed_at must be an ISO 8601 date-time")
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("executed_at must be an ISO 8601 date-time, e.g. 2026-10-19T14:30-05:00") from exc
    if t.tzinfo is None:
        t = t.astimezone()  # interpret as the local time of the machine running Olympus
    if t > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("executed_at is in the future")
    return t.isoformat()


def _record_state(project_path, case, r):
    """Return (result, stale_reason) for one stored record."""
    result = r.get("result", "NOT RUN")
    if not r or result not in RESULTS:
        return "NOT RUN", None
    if r.get("case_sha256") and r["case_sha256"] != case_fingerprint(case):
        return "STALE EVIDENCE", "Test case or its steps changed after the result was recorded"
    if r.get("evidence"):
        proof = (project_path.parent / str(r.get("evidence", ""))).resolve()
        if not proof.is_relative_to(project_path.parent) or not proof.is_file() or \
           proof.stat().st_size > 60_000_000 or fingerprint(proof) != r.get("evidence_sha256"):
            return "STALE EVIDENCE", "Evidence file changed or missing"
    elif not r.get("evidence_link"):
        return "STALE EVIDENCE", "No evidence attached"
    return result, None


def status(project_path):
    project_path = Path(project_path).resolve()
    project = load_project(project_path)
    cases = apollo(project)[1]
    obj = _load(project_path)
    current = fingerprint(project_path)
    stale = obj.get("project_sha256") != current
    results = obj.get("results", {})
    statuses = []
    for case in cases:
        r = {} if stale else results.get(case["case_id"], {})
        result, why = _record_state(project_path, case, r)
        recorded_steps = r.get("steps") or {}
        statuses.append({"case_id": case["case_id"], "workflow": case["workflow"], "scenario": case["scenario"],
                         "result": result, "stale_reason": why, "reviewer": r.get("reviewer"),
                         "executed_at": r.get("executed_at"), "recorded_at": r.get("recorded_at"),
                         "evidence": r.get("evidence"), "evidence_link": r.get("evidence_link"),
                         "evidence_link_verified": False if r.get("evidence_link") else None,
                         "notes": r.get("notes"),
                         "steps": [{**st, "result": recorded_steps.get(st["step_id"], "NOT RUN") if r else "NOT RUN"}
                                   for st in case["steps"]]})
    passed = sum(x["result"] == "PASS" for x in statuses)
    return {"project": project["project_name"], "project_sha256": current,
            "stale": stale, "stale_reason": "Project/UAT spec changed; all earlier results need re-review" if stale else None,
            "total": len(statuses), "passed": passed,
            "failed": sum(x["result"] == "FAIL" for x in statuses),
            "blocked": sum(x["result"] == "BLOCKED" for x in statuses),
            "not_run": sum(x["result"] == "NOT RUN" for x in statuses),
            "stale_evidence": sum(x["result"] == "STALE EVIDENCE" for x in statuses),
            "file_evidenced_passes": sum(x["result"] == "PASS" and bool(x["evidence"]) for x in statuses),
            "all_pass_claimed": bool(statuses) and passed == len(statuses) and not stale,
            "cases": statuses,
            "caveat": "Self-attested local evidence only, not independently validated test execution or go-live approval. Evidence links are recorded, not fetched or verified."}


def record(project_path, case_id, result, reviewer, evidence_path=None, workspace=None, *,
           executed_at=None, evidence_link=None, step_results=None, notes=None):
    project_path = Path(project_path).resolve()
    root = Path(workspace if workspace is not None else project_path.parent).resolve()
    if not project_path.is_relative_to(root):
        raise ValueError("Project must stay inside the workspace")
    evidence = None
    if evidence_path is not None:
        evidence = Path(evidence_path).resolve()
        if not evidence.is_relative_to(project_path.parent):
            raise ValueError("Project and evidence must stay in same project folder inside workspace")
        if not evidence.is_file() or evidence.stat().st_size > 60_000_000:
            raise ValueError("Evidence file missing or too large")
        if evidence == project_path or evidence == _target(project_path):
            raise ValueError("Project/receipt file is not valid UAT evidence")
    link = None
    if evidence_link not in (None, ""):
        if not isinstance(evidence_link, str) or not _LINK.fullmatch(evidence_link.strip()):
            raise ValueError("Evidence link must be a single http(s) URL up to 500 characters")
        link = evidence_link.strip()
    if evidence is None and link is None:
        raise ValueError("Attach an evidence file or an evidence link")
    if result not in RESULTS:
        raise ValueError("UAT result must be PASS, FAIL, or BLOCKED")
    if not isinstance(reviewer, str) or len(reviewer.strip()) < 2 or len(reviewer) > 120:
        raise ValueError("Explicit reviewer name required (2–120 characters)")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
        raise ValueError("Notes must be text up to 2000 characters")
    cases = {x["case_id"]: x for x in apollo(load_project(project_path))[1]}
    if case_id not in cases:
        raise ValueError("Unknown UAT case ID")
    case = cases[case_id]
    step_ids = [s["step_id"] for s in case["steps"]]
    steps = dict(step_results or {})
    if not isinstance(steps, dict) or set(steps) - set(step_ids):
        raise ValueError("Unknown step id(s) for " + case_id)
    if any(v not in STEP_RESULTS for v in steps.values()):
        raise ValueError("Step results must be PASS, FAIL, BLOCKED or NOT RUN")
    steps = {sid: steps.get(sid, "NOT RUN") for sid in step_ids}
    values = set(steps.values())
    if result == "PASS" and values != {"PASS"}:
        raise ValueError("A case can only PASS when every step is recorded as PASS")
    if result == "FAIL" and "FAIL" not in values:
        raise ValueError("A FAIL result needs at least one failed step")
    if result == "BLOCKED" and "BLOCKED" not in values:
        raise ValueError("A BLOCKED result needs at least one blocked step")
    when = _parse_time(executed_at)
    if when is None:
        raise ValueError("executed_at (when the test was actually run) is required")
    prev = _load(project_path)
    current = fingerprint(project_path)
    if prev.get("project_sha256") != current:
        prev = {"project_sha256": current, "results": {}}
    prev["results"][case_id] = {"result": result, "reviewer": reviewer.strip(), "executed_at": when,
            "case_sha256": case_fingerprint(case), "steps": steps,
            "evidence": str(evidence.relative_to(project_path.parent)) if evidence else None,
            "evidence_sha256": fingerprint(evidence) if evidence else None,
            "evidence_link": link, "notes": (notes or "").strip() or None,
            "recorded_at": datetime.now(timezone.utc).isoformat()}
    dest = _target(project_path)
    tmp = dest.with_suffix(".uat-tmp")
    tmp.write_text(json.dumps(prev, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return status(project_path)
