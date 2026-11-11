"""ALCG v0.32: locked, prequential synthetic expert switching regression tests."""
from __future__ import annotations

import copy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import alcg
import model_selection as m
import workload_estimator as w

ROOT = Path(__file__).resolve().parents[1]


class ModelSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = m.report()
        cls.records = {(r['scenario'],r['at_tick']): r for r in cls.report['issuances']}

    def test_01_config_pins_prior_sources(self):
        cfg=m.config()
        self.assertEqual(cfg['source_v030_events_sha256'],sha256(w.FIXTURE_PATH.read_bytes()).hexdigest())
        self.assertEqual(cfg['cuts'],[32,64,96,128,160])
        self.assertEqual(cfg['history_lookback'],2)

    def test_02_synthetic_extended_streams(self):
        for label in m.SCENARIOS:
            full=m.stream(label)
            self.assertEqual(len(full['events']),192)
            w.validate_document(full)

    def test_03_other_labels_rejected(self):
        with self.assertRaises(m.SelectionError):m.stream('production')
        with self.assertRaises(m.SelectionError):m.stream('stable',96)

    def test_04_issue_counts(self):
        self.assertEqual(self.report['summary']['issued_windows'],20)
        self.assertEqual(self.report['summary']['supported_windows'],15)
        self.assertEqual(self.report['summary']['unsupported_windows'],5)

    def test_05_model_inventory(self):
        self.assertEqual(self.report['summary']['selected_inventory'],
                         {'RAW':5,'LAGGED':7,'HEDGE':3,'DEFER':5})

    def test_06_switch_inventory(self):
        self.assertEqual(self.report['summary']['switches'],5)
        self.assertEqual([(r['scenario'],r['at_tick']) for r in self.report['issuances']
                          if r['reason']=='switch_after_closed_window_scoring'],
                         [('stable',96),('churn',64),('churn',96),('drift',96),('drift',160)])

    def test_07_no_future_access_in_issuance(self):
        full=m.stream('drift')
        first=m.issue_at(m.prefix(full,96),96)
        new_events=copy.deepcopy(full['events'])
        new_events[120]={'tick':120,'kind':'idle'}
        altered=w.document('drift','synthetic-fixture',new_events)
        self.assertEqual(m.issue_at(m.prefix(altered,96),96),first)

    def test_08_already_visible_data_changes_forecast(self):
        full=m.stream('stable')
        row=m.issue_at(m.prefix(full,64),64)
        events=copy.deepcopy(full['events'])
        events[40]={'tick':40,'kind':'idle'}
        mutated=w.document('stable','synthetic-fixture',events)
        self.assertNotEqual(m.issue_at(m.prefix(mutated,64),64),row)

    def test_09_refuses_future_holdout_before_closed(self):
        past=m.prefix(m.stream('churn'),128)
        with self.assertRaises(m.SelectionError):m.closed_outcome(past['events'],128)

    def test_10_allow_already_closed_holdout(self):
        past=m.prefix(m.stream('churn'),128)
        obs=m.closed_outcome(past['events'],96)
        self.assertEqual((obs['start_tick'],obs['end_tick']),(96,128))

    def test_11_no_wrong_cut(self):
        with self.assertRaises(m.SelectionError):m.issue_at(m.prefix(m.stream('stable'),64),65)
        with self.assertRaises(m.SelectionError):m.prefix(m.stream('stable'),True)
        with self.assertRaises(m.SelectionError):m.issue_at(m.prefix(m.stream('stable'),64),32)

    def test_12_only_exact_prefix(self):
        with self.assertRaises(m.SelectionError):m.issue_at(m.stream('stable'),64)

    def test_13_unknown_origin_rejected(self):
        events=m.stream('stable')['events'][:64]
        fake=w.document('stable','instrumented-process',events)
        with self.assertRaises(m.SelectionError):m.issue_at(fake,64)

    def test_14_sparse_is_deferred(self):
        self.assertTrue(all(r['selected']=='DEFER' and r['policy_route']=='direct'
                            and r['candidates'] is None for r in self.report['issuances']
                            if r['scenario']=='sparse'))

    def test_15_all_probabilities_exact(self):
        for row in self.report['issuances']:
            if row['candidates']:
                for model in m.EXPERTS:
                    for field in ('read_probability','reset_probability'):
                        self.assertTrue(0<=m.frac(row['candidates'][model][field])<=1)

    def test_16_rational_validation(self):
        with self.assertRaises(m.SelectionError):m.frac({'num':1,'den':0})
        with self.assertRaises(m.SelectionError):m.frac({'num':True,'den':2})
        with self.assertRaises(m.SelectionError):m.frac({'num':1,'den':2,'extra':3})

    def test_17_hedge_respects_fixed_floor(self):
        row=self.records[('stable',64)]
        self.assertEqual(m.frac(row['candidates']['HEDGE']['reset_probability']),Fraction(1,3))

    def test_18_lagged_is_initially_identical(self):
        row=self.records[('stable',32)]['candidates']
        self.assertEqual(row['RAW'],row['LAGGED'])

    def test_19_lagged_differs_after_closed_evidence(self):
        row=self.records[('stable',64)]['candidates']
        self.assertNotEqual(row['RAW'],row['LAGGED'])

    def test_20_history_only_closed_windows(self):
        for r in self.report['issuances']:
            for evidence in r['scored_prior_evidence']:
                self.assertLessEqual(evidence['prior_cut']+32,r['at_tick'])
                self.assertEqual(evidence['outcome']['end_tick'],evidence['prior_cut']+32)

    def test_21_history_bounded(self):
        self.assertTrue(all(len(r['scored_prior_evidence'])<=2 for r in self.report['issuances']))

    def test_22_switch_has_actual_scored_evidence(self):
        self.assertTrue(all(r['scored_prior_evidence'] for r in self.report['issuances']
                            if r['reason']=='switch_after_closed_window_scoring'))

    def test_23_fingerprint_verify(self):
        issued=self.records[('churn',96)]
        self.assertTrue(m.verify_issuance(issued,m.prefix(m.stream('churn'),96)))

    def test_24_fingerprint_tamper_rejected(self):
        issued=copy.deepcopy(self.records[('churn',96)])
        issued['selected']='RAW'
        with self.assertRaises(m.SelectionError):m.verify_issuance(issued,m.prefix(m.stream('churn'),96))

    def test_25_self_rehashed_forgery_rejected(self):
        issued=copy.deepcopy(self.records[('churn',96)])
        issued['selected']='RAW'
        issued['issue_sha256']=m.digest({k:v for k,v in issued.items() if k!='issue_sha256'})
        with self.assertRaises(m.SelectionError):m.verify_issuance(issued,m.prefix(m.stream('churn'),96))

    def test_26_settlement_only_after_future(self):
        issue=self.records[('stable',160)]
        with self.assertRaises(m.SelectionError):m.settle(issue,m.prefix(m.stream('stable'),160))
        self.assertEqual(m.settle(issue,m.stream('stable'))['status'],'scored')

    def test_27_report_counts(self):
        self.assertEqual(self.report['summary']['scored_windows'],15)
        self.assertEqual(len(self.report['settlements']),20)

    def test_28_selected_better_than_raw_on_this_fixture(self):
        s=self.report['summary']
        self.assertLess(m.frac(s['selected_macro_combined_brier']),
                        m.frac(s['always_raw_macro_combined_brier']))

    def test_29_selection_not_globally_best(self):
        s=self.report['summary']
        self.assertGreater(m.frac(s['selected_macro_combined_brier']),
                           m.frac(s['always_lagged_macro_combined_brier']))
        self.assertGreater(m.frac(s['selected_minus_hindsight_oracle_total_loss']),0)

    def test_30_alcg_projection_roundtrip(self):
        for r in self.report['issuances']:
            value=m.expression(r)
            self.assertEqual(alcg.render(alcg.parse(value)),value)
            self.assertTrue(m.verify_expression(value,r))

    def test_31_alcg_tamper_rejected(self):
        issued=self.records[('drift',96)]
        value=m.expression(issued).replace('selected=HEDGE','selected=RAW')
        with self.assertRaises(m.SelectionError):m.verify_expression(value,issued)

    def test_32_validate_frozen_report_and_samples(self):
        self.assertEqual(m.check()['status'],'PASS')
        self.assertEqual(len([l for l in m.SAMPLE_PATH.read_text(encoding='utf-8').splitlines()
                             if l and not l.startswith('#')]),20)

    def test_33_tampered_report_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.json';bad=copy.deepcopy(self.report)
            bad['summary']['switches']=99
            p.write_text(json.dumps(bad),encoding='utf-8')
            with patch.object(m,'REPORT_PATH',p),self.assertRaises(m.SelectionError):
                m.check()

    def test_34_config_version_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.json';bad=m.config()
            bad['history_lookback']=999
            p.write_text(json.dumps(bad),encoding='utf-8')
            with patch.object(m,'CONFIG_PATH',p),self.assertRaises(m.SelectionError):
                m.config()

    def test_35_alcg_frozen_samples_syntax(self):
        self.assertEqual(len(alcg.read_expressions(m.SAMPLE_PATH)),20)

    def test_36_issuance_hash_matches_payload(self):
        for r in self.report['issuances']:
            self.assertEqual(r['issue_sha256'],m.digest({k:v for k,v in r.items() if k!='issue_sha256'}))

    def test_37_report_hash_matches_payload(self):
        self.assertEqual(self.report['report_sha256'],m.digest(
            {k:v for k,v in self.report.items() if k!='report_sha256'}))

    def test_38_cli_report(self):
        p=subprocess.run([sys.executable,'model_selection.py','report'],cwd=ROOT,
                         capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['summary']['switches'],5)

    def test_39_cli_issue(self):
        p=subprocess.run([sys.executable,'model_selection.py','issue','--case','drift','--at','128'],
                         cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('SELECT_V032(',p.stdout)

    def test_40_cli_replay(self):
        p=subprocess.run([sys.executable,'model_selection.py','replay','--case','drift','--at','128'],
                         cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['settled']['status'],'scored')

    def test_41_sparse_not_scored(self):
        for issued,settled in zip(self.report['issuances'],self.report['settlements']):
            if issued['scenario']=='sparse':
                self.assertEqual(settled['status'],'not_scored')

    def test_42_only_synthetic_claims(self):
        lim=' '.join(self.report['limitations']).lower()
        self.assertIn('synthetic',lim)
        self.assertIn('not measured production traffic',lim)
        self.assertIn('not a universal optimum',lim)


if __name__=='__main__':
    unittest.main()
