"""Minimal newline-delimited MCP stdio server; fully local workspace boundary.

Implements core JSON-RPC initialize, ping, tools/list and tools/call.
No network listeners or telemetry; approval writes intentionally not exposed.
"""
import json
import sys
from pathlib import Path
from .engine import run, summary, suggest_mapping, parse_spec
from .templates import TEMPLATES, describe
from .inputs import profile, read_rows
from .reporting import build
from .signoff import status as signoff_status
from .cli import _init
from . import erp_agents as agents
from . import reconcile as poseidon, uat_evidence as clio, incidents as argus_ops
from . import mapping as hermes_mapping, project_summary

TOOL_SPECS = [
    ("list_templates", "List available migration target templates", {}, []),
    ("describe_template", "Describe required fields and aliases", {"name": {"type": "string"}}, ["name"]),
    ("profile_file", "Report columns/missing values from a CSV or XLSX", {"path": {"type": "string"}, "sheet": {"type": "string"}}, ["path"]),
    ("suggest_mapping", "Suggest explicit human-reviewable column mappings", {"path": {"type": "string"}, "template": {"type": "string"}, "preset": {"type": "string"}}, ["path", "template"]),
    ("write_spec", "Write new TOML spec (never overwrites an existing spec)", {"path": {"type": "string"}, "project": {"type": "string"}, "loads": {"type": "array", "items": {"type": "string"}}, "preset": {"type": "string"}}, ["path", "project", "loads"]),
    ("check", "Check migration data readiness without modifying files", {"spec": {"type": "string"}}, ["spec"]),
    ("build", "Write cleaned CSVs, rejects (original values + line numbers), change log and reports; refuses unless a human confirmed the mapping table", {"spec": {"type": "string"}, "output": {"type": "string"}, "pdf": {"type": "boolean"}, "require_signoff": {"type": "boolean"}}, ["spec", "output"]),
    ("signoff_status", "Read human mapping-spec signoff state (read-only)", {"spec": {"type": "string"}}, ["spec"]),
    ("mapping_table", "Hermes: suggested mappings with confidence tiers for a spec, plus decision status (read-only; only a human can confirm)", {"spec": {"type": "string"}}, ["spec"]),
    ("mapping_status", "Hermes: whether confirmed mapping decisions are current for the spec and source files (read-only)", {"spec": {"type": "string"}}, ["spec"]),
    ("project_summary", "Project summary from local evidence: blockers, fingerprints, load counts, exceptions, Zeus status (read-only)", {"project_dir": {"type": "string"}}, ["project_dir"]),
    ("assess_project", "Athena discovery questions, missing facts and risk flags for a customer-entered project JSON", {"project": {"type": "string"}}, ["project"]),
    ("draft_erp_roadmap", "Athena: draft requirements, discovery questions and responsibility matrix", {"project": {"type": "string"}}, ["project"]),
    ("draft_integration_design", "Daedalus: draft candidate integrations and review checklist; no vendor connection", {"project": {"type": "string"}}, ["project"]),
    ("draft_uat", "Apollo: create human-reviewable UAT tests; does not execute tests", {"project": {"type": "string"}}, ["project"]),
    ("draft_cutover", "Chronos: create cutover plan with sign-off checkpoints", {"project": {"type": "string"}}, ["project"]),
    ("draft_training", "Hestia: draft role-based training curriculum", {"project": {"type": "string"}}, ["project"]),
    ("draft_hypercare", "Argus: draft support, incident and monitoring playbook", {"project": {"type": "string"}}, ["project"]),
    ("model_roi", "Plutus: calculate explicit ROI scenarios from supplied assumptions only", {"project": {"type": "string"}}, ["project"]),
    ("go_live_gate", "Zeus: conservative gate from file-backed evidence; never outputs GO", {"project": {"type": "string"}}, ["project"]),
    ("generate_erp_pack", "Generate ten local consultant deliverable drafts; refuses to overwrite an existing directory", {"project": {"type": "string"}, "output": {"type": "string"}}, ["project", "output"]),
    ("reconcile_exports", "Poseidon: read-only key, count, amount comparison of source vs trial-load CSV/XLSX", {"source": {"type": "string"}, "target": {"type": "string"}, "source_key": {"type": "string"}, "target_key": {"type": "string"}, "source_amount": {"type": "string"}, "target_amount": {"type": "string"}, "tolerance": {"type": "string"}}, ["source", "target", "source_key", "target_key", "source_amount", "target_amount"]),
    ("uat_status", "Clio: read claimed UAT results and independent file fingerprints, conservatively", {"project": {"type": "string"}}, ["project"]),
    ("incident_list", "Argus: list local manually-entered incidents; not vendor monitoring", {}, []),
    ("incident_create", "Argus: create manually-entered incident for local review", {"title": {"type": "string"}, "severity": {"type": "string", "enum": ["critical","high","medium","low"]}, "owner": {"type": "string"}}, ["title", "severity", "owner"]),
    ("incident_update", "Argus: human-entered incident state change", {"ticket_id": {"type": "string"}, "status": {"type": "string", "enum": ["open","investigating","mitigated","resolved"]}, "actor": {"type": "string"}}, ["ticket_id", "status", "actor"]),
]

