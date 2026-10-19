"""Hermes engine: mapping suggestions, deterministic validation and traceable cleaning."""
from __future__ import annotations
import hashlib
import json
import re
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .inputs import read_rows, SourceError
from .templates import TEMPLATES, Field, PRESETS

STATES = {
    "Alabama":"AL", "Alaska":"AK", "Arizona":"AZ", "Arkansas":"AR", "California":"CA", "Colorado":"CO", "Connecticut":"CT", "Delaware":"DE", "Florida":"FL", "Georgia":"GA", "Hawaii":"HI", "Idaho":"ID", "Illinois":"IL", "Indiana":"IN", "Iowa":"IA", "Kansas":"KS", "Kentucky":"KY", "Louisiana":"LA", "Maine":"ME", "Maryland":"MD", "Massachusetts":"MA", "Michigan":"MI", "Minnesota":"MN", "Mississippi":"MS", "Missouri":"MO", "Montana":"MT", "Nebraska":"NE", "Nevada":"NV", "New Hampshire":"NH", "New Jersey":"NJ", "New Mexico":"NM", "New York":"NY", "North Carolina":"NC", "North Dakota":"ND", "Ohio":"OH", "Oklahoma":"OK", "Oregon":"OR", "Pennsylvania":"PA", "Rhode Island":"RI", "South Carolina":"SC", "South Dakota":"SD", "Tennessee":"TN", "Texas":"TX", "Utah":"UT", "Vermont":"VT", "Virginia":"VA", "Washington":"WA", "West Virginia":"WV", "Wisconsin":"WI", "Wyoming":"WY", "District of Columbia":"DC"
}
STATE_LOOKUP = {k.lower(): v for k, v in STATES.items()} | {v.lower(): v for v in STATES.values()}
COUNTRIES = {"us":"US", "usa":"US", "united states":"US", "united states of america":"US", "uk":"GB", "united kingdom":"GB", "canada":"CA", "ca":"CA", "mexico":"MX", "mx":"MX", "gb":"GB", "germany":"DE", "de":"DE", "france":"FR", "fr":"FR"}

class SpecError(ValueError):
    pass

@dataclass
class Finding:
    severity: str
    column: str
    line: int
    code: str
    message: str

@dataclass
class Row:
    line: int
    original: dict
    clean: dict
    findings: list[Finding] = field(default_factory=list)
    changes: list = field(default_factory=list)
    @property
    def rejected(self):
        return any(f.severity == "error" for f in self.findings)
    def flag(self, level, column, code, message):
        if not any(f.code == code and f.column == column and f.message == message for f in self.findings):
            self.findings.append(Finding(level, column, self.line, code, message))

