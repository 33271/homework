"""Calibrate a bounded per-workload GateANN budget; dispatch the course adapter.

This is a batch-level prototype, not per-query C++ routing. Calibration CSVs
must come from separate calibration queries, never the held-out evaluation set.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

BUCKETS = ('low', 'medium', 'high')

def calibrate(rows, target=90.0, max_l=2560):
    if not 0 < target <= 100 or max_l < 10:
        raise ValueError('invalid target or L cap')
    groups = {}
    identity = set()
    for r in rows:
        if r['system'] != 'gateann':
            continue
        if r['bucket'] not in BUCKETS:
            raise ValueError('unknown workload bucket')
        identity.add((r['tier'], r['system_commit'], r['k'], r['threads'], r['beamwidth']))
        if (int(r['k']), int(r['threads']), int(r['beamwidth'])) != (10, 1, 8):
            raise ValueError('requires K=10, threads=1, beamwidth=8')
        l, recall = int(r['L']), float(r['recall_percent'])
        if l < 10 or not math.isfinite(recall) or not 0 <= recall <= 100:
            raise ValueError('invalid measurement')
        groups.setdefault((r['bucket'], l), []).append(r)
    if len(identity) != 1:
        raise ValueError('calibration mixes tiers/commits/settings, or has no GateANN rows')
    selected = {}
    for bucket in BUCKETS:
        candidates = []
        for (b, l), rr in groups.items():
            if b != bucket or l > max_l:
                continue
            if len(rr) != 3 or {int(r['repeat']) for r in rr} != {1, 2, 3}:
                raise ValueError(f'{bucket} L={l}: requires exactly three distinct repeats')
            if min(float(r['recall_percent']) for r in rr) >= target:
                candidates.append(l)
        if not candidates:
            raise ValueError(f'{bucket}: no measured budget meets Recall>={target}% in all repeats within L<={max_l}')
        selected[bucket] = min(candidates)
    tier, commit, k, threads, beamwidth = next(iter(identity))
    return dict(version=1, scope='workload_bucket', target_recall=target,
                max_l=max_l, budgets=selected, tier=tier, system_commit=commit,
                k=int(k), threads=int(threads), beamwidth=int(beamwidth), full_adj_neighbors=32)

def command(policy, bucket, repo, dataset, run_root, run_id):
    if policy.get('version') != 1 or policy.get('scope') != 'workload_bucket':
        raise ValueError('unsupported policy')
    if (policy.get('k'), policy.get('threads'), policy.get('beamwidth'), policy.get('full_adj_neighbors')) != (10, 1, 8, 32):
        raise ValueError('unsupported policy settings')
    l = policy['budgets'].get(bucket)
    if type(l) is not int or not 10 <= l <= policy['max_l']:
        raise ValueError('missing/invalid budget or exceeds cap')
    adapter = Path(__file__).resolve().parents[1] / 'adapters/gateann_adapter.py'
    return [sys.executable, str(adapter), 'search', '--repo', str(repo),
            '--dataset-root', str(dataset), '--tier', policy['tier'],
            '--run-root', str(run_root), '--run-id', run_id, '--bucket', bucket,
            '--threads', '1', '--beamwidth', '8', '--k', '10', '--L', str(l),
            '--full-adj-neighbors', '32', '--mem-L', '0', '--cache-budget', '0']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('calibrate')
    c.add_argument('--csv',type=Path,required=True)
    c.add_argument('--output',type=Path,required=True)
    c.add_argument('--calibration-id',required=True,help='Identity of the separate calibration query set')
    c.add_argument('--target',type=float,default=90.0)
    c.add_argument('--max-L',type=int,default=2560)
    r=sub.add_parser('run')
    r.add_argument('--policy',type=Path,required=True)
    r.add_argument('--bucket',choices=BUCKETS,required=True)
    for name in ('repo','dataset-root','run-root'):
        r.add_argument('--'+name,type=Path,required=True)
    r.add_argument('--run-id',required=True)
    r.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.action=='calibrate':
        rows=list(csv.DictReader(a.csv.open(encoding='utf-8-sig')))
        policy=calibrate(rows,a.target,a.max_L)
        policy.update(calibration_id=a.calibration_id,
                      calibration_sha256=hashlib.sha256(a.csv.read_bytes()).hexdigest())
        # Never replace an earlier policy on failed or accidental recalibration.
        with a.output.open('x',encoding='utf8') as f:json.dump(policy,f,ensure_ascii=False,indent=2)
        print(json.dumps(policy,ensure_ascii=False))
    else:
        policy=json.loads(a.policy.read_text(encoding='utf8'))
        cmd=command(policy,a.bucket,a.repo,a.dataset_root,a.run_root,a.run_id)
        print(json.dumps(cmd,ensure_ascii=False),flush=True)
        if not a.dry_run:
            commit=subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip()
            if commit != policy['system_commit']:raise ValueError('source commit differs from calibration')
            return subprocess.run(cmd,check=False).returncode
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError) as e:
        print(f'Budget policy rejected: {e}',file=sys.stderr);sys.exit(2)
