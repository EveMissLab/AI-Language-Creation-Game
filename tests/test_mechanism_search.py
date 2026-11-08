"""v0.18 exhaustive bounded mechanism-completion and witness regression tests."""
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

import mechanism_search as lab
import causal_robustness as v17
from causal_lab import BooleanSCM

ROOT = Path(__file__).resolve().parents[1]


class MechanismCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.families = {f.family_id: f for f in v17.load_families()}
        cls.record = json.loads(lab.REPORT_PATH.read_text(encoding='utf-8'))
        cls.by_family = {x['family_id']: x for x in cls.record['families']}

    def test_frozen_sources_and_explicit_versioned_space(self):
        lab._guard_inputs()
        self.assertEqual(sha256(v17.FIXTURE.read_bytes()).hexdigest(), lab.FIXTURE_SHA256)
        self.assertEqual(sha256(v17.REPORT.read_bytes()).hexdigest(), lab.REPORT_V17_SHA256)
        self.assertEqual(lab.SPEC_PATH.read_text(encoding='utf-8'), lab.serialized_spec())
        self.assertEqual(lab.search_spec()['candidate_masks'], list(range(16)))

    def test_old_published_patterns_unchanged(self):
        self.assertEqual(sha256(v17.ACTIVE_PATTERNS.read_bytes()).hexdigest(), v17.ACTIVE_PATTERNS_SHA256)
        self.assertTrue(self.record['summary']['active_registry_changed'] is False)
        self.assertIsNone(self.record['summary']['empirical_causal_evidence'])
        self.assertIsNone(self.record['summary']['ai_comprehension_score'])

    def test_search_dimensions(self):
        summary=self.record['summary']
        self.assertEqual(summary['families'], 7)
        self.assertEqual(summary['original_models'], 21)
        self.assertEqual(summary['candidates_per_family'], 16)
        self.assertEqual(summary['candidate_models'], 112)
        self.assertEqual(summary['candidate_observation_evaluations'], 448)
        self.assertEqual(summary['candidate_intervention_evaluations'], 896)
        self.assertEqual(summary['families_with_nonvacuous_invariant'], 5)
        self.assertEqual(summary['nonvacuous_invariants_refuted_by_a_completion'], 5)
        self.assertEqual(summary['families_with_preexisting_noninvariance'], 2)

    def test_generated_models_are_valid_bounded_scms(self):
        for fam in self.families.values():
            for mask in range(16):
                with self.subTest(family=fam.family_id, mask=mask):
                    model = lab.construct(fam, mask)
                    self.assertIsInstance(model, BooleanSCM)
                    self.assertLessEqual(len(model.equations), 24)
                    self.assertEqual(model.exogenous, ('U', 'G'))
                    self.assertEqual(model.outcomes[lab.parse_cause(fam.expression)[1]], 'Y')
                    self.assertTrue(all(eq.op in {'copy', 'not','and','or','xor'} for eq in model.equations))

    def test_observational_equivalence_every_context(self):
        for fam in self.families.values():
            anchor = fam.models[0]
            for mask in range(16):
                new = lab.construct(fam, mask)
                for u, g in lab.CONTEXTS:
                    context = {'U':u, 'G':g}
                    with self.subTest(family=fam.family_id, mask=mask, context=context):
                        self.assertEqual(anchor.run(context)['SIGNAL'], u)
                        self.assertEqual(new.run(context)['SIGNAL'], u)
                        self.assertEqual(anchor.run(context)['Y'], new.run(context)['Y'])

    def test_all_sixteen_intervention_completions_are_distinct(self):
        for family in self.families.values():
            signatures = {lab._signature(lab._responses(lab.construct(family, mask), family))
                          for mask in range(16)}
            self.assertEqual(len(signatures), 16)

    def test_off_observation_truth_bit_matches_independent_xor_specification(self):
        # Independent direct evaluation of the declared four-bit completion formula.
        for family in self.families.values():
            anchor=family.models[0]
            for mask in range(16):
                model=lab.construct(family,mask)
                for index,(u,g) in enumerate(lab.CONTEXTS):
                    ctx={'U':u,'G':g}
                    base=anchor.run(ctx)['Y']
                    opposite=model.run(ctx,intervene={'SIGNAL':not u})['Y']
                    self.assertEqual(opposite, base ^ bool(mask & (1<<index)))
                    natural=model.run(ctx,intervene={'SIGNAL':u})['Y']
                    self.assertEqual(natural,base)

    def test_zero_mask_has_no_causal_effect_despite_possible_observed_association(self):
        for family in self.families.values():
            rows = lab._responses(lab.construct(family, 0), family)
            self.assertTrue(all(r['do_false_Y'] == r['do_true_Y'] for r in rows))

    def test_f17_direct_observationally_equivalent_but_no_intervention(self):
        fam = self.families['F17_DIRECT']
        before = v17._evaluate_family(fam)
        self.assertEqual(before['classification'], 'exact_intervention_response_invariant')
        new = lab.construct(fam, 0)
        for u, g in lab.CONTEXTS:
            ctx={'U':u,'G':g}
            self.assertEqual(new.run(ctx)['Y'], fam.models[0].run(ctx)['Y'])
            self.assertEqual(new.run(ctx,intervene={'SIGNAL':False})['Y'], u)
            self.assertEqual(new.run(ctx,intervene={'SIGNAL':True})['Y'], u)
        trial=self.by_family['F17_DIRECT']
        self.assertEqual(trial['first_refuting_mask'], 0)
        self.assertEqual(trial['first_refuting_witness']['candidate']['direction'], 'unchanged')
        self.assertEqual({x['direction'] for x in trial['first_refuting_witness']['original_models']}, {'positive'})

    def test_no_effect_family_gains_intervention_with_same_observations(self):
        fam=self.families['F17_NO_EFFECT']
        candidate=lab.construct(fam,1)
        context={'U':False,'G':False}
        self.assertEqual(candidate.run(context)['Y'],fam.models[0].run(context)['Y'])
        self.assertNotEqual(candidate.run(context,intervene={'SIGNAL':False})['Y'],
                            candidate.run(context,intervene={'SIGNAL':True})['Y'])
        self.assertEqual(self.by_family['F17_NO_EFFECT']['first_refuting_mask'],1)

    def test_families_without_original_invariant_are_not_false_refutations(self):
        for family_id in ('F17_POLARITY','F17_DISPUTED'):
            row=self.by_family[family_id]
            self.assertEqual(row['original_classification'],'no_common_nonzero_direction')
            self.assertIsNone(row['first_refuting_mask'])
            self.assertIsNone(row['first_refuting_witness'])
            self.assertTrue(all(not r['refutes_original_nonvacuous_invariant'] for r in row['candidates']))

    def test_all_positive_baseline_categories_have_reproducible_counterexample(self):
        refuted=[]
        for row in self.record['families']:
            if row['first_refuting_mask'] is None:
                continue
            refuted.append(row['family_id'])
            first=row['candidates'][row['first_refuting_mask']]
            self.assertTrue(first['refutes_original_nonvacuous_invariant'])
            self.assertEqual(first['first_violation'],row['first_refuting_witness'])
            witness=lab.replay(row['family_id'], first['mask'], first['first_violation']['context_index'])
            self.assertTrue(witness['observational_equivalence_to_anchor'])
            self.assertEqual(witness['new_model_response']['direction'],first['first_violation']['candidate']['direction'])
        self.assertEqual(len(refuted),5)

    def test_no_duplicate_output_and_no_context_leakage(self):
        for row in self.record['families']:
            self.assertEqual(len(row['candidates']),16)
            self.assertEqual([r['mask'] for r in row['candidates']],list(range(16)))
            self.assertEqual(row['unique_full_intervention_signatures'],16)
            self.assertTrue(all(r['observationally_identical_to_first_model'] for r in row['candidates']))
            self.assertTrue(all(1 <= r['structural_equations'] <= 24 for r in row['candidates']))

    def test_invalid_mask_types_and_values_rejected(self):
        fam=self.families['F17_DIRECT']
        for bad in (-1,16, 1.5, True, False, '0'):
            with self.subTest(bad=bad),self.assertRaises(lab.SearchError):
                lab.construct(fam,bad)

    def test_invalid_context_and_family_rejected(self):
        for args in [('F17_DIRECT',0,-1),('F17_DIRECT',0,4),('F17_DIRECT',0,True),
                     ('F17_UNKNOWN',0,0),('F17_DIRECT',16,0),('F17_DIRECT',False,0)]:
            with self.subTest(args=args), self.assertRaises(lab.SearchError):
                lab.replay(*args)

    def test_wrong_assumed_natural_source_detected(self):
        fam=self.families['F17_DIRECT']
        fake=deepcopy(fam)
        e=fake.models[0].equations
        wrong=e[0].__class__('SIGNAL','not',('U',))
        model=fake.models[0].__class__(fake.models[0].case_id,fake.models[0].mechanism,
                                      fake.models[0].exogenous,(wrong,)+e[1:],
                                      fake.models[0].outcomes,fake.models[0].note)
        alternate=fake.__class__(fake.family_id,fake.expression,fake.question,(model,)+fake.models[1:])
        with self.assertRaises(lab.SearchError):
            lab.construct(alternate,0)

    def test_read_receipt_mismatch_rejected(self):
        forged=deepcopy(self.record)
        forged['summary']['nonvacuous_invariants_refuted_by_a_completion']=0
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'forged.json'
            target.write_text(json.dumps(forged),encoding='utf-8')
            with patch.object(lab,'REPORT_PATH',target),self.assertRaises(lab.SearchError):
                lab.check_report()

    def test_tampered_spec_or_pin_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            spec=Path(d)/'space.json'
            spec.write_text(lab.serialized_spec()+' ',encoding='utf-8')
            with patch.object(lab,'SPEC_PATH',spec),self.assertRaises(lab.SearchError):
                lab.report()
        with patch.object(lab,'FIXTURE_SHA256','0'*64),self.assertRaises(lab.SearchError):
            lab.report()
        with patch.object(lab,'REPORT_V17_SHA256','0'*64),self.assertRaises(lab.SearchError):
            lab.report()

    def test_final_report_is_exact_recomputation(self):
        self.assertEqual(lab.report(),self.record)
        self.assertEqual(lab.check_report()['candidate_models_verified'],112)

    def test_cli_summary_replay_check_emit_space(self):
        cases=(['summary'],['replay','--family','F17_DIRECT','--mask','0','--context-index','0'],
               ['check'],['emit-space'])
        for args in cases:
            with self.subTest(args=args):
                proc=subprocess.run([sys.executable,'mechanism_search.py',*args],cwd=ROOT,
                                    text=True,capture_output=True,timeout=30)
                self.assertEqual(proc.returncode,0,proc.stderr)
                data=json.loads(proc.stdout)
                if args==['check']:
                    self.assertTrue(data['ok'])
                if args==['emit-space']:
                    self.assertEqual(data,lab.search_spec())
                if args==['replay']:
                    self.assertTrue(data['observational_equivalence_to_anchor'])


if __name__ == '__main__':
    unittest.main()
