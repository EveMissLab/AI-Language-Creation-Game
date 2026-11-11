"""v0.29 admission economy: deterministic model and real trusted reader paths."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import io
import json
import unittest
from unittest.mock import patch

import adaptive_cache as a
import checkpoint_planner as v26
import measured_replay as v27
import session_language as v23
import trusted_cache as v28


class AdaptiveCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = a.read_policy()
        cls.evidence = a.measured_evidence()
        cls.report = a.analyze(cls.evidence, cls.policy)
        cls.session = v27._session('R23_TWO_ROUNDS')
        cls.sources = {r['mode']: r['expression'] for r in v27.representations(cls.session)}
        cls.last_index = len(cls.session.rounds)

    def test_01_profiles_and_pinned_measured_source(self):
        self.assertEqual(self.policy['format'], a.FORMAT)
        self.assertEqual(self.policy['source_report_sha256'], a._sha(a.SOURCE_REPORT_PATH.read_bytes()))
        self.assertEqual(len(self.policy['workloads']), 7)

    def test_02_all_case_counts_and_determinism(self):
        self.assertEqual(len(self.report['cases']), 21)
        self.assertEqual(a.analyze(self.evidence, self.policy), self.report)

    def test_03_frozen_report_matches_computation(self):
        stored = json.loads(a.REPORT_PATH.read_text(encoding='utf-8'))
        self.assertTrue(a.verify_analysis(stored, self.evidence, self.policy))
        self.assertEqual(stored, self.report)

    def test_04_receipt_rejects_unacknowledged_modification(self):
        fake = deepcopy(self.report)
        fake['cases'][0]['decision']['selection'] = 'invalid'
        with self.assertRaisesRegex(a.AdaptiveError, 'receipt'):
            a.verify_analysis(fake, self.evidence, self.policy)

    def test_05_receipt_can_be_recomputed_but_cannot_invent_model_result(self):
        fake = deepcopy(self.report)
        fake['cases'][0]['decision']['selection'] = 'invalid'
        fake['receipt_sha256'] = a._sha(a._canon({k:v for k,v in fake.items() if k != 'receipt_sha256'}))
        with self.assertRaisesRegex(a.AdaptiveError, 'match pinned'):
            a.verify_analysis(fake, self.evidence, self.policy)

    def test_06_exact_break_even_under_zero_hazard(self):
        r = self.evidence['measurements']
        p = self.policy['workloads']['one_off']
        self.assertEqual([a.breakeven(row,p) for row in r], [22,23,3])

    def test_07_one_off_bypasses_all_three(self):
        self.assertEqual([a.estimate(row, self.policy['workloads']['one_off'])['selection']
                          for row in self.evidence['measurements']], ['direct']*3)

    def test_08_stable_repeat_admits_all_three(self):
        self.assertEqual([a.estimate(row, self.policy['workloads']['stable_repeat'])['selection']
                          for row in self.evidence['measurements']], ['cache']*3)

    def test_09_hazard_can_favor_direct_for_compact_but_cache_for_full(self):
        self.assertEqual([a.estimate(row, self.policy['workloads']['medium_churn'])['selection']
                          for row in self.evidence['measurements']], ['direct','direct','cache'])

    def test_10_high_churn_refuses_all_caches(self):
        self.assertEqual([a.estimate(row, self.policy['workloads']['rapid_churn'])['selection']
                          for row in self.evidence['measurements']], ['direct']*3)

    def test_11_high_retention_cost_changes_decision(self):
        outcomes = [a.estimate(row,self.policy['workloads']['retention_cost'])['selection']
                    for row in self.evidence['measurements']]
        self.assertEqual(outcomes, ['direct','direct','cache'])

    def test_12_hand_computed_fractional_probabilities(self):
        row = {'uncached_median_ns':5,'cold_admission_ns':10,'cached_median_ns':1}
        p = {'expected_reads':3,'invalidation_per_million':500000,
             'rebuild_penalty_ns':3,'retention_ns_per_read':0}
        d = a.estimate(row,p)
        self.assertEqual(d['expected_cache_admissions'], {'num':2,'den':1})
        self.assertEqual(d['expected_cache_hits'], {'num':1,'den':1})
        self.assertEqual(d['direct_cost_ns'], {'num':15,'den':1})
        self.assertEqual(d['cache_cost_ns'], {'num':24,'den':1})
        self.assertEqual(d['selection'], 'direct')
        p['invalidation_per_million']=250000
        d = a.estimate(row,p)
        self.assertEqual(Fraction(**{'numerator':d['expected_cache_admissions']['num'],
                                      'denominator':d['expected_cache_admissions']['den']}), Fraction(3,2))
        self.assertEqual(d['cache_cost_ns'], {'num':18,'den':1})

    def test_13_zero_reads_and_bool_are_not_allowed(self):
        base = dict(self.policy['workloads']['one_off'])
        for value in (0, -1, True, 1.0, a.MAX_READS+1):
            with self.subTest(value=value),self.assertRaises(a.AdaptiveError):
                a.validate_profile({**base,'expected_reads':value})

    def test_14_bad_hazard_and_penalty_types_are_rejected(self):
        base = dict(self.policy['workloads']['one_off'])
        for field,value in [('invalidation_per_million',1000001),('invalidation_per_million',True),
                            ('rebuild_penalty_ns',-1),('retention_ns_per_read',1.25)]:
            with self.subTest(field=field), self.assertRaises(a.AdaptiveError):
                a.validate_profile({**base,field:value})

    def test_15_bad_measurement_numbers_fail(self):
        row = dict(self.evidence['measurements'][0])
        for field, value in [('uncached_median_ns',True),('cached_median_ns',0),
                             ('cold_admission_ns',-1)]:
            with self.subTest(field=field),self.assertRaises(a.AdaptiveError):
                a.estimate({**row,field:value},self.policy['workloads']['one_off'])

    def test_16_forecast_one_read_never_admits(self):
        p={**self.policy['workloads']['stable_repeat'],'expected_reads':1}
        self.assertTrue(all(a.estimate(row,p)['selection']=='direct'
                            for row in self.evidence['measurements']))

    def test_17_always_invalidated_source_prefers_direct(self):
        p={**self.policy['workloads']['stable_repeat'],'invalidation_per_million':1_000_000}
        self.assertEqual([a.estimate(row,p)['selection'] for row in self.evidence['measurements']],['direct']*3)

    def test_18_cache_advantage_increases_with_more_stable_reads(self):
        row=self.evidence['measurements'][0]
        p=self.policy['workloads']['one_off']
        at22=a.estimate(row,{**p,'expected_reads':22})
        at64=a.estimate(row,{**p,'expected_reads':64})
        self.assertEqual(at22['selection'],'cache')
        self.assertGreater(at64['expected_savings_ns_if_cached']['num'],
                           at22['expected_savings_ns_if_cached']['num'])

    def test_19_live_one_off_does_actual_direct_verification(self):
        rd=a.AdaptiveCacheReader()
        source=self.sources['selective']
        with patch.object(a.v26,'access_state',wraps=a.v26.access_state) as spy:
            result=rd.read('source',source,2,profile='one_off')
            self.assertEqual(spy.call_count,1)
        self.assertEqual(result,v26.access_state(source,2))
        self.assertEqual(rd.stats()['underlying_cache']['verified_admissions'],0)
        self.assertEqual(rd.stats()['direct_reads'],1)

    def test_20_hot_second_read_avoids_second_full_model_replay(self):
        rd=a.AdaptiveCacheReader()
        source=self.sources['selective']
        with patch.object(a.v28.v26,'decode',wraps=a.v28.v26.decode) as spy:
            first=rd.read('source',source,2,profile='stable_repeat')
            second=rd.read('source',source,2,profile='stable_repeat')
            self.assertEqual(spy.call_count,1)
        self.assertEqual(first,second)
        self.assertEqual(rd.stats()['underlying_cache']['hits'],1)
        self.assertEqual(rd.stats()['cached_reads'],2)

    def test_21_alternate_alias_for_same_source_uses_same_verified_entry(self):
        rd=a.AdaptiveCacheReader()
        s=self.sources['selective']
        rd.read('left',s,0,profile='stable_repeat')
        rd.read('right',s,1,profile='stable_repeat')
        self.assertEqual(rd.stats()['underlying_cache']['verified_admissions'],1)
        self.assertEqual(rd.stats()['source_invalidations'],0)

    def test_22_alias_revision_forces_cache_clear_and_fresh_admission(self):
        rd=a.AdaptiveCacheReader()
        s0=self.sources['selective']; s1=self.sources['full']
        rd.read('case',s0,0,profile='stable_repeat')
        rd.read('case',s1,0,profile='stable_repeat')
        stats=rd.stats()
        self.assertEqual(stats['source_invalidations'],1)
        self.assertEqual(stats['underlying_cache']['verified_admissions'],2)
        self.assertEqual(stats['underlying_cache']['live_entries'],1)

    def test_23_same_alias_same_source_does_not_invalidate(self):
        rd=a.AdaptiveCacheReader()
        s=self.sources['selective']
        for _ in range(3):rd.read('case',s,0,profile='stable_repeat')
        self.assertEqual(rd.stats()['source_invalidations'],0)

    def test_24_dependency_mutation_blocks_direct_path_even_if_restored(self):
        rd=a.AdaptiveCacheReader()
        old=rd._live_manifest()
        changed={**old,'data/correlated-design-space-v0.21.json':'f'*64}
        with patch.object(a.AdaptiveCacheReader,'_live_manifest',return_value=changed):
            with self.assertRaises(a.AdaptiveEnvironmentChanged):
                rd.read('case',self.sources['selective'],0,profile='one_off')
        self.assertTrue(rd.stats()['blocked'])
        with self.assertRaises(a.AdaptiveEnvironmentChanged):
            rd.read('case',self.sources['selective'],0,profile='one_off')

    def test_25_dependency_mutation_clears_hot_cache(self):
        rd=a.AdaptiveCacheReader()
        rd.read('case',self.sources['selective'],0,profile='stable_repeat')
        changed={**rd._live_manifest(),'adaptive_cache.py':'b'*64}
        with patch.object(a.AdaptiveCacheReader,'_live_manifest',return_value=changed):
            with self.assertRaises(a.AdaptiveEnvironmentChanged):
                rd.read('case',self.sources['selective'],0,profile='stable_repeat')
        self.assertEqual(rd.stats()['underlying_cache']['live_entries'],0)

    def test_26_cache_entry_mutation_rejected_by_existing_guard(self):
        rd=a.AdaptiveCacheReader()
        s=self.sources['selective']
        rd.read('case',s,0,profile='stable_repeat')
        key=next(iter(rd._cache._entries))
        entry=rd._cache._entries[key]
        rd._cache._entries[key]=replace(entry,states=('FORGED',)+entry.states[1:])
        with self.assertRaises(v28.CacheError):
            rd.read('case',s,0,profile='stable_repeat')

    def test_27_unknown_input_never_admitted_even_under_hot_workload(self):
        rd=a.AdaptiveCacheReader()
        other=next(s for s in v26._sessions() if s.id!='R23_TWO_ROUNDS')
        source=v23.encode(other)
        self.assertEqual(rd.decision(source,'stable_repeat')['selection'],'direct')
        self.assertEqual(rd.read('case',source,0,profile='stable_repeat'),v26.access_state(source,0))
        self.assertEqual(rd.stats()['unknown_direct_reads'],1)
        self.assertEqual(rd.stats()['underlying_cache']['verified_admissions'],0)

    def test_28_invalid_source_is_not_silently_admitted(self):
        rd=a.AdaptiveCacheReader()
        for s in ('RAW(text="bogus")', 'RUN_V023()', '', '\ud800'):
            with self.subTest(s=s[:12]),self.assertRaises((a.AdaptiveError,v28.CacheError)):
                rd.read('case',s,0,profile='stable_repeat')
        self.assertEqual(rd.stats()['underlying_cache']['verified_admissions'],0)

    def test_29_invalid_state_index_is_rejected(self):
        rd=a.AdaptiveCacheReader()
        for index in (True,-1,1.1,'0',None):
            with self.subTest(index=index),self.assertRaises(a.AdaptiveError):
                rd.read('case',self.sources['selective'],index,profile='one_off')

    def test_30_invalid_alias_and_unknown_profile_are_rejected(self):
        rd=a.AdaptiveCacheReader()
        for alias in ('','two words','../key','-dash', 'x'*65):
            with self.subTest(alias=alias),self.assertRaises(a.AdaptiveError):
                rd.read(alias,self.sources['selective'],0,profile='one_off')
        with self.assertRaises(a.AdaptiveError):
            rd.read('case',self.sources['selective'],0,profile='unknown')

    def test_31_concurrent_accesses_preserve_one_admission(self):
        rd=a.AdaptiveCacheReader()
        s=self.sources['selective']
        with ThreadPoolExecutor(max_workers=5) as pool:
            answers=list(pool.map(lambda i:rd.read('case',s,i%3,profile='stable_repeat'),range(10)))
        self.assertEqual(len(answers),10)
        self.assertEqual(rd.stats()['underlying_cache']['verified_admissions'],1)
        self.assertEqual(rd.stats()['underlying_cache']['hits'],9)

    def test_32_check_uses_actual_direct_and_cached_paths(self):
        result=a.check()
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['sample_runtime']['direct_reads'],1)
        self.assertEqual(result['sample_runtime']['underlying_cache']['hits'],1)

    def test_33_cli_plan_is_deterministic(self):
        stream=io.StringIO()
        with redirect_stdout(stream):
            code=a.main(['plan','--mode','selective','--profile','stable_repeat'])
        self.assertEqual(code,0)
        result=json.loads(stream.getvalue())
        self.assertEqual(result['break_even_reads'],22)
        self.assertEqual(result['result']['selection'],'cache')

    def test_34_report_per_profile_has_three_sources_and_no_AI_claims(self):
        items=self.report['cases']
        self.assertEqual(len({x['source_sha256'] for x in items}),3)
        self.assertEqual(len({x['profile'] for x in items}),7)
        self.assertTrue(any('AI' in x for x in self.report['claims_excluded']))

    def test_35_cost_model_ties_bypass_even_if_cache_is_available(self):
        row={'uncached_median_ns':10,'cold_admission_ns':10,'cached_median_ns':10}
        p=self.policy['workloads']['one_off']
        self.assertEqual(a.estimate(row,p)['selection'],'direct')

    def test_36_rounding_free_exact_fraction_for_rare_invalidations(self):
        p={**self.policy['workloads']['stable_repeat'],'expected_reads':2,
           'invalidation_per_million':1}
        result=a.estimate({'uncached_median_ns':1,'cold_admission_ns':1,
                           'cached_median_ns':1},p)
        self.assertEqual(result['expected_cache_admissions'], {'num':1000001,'den':1000000})
        self.assertEqual(result['cache_cost_ns'],{'num':2,'den':1})


if __name__ == '__main__':
    unittest.main()
