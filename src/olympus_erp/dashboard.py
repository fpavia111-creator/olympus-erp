"""Olympus ERP v0.4: single-user, loopback-only four-stage local dashboard.

Not a production website, not authenticated, not multi-tenant. No telemetry, email,
external system API, remote CDN, or model API. Browser downloads are generated docs only.
"""
from __future__ import annotations
import base64
import io
import json
import secrets
import shutil
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from datetime import datetime, timezone
from . import erp_agents, incidents, mapping, project_summary, reconcile, uat_evidence
from .reporting import build
from .engine import run, summary, suggest_mapping
from .templates import TEMPLATES
from .inputs import read_rows, profile
from .cli import _init

MAX_JSON_BYTES = 4_800_000
MAX_FILE_BYTES = 3_000_000


def _str(value, max_chars=180):
    if not isinstance(value, str) or len(value.strip()) > max_chars:
        raise ValueError(f"Expected a text value of at most {max_chars} characters")
    return value.strip()


def _list(s):
    return [x.strip() for x in _str(s, 2000).split("\n") if x.strip()][:30]


def _project_dir(root, pid):
    if not isinstance(pid, str) or len(pid) != 32 or not all(c in "0123456789abcdef" for c in pid):
        raise ValueError("Invalid project ID")
    directory = root / "projects" / pid
    if not directory.is_dir():
        raise ValueError("Project does not exist")
    return directory


def _upload_blob(directory, extension, encoded, allowed, max_bytes=MAX_FILE_BYTES):
    if not isinstance(extension, str) or extension not in allowed:
        raise ValueError("Unsupported file extension")
    if not isinstance(encoded, str) or len(encoded) > MAX_JSON_BYTES:
        raise ValueError("Invalid uploaded file")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Invalid uploaded file encoding") from exc
    if not blob or len(blob) > max_bytes:
        raise ValueError(f"File must be 1 byte to {max_bytes} bytes")
    if extension == ".xlsx" and not blob.startswith(b"PK"):
        raise ValueError("Invalid XLSX container")
    if extension == ".pdf" and not blob.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF header")
    if extension == ".png" and not blob.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG header")
    directory.mkdir(exist_ok=True)
    path=directory/(uuid4().hex+extension)
    path.write_bytes(blob)
    return path


DEMO_EXPORT = (
    "Customer Number,Customer ID,Customer Name,E-mail,Email Address,State,Country Name,Payment Terms,Credit Lim\n"
    "1001,C1001,Brightline Fabrication LLC,ops@brightline.example.com,OPS@BRIGHTLINE.EXAMPLE.COM,Illinois,United States,Net 30,\"$10,000.00\"\n"
    "1002,C1002,Cascade Pumps,cascade@pumps,ar@cascade.example.com,TX,USA,Net 30,500\n"
    "1003,C1003,Omega Metal,contact@omegametal.example.com,,Texs,USA,Net 15,\"(2,500.00)\"\n"
    "1004,C1004,Brightline Fabrication,contact@brightline.example.com,,IL,USA,Net 30,15000\n"
    "1005,C1005,Valid Manufacturing,valid@example.com,,Texas,United States,Net 30,\"$1,000\"\n")
DEMO_CUTOVER = {"timezone": "America/Chicago", "window_start": "2027-04-16T18:00", "window_end": "2027-04-18T06:00",
                "backup_taken_by": "2027-04-16T17:00", "backup_method": "Full sandbox and legacy database export, restore-tested",
                "rollback_trigger": "Opening balances not reconciled or a P1 incident by the rollback deadline",
                "rollback_method": "Re-point users to the legacy system; void imported records",
                "rollback_deadline": "2027-04-17T22:00", "cutover_owner": "Dana Example (fictional)",
                "backup_owner": "Lee Example (fictional)", "rollback_owner": "Sam Example (fictional)"}
_CUTOVER_KEYS = tuple(k for k, _ in erp_agents.CUTOVER_OWNER_FIELDS) + erp_agents.CUTOVER_TEXT_FIELDS + erp_agents.CUTOVER_TIME_FIELDS


def _hexid(value, what):
    if not isinstance(value, str) or len(value) != 32 or not all(c in "0123456789abcdef" for c in value):
        raise ValueError("Invalid " + what)
    return value


def _cutover(req):
    raw = req.get("cutover") or {}
    if not isinstance(raw, dict):
        raise ValueError("cutover must be an object")
    out = {}
    for key in _CUTOVER_KEYS:
        v = raw.get(key, "")
        if v in (None, ""):
            continue
        out[key] = _str(v, 200)
    if set(raw) - set(_CUTOVER_KEYS):
        raise ValueError("Unknown cutover field")
    erp_agents.validate_cutover(out)
    return out


def _write_project(directory, p):
    erp_agents.validate_cutover(p.get("cutover") or {})
    (directory / "project.json").write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")


def _spec_path(directory, spec_id):
    spec = directory / (_hexid(spec_id, "spec identifier") + ".toml")
    if not spec.is_file():
        raise ValueError("Diagnosed file not found; diagnose it again")
    return spec


def _decisions(req, load_name):
    raw = req.get("decisions")
    if not isinstance(raw, dict) or not 0 < len(raw) <= 80:
        raise ValueError("decisions must be an object with one entry per target field")
    out = {}
    for target, d in raw.items():
        if not isinstance(target, str) or len(target) > 120 or not isinstance(d, dict):
            raise ValueError("Invalid mapping decision")
        src = d.get("source")
        if isinstance(src, list):
            if not 0 < len(src) <= 5 or any(not isinstance(x, str) or len(x) > 200 for x in src):
                raise ValueError("Invalid combined source columns")
        elif src is not None and (not isinstance(src, str) or len(src) > 200):
            raise ValueError("Invalid source column")
        out[target] = {"source": src or None, "reviewed": d.get("reviewed") is True, "explicit": d.get("explicit") is True}
    return {load_name: out}


def _mapping_view(spec):
    proposal = mapping.propose(spec)
    load = proposal["loads"][0]
    if proposal["decisions"].get("current"):
        body = json.loads(mapping.decisions_path(spec).read_text(encoding="utf-8"))
        decided = ((body.get("loads") or {}).get(load["name"]) or {}).get("fields") or {}
        load = load | {"rows": [r | {"decided": {"source": decided[r["target"]].get("source"),
                                                 "decision": decided[r["target"]].get("decision")}}
                                if r["target"] in decided else r for r in load["rows"]]}
    return {"spec_id": spec.stem, "load": load["name"], "template": load["template"], "headers": load["headers"],
            "source_sha256": load["source_sha256"], "rows": load["rows"], "decisions": proposal["decisions"]}


