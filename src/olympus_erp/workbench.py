"""Human-invoked Poseidon, Clio and Argus operations for local pilots."""
import argparse
import json
from pathlib import Path
from . import incidents, reconcile, uat_evidence


def main(argv=None):
    p=argparse.ArgumentParser(prog='olympus-workbench', description='Offline operations CLI (no ERP or cloud access)')
    p.add_argument('--workspace',default='.',help='Root folder containing approved local project files')
    sub=p.add_subparsers(dest='command',required=True)
    x=sub.add_parser('reconcile',help='Compare source/target key amounts and counts, read only')
    for name in ('source','target','source-key','target-key','source-amount','target-amount'):
        x.add_argument('--'+name,required=True)
    x.add_argument('--tolerance',default='0.01')
    x=sub.add_parser('uat-status'); x.add_argument('--project',required=True)
    x=sub.add_parser('uat-record',help='Human self-attested UAT record, not identity verification')
    for name in ('project','case-id','result','reviewer','executed-at'):
        x.add_argument('--'+name,required=True)
    x.add_argument('--evidence',help='Evidence file inside the project folder (fingerprinted)')
    x.add_argument('--evidence-link',help='http(s) link to evidence (recorded, not verified)')
    x.add_argument('--step',action='append',metavar='STEP_ID=RESULT',help='Per-step result, e.g. UAT-01-1.S1=PASS')
    x.add_argument('--notes')
    x.add_argument('--attest',action='store_true',help='Human confirms the results and evidence are genuinely observed')
    sub.add_parser('incidents')
    x=sub.add_parser('incident-new')
    for name in ('title','severity','owner'): x.add_argument('--'+name,required=True)
    x=sub.add_parser('incident-update')
    for name in ('ticket-id','status','actor'): x.add_argument('--'+name,required=True)
    args=p.parse_args(argv)
    root=Path(args.workspace).resolve()
    def inside(value):
        path=(root/value).resolve()
        if not path.is_relative_to(root): raise ValueError('Path outside workspace')
        return path
    try:
        if args.command=='reconcile':
            x=reconcile.reconcile(inside(args.source),inside(args.target),args.source_key,args.target_key,
                                  args.source_amount,args.target_amount,args.tolerance)
        elif args.command=='uat-status': x=uat_evidence.status(inside(args.project))
        elif args.command=='uat-record':
            if not args.attest: raise ValueError('UAT writing requires explicit human --attest')
            steps={}
            for item in args.step or []:
                if '=' not in item: raise ValueError('--step expects STEP_ID=RESULT')
                k,v=item.split('=',1); steps[k.strip()]=v.strip().upper()
            x=uat_evidence.record(inside(args.project),args.case_id,args.result,args.reviewer,
                                   inside(args.evidence) if args.evidence else None,root,
                                   executed_at=args.executed_at,evidence_link=args.evidence_link,
                                   step_results=steps,notes=args.notes)
        elif args.command=='incidents': x=incidents.listing(root)
        elif args.command=='incident-new': x=incidents.create(root,args.title,args.severity,args.owner)
        else: x=incidents.change(root,args.ticket_id,args.status,args.actor)
        print(json.dumps(x,indent=2,ensure_ascii=False))
        if args.command=='reconcile' and x['status']!='RECONCILED': return 1
        return 0
    except (OSError,ValueError,KeyError) as exc:
        p.exit(2, f'olympus-workbench: {exc}\n')

if __name__=='__main__': raise SystemExit(main())
