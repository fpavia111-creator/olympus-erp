"""Readiness reports and traceable clean / rejects / change-log output writing."""
import csv
import json
import re
from pathlib import Path
from .engine import summary


def markdown(s):
    rows = [f"# Hermes readiness: {s['project']}", "",
            f"**{s['status']}** | {s['loadable_rows']}/{s['total_rows']} loadable rows ({s['readiness_percent']}%).",
            f"**Issues:** {s['errors']} errors; {s['warnings']} warnings.",
            f"**Planning estimate:** {s['estimated_hours']} hours; ${s['estimated_cost_low']:,.0f}-${s['estimated_cost_high']:,.0f}.", "",
            "| Load | Target | Rows | Loadable | Rejected | Warnings |", "|---|---|---:|---:|---:|---:|"]
    for l in s["loads"]:
        rows.append(f"| {l['name']} | {l['template']} | {l['rows']} | {l['loadable']} | {l['rejected']} | {l['warnings']} |")
    m = s.get("mapping_decisions") or {}
    rows += ["", "## Mapping decisions", "",
             (f"Confirmed v{m.get('version')} by {m.get('reviewer')} at {m.get('decided_at')} (sha256 `{str(m.get('sha256'))[:16]}…`)."
              if m.get("current") else f"**NOT CONFIRMED** — {m.get('reason', 'unknown')}. This is a preview; no import-ready files may be produced.")]
    if s["unchecked_dependencies"]:
        rows += ["", "## Unverified relationships", *["- " + x for x in s["unchecked_dependencies"]]]
    for l in s["loads"]:
        rows += ["", f"## {l['name']}", f"Source: `{l['source']}` (sha256 `{l.get('source_sha256', '')[:16]}…`); "
                 f"{l.get('transformations', 0)} logged value transformations", "",
                 "| Severity | Line | Column | Issue |", "|---|---:|---|---|"]
        for f in l["findings"]:
            msg = f["message"].replace("|", "\\|")
            rows.append(f"| {f['severity']} | {f['line']} | {f['column']} | {msg} |")
        if not l["findings"]:
            rows.append("| - | - | - | No issues found |")
        if l["auto_mapped"]:
            rows += ["", "Auto-mapped fields (review before import):", ""]
            rows += [f"- `{a}` <- `{b}`" for a, b in l["auto_mapped"].items()]
        if l["notes"]:
            rows += ["", *["- " + n for n in l["notes"]]]
    rows += ["", "## Important limitations", "",
             "- This is a local diagnostic, not a vendor-certified import or completed trial load.",
             "- Reconcile with the real target system in a sandbox; validate custom fields and current picklists.",
             "- Dates with ambiguous US/EU day ordering are rejected unless configured.",
             "- Readiness excludes target-account permissions, API quotas, transformation scripts, and go-live cutover tasks.",
             "- Estimates use fixed issue weights, not measured implementation hours.", ""]
    return "\n".join(rows)


