"""ALCG v0.5 regression tests: structural invariance + bounded countermodels."""
from pathlib import Path
import json
import tempfile
import unittest

from finite_probe import FiniteModel, ProbeError, evaluate
from semantic_lab import LabError, check_cases, compare, model_suite, normalize

ROOT = Path(__file__).resolve().parents[1]
BASE_MODEL = FiniteModel.load(ROOT / 'data/finite-world-v0.4.json')


class SemanticStabilityTests(unittest.TestCase):
    def test_regression_suite_and_score_boundary(self):
        report = check_cases()
        self.assertEqual(report['pair_cases'], 34)
        self.assertEqual(report['same_in_suite'], 16)
        self.assertEqual(report['distinguished_by_counterexample'], 18)
        self.assertEqual(report['synthetic_models'], 192)
        self.assertEqual(report['worlds_per_model'], 2)
        self.assertIsNone(report['independent_ai_reading_score'])
        self.assertEqual(len(report['first_witnesses']), 18)

    def test_generator_is_deterministic_unique_and_contains_empty_domain(self):
        first = list(model_suite())
        second = list(model_suite())
        self.assertEqual(len(first), 192)
        self.assertEqual([id for id, _ in first], [id for id, _ in second])
        self.assertEqual(len({id for id, _ in first}), 192)
        self.assertEqual({len(model.domains['PERSON']) for _, model in first}, {0, 1, 2, 3})
        self.assertIn((), {model.accessible['actual'] for _, model in first})
        self.assertIn(('actual','possible'), {model.accessible['actual'] for _, model in first})

    def test_event_argument_order_regression(self):
        a = 'BEFORE(earlier=DO(actor=PROGRAM, action=READ, object=FILE), later=DO(actor=PROGRAM, action=WRITE, object=OUTPUT))'
        b = 'BEFORE(later=DO(object=OUTPUT, actor=PROGRAM, action=WRITE), earlier=DO(object=FILE, action=READ, actor=PROGRAM))'
        self.assertTrue(evaluate(a, BASE_MODEL, world='actual'))
        self.assertTrue(evaluate(b, BASE_MODEL, world='actual'))
        self.assertEqual(normalize(a), normalize(b))
        self.assertEqual(compare(a, b).relation, 'indistinguishable_in_suite')

    def test_alpha_equivalent_nested_shadowing_is_canonical(self):
        one = 'FORALL(var=X, domain=PERSON, claim=EXISTS(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))'
        other = 'FORALL(var=Z, domain=PERSON, claim=EXISTS(var=Y, domain=PERSON, claim=IS(subject=REF(var=Y), property=READY)))'
        self.assertEqual(normalize(one), normalize(other))
        self.assertTrue(compare(one, other).canonical_same)

    def test_canonical_form_does_not_claim_logical_equivalence(self):
        p = 'IS(subject=ALICE, property=READY)'
        self.assertNotEqual(normalize(p), normalize(f'NOT(claim=NOT(claim={p}))'))
        self.assertEqual(compare(p, f'NOT(claim=NOT(claim={p}))').relation, 'indistinguishable_in_suite')

    def test_quantifier_scope_rejects_unbound_ref_even_on_empty_set(self):
        free = 'FORALL(var=X, domain=EMPTY, claim=IS(subject=REF(var=Y), property=READY))'
        with self.assertRaisesRegex(ProbeError, 'unbound variable'):
            evaluate(free, BASE_MODEL)
        with self.assertRaisesRegex(LabError, 'unbound variable'):
            normalize(free)

    def test_unbound_in_unvisited_and_branch_rejected(self):
        invalid = 'AND(left=IS(subject=BOB, property=READY), right=IS(subject=REF(var=GHOST), property=READY))'
        with self.assertRaisesRegex(ProbeError, 'unbound variable'):
            evaluate(invalid, BASE_MODEL)

    def test_changed_variable_reference_changes_meaning(self):
        one = 'FORALL(var=X, domain=PERSON, claim=EXISTS(var=Y, domain=PERSON, claim=COMPARE(left=REF(var=X), right=REF(var=Y), by=EQUAL)))'
        two = 'EXISTS(var=Y, domain=PERSON, claim=FORALL(var=X, domain=PERSON, claim=COMPARE(left=REF(var=X), right=REF(var=Y), by=EQUAL)))'
        result = compare(one, two)
        self.assertEqual(result.relation, 'distinguishable')
        self.assertIsNotNone(result.first_witness)
        self.assertNotEqual(result.first_witness.left, result.first_witness.right)

    def test_modal_logic_reports_a_real_witness_not_a_score(self):
        p = 'IS(subject=SYSTEM, property=DISTURBED)'
        result = compare(f'MAY(claim={p})', p)
        self.assertEqual(result.relation, 'distinguishable')
        self.assertIsNotNone(result.first_witness)
        self.assertTrue(result.first_witness.left)
        self.assertFalse(result.first_witness.right)
        self.assertIsNone(result.report()['independent_ai_comprehension_score'])

    def test_reference_to_constant_not_rewritten(self):
        expr = 'FORALL(var=X, domain=PERSON, claim=COMPARE(left=REF(var=X), right=ALICE, by=EQUAL))'
        self.assertIn('right=ALICE', normalize(expr))

    def test_invalid_relations_rejected(self):
        with self.assertRaises(LabError):
            compare('WIZARD()', 'IS(subject=ALICE, property=READY)')
        with self.assertRaises(LabError):
            normalize('FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=Q), property=READY))')

    def test_non_evaluable_operators_fail_closed(self):
        expr = 'DO(actor=AI, action=CREATE, object=LANGUAGE)'
        with self.assertRaisesRegex(LabError, 'no finite-probe semantics'):
            compare(expr, expr)

    def test_bad_case_expected_value_rejected(self):
        rows = (ROOT / 'benchmarks/semantic-pairs-v0.5.jsonl').read_text(encoding='utf-8').splitlines()
        data = json.loads(rows[0]); data['expected'] = 'both'
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cases.jsonl'
            p.write_text(json.dumps(data) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(LabError, 'expected must'):
                check_cases(p)

    def test_duplicate_cases_rejected(self):
        lines = (ROOT / 'benchmarks/semantic-pairs-v0.5.jsonl').read_text(encoding='utf-8').splitlines()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cases.jsonl'; p.write_text(lines[0] + '\n' + lines[0] + '\n', encoding='utf-8')
            with self.assertRaisesRegex(LabError, 'duplicate'):
                check_cases(p)

    def test_bad_case_expectation_mismatch_detected(self):
        line = (ROOT / 'benchmarks/semantic-pairs-v0.5.jsonl').read_text(encoding='utf-8').splitlines()[0]
        data = json.loads(line); data['expected'] = 'different'
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'cases.jsonl'; p.write_text(json.dumps(data) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(LabError, 'expected different'):
                check_cases(p)

    def test_toy_model_does_not_mutate_v04_fixture(self):
        baseline = (ROOT / 'data/finite-world-v0.4.json').read_bytes()
        self.assertEqual(BASE_MODEL.domains['PERSON'], ('ALICE', 'BOB'))
        for _, model in model_suite():
            self.assertIn('actual', model.facts)
        self.assertEqual((ROOT / 'data/finite-world-v0.4.json').read_bytes(), baseline)


if __name__ == '__main__':
    unittest.main()