def _within(root, path):
    path = Path(path)
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path outside configured workspace")
    return target

def _check_sources(root, spec):
    _, cfg = parse_spec(spec)
    for load in cfg["load"]:
        path = Path(load.get("source", ""))
        resolved = (spec.parent / path).resolve() if not path.is_absolute() else path.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("Source outside workspace: " + str(path))

def _dispatch(name, args, root):
    if name == "reconcile_exports":
        return poseidon.reconcile(_within(root, args["source"]), _within(root, args["target"]),
                                  args["source_key"], args["target_key"], args["source_amount"],
                                  args["target_amount"], args.get("tolerance", "0.01"))
    if name == "uat_status": return clio.status(_within(root, args["project"]))
    if name == "incident_list": return argus_ops.listing(root)
    if name == "incident_create": return argus_ops.create(root, args["title"], args["severity"], args["owner"])
    if name == "incident_update": return argus_ops.change(root, args["ticket_id"], args["status"], args["actor"])
    if name == "project_summary":
        directory = _within(root, args["project_dir"])
        return project_summary.collect_evidence(directory)
    if name == "list_templates": return sorted(TEMPLATES)
    if name == "describe_template": return describe(args["name"])
    if name == "profile_file": return profile(_within(root, args["path"]), args.get("sheet"))
    if name == "suggest_mapping":
        headers, _ = read_rows(_within(root, args["path"]))
        return suggest_mapping(headers, args["template"], args.get("preset"))
    if name == "write_spec":
        spec = _within(root, args["path"])
        # Refuse external paths embedded in a spec being created.
        for ent in args["loads"]:
            if "=" not in ent:
                raise ValueError("Loads must be TEMPLATE=SOURCE")
            _within(root, spec.parent / ent.split("=",1)[1])
        _init(spec, args["project"], args["loads"], args.get("preset"))
        return {"created": str(spec)}
    if name in {"assess_project", "draft_erp_roadmap", "draft_integration_design", "draft_uat", "draft_cutover", "draft_training", "draft_hypercare", "model_roi", "go_live_gate", "generate_erp_pack"}:
        p = agents.load_project(_within(root, args["project"]))
        functions = {"assess_project": agents.assess_project, "draft_erp_roadmap": agents.athena,
                     "draft_integration_design": agents.daedalus, "draft_uat": agents.apollo,
                     "draft_cutover": agents.chronos, "draft_training": agents.hestia,
                     "draft_hypercare": agents.argus, "model_roi": agents.plutus,
                     "go_live_gate": agents.go_live_gate}
        if name == "generate_erp_pack":
            return agents.pack(p, _within(root, args["output"]))
        if name == "go_live_gate":
            # Evidence comes only from files next to the project, never from the caller.
            project_path = _within(root, args["project"])
            try:
                ev = project_summary.collect_evidence(project_path.parent)
                return ev["zeus"] | {"project": p["project_name"]}
            except (ValueError, OSError):
                return agents.go_live_gate(p)
        return functions[name](p)
    spec = _within(root, args["spec"])
    if name == "signoff_status": return signoff_status(spec)
    if name == "mapping_table":
        _check_sources(root, spec); return hermes_mapping.propose(spec)
    if name == "mapping_status":
        _check_sources(root, spec); return hermes_mapping.status(spec)
    _check_sources(root, spec)
    if name == "check": return summary(run(spec))
    if name == "build":
        if args.get("require_signoff") and not signoff_status(spec)["approved"]:
            raise ValueError("Themis approval missing or stale")
        return build(run(spec), _within(root, args["output"]), pdf=args.get("pdf", True))
    raise ValueError("Unknown tool: " + name)

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
_TOOLS = {n: (p, r) for n, d, p, r in TOOL_SPECS}
_TYPES = {"string": str, "boolean": bool, "array": list}


