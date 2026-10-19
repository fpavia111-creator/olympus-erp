"""Project summary: one honest view of where a migration project stands.

Collected only from files in the project folder: source-file fingerprints,
confirmed mapping decisions, the latest Hermes build (target load counts and
exceptions), Poseidon reconciliations, Clio UAT records, Chronos cutover facts,
Argus incidents, and the resulting Zeus gate. Drafts are never evidence.

Project-folder layout (created by the dashboard; CLI users can follow it):
    project.json                      Athena/Chronos inputs (UAT spec for Clio)
    incoming/, reconciliation_inputs/ uploaded source/trial-load files
    *.toml (+ .mappings.json, .approval.json)  Hermes specs and decisions
    builds/<id>/manifest.json + report.json     Hermes builds
    reconciliations/<id>.json                    Poseidon results
    project.uat-evidence.json                    Clio register
    olympus_incidents.jsonl                      Argus project incidents
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import erp_agents, incidents, uat_evidence
from . import mapping as mapping_mod
from .signoff import status as themis_status

FILE_DIRS = ("incoming", "reconciliation_inputs", "uat_evidence")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest(items, key):
    items = [i for i in items if i and i.get(key)]
    return max(items, key=lambda i: i[key]) if items else None


def _builds(directory):
    out = []
    for manifest in sorted((directory / "builds").glob("*/manifest.json")):
        m = _json(manifest)
        report = _json(manifest.parent / "report.json")
        if m and report:
            out.append({**m, "id": manifest.parent.name, "report": report, "dir": manifest.parent})
    return out


def _reconciliations(directory):
    out = []
    for f in sorted((directory / "reconciliations").glob("*.json")):
        r = _json(f)
        if isinstance(r, dict):
            out.append({**r, "id": f.stem})
    return out


def collect_evidence(project_dir):
    directory = Path(project_dir).resolve()
    project_file = directory / "project.json"
    p = erp_agents.load_project(project_file)
    blockers = []
    files = []
    for sub in FILE_DIRS:
        for f in sorted((directory / sub).glob("*")) if (directory / sub).is_dir() else []:
            if f.is_file() and not f.is_symlink():
                files.append({"folder": sub, "file": f.name, "bytes": f.stat().st_size, "sha256": _sha(f)})

    # Hermes: latest build, re-checked against current mapping decisions and source bytes.
    ev = {"_source": "files"}
    build = _latest(_builds(directory), "built_at")
    loads = []
    if build:
        rep = build["report"]
        spec = (directory / build.get("spec", "")).resolve()
        m = mapping_mod.status(spec) if spec.is_file() and spec.is_relative_to(directory) else {"current": False, "reason": "Spec missing"}
        t = themis_status(spec) if spec.is_file() and spec.is_relative_to(directory) else {"approved": False, "reason": "Spec missing"}
        stale_sources = []
        for l in rep.get("loads", []):
            src = next((x for x in files if x["file"] == l.get("source")), None)
            if src is None or src["sha256"] != l.get("source_sha256"):
                stale_sources.append(l.get("source"))
            codes = {}
            for f in l.get("findings", []):
                if f["severity"] == "error":
                    codes[f["code"]] = codes.get(f["code"], 0) + 1
            loads.append({"name": l["name"], "template": l["template"], "source": l["source"],
                          "source_sha256": l.get("source_sha256"), "rows": l["rows"], "loadable": l["loadable"],
                          "rejected": l["rejected"], "warnings": l["warnings"],
                          "transformations": l.get("transformations", 0), "exceptions_by_code": codes})
        spec_changed = spec.is_file() and _sha(spec) != rep.get("spec_sha256")
        ev["mapping_confirmed"] = bool(m.get("current"))
        ev["mapping_detail"] = m.get("reason")
        ev["themis_signed_off"] = bool(t.get("approved"))
        ev["themis_detail"] = (t.get("reason") or "") + ("; signer name only, not identity-verified" if t.get("approved") else "")
        ev["build_clean"] = rep.get("status") == "READY" and not stale_sources and not spec_changed
        ev["build_detail"] = (f"{rep.get('status')}: {rep.get('loadable_rows')}/{rep.get('total_rows')} loadable, "
                              f"{rep.get('errors')} errors" + (f"; source changed since build: {stale_sources}" if stale_sources else "")
                              + ("; spec changed since build" if spec_changed else ""))
        if not m.get("current"): blockers.append(("Mapping", "Mapping decisions not current: " + str(m.get("reason"))))
        if not t.get("approved"): blockers.append(("Themis", "Mapping spec not signed off: " + str(t.get("reason"))))
        if rep.get("errors"): blockers.append(("Hermes", f"{rep['errors']} import-breaking errors in latest build"))
        if stale_sources or spec_changed: blockers.append(("Hermes", "Latest build is stale; rebuild after review"))
        if rep.get("unchecked_dependencies"): blockers.append(("Hermes", f"{len(rep['unchecked_dependencies'])} unverified relationships"))
    else:
        ev["mapping_confirmed"] = ev["themis_signed_off"] = ev["build_clean"] = None
        ev["build_detail"] = "No confirmed build yet"
        blockers.append(("Hermes", "No build from confirmed mappings yet"))

    # Poseidon
    rec = _latest(_reconciliations(directory), "recorded_at")
    if rec:
        changed = [side for side in ("source", "target")
                   if not (directory / "reconciliation_inputs" / str(rec.get(side))).is_file()
                   or _sha(directory / "reconciliation_inputs" / str(rec.get(side))) != rec.get(side + "_sha256")]
        ev["reconciled"] = rec.get("status") == "RECONCILED" and not changed
        ev["reconcile_detail"] = (f"{rec.get('status')}: {rec.get('matched_keys')} matched, {rec.get('different_keys')} different keys, "
                                  f"net variance {rec.get('net_variance')}" + (f"; input changed: {changed}" if changed else ""))
        if not ev["reconciled"]:
            blockers.append(("Poseidon", "Trial load not reconciled: " + ev["reconcile_detail"]))
    else:
        ev["reconciled"], ev["reconcile_detail"] = None, "No reconciliation recorded"
        blockers.append(("Poseidon", "No trial-load reconciliation yet"))

    # Clio
    uat = uat_evidence.status(project_file)
    ev["uat_passed"] = uat["all_pass_claimed"] and uat["stale_evidence"] == 0
    ev["uat_detail"] = (f"{uat['passed']}/{uat['total']} PASS, {uat['failed']} FAIL, {uat['blocked']} BLOCKED, "
                        f"{uat['not_run']} NOT RUN, {uat['stale_evidence']} stale")
    if not ev["uat_passed"]:
        blockers.append(("Clio", "UAT incomplete: " + ev["uat_detail"]))

    # Chronos
    cut = erp_agents.cutover_readiness(p)
    if not cut["complete"]:
        blockers.append(("Chronos", f"{len(cut['missing'])} cutover/backup/rollback facts missing"))

    # Argus (project-scoped queue)
    try:
        inc = incidents.listing(directory)
        open_tickets = [t for t in inc["tickets"] if t["status"] != "resolved"]
        crit = [t for t in open_tickets if t["severity"] in ("critical", "high")]
        ev["no_open_critical"] = not crit
        ev["incident_detail"] = f"{len(open_tickets)} open, {len(crit)} critical/high"
    except ValueError as exc:
        open_tickets, crit = [], []
        ev["no_open_critical"], ev["incident_detail"] = False, str(exc)
    for t in crit:
        blockers.append(("Argus", f"Open {t['severity']} incident {t['id']}: {t['title']}"))

    zeus = erp_agents.go_live_gate(p, ev)
    by_cat = {}
    for cat, _ in blockers:
        by_cat[cat] = by_cat.get(cat, 0) + 1
    return {"project": p["project_name"], "company": p["company_name"], "target_system": p["target_system"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_sha256": _sha(project_file),
            "open_blockers": len(blockers), "blockers_by_area": by_cat,
            "blockers": [{"area": c, "detail": d} for c, d in blockers],
            "source_files": files,
            "latest_build": ({"id": build["id"], "built_at": build["built_at"], "spec": build.get("spec"),
                              "status": build["report"].get("status"), "total_rows": build["report"].get("total_rows"),
                              "loadable_rows": build["report"].get("loadable_rows"), "errors": build["report"].get("errors"),
                              "warnings": build["report"].get("warnings"), "loads": loads} if build else None),
            "reconciliation": ({k: rec.get(k) for k in ("id", "recorded_at", "status", "source", "target", "source_sha256",
                                                         "target_sha256", "source_rows", "target_rows", "matched_keys",
                                                         "different_keys", "source_total", "target_total", "net_variance")}
                               if rec else None),
            "uat": {k: uat[k] for k in ("total", "passed", "failed", "blocked", "not_run", "stale_evidence", "stale")},
            "cutover": cut,
            "incidents": {"open": len(open_tickets), "critical_or_high": len(crit)},
            "zeus": {"decision": zeus["decision"], "gates": zeus["required_evidence"],
                     "ignored_assertions": zeus["ignored_assertions"]},
            "caveat": "Generated from local files only. Not a go-live approval; reviewer identities are not verified."}


def markdown(s):
    out = [f"# Olympus project summary: {s['project']}", "",
           f"{s['company']} → {s['target_system']} · generated {s['generated_at']}", "",
           f"**Zeus:** {s['zeus']['decision']}  ", f"**Open blockers:** {s['open_blockers']}"
           + (" (" + ", ".join(f"{k} {v}" for k, v in s["blockers_by_area"].items()) + ")" if s["blockers_by_area"] else ""), ""]
    if s["blockers"]:
        out += ["## Open blockers", "", *[f"- **{b['area']}** — {b['detail']}" for b in s["blockers"]], ""]
    b = s["latest_build"]
    out += ["## Target load counts (latest confirmed build)", ""]
    if b:
        out += [f"Build `{b['id'][:8]}` at {b['built_at']}: **{b['status']}**, {b['loadable_rows']}/{b['total_rows']} loadable, "
                f"{b['errors']} errors, {b['warnings']} warnings.", "",
                "| Load | Target | Rows | Loadable | Rejected | Logged transformations | Exceptions |", "|---|---|---:|---:|---:|---:|---|"]
        for l in b["loads"]:
            exc = ", ".join(f"{k}×{v}" for k, v in sorted(l["exceptions_by_code"].items())) or "—"
            out.append(f"| {l['name']} | {l['template']} | {l['rows']} | {l['loadable']} | {l['rejected']} | {l['transformations']} | {exc} |")
    else:
        out.append("No build from confirmed mappings yet.")
    r = s["reconciliation"]
    out += ["", "## Trial-load reconciliation (Poseidon)", "",
            (f"**{r['status']}** — {r['matched_keys']} matched keys, {r['different_keys']} different; totals {r['source_total']} vs "
             f"{r['target_total']} (net {r['net_variance']})." if r else "None recorded.")]
    u = s["uat"]
    out += ["", "## UAT (Clio)", "", f"{u['passed']}/{u['total']} PASS · {u['failed']} FAIL · {u['blocked']} BLOCKED · "
            f"{u['not_run']} NOT RUN · {u['stale_evidence']} stale" + (" · project changed: all results need re-review" if u["stale"] else "")]
    out += ["", "## Cutover (Chronos)", "", "Complete." if s["cutover"]["complete"] else "Missing: " + "; ".join(s["cutover"]["missing"])]
    out += ["", "## Incidents (Argus)", "", f"{s['incidents']['open']} open, {s['incidents']['critical_or_high']} critical/high."]
    out += ["", "## Zeus gates", "", "| Gate | Status | Detail |", "|---|---|---|",
            *[f"| {g['gate']} | {g['status']} | {str(g['detail'] or '').replace('|', '/')} |" for g in s["zeus"]["gates"]]]
    if s["zeus"]["ignored_assertions"]:
        out += ["", "Ignored approval-like fields in project.json (not evidence): " + ", ".join(s["zeus"]["ignored_assertions"])]
    out += ["", "## Source file fingerprints (SHA-256)", "", "| Folder | File | Bytes | SHA-256 |", "|---|---|---:|---|",
            *([f"| {f['folder']} | {f['file']} | {f['bytes']} | `{f['sha256']}` |" for f in s["source_files"]] or ["| — | — | — | — |"]),
            "", "_" + s["caveat"] + "_", ""]
    return "\n".join(out)


def pdf(s, filename):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor
    except ImportError as exc:
        raise RuntimeError("PDF requires: pip install 'olympus-erp[pdf]'") from exc
    c = canvas.Canvas(str(filename), pagesize=(612, 792))
    c.setTitle("Olympus project summary - " + s["project"])
    dark, red, teal, grey = HexColor("#132239"), HexColor("#B33D42"), HexColor("#107D85"), HexColor("#5D6877")
    y = [0]

    def header():
        c.setFillColor(dark); c.rect(0, 712, 612, 80, fill=1, stroke=0)
        c.setFillColor(HexColor("#EABF79")); c.setFont("Helvetica-Bold", 11); c.drawString(38, 768, "Olympus ERP | Project summary")
        c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold", 17); c.drawString(38, 738, s["project"][:60])
        y[0] = 690

    def line(text, font="Helvetica", size=9, color=dark, gap=13):
        if y[0] < 60:
            c.showPage(); header()
        c.setFont(font, size); c.setFillColor(color); c.drawString(38, y[0], str(text)[:115]); y[0] -= gap

    header()
    line(s["zeus"]["decision"], "Helvetica-Bold", 14, teal if s["zeus"]["decision"].startswith("EVIDENCE") else red, 20)
    line(f"Open blockers: {s['open_blockers']}   " + ", ".join(f"{k} {v}" for k, v in s["blockers_by_area"].items()), "Helvetica-Bold", 10)
    for bl in s["blockers"][:14]:
        line(f"- {bl['area']}: {bl['detail']}")
    y[0] -= 6; line("TARGET LOAD COUNTS", "Helvetica-Bold", 10)
    b = s["latest_build"]
    if b:
        line(f"Build {b['id'][:8]} {b['status']}: {b['loadable_rows']}/{b['total_rows']} loadable, {b['errors']} errors")
        for l in b["loads"]:
            exc = ", ".join(f"{k} x{v}" for k, v in sorted(l["exceptions_by_code"].items())) or "-"
            line(f"  {l['name']:<14} rows {l['rows']:>5}  loadable {l['loadable']:>5}  rejected {l['rejected']:>5}  changes {l['transformations']:>4}  {exc}")
    else:
        line("No build from confirmed mappings yet.")
    r = s["reconciliation"]
    y[0] -= 6; line("RECONCILIATION", "Helvetica-Bold", 10)
    line(f"{r['status']}: {r['matched_keys']} matched, {r['different_keys']} different, net {r['net_variance']}" if r else "None recorded.")
    u = s["uat"]
    y[0] -= 6; line("UAT", "Helvetica-Bold", 10)
    line(f"{u['passed']}/{u['total']} PASS, {u['failed']} FAIL, {u['blocked']} BLOCKED, {u['not_run']} NOT RUN, {u['stale_evidence']} stale")
    y[0] -= 6; line("ZEUS GATES", "Helvetica-Bold", 10)
    for g in s["zeus"]["gates"]:
        line(f"  [{g['status']}] {g['gate']}", color=teal if g["status"] == "VERIFIED" else red if g["status"] == "FAILED" else grey)
    y[0] -= 6; line("SOURCE FILE FINGERPRINTS (SHA-256)", "Helvetica-Bold", 10)
    for f in s["source_files"][:20]:
        line(f"  {f['folder']}/{f['file'][:40]}  {f['sha256']}", size=7, gap=10)
    y[0] -= 8
    line(s["caveat"], size=7, color=grey)
    c.save()


def write(s, out_dir, formats=("md", "json", "pdf")):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    written = []
    if "json" in formats:
        (out / "project_summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); written.append("project_summary.json")
    if "md" in formats:
        (out / "project_summary.md").write_text(markdown(s), encoding="utf-8"); written.append("project_summary.md")
    if "pdf" in formats:
        pdf(s, out / "project_summary.pdf"); written.append("project_summary.pdf")
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(prog="olympus summary", description="Project summary from local evidence (MD / JSON / PDF)")
    ap.add_argument("project_dir", help="Folder containing project.json (dashboard projects live in WORKSPACE/projects/<id>)")
    ap.add_argument("--format", choices=["md", "json"], default="md", help="what to print")
    ap.add_argument("-o", "--output", help="also write project_summary.md/.json/.pdf here")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args(argv)
    try:
        s = collect_evidence(args.project_dir)
        print(json.dumps(s, indent=2, ensure_ascii=False) if args.format == "json" else markdown(s))
        if args.output:
            write(s, args.output, ("md", "json") if args.no_pdf else ("md", "json", "pdf"))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        ap.exit(2, f"olympus summary: {exc}\n")
