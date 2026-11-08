"""Generated and adversarially mutated v0.14 syntax fixtures (no AI readers)."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alcg import parse
from compact_surface import check_cases, locked_patterns
from coverage_lab import jsonl
from pattern_lab import PATTERNS, sha256
from semantic_lab import normalize
from challenge_generator import (
    LEXICON, SUITE, REPORT, REGISTRY_SHA,
    GenerationError, read_lexicon, validate_lexicon, _old_nontraining_forms,
    _read_candidate_patterns, apply_pattern, generate, validate, verify, report, main,
)


class ChallengeGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = generate()
        cls.result = validate(cls.rows)
        cls.patterns, cls.active = _read_candidate_patterns()
        cls.by_name = {p.name: p for p in cls.patterns}

    def test_all_existing_benchmarks_untouched(self):
        self.assertEqual(sha256(PATTERNS), REGISTRY_SHA)
        self.assertEqual(len(locked_patterns()), 16)
        self.assertEqual(check_cases()['exact_expanded_canonical_roundtrips'], 24)

    def test_exact_provenance_and_no_ai_scores(self):
        self.assertEqual(self.result['independent_ai_readers'], 0)
        self.assertIsNone(self.result['semantic_comprehension_score'])
        self.assertIsNone(self.result['actual_english_coverage_gain'])
        self.assertEqual(self.result['promoted_patterns'], 0)
        self.assertIn('NOT independent generalization', self.result['warning'])
        self.assertTrue(all('human_curated' in row['provenance'] for row in self.rows))

    def test_32_cases_across_four_frozen_candidate_patterns(self):
        self.assertEqual(len(self.rows), 32)
        for root in ('BEFORE', 'CAUSE', 'EXISTS', 'NOT'):
            self.assertEqual(sum(row['root'] == root for row in self.rows), 8)
        self.assertEqual(len({row['id'] for row in self.rows}), 32)

    def test_104_generated_variants_and_expected_classes(self):
        self.assertEqual(self.result['metamorphic_variants_checked'], 104)
        self.assertEqual(self.result['variant_classes'], {
            'equivalent_reordering': 32,
            'equivalent_alpha_rename': 8,
            'same_shape_but_canonical_changed': 32,
            'non_matching_structural_controls': 32,
        })

    def test_all_positive_expressions_new_relative_to_frozen_training_and_old_trials(self):
        frozen = _old_nontraining_forms()
        positive = {normalize(row['expression']) for row in self.rows}
        self.assertEqual(len(positive), len(self.rows))
        self.assertFalse(positive & frozen)

    def test_mutated_non_equivalent_ast_are_new_and_unique(self):
        frozen = _old_nontraining_forms()
        seen = {normalize(row['expression']) for row in self.rows}
        for row in self.rows:
            for variant in row['variants']:
                if not variant['canonical_equal']:
                    canonical = normalize(variant['expression'])
                    self.assertNotIn(canonical, frozen)
                    self.assertNotIn(canonical, seen)
                    seen.add(canonical)
        self.assertEqual(len(seen), 96)

    def test_canonical_equivalence_is_not_literal_identity(self):
        for row in self.rows:
            a = normalize(row['expression'])
            for variant in row['variants']:
                actual = normalize(variant['expression'])
                self.assertEqual(a == actual, variant['canonical_equal'])
                self.assertEqual(apply_pattern(variant['expression'],
                                self.by_name[row['pattern']], self.active) is not None,
                                 variant['matches_candidate'])

    def test_same_shape_change_not_mislabeled_semantic_success(self):
        changed = [v for row in self.rows for v in row['variants']
                   if v['type'] == 'lexical_slot_change']
        self.assertEqual(len(changed), 32)
        self.assertTrue(all(v['matches_candidate'] and not v['canonical_equal'] for v in changed))
        self.assertIsNone(self.result['semantic_comprehension_score'])

    def test_quantifier_bound_var_alpha_invariance(self):
        for row in self.rows:
            if row['root'] == 'EXISTS':
                alpha = next(v for v in row['variants'] if v['type'] == 'bound_variable_alpha_rename')
                self.assertEqual(normalize(alpha['expression']), normalize(row['expression']))
                self.assertTrue(alpha['matches_candidate'])

    def test_generator_is_deterministic(self):
        self.assertEqual(generate(), self.rows)

    def test_different_seed_changes_generated_sample_not_published_rules(self):
        lexicon = read_lexicon()
        alt = copy.deepcopy(lexicon)
        alt['seed'] += 1
        fresh = generate(alt)
        self.assertEqual(len(fresh), len(self.rows))
        self.assertNotEqual([x['expression'] for x in fresh],
                            [x['expression'] for x in self.rows])
        self.assertEqual(sha256(PATTERNS), REGISTRY_SHA)

    def test_lexicon_unknown_field_fails_closed(self):
        altered = copy.deepcopy(read_lexicon())
        altered['unrecognized_setting'] = True
        with self.assertRaisesRegex(GenerationError, 'schema'):
            generate(altered)

    def test_lexicon_invalid_identifier_rejected(self):
        altered = copy.deepcopy(read_lexicon())
        altered['banks']['CAUSE']['item_01'][0] = 'INVALID TERM WITH SPACES'
        with self.assertRaisesRegex(GenerationError, 'identifiers'):
            generate(altered)

    def test_lexicon_invalid_duplicate_labels_rejected(self):
        altered = copy.deepcopy(read_lexicon())
        altered['banks']['BEFORE']['item_01'][1] = altered['banks']['BEFORE']['item_01'][0]
        with self.assertRaisesRegex(GenerationError, 'distinct'):
            generate(altered)

    def test_lexicon_wrong_slot_rejected(self):
        altered = copy.deepcopy(read_lexicon())
        del altered['banks']['EXISTS']['item_04']
        with self.assertRaisesRegex(GenerationError, 'missing/extra'):
            generate(altered)

    def test_tampered_generated_classification_is_rejected(self):
        altered = copy.deepcopy(self.rows)
        altered[0]['variants'][1]['canonical_equal'] = True
        with self.assertRaisesRegex(GenerationError, 'changed'):
            validate(altered)

    def test_tampered_positive_expression_is_rejected(self):
        altered = copy.deepcopy(self.rows)
        altered[0]['expression'] = 'IS(subject=WATER, property=LIQUID)'
        with self.assertRaisesRegex(GenerationError, 'changed'):
            validate(altered)

    def test_historical_digest_mutation_refused(self):
        with patch('challenge_generator.HISTORICAL_PIN', {'benchmarks/contrast-v0.3.jsonl': '0'*64}):
            with self.assertRaisesRegex(GenerationError, 'historical contrast changed'):
                generate()

    def test_manifest_matches_recomputed_and_cli_check_succeeds(self):
        self.assertEqual(verify(), self.result)
        self.assertEqual(json.loads(REPORT.read_text(encoding='utf-8')), self.result)
        self.assertEqual(jsonl(SUITE), self.rows)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['check']), 0)
        self.assertIn('104 metamorphic checks', out.getvalue())

    def test_generate_cli_to_temporary_file(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'questions.jsonl'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['generate', '--out', str(dest)]), 0)
            self.assertEqual(jsonl(dest), self.rows)

    def test_generate_cli_does_not_overwrite_existing_different_file(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'work.jsonl'
            dest.write_text('keep me\n', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['generate', '--out', str(dest)]), 1)
            self.assertEqual(dest.read_text(), 'keep me\n')

    def test_generate_cli_does_not_overwrite_repository_artifact(self):
        old = REPORT.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['generate', '--out', str(REPORT)]), 1)
        self.assertEqual(REPORT.read_bytes(), old)

    def test_cli_report_disclaims_semantic_understanding(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['report']), 0)
        rendered = json.loads(out.getvalue())
        self.assertEqual(rendered['independent_ai_readers'], 0)
        self.assertIsNone(rendered['semantic_comprehension_score'])


if __name__ == '__main__':
    unittest.main()
