"""Hermes command line (run as `olympus hermes ...`; `olympus mapping ...` for the mapping table)."""
import argparse
import json
from pathlib import Path
from .engine import SpecError, SourceError, run, summary, suggest_mapping
from .inputs import profile, read_rows
from .templates import TEMPLATES, describe
from .reporting import build, markdown
from .signoff import status as signoff_status


def _init(path, project, loads, source_system=None):
    if not loads:
        raise SpecError("Provide at least one --load TEMPLATE=SOURCE")
    lines = ["[project]", "name = " + json.dumps(project), "day_first = \"auto\"",
             "rate_low = 150", "rate_high = 250"]
    if source_system:
        lines += ["source_system = " + json.dumps(source_system)]
    for i, entry in enumerate(loads, 1):
        if "=" not in entry:
            raise SpecError("Each --load is TEMPLATE=SOURCE")
        template, source = entry.split("=", 1)
        if template not in TEMPLATES:
            raise SpecError("Unknown template: " + template)
        lines += ["", "[[load]]", f"name = {json.dumps(template.split('.')[-1] + '_' + str(i))}",
                  "template = " + json.dumps(template), "source = " + json.dumps(source)]
    if path.exists():
        raise SpecError("Spec exists; refusing overwrite: " + str(path))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mapping_table(proposal):
    lines = [f"Mapping table for {proposal['spec']}  (decisions: "
             + ("CURRENT v%s by %s" % (proposal['decisions'].get('version'), proposal['decisions'].get('reviewer'))
                if proposal["decisions"]["current"] else "NOT CONFIRMED — " + proposal["decisions"]["reason"]) + ")"]
    for load in proposal["loads"]:
        lines += ["", f"[{load['name']}] {load['template']} <- {load['source']}  (sha256 {load['source_sha256'][:12]}…)",
                  f"  {'target field':<22} {'req':<4} {'suggested source':<24} {'tier':<10} review"]
        for r in load["rows"]:
            sug = " + ".join(r["suggested"]) if isinstance(r["suggested"], list) else (r["suggested"] or "—")
            extra = ("  candidates: " + ", ".join(r["candidates"])) if r["tier"] == "AMBIGUOUS" else ""
            lines.append(f"  {r['target']:<22} {'yes' if r['required'] else '':<4} {sug:<24} {r['tier']:<10} "
                         f"{'EXPLICIT REQUIRED' if r['review_required'] else 'confirm'}{extra}")
    lines += ["", "HIGH/MEDIUM rows may be accepted together with --accept-suggestions; LOW, AMBIGUOUS and",
              "unmatched required rows need --set LOAD.FIELD=Header (use + to combine) or --unmap LOAD.FIELD,",
              "or run with --interactive to decide each row."]
    return "\n".join(lines)


def _parse_sets(values):
    out = {}
    for v in values or []:
        if "=" not in v:
            raise SpecError("--set expects LOAD.FIELD=Header")
        k, col = v.split("=", 1)
        cols = [c for c in col.split("+")]
        out[k.strip()] = cols if len(cols) > 1 else cols[0]
    return out


def _interactive(proposal, ask=input, say=print):
    decisions = {}
    for load in proposal["loads"]:
        say(f"\n[{load['name']}] headers: {', '.join(load['headers'])}")
        fields = {}
        for r in load["rows"]:
            sug = r["suggested"]
            prompt = (f"{load['name']}.{r['target']} ({r['tier']}{', required' if r['required'] else ''}) "
                      f"suggested={sug or '—'}"
                      + (f" candidates={r['candidates']}" if r["candidates"] and r["tier"] == "AMBIGUOUS" else "")
                      + " [Enter=accept, Header(+Header)=override, -=leave unmapped]: ")
            while True:
                answer = ask(prompt).strip()
                if answer == "" and r["review_required"]:
                    say("  This row needs an explicit choice: type a header name or '-'.")
                    continue
                if answer == "":
                    fields[r["target"]] = {"source": sug, "reviewed": True, "explicit": False}
                elif answer == "-":
                    fields[r["target"]] = {"source": None, "reviewed": True, "explicit": True}
                else:
                    cols = answer.split("+")
                    if any(c not in load["headers"] for c in cols):
                        say("  Unknown header; try again.")
                        continue
                    fields[r["target"]] = {"source": cols if len(cols) > 1 else cols[0], "reviewed": True, "explicit": True}
                break
        decisions[load["name"]] = fields
    return decisions


