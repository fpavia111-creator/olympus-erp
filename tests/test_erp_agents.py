import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from olympus_erp import erp_agents as a
from olympus_erp.mcp import _dispatch, TOOL_SPECS

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.p = {"project_name":"Testing","company_name":"Company","target_system":"NetSuite",
                  "source_systems":["Legacy"],"workflows":["Invoice-to-cash"],"data_objects":["customer"]}
        (self.root/'project.json').write_text(json.dumps(self.p))

    def test_assessment_missing_and_conservative(self):
        result = a.assess_project(self.p)
        self.assertIn('go_live_date', result['missing_discovery_fields'])
        self.assertEqual('NO GO — NOT VERIFIED', a.go_live_gate(self.p)['decision'])

    def test_uat_per_workflow(self):
        m,cases = a.apollo(self.p)
        self.assertEqual(3, len(cases))
        self.assertTrue(all(c['status']=='NOT RUN' for c in cases))
        self.assertIn('Invoice-to-cash',m)

    def test_rollout_relative_and_absolute(self):
        self.assertIn('T-21 days', a.chronos(self.p))
        p = {**self.p,"go_live_date":"2027-04-15"}
        self.assertIn('2027-03-25',a.chronos(p))

    def test_roi_refuses_missing(self):
        self.assertIn('MISSING INPUTS', a.plutus(self.p))

    def test_roi_scenarios_math(self):
        p = {**self.p,"financial":{"manual_hours_per_month":100,"fully_loaded_hourly_rate":50,"subscription_per_month":100,"setup_cost":300}}
        r = a.plutus(p)
        self.assertIn('$500.00',r)
        self.assertIn('$400.00',r)

    def test_pack_non_overwrite(self):
        result = a.pack(self.p, self.root/'pack')
        self.assertEqual(10,len(result['files']))
        self.assertTrue((self.root/'pack/04_chronos_cutover.md').is_file())
        with self.assertRaises(ValueError): a.pack(self.p,self.root/'pack')

    def test_rejects_invalid_input(self):
        (self.root/'project.json').write_text(json.dumps({**self.p,"integrations":[{"from":"x"}]}))
        with self.assertRaises(ValueError): a.load_project(self.root/'project.json')

    def test_mcp_exposes_and_dispatches(self):
        names = [x[0] for x in TOOL_SPECS]
        for name in ('assess_project','draft_erp_roadmap','generate_erp_pack','go_live_gate'):
            self.assertIn(name,names)
        self.assertEqual('Testing',_dispatch('assess_project',{"project":"project.json"},self.root)['project'])
        with self.assertRaises(ValueError): _dispatch('assess_project',{"project":"../outside.json"},self.root)
        self.assertEqual(10,len(_dispatch('generate_erp_pack',{"project":"project.json","output":"project_pack"},self.root)['files']))

if __name__ == '__main__': unittest.main()
