"""Sprint 1/2: confirmable mapping table, Clio steps, project summary, Chronos cutover, Zeus."""
import base64
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from olympus_erp import dashboard, erp_agents, incidents, mapping, project_summary, uat_evidence  # noqa: E402
from olympus_erp.cli import mapping_main  # noqa: E402
from olympus_erp.engine import run, summary  # noqa: E402
from olympus_erp.inputs import read_rows, SourceError  # noqa: E402
from olympus_erp.mcp import TOOL_SPECS, _dispatch  # noqa: E402
from olympus_erp.reporting import build  # noqa: E402
from olympus_erp.signoff import approve  # noqa: E402

GO_WORD = re.compile(r"(?<!NO )(?<!NO-)(?<!/)\bGO\b(?!/)")  # a bare "GO" that is not part of NO GO / GO/NO-GO


def b64(text):
    return base64.b64encode(text.encode()).decode()


def all_reviewed(view, overrides=None):
    overrides = overrides or {}
    out = {}
    for r in view["rows"]:
        src = overrides.get(r["target"], r["suggested"] if r["tier"] != "AMBIGUOUS" else None)
        out[r["target"]] = {"source": src, "reviewed": True, "explicit": True}
    return out


class Workspace(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)

    def spec(self, csv_text, template="netsuite.customer", extra=""):
        (self.root / "src.csv").write_text(csv_text, encoding="utf-8")
        spec = self.root / "spec.toml"
        spec.write_text(f'[project]\nname="T"\n\n[[load]]\nname="c"\ntemplate="{template}"\nsource="src.csv"\n{extra}', encoding="utf-8")
        return spec


