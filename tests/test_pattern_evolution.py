"""v0.11 proposal gate: structural checks do not prove intended meaning."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from compact_surface import locked_patterns
from pattern_lab import PATTERNS, PatternError, load_patterns, sha256
from pattern_evolution import (
    EvolutionError, NEEDS_EVIDENCE, PROPOSALS, REJECTED, STAGED,
    audit, evaluate_one, read_proposals, staging_preview,
)


class EvolutionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_proposals(PROPOSALS)
        cls.baseline = locked_patterns()
        cls.base_doc = json.loads(PATTERNS.read_text(encoding='utf-8'))
        cls.report = audit(enforce_fixture=True)

    def case(self, id):
        return next(c for c in self.report['cases'] if c['id'] == id)

    def fresh_one(self, id, mutate=None):
        item = copy.deepcopy(next(p for p in self.rows if p['id'] == id))
        if mutate:
            mutate(item)
        from pattern_evolution import _signature
        sigs = {_signature(name, self.baseline): name for name in self.baseline}
        return evaluate_one(item, self.base_doc, self.baseline, set(), sigs)

    def test_expected_counts(self):
        self.assertEqual(self.report['candidate_count'], 14)
        self.assertEqual(self.report['decisions'], {
            STAGED: 4, NEEDS_EVIDENCE: 2, REJECTED: 8
        })

    def test_four_stage_examples_are_checked(self):
        for number in range(1, 5):
            with self.subTest(number=number):
                case = self.case(f'EV011-{number:02}')
                self.assertEqual(case['status'], STAGED)
                self.assertEqual(case['examples_checked'], 2)
                self.assertEqual(len(case['example_checks']), 2)

    def test_expected_negative_decisions(self):
        for number in (5, 6, 7, 8, 9, 10, 13, 14):
            with self.subTest(number=number):
                self.assertEqual(self.case(f'EV011-{number:02}')['status'], REJECTED)

    def test_insufficient_examples_remain_unstaged(self):
        for number in (11, 12):
            with self.subTest(number=number):
                case = self.case(f'EV011-{number:02}')
                self.assertEqual(case['status'], NEEDS_EVIDENCE)
                self.assertEqual(case['examples_checked'], 1)

    def test_base_registry_immutability(self):
        before = sha256(PATTERNS)
        audit()
        self.assertEqual(before, sha256(PATTERNS))
        self.assertEqual(len(self.baseline), 16)
        self.assertTrue(all(c['name'] not in self.baseline for c in self.report['cases'] if c['status'] == STAGED))
        self.assertFalse(self.report['promotion_performed'])

    def test_duplicate_native_pattern_detected(self):
        self.assertEqual(self.case('EV011-05')['reason'], 'duplicate_expansion_signature')

    def test_duplicate_staged_pattern_detected(self):
        duplicate = self.case('EV011-06')
        self.assertEqual(duplicate['reason'], 'duplicate_expansion_signature')
        self.assertEqual(duplicate['duplicate_of'], 'P_BEFORE_CHECK_DELETE')

    def test_scoped_binder_rejected(self):
        self.assertEqual(self.case('EV011-07')['reason'], 'template_validation_failed')

    def test_unused_argument_rejected(self):
        self.assertEqual(self.case('EV011-08')['reason'], 'template_validation_failed')

    def test_raw_tunnel_rejected(self):
        self.assertEqual(self.case('EV011-09')['reason'], 'template_validation_failed')

    def test_wrong_expected_reference_rejected(self):
        self.assertEqual(self.case('EV011-10')['reason'], 'reference_structure_mismatch')
        self.assertEqual(self.case('EV011-10')['failing_example'], 1)

    def test_existing_id_collision_rejected(self):
        self.assertEqual(self.case('EV011-13')['reason'], 'existing_registry_name_collision')

    def test_cycle_rejected(self):
        self.assertEqual(self.case('EV011-14')['reason'], 'template_validation_failed')

    def test_human_preview_has_non_active_schema(self):
        preview = staging_preview(self.report)
        self.assertFalse(preview['promotion_performed'])
        self.assertEqual(len(preview['patterns_for_human_review']), 4)
        self.assertIn('NOT-ACTIVE', preview['format'])
        with tempfile.TemporaryDirectory() as dir:
            path = Path(dir) / 'non-active.json'
            path.write_text(json.dumps(preview), encoding='utf-8')
            with self.assertRaises(PatternError):
                load_patterns(path)

    def test_literal_role_swap_fails_reference(self):
        result = self.fresh_one('EV011-01', lambda row: row['examples'][0].update({
            'expected': 'BEFORE(earlier=DO(actor=FILE, action=CHECK, object=PROGRAM), '
                        'later=DO(actor=PROGRAM, action=DELETE, object=FILE))'}))
        self.assertEqual(result['reason'], 'reference_structure_mismatch')

    def test_missing_provenance_rejected(self):
        result = self.fresh_one('EV011-01', lambda row: row.update({'origin': ''}))
        self.assertEqual(result['reason'], 'missing_or_invalid_provenance')

    def test_unrecognized_field_rejected(self):
        result = self.fresh_one('EV011-01', lambda row: row.update({'run_remote_code': 'yes'}))
        self.assertEqual(result['reason'], 'unknown_proposal_fields')

    def test_invalid_example_does_not_partial_stage(self):
        result = self.fresh_one('EV011-02', lambda row: row['examples'][1].update({'input': 'P_ACT(actor=AI,action=HELP,object=PERSON)'}))
        self.assertEqual(result['reason'], 'example_must_call_candidate')

    def test_duplicate_ids_fail_the_benchmark(self):
        rows = self.rows[:2] + self.rows[:1]
        with tempfile.TemporaryDirectory() as dir:
            path = Path(dir) / 'duplicated.jsonl'
            path.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            with self.assertRaisesRegex(EvolutionError, 'duplicate proposal ID'):
                read_proposals(path)

    def test_invalid_json_fails_the_benchmark(self):
        with tempfile.TemporaryDirectory() as dir:
            path = Path(dir) / 'bad.jsonl'
            path.write_text('{invalid JSON}', encoding='utf-8')
            with self.assertRaisesRegex(EvolutionError, 'malformed JSON'):
                read_proposals(path)

    def test_oversized_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as dir:
            path = Path(dir) / 'oversized.jsonl'
            path.write_bytes(b'X' * 256_001)
            with self.assertRaisesRegex(EvolutionError, 'limit'):
                read_proposals(path)

    def test_fixture_expectation_is_checked_not_trusted(self):
        altered = copy.deepcopy(self.rows)
        altered[0]['expected_status'] = REJECTED
        with tempfile.TemporaryDirectory() as dir:
            path = Path(dir) / 'false-expectation.jsonl'
            path.write_text('\n'.join(json.dumps(row) for row in altered), encoding='utf-8')
            with self.assertRaisesRegex(EvolutionError, 'expected rejected'):
                audit(path, enforce_fixture=True)


if __name__ == '__main__':
    unittest.main()