def _validate_arguments(name, args):
    """Enforce the advertised inputSchema (required keys, no extras, basic types)."""
    if name not in _TOOLS:
        raise LookupError("Unknown tool: " + str(name))
    if not isinstance(args, dict):
        raise TypeError("Tool arguments must be a JSON object")
    props, required = _TOOLS[name]
    missing = [k for k in required if k not in args]
    if missing:
        raise TypeError("Missing required argument(s): " + ", ".join(missing))
    extra = sorted(set(args) - set(props))
    if extra:
        raise TypeError("Unexpected argument(s): " + ", ".join(extra))
    for key, value in args.items():
        schema = props[key]
        if value is None and key not in required:
            continue
        kind = _TYPES.get(schema.get("type"))
        if kind and not isinstance(value, kind):
            raise TypeError(f"Argument {key} must be {schema['type']}")
        if kind is list and not all(isinstance(x, str) for x in value):
            raise TypeError(f"Argument {key} must be an array of strings")
        if "enum" in schema and value not in schema["enum"]:
            raise TypeError(f"Argument {key} must be one of: " + ", ".join(schema["enum"]))


def _error(ident, code, message):
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def handle(req, root, tool_list):
    """Return one JSON-RPC response object, or None for notifications."""
    if not isinstance(req, dict) or not isinstance(req.get("method", None), str):
        return _error(req.get("id") if isinstance(req, dict) else None, -32600, "Invalid Request")
    ident = req.get("id")
    method = req["method"]
    params = req.get("params") or {}
    if "id" not in req:  # notification: never answered
        return None
    if not isinstance(params, dict):
        return _error(ident, -32602, "params must be an object")
    if method == "initialize":
        asked = params.get("protocolVersion")
        value = {"protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0],
                 "capabilities": {"tools": {"listChanged": False}},
                 "serverInfo": {"name": "hermes", "version": "0.4.0"}}
    elif method == "ping":
        value = {}
    elif method == "tools/list":
        value = {"tools": tool_list}
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments")
        args = {} if args is None else args
        try:
            _validate_arguments(name, args)
        except (LookupError, TypeError) as exc:
            return _error(ident, -32602, str(exc))
        try:
            answer = _dispatch(name, args, root)
            value = {"content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}]}
        except (KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
            # MCP: tool execution failures are results with isError, visible to the model.
            value = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except Exception as exc:  # never let one bad call kill the stdio session
            value = {"content": [{"type": "text", "text": "Internal error: " + type(exc).__name__}], "isError": True}
    else:
        return _error(ident, -32601, "Method not found: " + method)
    return {"jsonrpc": "2.0", "id": ident, "result": value}


def serve(workspace="."):
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ValueError("Workspace not found: " + str(root))
    tool_list = [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r, "additionalProperties": False}}
                 for n, d, p, r in TOOL_SPECS]
    for binary_line in sys.stdin.buffer:
        if not binary_line.strip():
            continue
        try:
            req = json.loads(binary_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            msg = _error(None, -32700, "Parse error")
        else:
            if isinstance(req, list):
                msg = _error(None, -32600, "JSON-RPC batches are not supported")
            else:
                msg = handle(req, root, tool_list)
        if msg is not None:
            sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n"); sys.stdout.flush()
    return 0
