"""Deterministic laboratory tests, without AI or paid API calls."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from alcg import parse
from coverage_lab import (
    BenchmarkError,
    blind_rows,
    jsonl,
    load_benchmark,
    relations,
    score_rows,
    summarize,
    validate_row,
)

ROOT = Path(__file__).resolve().parents[1]


class CoverageLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_benchmark()
        cls.registry = relations()

    def test_benchmark_balanced_and_parser_roundtrip(self):
        self.assertEqual(len(self.rows), 36)
        stats = summarize(self.rows, self.registry)
        self.assertEqual(stats['candidate_not_yet_verified'], 24)
        self.assertEqual(stats['partial_with_explicit_gap'], 6)
        self.assertEqual(stats['raw_unrepresented'], 6)
        self.assertIsNone(stats['independent_reconstruction_scores'])
        self.assertEqual(set(stats['by_domain']), {'daily', 'science', 'mathematics', 'computing', 'society', 'epistemic'})
        self.assertTrue(all(d['total'] == 6 for d in stats['by_domain'].values()))
        for row in self.rows:
            self.assertEqual(parse(row['expression']), parse(row['expression']))

    def test_blind_excludes_all_original_english_and_gap_labels(self):
        packet = blind_rows(self.rows)
        self.assertEqual(len(packet), 36)
        self.assertTrue(all(set(row) == {'id', 'expression'} for row in packet))
        for row, blind in zip(self.rows, packet):
            self.assertNotIn('english', blind)
            self.assertNotIn('hypothesis', blind)
            self.assertNotIn('gap', blind)
            self.assertNotIn('domain', blind)
            self.assertEqual(blind['id'], row['id'])

    def test_rejects_unknown_operator(self):
        row = copy.deepcopy(self.rows[0])
        row['expression'] = 'MAGIC(actor=PERSON, action=DRINK, object=WATER)'
        with self.assertRaisesRegex(BenchmarkError, 'unregistered relation'):
            validate_row(row, self.registry)

    def test_rejects_missing_or_extra_role(self):
        row = copy.deepcopy(self.rows[0])
        row['expression'] = 'DO(actor=PERSON, irrelevant=WATER)'
        with self.assertRaisesRegex(BenchmarkError, 'invalid roles'):
            validate_row(row, self.registry)

    def test_rejects_opaque_text_in_candidate(self):
        row = copy.deepcopy(self.rows[0])
        row['expression'] = 'DO(actor=PERSON, action=DRINK, object="water")'
        with self.assertRaisesRegex(BenchmarkError, 'escape or partial marker'):
            validate_row(row, self.registry)

    def test_rejects_partially_encoded_as_full(self):
        row = copy.deepcopy(self.rows[4])
        row['hypothesis'] = 'candidate'
        row['gap'] = ''
        with self.assertRaisesRegex(BenchmarkError, 'escape or partial marker'):
            validate_row(row, self.registry)

    def test_partial_core_must_be_structured(self):
        row = copy.deepcopy(self.rows[4])
        row['expression'] = 'PARTIAL(core=RAW(text="nothing modeled"), missing=RAW(text="time"))'
        with self.assertRaisesRegex(BenchmarkError, 'partial core'):
            validate_row(row, self.registry)

    def test_raw_requires_natural_language_escape(self):
        row = copy.deepcopy(self.rows[5])
        row['expression'] = 'RAW(text=WATER)'
        with self.assertRaisesRegex(BenchmarkError, 'quoted string'):
            validate_row(row, self.registry)

    def test_duplicate_case_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tempdir:
            dataset = Path(tempdir) / 'duplicate.jsonl'
            dataset.write_text(''.join(json.dumps(x) + '\n' for x in [self.rows[0], self.rows[0]]), encoding='utf-8')
            with self.assertRaisesRegex(BenchmarkError, 'duplicate case ID'):
                load_benchmark(dataset)

    def test_scoring_only_consumes_external_adjudication(self):
        grades = [
            {'id': 'D01', 'rating': 3, 'notes': 'Recovered the complete intended claim.'},
            {'id': 'D02', 'rating': 1, 'notes': 'Only the desire topic remained.'},
        ]
        stats = score_rows(self.rows, grades)
        self.assertEqual(stats['rated_cases'], 2)
        self.assertEqual(stats['unrated_cases'], 34)
        self.assertEqual(stats['average_rating_over_rated_cases_only'], 2)
        self.assertEqual(stats['faithful_rating_3_over_rated_cases_only'], 0.5)

    def test_rating_bool_and_unknown_id_and_duplicate_are_rejected(self):
        with self.assertRaisesRegex(BenchmarkError, 'integer'):
            score_rows(self.rows, [{'id': 'D01', 'rating': True, 'notes': 'not valid'}])
        with self.assertRaisesRegex(BenchmarkError, 'unknown or duplicate'):
            score_rows(self.rows, [{'id': 'Z99', 'rating': 0, 'notes': 'unknown'}])
        good = {'id': 'D01', 'rating': 2, 'notes': 'valid'}
        with self.assertRaisesRegex(BenchmarkError, 'unknown or duplicate'):
            score_rows(self.rows, [good, good])

    def test_jsonl_roundtrip(self):
        with tempfile.TemporaryDirectory() as tempdir:
            dest = Path(tempdir) / 'packet.jsonl'
            packet = blind_rows(self.rows)
            dest.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in packet), encoding='utf-8')
            self.assertEqual(jsonl(dest), packet)


if __name__ == '__main__':
    unittest.main()
