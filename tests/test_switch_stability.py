"""ALCG v0.33 synthetic switch stability and genuine past-only receipts."""
from __future__ import annotations

import copy
from fractions import Fraction
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import alcg
import model_selection as v32
import workload_estimator as v30
import switch_stability as g

ROOT=Path(__file__).resolve().parents[1]


class SwitchGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads(g.REPORT.read_text(encoding='utf-8'))
        cls.records={(r['scenario'],r['at_tick']):r for r in cls.report['issuances']}

    def test_01_format_and_source_pinning(self):
        self.assertEqual(g.config(),g.expected_config())
        self.assertEqual(self.report['format'],g.FORMAT)

    def test_02_canonical_fraction_reduces(self):
        self.assertEqual(g.exact(Fraction(2,4)),{'num':1,'den':2})
        self.assertEqual(g.frac({'num':1,'den':2}),Fraction(1,2))

    def test_03_noncanonical_fraction_rejected(self):
        for wrong in ({'num':2,'den':4},{'num':0,'den':0},
                      {'num':False,'den':1},{'num':1,'den':2,'x':0}):
            with self.subTest(wrong=wrong),self.assertRaises(g.GuardError):
                g.frac(wrong)

    def test_04_posterior_exact_tails(self):
        self.assertEqual(g.beta_tail_probability(0,0),Fraction(1,2))
        self.assertEqual(g.beta_tail_probability(1,1),Fraction(1,2))
        self.assertEqual(g.beta_tail_probability(2,0),Fraction(7,8))
        self.assertEqual(g.beta_tail_probability(3,0),Fraction(15,16))

    def test_05_beta_input_validation(self):
        for wins,losses in ((True,0),(-1,0),(1,1.5)):
            with self.subTest(pair=(wins,losses)),self.assertRaises(g.GuardError):
                g.beta_tail_probability(wins,losses)

    def test_06_warmup_keeps_incumbent(self):
        d=g.decision([], 'RAW',0,None)
        self.assertEqual((d['selected'],d['reason']),('RAW','INSUFFICIENT_CLOSED_EVIDENCE'))

    def test_07_one_win_is_not_evidence(self):
        d=g.decision([{'RAW':Fraction(1,2),'LAGGED':Fraction(1,10),'HEDGE':1}], 'RAW',1,None)
        self.assertEqual(d['selected'],'RAW')

    def test_08_persistent_two_wins_can_switch(self):
        row={'RAW':Fraction(1,2),'LAGGED':Fraction(1,10),'HEDGE':Fraction(3,4)}
        d=g.decision([row,row], 'RAW',2,None)
        self.assertEqual((d['selected'],d['reason']),('LAGGED','PERSISTENT_ADVANTAGE_SWITCH'))
        self.assertEqual(next(x['posterior_win_score'] for x in d['candidate_evidence']
                              if x['expert']=='LAGGED'),{'num':7,'den':8})

    def test_09_small_margin_is_not_enough(self):
        row={'RAW':Fraction(1,10),'LAGGED':Fraction(999,10000),'HEDGE':1}
        self.assertEqual(g.decision([row,row],'RAW',2,None)['selected'],'RAW')

    def test_10_tied_outcomes_no_switch(self):
        row={'RAW':Fraction(1,5),'LAGGED':Fraction(1,5),'HEDGE':Fraction(1,5)}
        self.assertEqual(g.decision([row,row,row],'RAW',3,None)['selected'],'RAW')

    def test_11_cooldown_keeps_previous(self):
        row={'RAW':Fraction(1,2),'LAGGED':Fraction(1,10),'HEDGE':1}
        d=g.decision([row,row],'RAW',3,2)
        self.assertEqual((d['selected'],d['reason']),('RAW','COOLDOWN_KEEP'))

    def test_12_cooldown_ends_after_one_window(self):
        row={'RAW':Fraction(1,2),'LAGGED':Fraction(1,10),'HEDGE':1}
        self.assertEqual(g.decision([row,row],'RAW',4,2)['selected'],'LAGGED')

    def test_13_future_evidence_rejected(self):
        row={'RAW':1,'LAGGED':0,'HEDGE':1}
        with self.assertRaises(g.GuardError):g.decision([row,row],'RAW',1,None)

    def test_14_future_switch_index_rejected(self):
        with self.assertRaises(g.GuardError):g.decision([], 'RAW',3,3)

    def test_15_missing_expert_rejected(self):
        with self.assertRaises(g.GuardError):
            g.decision([{'RAW':0,'LAGGED':1}],'RAW',1,None)

    def test_16_float_loss_rejected(self):
        with self.assertRaises(g.GuardError):
            g.decision([{'RAW':0.1,'LAGGED':0,'HEDGE':1}],'RAW',1,None)

    def test_17_alternating_avoids_thrash(self):
        p=self.report['stress']['alternating']
        self.assertEqual((p['gated_switches'],p['naive_switches']),(0,10))
        self.assertLess(g.frac(p['gated_realized_total_loss']),g.frac(p['naive_realized_total_loss']))

    def test_18_short_spike_is_ignored(self):
        p=self.report['stress']['single_spike']
        self.assertEqual((p['gated_switches'],p['naive_switches']),(0,2))

    def test_19_sustained_shift_is_detected_late(self):
        p=self.report['stress']['sustained_shift']
        self.assertEqual(p['post_shift_first_gated_change'],9)
        self.assertGreater(g.frac(p['gated_realized_total_loss']),g.frac(p['naive_realized_total_loss']))

    def test_20_flat_stays_stable(self):
        p=self.report['stress']['flat']
        self.assertEqual((p['gated_switches'],p['naive_switches']),(0,0))

    def test_21_all_stress_tracks_exactly_replayed(self):
        for name, saved in self.report['stress'].items():
            self.assertEqual(g.stress_evaluate(name),saved)

    def test_22_pinned_issuance_counts(self):
        self.assertEqual((len(self.report['issuances']),len(self.report['settlements'])),(20,20))
        self.assertEqual(self.report['summary']['eligible_scored_windows'],15)

    def test_23_deferral_persists_in_sparse(self):
        self.assertTrue(all(self.records[('sparse',cut)]['selected']=='DEFER' for cut in g.CUTS))

    def test_24_bounded_realized_score_not_assumed_better(self):
        s=self.report['summary']
        self.assertEqual(s['total_switches'],4)
        self.assertGreater(g.frac(s['gated_mean_combined_brier']),g.frac(s['v032_mean_combined_brier']))

    def test_25_no_future_outcome_in_receipts(self):
        for row in self.report['issuances']:
            for p in row['prior_closed_receipts']:
                self.assertLessEqual(p['prior_cut']+g.HORIZON,row['at_tick'])
                self.assertEqual(set(p['losses']),set(g.EXPERTS))

    def test_26_prefix_issuance_matches_frozen_receipt(self):
        full=v32.stream('churn')
        cut=96
        past=v32.prefix(full,cut)
        row=self.records[('churn',cut)]
        self.assertEqual(g.issue_at(past,cut),row)
        self.assertTrue(g.verify_issuance(row,past))

    def test_27_future_changes_do_not_affect_prior_issuance(self):
        full=v32.stream('drift')
        cut=96
        before=g.issue_at(v32.prefix(full,cut),cut)
        event=copy.deepcopy(full['events'])
        event[105]={'tick':105,'kind':'idle'}
        edited=v30.document('drift','synthetic-fixture',event)
        after=g.issue_at(v32.prefix(edited,cut),cut)
        self.assertEqual(before,after)

    def test_28_refuse_complete_stream_as_past(self):
        with self.assertRaises(g.GuardError):
            g.issue_at(v32.stream('stable'),96)

    def test_29_tampered_signature_fails(self):
        row=copy.deepcopy(self.records[('churn',96)])
        row['selected']='RAW'
        with self.assertRaises(g.GuardError):
            g.verify_issuance(row,v32.prefix(v32.stream('churn'),96))

    def test_30_self_rehashed_forgery_fails(self):
        row=copy.deepcopy(self.records[('churn',96)])
        row['selected']='RAW' if row['selected']!='RAW' else 'LAGGED'
        row['issue_sha256']=g.digest({k:v for k,v in row.items() if k!='issue_sha256'})
        with self.assertRaises(g.GuardError):
            g.verify_issuance(row,v32.prefix(v32.stream('churn'),96))

    def test_31_alcg_roundtrip(self):
        for row in self.report['issuances']:
            text=g.expression(row)
            self.assertEqual(alcg.render(alcg.parse(text)),text)
            self.assertTrue(g.verify_expression(text,row))

    def test_32_alcg_tamper_rejected(self):
        row=self.records[('stable',96)]
        text=g.expression(row)
        with self.assertRaises(g.GuardError):
            g.verify_expression(text.replace('GATE_V033','GATE_V031'),row)

    def test_33_current_report_integrity(self):
        self.assertEqual(self.report['report_sha256'],g.digest(
            {k:v for k,v in self.report.items() if k!='report_sha256'}))

    def test_34_public_fixture_and_sample_recompute(self):
        self.assertEqual(g.check()['status'],'PASS')
        self.assertEqual(len(alcg.read_expressions(g.SAMPLES)),20)

    def test_35_wrong_config_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.json'
            cfg=copy.deepcopy(g.config()); cfg['lookback_closed_windows']=100
            p.write_text(json.dumps(cfg),encoding='utf-8')
            with patch.object(g,'CONFIG',p),self.assertRaises(g.GuardError):
                g.config()

    def test_36_cli_stress(self):
        p=subprocess.run([sys.executable,'switch_stability.py','stress','--case','alternating'],
                         cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['naive_switches'],10)

    def test_37_cli_issue(self):
        p=subprocess.run([sys.executable,'switch_stability.py','issue','--case','drift','--at','128'],
                         cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('GATE_V033(',p.stdout)

    def test_38_cli_report(self):
        p=subprocess.run([sys.executable,'switch_stability.py','report'],
                         cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['total_switches'],4)

    def test_39_non_empirical_limitations_explicit(self):
        warnings=' '.join(self.report['limitations']).lower()
        self.assertIn('synthetic',warnings)
        self.assertIn('not calibrated confidence',warnings)
        self.assertIn('not optimal',warnings)


if __name__=='__main__':
    unittest.main()
