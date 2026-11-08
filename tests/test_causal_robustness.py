"""ALCG v0.17 bounded cross-model invariance regression and failure checks."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import causal_robustness as robust
import family_fixtures_v017 as builder

ROOT = Path(__file__).resolve().parents[1]


class CrossModelEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = builder.build_fixture()
        cls.families = {f.family_id: f for f in robust.load_families()}
        cls.report = robust.report()
        cls.rows = {r['family_id']: r for r in cls.report['results']}

    def test_builder_is_reproducible_and_has_synthetic_provenance(self):
        self.assertEqual(builder.serialized_fixture(), robust.FIXTURE.read_text(encoding='utf-8'))
        self.assertIn('assistant-authored', self.fixture['provenance'])
        self.assertIn('not empirical', self.fixture['provenance'])

    def test_frozen_v016_and_published_patterns_are_pinned(self):
        robust._guard_inputs()
        for path, pinned in ((robust.LEGACY_FIXTURE, robust.LEGACY_FIXTURE_SHA256),
                             (robust.LEGACY_REPORT, robust.LEGACY_REPORT_SHA256),
                             (robust.ACTIVE_PATTERNS, robust.ACTIVE_PATTERNS_SHA256)):
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), pinned)

    def test_expected_exhaustive_dimensions(self):
        summary = self.report['summary']
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(summary['families'], 7)
        self.assertEqual(summary['models'], 21)
        self.assertEqual(summary['background_evaluations'], 84)
        self.assertEqual(summary['intervention_evaluations'], 168)
        self.assertEqual(summary['classification_counts'], {
            'exact_intervention_response_invariant': 1,
            'qualitative_direction_invariant_only': 3,
            'context_limited_direction_invariant': 1,
            'no_common_nonzero_direction': 2,
        })

    def test_no_claims_of_outside_world_or_independent_readers(self):
        summary = self.report['summary']
        self.assertIsNone(summary['empirical_causal_evidence'])
        self.assertIsNone(summary['ai_comprehension_score'])
        self.assertEqual(summary['independent_ai_readers'], 0)
        self.assertFalse(summary['active_registry_changed'])

    def test_direct_is_exact_even_when_dag_differs(self):
        row = self.rows['F17_DIRECT']
        self.assertTrue(row['exact_intervention_response_invariant'])
        self.assertEqual(row['classification'], 'exact_intervention_response_invariant')
        self.assertEqual(len(row['identical_intervention_value_contexts']), 4)
        self.assertEqual({x['direction'] for x in row['robust_nonzero_direction_contexts']}, {'positive'})
        self.assertIsNone(row['first_direction_disagreement'])
        self.assertIsNone(row['first_intervention_value_disagreement'])

    def test_gated_family_retains_direction_not_baseline(self):
        row = self.rows['F17_DIRECTION_ONLY']
        self.assertTrue(row['qualitative_direction_invariant'])
        self.assertFalse(row['exact_intervention_response_invariant'])
        self.assertEqual(row['classification'], 'qualitative_direction_invariant_only')
        self.assertEqual(len(row['robust_nonzero_direction_contexts']), 2)
        self.assertIsNone(row['first_direction_disagreement'])
        diff = row['first_intervention_value_disagreement']
        self.assertFalse(diff['context']['G'])
        self.assertEqual({(x['do_false'],x['do_true']) for x in diff['models']}, {(False,False),(True,True)})

    def test_context_family_is_only_robust_when_gate_is_true(self):
        row = self.rows['F17_CONTEXT']
        self.assertEqual(row['classification'], 'context_limited_direction_invariant')
        self.assertFalse(row['qualitative_direction_invariant'])
        self.assertEqual(len(row['robust_nonzero_direction_contexts']), 2)
        self.assertTrue(all(x['context']['G'] and x['direction'] == 'positive'
                            for x in row['robust_nonzero_direction_contexts']))
        self.assertFalse(row['first_direction_disagreement']['context']['G'])

    def test_polarity_cannot_be_converted_to_one_robust_sign(self):
        row = self.rows['F17_POLARITY']
        self.assertEqual(row['classification'], 'no_common_nonzero_direction')
        self.assertTrue(row['every_model_influential_in_some_context'])
        self.assertTrue(row['existential_influence_agreement'])
        self.assertFalse(row['qualitative_direction_invariant'])
        self.assertEqual(row['robust_nonzero_direction_contexts'], [])
        self.assertEqual({m['responses'][0]['direction'] for m in row['model_results']},
                         {'positive', 'negative'})

    def test_disputed_family_has_observational_confounding(self):
        row = self.rows['F17_DISPUTED']
        self.assertFalse(row['existential_influence_agreement'])
        self.assertFalse(row['every_model_influential_in_some_context'])
        self.assertEqual(row['classification'], 'no_common_nonzero_direction')
        proxy = next(m for m in row['model_results'] if m['mechanism'] == 'confounded_proxy')
        self.assertTrue(proxy['observational']['observational_association'])
        self.assertFalse(proxy['influence_in_some_context'])
        self.assertTrue(all(x['direction'] == 'unchanged' for x in proxy['responses']))

    def test_null_family_has_robust_absence_but_different_observations(self):
        row = self.rows['F17_NO_EFFECT']
        self.assertTrue(row['qualitative_direction_invariant'])
        self.assertFalse(row['exact_intervention_response_invariant'])
        self.assertFalse(row['every_model_influential_in_some_context'])
        self.assertTrue(row['existential_influence_agreement'])
        self.assertEqual(row['robust_nonzero_direction_contexts'], [])
        self.assertEqual({m['observational']['observational_association']
                          for m in row['model_results']}, {True, False})

    def test_negative_family_preserves_negative_direction_under_gate(self):
        row = self.rows['F17_NEGATIVE']
        self.assertTrue(row['qualitative_direction_invariant'])
        self.assertFalse(row['exact_intervention_response_invariant'])
        self.assertEqual(len(row['robust_nonzero_direction_contexts']), 2)
        self.assertEqual({x['direction'] for x in row['robust_nonzero_direction_contexts']}, {'negative'})
        self.assertTrue(all(x['context']['G'] for x in row['robust_nonzero_direction_contexts']))

    def test_each_reported_direction_matches_actual_do_values(self):
        for family in self.rows.values():
            for model in family['model_results']:
                for observed in model['responses']:
                    with self.subTest(model=model['case_id'],ctx=observed['context_index']):
                        a,b=observed['do_false_indicator'],observed['do_true_indicator']
                        expected='unchanged' if a==b else 'positive' if (not a and b) else 'negative'
                        self.assertEqual(observed['direction'], expected)

    def test_positive_and_negative_contexts_are_disjoint(self):
        for row in self.rows.values():
            sign_rows = row['consistent_direction_contexts']
            self.assertEqual(len({x['context_index'] for x in sign_rows}), len(sign_rows))
            self.assertTrue(all(x['direction']!='unchanged' for x in row['robust_nonzero_direction_contexts']))
            self.assertTrue(all(x in sign_rows for x in row['robust_nonzero_direction_contexts']))

    def test_saved_report_matches_recomputed_receipts(self):
        verified = robust.verify_report()
        self.assertTrue(verified['ok'])
        self.assertEqual(verified['families_verified'], 7)
        self.assertEqual(verified['model_contexts_replayed'], 84)

    def test_every_context_replays_all_three_models(self):
        for row in self.report['results']:
            for index in range(4):
                with self.subTest(family=row['family_id'],index=index):
                    view=robust.replay(row['family_id'],index,receipt=row)
                    self.assertEqual(len(view['individual_models']),3)
                    self.assertEqual(view['context'],row['model_results'][0]['responses'][index]['context'])
                    self.assertEqual(view['causal_truth_in_reality'],'not established')

    def test_replay_rejects_wrong_family_and_context(self):
        with self.assertRaises(robust.RobustnessError): robust.replay('F17_NOT_PRESENT',0)
        with self.assertRaises(robust.RobustnessError): robust.replay('F17_DIRECT',-1)
        with self.assertRaises(robust.RobustnessError): robust.replay('F17_DIRECT',4)
        with self.assertRaises(robust.RobustnessError): robust.replay('F17_DIRECT',True)

    def test_tampered_witness_receipt_is_rejected(self):
        fake=deepcopy(self.rows['F17_CONTEXT'])
        fake['model_results'][0]['responses'][0]['do_true_indicator']=True
        with self.assertRaises(robust.RobustnessError):
            robust.replay('F17_CONTEXT',0,receipt=fake)

    def test_tampered_report_file_is_rejected(self):
        altered=deepcopy(self.report)
        altered['summary']['models']=20
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'forged-report.json'
            path.write_text(json.dumps(altered),encoding='utf-8')
            with patch.object(robust,'REPORT',path):
                with self.assertRaises(robust.RobustnessError): robust.verify_report()

    def test_frozen_legacy_edit_is_rejected(self):
        with patch.object(robust,'LEGACY_REPORT_SHA256','0000'):
            with self.assertRaises(robust.RobustnessError): robust._guard_inputs()
        with patch.object(robust,'ACTIVE_PATTERNS_SHA256','0000'):
            with self.assertRaises(robust.RobustnessError): robust.report()

    def test_v017_fixture_edit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            altered=Path(tmp)/'fake.json'
            altered.write_text(robust.FIXTURE.read_text(encoding='utf-8')+' ',encoding='utf-8')
            with patch.object(robust,'FIXTURE',altered):
                with self.assertRaises(robust.RobustnessError): robust._guard_inputs()

    def test_reject_duplicate_family_id(self):
        fake=deepcopy(self.fixture)
        fake['families'].append(deepcopy(fake['families'][0]))
        self._invalid_fixture(fake)

    def test_reject_missing_family_model(self):
        fake=deepcopy(self.fixture)
        fake['families'][0]['models'] = fake['families'][0]['models'][:1]
        self._invalid_fixture(fake)

    def test_reject_misaligned_background_order(self):
        fake=deepcopy(self.fixture)
        fake['families'][0]['models'][1]['exogenous']=['G','U']
        self._invalid_fixture(fake)

    def test_reject_outcome_indicator_incomparable(self):
        fake=deepcopy(self.fixture)
        row=fake['families'][0]['models'][1]
        row['equations'].append({'name':'OTHER','op':'copy','args':['Y']})
        row['outcomes'][0]['indicator']='OTHER'
        self._invalid_fixture(fake)

    def test_reject_missing_source_mapping(self):
        fake=deepcopy(self.fixture)
        fake['families'][0]['expression']=fake['families'][0]['expression'].replace('source=SIGNAL','source=UNKNOWN')
        self._invalid_fixture(fake)

    def test_reject_duplicate_structural_equations_disguised_as_new_model(self):
        fake=deepcopy(self.fixture)
        fake['families'][0]['models'][1]['equations']=deepcopy(fake['families'][0]['models'][0]['equations'])
        self._invalid_fixture(fake)

    def test_reject_cyclic_equations(self):
        fake=deepcopy(self.fixture)
        fake['families'][0]['models'][0]['equations'][0]['args']=['Y']
        self._invalid_fixture(fake)

    def test_reject_undeclared_real_world_source(self):
        fake=deepcopy(self.fixture)
        fake['provenance']='empirically verified causal truth'
        self._invalid_fixture(fake)

    def test_reject_nontyped_cause(self):
        fake=deepcopy(self.fixture)
        fake['families'][0]['expression']='IS(subject=SIGNAL,property=RELIABILITY)'
        self._invalid_fixture(fake)

    def test_cli_summary_and_replay_and_check(self):
        for args in (['summary'],['replay','--family','F17_CONTEXT','--context-index','1'],['check']):
            proc=subprocess.run([sys.executable,'causal_robustness.py',*args],cwd=ROOT,
                                capture_output=True,text=True,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stderr)
            data=json.loads(proc.stdout)
            if args==['summary']:
                self.assertEqual(data['families'],7)
            if args[0]=='replay':
                self.assertTrue(data['context']['G'])
            if args==['check']:
                self.assertTrue(data['ok'])

    def _invalid_fixture(self,data: dict) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'invalid.json'
            path.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(robust.RobustnessError):
                robust.load_families(path)


if __name__=='__main__':
    unittest.main()
