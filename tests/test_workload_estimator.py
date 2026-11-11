"""v0.30: measured-event format, prefix-only forecast and safe actual reader."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch
import json
import unittest

import workload_estimator as w
import measured_replay as v27
import checkpoint_planner as v26
import trusted_cache as v28


class WorkloadFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = w.read_fixture()
        cls.row = w.measurement_rows()['selective']

    def stream(self, key='stable'):
        return next(x for x in self.fixture['scenarios'] if x['label'] == key)

    def test_exact_fixture_cases(self):
        self.assertEqual(len(self.fixture['scenarios']), 4)
        self.assertEqual([len(x['events']) for x in self.fixture['scenarios']], [96]*4)
        for case in self.fixture['scenarios']:
            w.validate_document(case)
            self.assertEqual(case['origin'], 'synthetic-fixture')

    def test_source_and_private_info_not_exported(self):
        stream = self.stream()
        self.assertNotIn('source', json.dumps(stream))
        self.assertNotIn('session_id', json.dumps(stream))
        self.assertNotIn('source_sha256', json.dumps(stream))

    def test_bad_top_level_rejected(self):
        row = deepcopy(self.stream())
        row['extra'] = 'something'
        with self.assertRaises(w.WorkloadError): w.validate_document(row)

    def test_wrong_checksum_rejected(self):
        row = deepcopy(self.stream())
        row['events'][0]['route'] = 'cache'
        with self.assertRaises(w.WorkloadError): w.validate_document(row)

    def test_unknown_event_fields_rejected_even_with_valid_digest(self):
        row = deepcopy(self.stream())
        row['events'][0]['plaintext'] = 'secret'
        row['receipt_sha256'] = w._sha(w._canonical({k:v for k,v in row.items() if k != 'receipt_sha256'}))
        with self.assertRaises(w.WorkloadError): w.validate_document(row)

    def test_first_read_cannot_be_revision_changed(self):
        row = deepcopy(self.stream())
        first = next(x for x in row['events'] if x['kind']=='read')
        first['revision_changed'] = True
        row['receipt_sha256'] = w._sha(w._canonical({k:v for k,v in row.items() if k != 'receipt_sha256'}))
        with self.assertRaisesRegex(w.WorkloadError, 'first observed'):
            w.validate_document(row)

    def test_tick_contiguity_required(self):
        row = deepcopy(self.stream())
        row['events'][4]['tick'] = 100
        row['receipt_sha256'] = w._sha(w._canonical({k:v for k,v in row.items() if k != 'receipt_sha256'}))
        with self.assertRaises(w.WorkloadError): w.validate_document(row)

    def test_no_idle_extra_fields(self):
        row = deepcopy(self.stream())
        idle = next(e for e in row['events'] if e['kind']=='idle')
        idle['revision_changed'] = False
        row['receipt_sha256'] = w._sha(w._canonical({k:v for k,v in row.items() if k != 'receipt_sha256'}))
        with self.assertRaises(w.WorkloadError): w.validate_document(row)

    def test_bad_event_route(self):
        row = deepcopy(self.stream())
        next(e for e in row['events'] if e['kind']=='read')['route'] = 'trusted-no-verify'
        row['receipt_sha256'] = w._sha(w._canonical({k:v for k,v in row.items() if k != 'receipt_sha256'}))
        with self.assertRaises(w.WorkloadError): w.validate_document(row)

    def test_unsupported_origin_rejected(self):
        with self.assertRaises(w.WorkloadError): w.document('test', 'from-production', [])

    def test_label_is_anonymous_ascii(self):
        for label in ('../secret', '讀取', 'x/y', '', 'a'*60):
            with self.subTest(label=label), self.assertRaises(w.WorkloadError):
                w.document(label,'synthetic-fixture',[])

    def test_max_event_bounds(self):
        with self.assertRaises(w.WorkloadError):
            w.document('long','synthetic-fixture', [{'tick':i,'kind':'idle'} for i in range(w.MAX_EVENTS+1)])

    def test_integer_window_and_horizon_bounds(self):
        for option in [{'at_tick':True}, {'at_tick':-1},{'window':True}, {'window':2}, {'horizon':0}]:
            with self.subTest(option=option), self.assertRaises(w.WorkloadError):
                w.forecast(self.stream(),32,row=self.row,**option) if 'at_tick' not in option else w.forecast(self.stream(),option['at_tick'],row=self.row)

    def test_report_is_reconstructable(self):
        report = json.loads(w.REPORT_PATH.read_text('utf-8'))
        self.assertTrue(w.verify_report(report))
        self.assertEqual(len(report['cases']),16)

    def test_report_tamper_rejected(self):
        report = w.report()
        report['cases'][2]['selection'] = 'fake'
        with self.assertRaises(w.WorkloadError):w.verify_report(report)


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = {x['label']:x for x in w.read_fixture()['scenarios']}
        cls.row = w.measurement_rows()['selective']

    def f(self,name,at=96):
        return w.forecast(self.fixture[name],at,row=self.row)

    def test_initial_no_evidence_fails_closed(self):
        self.assertEqual(self.f('stable',0)['selection'],'direct')

    def test_early_stable_needs_full_window(self):
        self.assertEqual(self.f('stable',16)['selection'],'direct')

    def test_sparse_reads_are_insufficient(self):
        self.assertEqual(self.f('sparse')['selection'],'direct')

    def test_stable_change_to_cache_after_observation(self):
        self.assertEqual(self.f('stable',32)['selection'],'direct')
        self.assertEqual(self.f('stable',64)['selection'],'cache')
        self.assertEqual(self.f('stable',96)['selection'],'cache')

    def test_churn_prefers_direct(self):
        self.assertEqual(self.f('churn',64)['selection'],'direct')

    def test_drift_reverts_from_cache_to_direct(self):
        self.assertEqual(self.f('drift',64)['selection'],'cache')
        self.assertEqual(self.f('drift',96)['selection'],'direct')

    def test_source_changes_are_not_assumed_zero(self):
        x=self.f('stable')
        self.assertGreater(x['forecast']['invalidation_per_million'],0)

    def test_forecast_does_not_see_future_events(self):
        original=self.fixture['drift']
        altered=deepcopy(original)
        for e in altered['events'][64:]:
            if e['kind']=='read':e['revision_changed'] = False
        altered['receipt_sha256']=w._sha(w._canonical({k:v for k,v in altered.items() if k!='receipt_sha256'}))
        self.assertEqual(w.forecast(original,64,row=self.row),w.forecast(altered,64,row=self.row))
        self.assertNotEqual(w.forecast(original,96,row=self.row)['forecast'],w.forecast(altered,96,row=self.row)['forecast'])

    def test_unique_prefix_receipt(self):
        a=self.f('stable',64)
        b=self.f('stable',96)
        self.assertNotEqual(a['prefix_sha256'],b['prefix_sha256'])

    def test_observations_match_rolling_window(self):
        a=self.f('drift',96)
        self.assertEqual((a['window_opportunities'],a['observed_reads'],a['observed_read_gaps'],a['observed_revision_changes']),(32,32,31,15))

    def test_forecast_value_bounded_by_v29(self):
        a=w.forecast(self.fixture['stable'],96,row=self.row,horizon=4096)
        self.assertLessEqual(a['forecast']['expected_reads'],w.v29.MAX_READS)

    def test_unknown_measurement_not_silent(self):
        with self.assertRaises((w.WorkloadError,w.v29.AdaptiveError)):
            w.forecast(self.fixture['stable'],96,row={'uncached_median_ns':0})


class LiveReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case=v27._session('R23_TWO_ROUNDS')
        cls.end=len(case.rounds)
        cls.source=next(x['expression'] for x in v27.representations(case) if x['mode']=='selective')
        cls.other=next(x['expression'] for x in v27.representations(case) if x['mode']=='hybrid_final')

    def test_idle_instrumentation_no_plaintext(self):
        reader=w.ObservedCacheReader(label='test_local')
        reader.idle()
        data=reader.export()
        self.assertEqual(data['origin'],'instrumented-process')
        self.assertEqual(data['events'],[{'tick':0,'kind':'idle'}])
        w.validate_document(data)
        self.assertNotIn(self.source,json.dumps(data))

    def test_initial_read_direct_and_records_only_success(self):
        reader=w.ObservedCacheReader()
        state=reader.read(self.source,self.end)
        self.assertEqual(state,v26.access_state(self.source,self.end))
        self.assertEqual(reader.stats()['direct_reads'],1)
        self.assertEqual(reader.export()['events'][0]['route'],'direct')

    def test_actual_repeat_reads_activate_v28_verified_cache(self):
        reader=w.ObservedCacheReader()
        for _ in range(34): reader.read(self.source,self.end)
        self.assertGreater(reader.stats()['cached_reads'],0)
        self.assertEqual(reader.stats()['cache']['verified_admissions'],1)
        self.assertGreater(reader.stats()['cache']['hits'],0)
        data=reader.export();w.validate_document(data)
        self.assertEqual(len(data['events']),34)

    def test_revision_invalidates_and_records_change(self):
        reader=w.ObservedCacheReader()
        reader.read(self.source,self.end)
        reader.read(self.other,self.end)
        stats=reader.stats()
        self.assertEqual(stats['source_invalidations'],1)
        self.assertTrue(reader.export()['events'][1]['revision_changed'])

    def test_invalid_source_not_emitted(self):
        reader=w.ObservedCacheReader()
        with self.assertRaises(w.WorkloadError): reader.read('NOT_A_SESSION',0)
        self.assertEqual(reader.export()['events'],[])

    def test_boolean_index_rejected_and_not_recorded(self):
        reader=w.ObservedCacheReader()
        with self.assertRaises(w.WorkloadError):reader.read(self.source,True)
        self.assertEqual(reader.stats()['direct_reads'],0)

    def test_dependency_change_blocks_reader(self):
        reader=w.ObservedCacheReader()
        initial=reader._dependencies
        with patch.object(w.ObservedCacheReader,'_manifest',return_value={**initial,'falsified':'x'}):
            with self.assertRaises(w.WorkloadEnvironmentChanged):reader.idle()
        with self.assertRaises(w.WorkloadEnvironmentChanged):reader.idle()

    def test_log_carries_no_source_bytes_or_digest(self):
        reader=w.ObservedCacheReader()
        reader.read(self.source,self.end)
        raw=json.dumps(reader.export())
        self.assertNotIn(self.source,raw)
        self.assertNotIn(w._sha(self.source.encode('utf-8')),raw)

    def test_failed_read_after_revision_not_claimed_success(self):
        reader=w.ObservedCacheReader()
        reader.read(self.source,self.end)
        with self.assertRaises(w.WorkloadError):reader.read(self.other,self.end+1)
        self.assertEqual(reader.stats()['source_invalidations'],0)
        self.assertEqual(len(reader.export()['events']),1)

    def test_export_is_deep_copy(self):
        reader=w.ObservedCacheReader()
        reader.idle()
        doc=reader.export();doc['events'][0]['kind']='read'
        self.assertEqual(reader.export()['events'][0]['kind'],'idle')


if __name__ == '__main__': unittest.main()
