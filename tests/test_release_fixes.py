"""Regression tests for bugs found during the v0.4 release-readiness pass."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from olympus_erp import incidents, peitho, dashboard  # noqa: E402


def mcp_session(lines):
    proc = subprocess.run([sys.executable, "-m", "olympus_erp.cli", "mcp", "--workspace", str(ROOT)],
                          input="\n".join(lines) + "\n", capture_output=True, text=True, timeout=20,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    return proc, [json.loads(x) for x in proc.stdout.splitlines()]


class McpProtocolTests(unittest.TestCase):
    def test_parse_error_does_not_reuse_previous_id(self):
        proc, out = mcp_session(['{"jsonrpc":"2.0","id":7,"method":"ping"}', "not json"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out[1]["id"], None)
        self.assertEqual(out[1]["error"]["code"], -32700)

    def test_non_object_request_does_not_crash_server(self):
        proc, out = mcp_session(["[1,2]", "42", '{"jsonrpc":"2.0","id":1,"method":"ping"}'])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([m["error"]["code"] for m in out[:2]], [-32600, -32600])
        self.assertEqual(out[2], {"jsonrpc": "2.0", "id": 1, "result": {}})

    def test_unknown_tool_and_method_codes(self):
        _, out = mcp_session(['{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"nope","arguments":{}}}',
                              '{"jsonrpc":"2.0","id":2,"method":"bogus"}'])
        self.assertEqual(out[0]["error"]["code"], -32602)
        self.assertIn("Unknown tool", out[0]["error"]["message"])
        self.assertEqual(out[1]["error"]["code"], -32601)

    def test_argument_schema_enforced(self):
        _, out = mcp_session([
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"profile_file","arguments":"x"}}',
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"profile_file","arguments":{}}}',
            '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"profile_file","arguments":{"path":"a.csv","x":1}}}',
            '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"incident_create","arguments":{"title":"abc","severity":"urgent","owner":"Kurt"}}}'])
        self.assertTrue(all(m["error"]["code"] == -32602 for m in out), out)

    def test_tool_failure_is_iserror_result(self):
        _, out = mcp_session(['{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"profile_file","arguments":{"path":"/etc/passwd"}}}'])
        self.assertTrue(out[0]["result"]["isError"])
        self.assertIn("outside", out[0]["result"]["content"][0]["text"])

    def test_notifications_get_no_reply_and_version_negotiated(self):
        _, out = mcp_session(['{"jsonrpc":"2.0","method":"notifications/initialized"}',
                              '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26"}}'])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-03-26")


class IncidentConcurrencyTests(unittest.TestCase):
    def test_parallel_creates_keep_hash_chain_valid(self):
        with tempfile.TemporaryDirectory() as d:
            errors = []
            def worker(i):
                try: incidents.create(d, f"Ticket {i}", "low", "Kurt")
                except Exception as exc: errors.append(exc)
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
            for t in threads: t.start()
            for t in threads: t.join()
            self.assertEqual(errors, [])
            self.assertEqual(incidents.listing(d)["total"], 25)


class PeithoSanitizeTests(unittest.TestCase):
    def test_source_fields_cannot_inject_markdown_lines(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "l.csv"
            src.write_text('company,contact,source_url,source_note,erp_project_announced,reviewed,do_not_contact\n'
                           'Co,Al,"https://x.example\n## Fake",'
                           '"note\nSubject: injected",yes,yes,no\n', encoding="utf-8")
            peitho.draft(src, Path(d) / "out.md")
            text = (Path(d) / "out.md").read_text()
            self.assertNotIn("\n## Fake", text)
            self.assertNotIn("\nSubject: injected", text)


class DashboardPortTests(unittest.TestCase):
    def test_port_in_use_is_friendly_exit(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); s.listen()
            port = s.getsockname()[1]
            with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit) as ctx:
                dashboard.serve(d, port)
            self.assertIn("cannot listen", str(ctx.exception.code))


if __name__ == "__main__":
    unittest.main()
