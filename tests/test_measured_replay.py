"""ALCG v0.27 tests — structural guarantees, not fragile speed thresholds."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import measured_replay as lab
import checkpoint_planner as v26
import selective_delta as v25
import session_language as v23
import trace_language as v22


ROOT = Path(__file__).resolve().parents[1]


class MeasuredReplayTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = lab.load_verified(lab.REPORT_PATH)
        cls.session = lab._session(cls.record['session_id'])

    @staticmethod
    def resign(record):
        record['receipt_sha256'] = sha256(lab._canonical({k: v for k,v in record.items()
                                                           if k != 'receipt_sha256'})).hexdigest()
        return record

    def test_01_sample_verifies_against_exact_v026_sources(self):
        self.assertTrue(lab.verify_report(self.record)['checked'])

    def test_02_three_modes_and_source_hashes_are_frozen(self):
        self.assertEqual([r['mode'] for r in self.record['results']],
                         ['selective', 'hybrid_final', 'full'])
        self.assertEqual(self.record['source_fingerprints'], lab._source_hashes())

    def test_03_sample_was_really_measured_per_state_and_not_generated_time_units(self):
        self.assertEqual(self.record['clock'].split(';')[0], 'time.perf_counter_ns')
        self.assertEqual(self.record['repetitions'], 3)
        self.assertTrue(all(len(vals) == 3 for r in self.record['results']
                            for vals in r['sample_ns_by_state']))

    def test_04_every_candidate_is_verified_and_expands_to_exact_original_bytes(self):
        for entry in lab.representations(self.session):
            with self.subTest(mode=entry['mode']):
                self.assertEqual(v26.expand(entry['expression']),v23.encode(self.session))
                self.assertEqual(v26.access_state(entry['expression'], len(self.session.rounds)),
                                 v22.encode(v26._state(self.session,len(self.session.rounds))))

    def test_05_zero_read_profile_favors_smallest_storage(self):
        c=lab.evaluate_choices(self.record['results'],(0,)*3,2000)
        self.assertEqual(c['selected_mode'],'selective')

    def test_06_score_is_exact_raw_integer_model_no_float(self):
        c=lab.evaluate_choices(self.record['results'],(1,2,3),700)
        for r,row in zip(c['evaluated'],sorted(c['evaluated'],key=lambda x:(x['score_ns_equivalent'],x['utf8_bytes'],x['mode']))):
            self.assertEqual(r,row)
            self.assertEqual(r['score_ns_equivalent'], r['weighted_latency_ns']+r['storage_charge_ns_equivalent'])

    def test_07_measured_vs_abstract_planner_are_not_conflated(self):
        self.assertIn(self.record['observed_scenario']['selected_mode'],
                      ('selective','hybrid_final','full'))
        self.assertEqual(self.record['v026_abstract_planner']['mode'],
                         v26.choose(self.session,v26.profiles(self.session)['hot_tail']).mode)

    def test_08_rejects_changed_raw_time_even_with_old_digest(self):
        changed=deepcopy(self.record)
        changed['results'][0]['sample_ns_by_state'][0][0]+=1
        with self.assertRaises(lab.MeasurementError):
            lab.verify_report(changed)

    def test_09_rejects_false_median_even_when_digest_is_recomputed(self):
        changed=deepcopy(self.record)
        changed['results'][0]['median_ns_by_state'][0]+=1
        self.resign(changed)
        with self.assertRaisesRegex(lab.MeasurementError,'median'):
            lab.verify_report(changed)

    def test_10_rejects_mismatched_source_size_even_if_digest_recomputed(self):
        changed=deepcopy(self.record)
        changed['results'][1]['utf8_bytes']+=1
        self.resign(changed)
        with self.assertRaises(lab.MeasurementError):
            lab.verify_report(changed)

    def test_11_rejects_false_decision_score(self):
        changed=deepcopy(self.record)
        changed['observed_scenario']['evaluated'][0]['score_ns_equivalent']+=100
        self.resign(changed)
        with self.assertRaises(lab.MeasurementError):
            lab.verify_report(changed)

    def test_12_rejects_modified_old_model_baseline(self):
        changed=deepcopy(self.record)
        changed['v026_abstract_planner']['mode']='nonexistent'
        self.resign(changed)
        with self.assertRaises(lab.MeasurementError):
            lab.verify_report(changed)

    def test_13_rejects_changed_source_fingerprint(self):
        changed=deepcopy(self.record)
        changed['source_fingerprints']['checkpoint_planner.py']='0'*64
        self.resign(changed)
        with self.assertRaises(lab.MeasurementError):
            lab.verify_report(changed)

    def test_14_rejects_malformed_repetitions(self):
        for reps in (0,-1,True,1000):
            with self.subTest(reps=reps),self.assertRaises(lab.MeasurementError):
                lab.measure(repetitions=reps)

    def test_15_invalid_profiles_are_refused(self):
        with self.assertRaises(lab.MeasurementError):
            lab._profile_reads(self.session,'fiction')

    def test_16_invalid_weights_are_refused(self):
        row=self.record['results']
        for invalid in (-1, True, 0.5):
            with self.subTest(value=invalid),self.assertRaises(lab.MeasurementError):
                lab.evaluate_choices(row,(0,0,1),invalid)

    def test_17_wrong_number_of_requested_states_is_refused(self):
        with self.assertRaises(lab.MeasurementError):
            lab.evaluate_choices(self.record['results'],(1,2),100)

    def test_18_true_median_low_not_arithmetic_mean(self):
        row=deepcopy(self.record['results'])
        for x in row:
            x['median_ns_by_state']=[1,10,30]
        r=lab.evaluate_choices(row,(0,1,1),0)
        self.assertEqual(r['evaluated'][0]['weighted_latency_ns'],40)

    def test_19_same_reads_different_plans_are_possible_under_fake_timings(self):
        rows=deepcopy(self.record['results'])
        for entry, value in zip(rows,(900000,1000,2000000)):
            entry['median_ns_by_state']=[value]*3
        got=lab.evaluate_choices(rows,(0,0,10),0)
        self.assertEqual(got['selected_mode'],'hybrid_final')
        got=lab.evaluate_choices(rows,(0,0,10),100000)
        self.assertEqual(got['selected_mode'],'selective')

    def test_20_observed_access_equal_across_synthetic_fake_clock(self):
        s=lab._session('R23_TWO_ROUNDS')
        states=[v22.encode(v26._state(s,i)) for i in range(3)]
        counter={'t':0}
        def clock():
            return counter['t']
        def reader(source,index):
            counter['t'] += 1000 + (1000 if source.startswith('RUN_V023') else 0) + index*10
            return states[index]
        record=lab.measure(repetitions=1,warmups=0,clock=clock,reader=reader)
        self.assertTrue(lab.verify_report(record)['checked'])
        self.assertEqual(record['results'][0]['median_ns_by_state'],[1000,1010,1020])
        self.assertEqual(record['results'][2]['median_ns_by_state'],[2000,2010,2020])

    def test_21_incorrect_state_read_is_rejected_even_if_timer_increases(self):
        counter={'t':0}
        def clock():return counter['t']
        def fake_reader(_,__):
            counter['t']+=1
            return 'INVALID'
        with self.assertRaisesRegex(lab.MeasurementError,'canonical trace'):
            lab.measure(repetitions=1,warmups=0,clock=clock,reader=fake_reader)

    def test_22_zero_timer_resolution_refused(self):
        s=lab._session('R23_TWO_ROUNDS')
        states=[v22.encode(v26._state(s,i)) for i in range(3)]
        with self.assertRaisesRegex(lab.MeasurementError,'timer'):
            lab.measure(repetitions=1,warmups=0,clock=lambda:100,
                        reader=lambda _,i:states[i])

    def test_23_recorded_time_is_not_required_to_be_stable_across_runs(self):
        r=deepcopy(self.record)
        # Alter raw observations consistently and re-sign. Truth about the
        # local timer is *not* verified by a self-issued SHA digest.
        r['results'][0]['sample_ns_by_state'][0]=[15,20,25]
        r['results'][0]['median_ns_by_state'][0]=20
        r['observed_scenario']=lab.evaluate_choices(r['results'],
            lab._profile_reads(self.session,r['profile']),
            r['observed_scenario']['byte_price_ns_equivalent'])
        self.resign(r)
        self.assertTrue(lab.verify_report(r)['checked'])

    def test_24_original_language_dictionary_and_synthetic_samples_still_pass(self):
        self.assertEqual(len(v26._sessions()),5)
        v26._check_pins()

    def test_25_benchmark_output_refuses_writing_project_files(self):
        with patch.object(lab,'measure',return_value=self.record):
            self.assertEqual(lab.main(['bench','--output','README.md']),1)
            self.assertEqual(lab.main(['bench','--output','reports/measured-replay-v0.27.json']),1)

    def test_26_sample_file_valid_json(self):
        self.assertEqual(json.loads(lab.REPORT_PATH.read_text(encoding='utf-8')),self.record)

    def test_27_reader_discloses_full_verification_not_lazy_state_access(self):
        self.assertIn('EVERY read',self.record['reader'])
        self.assertIn('do not enable lazy state retrieval',self.record['notes'][1])

    def test_28_sample_is_illustrative_not_allocation_for_general_hardware(self):
        self.assertTrue(self.record['os'])
        self.assertTrue(self.record['measurement_start_utc'])
        self.assertIn('environment-specific',self.record['kind'])


if __name__=='__main__':
    import unittest
    unittest.main()
