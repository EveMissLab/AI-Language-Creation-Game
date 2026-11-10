"""ALCG v0.21: tests of exact synthetic correlated/noisy Bayes and stopping decisions."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from fractions import Fraction
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import active_design as old
import correlated_design as lab
import noisy_design as v20


class CorrelatedDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = lab.pinned_rows()
        cls.row = cls.rows['F17_DIRECT']
        cls.prior = lab.initial_joint()

    def test_pinned_baseline_unchanged(self):
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(lab.sha256(v20.SPEC_PATH.read_bytes()).hexdigest(),
                         lab.PINNED_V020_SPEC_SHA256)
        self.assertEqual(lab.sha256(v20.REPORT_PATH.read_bytes()).hexdigest(),
                         lab.PINNED_V020_REPORT_SHA256)

    def test_canonical_spec_bytes_and_scope(self):
        self.assertEqual(lab.SPEC_PATH.read_bytes(), lab.serialized_spec().encode('utf-8'))
        self.assertTrue(lab.experiment_spec()['published_language_dictionary_unmodified'])
        self.assertEqual(lab.experiment_spec()['planning_budget_max'], 4)

    def test_asymmetric_false_positive_false_negative(self):
        self.assertNotEqual(lab.FALSE_POSITIVE[1], lab.FALSE_NEGATIVE[1])
        self.assertEqual(lab.FALSE_POSITIVE[1], Fraction(1, 16))
        self.assertEqual(lab.FALSE_NEGATIVE[1], Fraction(3, 16))
        self.assertTrue(all(Fraction(0) < x < Fraction(1, 2)
                            for x in lab.FALSE_POSITIVE + lab.FALSE_NEGATIVE))

    def test_prior_is_joint_over_sixteen_masks_and_persistent_fault(self):
        self.assertEqual(len(self.prior), 32)
        self.assertEqual(sum(self.prior), Fraction(1))
        self.assertEqual(lab.mask_posterior(self.prior), (Fraction(1,16),)*16)
        self.assertEqual(lab.fault_posterior(self.prior), Fraction(1, 8))

    def test_every_channel_probability_sums_to_one(self):
        for mask in range(16):
            for fault in (False, True):
                for action in range(8):
                    with self.subTest(mask=mask, fault=fault, action=action):
                        p0 = lab.likelihood(self.row, mask, fault, action, False)
                        p1 = lab.likelihood(self.row, mask, fault, action, True)
                        self.assertEqual(p0+p1, Fraction(1))
                        self.assertTrue(0 < p0 < 1)
                        self.assertTrue(0 < p1 < 1)

    def test_fault_flips_observation_distribution_not_true_model(self):
        for action in (0, 3, 4, 7):
            p = lab.likelihood(self.row, 5, False, action, True)
            q = lab.likelihood(self.row, 5, True, action, True)
            self.assertEqual(q, 1-p)

    def test_predictive_distribution_is_normalized_after_evidence(self):
        posterior = lab.posterior(self.row, [{'action_id':3,'observed_Y':True}])
        for action in range(8):
            self.assertEqual(lab.predictive(self.row, posterior, action, False)
                             + lab.predictive(self.row, posterior, action, True), 1)

    def test_one_observation_marginal_matches_redrawn_fault_control(self):
        obs = [{'action_id':3,'observed_Y':True}]
        self.assertEqual(lab.mask_posterior(lab.posterior(self.row, obs)),
                         lab.redraw_fault_posterior(self.row, obs))

    def test_repeated_observations_are_not_conditionally_independent_after_marginalizing_fault(self):
        obs = [{'action_id':3,'observed_Y':True}] * 3
        a = lab.mask_posterior(lab.posterior(self.row, obs))
        b = lab.redraw_fault_posterior(self.row, obs)
        self.assertNotEqual(a, b)
        self.assertLess(max(a), max(b))

    def test_fixed_latent_causes_positive_within_session_correlation(self):
        mask, action = 2, 3
        p = lab.SESSION_FAULT_PRIOR
        base = lab.likelihood(self.row, mask, False, action, True)
        flipped = lab.likelihood(self.row, mask, True, action, True)
        p_two_ones = (1-p)*base*base + p*flipped*flipped
        independent = ((1-p)*base + p*flipped)**2
        self.assertGreater(p_two_ones, independent)

    def test_natural_probe_calibrates_fault_without_direct_mask_information(self):
        natural = 2
        self.assertTrue(old.action_data(natural)['same_as_natural_SIGNAL'])
        y = old._response(self.row, 0, natural)
        after = lab.posterior(self.row,[{'action_id':natural,'observed_Y':y}])
        self.assertEqual(lab.mask_posterior(after), lab.mask_posterior(self.prior))
        self.assertNotEqual(lab.fault_posterior(after), lab.SESSION_FAULT_PRIOR)

    def test_calibration_indirectly_changes_mask_posterior_after_informative_reading(self):
        first = [{'action_id':3,'observed_Y':True}]
        y = old._response(self.row, 0, 2)
        before = lab.posterior(self.row, first)
        after = lab.posterior(self.row, first + [{'action_id':2,'observed_Y':y}])
        self.assertNotEqual(lab.mask_posterior(before),lab.mask_posterior(after))

    def test_evidence_reordering_preserves_joint_posterior(self):
        events = [{'action_id':3,'observed_Y':True},{'action_id':2,'observed_Y':False},
                  {'action_id':5,'observed_Y':True}]
        self.assertEqual(lab.posterior(self.row, events), lab.posterior(self.row, events[::-1]))

    def test_zero_fault_limit_agrees_with_independent_sensor_control(self):
        obs = [{'action_id':3,'observed_Y':True},{'action_id':3,'observed_Y':False},
               {'action_id':4,'observed_Y':True}]
        joint = lab.posterior(self.row,obs,Fraction(0))
        redraw = lab.redraw_fault_posterior(self.row,obs,Fraction(0))
        self.assertEqual(lab.mask_posterior(joint),redraw)
        self.assertEqual(lab.fault_posterior(joint),0)

    def test_positive_rates_prevent_exact_finite_elimination(self):
        events = [{'action_id':3,'observed_Y':True}]*5
        masks = lab.mask_posterior(lab.posterior(self.row,events))
        self.assertTrue(all(m > 0 for m in masks))
        self.assertLess(max(masks),1)

    def test_stop_loss_matches_map_error(self):
        self.assertEqual(lab.stop_loss(self.prior,64),60)
        self.assertEqual(lab.stop_loss(self.prior,0),0)

    def test_optimal_stop_when_misclassification_cost_is_small(self):
        plan = lab.plan(self.row,self.prior,2,8)
        self.assertEqual(plan['decision'],'STOP')
        self.assertIsNone(plan['optimal_first_action'])
        self.assertEqual(plan['optimal_expected_future_total_loss']['numerator'],Fraction(15,2).numerator)

    def test_optimal_continue_when_misclassification_cost_is_large(self):
        plan = lab.plan(self.row,self.prior,1,64)
        self.assertEqual(plan['decision'],'CONTINUE')
        self.assertEqual(plan['optimal_first_action'],3)
        self.assertEqual((plan['optimal_expected_future_total_loss']['numerator'],
                          plan['optimal_expected_future_total_loss']['denominator']), (235,4))

    def test_larger_budget_never_worsens_exact_optimal_risk(self):
        p=[lab.plan(self.row,self.prior,b,64)['optimal_expected_future_total_loss']['decimal']
           for b in range(5)]
        self.assertEqual(p,sorted(p,reverse=True))

    def test_exact_policy_matches_independent_naive_two_stage_enumeration(self):
        """Cross-check DP without calling itself, using explicit one/two trial enumeration."""
        state=self.prior
        loss=64
        actions=[a for a in range(8) if lab.action_cost(a)==1]
        def terminal(s):
            return loss*(1-max(lab.mask_posterior(s)))
        best=terminal(state)
        for a in actions:
            after_one=Fraction(0)
            for y in (False,True):
                py=lab.predictive(self.row,state,a,y)
                child=lab.update(self.row,state,a,y)
                best_next=terminal(child)
                for b in actions:
                    outcome=Fraction(1)
                    for next_y in (False,True):
                        p2=lab.predictive(self.row,child,b,next_y)
                        final=lab.update(self.row,child,b,next_y)
                        outcome += p2*terminal(final)
                    best_next=min(best_next,outcome)
                after_one+=py*best_next
            best=min(best,Fraction(1)+after_one)
        got=lab.plan(self.row,state,2,loss)['optimal_expected_future_total_loss']
        self.assertEqual(Fraction(got['numerator'],got['denominator']),best)

    def test_plan_zero_budget_stops_even_when_penalty_positive(self):
        self.assertEqual(lab.plan(self.row,self.prior,0,64)['decision'],'STOP')

    def test_plan_will_stop_with_certain_mask_even_if_fault_unknown(self):
        state=tuple([Fraction(0)]*5 + [Fraction(1,2)] + [Fraction(0)]*15
                    +[Fraction(1,2)] + [Fraction(0)]*10)
        # Sparse state: only mask 5, in both Z states.
        self.assertEqual(len(state),32)
        self.assertEqual(lab.stop_loss(state,100),0)
        self.assertEqual(lab.plan(self.row,state,3,100)['decision'],'STOP')

    def test_invalid_observation_and_prior_inputs_are_rejected(self):
        for bad in ([],[{}],[{'action_id':3,'observed_Y':1}],
                    [{'action_id':3,'observed_Y':True,'mask':5}],
                    [{}]*33, '3=1'):
            if bad==[]:
                continue
            with self.subTest(bad=str(bad)[:30]),self.assertRaises(lab.ChannelError):
                lab.posterior(self.row,bad)
        for bad in ((Fraction(0),)*32,(Fraction(1),)*16,(1,)*32):
            with self.assertRaises(lab.ChannelError):
                lab.normalized_joint(bad)
        for q in (True, Fraction(-1,8), Fraction(3,4), 0.125):
            with self.assertRaises(lab.ChannelError):
                lab.initial_joint(q)

    def test_invalid_actions_and_budget_rejected(self):
        for act in (True,8,-1,1.5,'3'):
            with self.subTest(action=act),self.assertRaises((lab.ChannelError,old.DesignError)):
                lab.action_cost(act)
        for budget in (True,5,-1,'2'):
            with self.assertRaises(lab.ChannelError):
                lab.plan(self.row,self.prior,budget,64)
        for penalty in (True,-1,10001):
            with self.assertRaises(lab.ChannelError):
                lab.plan(self.row,self.prior,1,penalty)

    def test_pinned_report_guard_rejects_drift(self):
        with TemporaryDirectory() as td:
            target = Path(td)/'v020-report.json'
            target.write_text('{}',encoding='utf-8')
            with patch.object(v20,'REPORT_PATH',target):
                with self.assertRaisesRegex(lab.ChannelError,'modified'):
                    lab.pinned_rows()

    def test_canonical_spec_guard_rejects_drift(self):
        with TemporaryDirectory() as td:
            target = Path(td)/'spec.json'
            target.write_text('{}',encoding='utf-8')
            with patch.object(lab,'SPEC_PATH',target):
                with self.assertRaisesRegex(lab.ChannelError,'not canonical'):
                    lab.pinned_rows()

    def test_saved_report_matches_recomputation(self):
        self.assertEqual(lab.REPORT_PATH.read_bytes(), lab.serialized_report().encode('utf-8'))
        report=lab.make_report()
        self.assertEqual(report['counts']['families_frozen'],7)
        self.assertEqual(report['counts']['joint_fault_mask_states'],32)
        self.assertTrue(report['preview']['persistent_and_redrawn_mask_posteriors_differ'])

    def test_cli_check_summary_plan_replay_and_invalid_input(self):
        sink=StringIO()
        with redirect_stdout(sink),redirect_stderr(sink):
            self.assertEqual(lab.main(['check']),0)
            self.assertEqual(lab.main(['summary']),0)
            self.assertEqual(lab.main(['plan','--budget','2','--loss','64','--observe','3=1']),0)
            self.assertEqual(lab.main(['replay','--mask','5','--fault','1','--action','3']),0)
            self.assertEqual(lab.main(['plan','--budget','5']),1)
            self.assertEqual(lab.main(['plan','--observe','3=wrong']),1)
            self.assertEqual(lab.main(['replay','--mask','17','--fault','0','--action','3']),1)


if __name__ == '__main__':
    unittest.main()