def pdf_report(s, filename, brand="Hermes | Olympus"):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor
    except ImportError as exc:
        raise RuntimeError("PDF requires: pip install -e '.[pdf]'") from exc
    filename = Path(filename)
    c = canvas.Canvas(str(filename), pagesize=(612, 792))
    c.setTitle("Hermes migration readiness - " + s["project"])
    dark = HexColor("#132239"); teal = HexColor("#107D85"); red = HexColor("#B33D42")
    c.setFillColor(dark)
    c.rect(0, 672, 612, 120, fill=1, stroke=0)
    c.setFillColor(HexColor("#EABF79")); c.setFont("Helvetica-Bold", 13)
    c.drawString(38, 752, brand[:68])
    c.setFillColor(HexColor("#FFFFFF"))
    title = s["project"]
    title_size = 21
    while title_size > 14 and c.stringWidth(title, "Helvetica-Bold", title_size) > 530:
        title_size -= 1
    if c.stringWidth(title, "Helvetica-Bold", title_size) > 530:
        while len(title) > 1 and c.stringWidth(title + "...", "Helvetica-Bold", title_size) > 530:
            title = title[:-1]
        title += "..."
    c.setFont("Helvetica-Bold", title_size)
    c.drawString(38, 709, title)
    c.setFillColor(red if s["status"] != "READY" else teal)
    c.setFont("Helvetica-Bold", 19); c.drawString(38, 633, s["status"])
    c.setFillColor(dark); c.setFont("Helvetica", 11)
    c.drawString(38, 606, f"{s['loadable_rows']} of {s['total_rows']} rows loadable | {s['readiness_percent']}% ready")
    c.drawString(38, 588, f"{s['errors']} errors   {s['warnings']} warnings   {len(s['unchecked_dependencies'])} unchecked relationships")
    c.setStrokeColor(HexColor("#D8E1E9")); c.line(38, 567, 574, 567)
    c.setFont("Helvetica-Bold", 12); c.drawString(38, 542, "MIGRATION OBJECTS")
    c.setFont("Helvetica-Bold", 9)
    for x, h in [(40,"Object"),(295,"Rows"),(361,"Loadable"),(445,"Rejected")]: c.drawString(x,519,h)
    y = 501
    for l in s["loads"][:11]:
        c.setFont("Helvetica", 9)
        c.drawString(40, y, l["name"][:38]); c.drawRightString(324,y,str(l["rows"]))
        c.drawRightString(405,y,str(l["loadable"])); c.drawRightString(480,y,str(l["rejected"]))
        y -= 21
        c.setStrokeColor(HexColor("#E6EAEE")); c.line(38,y+7,574,y+7)
    y = min(y - 25, 270)
    c.setFont("Helvetica-Bold", 12); c.drawString(38,y,"PLANNING ESTIMATE")
    y -= 27; c.setFont("Helvetica-Bold", 20)
    c.drawString(38,y,f"{s['estimated_hours']:.2f} hours")
    c.setFont("Helvetica", 13)
    c.drawString(235,y,f"${s['estimated_cost_low']:,.0f} - ${s['estimated_cost_high']:,.0f}")
    c.setFont("Helvetica", 9)
    if s["unchecked_dependencies"]:
        c.setFillColor(red); c.drawString(38, y - 25, "Some parent-child relationships could not be verified.")
        c.setFillColor(dark)
    c.setStrokeColor(HexColor("#D8E1E9")); c.line(38, 118, 574, 118)
    for i, txt in enumerate(("Local analysis only. Not a certified or completed ERP/CRM/HCM import.",
                             "Confirm against your account configuration and perform a sandbox trial load.",
                             "Estimates are directional, not a fixed quote. See detailed report and rejects files.")):
        c.setFillColor(HexColor("#5D6877")); c.setFont("Helvetica", 8)
        c.drawString(38, 100 - i*14, txt)
    c.save()


def _csv_safe(value):
    """Stop spreadsheet apps interpreting free-text values as formulas."""
    text = str(value) if value is not None else ""
    if text and (text[:1] in ("=", "+", "@", "\t", "\r", "\n") or
                 (text.startswith("-") and not re.fullmatch(r"-\d+(?:\.\d+)?", text))):
        return "'" + text
    return text

def _write_csv(path, header, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        for vals in rows:
            wr.writerow([_csv_safe(v) for v in vals])


def build(result, out, pdf=True, brand="Hermes | Olympus"):
    mapping = result.get("mapping") or {}
    if not mapping.get("current"):
        raise ValueError("Import-ready files need confirmed mapping decisions: "
                         + mapping.get("reason", "not confirmed")
                         + ". Review with `olympus mapping show SPEC`, then `olympus mapping confirm SPEC ...`.")
    out = Path(out).resolve()
    sources = {l.source.resolve() for l in result["loads"]}
    # Never write into a source file; build files are distinctly named.
    paths = {out / f"{l.name}.{kind}.csv" for l in result["loads"] for kind in ("clean", "rejects", "changes")}
    paths |= {out / "report.json", out / "report.md", out / "report.pdf"}
    if paths & sources:
        raise ValueError("Output would overwrite a source file")
    out.mkdir(parents=True, exist_ok=True)
    s = summary(result)
    # Fail before mutating if output PDF is requested but dependency is absent.
    if pdf:
        try:
            import reportlab
        except ImportError as e:
            raise RuntimeError("PDF requires: pip install -e '.[pdf]'") from e
    for l in result["loads"]:
        headers = list(l.fields)
        _write_csv(out / f"{l.name}.clean.csv", headers,
                   ([r.clean.get(k, "") for k in headers] for r in l.rows if not r.rejected))
        # Rejects carry the ORIGINAL source values, keyed by the original line number.
        source_headers = list(l.rows[0].original) if l.rows else []
        _write_csv(out / f"{l.name}.rejects.csv", ["source_line", "issue_codes", "issue_details",
                                                   *[f"source:{h}" for h in source_headers]],
                   ([r.line, ";".join(sorted(set(f.code for f in r.findings if f.severity == "error"))),
                     ";".join(sorted(set(f"{f.column}: {f.message}" for f in r.findings if f.severity == "error"))),
                     *[r.original.get(h, "") for h in source_headers]] for r in l.rows if r.rejected))
        _write_csv(out / f"{l.name}.changes.csv", ["source_line", "field", "source_column", "original", "output", "reason", "row_status"],
                   ([c["line"], c["field"], c["source_column"], c["original"], c["output"], c["reason"],
                     "rejected" if r.rejected else "clean"] for r in l.rows for c in r.changes))
    (out / "report.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    (out / "report.md").write_text(markdown(s), encoding="utf-8")
    if pdf:
        pdf_report(s, out / "report.pdf", brand)
    return s
