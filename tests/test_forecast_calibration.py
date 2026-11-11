"""ALCG v0.31: strict temporal scoring, synthetic calibration and cost audits."""
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

import forecast_calibration as c
import workload_estimator as w

ROOT=Path(__file__).resolve().parents[1]


class ForecastCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, streams, cls.rows = c.inputs()
        cls.streams={x['label']:x for x in streams}
        cls.report=c.report()

    def issued(self,label='stable',tick=64,mode='selective'):
        return c.issue(self.streams[label],tick,mode=mode,row=self.rows[mode])

    def training(self,label='stable',mode='selective'):
        s=self.streams[label];row=self.rows[mode];old=self.issued(label,32,mode)
        return {'scenario':label,'at_tick':32,'end_tick':64,
                'issue_sha256':old['issue_sha256'],'realization':c.truth(s,32)}

    def test_01_config_fingerprints(self):
        self.assertEqual(self.cfg['source_events_sha256'],sha256(w.FIXTURE_PATH.read_bytes()).hexdigest())
        self.assertEqual(self.cfg['horizon_opportunities'],32)

    def test_02_read_fixture_unchanged(self):
        self.assertTrue(w.read_fixture()['scenarios'])

    def test_03_horizon_exact(self):
        self.assertEqual(c.truth(self.streams['stable'],32)['end_tick'],64)

    def test_04_time_cut_exact(self):
        for i in (0,31,33,65,96,True,'64'):
            with self.subTest(i=i),self.assertRaises(c.CalibrationError):
                c.issue(self.streams['stable'],i,row=self.rows['selective'])

    def test_05_mode_known(self):
        with self.assertRaises(c.CalibrationError): c.issue(self.streams['stable'],64,mode='nonexistent')

    def test_06_prefix_fingerprint_matches(self):
        doc=self.issued();self.assertEqual(doc['forecast']['prefix_sha256'],c.digest(self.streams['stable']['events'][:64]))

    def test_07_no_future_leakage_at_cut_64(self):
        original=self.streams['drift'];changed=copy.deepcopy(original)
        for event in changed['events'][64:]:
            if event['kind']=='read':event['revision_changed']=not event['revision_changed']
        modified=w.document(changed['label'],changed['origin'],changed['events'])
        self.assertEqual(self.issued('drift',64),c.issue(modified,64,row=self.rows['selective']))
        self.assertNotEqual(c.truth(original,64),c.truth(modified,64))

    def test_08_no_future_leakage_at_cut_32(self):
        original=self.streams['stable'];changed=copy.deepcopy(original)
        for event in changed['events'][32:]:
            if event['kind']=='read':event['revision_changed']=not event['revision_changed']
        modified=w.document(changed['label'],changed['origin'],changed['events'])
        self.assertEqual(self.issued('stable',32),c.issue(modified,32,row=self.rows['selective']))

    def test_08b_issuance_from_prefix_only_is_identical(self):
        stream=self.streams['stable']
        prefix=w.document(stream['label'],stream['origin'],stream['events'][:64])
        self.assertEqual(self.issued('stable',64),c.issue(prefix,64,row=self.rows['selective']))

    def test_09_issue_receipt_validation(self):
        rec=self.issued();c.ensure_issue(rec,self.streams['stable'],self.rows['selective'])

    def test_10_tampered_receipt_rejected(self):
        rec=self.issued();rec['issue_sha256']='0'*64
        with self.assertRaises(c.CalibrationError):c.ensure_issue(rec,self.streams['stable'],self.rows['selective'])

    def test_11_forged_issue_rejected(self):
        rec=self.issued();rec['forecast']['observed_reads']+=1
        rec['issue_sha256']=c.digest({k:v for k,v in rec.items() if k!='issue_sha256'})
        with self.assertRaises(c.CalibrationError):c.ensure_issue(rec,self.streams['stable'],self.rows['selective'])

    def test_12_future_receipt_is_separate(self):
        self.assertNotIn('future_receipt_sha256',json.dumps(self.issued('drift',64)))
        self.assertIn('future_receipt_sha256',c.truth(self.streams['drift'],64))

    def test_13_scored_window_count(self):
        self.assertEqual(self.report['summary']['scored_windows'],6)

    def test_14_sparse_not_force_scored(self):
        a=[x for x in self.report['records'] if x['issue']['scenario']=='sparse']
        self.assertEqual(len(a),2)
        self.assertTrue(all(x['status']=='insufficient_prefix' and x['raw_scores'] is None for x in a))

    def test_15_stable_read_count(self):
        self.assertEqual(c.truth(self.streams['stable'],64)['reads'],32)

    def test_16_internal_gaps_are_n_minus_1(self):
        for name in self.streams:
            for t in c.CUTS:
                a=c.truth(self.streams[name],t)
                self.assertEqual(a['read_gaps'],max(0,a['reads']-1))

    def test_17_brier_extremes(self):
        self.assertEqual(c.brier(Fraction(1),1,1),Fraction(0))
        self.assertEqual(c.brier(Fraction(0),1,1),Fraction(1))

    def test_18_brier_zero_denominator(self):
        self.assertIsNone(c.brier(Fraction(1,3),0,0))

    def test_19_brier_invalid_raises(self):
        for p,k,n in ((Fraction(2),1,1),(Fraction(-1,2),0,1),(Fraction(1,2),2,1)):
            with self.assertRaises(c.CalibrationError):c.brier(p,k,n)

    def test_20_raw_stable_32_brier_exact(self):
        rec=next(x for x in self.report['records'] if x['issue']['scenario']=='stable' and x['issue']['at_tick']==32)
        self.assertEqual(c.frac(rec['raw_scores']['read_brier']),Fraction(625,1156))

    def test_21_calibration_only_after_completed_prior(self):
        rec=c.settle(self.issued(),self.streams['stable'],self.rows['selective'],training=self.training())
        self.assertIsNotNone(rec['calibrated_scores'])

    def test_22_future_training_disallowed(self):
        bad=self.training();bad['end_tick']=96
        with self.assertRaises(c.CalibrationError):c.settle(self.issued(),self.streams['stable'],self.rows['selective'],training=bad)

    def test_23_false_prior_outcome_rejected(self):
        bad=self.training();bad['realization']['reads']-=1
        with self.assertRaises(c.CalibrationError):c.settle(self.issued(),self.streams['stable'],self.rows['selective'],training=bad)

    def test_24_other_scenario_prior_rejected(self):
        with self.assertRaises(c.CalibrationError):c.settle(self.issued(),self.streams['stable'],self.rows['selective'],training=self.training('churn'))

    def test_25_issue_32_no_training_allowed(self):
        with self.assertRaises(c.CalibrationError):c.settle(self.issued('stable',32),self.streams['stable'],self.rows['selective'],training=self.training())

    def test_26_exact_fraction_roundtrip(self):
        for p in (Fraction(0),Fraction(1,37),Fraction(100,37)):
            self.assertEqual(c.frac(c.exact(p)),p)

    def test_27_fraction_schema_strict(self):
        for bad in ({'num':1,'den':0},{'num':True,'den':1},{'num':1,'den':1,'extra':5}):
            with self.assertRaises(c.CalibrationError):c.frac(bad)

    def test_28_round_half_up(self):
        self.assertEqual(c.round_half_up(Fraction(1,2)),1)
        self.assertEqual(c.round_half_up(Fraction(3,2)),2)

    def test_29_calibration_drift_harm_visible(self):
        r=next(x for x in self.report['records'] if x['issue']['scenario']=='drift' and x['issue']['at_tick']==64)
        self.assertGreater(c.frac(r['calibrated_scores']['reset_brier']),c.frac(r['raw_scores']['reset_brier']))

    def test_30_calibration_stable_improvement_visible(self):
        r=next(x for x in self.report['records'] if x['issue']['scenario']=='stable' and x['issue']['at_tick']==64)
        self.assertLess(c.frac(r['calibrated_scores']['read_brier']),c.frac(r['raw_scores']['read_brier']))

    def test_31_mode_decisions_3_times_8(self):
        self.assertEqual(len(self.report['mode_decisions']),24)

    def test_32_hindsight_regret_nonnegative(self):
        for d in self.report['mode_decisions']:
            if d['decision']:
                self.assertGreaterEqual(d['decision']['raw_regret_ns'],0)
                if d['decision']['calibrated_regret_ns'] is not None:
                    self.assertGreaterEqual(d['decision']['calibrated_regret_ns'],0)

    def test_33_drift_cache_admission_worsens_regret(self):
        x=next(x for x in self.report['mode_decisions'] if x['scenario']=='drift' and x['cut']==64 and x['mode']=='selective')
        self.assertEqual(x['decision']['forecast_route'],'direct')
        self.assertEqual(x['decision']['calibrated_route'],'cache')
        self.assertGreater(x['decision']['calibrated_regret_ns'],x['decision']['raw_regret_ns'])

    def test_34_stable_cache_admission_improves_regret(self):
        x=next(x for x in self.report['mode_decisions'] if x['scenario']=='stable' and x['cut']==64 and x['mode']=='selective')
        self.assertEqual(x['decision']['calibrated_route'],'cache')
        self.assertLess(x['decision']['calibrated_regret_ns'],x['decision']['raw_regret_ns'])

    def test_35_full_cost_independent_computation(self):
        r=c.realized_costs(self.rows['selective'],c.truth(self.streams['stable'],64))
        self.assertEqual(r['direct_cost_ns'],32*self.rows['selective']['uncached_median_ns'])
        self.assertEqual(r['cache_cost_ns'],self.rows['selective']['cold_admission_ns']+31*self.rows['selective']['cached_median_ns'])

    def test_36_report_deterministic(self):
        self.assertEqual(self.report,c.report())

    def test_37_report_integrity_check(self):
        self.assertEqual(c.check()['status'],'PASS')

    def test_38_report_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'tamper.json'
            f=copy.deepcopy(self.report)
            f['summary']['scored_windows']=0
            p.write_text(json.dumps(f),encoding='utf-8')
            with patch.object(c,'REPORT_PATH',p),self.assertRaises(c.CalibrationError): c.check()

    def test_39_config_changed_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'config.json';row=copy.deepcopy(self.cfg)
            row['calibration_strength']=0;p.write_text(json.dumps(row),encoding='utf-8')
            with patch.object(c,'CONFIG_PATH',p),self.assertRaises(c.CalibrationError):c.inputs()

    def test_40_cli_check(self):
        proc=subprocess.run([sys.executable,'forecast_calibration.py','check'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['status'],'PASS')

    def test_41_cli_score(self):
        proc=subprocess.run([sys.executable,'forecast_calibration.py','score','--case','drift','--at','64'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['issue']['scenario'],'drift')

    def test_42_no_ai_or_production_claim_in_report(self):
        lim=' '.join(self.report['limitations']).lower()
        self.assertIn('synthetic',lim)
        self.assertIn('counterfactual',lim)
        self.assertIn('calibration may worsen',lim)


    def test_43_audit_sample_roundtrip(self):
        rows=c.report()['records']
        sample=[x for x in c.SAMPLE_PATH.read_text(encoding='utf-8').splitlines() if x and not x.startswith('#')]
        self.assertEqual(len(sample),8)
        self.assertTrue(all(c.verify_audit_expression(line,r) for line,r in zip(sample,rows)))

    def test_44_expression_valid_alcg_syntax(self):
        from alcg import parse, render
        for rec in self.report['records']:
            x=c.audit_expression(rec)
            self.assertEqual(render(parse(x)),x)

    def test_45_expression_tampering_fails(self):
        row=self.report['records'][0]
        expr=c.audit_expression(row)
        with self.assertRaises(c.CalibrationError):c.verify_audit_expression(expr.replace('reads=\"32\"','reads=\"1\"'),row)

    def test_46_expression_has_explicit_posthoc_roles(self):
        expr=c.audit_expression(self.report['records'][0])
        for label in ('AUDIT_V031(','ISSUE_V031(','OBSERVED_V031(','FEEDBACK_V031('):
            self.assertIn(label,expr)

    def test_47_expression_emission_cli(self):
        proc=subprocess.run([sys.executable,'forecast_calibration.py','emit','--case','stable','--at','64'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,0,proc.stderr)
        c.verify_audit_expression(proc.stdout.strip(),next(x for x in self.report['records'] if x['issue']['scenario']=='stable' and x['issue']['at_tick']==64))

    def test_48_expression_no_full_source_material(self):
        expr=c.audit_expression(self.report['records'][0])
        self.assertNotIn('SOURCE_BYTES',expr)
        self.assertNotIn('RAW(',expr)


if __name__=='__main__':unittest.main()
