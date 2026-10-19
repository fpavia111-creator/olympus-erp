"""Argus: local-only incident queue with tamper-evident (not tamper-proof) hash chain.

No email/pager, ERP monitoring, authentication, or guaranteed SLA; human-entered tickets.
"""
from __future__ import annotations
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

SEVERITIES = {"critical", "high", "medium", "low"}
STATES = {"open", "investigating", "mitigated", "resolved"}
_APPEND_LOCK = threading.Lock()  # dashboard uses a threading HTTP server

def _digest(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _path(workspace):
    return Path(workspace).resolve() / "olympus_incidents.jsonl"

def events(workspace):
    file = _path(workspace)
    if not file.exists(): return []
    prev = "0" * 64
    result = []
    for num, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        try: obj = json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"Corrupted incident log line {num}") from exc
        mac = obj.pop("hash", None)
        if obj.get("prev") != prev or mac != _digest(obj):
            raise ValueError(f"Incident log hash chain broken at line {num}")
        obj["hash"] = mac
        result.append(obj)
        prev = mac
    return result

def listing(workspace):
    entries = events(workspace)
    latest = {}
    for e in entries:
        if e["action"] == "create":
            latest[e["id"]] = {"id": e["id"], "title": e["title"], "severity": e["severity"],
                               "owner": e["owner"], "status": "open", "opened_at": e["time"]}
        elif e["id"] in latest:
            latest[e["id"]]["status"] = e["status"]
            latest[e["id"]]["updated_at"] = e["time"]
    issues = list(latest.values())
    return {"total": len(issues), "unresolved": sum(i["status"] != "resolved" for i in issues),
            "events": len(entries), "tickets": issues,
            "caveat": "Manual local incidents; no live monitoring, paging, access controls or SLA enforcement"}

def _append(workspace, item):
    root = Path(workspace).resolve()
    if not root.is_dir(): raise ValueError("Workspace does not exist")
    with _APPEND_LOCK:
        old = events(root)
        item["prev"] = old[-1]["hash"] if old else "0" * 64
        item["hash"] = _digest(item)
        with _path(root).open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, sort_keys=True) + "\n")
    return item

def create(workspace, title, severity, owner):
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 200: raise ValueError("Ticket title requires 3–200 chars")
    if not isinstance(owner, str) or not 2 <= len(owner.strip()) <= 120: raise ValueError("Owner requires 2–120 chars")
    if severity not in SEVERITIES: raise ValueError("Invalid severity")
    from uuid import uuid4
    return _append(workspace, {"action":"create", "id":uuid4().hex[:12], "title":title.strip(),
                               "severity":severity, "owner":owner.strip(), "time":datetime.now(timezone.utc).isoformat()})

def change(workspace, ticket_id, status, actor):
    if status not in STATES: raise ValueError("Invalid status")
    if not isinstance(actor, str) or not 2 <= len(actor.strip()) <= 120: raise ValueError("Actor requires 2–120 chars")
    current = {i["id"]: i for i in listing(workspace)["tickets"]}
    if ticket_id not in current: raise ValueError("Ticket not found")
    if current[ticket_id]["status"] == "resolved" and status != "resolved":
        raise ValueError("Resolved tickets cannot reopen; create a linked follow-up ticket")
    return _append(workspace, {"action":"update", "id":ticket_id, "status":status,
                               "actor":actor.strip(), "time":datetime.now(timezone.utc).isoformat()})
