"""ALCG v0.19: finite, replayable active experiment-design checks.

These tests assert properties of a 16-mask synthetic Boolean SCM family, not
empirical causal identifiability or natural-language comprehension.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import active_design as lab
import causal_robustness as v17
import mechanism_search as v18

ROOT = Path(__file__).resolve().parents[1]


class ActiveDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {r['family_id']: r for r in lab._read_pinned_report()['families']}
        cls.families = {fam.family_id: fam for fam in v17.load_families()}
        cls.row = cls.rows['F17_DIRECT']
        cls.family = cls.families['F17_DIRECT']
        cls.anchor = lab._anchor_mask(cls.row, cls.family)

    def test_pinned_frozen_source_and_spec(self):
        self.assertEqual(lab.design_spec()['hypotheses_per_family'], 16)
        self.assertEqual(lab.SPEC_PATH.read_text(encoding='utf-8'), lab.serialized_spec())
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(set(self.rows), set(self.families))

    def test_exact_action_order_and_four_informative_queries(self):
        self.assertEqual(lab.informative_actions(), (1, 3, 4, 6))
        self.assertEqual([lab.action_data(a)['do_SIGNAL'] for a in range(8)],
                         [False, True] * 4)
        self.assertEqual([lab.action_data(a)['same_as_natural_SIGNAL'] for a in range(8)],
                         [True, False, True, False, False, True, False, True])

    def test_all_natural_observations_are_identical_across_all_masks(self):
        for row in self.rows.values():
            for i, (u,g) in enumerate(v18.CONTEXTS):
                natural_action = i*2 + int(u)
                answers = {lab._response(row, m, natural_action) for m in range(16)}
                self.assertEqual(answers, {row['anchor_observations_U_G'][i]})

    def test_each_off_support_action_reveals_exactly_one_mask_bit(self):
        for row in self.rows.values():
            for mask in lab.MASKS:
                for i, (u,g) in enumerate(v18.CONTEXTS):
                    off_support = i*2 + int(not u)
                    result = lab._response(row, mask, off_support)
                    self.assertEqual(result ^ row['anchor_observations_U_G'][i], bool(mask & (1 << i)))

    def test_independent_scm_check_matches_all_reported_responses(self):
        count = sum(lab._cross_check_scm(self.rows[fam.family_id], fam)
                    for fam in self.families.values())
        self.assertEqual(count, 896)

    def test_full_identification_minimax_dp(self):
        for fid, row in self.rows.items():
            anchor = lab._anchor_mask(row, self.families[fid])
            optimal = lab.optimize(row, lab.MASKS, 'identify', anchor)
            self.assertEqual(optimal.worst, 4)
            self.assertEqual(optimal.expected, Fraction(4))
            self.assertEqual(optimal.action, 1)

    def test_original_anchor_has_exact_synthetic_completion(self):
        for fid, row in self.rows.items():
            mask = lab._anchor_mask(row, self.families[fid])
            self.assertIn(mask, lab.MASKS)
            self.assertEqual(lab.simulate(row, self.families[fid], mask, 'anchor')['final_decision'], True)

    def test_anchor_agreement_optimum(self):
        for fid, row in self.rows.items():
            anchor = lab._anchor_mask(row, self.families[fid])
            result = lab.optimize(row, lab.MASKS, 'anchor', anchor)
            self.assertEqual((result.worst, result.expected, result.action), (4, Fraction(15, 8), 1))

    def test_complete_exact_discovery_traces_replay(self):
        traces = [lab.simulate(self.row, self.family, m, 'identify') for m in lab.MASKS]
        self.assertEqual({t['number_of_interventions'] for t in traces}, {4})
        self.assertTrue(all(t['compatible_masks_at_end'] == [t['true_mask']] for t in traces))
        self.assertTrue(all(t['final_decision'] == t['true_mask'] for t in traces))

    def test_early_rejection_and_anchor_receipt_histogram(self):
        traces = [lab.simulate(self.row, self.family, m, 'anchor') for m in lab.MASKS]
        histogram = Counter(t['number_of_interventions'] for t in traces)
        self.assertEqual(dict(sorted(histogram.items())), {1:8, 2:4, 3:2, 4:2})
        self.assertEqual(sum(t['number_of_interventions'] for t in traces), 30)
        self.assertEqual([t['true_mask'] for t in traces if t['final_decision'] is True], [self.anchor])
        self.assertTrue(all(t['final_decision'] is False for t in traces if t['true_mask'] != self.anchor))

    def test_all_three_example_traces_are_reproducible(self):
        for fid, row in self.rows.items():
            fam = self.families[fid]
            a = lab._anchor_mask(row, fam)
            self.assertEqual(lab.simulate(row, fam, a, 'anchor')['number_of_interventions'], 4)
            self.assertEqual(lab.simulate(row, fam, a ^ 1, 'anchor')['number_of_interventions'], 1)
            self.assertEqual(lab.simulate(row, fam, a ^ 5, 'identify')['number_of_interventions'], 4)

    def test_distinguishing_set_is_necessary_and_sufficient(self):
        for row in self.rows.values():
            result = lab.static_budgets(row)
            self.assertEqual([r['best_distinguishable_classes'] for r in result], [1,2,4,8,16])
            self.assertEqual([r['largest_indistinguishable_class'] for r in result], [16,8,4,2,1])
            for size in range(4):
                for a in combinations(range(8), size):
                    self.assertLess(len({lab._action_signature(row,m,a) for m in lab.MASKS}),16)
            ids = lab.informative_actions()
            self.assertEqual(len({lab._action_signature(row,m,ids) for m in lab.MASKS}),16)

    def test_restricted_context_cannot_fully_identify(self):
        allowed = [a for a in range(8) if lab.action_data(a)['context_index'] != 2]
        response = lab.recommend(self.row, self.anchor, 'identify', allowed_actions=allowed)
        self.assertFalse(response['identifiability_under_allowed_actions'])
        self.assertIsNone(response['minimum_worst_case_additional_interventions'])
        self.assertIsNone(response['minimum_expected_additional_interventions_uniform'])
        self.assertTrue(response['next_experiment']['partial_information_only'])
        self.assertAlmostEqual(response['next_experiment']['information_gain_bits_uniform'],1.0)

    def test_only_natural_interventions_have_no_information(self):
        natural = [a for a in range(8) if lab.action_data(a)['same_as_natural_SIGNAL']]
        reply = lab.recommend(self.row,self.anchor,'identify',allowed_actions=natural)
        self.assertIsNone(reply['next_experiment'])
        self.assertFalse(reply['identifiability_under_allowed_actions'])

    def test_observed_response_eliminates_incompatible_models(self):
        action = lab.informative_actions()[0]
        actual = lab._response(self.row, 5, action)
        remaining, tried = lab.apply_evidence(self.row,[{'action_id': action,'observed_Y': actual}])
        self.assertEqual(len(remaining),8)
        self.assertEqual(tried,(action,))
        self.assertIn(5, remaining)
        self.assertNotIn(action, [lab.action_data(a)['action_id'] for a in [lab.recommend(
            self.row,self.anchor,'identify',evidence=[{'action_id':action,'observed_Y':actual}])['next_experiment']['action_id']]])

    def test_conflicting_natural_control_rejected(self):
        i = 0
        action = i*2 + int(v18.CONTEXTS[i][0])
        wrong = not self.row['anchor_observations_U_G'][i]
        with self.assertRaisesRegex(lab.DesignError,'no v0.18 hypothesis'):
            lab.apply_evidence(self.row,[{'action_id':action,'observed_Y':wrong}])

    def test_duplicate_and_malformed_observations_are_rejected(self):
        valid = {'action_id':1,'observed_Y':False}
        invalid = [
            [valid, valid],
            [{'action_id':1,'observed_Y':1}],
            [{'action_id':1,'observed_Y':False, 'answer':'hint'}],
            [{'action_id':True,'observed_Y':False}],
            [{'action_id':-1,'observed_Y':False}],
            [{'action_id':8,'observed_Y':False}],
        ]
        for observed in invalid:
            with self.subTest(observed=observed), self.assertRaises(lab.DesignError):
                lab.apply_evidence(self.row,observed)

    def test_invalid_evidence_cli_strings(self):
        with self.assertRaises(lab.DesignError):
            lab.parse_evidence(['1=maybe'])
        with self.assertRaises(lab.DesignError):
            lab.parse_evidence(['abc=true'])
        self.assertEqual(lab.parse_evidence(['1=true','4=0']),
                         [{'action_id':1,'observed_Y':True},{'action_id':4,'observed_Y':False}])

    def test_bad_mask_or_action_and_bool_integer_confusion_rejected(self):
        for value in (-1,16,False,True,1.5,'3'):
            with self.subTest(value=value),self.assertRaises(lab.DesignError):
                lab._response(self.row,value,1)
        for value in (-1,8,False,True,'1'):
            with self.subTest(value=value),self.assertRaises(lab.DesignError):
                lab.action_data(value)
        with self.assertRaises(lab.DesignError):
            lab.optimize(self.row,lab.MASKS,'identify',self.anchor,[True])
        with self.assertRaises(lab.DesignError):
            lab.recommend(self.row,self.anchor,'identify',allowed_actions=[True])

    def test_anchor_test_terminates_without_queries_if_anchor_eliminated(self):
        selection = (0,1) if self.anchor not in (0,1) else (2,3)
        plan = lab.optimize(self.row,selection,'anchor',self.anchor)
        self.assertEqual(plan,lab.Plan(0,Fraction(0),None))

    def test_single_remaining_candidate_requires_no_queries(self):
        for objective in ('identify','anchor'):
            response = lab.recommend(self.row,self.anchor,objective,
                evidence=[{'action_id':a,'observed_Y':lab._response(self.row,0,a)}
                          for a in lab.informative_actions()])
            self.assertEqual(response['count'],1)
            self.assertTrue(response['identified'])
            self.assertIsNone(response['next_experiment'])

    def test_structural_mutation_invalidates_saved_receipt(self):
        fake = deepcopy(self.row)
        fake['candidates'][0]['new_intervention_signature'][0][1] ^= True
        with self.assertRaises(lab.DesignError):
            lab._cross_check_scm(fake,self.family)

    def test_frozen_source_manifest_tampering_rejected(self):
        with patch.object(lab,'V018_REPORT_SHA256','0'*64), self.assertRaises(lab.DesignError):
            lab._read_pinned_report()
        with tempfile.TemporaryDirectory() as temp:
            spec = Path(temp)/'changed.json'
            spec.write_text(lab.serialized_spec()+' ',encoding='utf-8')
            with patch.object(lab,'SPEC_PATH',spec), self.assertRaises(lab.DesignError):
                lab._read_pinned_report()

    def test_report_recalculation_and_saved_evidence(self):
        saved = json.loads(lab.REPORT_PATH.read_text(encoding='utf-8'))
        checked = lab.verify_report()
        self.assertTrue(checked['ok'])
        self.assertEqual(checked['synthetic_scm_interventions_replayed'],896)
        self.assertEqual(saved['summary']['minimum_worst_case_exact_identification_interventions'],4)
        self.assertEqual(saved['summary']['empirical_interventions'],0)
        self.assertEqual(saved['summary']['independent_ai_readers'],0)
        self.assertTrue(all(sum(f['enumerated_anchor_agreement_costs_per_mask_0_to_15']) == 30 for f in saved['family_results']))

    def test_modified_report_is_rejected(self):
        original = json.loads(lab.REPORT_PATH.read_text(encoding='utf-8'))
        original['summary']['candidate_models'] = 0
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'report.json'
            path.write_text(json.dumps(original),encoding='utf-8')
            with patch.object(lab,'REPORT_PATH',path),self.assertRaises(lab.DesignError):
                lab.verify_report()

    def test_cli_recommend_evidence_simulate_check(self):
        for args in (
            ['recommend','--family','F17_DIRECT'],
            ['recommend','--family','F17_DIRECT','--forbid-context','2'],
            ['recommend','--family','F17_DIRECT','--objective','anchor','--evidence','1=true'],
            ['simulate','--family','F17_DIRECT','--mask','9','--objective','anchor'],
            ['emit-spec'],
        ):
            with self.subTest(args=args):
                result=subprocess.run([sys.executable,'active_design.py',*args], cwd=ROOT,
                                      capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIsInstance(json.loads(result.stdout),dict)
        result=subprocess.run([sys.executable,'active_design.py','recommend','--evidence','1=maybe'],
                              cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('ERROR:',result.stderr)


if __name__ == '__main__':
    unittest.main()
