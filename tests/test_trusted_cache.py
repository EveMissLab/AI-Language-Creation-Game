"""v0.28 verification-first process cache: no blind trust or speed thresholds."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import trusted_cache as lab
import measured_replay as v27
import checkpoint_planner as v26
import session_language as v23
import trace_language as v22


class TrustedCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = v27._session('R23_TWO_ROUNDS')
        cls.choices = v27.representations(cls.session)
        cls.sources = {e['mode']:e['expression'] for e in cls.choices}
        cls.expected = [v22.encode(v26._state(cls.session,i))
                        for i in range(len(cls.session.rounds)+1)]

    @staticmethod
    def _resign(report):
        report['receipt_sha256']=lab._sha(lab._json_bytes({k:v for k,v in report.items()
                                                           if k!='receipt_sha256'}))
        return report

    def test_01_all_three_formats_are_byte_identical_to_uncached_reader(self):
        cache=lab.VerifiedStateCache()
        for mode,source in self.sources.items():
            for i,expected in enumerate(self.expected):
                with self.subTest(mode=mode,i=i):
                    self.assertEqual(cache.read(source,i),expected)
                    self.assertEqual(cache.read(source,i),v26.access_state(source,i))
        self.assertEqual(cache.stats()['verified_admissions'],3)

    def test_02_repeated_read_avoids_second_full_replay(self):
        cache=lab.VerifiedStateCache()
        src=self.sources['hybrid_final']
        with patch.object(lab.v26,'decode',wraps=lab.v26.decode) as spy:
            self.assertEqual(cache.read(src,2),self.expected[2])
            self.assertEqual(cache.read(src,2),self.expected[2])
            self.assertEqual(cache.read(src,1),self.expected[1])
            self.assertEqual(spy.call_count,1)
        self.assertEqual(cache.stats()['hits'],2)

    def test_03_first_read_full_session_is_checked(self):
        src=self.sources['selective']
        cache=lab.VerifiedStateCache()
        with patch.object(lab.v26,'decode',wraps=lab.v26.decode) as spy:
            self.assertEqual(cache.read(src,0),self.expected[0])
            self.assertEqual(spy.call_count,1)
        self.assertEqual(cache.stats()['verified_admissions'],1)

    def test_04_expand_exact_original_without_unverified_bytes(self):
        cache=lab.VerifiedStateCache()
        for source in self.sources.values():
            self.assertEqual(cache.expand(source),v23.encode(self.session))

    def test_05_open_and_stop_status_preserved(self):
        cache=lab.VerifiedStateCache()
        for s in v26._sessions():
            source=v23.encode(s)
            self.assertEqual(cache.expand(source),source)
            self.assertEqual(cache.read(source,len(s.rounds)),v22.encode(v26._state(s,len(s.rounds))))

    def test_06_mutated_input_with_old_receipt_is_rejected(self):
        src=self.sources['selective']
        cache=lab.VerifiedStateCache()
        cache.read(src,2)
        modified=src.replace('TRUE','FALSE',1)
        if modified==src:
            modified=src.replace('FALSE','TRUE',1)
        self.assertNotEqual(modified,src)
        with self.assertRaises(lab.CacheError):
            cache.read(modified,2)
        self.assertEqual(cache.read(src,2),self.expected[2])

    def test_07_noncanonical_whitespace_fails_closed(self):
        with self.assertRaises(lab.CacheError):
            lab.VerifiedStateCache().read(self.sources['hybrid_final'].replace('base=', 'base =',1),1)

    def test_08_invalid_syntax_fails_closed(self):
        for src in ('HELLO', 'RAW(text="unverified")', 'RUN_V023()', 'NOT_A_RUN(x=Y)'):
            with self.subTest(src=src),self.assertRaises(lab.CacheError):
                lab.VerifiedStateCache().read(src,0)

    def test_09_invalid_source_types_and_bounds(self):
        for src in ('',None,123,True,'X'*(v26.MAX_CHARS+1),'\ud800'):
            with self.subTest(src=str(src)[:15]),self.assertRaises(lab.CacheError):
                lab.VerifiedStateCache().read(src,0)

    def test_10_invalid_state_indices_do_not_admit_untrusted_source(self):
        cache=lab.VerifiedStateCache()
        for i in (-1,True,1.5,None,'2'):
            with self.subTest(i=i),self.assertRaises(lab.CacheError):
                cache.read(self.sources['selective'],i)
        self.assertEqual(cache.stats()['verified_admissions'],0)
        with self.assertRaises(lab.CacheError):
            cache.read(self.sources['selective'],100)

    def test_11_manual_invalidation_forces_replay(self):
        cache=lab.VerifiedStateCache()
        src=self.sources['selective']
        cache.read(src,0)
        cache.clear()
        self.assertEqual(cache.stats()['live_entries'],0)
        cache.read(src,0)
        self.assertEqual(cache.stats()['verified_admissions'],2)
        self.assertEqual(cache.stats()['invalidations'],1)

    def test_12_exact_lru_eviction(self):
        cache=lab.VerifiedStateCache(max_entries=2)
        a,b,c=(self.sources[n] for n in ('selective','hybrid_final','full'))
        cache.read(a,0)
        cache.read(b,0)
        cache.read(a,0)
        cache.read(c,0)
        self.assertEqual(cache.stats()['evictions'],1)
        cache.read(b,0)
        self.assertEqual(cache.stats()['verified_admissions'],4)
        self.assertEqual(cache.stats()['evictions'],2)

    def test_13_environment_changes_fail_closed_and_clear(self):
        cache=lab.VerifiedStateCache()
        cache.read(self.sources['selective'],0)
        changed=lab.source_manifest()
        changed['data/correlated-design-space-v0.21.json']='0'*64
        with patch.object(lab,'source_manifest',return_value=changed):
            with self.assertRaises(lab.CacheEnvironmentChanged):
                cache.read(self.sources['selective'],0)
        self.assertEqual(cache.stats()['live_entries'],0)
        self.assertEqual(cache.stats()['invalidations'],1)
        # Once the original environment is back, a fresh full replay is required.
        self.assertEqual(cache.read(self.sources['selective'],0),self.expected[0])
        self.assertEqual(cache.stats()['verified_admissions'],2)

    def test_14_dependency_change_during_first_replay_is_rejected(self):
        manifest=lab.source_manifest()
        changed={**manifest,'trace_language.py':'e'*64}
        cache=lab.VerifiedStateCache()
        with patch.object(lab,'source_manifest',side_effect=[manifest,changed]):
            with self.assertRaises(lab.CacheEnvironmentChanged):
                cache.read(self.sources['selective'],0)
        self.assertEqual(cache.stats()['verified_admissions'],0)

    def test_15_mutated_cached_snapshot_detected_not_accepted(self):
        cache=lab.VerifiedStateCache()
        cache.read(self.sources['selective'],0)
        key=next(iter(cache._entries))
        entry=cache._entries[key]
        cache._entries[key]=replace(entry,states=('FORGED',)+entry.states[1:])
        with self.assertRaisesRegex(lab.CacheError,'snapshot'):
            cache.read(self.sources['selective'],0)
        self.assertEqual(cache.stats()['live_entries'],0)

    def test_16_mutated_cached_full_session_detected(self):
        cache=lab.VerifiedStateCache()
        cache.expand(self.sources['selective'])
        key=next(iter(cache._entries))
        cache._entries[key]=replace(cache._entries[key],full_session='FORGED')
        with self.assertRaisesRegex(lab.CacheError,'canonical'):
            cache.expand(self.sources['selective'])

    def test_17_hash_collision_cannot_return_wrong_input(self):
        cache=lab.VerifiedStateCache()
        cache.read(self.sources['selective'],0)
        oldkey=next(iter(cache._entries))
        src=self.sources['full']
        with patch.object(lab.VerifiedStateCache,'_source_key',return_value=(oldkey,src.encode())):
            with self.assertRaisesRegex(lab.CacheError,'collision'):
                cache.read(src,0)
        self.assertEqual(cache.stats()['live_entries'],0)

    def test_18_multi_thread_same_source_single_admission(self):
        cache=lab.VerifiedStateCache()
        src=self.sources['selective']
        with ThreadPoolExecutor(max_workers=4) as ex:
            outputs=list(ex.map(lambda _:cache.read(src,2), range(8)))
        self.assertEqual(outputs,[self.expected[2]]*8)
        self.assertEqual(cache.stats()['verified_admissions'],1)
        self.assertEqual(cache.stats()['hits'],7)

    def test_19_invalid_cache_sizes_rejected(self):
        for limit in (0,17,True,1.5,-2,'4'):
            with self.subTest(limit=limit),self.assertRaises(lab.CacheError):
                lab.VerifiedStateCache(limit)

    def test_20_policy_is_explicit_process_only_not_external_transport(self):
        policy=lab._policy()
        self.assertEqual(policy['persistence'],'process-only')
        self.assertEqual(policy['trust_domain'],'non-hostile single process')
        self.assertNotIn('remote_token',policy)

    def test_21_a_new_cache_has_zero_hits_even_with_existing_instance(self):
        first=lab.VerifiedStateCache()
        first.read(self.sources['selective'],0)
        second=lab.VerifiedStateCache()
        self.assertEqual(second.stats()['verified_admissions'],0)
        second.read(self.sources['selective'],0)
        self.assertEqual(second.stats()['verified_admissions'],1)

    def test_22_benchmark_actual_time_and_receipt_internal_consistency(self):
        r=lab.benchmark(repeats=1)
        self.assertTrue(lab.verify_report(r)['verified'])
        self.assertEqual(len(r['measurements']),3)
        self.assertEqual([x['cache_hits'] for x in r['measurements']],[1]*3)

    def test_23_report_checksum_detects_observation_changes(self):
        r=lab.benchmark(repeats=1)
        r['measurements'][0]['cached_samples_ns'][0]+=1
        with self.assertRaisesRegex(lab.CacheError,'receipt'):
            lab.verify_report(r)

    def test_24_re_signed_false_median_is_detected(self):
        r=lab.benchmark(repeats=1)
        r['measurements'][0]['cached_median_ns']+=1
        self._resign(r)
        with self.assertRaisesRegex(lab.CacheError,'medians'):
            lab.verify_report(r)

    def test_25_re_signed_wrong_source_identity_is_detected(self):
        r=lab.benchmark(repeats=1)
        r['measurements'][0]['source_sha256']='0'*64
        self._resign(r)
        with self.assertRaisesRegex(lab.CacheError,'identity'):
            lab.verify_report(r)

    def test_26_re_signed_false_counts_are_detected(self):
        r=lab.benchmark(repeats=1)
        r['measurements'][0]['verified_admissions']=0
        self._resign(r)
        with self.assertRaisesRegex(lab.CacheError,'counts'):
            lab.verify_report(r)

    def test_27_invalid_benchmark_repeats_rejected(self):
        for repeats in (0,True,-1,21,'5'):
            with self.subTest(repeats=repeats),self.assertRaises(lab.CacheError):
                lab.benchmark(repeats=repeats)

    def test_28_benchmark_output_is_restricted(self):
        for path in ('README.md','data/checkpoint-profiles-v0.26.json',
                     'reports/trusted-cache-v0.28.json','../ALCG_v0.28_work/README.md',
                     'timing.txt'):
            with self.subTest(path=path),self.assertRaises(lab.CacheError):
                lab._safe_destination(path)
        self.assertTrue(str(lab._safe_destination('.local/custom-v0.28.json')).endswith('.json'))

    def test_29_static_report_is_verified(self):
        self.assertTrue(lab.check()['verified'])

    def test_30_source_hash_is_sha256_of_exact_utf8_bytes(self):
        for row in self.choices:
            self.assertEqual(row['expression_sha256'],
                             sha256(row['expression'].encode('utf-8')).hexdigest())

    def test_31_clear_does_not_destroy_archive_or_source(self):
        cache=lab.VerifiedStateCache()
        cache.expand(self.sources['full'])
        cache.clear()
        self.assertEqual(v23.encode(self.session),self.sources['full'])

    def test_32_zero_hash_pins_not_allowed_to_bypass_decode(self):
        cache=lab.VerifiedStateCache()
        with patch.object(lab.v26,'decode',side_effect=v26.CheckpointError('blocked')):
            with self.assertRaisesRegex(lab.CacheError,'fresh full verification'):
                cache.read(self.sources['selective'],0)
        self.assertEqual(cache.stats()['live_entries'],0)

    def test_33_duplicate_version_pins_detected(self):
        hashes=lab.source_manifest()
        self.assertEqual(len(hashes),len(lab.WATCH_FILES))
        self.assertTrue(all(len(v)==64 for v in hashes.values()))

    def test_34_no_speedup_hard_assertions_in_published_audit(self):
        data=lab.REPORT_PATH.read_text(encoding='utf-8')
        self.assertNotIn('minimum_required_speedup',data)
        self.assertNotIn('always_faster',data)


if __name__ == '__main__':
    unittest.main()
