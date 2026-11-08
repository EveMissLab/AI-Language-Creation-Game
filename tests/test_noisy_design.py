"""v0.20 exact finite Bayes/noise/cost diagnostics; not real causal inference."""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import active_design as old
import noisy_design as lab

ROOT = Path(__file__).resolve().parents[1]


class NoisyDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = lab._frozen_rows()
        cls.row = cls.rows['F17_DIRECT']
        cls.prior = lab.initial_prior()
        cls.action = 3
        cls.observed = old._response(cls.row, 0, cls.action)

    def test_original_v019_frozen_files_untouched(self):
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(lab.V019_REPORT_SHA256, lab.sha256(old.REPORT_PATH.read_bytes()).hexdigest())
        self.assertEqual(lab.V019_SPEC_SHA256, lab.sha256(old.SPEC_PATH.read_bytes()).hexdigest())

    def test_generated_spec_is_exact_canonical_utf8(self):
        self.assertEqual(lab.SPEC_PATH.read_bytes(), lab.serialized_spec().encode('utf-8'))
        self.assertTrue(lab.experiment_spec()['published_registry_unmodified'])

    def test_chosen_error_rates_are_strictly_between_zero_and_half(self):
        self.assertTrue(all(Fraction(0) < x < Fraction(1, 2) for x in lab.CONTEXT_RATES))
        self.assertEqual(lab.CONTEXT_RATES, (Fraction(1,16), Fraction(1,8), Fraction(1,4), Fraction(1,8)))

    def test_action_costs_and_informativeness(self):
        self.assertEqual(old.informative_actions(), (1, 3, 4, 6))
        self.assertEqual([lab.action_cost(x) for x in (1, 3, 4, 6)], [4,1,1,3])
        self.assertEqual(lab.action_profile(3)['flip_probability']['numerator'],1)

    def test_uniform_prior_has_sixteen_rational_weights(self):
        self.assertEqual(len(self.prior), 16)
        self.assertEqual(sum(self.prior), Fraction(1))
        self.assertEqual(lab.entropy(self.prior), 4.0)
        self.assertEqual(lab.map_accuracy(self.prior), Fraction(1,16))

    def test_posterior_matches_exact_bayes_likelihood(self):
        weights = lab.posterior(self.row, [{'action_id':3,'observed_Y':self.observed}])
        self.assertEqual(sum(weights), Fraction(1))
        self.assertEqual({weights[i] for i in range(16) if old._response(self.row,i,3)==self.observed}, {Fraction(7,64)})
        self.assertEqual({weights[i] for i in range(16) if old._response(self.row,i,3)!=self.observed}, {Fraction(1,64)})
        self.assertTrue(all(weight > 0 for weight in weights))
        self.assertEqual(lab.map_accuracy(weights), Fraction(7,64))

    def test_two_opposite_readings_cancel_for_symmetric_sensor(self):
        events = [{'action_id':3,'observed_Y':True},{'action_id':3,'observed_Y':False}]
        self.assertEqual(lab.posterior(self.row, events), self.prior)

    def test_repeated_agreeing_readings_increase_confidence_without_elimination(self):
        events = [{'action_id':3,'observed_Y':self.observed}] * 2
        updated = lab.posterior(self.row, events)
        self.assertEqual(lab.map_accuracy(updated), Fraction(49,400))
        self.assertTrue(all(w > 0 for w in updated))
        self.assertLess(lab.entropy(updated), 4.0)

    def test_natural_action_with_sensor_error_never_informs_mask(self):
        natural_action = 0
        self.assertTrue(old.action_data(natural_action)['same_as_natural_SIGNAL'])
        self.assertEqual(lab.posterior(self.row,[{'action_id':natural_action,'observed_Y':False}]), self.prior)
        self.assertEqual(lab.posterior(self.row,[{'action_id':natural_action,'observed_Y':True}]), self.prior)
        self.assertAlmostEqual(lab.information_gain(self.row,self.prior,natural_action),0,places=12)

    def test_all_actions_prediction_probabilities_sum_one(self):
        after = lab.posterior(self.row,[{'action_id':3,'observed_Y':True}])
        for a in range(8):
            self.assertEqual(lab.predictive(self.row,after,a,False) + lab.predictive(self.row,after,a,True),Fraction(1))

    def test_information_gain_matches_binary_symmetric_channel(self):
        for a in old.informative_actions():
            expected = 1-lab.binary_entropy(lab.action_rate(a))
            self.assertAlmostEqual(lab.information_gain(self.row,self.prior,a),expected)

    def test_information_gain_does_not_increase_entropy_in_expectation(self):
        for a in range(8):
            self.assertGreaterEqual(lab.information_gain(self.row,self.prior,a),0)
            self.assertLessEqual(lab.information_gain(self.row,self.prior,a),1)

    def test_cost_adjusted_greedy_selects_cheap_fairly_reliable_action(self):
        result = lab.greedy_choice(self.row,self.prior,4)
        self.assertEqual(result['action_id'],3)
        self.assertEqual(result['cost_units'],1)

    def test_greedy_with_no_budget_returns_no_choice(self):
        self.assertIsNone(lab.greedy_choice(self.row,self.prior,0))

    def test_greedy_max_information_ignoring_cost_differs(self):
        result = lab.greedy_choice(self.row,self.prior,4,per_cost=False)
        self.assertEqual(result['action_id'],1)
        self.assertEqual(result['cost_units'],4)

    def test_greedy_repeats_sensor_when_entropy_is_objective(self):
        p=lab.posterior(self.row,[{'action_id':3,'observed_Y':self.observed}])
        self.assertEqual(lab.greedy_choice(self.row,p,1)['action_id'],3)

    def test_exact_MAP_prefers_other_bit_after_first_observation(self):
        p=lab.posterior(self.row,[{'action_id':3,'observed_Y':self.observed}])
        self.assertEqual(lab.exact_budget_plan(self.row,p,1)['optimal_first_action']['action_id'],4)

    def test_exact_budget_zero_is_uninformed_guess(self):
        p=lab.exact_budget_plan(self.row,self.prior,0)
        self.assertIsNone(p['optimal_first_action'])
        self.assertEqual(p['expected_final_MAP_accuracy']['decimal'],0.0625)

    def test_exact_budget_one_is_exact_fraction(self):
        p=lab.exact_budget_plan(self.row,self.prior,1)
        self.assertEqual((p['expected_final_MAP_accuracy']['numerator'],p['expected_final_MAP_accuracy']['denominator']),(7,64))
        self.assertEqual(p['optimal_first_action']['action_id'],3)

    def test_exact_budget_two_uses_two_distinct_measurements(self):
        p=lab.exact_budget_plan(self.row,self.prior,2)
        self.assertEqual((p['expected_final_MAP_accuracy']['numerator'],p['expected_final_MAP_accuracy']['denominator']),(21,128))
        self.assertEqual(p['optimal_first_action']['action_id'],3)

    def test_exact_budget_non_decreasing_with_money(self):
        scores=[lab.exact_budget_plan(self.row,self.prior,b)['expected_final_MAP_accuracy']['decimal'] for b in range(5)]
        self.assertEqual(scores,sorted(scores))
        self.assertEqual(scores[-1],0.19140625)

    def test_identical_results_across_seven_synthetic_families(self):
        values=[lab.exact_budget_plan(row,self.prior,2)['expected_final_MAP_accuracy']['decimal'] for row in self.rows.values()]
        self.assertEqual(values,[0.1640625]*7)

    def test_replay_probabilistic_observation_can_be_flipped(self):
        true_result=old._response(self.row,5,3)
        weights=lab.posterior(self.row,[{'action_id':3,'observed_Y':not true_result}])
        self.assertEqual(weights[5],Fraction(1,64))

    def test_invalid_actions_do_not_coerce_bool_or_float(self):
        for wrong in (True, False, -1, 8, 2.5, '3'):
            with self.subTest(wrong=wrong),self.assertRaises((old.DesignError,lab.NoisyDesignError)):
                lab.action_cost(wrong)

    def test_invalid_evidence_rejected(self):
        for wrong in ([{'action_id':3,'observed_Y':1}],
                      [{'action_id':3,'observed_Y':True,'truth':True}],
                      [{'action_id':'3','observed_Y':False}],
                      [{'action_id':3}],
                      '3=1',
                      [{}]*33):
            with self.subTest(wrong=str(wrong)[:40]),self.assertRaises(lab.NoisyDesignError):
                lab.posterior(self.row,wrong)

    def test_invalid_prior_rejected(self):
        for bad in ((Fraction(0),)*16, (Fraction(1),)*15, (1,)*16):
            with self.assertRaises(lab.NoisyDesignError):
                lab.map_accuracy(bad)

    def test_observation_parser_rejects_malformed_strings(self):
        self.assertEqual(lab._parse_event('3=1'), {'action_id':3,'observed_Y':True})
        for text in ('3=true','9=1','abc=1','3','True=0','3=2'):
            with self.subTest(text=text),self.assertRaises(lab.NoisyDesignError):
                lab._parse_event(text)

    def test_stale_v019_source_is_rejected_before_reading(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'active-design-v0.19.json';p.write_text('{}',encoding='utf-8')
            with patch.object(old,'REPORT_PATH',p):
                with self.assertRaisesRegex(lab.NoisyDesignError,'changed'):
                    lab._frozen_rows()

    def test_modified_v020_scenario_is_rejected(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'v020.json';p.write_text('{}',encoding='utf-8')
            with patch.object(lab,'SPEC_PATH',p):
                with self.assertRaisesRegex(lab.NoisyDesignError,'not canonical'):
                    lab._frozen_rows()

    def test_report_fixture_matches_byte_for_byte(self):
        self.assertEqual(lab.REPORT_PATH.read_bytes(),lab.serialized_report().encode('utf-8'))
        self.assertEqual(lab.make_report()['counts']['families'],7)

    def test_cli_check_and_report(self):
        self.assertEqual(lab.main(['check']),0)
        self.assertEqual(lab.main(['report']),0)

    def test_cli_plan_replay_and_bad_input(self):
        self.assertEqual(lab.main(['plan','--family','F17_DIRECT','--budget','2','--observe','3=1']),0)
        self.assertEqual(lab.main(['replay','--family','F17_DIRECT','--mask','5','--action','3','--flip']),0)
        self.assertEqual(lab.main(['plan','--family','NOPE']),1)
        self.assertEqual(lab.main(['plan','--budget','9']),1)


if __name__ == '__main__':
    unittest.main()
