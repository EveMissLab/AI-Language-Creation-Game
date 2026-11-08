"""v0.6 coverage benchmark, polysemy label and blind-packet regressions."""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alcg import parse
from coverage_lab import BenchmarkError, load_benchmark
from sense_coverage import (
    NEW, OLD, REGISTRY, SENSES, blind_packet, inspect_benchmark,
    report, validate_senses,
)


class SenseCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = validate_senses()
        cls.old = load_benchmark(OLD, REGISTRY)
        cls.new = load_benchmark(NEW, REGISTRY)

    def test_frozen_baseline_and_counts(self):
        result = report()
        self.assertEqual(result['baseline']['cases'], 36)
        self.assertEqual(result['new_curated_cases'], 48)
        self.assertEqual(result['combined_curated_cases'], 84)
        self.assertEqual(result['proposal_labels'], {'candidate': 36, 'partial': 6, 'raw': 6})

    def test_polysemy_eight_surfaces_seventeen_senses(self):
        result = report()
        self.assertEqual(result['ambiguous_english_surfaces_reviewed'], 8)
        self.assertEqual(result['disambiguated_sense_ids'], 17)
        self.assertEqual(result['sense_ids_represented_in_cases'], 17)

    def test_no_reader_claim_or_general_english_coverage(self):
        result = report()
        self.assertIsNone(result['independent_ai_reader_score'])
        self.assertIsNone(result['wordnet_or_general_english_coverage'])

    def test_no_relation_registry_expansion(self):
        self.assertEqual(report()['additional_relation_operators_introduced'], 0)

    def test_freeze_source_duplicate_rejected(self):
        altered = copy.deepcopy(self.new)
        altered[0]['english'] = self.old[0]['english']
        with self.assertRaisesRegex(BenchmarkError, 'duplicates'):
            inspect_benchmark(altered, self.entries, self.old)

    def test_bare_polysemous_atom_rejected(self):
        altered = copy.deepcopy(self.new)
        altered[0]['expression'] = 'HAS(owner=BANK, item=MONEY)'
        with self.assertRaisesRegex(BenchmarkError, 'ambiguous bare'):
            inspect_benchmark(altered, self.entries, self.old)

    def test_mislabelled_domain_rejected(self):
        altered = copy.deepcopy(self.new)
        altered[0]['domain'] = 'science'
        with self.assertRaises(BenchmarkError):
            inspect_benchmark(altered, self.entries, self.old)

    def test_registry_rejects_duplicate_sense(self):
        data = json.loads(SENSES.read_text(encoding='utf-8'))
        data['entries'].append(dict(data['entries'][0]))
        with TemporaryDirectory() as folder:
            target = Path(folder)/'senses.json'
            target.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(BenchmarkError, 'duplicate'):
                validate_senses(target)

    def test_registry_rejects_singleton_surface(self):
        data = json.loads(SENSES.read_text(encoding='utf-8'))
        data['entries'] = [d for d in data['entries'] if d['sense_id'] != 'BANK_RIVER']
        with TemporaryDirectory() as folder:
            target = Path(folder)/'senses.json'
            target.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(BenchmarkError, 'two distinct'):
                validate_senses(target)

    def test_registry_rejects_wrong_surface_prefix(self):
        data = json.loads(SENSES.read_text(encoding='utf-8'))
        data['entries'][0]['sense_id'] = 'RIVER_FINANCIAL'
        with TemporaryDirectory() as folder:
            target = Path(folder)/'senses.json'
            target.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(BenchmarkError, 'prefix'):
                validate_senses(target)

    def test_all_new_cases_syntactically_roundtrip(self):
        from alcg import render
        for row in self.new:
            with self.subTest(row=row['id']):
                self.assertEqual(parse(render(parse(row['expression']))), parse(row['expression']))

    def test_blind_packets_no_english_target_or_adjudication(self):
        for condition in ['unaided','glossary']:
            with self.subTest(condition=condition):
                packet = blind_packet(self.new, self.entries, condition)
                self.assertEqual(len(packet), 36)
                expected = [row for row in self.new if row["hypothesis"] == "candidate"]
                for original, task in zip(expected, packet):
                    self.assertEqual(original['id'], task['id'])
                    self.assertEqual(original['expression'], task['expression'])
                    self.assertNotIn('english', task)
                    self.assertNotIn('hypothesis', task)
                    self.assertNotIn('gap', task)
                    self.assertNotIn(original['english'], json.dumps(task))
                    if condition == 'unaided':
                        self.assertEqual(set(task), {'id', 'expression'})
                    else:
                        self.assertEqual(set(task), {'id', 'expression', 'sense_glossary'})

    def test_one_glossary_specific_to_used_sense_ids(self):
        rows = self.new
        packet = blind_packet(rows, self.entries, 'glossary')
        bank = next(x for x in packet if x['id'] == 'D102')
        self.assertEqual(set(bank['sense_glossary']), {'BANK_RIVER'})
        self.assertNotIn('BANK_FINANCIAL', bank['sense_glossary'])
        self.assertFalse(any(t['id']=='D108' for t in packet))

    def test_unknown_condition_rejected(self):
        with self.assertRaises(BenchmarkError):
            blind_packet(self.new, self.entries, 'expose-target')


if __name__ == '__main__':
    unittest.main()
