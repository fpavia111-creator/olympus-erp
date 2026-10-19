"""v0.4 functional and safety regression checks."""
import base64
import json
import socket
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from olympus_erp import reconcile, uat_evidence, incidents, dashboard
from olympus_erp.mcp import _dispatch, TOOL_SPECS


def STEPS_PASS(case_id, n=3):
    return {f'{case_id}.S{i}': 'PASS' for i in range(1, n + 1)}


class V04Tests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.project = self.root / 'projects' / 'p' / 'project.json'
        self.project.parent.mkdir(parents=True)
        self.project.write_text(json.dumps({'project_name': 'Test', 'company_name': 'Testco', 'target_system': 'NetSuite',
                                            'workflows': ['Quote-to-cash', 'Procure-to-pay']}))

    def file(self, name, text):
        p = self.root / name
        p.write_text(text, encoding='utf8')
        return p

    def test_poseidon_detects_amounts_counts_and_missing(self):
        a = self.file('from.csv', 'Id,Amount\nA,1\nA,2\nB,4\nC,5\n')
        b = self.file('to.csv', 'Id,Amount\nA,3\nB,4\nX,9\n')
        r = reconcile.reconcile(a, b, 'Id','Id','Amount','Amount')
        self.assertEqual('NOT RECONCILED', r['status'])
        self.assertEqual('12', r['source_total'])
        self.assertEqual('16', r['target_total'])
        self.assertEqual(3, r['different_keys'])
        self.assertEqual({'A','C','X'}, {x['key'] for x in r['differences']})
        self.assertEqual('count_mismatch', next(x for x in r['differences'] if x['key']=='A')['issue'])

    def test_poseidon_pass_and_missing_and_invalid(self):
        a = self.file('from.csv', 'Ref,Amt\nA,$1.00\nB,(2)\n')
        b = self.file('to.csv', 'Key,Number\nA,1.00\nB,-2\n')
        r = reconcile.reconcile(a,b,'Ref','Key','Amt','Number')
        self.assertEqual('RECONCILED',r['status'])
        b.write_text('Key,Number\nA,1.00\nB,not-a-number\n')
        self.assertEqual('NOT RECONCILED',reconcile.reconcile(a,b,'Ref','Key','Amt','Number')['status'])
        with self.assertRaises(ValueError): reconcile.reconcile(a,b,'Ref','Key','Amt','Number', tolerance='NaN')

    def test_clio_evidence_and_staleness(self):
        e=self.file('proof.txt','Human marked this case passed in sandbox on Monday')
        # Evidence must be in the current project directory.
        kw=dict(executed_at='2026-10-01T10:00', step_results=STEPS_PASS('UAT-01-1'))
        with self.assertRaises(ValueError): uat_evidence.record(self.project, 'UAT-01-1','PASS','Reviewer',e,self.root,**kw)
        evidence=self.project.parent/'proof.txt'
        evidence.write_bytes(e.read_bytes())
        r=uat_evidence.record(self.project, 'UAT-01-1','PASS','Reviewer',evidence,self.root,**kw)
        self.assertEqual(1,r['passed'])
        self.assertFalse(r['all_pass_claimed'])
        evidence.write_text('evidence changed')
        r=uat_evidence.status(self.project)
        self.assertEqual(0,r['passed'])
        self.assertEqual(1,r['stale_evidence'])
        evidence.write_bytes(e.read_bytes())
        new=json.loads(self.project.read_text());new['industry']='Manufacturing'
        self.project.write_text(json.dumps(new))
        self.assertTrue(uat_evidence.status(self.project)['stale'])
        with self.assertRaises(ValueError): uat_evidence.record(self.project, 'UAT-99-9','PASS','Reviewer',evidence,self.root,executed_at='2026-10-01T10:00')

    def test_argus_create_update_detect_tampering(self):
        x=incidents.create(self.root,'Broken AR import','high','Support owner')
        self.assertEqual(1, incidents.listing(self.root)['unresolved'])
        incidents.change(self.root,x['id'],'investigating','Investigator')
        self.assertEqual('investigating',incidents.listing(self.root)['tickets'][0]['status'])
        incidents.change(self.root,x['id'],'resolved','Investigator')
        self.assertEqual(0, incidents.listing(self.root)['unresolved'])
        with self.assertRaises(ValueError): incidents.change(self.root,x['id'],'open','Investigator')
        p=self.root/'olympus_incidents.jsonl'
        data=p.read_text().replace('Broken AR','Fake AR')
        p.write_text(data)
        with self.assertRaises(ValueError): incidents.listing(self.root)

    def test_mcp_tools_and_path_boundary(self):
        for t in ('reconcile_exports','uat_status','incident_list','incident_create','incident_update'):
            self.assertIn(t,[x[0] for x in TOOL_SPECS])
        self.assertEqual(5,len([x for x in TOOL_SPECS if x[0] in
                             ('reconcile_exports','uat_status','incident_list','incident_create','incident_update')]))
        self.assertEqual(0,_dispatch('incident_list', {},self.root)['total'])
        _dispatch('incident_create',{'title':'Problem during demo','severity':'low','owner':'Operator'},self.root)
        self.assertEqual(1,_dispatch('incident_list',{},self.root)['total'])
        with self.assertRaises(ValueError): _dispatch('uat_status', {'project':'../outside.json'},self.root)

    def test_dashboard_full_local_workflow(self):
        p=dashboard.command(self.root,{'action':'demo_project'})
        self.assertEqual(32,len(p['id']))
        r=dashboard.command(self.root,{'action':'make_pack','id':p['id']})
        self.assertEqual(10,len(r['files']))
        csv=b'External ID,Company Name,Email\nA,Acme,hi@example.com\nB,Beta,not-email\n'
        result=dashboard.command(self.root,{'action':'diagnose','id':p['id'], 'template':'netsuite.customer',
                        'extension':'.csv','data_base64':base64.b64encode(csv).decode()})
        self.assertEqual(2,result['results']['total_rows'])
        self.assertGreater(result['results']['errors'],0)
        with self.assertRaises(ValueError): dashboard.command(self.root, {'action':'assess','id':'../../secrets'})
        self.assertEqual(0,dashboard.command(self.root,{'action':'incidents','id':p['id']})['total'])
        evidence=b'Sandbox UAT notes'
        r=dashboard.command(self.root,{'action':'uat_record','id':p['id'],'case_id':'UAT-01-1',
            'result':'PASS','reviewer':'Business reviewer','extension':'.txt','executed_at':'2026-10-01T10:00',
            'step_results':STEPS_PASS('UAT-01-1'),
            'data_base64':base64.b64encode(evidence).decode()})
        self.assertEqual(1,r['passed'])
        self.assertEqual(0,r['stale_evidence'])
        with self.assertRaises(ValueError): dashboard.command(self.root,{'action':'uat_record','id':p['id'],
            'case_id':'UAT-01-2','result':'PASS','reviewer':'Reviewer','extension':'.pdf','data_base64':base64.b64encode(b'not pdf').decode()})

    def test_dashboard_explicit_project_deletion(self):
        p=dashboard.command(self.root, {'action':'demo_project'})
        with self.assertRaises(ValueError):
            dashboard.command(self.root, {'action':'delete_project', 'id':p['id'], 'confirm_name':'wrong'})
        result=dashboard.command(self.root, {'action':'delete_project', 'id':p['id'],
                                             'confirm_name':'Olympus manufacturing demo'})
        self.assertEqual(p['id'], result['deleted_project'])
        with self.assertRaises(ValueError): dashboard.command(self.root,{'action':'assess','id':p['id']})

    def test_dashboard_reconcile_upload(self):
        p=dashboard.command(self.root,{'action':'demo_project'})
        data=base64.b64encode(b'Id,Amount\nX,100.00\n').decode()
        r=dashboard.command(self.root,{'action':'reconcile','id':p['id'],
           'source_extension':'.csv','source_data_base64':data,
           'target_extension':'.csv','target_data_base64':data,
           'source_key':'Id','target_key':'Id','source_amount':'Amount','target_amount':'Amount','tolerance':'0.01'})
        self.assertEqual('RECONCILED',r['status'])

    def test_local_http_host_origin_and_token(self):
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        server=ThreadingHTTPServer(('127.0.0.1',port),dashboard.make_handler(self.root,'secret',port))
        self.addCleanup(server.server_close)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{port}/'
        with urlopen(url,timeout=3) as r:
            self.assertIn(b'OLYMPUS ERP',r.read())
            self.assertIn('Content-Security-Policy',r.headers)
        body=b'{"action":"list_projects"}'
        req=Request(url+'api/action', data=body,headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as err: urlopen(req,timeout=3)
        self.assertEqual(403,err.exception.code)
        req=Request(url+'api/action',data=body,headers={'Content-Type':'application/json','X-Olympus-Token':'secret','Origin':'https://attacker.example'},method='POST')
        with self.assertRaises(HTTPError) as err: urlopen(req,timeout=3)
        self.assertEqual(403,err.exception.code)
        req=Request(url+'api/action',data=body,headers={'Content-Type':'application/json','X-Olympus-Token':'secret'},method='POST')
        with urlopen(req,timeout=3) as resp:
            self.assertTrue(json.load(resp)['ok'])

if __name__=='__main__': unittest.main()
