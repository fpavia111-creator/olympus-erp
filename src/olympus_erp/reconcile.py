"""Poseidon: deterministic, read-only source/target trial-load reconciliation.

Compares explicit business keys and one numeric field. This is a *sample* reconciliation,
not a complete GL/subledger close or vendor certification. Files are never modified.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .inputs import read_rows


def _amount(raw: str) -> Decimal:
    s = str(raw).strip().replace(",", "").replace("$", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        v = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount {raw!r}") from exc
    if not v.is_finite():
        raise ValueError("Nonfinite amount")
    return v


def _indexed(path, key_field, amount_field, sheet=None):
    headers, rows = read_rows(path, sheet)
    if key_field not in headers or amount_field not in headers:
        raise ValueError(f"Missing key/amount field in {Path(path).name}; available: {headers}")
    amounts = defaultdict(lambda: Decimal("0"))
    counts = defaultdict(int)
    missing = []
    invalid = []
    for line, row in rows:
        key = row[key_field].strip()
        if not key:
            missing.append(line)
            continue
        try:
            amount = _amount(row[amount_field])
        except ValueError:
            invalid.append(line)
            continue
        amounts[key] += amount
        counts[key] += 1
    return amounts, counts, missing, invalid, len(rows)


def reconcile(source, target, source_key, target_key, source_amount, target_amount,
              tolerance="0.01", source_sheet=None, target_sheet=None):
    try:
        tol = Decimal(str(tolerance))
    except InvalidOperation as exc:
        raise ValueError("tolerance must be a finite nonnegative decimal") from exc
    if not tol.is_finite() or tol < 0:
        raise ValueError("tolerance must be a finite nonnegative decimal")
    src, sc, sm, si, sn = _indexed(source, source_key, source_amount, source_sheet)
    dst, dc, dm, di, dn = _indexed(target, target_key, target_amount, target_sheet)
    allkeys = sorted(src.keys() | dst.keys())
    differences = []
    matched = 0
    for k in allkeys:
        a, b = src.get(k), dst.get(k)
        if a is not None and b is not None and abs(a - b) <= tol and sc[k] == dc[k]:
            matched += 1
            continue
        differences.append({"key": k,
                            "source_amount": None if a is None else str(a),
                            "target_amount": None if b is None else str(b),
                            "source_count": sc[k], "target_count": dc[k],
                            "variance": None if a is None or b is None else str(b - a),
                            "issue": "missing_target" if b is None else "new_target" if a is None else
                            "count_mismatch" if sc[k] != dc[k] else "amount_mismatch"})
    src_total = sum(src.values(), Decimal("0"))
    dst_total = sum(dst.values(), Decimal("0"))
    flags = []
    if sm or dm: flags.append("Blank business keys; some rows were excluded")
    if si or di: flags.append("Invalid amounts; some rows were excluded")
    return {"agent": "Poseidon", "status": "RECONCILED" if not differences and not flags else "NOT RECONCILED",
            "reconciliation_scope": "Selected key, amount and record count only; not a complete ledger reconciliation",
            "source": Path(source).name, "target": Path(target).name,
            "source_rows": sn, "target_rows": dn,
            "matched_keys": matched, "different_keys": len(differences),
            "source_total": str(src_total), "target_total": str(dst_total), "net_variance": str(dst_total - src_total),
            "missing_keys_lines": {"source": sm[:100], "target": dm[:100]},
            "invalid_amount_lines": {"source": si[:100], "target": di[:100]},
            "differences": differences[:500], "total_differences": len(differences),
            "truncated": len(differences) > 500, "warnings": flags,
            "note": "Independent business-owner validation remains required. No vendor API was contacted."}