@dataclass
class Load:
    name: str
    template: str
    source: Path
    fields: dict
    mappings: dict
    rows: list[Row]
    notes: list[str] = field(default_factory=list)
    auto_maps: dict = field(default_factory=dict)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def _name_key(s):
    return re.sub(r"\b(incorporated|inc|limited|ltd|corporation|corp|llc|company|co)\b", "", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()

def suggest_mapping(columns, template, preset=None):
    if template not in TEMPLATES:
        raise SpecError(f"Unknown template {template}")
    if preset and preset not in PRESETS:
        raise SpecError(f"Unknown source preset: {preset}")
    found, ambiguous = {}, {}
    for target, field in TEMPLATES[template].fields.items():
        candidates = {_norm(target), *(_norm(x) for x in field.aliases)}
        matches = [c for c in columns if _norm(c) in candidates]
        # Only consult source-system hints when the target has no direct
        # exact/alias match; otherwise a parent ID could steal an invoice ID.
        if preset and not matches:
            matches += [c for c in columns if PRESETS[preset].get(c) == target and c not in matches]
        if target in columns:
            found[target] = target
        elif len(matches) == 1:
            found[target] = matches[0]
        elif len(matches) > 1:
            ambiguous[target] = matches
    return {"mapping": found, "ambiguous": ambiguous, "unmapped": [t for t in TEMPLATES[template].fields if t not in found]}

def parse_spec(path):
    path = Path(path).resolve()
    try:
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise SpecError(f"Cannot read TOML spec: {e}") from e
    if not isinstance(cfg.get("load"), list) or not cfg["load"]:
        raise SpecError("Spec needs at least one [[load]] section")
    names = [str(l.get("name", "")) for l in cfg["load"]]
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", n) for n in names) or len(names) != len(set(names)):
        raise SpecError("Each load needs a unique safe name (letters, numbers, _ or -)")
    try:
        low = Decimal(str(cfg.get("project", {}).get("rate_low", 150)))
        high = Decimal(str(cfg.get("project", {}).get("rate_high", 250)))
    except InvalidOperation as e:
        raise SpecError("Invalid project rates") from e
    if low < 0 or high < low:
        raise SpecError("Rates must be positive and rate_high >= rate_low")
    return path, cfg

def _decimal(s):
    s = s.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        raise InvalidOperation
    d = Decimal(s)
    if not d.is_finite():
        raise InvalidOperation
    return d

def _date(value, day_first="auto"):
    value = value.strip()
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    p = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
    if not p:
        raise ValueError("Unrecognized date")
    a, b, y = map(int, p.groups())
    if day_first == "auto" and a <= 12 and b <= 12:
        raise ValueError("Ambiguous day/month; set project.day_first to true/false")
    if day_first is True:
        day, month = a, b
    elif day_first is False:
        day, month = b, a
    else:
        day, month = (a, b) if a > 12 else (b, a)
    return datetime(y, month, day).strftime("%Y-%m-%d")

def _field(spec):
    if isinstance(spec, Field):
        return spec
    if not isinstance(spec, dict):
        raise SpecError("Field overrides must be tables")
    return Field(kind=spec.get("type", "text"), required=bool(spec.get("required", False)),
                 minimum=str(spec["minimum"]) if "minimum" in spec else None,
                 allowed=tuple(spec.get("enum", [])), unique=bool(spec.get("unique", False)))

def _clean(raw, fld, day_first):
    v = str(raw).strip()
    if not v:
        return "", None
    if v.startswith(("=", "+", "-", "@", "\t", "\r")) and fld.kind not in ("number", "date"):
        return v, "Potential spreadsheet formula payload in text field"
    if fld.kind == "email":
        if ";" in v or "," in v:
            return v, "Multiple emails in one cell"
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", v):
            return v, "Invalid email address"
        return v.lower(), None
    if fld.kind == "state":
        if v.lower() not in STATE_LOOKUP:
            return v, "Unknown US state; provide a mapping"
        return STATE_LOOKUP[v.lower()], None
    if fld.kind == "country":
        if v.lower() not in COUNTRIES:
            return v, "Unknown country; provide a mapping"
        return COUNTRIES[v.lower()], None
    if fld.kind == "date":
        try:
            return _date(v, day_first), None
        except ValueError as e:
            return v, str(e)
    if fld.kind == "number":
        try:
            n = _decimal(v)
            if fld.minimum is not None and n < Decimal(fld.minimum):
                return str(n), f"Below minimum {fld.minimum}"
            return format(n, "f"), None
        except (InvalidOperation, ValueError):
            return v, "Not a valid number"
    if fld.kind == "enum" and fld.allowed and v not in fld.allowed:
        return v, "Unknown picklist value; provide a mapping"
    return v, None

def _change_reason(kind, source_text, after_default, after_values, final, defaulted, combined):
    reasons = []
    if combined: reasons.append("combined source columns")
    if defaulted: reasons.append("blank source; spec default applied")
    if after_values != after_default: reasons.append("spec value mapping")
    if final != str(after_values).strip():
        reasons.append({"email": "email lower-cased", "state": "state normalized to code",
                        "country": "country normalized to ISO code", "date": "date normalized to YYYY-MM-DD",
                        "number": "number normalized (symbols/commas/parentheses)"}.get(kind, "normalized"))
    elif str(after_values) != final: reasons.append("surrounding whitespace trimmed")
    return "; ".join(reasons) or "normalized"


def run(spec):
    from .mapping import status as mapping_status, decided_mappings
    path, cfg = parse_spec(spec)
    mstatus = mapping_status(path)
    decided = decided_mappings(path) if mstatus["current"] else None
    proj = cfg.get("project", {})
    day_first = proj.get("day_first", "auto")
    if day_first not in ("auto", True, False):
        raise SpecError("project.day_first must be 'auto', true or false")
    loads = []
    for ls in cfg["load"]:
        template = ls.get("template")
        if template not in TEMPLATES:
            raise SpecError(f"Unknown template: {template}")
        source = Path(ls.get("source", ""))
        if not source.is_absolute():
            source = (path.parent / source).resolve()
        columns, rows = read_rows(source, ls.get("sheet"))
        schema = dict(TEMPLATES[template].fields)
        schema.update({k: _field(v) for k, v in ls.get("fields", {}).items()})
        mappings = ls.get("map", {})
        if not isinstance(mappings, dict):
            raise SpecError("[load.map] must be a table")
        if any(k not in schema for k in mappings):
            raise SpecError(f"Unknown target mapping fields: {set(mappings) - set(schema)}")
        if any(isinstance(v, (dict, int, float, bool)) for v in mappings.values()):
            raise SpecError("Mappings must be a column name or list of column names")
        suggestions = suggest_mapping(columns, template, ls.get("preset", proj.get("source_system")))
        if decided is not None:
            # Human-confirmed decisions replace every automatic guess.
            allmap = dict(decided.get(ls["name"], {}))
        else:
            allmap = suggestions["mapping"] | mappings
        for target, expr in allmap.items():
            for col in expr if isinstance(expr, list) else [expr]:
                if col not in columns:
                    raise SpecError(f"Source column {col!r} not found in {source.name} for {target}")
        notes = []
        if suggestions["ambiguous"] and decided is None:
            notes.append("Ambiguous source columns: " + json.dumps(suggestions["ambiguous"], sort_keys=True))
        if any(field.required and target not in allmap and target not in ls.get("defaults", {})
               for target, field in schema.items()):
            notes.append("Some required columns are unmapped; all affected rows will be rejected")
        output = []
        for line, original in rows:
            cleaned = {}
            obj = Row(line, original, cleaned)
            for target, fld in schema.items():
                expr = allmap.get(target)
                if isinstance(expr, list):
                    raw = " ".join(str(original.get(x, "")).strip() for x in expr if original.get(x, "").strip())
                    source_text = " | ".join(str(original.get(x, "")) for x in expr)
                elif isinstance(expr, str):
                    raw = original.get(expr, "")
                    source_text = raw
                else:
                    raw = ""
                    source_text = ""
                defaulted = False
                if not str(raw).strip():
                    default = ls.get("defaults", {}).get(target, "")
                    defaulted = bool(str(default).strip())
                    raw = default
                after_default = raw
                mapped = ls.get("values", {}).get(target, {})
                raw = mapped.get(str(raw).strip(), raw)
                v, err = _clean(raw, fld, day_first)
                cleaned[target] = v
                if str(v) != str(source_text):
                    # Every difference between source text and output is logged; nothing changes silently.
                    obj.changes.append({"line": line, "field": target,
                                        "source_column": " + ".join(expr) if isinstance(expr, list) else (expr or ""),
                                        "original": source_text, "output": v,
                                        "reason": _change_reason(fld.kind, source_text, after_default, raw, str(v),
                                                                 defaulted, isinstance(expr, list) and len(expr) > 1)})
                if fld.required and not v:
                    obj.flag("error", target, "required", "Required value is blank")
                if err:
                    obj.flag("error", target, "invalid", err)
            output.append(obj)
        for target, fld in schema.items():
            if not fld.unique:
                continue
            seen = {}
            for row in output:
                v = row.clean[target]
                if v and v in seen:
                    row.flag("error", target, "duplicate_id", f"Same identifier as line {seen[v]}")
                    # Reject BOTH duplicates: no arbitrary winner.
                    other = next(r for r in output if r.line == seen[v])
                    other.flag("error", target, "duplicate_id", f"Same identifier as line {row.line}")
                elif v:
                    seen[v] = row.line
        name_col = TEMPLATES[template].duplicate_name
        if name_col:
            seen = {}
            for row in output:
                label = _name_key(row.clean.get(name_col, ""))
                if label and label in seen:
                    row.flag("warning", name_col, "possible_duplicate", f"Possible duplicate of line {seen[label]}")
                elif label:
                    seen[label] = row.line
        journal = TEMPLATES[template].journal
        if journal:
            jcol, debit, credit = journal
            groups = defaultdict(list)
            for r in output:
                if r.clean.get(jcol):
                    groups[r.clean[jcol]].append(r)
            for jid, group in groups.items():
                if any(any(f.column in (debit, credit) and f.severity == "error" for f in row.findings) for row in group):
                    continue
                balance = sum((Decimal(row.clean.get(debit) or "0") - Decimal(row.clean.get(credit) or "0") for row in group), Decimal("0"))
                if abs(balance) > Decimal("0.005"):
                    for row in group:
                        row.flag("error", jcol, "unbalanced", f"Journal {jid} out of balance by {balance}")
        loads.append(Load(ls["name"], template, source, schema, allmap, output, notes,
                          {} if decided is not None else
                          {k: v for k, v in suggestions["mapping"].items() if k not in mappings}))

    # References that cannot be checked are explicitly reported as UNVERIFIED.
    dependency_notes = []
    by_template = defaultdict(list)
    for load in loads:
        by_template[load.template].append(load)
    for load in loads:
        for fieldname, fld in load.fields.items():
            if fld.related and any(r.clean.get(fieldname) for r in load.rows) and not by_template.get(fld.related[0]):
                dependency_notes.append(f"{load.name}.{fieldname}: no {fld.related[0]} parent load; relation unverified")
    # Iterate to propagate rejected parents across child loads.
    for _ in range(max(1, len(loads) + 1)):
        changed = False
        for load in loads:
            for col, fld in load.fields.items():
                if not fld.related or not by_template.get(fld.related[0]):
                    continue
                parents = [row for parent in by_template[fld.related[0]] for row in parent.rows]
                matches = defaultdict(list)
                for parent in parents:
                    key = parent.clean.get(fld.related[1], "")
                    if key:
                        matches[key].append(parent)
                for child in load.rows:
                    key = child.clean.get(col)
                    if not key:
                        continue
                    before = child.rejected
                    if key not in matches:
                        child.flag("error", col, "broken_reference", "Parent identifier absent")
                    elif not any(not p.rejected for p in matches[key]):
                        child.flag("error", col, "rejected_parent", "Referenced parent record is rejected")
                    elif len(matches[key]) > 1:
                        child.flag("error", col, "ambiguous_reference", "Multiple parent rows share this identifier")
                    if child.rejected and not before:
                        changed = True
                    if fld.related[0] == load.template and key == child.clean.get(TEMPLATES[load.template].key):
                        child.flag("error", col, "self_reference", "Worker cannot manage themselves")
        if not changed:
            break
    return {"spec": path, "cfg": cfg, "loads": loads, "dependencies": dependency_notes, "mapping": mstatus}

def summary(result):
    loads = result["loads"]
    total = sum(len(l.rows) for l in loads)
    accepted = sum(sum(not r.rejected for r in l.rows) for l in loads)
    errors = sum(sum(f.severity == "error" for f in row.findings) for load in loads for row in load.rows)
    warnings = sum(sum(f.severity == "warning" for f in row.findings) for load in loads for row in load.rows)
    # Weight issues in hours, count individually. Baseline = 2h per load.
    counts = Counter((l.name, f.code) for l in loads for r in l.rows for f in r.findings if f.severity == "error")
    weights = {"required": 0.12, "invalid": 0.07, "duplicate_id": 0.12, "unbalanced": 0.2,
               "broken_reference": 0.15, "rejected_parent": 0.12, "ambiguous_reference": 0.15, "self_reference": 0.2}
    effort = round(len(loads) * 2 + sum(weights.get(c, 0.1)*n for (_, c), n in counts.items()), 2)
    proj = result["cfg"].get("project", {})
    low, high = float(proj.get("rate_low", 150)), float(proj.get("rate_high", 250))
    mapping = result.get("mapping") or {"current": False, "reason": "Mapping decisions not checked"}
    # READY needs confirmed human mapping decisions; a clean preview on guessed mappings stays UNVERIFIED.
    status = "NOT READY" if errors else "UNVERIFIED" if (result["dependencies"] or total == 0 or not mapping["current"]) else "READY"
    return {"project": proj.get("name", "Untitled migration"), "status": status,
            "total_rows": total, "loadable_rows": accepted, "readiness_percent": round(accepted / total * 100, 1) if total else 0,
            "errors": errors, "warnings": warnings, "estimated_hours": effort,
            "estimated_cost_low": round(effort * low, 2), "estimated_cost_high": round(effort * high, 2),
            "spec_sha256": hashlib.sha256(result["spec"].read_bytes()).hexdigest(),
            "unchecked_dependencies": result["dependencies"],
            "mapping_decisions": mapping,
            "loads": [{"name": l.name, "template": l.template, "source": l.source.name,
                       "rows": len(l.rows), "loadable": sum(not r.rejected for r in l.rows),
                       "rejected": sum(r.rejected for r in l.rows),
                       "warnings": sum(f.severity == "warning" for r in l.rows for f in r.findings),
                       "source_sha256": hashlib.sha256(l.source.read_bytes()).hexdigest(),
                       "mapping": {k: v for k, v in l.mappings.items()},
                       "transformations": sum(len(r.changes) for r in l.rows),
                       "auto_mapped": l.auto_maps, "notes": l.notes,
                       "findings": [{"line": f.line, "column": f.column, "severity": f.severity, "code": f.code,
                                     "message": f.message} for r in l.rows for f in r.findings]}
                      for l in loads], "caveat": "Planning estimate only, not a quote. Templates are illustrative; verify with target account sandbox."}
