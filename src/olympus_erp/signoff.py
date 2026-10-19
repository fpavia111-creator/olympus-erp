"""Themis: simple local approval evidence tied to the exact spec bytes.

Not a digital signature or identity verification; operator must check identity.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def digest(spec):
    return hashlib.sha256(Path(spec).read_bytes()).hexdigest()

def status(spec, receipt=None):
    spec = Path(spec).resolve()
    receipt = Path(receipt) if receipt else spec.with_suffix(".approval.json")
    current = digest(spec)
    if not receipt.exists():
        return {"approved": False, "reason": "No approval receipt", "sha256": current}
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"approved": False, "reason": "Unreadable approval receipt", "sha256": current}
    good = data.get("sha256") == current and data.get("attestation") == "I reviewed and approved this exact mapping specification"
    return {"approved": good, "reason": "Matches approved spec" if good else "Spec was changed, or receipt is invalid",
            "sha256": current, "signer": data.get("signer"), "approved_at": data.get("approved_at"),
            "receipt": str(receipt)}

def approve(spec, signer, attested=False, receipt=None):
    if not attested:
        raise ValueError("Explicit human review acknowledgement required (--attest)")
    if len(signer.strip()) < 2:
        raise ValueError("Provide a human reviewer name")
    spec = Path(spec).resolve()
    target = Path(receipt) if receipt else spec.with_suffix(".approval.json")
    payload = {"system": "Themis", "spec": spec.name, "sha256": digest(spec),
               "signer": signer.strip(), "approved_at": datetime.now(timezone.utc).isoformat(),
               "attestation": "I reviewed and approved this exact mapping specification",
               "note": "Local audit evidence only; not identity-verified or a cryptographic signature."}
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload

def main(argv=None):
    p = argparse.ArgumentParser(prog="themis", description="Themis human spec approval gate")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("status"); q.add_argument("spec"); q.add_argument("--receipt")
    q = sub.add_parser("approve"); q.add_argument("spec"); q.add_argument("--signer", required=True)
    q.add_argument("--attest", action="store_true"); q.add_argument("--receipt")
    args = p.parse_args(argv)
    try:
        if args.cmd == "status":
            value = status(args.spec, args.receipt)
            print(json.dumps(value, indent=2))
            return 0 if value["approved"] else 1
        value = approve(args.spec, args.signer, args.attest, args.receipt)
        print(json.dumps(value, indent=2))
        return 0
    except (OSError, ValueError) as e:
        p.exit(2, f"themis: {e}\n")
