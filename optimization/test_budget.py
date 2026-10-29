"""Synthetic fixtures check policy safety; these are not benchmark measurements."""
import unittest
from gateann_budget import calibrate, command

def fixture():
    return [dict(system='gateann',bucket=b,L=str(l),repeat=str(r),
                 recall_percent=str(95 if l>=need else 60),tier='formal_1000000',
                 system_commit='fixed-test-commit',k='10',threads='1',beamwidth='8')
            for b,need in [('low',1280),('medium',640),('high',320)]
            for l in [320,640,1280] for r in [1,2,3]]

class BudgetTests(unittest.TestCase):
    def test_select_smallest_and_dispatch(self):
        p=calibrate(fixture())
        self.assertEqual(p['budgets'],dict(low=1280,medium=640,high=320))
        c=command(p,'low','repo','dataset','runs','heldout-r1')
        self.assertEqual(c[c.index('--L')+1],'1280')
        self.assertEqual(c[c.index('--full-adj-neighbors')+1],'32')

    def test_quality_failure_and_budget_cap(self):
        with self.assertRaises(ValueError):calibrate(fixture(),max_l=640)
        rows=fixture();rows[8]['recall_percent']='89'
        with self.assertRaises(ValueError):calibrate(rows)

    def test_duplicate_repeat_and_mixed_config(self):
        rows=fixture();rows[0]['repeat']='2'
        with self.assertRaises(ValueError):calibrate(rows)
        rows=fixture();rows[0]['system_commit']='different'
        with self.assertRaises(ValueError):calibrate(rows)

    def test_invalid_or_missing_runtime_policy(self):
        p=calibrate(fixture());p['budgets']['low']=99999
        with self.assertRaises(ValueError):command(p,'low','r','d','o','x')
        p=calibrate(fixture());del p['budgets']['low']
        with self.assertRaises(ValueError):command(p,'low','r','d','o','x')

if __name__=='__main__':unittest.main()