class MappingTableTests(Workspace):
    def test_confidence_tiers(self):
        headers = dashboard.DEMO_EXPORT.splitlines()[0].split(",")
        rows = {r["target"]: r for r in mapping.suggest_table(headers, "netsuite.customer", "quickbooks")}
        self.assertEqual("AMBIGUOUS", rows["External ID"]["tier"]); self.assertIsNone(rows["External ID"]["suggested"])
        self.assertEqual("AMBIGUOUS", rows["Email"]["tier"])
        self.assertEqual("MEDIUM", rows["Company Name"]["tier"])
        self.assertEqual("HIGH", rows["State"]["tier"])
        self.assertEqual("LOW", rows["Country"]["tier"])
        self.assertEqual("LOW", rows["Credit Limit"]["tier"])
        self.assertEqual("NONE", rows["Subsidiary"]["tier"])
        self.assertTrue(all(rows[t]["review_required"] for t in ("External ID", "Email", "Country", "Credit Limit")))
        self.assertFalse(rows["Subsidiary"]["review_required"])  # optional + no candidate

    def test_no_artifacts_and_no_ready_without_confirmation(self):
        spec = self.spec("External ID,Company Name\nA,Acme\nB,Beta\n")
        s = summary(run(spec))
        self.assertEqual(0, s["errors"])
        self.assertEqual("UNVERIFIED", s["status"])  # clean preview on guesses is never READY
        with self.assertRaisesRegex(ValueError, "confirmed mapping"):
            build(run(spec), self.root / "out", pdf=False)
        self.assertFalse((self.root / "out").exists())
        mapping.confirm(spec, "Kurt Reviewer", {"c": all_reviewed(mapping.propose(spec)["loads"][0])}, attest=True)
        self.assertEqual("READY", summary(run(spec))["status"])
        build(run(spec), self.root / "out", pdf=False)
        self.assertTrue((self.root / "out" / "c.clean.csv").is_file())

    def test_every_row_must_be_reviewed_and_review_rows_explicit(self):
        spec = self.spec("Customer Number,Customer ID,Customer Name\n1,A,Acme\n")
        view = mapping.propose(spec)["loads"][0]
        d = all_reviewed(view, {"External ID": "Customer ID"})
        with self.assertRaisesRegex(ValueError, "attest"):
            mapping.confirm(spec, "Kurt", {"c": d})
        missing = dict(d); missing["Company Name"] = dict(d["Company Name"], reviewed=False)
        with self.assertRaisesRegex(ValueError, "Company Name: not reviewed"):
            mapping.confirm(spec, "Kurt", {"c": missing}, attest=True)
        bulk = dict(d); bulk["External ID"] = dict(d["External ID"], explicit=False)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS confidence requires an explicit"):
            mapping.confirm(spec, "Kurt", {"c": bulk}, attest=True)
        bad = dict(d); bad["Email"] = {"source": "Nope", "reviewed": True, "explicit": True}
        with self.assertRaisesRegex(ValueError, "existing header"):
            mapping.confirm(spec, "Kurt", {"c": bad}, attest=True)
        st = mapping.confirm(spec, "Kurt", {"c": d}, attest=True)
        self.assertTrue(st["current"])
        body = json.loads(mapping.decisions_path(spec).read_text())
        self.assertEqual("overridden" if view["rows"][0]["suggested"] else "overridden", body["loads"]["c"]["fields"]["External ID"]["decision"])

    def test_override_is_used_and_spec_map_is_not_applied_silently(self):
        spec = self.spec("External ID,Company Name,Email,Email Address\nA,Acme,bad,good@example.com\n",
                         extra='[load.map]\n"Email" = "Email"\n')
        view = mapping.propose(spec)["loads"][0]
        rows = {r["target"]: r for r in view["rows"]}
        self.assertEqual(("HIGH", "Email"), (rows["Email"]["tier"], rows["Email"]["suggested"]))
        mapping.confirm(spec, "Kurt", {"c": all_reviewed(view, {"Email": "Email Address"})}, attest=True)
        s = summary(run(spec))
        self.assertEqual("READY", s["status"])
        self.assertEqual({"External ID": "External ID", "Company Name": "Company Name", "Email": "Email Address"}, s["loads"][0]["mapping"])

    def test_versioned_hashed_and_stale_on_any_change(self):
        spec = self.spec("External ID,Company Name\nA,Acme\n")
        view = mapping.propose(spec)["loads"][0]
        v1 = mapping.confirm(spec, "Kurt", {"c": all_reviewed(view)}, attest=True)
        v2 = mapping.confirm(spec, "Kurt", {"c": all_reviewed(view)}, attest=True)
        self.assertEqual((1, 2), (v1["version"], v2["version"]))
        hist = mapping.history_dir(spec) / "v1.json"
        self.assertEqual(v1["sha256"], json.loads(hist.read_text())["sha256"])
        self.assertEqual(v1["sha256"], json.loads(mapping.decisions_path(spec).read_text())["previous_sha256"])
        # tamper with decision file
        p = mapping.decisions_path(spec); good = p.read_text()
        p.write_text(good.replace('"Company Name"', '"Company  Name"', 1))
        self.assertIn("hash mismatch", mapping.status(spec)["reason"])
        p.write_text(good); self.assertTrue(mapping.status(spec)["current"])
        # source bytes change
        (self.root / "src.csv").write_text("External ID,Company Name\nA,Acme\nB,Beta\n")
        st = mapping.status(spec)
        self.assertFalse(st["current"]); self.assertIn("source file changed", st["reason"])
        with self.assertRaises(ValueError): build(run(spec), self.root / "o", pdf=False)
        # header change and spec change
        (self.root / "src.csv").write_text("External ID,Company\nA,Acme\n")
        self.assertIn("header row changed", mapping.status(spec)["reason"])
        (self.root / "src.csv").write_text("External ID,Company Name\nA,Acme\n")
        self.assertTrue(mapping.status(spec)["current"])
        spec.write_text(spec.read_text() + '\n[load.defaults]\nCountry = "US"\n')
        self.assertIn("spec changed", mapping.status(spec)["reason"])

    def test_rejects_trace_and_no_silent_mutation(self):
        text = ("Customer ID,Customer Name,Email,State,Credit Limit\n"
                "C1,Acme,OPS@EXAMPLE.COM, Illinois ,\"$1,000\"\n"
                "C2,Beta,not-an-email,TX,5\n"
                "\n"
                "C3,Gamma,g@example.com,Texs,(20)\n")
        spec = self.spec(text)
        mapping.confirm(spec, "Kurt", {"c": all_reviewed(mapping.propose(spec)["loads"][0])}, attest=True)
        build(run(spec), self.root / "out", pdf=False)
        rd = lambda n: list(csv.DictReader(io.StringIO((self.root / "out" / n).read_text(encoding="utf-8-sig"))))
        rejects, clean, changes = rd("c.rejects.csv"), rd("c.clean.csv"), rd("c.changes.csv")
        self.assertEqual(["3", "5"], [r["source_line"] for r in rejects])  # original line numbers (blank line 4 skipped)
        self.assertEqual("(20)", rejects[1]["source:Credit Limit"])  # original value, not cleaned
        self.assertEqual("Texs", rejects[1]["source:State"])
        _, src_rows = read_rows(self.root / "src.csv")
        by_line = dict(src_rows)
        logged = {(c["source_line"], c["field"]) for c in changes}
        mp = {"External ID": "Customer ID", "Company Name": "Customer Name", "Email": "Email", "State": "State", "Credit Limit": "Credit Limit"}
        self.assertEqual(1, len(clean))
        for field, col in mp.items():
            if clean[0][field] != by_line[2][col]:
                self.assertIn(("2", field), logged, f"{field} changed without a change-log entry")
        reasons = {c["field"]: c["reason"] for c in changes if c["source_line"] == "2"}
        self.assertEqual("email lower-cased", reasons["Email"])
        self.assertIn("state normalized", reasons["State"])
        self.assertIn("number normalized", reasons["Credit Limit"])

    def test_required_field_left_unmapped_never_ready(self):
        spec = self.spec("Customer Name\nAcme\n")
        view = mapping.propose(spec)["loads"][0]
        rows = {r["target"]: r for r in view["rows"]}
        self.assertTrue(rows["External ID"]["review_required"])  # LOW: only a similar-looking header exists
        mapping.confirm(spec, "Kurt", {"c": all_reviewed(view, {"External ID": None})}, attest=True)
        s = summary(run(spec))
        self.assertEqual("NOT READY", s["status"]); self.assertEqual(0, s["loadable_rows"])

    def test_cli_show_and_confirm_paths(self):
        spec = self.spec("Customer Number,Customer ID,Customer Name\n1,A,Acme\n")
        out = subprocess.run([sys.executable, "-m", "olympus_erp", "mapping", "show", str(spec)], capture_output=True, text=True,
                             env={"PYTHONPATH": str(ROOT / "src")})
        self.assertIn("AMBIGUOUS", out.stdout); self.assertIn("EXPLICIT REQUIRED", out.stdout)
        with self.assertRaises(SystemExit):
            mapping_main(["confirm", str(spec), "--reviewer", "Kurt", "--attest", "--accept-suggestions"])
        self.assertFalse(mapping.status(spec)["current"])
        self.assertEqual(0, mapping_main(["confirm", str(spec), "--reviewer", "Kurt", "--attest", "--accept-suggestions",
                                          "--set", "c.External ID=Customer ID"]))
        self.assertTrue(mapping.status(spec)["current"])
        answers = iter(["", "Customer ID", "", "", "", "", "", "", ""])  # Enter on AMBIGUOUS row is refused, then typed
        self.assertEqual(0, mapping_main(["confirm", str(spec), "--reviewer", "Kurt", "--attest", "--interactive"],
                                         ask=lambda _p: next(answers)))
        self.assertEqual(2, json.loads(mapping.decisions_path(spec).read_text())["version"])

    def test_mcp_cannot_confirm_mappings(self):
        names = [t[0] for t in TOOL_SPECS]
        self.assertIn("mapping_table", names); self.assertIn("mapping_status", names)
        self.assertFalse([n for n in names if re.search(r"confirm|approve|signoff_write|uat_record", n)])
        spec = self.spec("External ID,Company Name\nA,Acme\n")
        with self.assertRaisesRegex(ValueError, "confirmed mapping"):
            _dispatch("build", {"spec": "spec.toml", "output": "out", "pdf": False}, self.root)


