"""Peitho: human-reviewed ERP outreach qualification and draft creation.

No web scraping, enrichment, guesses, email sending, or automated follow-up.
Facts must come from a reviewed lead spreadsheet.
"""
import argparse
import csv
import re
from pathlib import Path

HEADERS = ("company", "contact", "email", "source_url", "source_note",
           "erp_project_announced", "erp_role_hiring", "implementation_partner",
           "warm_introduction", "reviewed", "do_not_contact")

def yes(x):
    return str(x or "").strip().lower() in ("1", "yes", "true", "y")

def grade(row):
    if yes(row.get("do_not_contact")):
        return "SUPPRESSED", 0
    if not yes(row.get("reviewed")):
        return "NEEDS_REVIEW", 0
    weights = (("erp_project_announced", 40), ("erp_role_hiring", 20),
               ("implementation_partner", 25), ("warm_introduction", 25))
    score = min(100, sum(n for k, n in weights if yes(row.get(k))))
    return ("HIGH" if score >= 40 else "MEDIUM" if score >= 20 else "LOW"), score

def read_leads(path):
    with Path(path).open("r", newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames or "company" not in rdr.fieldnames:
            raise ValueError("Lead CSV must include a company column")
        return list(rdr)

def qualify(source, output):
    rows = read_leads(source)
    fields = list(dict.fromkeys([*HEADERS, *(rows[0].keys() if rows else ()), "priority", "score"]))
    from .reporting import _csv_safe
    with Path(output).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            priority, score = grade(row)
            writer.writerow({k: _csv_safe(v) for k, v in (row | {"priority": priority, "score": score}).items()})
    return len(rows)

def draft(source, output):
    rows = read_leads(source)
    content = ["# Peitho: review-only outreach drafts", "",
               "These drafts require human fact-checking and approval. Nothing is sent.", ""]
    count = 0
    for row in rows:
        priority, score = grade(row)
        if priority in ("SUPPRESSED", "NEEDS_REVIEW", "LOW"):
            continue
        company = row.get("company", "").strip()
        if not company:
            continue
        contact = row.get("contact", "").strip() or "there"
        # Avoid injecting untrusted spreadsheet text into markdown/email bodies.
        company = re.sub(r"[\r\n<>]", " ", company)[:110]
        contact = re.sub(r"[\r\n<>]", " ", contact)[:80]
        source_url = re.sub(r"[\r\n<>\s]", "", row.get("source_url", "") or "")[:300]
        source_note = re.sub(r"[\r\n<>]", " ", row.get("source_note", "") or "").strip()[:300]
        if yes(row.get("implementation_partner")):
            reason = "your work on implementation projects"
        elif yes(row.get("erp_project_announced")):
            reason = "a publicly mentioned system migration initiative"
        else:
            reason = "a possible future ERP/CRM data migration need"
        content += [f"## {company} ({priority}, score {score})", "",
                    f"**Review source:** {source_url or 'Not provided'}",
                    f"**Source note:** {source_note or 'No supporting note provided'}", "",
                    f"Subject: Before a migration starts, find the bad data", "",
                    f"Hello {contact},", "",
                    f"I'm reaching out because of {reason}. Hermes is a local-first tool that checks CSV and Excel exports before a migration and produces a line-numbered list of issues, validated files, and a readiness report.", "",
                    "We can walk through a sample report and discuss whether a scoped readiness scan would be useful. No access to your production system is required for an initial conversation.", "",
                    "Would a short introduction be worthwhile? If not, just reply and I won't follow up.", "",
                    "Best,", "[Your name]", "", "---", ""]
        count += 1
    Path(output).write_text("\n".join(content), encoding="utf-8")
    return count

def main(argv=None):
    p = argparse.ArgumentParser(prog="peitho", description="Human-controlled lead qualification and email drafts")
    sub = p.add_subparsers(dest="cmd", required=True)
    a=sub.add_parser("qualify"); a.add_argument("source"); a.add_argument("-o", "--output", default="leads_scored.csv")
    a=sub.add_parser("draft"); a.add_argument("source"); a.add_argument("-o", "--output", default="review_drafts.md")
    a=sub.add_parser("fields")
    v=p.parse_args(argv)
    try:
        if v.cmd == "fields":
            print(",".join(HEADERS)); return 0
        n = qualify(v.source, v.output) if v.cmd == "qualify" else draft(v.source, v.output)
        print(f"Processed {n} entries -> {v.output} (no messages sent)")
        return 0
    except (ValueError, OSError) as e:
        p.exit(2, f"peitho: {e}\n")

if __name__ == "__main__":
    raise SystemExit(main())
