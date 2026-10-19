import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from olympus_erp.engine import _date, _decimal, run, summary, suggest_mapping, SpecError
from olympus_erp.inputs import read_rows, profile, SourceError
from olympus_erp.reporting import build
from olympus_erp.signoff import approve, status
from olympus_erp.templates import TEMPLATES
from olympus_erp.peitho import grade, qualify, draft

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples/acme/hermes.toml"

class HermesTests(unittest.TestCase):
    def test_templates_extended(self):
        self.assertEqual(len(TEMPLATES), 11)
        self.assertIn("netsuite.open_ap_bill", TEMPLATES)
        self.assertIn("salesforce.opportunity", TEMPLATES)

    def test_suggest_respects_context(self):
        cols = ["Invoice Number", "Customer ID", "Item ID", "Invoice Date"]
        maps = suggest_mapping(cols, "netsuite.open_invoice", "quickbooks")
        self.assertEqual(maps["mapping"]["External ID"], "Invoice Number")
        self.assertEqual(maps["mapping"]["Customer"], "Customer ID")
        self.assertNotIn("External ID", maps["ambiguous"])

    def test_sample_finds_issues(self):
        s = summary(run(DEMO))
        self.assertEqual(s["status"], "NOT READY")
        self.assertEqual(s["total_rows"], 22)
        self.assertEqual(s["loadable_rows"], 11)
        self.assertGreater(s["errors"], 10)
        self.assertGreater(s["warnings"], 0)

    def test_row_references_and_cascade(self):
        s = summary(run(DEMO))
        inv = next(l for l in s["loads"] if l["name"] == "invoices")
        self.assertEqual(inv["loadable"], 2)
        self.assertIn("rejected_parent", [x["code"] for x in inv["findings"]])
        self.assertIn("broken_reference", [x["code"] for x in inv["findings"]])

    def test_duplicates_reject_both(self):
        r = run(DEMO)
        items = next(l for l in r["loads"] if l.name == "items")
        dup = [x for x in items.rows if x.clean["External ID"] == "BRK-100"]
        self.assertEqual(len(dup), 2)
        self.assertTrue(all(x.rejected for x in dup))

    def test_journal_balance_all_lines(self):
        r = run(DEMO)
        journals = next(l for l in r["loads"] if l.name == "journals")
        bad = [x for x in journals.rows if x.clean["Journal ID"] == "OB-2"]
        self.assertTrue(all(any(f.code == "unbalanced" for f in x.findings) for x in bad))
        self.assertEqual(2, sum(not x.rejected for x in journals.rows))

    def test_clean_numbers_dates(self):
        self.assertEqual(str(_decimal("($1,200.50)")), "-1200.50")
        self.assertEqual(_date("2026-04-22"), "2026-04-22")
        self.assertEqual(_date("22/04/2026"), "2026-04-22")
        with self.assertRaises(ValueError): _date("04/05/2026", "auto")
        self.assertEqual(_date("04/05/2026", True), "2026-05-04")
        self.assertEqual(_date("04/05/2026", False), "2026-04-05")
        with self.assertRaises(ValueError): _date("04/22/2026", True)

    def test_reports_and_csvs(self):
        with tempfile.TemporaryDirectory() as d:
            s = build(run(DEMO), Path(d)/"out", pdf=False)
            p = Path(d)/"out"
            self.assertTrue((p/"report.json").is_file())
            self.assertTrue((p/"customers.rejects.csv").is_file())
            self.assertEqual(s["loadable_rows"], 11)
            self.assertIn("source_line", (p/"customers.rejects.csv").read_text(encoding="utf-8-sig"))
            self.assertIn("line", (p/"report.md").read_text(encoding="utf-8"))

    def test_pdf_single_page(self):
        try: import reportlab
        except ImportError: self.skipTest("reportlab optional")
        with tempfile.TemporaryDirectory() as d:
            build(run(DEMO), d, pdf=True)
            blob = (Path(d)/"report.pdf").read_bytes()
            self.assertTrue(blob.startswith(b"%PDF"))
            self.assertLess(blob.count(b"/Type /Page "), 2)

    def test_approval_stales(self):
        with tempfile.TemporaryDirectory() as d:
            spec = Path(d)/"spec.toml"
            spec.write_text("[project]\nname='A'\n")
            self.assertFalse(status(spec)["approved"])
            with self.assertRaises(ValueError): approve(spec, "Reviewer", False)
            approve(spec, "Reviewer", True)
            self.assertTrue(status(spec)["approved"])
            spec.write_text("[project]\nname='B'\n")
            self.assertFalse(status(spec)["approved"])

    def test_unverified_missing_parents(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/"invoices.csv").write_text("Invoice Number,Customer ID,Invoice Date\nA-1,C1001,2026-01-02\n")
            (root/"s.toml").write_text("[[load]]\nname='i'\ntemplate='netsuite.open_invoice'\nsource='invoices.csv'\n")
            s = summary(run(root/"s.toml"))
            self.assertEqual(s["status"], "UNVERIFIED")
            self.assertEqual(s["loadable_rows"], 1)
            self.assertTrue(s["unchecked_dependencies"])

    def test_formula_text_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"x.csv").write_text("Customer ID,Customer Name\n1,=DANGEROUS()\n")
            (root/"s.toml").write_text("[[load]]\nname='x'\ntemplate='netsuite.customer'\nsource='x.csv'\n")
            s = summary(run(root/"s.toml"))
            self.assertEqual(s["status"], "NOT READY")
            self.assertTrue(any(f["message"].startswith("Potential spreadsheet") for f in s["loads"][0]["findings"]))

    def test_bad_csv_headers(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.csv"
            p.write_text("ID,ID\n1,2\n")
            with self.assertRaises(SourceError): read_rows(p)

    def test_xlsx_shared_strings(self):
        # Minimal OPC xlsx; no external spreadsheet dependency needed.
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.xlsx"
            book = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
            rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'
            shared = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>ID</t></si><si><t>Company</t></si><si><t>Test Company</t></si></sst>'
            ws = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2"><v>101</v></c><c r="B2" t="s"><v>2</v></c></row></sheetData></worksheet>'
            with ZipFile(p,"w") as z:
                z.writestr("xl/workbook.xml",book); z.writestr("xl/_rels/workbook.xml.rels",rels)
                z.writestr("xl/sharedStrings.xml",shared); z.writestr("xl/worksheets/sheet1.xml",ws)
            columns, rows=read_rows(p)
            self.assertEqual(columns,["ID","Company"])
            self.assertEqual(rows[0][1]["Company"],"Test Company")
            self.assertEqual(rows[0][0],2)

    def test_peitho_review_and_suppression(self):
        with (ROOT/"examples/peitho_leads.csv").open(encoding="utf-8") as f:
            rows = list(__import__("csv").DictReader(f))
        self.assertEqual(grade(rows[0])[0], "MEDIUM")
        self.assertEqual(grade(rows[1])[0], "HIGH")
        self.assertEqual(grade(rows[2])[0], "NEEDS_REVIEW")
        self.assertEqual(grade(rows[3])[0], "SUPPRESSED")
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/"drafts.md"
            self.assertEqual(draft(ROOT/"examples/peitho_leads.csv", output), 2)
            data=output.read_text(encoding="utf-8")
            self.assertNotIn("Example Unreviewed Company", data)
            self.assertNotIn("Example Suppressed Company", data)
            self.assertIn("No access to your production system", data)

    def test_empty_no_false_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"empty.csv").write_text("Customer ID,Customer Name\n")
            (root/"spec.toml").write_text("[[load]]\nname='c'\ntemplate='netsuite.customer'\nsource='empty.csv'\n")
            self.assertEqual(summary(run(root/"spec.toml"))["status"], "UNVERIFIED")

    def test_mcp_workspace_boundary(self):
        from olympus_erp.mcp import _within
        with tempfile.TemporaryDirectory() as d:
            workspace=Path(d).resolve()
            with self.assertRaises(ValueError): _within(workspace,"../outside.csv")

    def test_xlsx_formulas_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"f.xlsx"
            book='<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
            rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
            xml='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Name</t></is></c></row><row r="2"><c r="A2"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>'
            with ZipFile(p,"w") as z:
                z.writestr("xl/workbook.xml",book); z.writestr("xl/_rels/workbook.xml.rels",rels)
                z.writestr("xl/worksheets/sheet1.xml",xml)
            with self.assertRaisesRegex(SourceError, "formulas"):
                read_rows(p)

    def test_mcp_handshake_and_tools(self):
        requests=[{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}},
                  {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},
                  {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_templates","arguments":{}}}]
        process=subprocess.run([sys.executable,"-m","olympus_erp.cli","mcp","--workspace",str(ROOT)],
                               input="\n".join(json.dumps(x) for x in requests)+"\n", capture_output=True, text=True,
                               env={**os.environ, "PYTHONPATH":str(ROOT/"src")}, timeout=10)
        self.assertEqual(process.returncode,0,process.stderr)
        answers=[json.loads(x) for x in process.stdout.splitlines()]
        self.assertEqual(len(answers),3)
        self.assertEqual(answers[0]["result"]["serverInfo"]["name"],"hermes")
        self.assertTrue(any(t["name"]=="build" for t in answers[1]["result"]["tools"]))
        self.assertIn("netsuite.customer",answers[2]["result"]["content"][0]["text"])

if __name__ == "__main__":
    unittest.main()