class ClioStepTests(Workspace):
    def setUp(self):
        super().setUp()
        self.project = self.root / "p" / "project.json"; self.project.parent.mkdir()
        self.project.write_text(json.dumps({"project_name": "T", "company_name": "C", "target_system": "NetSuite", "workflows": ["Order|cash"]}))
        self.ev = self.project.parent / "e.txt"; self.ev.write_text("screenshot notes")

    def test_steps_generated_and_rendered(self):
        text, cases = erp_agents.apollo(erp_agents.load_project(self.project))
        self.assertEqual([3, 2, 3], [len(c["steps"]) for c in cases])
        self.assertIn("UAT-01-1.S2", text); self.assertIn("Order\\|cash", text)

    def test_pass_requires_all_steps_timestamp_and_evidence(self):
        steps = {"UAT-01-1.S1": "PASS", "UAT-01-1.S2": "PASS", "UAT-01-1.S3": "PASS"}
        rec = lambda **kw: uat_evidence.record(self.project, "UAT-01-1", kw.pop("result", "PASS"), "Reviewer", kw.pop("ev", self.ev), self.root, **kw)
        with self.assertRaisesRegex(ValueError, "every step"):
            rec(executed_at="2026-10-01T10:00", step_results={"UAT-01-1.S1": "PASS"})
        with self.assertRaisesRegex(ValueError, "executed_at"):
            rec(step_results=steps)
        with self.assertRaisesRegex(ValueError, "future"):
            rec(executed_at="2999-01-01T00:00", step_results=steps)
        with self.assertRaisesRegex(ValueError, "evidence"):
            rec(ev=None, executed_at="2026-10-01T10:00", step_results=steps)
        with self.assertRaisesRegex(ValueError, "failed step"):
            rec(result="FAIL", executed_at="2026-10-01T10:00", step_results=steps)
        r = rec(ev=None, evidence_link="https://tickets.example.com/UAT-1", executed_at="2026-10-01T10:00-05:00", step_results=steps)
        case = r["cases"][0]
        self.assertEqual("PASS", case["result"]); self.assertFalse(case["evidence_link_verified"])
        self.assertEqual("2026-10-01T10:00:00-05:00", case["executed_at"]); self.assertTrue(case["recorded_at"])
        self.assertEqual(["PASS"] * 3, [s["result"] for s in case["steps"]])
        self.assertEqual(0, r["file_evidenced_passes"])

    def test_stale_when_case_steps_or_evidence_or_spec_change(self):
        steps = {f"UAT-01-1.S{i}": "PASS" for i in (1, 2, 3)}
        uat_evidence.record(self.project, "UAT-01-1", "PASS", "Reviewer", self.ev, self.root, executed_at="2026-10-01T10:00", step_results=steps)
        reg = self.project.with_suffix(".uat-evidence.json"); data = json.loads(reg.read_text())
        data["results"]["UAT-01-1"]["case_sha256"] = "0" * 64; reg.write_text(json.dumps(data))
        c = uat_evidence.status(self.project)["cases"][0]
        self.assertEqual("STALE EVIDENCE", c["result"]); self.assertIn("steps changed", c["stale_reason"])
        uat_evidence.record(self.project, "UAT-01-1", "PASS", "Reviewer", self.ev, self.root, executed_at="2026-10-01T10:00", step_results=steps)
        self.ev.write_text("edited"); self.assertIn("Evidence file", uat_evidence.status(self.project)["cases"][0]["stale_reason"])
        p = json.loads(self.project.read_text()); p["industry"] = "x"; self.project.write_text(json.dumps(p))
        self.assertTrue(uat_evidence.status(self.project)["stale"])