def command(root, req):
    """Process a validated local UI action. No paths supplied by the browser."""
    if not isinstance(req, dict): raise ValueError("JSON must be an object")
    action = req.get("action")
    if action in ("create_project", "demo_project"):
        if action == "create_project":
            p = {"project_name":_str(req.get("project_name")), "company_name":_str(req.get("company_name")),
                 "target_system":_str(req.get("target_system")), "industry":_str(req.get("industry", "")),
                 "source_systems":_list(req.get("source_systems", "")), "workflows":_list(req.get("workflows", "")),
                 "data_objects":_list(req.get("data_objects", "")), "pain_points":_list(req.get("pain_points", ""))}
            if not all(p[k] for k in ("project_name", "company_name", "target_system")):
                raise ValueError("Project, company and target system are required")
            cut = _cutover(req)
            if cut: p["cutover"] = cut
            note = "Saved locally; no vendor connection"
        else:
            # Installed wheels do not include examples; inline self-contained synthetic demo.
            p = {"project_name":"Olympus manufacturing demo", "company_name":"Demo Manufacturing (fictional)",
                 "target_system":"NetSuite", "industry":"Manufacturing", "source_systems":["QuickBooks", "Legacy spreadsheets"],
                 "workflows":["Order-to-cash", "Procure-to-pay"], "data_objects":["customers", "items", "invoices"],
                 "cutover": dict(DEMO_CUTOVER)}
            note = "Fictional demo, no real customer data"
        pid = uuid4().hex
        directory = root / "projects" / pid
        directory.mkdir(parents=True, exist_ok=False)
        _write_project(directory, p)
        return {"id":pid, "assessment":erp_agents.assess_project(p), "cutover": p.get("cutover", {}), "note":note}
    if action == "delete_project":
        directory = _project_dir(root, req.get("id"))
        if directory.is_symlink(): raise ValueError("Refusing to delete linked project directory")
        p = erp_agents.load_project(directory / "project.json")
        if req.get("confirm_name") != p["project_name"]:
            raise ValueError("Exact project-name confirmation required")
        shutil.rmtree(directory)
        return {"deleted_project":req.get("id"),
                "note":"Local directory deleted, including its uploads, builds, UAT evidence and incidents; does not securely erase recovered disk copies or backups"}
    if action == "list_projects":
        projects=[]
        for folder in sorted((root/"projects").glob("*/project.json")) if (root/"projects").exists() else []:
            try:
                p=erp_agents.load_project(folder)
                projects.append({"id":folder.parent.name, "name":p["project_name"], "company":p["company_name"]})
            except (ValueError, OSError): continue
        return {"projects":projects[-25:], "templates":sorted(TEMPLATES)}
    if action == "reconcile":
        directory = _project_dir(root, req.get("id"))
        folder=directory/"reconciliation_inputs"
        files=[]
        try:
            for side in ("source", "target"):
                files.append(_upload_blob(folder, req.get(side+"_extension"),req.get(side+"_data_base64"),
                                          {".csv", ".xlsx"}, 1_500_000))
            result = reconcile.reconcile(files[0], files[1], _str(req.get("source_key"),100),
                      _str(req.get("target_key"),100),_str(req.get("source_amount"),100),
                      _str(req.get("target_amount"),100),_str(req.get("tolerance", "0.01"),40))
        except Exception:
            for file in files: file.unlink(missing_ok=True)
            raise
        record = {**result, "source": files[0].name, "target": files[1].name,
                  "source_sha256": project_summary._sha(files[0]), "target_sha256": project_summary._sha(files[1]),
                  "recorded_at": datetime.now(timezone.utc).isoformat()}
        (directory / "reconciliations").mkdir(exist_ok=True)
        (directory / "reconciliations" / (uuid4().hex + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record
    if action == "uat_record":
        directory = _project_dir(root, req.get("id"))
        evidence=None
        try:
            if req.get("data_base64"):
                evidence=_upload_blob(directory/"uat_evidence",req.get("extension"),req.get("data_base64"),
                                      {".txt", ".pdf", ".png", ".json", ".csv"})
            steps = req.get("step_results") or {}
            if not isinstance(steps, dict) or len(steps) > 20: raise ValueError("Invalid step results")
            link = req.get("evidence_link") or None
            return uat_evidence.record(directory/"project.json",_str(req.get("case_id"),40),
                  _str(req.get("result"),12),_str(req.get("reviewer"),120),evidence,root,
                  executed_at=_str(req.get("executed_at",""),40) or None,
                  evidence_link=_str(link,500) if link else None,
                  step_results={_str(k,60): _str(v,12) for k, v in steps.items()},
                  notes=_str(req.get("notes",""),2000) or None)
        except Exception:
            if evidence is not None: evidence.unlink(missing_ok=True)
            raise
    if action in {"assess", "make_pack", "uat", "diagnose", "demo_diagnose", "confirm_mapping", "build",
                  "summary", "update_cutover", "mapping_table"}:
        directory = _project_dir(root, req.get("id"))
        file=directory/"project.json"
        p=erp_agents.load_project(file)
        if action == "assess": return erp_agents.assess_project(p) | {"cutover": p.get("cutover", {}),
                                                                      "cutover_readiness": erp_agents.cutover_readiness(p)}
        if action == "update_cutover":
            p["cutover"] = _cutover(req)
            _write_project(directory, p)
            return {"cutover": p["cutover"], "cutover_readiness": erp_agents.cutover_readiness(p),
                    "note": "Project facts changed: previously recorded UAT results are now stale and need re-review."}
        if action == "make_pack":
            packname = uuid4().hex
            target=directory/"packs"/packname
            result=erp_agents.pack(p, target)
            return {"pack":packname, "files":result["files"], "warning":"Draft outputs. A person must verify tenant details and approvals."}
        if action == "uat": return uat_evidence.status(file)
        if action == "summary":
            s = project_summary.collect_evidence(directory)
            return {"summary": s, "markdown": project_summary.markdown(s)}
        if action in ("diagnose", "demo_diagnose"):
            if action == "demo_diagnose":
                template, extension = "netsuite.customer", ".csv"
                data = base64.b64encode(DEMO_EXPORT.encode()).decode()
            else:
                template = req.get("template")
                extension = _str(req.get("extension", ""), 12).lower()
                data = req.get("data_base64")
            if template not in TEMPLATES: raise ValueError("Select a valid migration template")
            if extension not in (".csv", ".xlsx"): raise ValueError("Only .csv and .xlsx are allowed")
            path = _upload_blob(directory / "incoming", extension, data, {".csv", ".xlsx"})
            spec = None
            try:
                headers, _=read_rows(path)
                spec=directory/(uuid4().hex+".toml")
                _init(spec, p["project_name"], [f"{template}=incoming/{path.name}"])
                result=summary(run(spec))
                return {"profile":profile(path) | {"file": path.name}, "mapping":_mapping_view(spec), "results":result,
                        "note":"Preview on suggested mappings. Confirm every row in the mapping table before import-ready files can be built."}
            except Exception:
                path.unlink(missing_ok=True)
                if spec is not None: spec.unlink(missing_ok=True)
                raise
        spec = _spec_path(directory, req.get("spec"))
        if action == "mapping_table":
            return _mapping_view(spec)
        if action == "confirm_mapping":
            view = _mapping_view(spec)
            st = mapping.confirm(spec, _str(req.get("reviewer"), 120), _decisions(req, view["load"]),
                                 attest=req.get("attest") is True)
            return {"decisions": st, "preview": summary(run(spec)), "mapping": _mapping_view(spec)}
        if action == "build":
            result = run(spec)
            if not result["mapping"]["current"]:
                raise ValueError("Confirm the mapping table first: " + result["mapping"]["reason"])
            build_id = uuid4().hex
            out = directory / "builds" / build_id
            try:
                import reportlab  # noqa: F401
                with_pdf = True
            except ImportError:
                with_pdf = False
            s = build(result, out, pdf=with_pdf, brand="Hermes | Olympus ERP")
            (out / "manifest.json").write_text(json.dumps({"spec": spec.name, "built_at": datetime.now(timezone.utc).isoformat(),
                                                           "mapping_sha256": result["mapping"].get("sha256")}, indent=2), encoding="utf-8")
            return {"build": build_id, "status": s["status"], "total_rows": s["total_rows"], "loadable_rows": s["loadable_rows"],
                    "errors": s["errors"], "files": sorted(x.name for x in out.iterdir()),
                    "note": "Clean files contain only rows that passed every check; rejects keep original values and line numbers; changes.csv logs every transformed value."}
    if action in ("incidents", "incident_create", "incident_update"):
        # Incidents belong to a project folder (deleted with it); legacy calls without id use the workspace queue.
        base = _project_dir(root, req.get("id")) if req.get("id") is not None else root
        if action == "incidents": return incidents.listing(base)
        if action == "incident_create":
            return incidents.create(base, _str(req.get("title"), 200), _str(req.get("severity"), 12), _str(req.get("owner"), 120))
        return incidents.change(base, _str(req.get("ticket_id"), 20), _str(req.get("status"), 30), _str(req.get("actor"), 120))
    raise ValueError("Unknown operation")


def make_handler(root, token, port):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OlympusLocal/0.4"
        def _valid_host(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            good = {f"127.0.0.1:{port}", f"localhost:{port}"}
            return host in good and (origin is None or origin in {"http://"+s for s in good})
        def _send(self, status, body, content_type="application/json", extra=None):
            if isinstance(body, str): body=body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for k,v in (extra or {}).items(): self.send_header(k,v)
            self.end_headers()
            self.wfile.write(body)
        def _json(self, code, obj): self._send(code, json.dumps(obj, ensure_ascii=False).encode())
        def _authorized(self): return secrets.compare_digest(self.headers.get("X-Olympus-Token", "").encode(), token.encode())
        def do_GET(self):
            if not self._valid_host(): return self._json(403,{"error":"Invalid host/origin"})
            parsed=urlsplit(self.path)
            if parsed.path == "/":
                nonce=secrets.token_hex(16)
                html=UI.replace("__TOKEN__",token).replace("__NONCE__",nonce)
                policy=f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
                return self._send(200,html,"text/html; charset=utf-8",{"Content-Security-Policy":policy})
            if parsed.path == "/api/bundle":
                if not self._authorized(): return self._json(403,{"error":"Invalid local token"})
                qs=parse_qs(parsed.query)
                try:
                    directory=_project_dir(root,qs.get("project",[None])[0])
                    pack_id=_hexid(qs.get("pack",[None])[0],"pack identifier")
                    pack=directory/"packs"/pack_id
                    if not pack.is_dir(): raise ValueError("Pack not found")
                    output=io.BytesIO()
                    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                        for item in sorted(pack.iterdir()):
                            if item.is_file() and item.suffix in (".json",".md") and not item.is_symlink():
                                archive.write(item,arcname=item.name)
                    return self._send(200, output.getvalue(),"application/zip",{"Content-Disposition":'attachment; filename="olympus_erp_plan.zip"'})
                except (ValueError,OSError) as exc: return self._json(400,{"error":str(exc)})
            if parsed.path in ("/api/build", "/api/summary"):
                if not self._authorized(): return self._json(403,{"error":"Invalid local token"})
                qs=parse_qs(parsed.query)
                try:
                    directory=_project_dir(root,qs.get("project",[None])[0])
                    if parsed.path == "/api/build":
                        build_dir=directory/"builds"/_hexid(qs.get("build",[None])[0],"build identifier")
                        if not build_dir.is_dir() or build_dir.is_symlink(): raise ValueError("Build not found")
                        output=io.BytesIO()
                        with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                            for item in sorted(build_dir.iterdir()):
                                if item.is_file() and not item.is_symlink() and item.suffix in (".csv",".json",".md",".pdf"):
                                    archive.write(item,arcname=item.name)
                        return self._send(200, output.getvalue(),"application/zip",{"Content-Disposition":'attachment; filename="olympus_build.zip"'})
                    fmt=qs.get("format",["md"])[0]
                    s=project_summary.collect_evidence(directory)
                    if fmt=="json":
                        return self._send(200, json.dumps(s,indent=2,ensure_ascii=False),"application/json",{"Content-Disposition":'attachment; filename="project_summary.json"'})
                    if fmt=="md":
                        return self._send(200, project_summary.markdown(s),"text/markdown; charset=utf-8",{"Content-Disposition":'attachment; filename="project_summary.md"'})
                    if fmt=="pdf":
                        import tempfile
                        with tempfile.TemporaryDirectory() as t:
                            project_summary.pdf(s, Path(t)/"s.pdf")
                            data=(Path(t)/"s.pdf").read_bytes()
                        return self._send(200, data,"application/pdf",{"Content-Disposition":'attachment; filename="project_summary.pdf"'})
                    raise ValueError("Unknown summary format")
                except (ValueError,OSError,RuntimeError) as exc: return self._json(400,{"error":str(exc)})
            return self._json(404,{"error":"Not found"})
        def do_POST(self):
            if not self._valid_host() or not self._authorized():
                return self._json(403,{"error":"Invalid local origin or token"})
            if self.path != "/api/action" or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(404,{"error":"Unsupported endpoint/content type"})
            try:
                n=int(self.headers.get("Content-Length", "0"))
                if not 0<n<=MAX_JSON_BYTES:
                    return self._json(413,{"error":"Request exceeds 4.8MB limit"})
                req=json.loads(self.rfile.read(n))
                result=command(root,req)
                return self._json(200,{"ok":True,"data":result})
            except (ValueError,TypeError,KeyError,OSError,RuntimeError,json.JSONDecodeError) as exc:
                return self._json(400,{"ok":False,"error":str(exc)})
        def log_message(self, fmt, *args):
            # Exclude path and data from console to limit accidental sensitive-data logging.
            pass
    return Handler


def serve(workspace=".", port=8765):
    root=Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    token=secrets.token_hex(32)
    try:
        server=ThreadingHTTPServer(("127.0.0.1", port),make_handler(root,token,port))
    except OSError as exc:
        raise SystemExit(f"olympus-web: cannot listen on 127.0.0.1:{port} ({exc.strerror or exc}). "
                         "Is another program using it? Try --port 8766.") from exc
    print(f"Olympus LOCAL demo: http://127.0.0.1:{port}",flush=True)
    print(f"Workspace: {root}\nDo not expose this demo to the internet. Press Ctrl+C to stop.",flush=True)
    try: server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()

UI = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Olympus ERP — Migration Integrity Workspace</title>
<style nonce="__NONCE__">
:root{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#ebe8dc;background:#0c0e19;font-size:15px}*{box-sizing:border-box}
body{margin:0}button,input,select,textarea{font:inherit}button{cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}
header{border-bottom:1px solid #34323e;background:#131622;padding:20px max(24px,calc((100vw - 1180px)/2))}
.brand{display:flex;justify-content:space-between;align-items:center;gap:12px}h1{font-family:Georgia,serif;font-size:30px;color:#efc983;margin:0;letter-spacing:.05em}small,.muted{color:#a6a7b6}
main{max-width:1180px;margin:0 auto;padding:26px 20px 65px}.intro{max-width:860px;font-size:16px;color:#c8c9d2;line-height:1.6}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:25px 0}.tab{border:1px solid #41404e;background:#151827;color:#dfd8d1;border-radius:12px;padding:12px 16px}.tab[aria-selected="true"]{background:#bc9256;color:#11121c;font-weight:700;border-color:#bc9256}
.panel{display:none}.panel.active{display:block}.columns{display:grid;grid-template-columns:1.1fr .9fr;gap:20px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 14px}@media(max-width:760px){.columns,.grid3{grid-template-columns:1fr}}
.card{background:#171a2a;border:1px solid #363846;border-radius:16px;padding:22px;margin-bottom:16px}h2{font-family:Georgia,serif;color:#f3d39b;font-size:23px;margin:0 0 15px}h3{font-size:16px;color:#f3d39b;margin:18px 0 8px}
label{display:block;font-size:13px;color:#d0cdd1;margin:13px 0 6px}input,select,textarea{width:100%;background:#0e111e;color:#f0edf0;border:1px solid #57525a;border-radius:9px;padding:10px}textarea{min-height:65px;resize:vertical}
input[type=checkbox]{width:auto;accent-color:#efc983;transform:scale(1.25)}.inline{display:flex;align-items:center;gap:10px;margin-top:14px}.inline label{margin:0}
.project-picker{max-width:400px}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px;align-items:center}.primary,.secondary{border-radius:10px;padding:11px 15px;border:0;font-weight:700}.primary{background:#efc983;color:#1f1620}.secondary{background:#25293c;border:1px solid #505367;color:#f1f0ea}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b0d16;border:1px solid #363846;border-radius:10px;padding:14px;max-height:450px;overflow:auto;color:#c6d6e7;font-size:12px;line-height:1.6}
.notice{border-left:3px solid #ddaa68;background:#241f21;padding:12px 14px;color:#ead6ae;margin:17px 0;line-height:1.5}.kicker{letter-spacing:.15em;color:#d3ac71;text-transform:uppercase;font-size:11px;font-weight:750}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{border:1px solid #403e4d;border-radius:12px;padding:14px;background:#101421}.metric b{font-size:22px;color:#e6c991}.metric span{display:block;font-size:11px;color:#a8a6b5;margin-top:4px}.foot{padding:30px 0;color:#9f9dab;font-size:12px}.mono{font-family:ui-monospace,Consolas,monospace}
table.map{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}table.map th{text-align:left;color:#d3ac71;font-weight:700;font-size:11px;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #41404e;padding:8px 6px}table.map td{border-bottom:1px solid #2b2d3c;padding:7px 6px;vertical-align:middle}table.map select{padding:6px 8px;min-width:170px}tr.needs td{background:#221b1d}tr.done td{background:#141f1c}
.tier{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11px;font-weight:800;letter-spacing:.06em}.t-HIGH{background:#1d4d3f;color:#9ee6c6}.t-MEDIUM{background:#24405a;color:#a9d4ff}.t-LOW{background:#5a3d16;color:#ffd08a}.t-AMBIGUOUS{background:#5a1f2a;color:#ffb3c0}.t-NONE{background:#33343f;color:#c9c9d6}
.req{color:#efc983;font-weight:800}.why{color:#9d9bab;font-size:12px}.status{padding:10px 12px;border-radius:10px;margin-top:12px;font-weight:700}.ok{background:#14302a;color:#9ee6c6}.bad{background:#3a1d22;color:#ffb3c0}
.steps{margin-top:8px}.steps div{display:grid;grid-template-columns:1fr 140px;gap:10px;align-items:center;border-bottom:1px solid #2b2d3c;padding:6px 0;font-size:13px}.steps select{padding:6px}
</style></head><body>
<header><div class="brand"><div><div class="kicker">Project Olympus · v0.4 · MIT</div><h1>OLYMPUS ERP</h1></div><div class="muted">Migration Integrity Workspace · local only<br><small>No live ERP connection</small></div></div></header>
<main><div class="intro"><strong>Find import-breaking data problems, reconcile trial loads, and create the evidence pack your ERP project needs — before go-live.</strong> Everything stays on the machine running Olympus.</div>
<div class="actions"><label for="projectSelect" class="muted">Selected project</label><select id="projectSelect" class="project-picker" aria-label="Select local project"><option value="">No project selected</option></select><button class="secondary" id="refreshProjects">Refresh</button><button class="secondary" id="deleteProject">Delete selected project files</button></div>
<div class="notice"><strong>Safety:</strong> single-user local workspace with no account login, cloud storage, vendor writes or checkout. Use fictional or approved test files only; do not expose the port publicly.</div>
<nav class="tabs" aria-label="Stages"><button class="tab" data-tab="discover" aria-selected="true">01 · Discover</button><button class="tab" data-tab="diagnose" aria-selected="false">02 · Diagnose &amp; map</button><button class="tab" data-tab="prepare" aria-selected="false">03 · Prepare</button><button class="tab" data-tab="operate" aria-selected="false">04 · Operate</button><button class="tab" data-tab="summarytab" aria-selected="false">Project summary</button></nav>
<section class="panel active" id="discover"><div class="columns"><div class="card"><div class="kicker">Athena · Discovery</div><h2>Understand the project</h2>
<label for="project_name">Project name</label><input id="project_name" value="New ERP modernization">
<label for="company_name">Company name</label><input id="company_name" placeholder="Your organization">
<label for="target_system">Target ERP</label><select id="target_system"><option>NetSuite</option><option>Salesforce</option><option>Workday</option><option>Other / undecided</option></select>
<label for="industry">Industry</label><input id="industry" placeholder="Manufacturing, finance, services…">
<label for="source_systems">Legacy systems (one per line)</label><textarea id="source_systems" placeholder="QuickBooks&#10;Spreadsheets"></textarea>
<label for="workflows">Critical workflows (one per line)</label><textarea id="workflows" placeholder="Quote to cash&#10;Purchase to pay"></textarea>
<label for="data_objects">Data objects to migrate (one per line)</label><textarea id="data_objects" placeholder="Customers&#10;Items&#10;Open invoices"></textarea>
<label for="pain_points">Current problems (one per line)</label><textarea id="pain_points" placeholder="Duplicate customers&#10;Manual reconciliation"></textarea>
<div class="actions"><button class="primary" id="saveProject">Create and assess</button><button class="secondary" id="demoProject">Use fictional demo</button></div></div>
<div class="card"><h2>Assessment</h2><p class="muted">Athena highlights missing requirements instead of inventing facts.</p><div id="projectCurrent" class="notice">No project selected.</div><pre id="assessment">Create a project to begin.</pre></div></div>
<div class="card"><div class="kicker">Chronos · Cutover window</div><h2>Backup, rollback and cutover owners</h2><p class="muted">Named people, not roles. Saving changes to an existing project marks earlier UAT results stale (re-review required).</p>
<div class="grid3"><div><label for="c_window_start">Window start</label><input id="c_window_start" type="datetime-local"></div><div><label for="c_window_end">Window end</label><input id="c_window_end" type="datetime-local"></div><div><label for="c_timezone">Timezone</label><input id="c_timezone" placeholder="America/Chicago"></div>
<div><label for="c_backup_taken_by">Backup verified no later than</label><input id="c_backup_taken_by" type="datetime-local"></div><div><label for="c_rollback_deadline">Rollback deadline (point of no return)</label><input id="c_rollback_deadline" type="datetime-local"></div><div><label for="c_backup_method">Backup method</label><input id="c_backup_method" placeholder="Full export + restore test"></div>
<div><label for="c_rollback_trigger">Rollback trigger</label><input id="c_rollback_trigger" placeholder="Balances not reconciled by deadline"></div><div><label for="c_rollback_method">Rollback method</label><input id="c_rollback_method" placeholder="Re-point users to legacy system"></div><div><label for="c_cutover_owner">Cutover lead</label><input id="c_cutover_owner" placeholder="Full name"></div>
<div><label for="c_backup_owner">Backup owner</label><input id="c_backup_owner" placeholder="Full name"></div><div><label for="c_rollback_owner">Rollback decision owner</label><input id="c_rollback_owner" placeholder="Full name"></div><div><label for="c_go_no_go_approver">Go/no-go approver</label><input id="c_go_no_go_approver" placeholder="Full name"></div>
<div><label for="c_business_signoff_owner">Post-load sign-off owner</label><input id="c_business_signoff_owner" placeholder="Full name"></div></div>
<div class="actions"><button class="secondary" id="saveCutover">Save cutover facts to selected project</button></div><pre id="cutoverResults">Cutover facts appear in the Chronos runbook and the project summary.</pre></div></section>
<section class="panel" id="diagnose"><div class="columns"><div class="card"><div class="kicker">Hermes · Migration</div><h2>Scan a legacy export</h2><p class="muted">Select one CSV or XLSX and an illustrative target template. You will review every suggested mapping before any import-ready file is produced.</p>
<label for="sourceFile">Local CSV or XLSX (maximum 3 MB)</label><input id="sourceFile" type="file" accept=".csv,.xlsx">
<label for="template">Target object</label><select id="template"></select><div class="actions"><button class="primary" id="runScan">Diagnose file</button><button class="secondary" id="demoScan">Use fictional demo export</button></div><p class="muted">Deterministic checks only. Templates are starting points, NOT vendor certification.</p></div><div class="card"><h2>Preview findings</h2><div id="scanMetrics" class="metrics"></div><pre id="scanResults">Choose a project in Discover and an export to inspect.</pre></div></div>
<div class="card" id="mappingCard"><div class="kicker">Hermes + Themis · Mapping table</div><h2>Confirm every mapping</h2><p class="muted">Each row needs a human tick. <span class="tier t-HIGH">HIGH</span> exact header or spec · <span class="tier t-MEDIUM">MEDIUM</span> single alias · <span class="tier t-LOW">LOW</span> hint/similar name · <span class="tier t-AMBIGUOUS">AMBIGUOUS</span> several candidates · <span class="tier t-NONE">NONE</span> no candidate. Highlighted rows must be decided one by one; bulk accept skips them.</p>
<div id="mappingStatus" class="status bad">No file diagnosed yet.</div>
<table class="map" aria-label="Mapping table"><thead><tr><th>Target field</th><th>Type</th><th>Confidence</th><th>Source column</th><th>Confirm</th><th>Why</th></tr></thead><tbody id="mappingRows"></tbody></table>
<div class="grid3"><div><label for="mapReviewer">Reviewer (your name)</label><input id="mapReviewer" placeholder="Full name"></div><div class="inline"><input id="mapAttest" type="checkbox"><label for="mapAttest">I reviewed every row for this exact file</label></div><div></div></div>
<div class="actions"><button class="secondary" id="acceptHigh">Accept all HIGH / MEDIUM</button><button class="primary" id="confirmMap">Confirm mappings</button><button class="primary" id="buildClean" disabled>Build import-ready files</button><span id="buildDownload"></span></div><pre id="mapResults">Decisions are saved as a versioned, hashed file next to the spec; changing the file, header row or spec makes them stale.</pre></div>
<div class="card"><div class="kicker">Poseidon · Financial reconciliation</div><h2>Compare source vs trial import</h2><p class="muted">Two CSV/XLSX files, maximum 1.5 MB each. Enter exact column names. Compares keys, row counts and numeric totals, without writing to an ERP.</p>
<div class="columns"><div><label for="reconSource">Source export</label><input id="reconSource" type="file" accept=".csv,.xlsx"><label for="reconKeySource">Source key column</label><input id="reconKeySource" value="External ID"><label for="reconAmountSource">Source amount column</label><input id="reconAmountSource" value="Amount"></div><div><label for="reconTarget">Trial-load export</label><input id="reconTarget" type="file" accept=".csv,.xlsx"><label for="reconKeyTarget">Target key column</label><input id="reconKeyTarget" value="External ID"><label for="reconAmountTarget">Target amount column</label><input id="reconAmountTarget" value="Amount"></div></div>
<label for="reconTolerance">Allowed amount variance per key</label><input id="reconTolerance" value="0.01"><div class="actions"><button class="primary" id="reconRun">Run reconciliation</button></div><pre id="reconResults">Not compared yet.</pre></div></section>
<section class="panel" id="prepare"><div class="columns"><div class="card"><div class="kicker">Apollo · Clio · Chronos</div><h2>Plan and record UAT</h2><p class="muted">Generate ten draft deliverables (discovery, integration, UAT steps, cutover runbook, training, hypercare, ROI assumptions, Zeus gate).</p><div class="actions"><button class="primary" id="makePack">Generate project pack</button><button class="secondary" id="uatStatus">Read UAT evidence status</button></div><div class="notice">Software never outputs GO. A named human authorizes production outside Olympus.</div>
<h3>Record a UAT result (human-entered)</h3><label for="uatCase">Test case</label><select id="uatCase"></select><div id="uatSteps" class="steps"></div>
<div class="grid3"><div><label for="uatResult">Case outcome</label><select id="uatResult"><option>PASS</option><option>FAIL</option><option>BLOCKED</option></select></div><div><label for="uatExecuted">Executed at</label><input id="uatExecuted" type="datetime-local"></div><div><label for="uatReviewer">Actual reviewer</label><input id="uatReviewer" placeholder="Human reviewer"></div></div>
<label for="uatLink">Evidence link (optional, recorded not verified)</label><input id="uatLink" placeholder="https://…">
<label for="uatFile">Evidence file (.txt, .pdf, .png, .csv, .json — fingerprinted)</label><input id="uatFile" type="file" accept=".txt,.pdf,.png,.csv,.json"><label for="uatNotes">Notes</label><textarea id="uatNotes"></textarea><div class="actions"><button class="secondary" id="uatRecord">Record result</button></div><p class="muted">Results go stale if the project facts, the test case/steps, or the evidence file change.</p></div>
<div class="card"><h2>Artifacts and evidence</h2><div id="packDownload"></div><pre id="packResults">No implementation pack generated yet.</pre></div></div></section>
<section class="panel" id="operate"><div class="columns"><div class="card"><div class="kicker">Argus · ERP hypercare queue</div><h2>Incident tracking</h2><p class="muted">Record and review issues manually for the selected project. This does not monitor a live ERP or provide on-call support. (Olympus Argus is unrelated to the separate product Argus of MCP.)</p>
<label for="incidentTitle">Issue</label><input id="incidentTitle" placeholder="Unable to reconcile opening balances">
<label for="incidentSeverity">Severity</label><select id="incidentSeverity"><option>medium</option><option>critical</option><option>high</option><option>low</option></select>
<label for="incidentOwner">Assigned owner</label><input id="incidentOwner" placeholder="Human reviewer">
<div class="actions"><button class="primary" id="incidentCreate">Create ticket</button><button class="secondary" id="incidentList">Refresh queue</button></div></div><div class="card"><h2>Support queue</h2><pre id="incidentResults">No ticket data loaded.</pre></div></div></section>
<section class="panel" id="summarytab"><div class="card"><div class="kicker">Project summary · Zeus</div><h2>Where the project stands</h2><div class="actions"><button class="primary" id="summaryRun">Refresh summary</button><button class="secondary" data-fmt="md">Download MD</button><button class="secondary" data-fmt="json">Download JSON</button><button class="secondary" data-fmt="pdf">Download PDF</button></div><div id="summaryMetrics" class="metrics"></div><pre id="summaryResults">Select a project and refresh.</pre></div></section>
<div class="foot">Olympus ERP · MIT-licensed local workspace · No certified vendor integrations · Human owners remain accountable for migration, test execution and cutover.</div>
</main><script nonce="__NONCE__">
(()=>{const token='__TOKEN__';let project=null,pack=null,mapView=null,uatCases=[];const $=(id)=>document.getElementById(id);const pretty=x=>JSON.stringify(x,null,2);
const CUT=['window_start','window_end','timezone','backup_taken_by','rollback_deadline','backup_method','rollback_trigger','rollback_method','cutover_owner','backup_owner','rollback_owner','go_no_go_approver','business_signoff_owner'];
async function api(req){let response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Olympus-Token':token},body:JSON.stringify(req)});let json=await response.json();if(!response.ok||!json.ok)throw Error(json.error||'Request failed');return json.data}
async function download(url,name){let q=await fetch(url,{headers:{'X-Olympus-Token':token}});if(!q.ok)throw Error((await q.json()).error);let u=URL.createObjectURL(await q.blob());let a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
function display(id,result){$(id).textContent=pretty(result)}function error(id,e){$(id).textContent='ERROR: '+e.message}
function el(tag,cls,text){let e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
async function filePayload(file,max){if(!file)throw Error('Select the required file');if(file.size>max)throw Error('File is too large');let name=file.name.toLowerCase(),ext=['.xlsx','.csv','.txt','.pdf','.png','.json'].find(x=>name.endsWith(x));if(!ext)throw Error('Unsupported file extension');let bytes=new Uint8Array(await file.arrayBuffer());let parts=[];for(let i=0;i<bytes.length;i+=8192)parts.push(String.fromCharCode(...bytes.subarray(i,i+8192)));return {extension:ext,data_base64:btoa(parts.join(''))}}
function metrics(id,list){$(id).replaceChildren(...list.map(([a,b])=>{let d=el('div','metric');d.append(el('b','',String(b)),el('span','',a));return d}))}
function showCases(r){uatCases=r.cases;$('uatCase').replaceChildren(...r.cases.map(c=>{let o=document.createElement('option');o.value=c.case_id;o.textContent=c.case_id+' — '+c.workflow+' — '+c.scenario+' — '+c.result;return o}));showSteps()}
function showSteps(){let c=uatCases.find(x=>x.case_id===$('uatCase').value);$('uatSteps').replaceChildren(...(c?c.steps:[]).map(s=>{let d=el('div');let t=el('span','',s.step_id+' · '+s.action+' → '+s.expected);let sel=document.createElement('select');sel.dataset.step=s.step_id;for(const v of ['NOT RUN','PASS','FAIL','BLOCKED']){let o=el('option','',v);sel.append(o)}sel.value=s.result;d.append(t,sel);return d}))}
$('uatCase').onchange=showSteps;
for(const b of document.querySelectorAll('.tab'))b.addEventListener('click',()=>{for(const v of document.querySelectorAll('.tab'))v.setAttribute('aria-selected',String(v===b));for(const v of document.querySelectorAll('.panel'))v.classList.toggle('active',v.id===b.dataset.tab)})
function selected(id){if(!project)throw Error('Create a project in Discover first');return {action:id,id:project}}
function fillCutover(c){for(const k of CUT)$('c_'+k).value=(c&&c[k])||''}
function readCutover(){let c={};for(const k of CUT){let v=$('c_'+k).value.trim();if(v)c[k]=v}return c}
async function updateProjects(){let r=await api({action:'list_projects'});let previous=project;$('projectSelect').replaceChildren(...[null,...r.projects].map(t=>{let o=document.createElement('option');o.value=t?t.id:'';o.textContent=t?t.name+' — '+t.company:'Choose project';return o}));if(previous){$('projectSelect').value=previous;}return r}
function activate(p){project=p.id;$('projectCurrent').textContent='Selected local project ID: '+project;display('assessment',p.assessment);fillCutover(p.cutover);api({action:'uat',id:project}).then(showCases).catch(()=>{});updateProjects().catch(()=>{})}
async function select(id){project=id;let r=await api({action:'assess',id:project});$('projectCurrent').textContent='Selected local project ID: '+project;display('assessment',r);fillCutover(r.cutover);showCases(await api({action:'uat',id:project}))}
$('projectSelect').onchange=async()=>{let v=$('projectSelect').value;if(!v){project=null;$('projectCurrent').textContent='No project selected';$('assessment').textContent='Select or create a project';return}try{await select(v)}catch(e){error('assessment',e)}};
$('refreshProjects').onclick=async()=>{try{await updateProjects()}catch(e){error('assessment',e)}};
$('deleteProject').onclick=async()=>{try{if(!project)throw Error('Select a project');let sel=$('projectSelect').selectedOptions[0];let name=sel.textContent.split(' — ')[0];let text=window.prompt('Permanent local deletion. Enter the exact project name to delete its uploads, builds, evidence and incidents: '+name);if(text===null)return;await api({action:'delete_project',id:project,confirm_name:text});project=null;await updateProjects();$('projectCurrent').textContent='Deleted selected project files.';$('assessment').textContent='Create a new project to continue.';$('packResults').textContent='No project selected';$('scanResults').textContent='No project selected';$('packDownload').replaceChildren()}catch(e){error('assessment',e)}};
$('saveProject').onclick=async()=>{try{let req={action:'create_project',cutover:readCutover()};for(const key of ['project_name','company_name','target_system','industry','source_systems','workflows','data_objects','pain_points'])req[key]=$(key).value;activate(await api(req))}catch(e){error('assessment',e)}};
$('demoProject').onclick=async()=>{try{activate(await api({action:'demo_project'}))}catch(e){error('assessment',e)}};
$('saveCutover').onclick=async()=>{try{display('cutoverResults',await api({...selected('update_cutover'),cutover:readCutover()}))}catch(e){error('cutoverResults',e)}};
function tierBadge(t){return el('span','tier t-'+t,t)}
function rowState(tr){let cb=tr.querySelector('input');tr.classList.toggle('done',cb.checked);tr.classList.toggle('needs',tr.dataset.review==='1'&&!cb.checked)}
function renderMapping(v){mapView=v;let st=v.decisions;$('mappingStatus').textContent=st.current?('Confirmed v'+st.version+' by '+st.reviewer+' — '+st.reason):('Not confirmed — '+st.reason);$('mappingStatus').className='status '+(st.current?'ok':'bad');$('buildClean').disabled=!st.current;
$('mappingRows').replaceChildren(...v.rows.map(r=>{let tr=el('tr');tr.dataset.target=r.target;tr.dataset.review=r.review_required?'1':'0';tr.dataset.tier=r.tier;tr.dataset.explicit='0';
let name=el('td');name.append(el('span','',r.target));if(r.required)name.append(el('span','req',' *'));
let sel=document.createElement('select');sel.setAttribute('aria-label','Source column for '+r.target);sel.append(el('option','','— leave unmapped —'));sel.options[0].value='';for(const h of v.headers){let o=el('option','',h);o.value=h;sel.append(o)}
let sug=Array.isArray(r.suggested)?null:r.suggested;sel.value=(r.tier==='AMBIGUOUS'||!sug)?'':sug;if(r.decided){sel.value=r.decided.source||'';}
let cb=document.createElement('input');cb.type='checkbox';cb.setAttribute('aria-label','Confirm '+r.target);
sel.onchange=()=>{cb.checked=false;tr.dataset.explicit='0';rowState(tr)};cb.onchange=()=>{tr.dataset.explicit=cb.checked?'1':'0';rowState(tr)};
let c1=el('td');if(r.decided){cb.checked=true;tr.dataset.explicit=r.review_required?'1':'0';}c1.append(sel);let c2=el('td');c2.append(cb);let tierTd=el('td');tierTd.append(tierBadge(r.tier));
let why=el('td','why',(r.decided?'Confirmed: '+r.decided.decision+' · ':'')+r.reason+(r.candidates&&r.candidates.length>1?' ('+r.candidates.join(', ')+')':'')+(r.review_required?' · explicit decision required':''));
tr.append(name,el('td','muted',r.type),tierTd,c1,c2,why);rowState(tr);return tr}))}
function decisionsPayload(){let d={};for(const tr of $('mappingRows').children){let sel=tr.querySelector('select'),cb=tr.querySelector('input');d[tr.dataset.target]={source:sel.value||null,reviewed:cb.checked,explicit:tr.dataset.explicit==='1'}}return d}
$('acceptHigh').onclick=()=>{for(const tr of $('mappingRows').children){if(tr.dataset.tier==='HIGH'||tr.dataset.tier==='MEDIUM'||(tr.dataset.tier==='NONE'&&tr.dataset.review==='0')){tr.querySelector('input').checked=true;tr.dataset.explicit='0';rowState(tr)}}};
$('confirmMap').onclick=async()=>{try{if(!mapView)throw Error('Diagnose a file first');let r=await api({action:'confirm_mapping',id:project,spec:mapView.spec_id,reviewer:$('mapReviewer').value,attest:$('mapAttest').checked,decisions:decisionsPayload()});renderMapping(r.mapping);display('mapResults',{decisions:r.decisions,preview:{status:r.preview.status,loadable_rows:r.preview.loadable_rows,total_rows:r.preview.total_rows,errors:r.preview.errors}})}catch(e){error('mapResults',e)}};
$('buildClean').onclick=async()=>{try{let r=await api({action:'build',id:project,spec:mapView.spec_id});display('mapResults',r);let b=el('button','secondary','Download build ZIP');b.onclick=()=>download('/api/build?project='+project+'&build='+r.build,'olympus_build.zip').catch(e=>error('mapResults',e));$('buildDownload').replaceChildren(b)}catch(e){error('mapResults',e)}};
function showScan(r){display('scanResults',{profile:r.profile,results:{status:r.results.status,total_rows:r.results.total_rows,loadable_rows:r.results.loadable_rows,errors:r.results.errors,warnings:r.results.warnings,findings:r.results.loads[0].findings},note:r.note});metrics('scanMetrics',[['Rows',r.results.total_rows],['Loadable',r.results.loadable_rows],['Errors',r.results.errors],['Status',r.results.status]]);renderMapping(r.mapping);$('buildDownload').replaceChildren()}
$('runScan').onclick=async()=>{try{if(!project)throw Error('Select a project first');let file=$('sourceFile').files[0];if(!file)throw Error('Select a CSV or XLSX');if(file.size>3000000)throw Error('File is over 3 MB');let up=await filePayload(file,3000000);if(!['.csv','.xlsx'].includes(up.extension))throw Error('Unsupported file type');showScan(await api({action:'diagnose',id:project,template:$('template').value,...up}))}catch(e){error('scanResults',e)}};
$('demoScan').onclick=async()=>{try{if(!project)throw Error('Select a project first');showScan(await api({action:'demo_diagnose',id:project}))}catch(e){error('scanResults',e)}};
$('makePack').onclick=async()=>{try{let r=await api(selected('make_pack'));pack=r.pack;display('packResults',r);let b=el('button','primary','Download 10-file ZIP');b.onclick=()=>download('/api/bundle?project='+project+'&pack='+pack,'olympus_erp_plan.zip').catch(e=>error('packResults',e));$('packDownload').replaceChildren(b)}catch(e){error('packResults',e)}};
$('uatStatus').onclick=async()=>{try{let r=await api(selected('uat'));display('packResults',r);showCases(r)}catch(e){error('packResults',e)}};
$('uatRecord').onclick=async()=>{try{if(!project)throw Error('Select project first');let f=$('uatFile').files[0];let upload=f?await filePayload(f,3000000):{};let steps={};for(const s of $('uatSteps').querySelectorAll('select'))steps[s.dataset.step]=s.value;let when=$('uatExecuted').value;let r=await api({action:'uat_record',id:project,case_id:$('uatCase').value,result:$('uatResult').value,reviewer:$('uatReviewer').value,executed_at:when,evidence_link:$('uatLink').value.trim(),notes:$('uatNotes').value,step_results:steps,...upload});display('packResults',r);let keep=$('uatCase').value;showCases(r);$('uatCase').value=keep;showSteps()}catch(e){error('packResults',e)}};
$('reconRun').onclick=async()=>{try{if(!project)throw Error('Select project first');let a=await filePayload($('reconSource').files[0],1500000),b=await filePayload($('reconTarget').files[0],1500000);let r=await api({action:'reconcile',id:project,source_extension:a.extension,source_data_base64:a.data_base64,target_extension:b.extension,target_data_base64:b.data_base64,source_key:$('reconKeySource').value,target_key:$('reconKeyTarget').value,source_amount:$('reconAmountSource').value,target_amount:$('reconAmountTarget').value,tolerance:$('reconTolerance').value});display('reconResults',r)}catch(e){error('reconResults',e)}};
$('incidentList').onclick=async()=>{try{display('incidentResults',await api(selected('incidents')))}catch(e){error('incidentResults',e)}};
$('incidentCreate').onclick=async()=>{try{await api({...selected('incident_create'),title:$('incidentTitle').value,severity:$('incidentSeverity').value,owner:$('incidentOwner').value});display('incidentResults',await api(selected('incidents')))}catch(e){error('incidentResults',e)}};
$('summaryRun').onclick=async()=>{try{let r=await api(selected('summary'));let s=r.summary;metrics('summaryMetrics',[['Open blockers',s.open_blockers],['Loadable rows',s.latest_build?s.latest_build.loadable_rows+'/'+s.latest_build.total_rows:'—'],['UAT pass',s.uat.passed+'/'+s.uat.total],['Zeus',s.zeus.decision.startsWith('NO GO')?'NO GO':'EVIDENCE COMPLETE']]);$('summaryResults').textContent=r.markdown}catch(e){error('summaryResults',e)}};
for(const b of document.querySelectorAll('[data-fmt]'))b.onclick=()=>{if(!project)return error('summaryResults',Error('Select a project'));download('/api/summary?project='+project+'&format='+b.dataset.fmt,'project_summary.'+b.dataset.fmt).catch(e=>error('summaryResults',e))};
api({action:'list_projects'}).then(r=>{$('template').replaceChildren(...r.templates.map(t=>{let o=document.createElement('option');o.textContent=t;o.value=t;return o}));if(r.projects.length){let last=r.projects[r.projects.length-1];select(last.id).then(()=>{$('projectCurrent').textContent='Previous project: '+last.name+' ('+project+')'}).catch(e=>error('assessment',e))}updateProjects().catch(()=>{})}).catch(e=>error('assessment',e));})();
</script></body></html>'''


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description="Olympus single-user loopback development dashboard")
    parser.add_argument("--workspace",default=".")
    parser.add_argument("--port", type=int, default=8765)
    args=parser.parse_args(argv)
    if not 1024<=args.port<=65535: parser.error("Port must be 1024–65535")
    serve(args.workspace,args.port)

if __name__ == '__main__': main()
