"""ALCG v0.16: finite, stipulated SCM semantics and fail-closed audit tests."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import causal_lab as causal

ROOT = Path(__file__).resolve().parents[1]


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(causal.FIXTURE.read_text(encoding='utf-8'))
        cls.models = causal.load_models()
        cls.report = causal.report()

    def test_all_eight_scenarios(self):
        self.assertEqual(len(self.models), 8)
        self.assertEqual(len(self.report['observational_vs_intervention']), 8)
        self.assertEqual(self.report['scenarios'], 8)

    def test_frozen_inputs_unchanged(self):
        causal._guard_sources()
        self.assertEqual(self.report['frozen_active_patterns_sha256'], causal.ACTIVE_SHA256)
        self.assertEqual(self.report['frozen_v014_sha256'], causal.SOURCE_SHA256)
        self.assertEqual(self.report['frozen_v015_report_sha256'], causal.V15_REPORT_SHA256)

    def test_full_report_recomputes_from_fixtures(self):
        result = causal.verify_report()
        self.assertTrue(result['report_matches'])
        self.assertEqual(result['checked'], 24)
        self.assertGreater(result['witness_receipts_replayed'], 0)

    def test_statuses_are_disjoint_and_exhaustive(self):
        self.assertEqual(self.report['status_counts'], {
            'canonical_equivalent_same_scm': 8,
            'intervention_difference_in_stipulated_scm': 7,
            'not_separated_in_stipulated_scm': 1,
            'outside_typed_causal_subset': 8,
        })
        self.assertEqual(sum(self.report['status_counts'].values()), 24)
        self.assertIsNone(self.report['ai_comprehension_score'])
        self.assertIsNone(self.report['empirical_causal_evidence'])
        self.assertFalse(self.report['active_registry_changed'])

    def test_every_scenario_exactly_three_variants(self):
        for ident in self.models:
            with self.subTest(ident=ident):
                matching = [r for r in self.report['results'] if r['case_id'] == ident]
                self.assertEqual(len(matching), 3)
                self.assertEqual({r['variant'] for r in matching},
                    {'named_argument_reorder', 'lexical_slot_change', 'operator_or_coreference_change'})

    def test_reversed_argument_order_not_a_new_semantic(self):
        for r in self.report['results']:
            if r['variant'] == 'named_argument_reorder':
                with self.subTest(id=r['case_id']):
                    self.assertEqual(r['status'], 'canonical_equivalent_same_scm')
                    self.assertEqual(r['original'], r['alternate'])

    def test_bad_IS_effect_is_not_called_false_cause(self):
        for r in self.report['results']:
            if r['variant'] == 'operator_or_coreference_change':
                with self.subTest(id=r['case_id']):
                    self.assertEqual(r['status'], 'outside_typed_causal_subset')
                    self.assertIsNone(r['alternate'])
                    self.assertIn('CHANGE', r['reason'])

    def test_two_observationally_indistinguishable_sources(self):
        model = self.models['G14_CAUSE_01']
        for ctx in model.contexts():
            values = model.run(ctx)
            self.assertEqual(values['PRESSURE_CHANGE'], values['VIBRATION'])
        self.assertTrue(self.report['observational_vs_intervention'][0]['observational']['observational_association'])

    def test_influence_despite_observationally_zero_marginal_association(self):
        case = self.report['observational_vs_intervention'][6]
        self.assertEqual(case['case_id'], 'G14_CAUSE_07')
        self.assertFalse(case['observational']['observational_association'])
        self.assertEqual(case['observational']['observed_rates'], {'false':'1/2','true':'1/2'})
        self.assertTrue(case['original_influence_in_some_context'])

    def test_observation_correlation_without_influence(self):
        case = self.report['observational_vs_intervention'][5]
        self.assertEqual(case['case_id'], 'G14_CAUSE_06')
        self.assertTrue(case['observational']['observational_association'])
        self.assertFalse(case['original_influence_in_some_context'])
        row = next(r for r in self.report['results'] if r['case_id'] == case['case_id']
                   and r['variant'] == 'lexical_slot_change')
        self.assertEqual(row['status'], 'not_separated_in_stipulated_scm')
        self.assertFalse(row['alternate']['influence_in_some_context'])

    def test_foil_cause_instead_of_original(self):
        row = next(r for r in self.report['results'] if r['case_id'] == 'G14_CAUSE_08'
                   and r['variant'] == 'lexical_slot_change')
        self.assertEqual(row['status'], 'intervention_difference_in_stipulated_scm')
        self.assertFalse(row['original']['influence_in_some_context'])
        self.assertTrue(row['alternate']['influence_in_some_context'])
        self.assertEqual(causal.replay(row['case_id'], row['variant'], side='alternate')['model_only'], True)

    def test_gated_intervention_requires_G_true(self):
        model = self.models['G14_CAUSE_01']
        output = model.outcomes[('FILTRATION_SYSTEM','THERMAL_STABILITY')]
        for u in (False, True):
            for gate in (False, True):
                low = model.run({'U':u,'G':gate}, intervene={'PRESSURE_CHANGE':False})
                high = model.run({'U':u,'G':gate}, intervene={'PRESSURE_CHANGE':True})
                self.assertEqual(low[output] != high[output], gate)

    def test_mediated_effect(self):
        model = self.models['G14_CAUSE_03']
        ctx = {'U':False,'G':False}
        low = model.run(ctx,intervene={'HEAT_CYCLE':False})
        high = model.run(ctx,intervene={'HEAT_CYCLE':True})
        self.assertFalse(low['M'])
        self.assertTrue(high['M'])
        self.assertNotEqual(low['Y'],high['Y'])

    def test_inhibitory_effect(self):
        model = self.models['G14_CAUSE_05']
        low = model.run({'U':False,'G':False},intervene={'POWER_FLUCTUATION':False})
        high = model.run({'U':False,'G':False},intervene={'POWER_FLUCTUATION':True})
        self.assertTrue(low['Y'])
        self.assertFalse(high['Y'])

    def test_intervention_severs_parent_equation(self):
        model = self.models['G14_CAUSE_02']
        ctx = {'U':True,'G':True}
        self.assertTrue(model.run(ctx)['FREQUENCY_SHIFT'])
        self.assertFalse(model.run(ctx,intervene={'FREQUENCY_SHIFT':False})['FREQUENCY_SHIFT'])

    def test_full_enumeration_four_background_assignments(self):
        for model in self.models.values():
            with self.subTest(id=model.case_id):
                self.assertEqual(len(list(model.contexts())), 4)

    def test_receipts_replay(self):
        for row in self.report['results']:
            for side in ('original', 'alternate'):
                receipt = row[side]
                if receipt is not None and receipt['witness']:
                    with self.subTest(case=row['case_id'],variant=row['variant'],side=side):
                        result = causal.replay(row['case_id'],row['variant'],side=side)
                        self.assertNotEqual(result['do_source_false'], result['do_source_true'])

    def test_altered_receipt_is_rejected(self):
        forged = deepcopy(self.report)
        target = next(r for r in forged['results'] if r['case_id']=='G14_CAUSE_01' and r['variant']=='lexical_slot_change')
        target['original']['witness']['do_source_true'] = False
        with self.assertRaises(causal.CausalError):
            causal.replay('G14_CAUSE_01','lexical_slot_change',result=forged)

    def test_replay_wrong_side_has_no_witness(self):
        with self.assertRaises(causal.CausalError):
            causal.replay('G14_CAUSE_01','lexical_slot_change',side='alternate')

    def test_no_fake_causal_truth_from_unmapped_effect(self):
        model=self.models['G14_CAUSE_01']
        with self.assertRaises(causal.CausalError):
            model.influence('CAUSE(source=PRESSURE_CHANGE,effect=CHANGE(subject=EARTH,property=WARM))')

    def test_source_not_in_model_fails(self):
        model=self.models['G14_CAUSE_01']
        with self.assertRaises(causal.CausalError):
            model.influence('CAUSE(source=UNDECLARED,effect=CHANGE(subject=FILTRATION_SYSTEM,property=THERMAL_STABILITY))')

    def test_unsupported_CAUSE_shape_fails(self):
        expressions = [
            'CAUSE(source=HEAT,effect=IS(subject=WATER,property=HOT))',
            'CAUSE(source=HEAT,effect=CHANGE(subject=WATER))',
            'CAUSE(source=HEAT,effect=CHANGE(subject="WATER",property=HOT))',
            'CAUSE(source=HEAT,effect=CHANGE(subject=WATER,property=HOT),extra=AI)',
            'IS(subject=HEAT,property=HOT)',
        ]
        for expr in expressions:
            with self.subTest(expr=expr),self.assertRaises(causal.CausalError):
                causal.parse_cause(expr)

    def test_strict_boolean_values(self):
        model=self.models['G14_CAUSE_01']
        for context in ({'U':1,'G':False},{'U':False},{'U':False,'G':False,'X':True}):
            with self.subTest(context=context),self.assertRaises(causal.CausalError):
                model.run(context)
        with self.assertRaises(causal.CausalError):
            model.run({'U':False,'G':False},intervene={'PRESSURE_CHANGE':1})
        with self.assertRaises(causal.CausalError):
            model.run({'U':False,'G':False},intervene={'U':True})

    def test_reject_duplicate_exogenous(self):
        row=deepcopy(self.data['scenarios'][0]);row['exogenous']=['U','U']
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_unhashable_exogenous(self):
        row=deepcopy(self.data['scenarios'][0]);row['exogenous']=['U',{}]
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_cycle_or_forward_reference(self):
        row=deepcopy(self.data['scenarios'][0]);row['equations'][0]['args']=['Y']
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_unknown_equation_operator_and_arity(self):
        row=deepcopy(self.data['scenarios'][0]);row['equations'][0]['op']='python'
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)
        row=deepcopy(self.data['scenarios'][0]);row['equations'][0]['args']=['U','G']
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_malicious_operator_type(self):
        row=deepcopy(self.data['scenarios'][0]);row['equations'][0]['op']=[]
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_outcome_mapping_to_exogenous(self):
        row=deepcopy(self.data['scenarios'][0]);row['outcomes'][0]['indicator']='U'
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_duplicate_outcome_mapping(self):
        row=deepcopy(self.data['scenarios'][0]);row['outcomes'].append(deepcopy(row['outcomes'][0]))
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_reject_unknown_or_extra_schema_fields(self):
        row=deepcopy(self.data['scenarios'][0]);row['arbitrary_code']='print(1)'
        with self.assertRaises(causal.CausalError): causal.BooleanSCM.from_data(row)

    def test_tampered_pinned_registry_fails(self):
        with tempfile.TemporaryDirectory() as d:
            alt=Path(d)/'patterns.json'
            alt.write_text('{}',encoding='utf-8')
            with patch.object(causal,'ACTIVE_PATTERNS',alt):
                with self.assertRaises(causal.CausalError): causal._guard_sources()

    def test_invalid_json_fixture_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json'
            p.write_text('{broken}',encoding='utf-8')
            with self.assertRaises(causal.CausalError): causal.load_models(p)

    def test_report_fixture_not_internally_self_certifying(self):
        # A manually changed fixture must not silently pass the pinned report.
        modified=deepcopy(self.data)
        modified['scenarios'][0]['equations'][-1]['op']='or'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'alternative.json'
            p.write_text(json.dumps(modified),encoding='utf-8')
            alternative=causal.load_models(p)
            self.assertNotEqual(alternative['G14_CAUSE_01'].influence(
                'CAUSE(source=PRESSURE_CHANGE,effect=CHANGE(subject=FILTRATION_SYSTEM,property=THERMAL_STABILITY))')['witness'],
                self.models['G14_CAUSE_01'].influence(
                'CAUSE(source=PRESSURE_CHANGE,effect=CHANGE(subject=FILTRATION_SYSTEM,property=THERMAL_STABILITY))')['witness'])


if __name__ == '__main__':
    unittest.main()