class ChronosCutoverTests(unittest.TestCase):
    base = {"project_name": "T", "company_name": "C", "target_system": "NetSuite"}

    def test_section_owners_and_placeholders(self):
        p = dict(self.base, cutover={"window_start": "2027-04-16T18:00", "window_end": "2027-04-18T06:00", "timezone": "America/Chicago",
                                     "cutover_owner": "Dana Example", "backup_owner": "TBD"})
        text = erp_agents.chronos(p)
        self.assertIn("## Backup, rollback and cutover window", text)
        self.assertIn("| Cutover lead (runs the window) | Dana Example |", text)
        self.assertIn("| Backup owner (takes and verifies the pre-cutover backup) | **TO ASSIGN — required** |", text)
        missing = erp_agents.cutover_readiness(p)["missing"]
        self.assertTrue(any(m.startswith("Backup owner") for m in missing))
        self.assertFalse(any(m.startswith("Cutover lead") for m in missing))

    def test_validation(self):
        for bad in ({"window_start": "2027-04-18T00:00", "window_end": "2027-04-17T00:00"},
                    {"window_start": "2027-04-16T18:00", "window_end": "2027-04-18T06:00", "rollback_deadline": "2027-04-19T00:00"},
                    {"window_start": "soon"}, {"owner_of_everything": "x"}, {"cutover_owner": 5}):
            with self.assertRaises(ValueError, msg=bad):
                erp_agents.validate_cutover(bad)