def mapping_main(argv=None, ask=input):
    from . import mapping
    p = argparse.ArgumentParser(prog="olympus mapping", description="Review and confirm column mappings before import-ready files are built")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("show"); q.add_argument("spec"); q.add_argument("--json", action="store_true")
    q = sub.add_parser("status"); q.add_argument("spec")
    q = sub.add_parser("confirm"); q.add_argument("spec"); q.add_argument("--reviewer", required=True)
    q.add_argument("--attest", action="store_true", help="I reviewed every target field for these exact files")
    q.add_argument("--accept-suggestions", action="store_true", help="accept HIGH/MEDIUM suggestions as shown")
    q.add_argument("--set", action="append", metavar="LOAD.FIELD=Header", help="explicit mapping or override")
    q.add_argument("--unmap", action="append", metavar="LOAD.FIELD", help="explicitly leave a field unmapped")
    q.add_argument("--interactive", action="store_true", help="decide each row at a prompt")
    args = p.parse_args(argv)
    try:
        if args.cmd == "show":
            proposal = mapping.propose(args.spec)
            print(json.dumps(proposal, indent=2) if args.json else _mapping_table(proposal)); return 0
        if args.cmd == "status":
            v = mapping.status(args.spec); print(json.dumps(v, indent=2)); return 0 if v["current"] else 1
        proposal = mapping.propose(args.spec)
        if args.interactive:
            decisions = _interactive(proposal, ask)
        else:
            if not (args.accept_suggestions or args.set or args.unmap):
                raise SpecError("Nothing decided: use --interactive, or --accept-suggestions with --set/--unmap for review rows")
            decisions = mapping.accept_suggestions(proposal, _parse_sets(args.set), set(args.unmap or ()))
            if not args.accept_suggestions:
                explicit = set(_parse_sets(args.set)) | set(args.unmap or ())
                for load in proposal["loads"]:
                    for r in load["rows"]:
                        if f"{load['name']}.{r['target']}" not in explicit and r["target"] not in explicit:
                            decisions[load["name"]][r["target"]]["reviewed"] = False
        v = mapping.confirm(args.spec, args.reviewer, decisions, attest=args.attest)
        print(json.dumps(v, indent=2)); return 0
    except (SpecError, SourceError, OSError, ValueError, KeyError) as e:
        p.exit(2, f"olympus mapping: {e}\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="olympus hermes", description="Hermes migration readiness (local only)")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("templates"); q.add_argument("name", nargs="?")
    q = sub.add_parser("profile"); q.add_argument("file"); q.add_argument("--sheet")
    q = sub.add_parser("suggest"); q.add_argument("file"); q.add_argument("template")
    q.add_argument("--sheet"); q.add_argument("--preset", choices=["quickbooks", "sage"])
    q = sub.add_parser("init"); q.add_argument("--name", required=True); q.add_argument("--load", action="append", required=True)
    q.add_argument("--preset", choices=["quickbooks", "sage"]); q.add_argument("-o", "--output", default="hermes.toml")
    q = sub.add_parser("check"); q.add_argument("spec", nargs="?", default="hermes.toml"); q.add_argument("--json", action="store_true")
    q = sub.add_parser("build"); q.add_argument("spec", nargs="?", default="hermes.toml")
    q.add_argument("-o", "--output", default="out"); q.add_argument("--no-pdf", action="store_true")
    q.add_argument("--brand", default="Hermes | Olympus"); q.add_argument("--require-signoff", action="store_true")
    q = sub.add_parser("signoff"); q.add_argument("spec", nargs="?", default="hermes.toml")
    q = sub.add_parser("mcp"); q.add_argument("--workspace", default=".")
    args = p.parse_args(argv)
    try:
        if args.cmd == "templates":
            print(json.dumps(describe(args.name) if args.name else sorted(TEMPLATES), indent=2))
            return 0
        if args.cmd == "profile":
            print(json.dumps(profile(args.file, args.sheet), indent=2)); return 0
        if args.cmd == "suggest":
            columns, _ = read_rows(args.file, args.sheet)
            print(json.dumps(suggest_mapping(columns, args.template, args.preset), indent=2)); return 0
        if args.cmd == "init":
            _init(Path(args.output), args.name, args.load, args.preset)
            print("Created " + args.output); return 0
        if args.cmd == "mcp":
            from .mcp import serve
            return serve(args.workspace)
        if args.cmd == "signoff":
            v = signoff_status(args.spec); print(json.dumps(v, indent=2)); return 0 if v["approved"] else 1
        if args.cmd == "build" and args.require_signoff and not signoff_status(args.spec)["approved"]:
            raise SpecError("Themis approval missing or stale; request explicit human sign-off")
        v = run(args.spec)
        s = summary(v)
        if args.cmd == "check":
            print(json.dumps(s, indent=2) if args.json else markdown(s))
        else:
            s = build(v, args.output, pdf=not args.no_pdf, brand=args.brand)
            print(f"{s['status']}: {s['loadable_rows']}/{s['total_rows']} loadable. Output: {args.output}")
        return 0 if s["status"] == "READY" else 1
    except (SpecError, SourceError, OSError, ValueError, RuntimeError, KeyError) as e:
        p.exit(2, f"hermes: {e}\n")

if __name__ == "__main__":
    raise SystemExit(main())
