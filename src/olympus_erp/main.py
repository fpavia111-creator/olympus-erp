"""`olympus` umbrella command: one workspace, one entry point.

    olympus hermes ...      data readiness (profile, suggest, check, build, init, mcp)
    olympus mapping ...     confirmable mapping table (show, confirm, status)
    olympus themis ...      mapping-spec sign-off (status, approve)
    olympus poseidon ...    reconcile source vs trial-load exports
    olympus clio ...        UAT status / human result entry
    olympus argus ...       local ERP hypercare incident queue
    olympus summary ...     project summary (MD / JSON / PDF)
    olympus erp ...         planning drafts (assess, pack)
    olympus peitho ...      reviewed lead scoring and drafts (never sends)
    olympus web ...         loopback dashboard
    olympus mcp ...         local MCP stdio server
"""
import sys

USAGE = __doc__


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE.strip()); return 0
    if argv[0] in ("-V", "--version"):
        from . import __version__
        print(__version__); return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "hermes":
        from .cli import main as m; return m(rest)
    if cmd == "mapping":
        from .cli import mapping_main as m; return m(rest)
    if cmd == "mcp":
        from .cli import main as m; return m(["mcp", *rest])
    if cmd == "themis":
        from .signoff import main as m; return m(rest)
    if cmd == "peitho":
        from .peitho import main as m; return m(rest)
    if cmd == "erp":
        from .erp_agents import main as m; return m(rest)
    if cmd == "web":
        from .dashboard import main as m; return m(rest)
    if cmd == "mcp-sdk":
        from .sdk_server import main as m; return m(rest)
    if cmd == "summary":
        from .project_summary import main as m; return m(rest)
    if cmd in ("poseidon", "clio", "argus", "workbench"):
        from .workbench import main as m
        alias = {"poseidon": "reconcile"}
        if cmd == "workbench":
            return m(rest)
        # Keep options like --workspace before the sub-command for the workbench parser.
        opts, tail = [], list(rest)
        while tail and tail[0] == "--workspace" and len(tail) > 1:
            opts += tail[:2]; tail = tail[2:]
        if cmd == "poseidon":
            return m([*opts, "reconcile", *tail])
        mapping = {"clio": {"status": "uat-status", "record": "uat-record"},
                   "argus": {"list": "incidents", "new": "incident-new", "update": "incident-update"}}[cmd]
        if not tail or tail[0] not in mapping:
            print(f"usage: olympus {cmd} [--workspace DIR] {{{','.join(mapping)}}} ...", file=sys.stderr); return 2
        return m([*opts, mapping[tail[0]], *tail[1:]])
    print(f"olympus: unknown command {cmd!r}\n\n" + USAGE.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
