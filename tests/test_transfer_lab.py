"""v0.13 transfer constraints, historical controls, and non-promotion guard."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alcg import Call, Name, parse
from compact_surface import check_cases, locked_patterns
from coverage_lab import jsonl
from pattern_discovery import verify_snapshot
from pattern_lab import PATTERNS, sha256
from semantic_lab import normalize
from transfer_lab import (
    HISTORICAL, HISTORICAL_PIN, PROBES, REPORT, TransferError,
    _match, _read_candidate_patterns, _training_normal_forms,
    apply_pattern, historical_transfer, report, targeted_transfer, verify, main,
)


class TransferLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns, cls.active = _read_candidate_patterns()
        cls.training = _training_normal_forms()
        cls.report = report()
        cls.by_root = {p.template.name: p for p in cls.patterns}

    def test_cli_match_nonactive_proposal(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(['match', 'CAUSE(source=DROUGHT, effect=CHANGE(subject=SOIL, property=MOISTURE))'])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result['matched'])
        self.assertFalse(result['active_registry_changed'])
        self.assertEqual(result['semantic_accuracy'], None)
        self.assertIn('P_DISC_CAUSE_', result['candidate'])

    def test_cli_no_match_is_not_an_error_or_english_translation(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(['match', 'DO(actor=AI, action=READ, object=DATA)'])
        self.assertEqual(status, 0)
        self.assertFalse(json.loads(output.getvalue())['matched'])

    def test_frozen_training_only_64_structured_cases(self):
        self.assertEqual(len(self.training), 64)
        self.assertEqual(len(self.patterns), 4)
        self.assertEqual(set(self.by_root), {'CAUSE', 'BEFORE', 'EXISTS', 'NOT'})

    def test_historical_nontraining_boundary(self):
        summary = self.report['historical_nontraining']
        self.assertEqual(summary['total_historical_expressions'], 96)
        self.assertEqual(summary['exact_training_overlaps_excluded'], 39)
        self.assertEqual(summary['nontraining_expressions'], 57)
        self.assertEqual(summary['distinct_nontraining_expressions'], 57)
        self.assertEqual(summary['matches_to_candidates'], 3)
        self.assertEqual(summary['matches_by_answer_role'], {'foil': 3})
        self.assertEqual({r['id'] for r in summary['matched_cases']},
                         {'K403', 'K407', 'V715'})
        self.assertTrue(all(r['side'] == 'foil' for r in summary['matched_cases']))

    def test_historical_data_sha256_is_pinned(self):
        self.assertEqual(len(HISTORICAL), 3)
        for path in HISTORICAL:
            self.assertEqual(sha256(path), HISTORICAL_PIN[path.relative_to(PROBES.parents[1]).as_posix()])

    def test_historical_mutation_rejected(self):
        bad = dict(HISTORICAL_PIN)
        bad['benchmarks/contrast-v0.3.jsonl'] = '0' * 64
        with patch('transfer_lab.HISTORICAL_PIN', bad):
            with self.assertRaisesRegex(TransferError, 'historical data changed'):
                historical_transfer(self.patterns, self.active, self.training)

    def test_historical_foils_are_not_credited_as_correct(self):
        self.assertNotIn('correct', self.report['historical_nontraining']['matches_by_answer_role'])
        self.assertEqual(self.report['semantic_comprehension_accuracy'], None)
        self.assertFalse(self.report['external_generalization_claim'])

    def test_positive_targeted_transfer_and_foil_split(self):
        summary = self.report['posthoc_diagnostic']
        self.assertEqual(summary['positive_tests'], 16)
        self.assertEqual(summary['positive_structural_matches'], 16)
        self.assertEqual(summary['same_shape_meaning_shift_foils_still_match'], 8)
        self.assertEqual(summary['role_or_structure_foils_rejected'], 8)
        self.assertTrue(summary['authored_after_discovery'])
        self.assertEqual(len({r['domain'] for r in summary['pairs']}), 9)

    def test_posthoc_positive_canonical_structures_disjoint_from_training(self):
        for row in jsonl(PROBES):
            c = normalize(parse(row['positive']))
            self.assertNotIn(c, self.training)

    def test_named_argument_order_not_semantics(self):
        p = self.by_root['CAUSE']
        case = 'CAUSE(effect=CHANGE(property=MOISTURE, subject=SOIL), source=DROUGHT)'
        matched = apply_pattern(case, p, self.active)
        self.assertIsNotNone(matched)
        self.assertIn('P_DISC_CAUSE_', matched['call'])

    def test_different_lexical_leaf_substitution_roundtrips(self):
        p = self.by_root['NOT']
        e = 'NOT(claim=COMPARE(left=REVENUE, right=COST, by=LESS_THAN))'
        a = apply_pattern(e, p, self.active)
        self.assertEqual(len(a['sha256']), 64)
        self.assertTrue(a['compact'].startswith('@DISC_NOT_'))
        self.assertLess(a['compact_utf8_bytes'], a['expanded_utf8_bytes'])

    def test_actor_coreference_constraint(self):
        p = self.by_root['BEFORE']
        e = ('BEFORE(earlier=DO(actor=NURSE, action=CHECK, object=MEDICINE), '
             'later=DO(actor=DOCTOR, action=ADMINISTER, object=MEDICINE))')
        self.assertIsNone(apply_pattern(e, p, self.active))

    def test_binder_reference_constraint(self):
        p = self.by_root['EXISTS']
        e = ('EXISTS(var=S, domain=SCORE, claim=COMPARE(left=REF(var=T), '
             'right=PASS_MARK, by=EQUAL))')
        self.assertIsNone(apply_pattern(e, p, self.active))

    def test_shape_change_rejected(self):
        p = self.by_root['CAUSE']
        e = 'CAUSE(source=MEDICINE, effect=DO(actor=PATIENT, action=RECOVER))'
        self.assertIsNone(apply_pattern(e, p, self.active))

    def test_wrong_role_can_still_match_and_is_not_semantic_proof(self):
        p = self.by_root['CAUSE']
        before = 'CAUSE(source=DROUGHT, effect=CHANGE(subject=SOIL, property=MOISTURE))'
        altered = 'CAUSE(source=MOISTURE, effect=CHANGE(subject=SOIL, property=DROUGHT))'
        self.assertIsNotNone(apply_pattern(before, p, self.active))
        self.assertIsNotNone(apply_pattern(altered, p, self.active))
        self.assertNotEqual(normalize(parse(before)), normalize(parse(altered)))

    def test_temporal_reversal_still_matches_shape(self):
        p = self.by_root['BEFORE']
        before = ('BEFORE(earlier=DO(actor=DRONE, action=LOAD, object=PACKAGE), '
                  'later=DO(actor=DRONE, action=DELIVER, object=PACKAGE))')
        reversed_ = ('BEFORE(earlier=DO(actor=DRONE, action=DELIVER, object=PACKAGE), '
                     'later=DO(actor=DRONE, action=LOAD, object=PACKAGE))')
        self.assertIsNotNone(apply_pattern(before, p, self.active))
        self.assertIsNotNone(apply_pattern(reversed_, p, self.active))
        self.assertNotEqual(normalize(parse(before)), normalize(parse(reversed_)))

    def test_diagnostic_status_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            copy_rows = jsonl(PROBES)
            copy_rows[0]['foil_should_match'] = False
            bad = Path(d) / 'bad.jsonl'
            bad.write_text(''.join(json.dumps(r) + '\n' for r in copy_rows), encoding='utf-8')
            with self.assertRaisesRegex(TransferError, 'foil class disagrees'):
                targeted_transfer(self.patterns, self.active, self.training, bad)

    def test_training_data_leak_in_diagnostic_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            cases = jsonl(PROBES)
            cases[0]['positive'] = 'CAUSE(source=ERROR, effect=CHANGE(subject=OUTPUT, property=VALUE))'
            file = Path(d) / 'leak.jsonl'
            file.write_text(''.join(json.dumps(r) + '\n' for r in cases), encoding='utf-8')
            with self.assertRaisesRegex(TransferError, 'training leakage'):
                targeted_transfer(self.patterns, self.active, self.training, file)

    def test_foil_leaking_training_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            cases = jsonl(PROBES)
            cases[0]['foil'] = 'CAUSE(source=ERROR, effect=CHANGE(subject=OUTPUT, property=VALUE))'
            file = Path(d) / 'leak.jsonl'
            file.write_text(''.join(json.dumps(r) + '\n' for r in cases), encoding='utf-8')
            with self.assertRaisesRegex(TransferError, 'foil leaks training'):
                targeted_transfer(self.patterns, self.active, self.training, file)

    def test_same_shape_foils_are_not_claimed_semantically_correct(self):
        rows = self.report['posthoc_diagnostic']['pairs']
        foils = [r for r in rows if r['foil_matched']]
        self.assertEqual(len(foils), 8)
        self.assertTrue(all(r['foil_changed_canonical_structure'] for r in foils))

    def test_costs_include_one_definition_and_no_promotion(self):
        items = self.report['posthoc_diagnostic']['candidate_usage_costs']
        self.assertEqual(len(items), 4)
        for c in items:
            self.assertEqual(c['net_after_one_definition_bytes'],
                             c['payload_bytes_saved'] - c['definition_utf8_bytes_estimate'])
            self.assertLess(c['net_after_one_definition_bytes'], 0)
        self.assertEqual(self.report['promoted_patterns'], 0)
        self.assertEqual(self.report['independent_ai_readers'], 0)

    def test_original_16_entry_active_registry_unchanged(self):
        pinned = '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6'
        self.assertEqual(sha256(PATTERNS), pinned)
        self.assertEqual(len(locked_patterns()), 16)
        self.assertEqual(check_cases()['exact_expanded_canonical_roundtrips'], 24)
        self.assertEqual(sha256(PATTERNS), pinned)
        self.assertEqual(verify_snapshot()['generated_candidate_count'], 4)

    def test_report_reproduces_committed_artifact(self):
        self.assertEqual(verify(), self.report)
        self.assertEqual(json.loads(REPORT.read_text(encoding='utf-8')), self.report)

    def test_report_discloses_non_independence(self):
        self.assertTrue(self.report['posthoc_diagnostic']['authored_after_discovery'])
        self.assertEqual(self.report['semantic_comprehension_accuracy'], None)
        self.assertFalse(self.report['external_generalization_claim'])
        self.assertIn('NO INDEPENDENT', self.report['caution'].upper())


if __name__ == '__main__':
    unittest.main()
