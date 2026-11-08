import json
from pathlib import Path
import tempfile
import unittest

from finite_probe import FiniteModel, ProbeError, check_cases, evaluate

ROOT = Path(__file__).resolve().parents[1]
MODEL = FiniteModel.load(ROOT / 'data/finite-world-v0.4.json')


class FiniteProbeTests(unittest.TestCase):
    def test_regression_cases(self):
        result = check_cases()
        self.assertEqual(result['cases_checked'], 20)
        self.assertEqual(result['expected_true'], 10)
        self.assertEqual(result['expected_false'], 10)
        self.assertIsNone(result['independent_ai_reading_score'])

    def test_temporal_direction_and_world_change(self):
        expr = 'BEFORE(earlier=READ_EVENT, later=WRITE_EVENT)'
        self.assertTrue(evaluate(expr, MODEL, world='actual'))
        self.assertFalse(evaluate(expr, MODEL, world='possible'))
        self.assertFalse(evaluate('BEFORE(earlier=WRITE_EVENT, later=READ_EVENT)', MODEL))

    def test_structured_event_descriptors(self):
        expr = 'BEFORE(earlier=DO(actor=PROGRAM, action=READ, object=FILE), later=DO(actor=PROGRAM, action=WRITE, object=OUTPUT))'
        self.assertTrue(evaluate(expr, MODEL))

    def test_possibility_is_not_fact(self):
        claim = 'IS(subject=SYSTEM, property=DISTURBED)'
        self.assertFalse(evaluate(claim, MODEL))
        self.assertTrue(evaluate(f'MAY(claim={claim})', MODEL))

    def test_not_possible_distinct_from_possibly_not(self):
        claim = 'IS(subject=SYSTEM, property=DISTURBED)'
        self.assertFalse(evaluate(f'NOT(claim=MAY(claim={claim}))', MODEL))
        self.assertTrue(evaluate(f'MAY(claim=NOT(claim={claim}))', MODEL))

    def test_existential_not_universal(self):
        claim = 'IS(subject=REF(var=X), property=READY)'
        self.assertTrue(evaluate(f'EXISTS(var=X, domain=PERSON, claim={claim})', MODEL))
        self.assertFalse(evaluate(f'FORALL(var=X, domain=PERSON, claim={claim})', MODEL))

    def test_quantifier_order_changes_meaning(self):
        compare = 'COMPARE(left=REF(var=X), right=REF(var=Y), by=EQUAL)'
        self.assertTrue(evaluate(f'FORALL(var=X, domain=PERSON, claim=EXISTS(var=Y, domain=PERSON, claim={compare}))', MODEL))
        self.assertFalse(evaluate(f'EXISTS(var=Y, domain=PERSON, claim=FORALL(var=X, domain=PERSON, claim={compare}))', MODEL))

    def test_lexical_shadowing(self):
        expr = 'FORALL(var=X, domain=PERSON, claim=EXISTS(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))'
        self.assertTrue(evaluate(expr, MODEL))

    def test_empty_domain_vacuity(self):
        expr = 'IS(subject=REF(var=X), property=READY)'
        self.assertTrue(evaluate(f'FORALL(var=X, domain=EMPTY, claim={expr})', MODEL))
        self.assertFalse(evaluate(f'EXISTS(var=X, domain=EMPTY, claim={expr})', MODEL))

    def test_finite_integer_example_false(self):
        claim = 'COMPARE(left=REF(var=Y), right=REF(var=X), by=GREATER_THAN)'
        expr = f'FORALL(var=X, domain=INTEGER, claim=EXISTS(var=Y, domain=INTEGER, claim={claim}))'
        self.assertFalse(evaluate(expr, MODEL))

    def test_unbound_ref_rejected(self):
        with self.assertRaisesRegex(ProbeError, 'unbound variable'):
            evaluate('IS(subject=REF(var=X), property=READY)', MODEL)

    def test_unknown_domain_rejected(self):
        with self.assertRaisesRegex(ProbeError, 'unknown finite domain'):
            evaluate('EXISTS(var=X, domain=REAL, claim=IS(subject=REF(var=X), property=READY))', MODEL)

    def test_unknown_world_rejected(self):
        with self.assertRaisesRegex(ProbeError, 'unknown world'):
            evaluate('IS(subject=ALICE, property=READY)', MODEL, world='unseen')

    def test_unsupported_operator_fails_closed(self):
        with self.assertRaisesRegex(ProbeError, 'no finite-probe semantics'):
            evaluate('DO(actor=ALICE, action=READ, object=DATA)', MODEL)

    def test_unknown_relation_fails_closed(self):
        with self.assertRaisesRegex(ProbeError, 'unregistered relation'):
            evaluate('MAGIC(test=ALICE)', MODEL)

    def test_wrong_roles_rejected(self):
        with self.assertRaises(ProbeError):
            evaluate('BEFORE(left=READ_EVENT, right=WRITE_EVENT)', MODEL)

    def test_plain_string_not_a_formula(self):
        with self.assertRaises(ProbeError):
            evaluate('"Hello"', MODEL)

    def test_unknown_comparator_rejected(self):
        with self.assertRaisesRegex(ProbeError, 'unsupported comparator'):
            evaluate('COMPARE(left=ALICE, right=BOB, by=BETTER_THAN)', MODEL)

    def test_budget_rejected(self):
        with self.assertRaisesRegex(ProbeError, 'budget'):
            evaluate('IS(subject=ALICE, property=READY)', MODEL, budget=1)

    def test_unreachable_world_not_possible(self):
        # From 'possible', only itself is accessible, where READY(ALICE) is true;
        # the missing STABLE fact is therefore not possible there.
        self.assertFalse(evaluate('MAY(claim=IS(subject=SYSTEM, property=STABLE))', MODEL, world='possible'))

    def test_invalid_world_file_rejected(self):
        source = json.loads((ROOT / 'data/finite-world-v0.4.json').read_text(encoding='utf-8'))
        source['accessibility']['actual'] = ['absent']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            path.write_text(json.dumps(source), encoding='utf-8')
            with self.assertRaisesRegex(ProbeError, 'accessibility'):
                FiniteModel.load(path)

    def test_duplicate_fact_rejected(self):
        source = json.loads((ROOT / 'data/finite-world-v0.4.json').read_text(encoding='utf-8'))
        source['worlds']['actual']['facts'].append(['ALICE','READY'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            path.write_text(json.dumps(source), encoding='utf-8')
            with self.assertRaisesRegex(ProbeError, 'duplicate pair'):
                FiniteModel.load(path)

    def test_semantic_counterexample_to_naive_negation_equivalence(self):
        claim = 'IS(subject=REF(var=X), property=READY)'
        not_all = f'NOT(claim=FORALL(var=X, domain=PERSON, claim={claim}))'
        all_not = f'FORALL(var=X, domain=PERSON, claim=NOT(claim={claim}))'
        self.assertTrue(evaluate(not_all, MODEL))
        self.assertFalse(evaluate(all_not, MODEL))

    def test_read_only_definition_model_object(self):
        with self.assertRaises(AttributeError):
            MODEL.facts = {}


if __name__ == '__main__':
    unittest.main()