class ZeusAndSummaryTests(Workspace):
    CLEAN = "External ID,Company Name,Email\nA1,Acme,a@example.com\nB2,Beta,b@example.com\n"

    def full_project(self, clean=True):
        cmd = lambda **kw: dashboard.command(self.root, kw)
        p = cmd(action="demo_project"); pid = p["id"]
        d = self.root / "projects" / pid
        cmd(action="update_cutover", id=pid, cutover=dict(dashboard.DEMO_CUTOVER, go_no_go_approver="Pat Example",
                                                          business_signoff_owner="Ari Example"))
        diag = cmd(action="diagnose", id=pid, template="netsuite.customer", extension=".csv",
                   data_base64=b64(self.CLEAN if clean else self.CLEAN + "B2,Dup,bad\n"))
        view = diag["mapping"]
        cmd(action="confirm_mapping", id=pid, spec=view["spec_id"], reviewer="Kurt", attest=True, decisions=all_reviewed(view))
        approve(d / (view["spec_id"] + ".toml"), "Kurt", attested=True)
        b = cmd(action="build", id=pid, spec=view["spec_id"])
        amt = "External ID,Amount\nA1,10\nB2,20\n"
        cmd(action="reconcile", id=pid, source_extension=".csv", source_data_base64=b64(amt), target_extension=".csv",
            target_data_base64=b64(amt), source_key="External ID", target_key="External ID", source_amount="Amount", target_amount="Amount")
        for c in cmd(action="uat", id=pid)["cases"]:
            steps = {s["step_id"]: "PASS" for s in c["steps"]}
            cmd(action="uat_record", id=pid, case_id=c["case_id"], result="PASS", reviewer="Business reviewer",
                executed_at="2026-10-01T10:00", step_results=steps, extension=".txt", data_base64=b64("ok " + c["case_id"]))
        return pid, d, b

    def test_zeus_never_go_from_drafts_or_assertions(self):
        project = self.root / "p" / "project.json"; project.parent.mkdir()
        claims = {"project_name": "T", "company_name": "C", "target_system": "NetSuite", "workflows": ["O2C"],
                  "decision": "GO", "go_live_approved": True, "uat_passed": True, "reconciled": True, "zeus": {"decision": "GO"},
                  "approvals": ["CFO"], "status": "READY"}
        project.write_text(json.dumps(claims))
        p = erp_agents.load_project(project)
        erp_agents.pack(p, project.parent / "pack")  # a full set of drafts exists
        for gate in (erp_agents.go_live_gate(p),
                     erp_agents.go_live_gate(p, {"mapping_confirmed": True, "build_clean": True, "reconciled": True,
                                                 "uat_passed": True, "themis_signed_off": True, "no_open_critical": True}),
                     project_summary.collect_evidence(project.parent)["zeus"],
                     _dispatch("go_live_gate", {"project": "p/project.json"}, self.root)):
            self.assertEqual(erp_agents.ZEUS_NO_GO, gate["decision"])
            self.assertFalse(GO_WORD.search(json.dumps(gate)), gate)
        self.assertEqual(["approvals", "decision", "go_live_approved", "reconciled", "status", "uat_passed", "zeus"],
                         erp_agents.go_live_gate(p)["ignored_assertions"])
        for name in project.parent.joinpath("pack").iterdir():
            self.assertFalse(GO_WORD.search(name.read_text()), name)

    def test_full_evidence_still_needs_a_human(self):
        pid, d, b = self.full_project()
        self.assertEqual("READY", b["status"])
        s = project_summary.collect_evidence(d)
        self.assertEqual(erp_agents.ZEUS_EVIDENCE_COMPLETE, s["zeus"]["decision"], s["blockers"])
        self.assertFalse(GO_WORD.search(json.dumps(s)))
        self.assertEqual(0, s["open_blockers"])
        # one open critical incident flips it back
        dashboard.command(self.root, {"action": "incident_create", "id": pid, "title": "Balances off", "severity": "critical", "owner": "Kurt"})
        s = project_summary.collect_evidence(d)
        self.assertEqual(erp_agents.ZEUS_NO_GO, s["zeus"]["decision"]); self.assertEqual({"Argus": 1}, s["blockers_by_area"])

    def test_summary_contents_and_formats(self):
        pid, d, b = self.full_project(clean=False)
        s = project_summary.collect_evidence(d)
        self.assertEqual(erp_agents.ZEUS_NO_GO, s["zeus"]["decision"])
        self.assertGreater(s["open_blockers"], 0); self.assertIn("Hermes", s["blockers_by_area"])
        lb = s["latest_build"]["loads"][0]
        self.assertEqual((3, 1, 2), (lb["rows"], lb["loadable"], lb["rejected"]))
        self.assertIn("duplicate_id", lb["exceptions_by_code"])
        incoming = [f for f in s["source_files"] if f["folder"] == "incoming"]
        self.assertEqual(lb["source_sha256"], incoming[0]["sha256"])
        self.assertEqual(64, len(incoming[0]["sha256"]))
        out = self.root / "summary"
        self.assertEqual(["project_summary.json", "project_summary.md", "project_summary.pdf"], project_summary.write(s, out))
        md = (out / "project_summary.md").read_text()
        for needle in ("Open blockers", "Target load counts", "Source file fingerprints", "Zeus gates", "duplicate_id"):
            self.assertIn(needle, md)
        self.assertTrue((out / "project_summary.pdf").read_bytes().startswith(b"%PDF-"))
        # stale build after the source file changes
        src = d / "incoming" / incoming[0]["file"]; src.write_text(self.CLEAN + "C3,New,c@example.com\n")
        s2 = project_summary.collect_evidence(d)
        self.assertTrue(any("stale" in x["detail"] for x in s2["blockers"]))

    def test_dashboard_build_download_and_summary_endpoints(self):
        pid, d, b = self.full_project()
        z = zipfile.ZipFile(io.BytesIO(self._get(f"/api/build?project={pid}&build={b['build']}")))
        self.assertTrue({"customer_1.clean.csv", "customer_1.rejects.csv", "customer_1.changes.csv", "report.json"} <= set(z.namelist()))
        self.assertTrue(self._get(f"/api/summary?project={pid}&format=pdf").startswith(b"%PDF-"))
        self.assertIn(b"Zeus", self._get(f"/api/summary?project={pid}&format=md"))

    def test_dashboard_table_shows_confirmed_decisions(self):
        pid, d, b = self.full_project()
        view = dashboard.command(self.root, {"action": "mapping_table", "id": pid, "spec": next(d.glob("*.mappings.json")).name.split(".")[0]})
        self.assertTrue(view["decisions"]["current"])
        self.assertTrue(all("decided" in r for r in view["rows"]))

    def _get(self, path):
        import socket, threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        server = ThreadingHTTPServer(("127.0.0.1", port), dashboard.make_handler(self.root, "tok", port))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with urlopen(Request(f"http://127.0.0.1:{port}{path}", headers={"X-Olympus-Token": "tok"}), timeout=5) as r:
                return r.read()
        finally:
            server.shutdown(); server.server_close()


