"""Confirmable mapping table: confidence tiers + versioned, hashed human decisions.

Nothing here decides for the user. Suggestions are proposals; a clean or
import-ready artifact is only produced after a person has reviewed every
target field, and fields with ambiguous or low-confidence suggestions were
decided one by one (``explicit``). The decision file is bound to the exact
spec bytes, source-file bytes and header row, so any change makes it stale.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .engine import SpecError, parse_spec, _field, _norm
from .inputs import read_rows
from .templates import TEMPLATES, PRESETS

FORMAT = "olympus.mapping-decisions/1"
ATTESTATION = "I reviewed every target field mapping for these exact source files"
TIER_ORDER = ("HIGH", "MEDIUM", "LOW", "AMBIGUOUS", "NONE")
# Tiers a bulk "accept suggestions" action may confirm. Everything else needs an
# explicit per-field decision.
BULK_TIERS = {"HIGH", "MEDIUM"}


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path) -> str:
    return _sha_bytes(Path(path).read_bytes())


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decisions_path(spec) -> Path:
    return Path(spec).resolve().with_suffix(".mappings.json")


def history_dir(spec) -> Path:
    p = decisions_path(spec)
    return p.with_name(p.stem.replace(".mappings", "") + ".mappings.history")


def _fuzzy(columns, target, aliases):
    names = [_norm(target), *(_norm(a) for a in aliases)]
    out = []
    for col in columns:
        n = _norm(col)
        if not n:
            continue
        score = max(difflib.SequenceMatcher(None, n, x).ratio() for x in names)
        contains = any(len(x) >= 4 and (x in n or n in x) for x in names)
        if score >= 0.8 or contains:
            out.append((round(score, 2), col))
    return [c for _, c in sorted(out, key=lambda t: (-t[0], t[1]))]


def suggest_table(columns, template, preset=None, spec_map=None, fields=None):
    """Return one row per target field with a suggestion and confidence tier.

    HIGH: header equals target name, or a human wrote it in the spec [load.map].
    MEDIUM: exactly one header matches a documented alias.
    LOW: a source-system preset hint or a fuzzy name match (needs explicit review).
    AMBIGUOUS: more than one plausible header (needs explicit review; nothing preselected).
    NONE: no candidate. Required + NONE needs explicit review (map, or knowingly leave unmapped).
    """
    if template not in TEMPLATES:
        raise SpecError(f"Unknown template {template}")
    if preset and preset not in PRESETS:
        raise SpecError(f"Unknown source preset: {preset}")
    spec_map = spec_map or {}
    schema = dict(TEMPLATES[template].fields)
    schema.update(fields or {})
    rows = []
    for target, fld in schema.items():
        aliases = getattr(fld, "aliases", ()) or ()
        alias_norms = {_norm(a) for a in aliases}
        if target in spec_map:
            suggested, candidates, tier, reason = spec_map[target], [], "HIGH", "Declared in spec [load.map] by a person"
        elif target in columns:
            suggested, candidates, tier, reason = target, [target], "HIGH", "Header exactly equals target field"
        else:
            alias = [c for c in columns if _norm(c) in alias_norms or _norm(c) == _norm(target)]
            if len(alias) == 1:
                suggested, candidates, tier, reason = alias[0], alias, "MEDIUM", "Single header matches a documented alias"
            elif len(alias) > 1:
                suggested, candidates, tier, reason = None, alias, "AMBIGUOUS", "Several headers match aliases; choose one"
            else:
                hints = [c for c in columns if preset and PRESETS[preset].get(c) == target]
                fuzzy = [c for c in _fuzzy(columns, target, aliases) if c not in hints]
                cands = hints + fuzzy
                if len(cands) == 1:
                    why = "Source-system preset hint" if hints else "Similar header name only"
                    suggested, candidates, tier, reason = cands[0], cands, "LOW", why + "; confirm explicitly"
                elif cands:
                    suggested, candidates, tier, reason = None, cands, "AMBIGUOUS", "Several weak candidates; choose one"
                else:
                    suggested, candidates, tier, reason = None, [], "NONE", "No candidate header"
        required = bool(getattr(fld, "required", False))
        review = tier in ("LOW", "AMBIGUOUS") or (tier == "NONE" and required)
        rows.append({"target": target, "required": required, "type": getattr(fld, "kind", "text"),
                     "suggested": suggested, "candidates": candidates, "tier": tier, "reason": reason,
                     "review_required": review})
    return rows


def _loads(spec):
    path, cfg = parse_spec(spec)
    proj = cfg.get("project", {})
    result = []
    for ls in cfg["load"]:
        template = ls.get("template")
        if template not in TEMPLATES:
            raise SpecError(f"Unknown template: {template}")
        src = Path(ls.get("source", ""))
        source = src if src.is_absolute() else (path.parent / src).resolve()
        headers, _ = read_rows(source, ls.get("sheet"))
        fields = {k: _field(v) for k, v in (ls.get("fields") or {}).items()}
        table = suggest_table(headers, template, ls.get("preset", proj.get("source_system")),
                              ls.get("map") or {}, fields)
        result.append({"name": ls["name"], "template": template, "source": str(src),
                       "source_path": source, "source_sha256": _sha_file(source), "headers": headers,
                       "rows": table})
    return path, result


def propose(spec):
    """The interactive mapping table for every load in a spec, plus current decision status."""
    path, loads = _loads(spec)
    return {"spec": path.name, "spec_sha256": _sha_file(path),
            "loads": [{k: v for k, v in l.items() if k != "source_path"} for l in loads],
            "decisions": status(path),
            "note": "Suggestions only. Review each row; ambiguous/low-confidence rows need an explicit choice."}


def _validate_source(value, headers):
    if value is None or value == "":
        return None
    cols = value if isinstance(value, list) else [value]
    if not cols or any(not isinstance(c, str) or c not in headers for c in cols):
        raise ValueError(f"Mapping source must be existing header name(s): {value!r}")
    return value if isinstance(value, list) else value


def confirm(spec, reviewer, decisions, attest=False):
    """Write a new version of the decision file.

    ``decisions`` = {load_name: {target: {"source": header | [headers] | None,
                                           "reviewed": True, "explicit": bool}}}
    """
    if not attest:
        raise ValueError("Explicit human review acknowledgement required (attest)")
    if not isinstance(reviewer, str) or not 2 <= len(reviewer.strip()) <= 120:
        raise ValueError("Provide the human reviewer's name (2-120 characters)")
    if not isinstance(decisions, dict):
        raise ValueError("decisions must be an object keyed by load name")
    path, loads = _loads(spec)
    names = {l["name"] for l in loads}
    if set(decisions) - names:
        raise ValueError("Unknown load(s): " + ", ".join(sorted(set(decisions) - names)))
    now = datetime.now(timezone.utc).isoformat()
    out_loads, problems = {}, []
    for load in loads:
        given = decisions.get(load["name"])
        if not isinstance(given, dict):
            problems.append(f"{load['name']}: no decisions supplied")
            continue
        targets = {r["target"] for r in load["rows"]}
        if set(given) - targets:
            problems.append(f"{load['name']}: unknown target field(s) " + ", ".join(sorted(set(given) - targets)))
        fields = {}
        for row in load["rows"]:
            t = row["target"]
            d = given.get(t)
            if not isinstance(d, dict) or d.get("reviewed") is not True:
                problems.append(f"{load['name']}.{t}: not reviewed")
                continue
            if row["review_required"] and d.get("explicit") is not True:
                problems.append(f"{load['name']}.{t}: {row['tier']} confidence requires an explicit per-field decision")
                continue
            try:
                source = _validate_source(d.get("source"), load["headers"])
            except ValueError as exc:
                problems.append(f"{load['name']}.{t}: {exc}")
                continue
            decision = "unmapped" if source is None else ("accepted" if source == row["suggested"] else "overridden")
            fields[t] = {"source": source, "decision": decision, "suggested": row["suggested"],
                         "tier": row["tier"], "required": row["required"], "explicit": d.get("explicit") is True}
        out_loads[load["name"]] = {"template": load["template"], "source": load["source"],
                                   "source_sha256": load["source_sha256"], "headers": load["headers"],
                                   "fields": fields}
    if problems:
        raise ValueError("Mapping not confirmed: " + "; ".join(problems[:20]) +
                         (f" (+{len(problems)-20} more)" if len(problems) > 20 else ""))
    target = decisions_path(path)
    previous = None
    version = 1
    if target.exists():
        try:
            old = json.loads(target.read_text(encoding="utf-8"))
            previous, version = old.get("sha256"), int(old.get("version", 0)) + 1
            hist = history_dir(path)
            hist.mkdir(exist_ok=True)
            shutil.copy2(target, hist / f"v{int(old.get('version', 0))}.json")
        except (ValueError, OSError, json.JSONDecodeError):
            raise ValueError("Existing mapping decision file is unreadable; move it aside before re-confirming")
    body = {"format": FORMAT, "version": version, "spec": path.name, "spec_sha256": _sha_file(path),
            "reviewer": reviewer.strip(), "decided_at": now, "previous_sha256": previous,
            "attestation": ATTESTATION, "loads": out_loads,
            "note": "Local evidence; reviewer identity is not verified."}
    body["sha256"] = _sha_bytes(_canonical(body))
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return status(path)


def _read(spec):
    target = decisions_path(spec)
    if not target.exists():
        return None, "No mapping decisions recorded"
    try:
        body = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "Mapping decision file unreadable"
    if not isinstance(body, dict) or body.get("format") != FORMAT:
        return None, "Unknown mapping decision format"
    claimed = body.get("sha256")
    check = {k: v for k, v in body.items() if k != "sha256"}
    if claimed != _sha_bytes(_canonical(check)):
        return None, "Mapping decision file was edited after confirmation (hash mismatch)"
    return body, None


def status(spec):
    """Is there a current, intact decision for every load and field of this spec?"""
    path = Path(spec).resolve()
    body, err = _read(path)
    base = {"file": decisions_path(path).name, "current": False}
    if err:
        return base | {"reason": err}
    base |= {"version": body.get("version"), "sha256": body.get("sha256"), "reviewer": body.get("reviewer"),
             "decided_at": body.get("decided_at")}
    try:
        _, loads = _loads(path)
    except (SpecError, ValueError, OSError) as exc:
        return base | {"reason": f"Cannot read spec/sources: {exc}"}
    stale = []
    if body.get("spec_sha256") != _sha_file(path):
        stale.append("spec changed since confirmation")
    recorded = body.get("loads") or {}
    for l in loads:
        r = recorded.get(l["name"])
        if not r:
            stale.append(f"{l['name']}: no decision")
            continue
        if r.get("template") != l["template"] or r.get("source") != l["source"]:
            stale.append(f"{l['name']}: template or source path changed")
        if r.get("source_sha256") != l["source_sha256"]:
            stale.append(f"{l['name']}: source file changed")
        if r.get("headers") != l["headers"]:
            stale.append(f"{l['name']}: header row changed")
        missing = {x["target"] for x in l["rows"]} - set(r.get("fields") or {})
        if missing:
            stale.append(f"{l['name']}: undecided field(s) " + ", ".join(sorted(missing)))
    if set(recorded) - {l["name"] for l in loads}:
        stale.append("decisions include loads no longer in spec")
    if stale:
        return base | {"reason": "Stale: " + "; ".join(stale), "stale": stale}
    return base | {"current": True, "reason": "All fields reviewed for the current spec and source files"}


def decided_mappings(spec):
    """{load: {target: header | [headers]}} from a current decision file, or raise."""
    st = status(spec)
    if not st["current"]:
        raise ValueError("Mapping decisions missing or stale: " + st["reason"])
    body, _ = _read(spec)
    return {name: {t: f["source"] for t, f in load["fields"].items() if f["source"] is not None}
            for name, load in body["loads"].items()}


def accept_suggestions(proposal, overrides=None, unmapped=()):
    """CLI helper: build a decisions payload.

    HIGH/MEDIUM suggestions are accepted in bulk (the human ran the command);
    every review-required field must appear in ``overrides`` or ``unmapped``,
    otherwise :func:`confirm` refuses.
    """
    overrides = overrides or {}
    out = {}
    for load in proposal["loads"]:
        fields = {}
        for row in load["rows"]:
            key_full, key = f"{load['name']}.{row['target']}", row["target"]
            if key_full in overrides or key in overrides:
                fields[key] = {"source": overrides.get(key_full, overrides.get(key)), "reviewed": True, "explicit": True}
            elif key_full in unmapped or key in unmapped:
                fields[key] = {"source": None, "reviewed": True, "explicit": True}
            elif row["tier"] in BULK_TIERS:
                fields[key] = {"source": row["suggested"], "reviewed": True, "explicit": False}
            elif row["tier"] == "NONE" and not row["required"]:
                fields[key] = {"source": None, "reviewed": True, "explicit": False}
            else:
                fields[key] = {"source": row["suggested"], "reviewed": True, "explicit": False}
        out[load["name"]] = fields
    return out
