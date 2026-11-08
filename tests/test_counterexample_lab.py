"""v0.15 bounded witnesses and explicit unsupported/inconclusive cases."""
from __future__ import annotations

import contextlib
import copy
from hashlib import sha256
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from alcg import parse
from challenge_generator import SUITE
from finite_probe import ProbeError, evaluate
from counterexample_lab import (
    REPORT, SOURCE_SHA256, WitnessError, _candidate_models, _empty_model,
    _find_witness, audit, main, model_from_data, model_to_data, replay, verify,
)


class CounterexampleLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit()
        cls.findings = cls.report['findings']
        cls.by_root = {r: [x for x in cls.findings if x['root'] == r]
                       for r in ('BEFORE', 'CAUSE', 'EXISTS', 'NOT')}

    def test_source_is_sha_pinned_v014_not_modified(self):
        self.assertEqual(sha256(SUITE.read_bytes()).hexdigest(), SOURCE_SHA256)

    def test_104_variants_four_roots(self):
        self.assertEqual(self.report['variants'], 104)
        self.assertEqual(self.report['cases'], 32)
        for root in self.by_root:
            self.assertEqual(len({x['case_id'] for x in self.by_root[root]}), 8)

    def test_explicit_status_partition(self):
        self.assertEqual(self.report['counts'], {
            'canonical_equivalent': 40,
            'finite_counterexample': 46,
            'no_witness_under_bounded_model': 2,
            'unsupported_causality': 16,
        })
        self.assertEqual(sum(self.report['counts'].values()), 104)

    def test_no_ai_semantic_score_claimed(self):
        self.assertEqual(self.report['independent_ai_readers'], 0)
        self.assertIsNone(self.report['ai_comprehension_score'])
        self.assertIsNone(self.report['real_world_semantic_accuracy'])
        self.assertTrue(self.report['no_active_registry_change'])
        self.assertIn('NOT evidence', self.report['caveat'])

    def test_not_wrongly_claiming_causes(self):
        invalid = [x for x in self.by_root['CAUSE'] if not x['canonical_equal']]
        self.assertEqual(len(invalid), 16)
        self.assertTrue(all(x['status'] == 'unsupported_causality'
                            and x['witness'] is None and x['models_examined'] == 0
                            for x in invalid))

    def test_causal_canonical_equivalence_is_structural_only(self):
        self.assertEqual(self.report['cause_canonical_equivalences_structural_only'], 8)
        self.assertEqual(self.report['canonical_equivalences_finite_spot_checked'], 32)
        self.assertTrue(all(x['models_examined'] == 0
                            for x in self.by_root['CAUSE'] if x['canonical_equal']))

    def test_before_difference_receipt(self):
        records = [x for x in self.by_root['BEFORE'] if not x['canonical_equal']]
        self.assertEqual(len(records), 16)
        self.assertTrue(all(x['status'] == 'finite_counterexample' for x in records))
        for x in records:
            out = replay(x['case_id'], x['variant'], result=self.report)
            self.assertNotEqual(out['left_truth'], out['right_truth'])
            self.assertTrue(out['finite_model']['before']['actual'])

    def test_quantifier_counterexample_receipt(self):
        records = [x for x in self.by_root['EXISTS'] if not x['canonical_equal']]
        self.assertEqual(len(records), 16)
        self.assertTrue(all(x['status'] == 'finite_counterexample' for x in records))
        for x in records:
            out = replay(x['case_id'], x['variant'], result=self.report)
            self.assertTrue(out['left_truth'])
            self.assertFalse(out['right_truth'])
            self.assertTrue(out['finite_model']['domains'])

    def test_negation_modal_and_lexical_comparisons(self):
        records = [x for x in self.by_root['NOT'] if not x['canonical_equal']]
        self.assertEqual(len(records), 16)
        self.assertEqual(sum(x['status'] == 'finite_counterexample' for x in records), 14)
        self.assertEqual(sum(x['status'] == 'no_witness_under_bounded_model' for x in records), 2)
        self.assertTrue(all(x['models_examined'] > 0 for x in records))

    def test_literal_equal_shortcoming_is_inconclusive_not_equivalence(self):
        undecided = [x for x in self.findings if x['status'] == 'no_witness_under_bounded_model']
        self.assertEqual({x['variant'] for x in undecided}, {'lexical_slot_change'})
        self.assertEqual({x['root'] for x in undecided}, {'NOT'})
        self.assertTrue(all(not x['canonical_equal'] for x in undecided))
        self.assertTrue(all(x['witness'] is None for x in undecided))
        self.assertTrue(all(x['models_examined'] == 27 for x in undecided))

    def test_less_than_is_supported_in_finite_probe(self):
        model = _empty_model(order={'LOW': 0, 'HIGH': 1})
        self.assertTrue(evaluate('COMPARE(left=LOW, right=HIGH, by=LESS_THAN)', model))
        self.assertFalse(evaluate('COMPARE(left=HIGH, right=LOW, by=LESS_THAN)', model))
        self.assertTrue(evaluate('COMPARE(left=HIGH, right=LOW, by=GREATER_THAN)', model))

    def test_named_argument_reordering_and_alpha_renaming(self):
        equivalent = [x for x in self.findings if x['canonical_equal']]
        self.assertEqual(len(equivalent), 40)
        self.assertEqual(sum(x['variant'] == 'bound_variable_alpha_rename' for x in equivalent), 8)
        self.assertTrue(all(x['status'] == 'canonical_equivalent' and x['witness'] is None
                            for x in equivalent))

    def test_first_witness_is_replayable_for_all_46(self):
        witnesses = [x for x in self.findings if x['status'] == 'finite_counterexample']
        self.assertEqual(len(witnesses), 46)
        self.assertEqual(len({(x['case_id'], x['variant']) for x in witnesses}), 46)
        for x in witnesses:
            r = replay(x['case_id'], x['variant'], result=self.report)
            self.assertIn(r['world'], ('actual',))
            self.assertNotEqual(r['left_truth'], r['right_truth'])

    def test_model_roundtrip_canonical(self):
        witness = next(x for x in self.findings if x['status'] == 'finite_counterexample')['witness']
        self.assertEqual(model_to_data(model_from_data(witness['model'])), witness['model'])
        self.assertEqual(model_to_data(model_from_data(json.loads(json.dumps(witness['model'])))),
                         witness['model'])

    def test_reject_model_extra_field(self):
        witness = next(x for x in self.findings if x['status'] == 'finite_counterexample')['witness']
        altered = copy.deepcopy(witness['model'])
        altered['fake'] = 1
        with self.assertRaises(WitnessError):
            model_from_data(altered)

    def test_reject_accessibility_beyond_model(self):
        witness = next(x for x in self.findings if x['status'] == 'finite_counterexample')['witness']
        altered = copy.deepcopy(witness['model'])
        altered['accessibility']['actual'] = ['external-world']
        with self.assertRaises(WitnessError):
            model_from_data(altered)

    def test_reject_duplicate_or_invalid_edges(self):
        receipt = next(x for x in self.by_root['BEFORE'] if x['status'] == 'finite_counterexample')['witness']
        bad = copy.deepcopy(receipt['model'])
        bad['before']['actual'].append(bad['before']['actual'][0])
        with self.assertRaisesRegex(WitnessError, 'duplicate'):
            model_from_data(bad)

    def test_reject_tampered_witness_truth(self):
        item = next(x for x in self.findings if x['status'] == 'finite_counterexample')
        modified = copy.deepcopy(self.report)
        entry = next(x for x in modified['findings'] if
                     x['case_id'] == item['case_id'] and x['variant'] == item['variant'])
        entry['witness']['left'] = not entry['witness']['left']
        with self.assertRaises(WitnessError):
            replay(item['case_id'], item['variant'], result=modified)

    def test_reject_tampered_witness_model(self):
        item = next(x for x in self.by_root['BEFORE'] if x['status'] == 'finite_counterexample')
        modified = copy.deepcopy(self.report)
        entry = next(x for x in modified['findings'] if
                     x['case_id'] == item['case_id'] and x['variant'] == item['variant'])
        entry['witness']['model']['before']['actual'] = []
        with self.assertRaises(WitnessError):
            replay(item['case_id'], item['variant'], result=modified)

    def test_reject_tampered_witness_world(self):
        item = next(x for x in self.findings if x['status'] == 'finite_counterexample')
        modified = copy.deepcopy(self.report)
        entry = next(x for x in modified['findings'] if
                     x['case_id'] == item['case_id'] and x['variant'] == item['variant'])
        entry['witness']['world'] = 'possible'
        with self.assertRaisesRegex(WitnessError, 'world'):
            replay(item['case_id'], item['variant'], result=modified)

    def test_refuse_replay_of_unknown_or_unwitnessed_case(self):
        with self.assertRaisesRegex(WitnessError, 'unknown'):
            replay('NO_SUCH_ID', 'lexical_slot_change', result=self.report)
        with self.assertRaisesRegex(WitnessError, 'no finite'):
            replay('G14_CAUSE_01', 'lexical_slot_change', result=self.report)

    def test_unspecified_operators_not_given_fake_semantics(self):
        with self.assertRaisesRegex(WitnessError, 'no bounded'):
            list(_candidate_models(parse('CAUSE(source=HEAT, effect=CHANGE(subject=WATER,property=STATE))'),
                                   parse('CAUSE(source=FIRE,effect=CHANGE(subject=WATER,property=STATE))')))

    def test_source_digest_attack_caught(self):
        with patch('counterexample_lab.SOURCE_SHA256', '0'*64):
            with self.assertRaisesRegex(WitnessError, 'immutable'):
                audit()

    def test_report_reproducibility_and_replay_validation(self):
        self.assertEqual(verify(), self.report)
        self.assertEqual(json.loads(REPORT.read_text(encoding='utf-8')), self.report)

    def test_modified_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'fake.json'
            modified = copy.deepcopy(self.report)
            modified['counts']['finite_counterexample'] = 999
            p.write_text(json.dumps(modified), encoding='utf-8')
            with patch('counterexample_lab.REPORT', p):
                with self.assertRaisesRegex(WitnessError, 'disagrees'):
                    verify()

    def test_cli_summary_does_not_claim_ai_comprehension(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(['report']), 0)
        summary = json.loads(stream.getvalue())
        self.assertNotIn('findings', summary)
        self.assertIsNone(summary['ai_comprehension_score'])
        self.assertEqual(summary['counts'], self.report['counts'])

    def test_cli_replay_one_case(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(['replay', '--case', 'G14_EXISTS_01',
                           '--variant', 'operator_or_coreference_change'])
        self.assertEqual(result, 0)
        doc = json.loads(output.getvalue())
        self.assertTrue(doc['left_truth'])
        self.assertFalse(doc['right_truth'])

    def test_cli_check_runs_report_and_replay(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(['check']), 0)
        self.assertIn('all finite witnesses replayed', stream.getvalue())

    def test_reports_cover_all_roots_without_promotion(self):
        self.assertEqual(set(x['root'] for x in self.findings),
                         {'BEFORE','CAUSE','EXISTS','NOT'})
        self.assertEqual(self.report['no_active_registry_change'], True)


if __name__ == '__main__':
    unittest.main()