class ReadinessFixTests(Workspace):
    def test_xlsx_decompression_limit(self):
        p = self.root / "bomb.xlsx"
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("xl/workbook.xml", "<workbook/>")
            z.writestr("xl/worksheets/sheet1.xml", "<a>" + " " * 26_000_000 + "</a>")
        self.assertLess(p.stat().st_size, 3_000_000)  # fits the dashboard upload limit
        with self.assertRaisesRegex(SourceError, "safety limits"):
            read_rows(p)

    def test_incidents_deleted_with_project(self):
        pid = dashboard.command(self.root, {"action": "demo_project"})["id"]
        dashboard.command(self.root, {"action": "incident_create", "id": pid, "title": "Import broke", "severity": "high", "owner": "Kurt"})
        self.assertEqual(1, dashboard.command(self.root, {"action": "incidents", "id": pid})["total"])
        self.assertFalse((self.root / "olympus_incidents.jsonl").exists())
        dashboard.command(self.root, {"action": "delete_project", "id": pid, "confirm_name": "Olympus manufacturing demo"})
        self.assertFalse(list(self.root.rglob("olympus_incidents.jsonl")))

    def test_packaging_metadata(self):
        meta = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual("olympus-erp", meta["project"]["name"]); self.assertEqual("MIT", meta["project"]["license"])
        self.assertEqual([{"name": "Kurt Francisco"}], meta["project"]["authors"])
        scripts = meta["project"]["scripts"]
        self.assertEqual("olympus_erp.main:main", scripts["olympus"])
        self.assertNotIn("loadready", scripts); self.assertNotIn("hermes", scripts)
        self.assertTrue((ROOT / "LICENSE").read_text().startswith("MIT License\n\nCopyright (c) 2026 Kurt Francisco"))
        out = subprocess.run([sys.executable, "-m", "olympus_erp", "hermes", "templates"], capture_output=True, text=True,
                             env={"PYTHONPATH": str(ROOT / "src")})
        self.assertIn("netsuite.customer", out.stdout)

    def test_release_tree_hygiene(self):
        self.assertFalse((ROOT / "references" / "BUSINESS.md").exists())
        self.assertFalse((ROOT / "docs" / "RHL_26_AI_OPPORTUNITIES.md").exists())
        text = "\n".join(p.read_text(errors="ignore") for p in [*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md"),
                         *(ROOT / "references").glob("*.md"), *(ROOT / "examples").rglob("*.csv")])
        self.assertNotIn("30 Wall St", text)
        for domain in re.findall(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", text):
            self.assertTrue(domain.lower().endswith(("example.com", "example.org")), domain)
        self.assertNotIn("18 MCP tools", text); self.assertNotIn("18-tool", text)
        self.assertNotIn("formerly SpecGate", text); self.assertNotIn("Hephaestus", text)
        self.assertNotRegex(text, r"(?i)all rights reserved|evaluation only|evaluation package")


if __name__ == "__main__":
    unittest.main()
