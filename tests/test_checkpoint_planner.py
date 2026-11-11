"""v0.26 bounded, verifiable hybrid checkpoint planning; synthetic workloads."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
from unittest import TestCase
from unittest.mock import patch

import checkpoint_planner as lab
import session_language as v23
import selective_delta as v25
import trace_language as v22
from alcg import parse, render


ROOT = Path(__file__).resolve().parents[1]


class CheckpointPlannerTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = lab._sessions()
        cls.first = cls.sessions[0]
        cls.hot = lab.choose(cls.first, lab.profiles(cls.first)['hot_tail'])

    def test_01_original_fixtures_untouched(self):
        self.assertEqual(len(self.sessions), 5)
        self.assertEqual(sum(len(s.rounds) for s in self.sessions), 8)
        self.assertEqual(len(lab.PINNED_V025), 4)
        lab._check_pins()

    def test_02_cold_archive_prefers_selective(self):
        for session in self.sessions:
            self.assertEqual(lab.choose(session, lab.profiles(session)['cold_archive']).mode,
                             'selective')

    def test_03_hot_tail_selects_hybrid_for_multiple_rounds(self):
        self.assertEqual(self.hot.mode, 'hybrid')
        self.assertEqual(self.hot.checkpoints, (2,))
        self.assertGreater(self.hot.byte_size, len(v25.encode(self.first)))

    def test_04_full_snapshot_is_a_real_candidate(self):
        candidate = lab.choose(self.sessions[2], lab.profiles(self.sessions[2])['hot_tail'])
        self.assertEqual(candidate.mode, 'full')
        self.assertEqual(candidate.checkpoints, (0,))

    def test_05_tight_budget_selects_selective(self):
        for session in self.sessions:
            p = lab.choose(session, lab.profiles(session)['storage_limited'])
            self.assertEqual(p.mode, 'selective')

    def test_06_middle_checkpoint_is_useful(self):
        s = self.sessions[1]
        candidate = lab.choose(s, lab.profiles(s)['mixed_reads'])
        self.assertEqual(candidate.mode, 'hybrid')
        self.assertEqual(candidate.checkpoints, (2,))

    def test_07_latency_bound_can_force_two_checkpoints(self):
        s = self.sessions[1]
        c = lab.choose(s, lab.profiles(s)['bounded_latency'])
        self.assertLessEqual(c.max_read_work_units, 1)
        self.assertEqual(c.checkpoints, (0, 2))

    def test_08_all_modes_restore_identical_original_source(self):
        s = self.first
        representations = [v23.encode(s), v25.encode(s),
                           lab.encode_hybrid(s, (1,)),
                           lab.encode_hybrid(s, (0, 2))]
        for expression in representations:
            with self.subTest(root=expression[:30]):
                self.assertEqual(lab.expand(expression).encode('utf-8'),
                                 v23.encode(s).encode('utf-8'))
                self.assertEqual(lab.decode(expression), s)

    def test_09_exact_state_access_returns_canonical_trace(self):
        for index in range(len(self.first.rounds) + 1):
            self.assertEqual(lab.access_state(self.hot.expression, index),
                             v22.encode(lab._state(self.first, index)))

    def test_10_initial_and_final_checkpoints(self):
        source = lab.encode_hybrid(self.first, (0, 2))
        self.assertIn('s0000=TRACE_V022(', source)
        self.assertIn('s0002=TRACE_V022(', source)
        self.assertEqual(lab.expand(source), v23.encode(self.first))

    def test_11_selection_does_not_change_open_status(self):
        for s in self.sessions:
            for name in ('cold_archive', 'hot_tail'):
                p = lab.choose(s, lab.profiles(s)[name])
                self.assertEqual(lab.decode(p.expression).status, s.status)

    def test_12_rejects_changed_checkpoint_fields(self):
        original = self.hot.expression
        self.assertIn('s0002=TRACE_V022', original)
        manipulated = original.replace('s0002=TRACE_V022',
                                       's0002=TRACE_WRONG', 1)
        with self.assertRaises(lab.CheckpointError):
            lab.decode(manipulated)

    def test_13_rejects_changed_snapshot_values(self):
        source = self.hot.expression
        # Only rewrite the embedded checkpoint; leave the baseline unchanged.
        before, after = source.split('s0002=TRACE_V022(', 1)
        modified = before + 's0002=TRACE_V022(' + after.replace('TRUE', 'FALSE', 1)
        if modified == source:
            modified = before + 's0002=TRACE_V022(' + after.replace('0', '1', 1)
        self.assertNotEqual(modified, source)
        with self.assertRaises(lab.CheckpointError):
            lab.decode(modified)

    def test_14_rejects_modified_base_pins(self):
        source = self.hot.expression
        altered = source.replace('SYNTHETIC', 'INVENTED', 1)
        self.assertNotEqual(source, altered)
        with self.assertRaises(lab.CheckpointError):
            lab.decode(altered)

    def test_15_rejects_extra_checkpoint(self):
        source = self.hot.expression
        altered = source.replace('s0002=TRACE_V022', 's9999=TRACE_V022', 1)
        with self.assertRaises(lab.CheckpointError):
            lab.decode(altered)

    def test_16_rejects_duplicate_or_unsorted_indices(self):
        for indices in ((1, 1), (2, 1), (-1,), (3,), (True,)):
            with self.subTest(indices=indices), self.assertRaises(lab.CheckpointError):
                lab.encode_hybrid(self.first, indices)

    def test_17_empty_hybrid_is_invalid(self):
        with self.assertRaises(lab.CheckpointError):
            lab.encode_hybrid(self.first, ())

    def test_18_rejects_unrelated_root(self):
        for source in ('RAW(text="anything")', 'LANGUAGE',
                       'CHECKPOINT_RUN_V026(base=AI, states=STATES_V026())'):
            with self.subTest(src=source), self.assertRaises(lab.CheckpointError):
                lab.decode(source)

    def test_19_requires_canonical_rendering(self):
        source = self.hot.expression
        with self.assertRaises(lab.CheckpointError):
            lab.decode(source.replace('base=', 'base =', 1))

    def test_20_weights_must_be_nonnegative_integers(self):
        for values in ((0, -1, 0), (0, True, 0), (1, 0), (0, 0, 0, 0)):
            with self.subTest(values=values), self.assertRaises(lab.CheckpointError):
                lab.Workload(tuple(values)).validate(2)

    def test_21_bad_budget_and_latency_inputs_rejected(self):
        s = self.first
        for config in (lab.Workload((1, 1, 1), byte_budget=True),
                       lab.Workload((1, 1, 1), replay_weight=-1),
                       lab.Workload((1, 1, 1), max_lookup_units=-1)):
            with self.assertRaises(lab.CheckpointError):
                lab.choose(s, config)

    def test_22_impossible_storage_budget_fails(self):
        with self.assertRaises(lab.CheckpointError):
            lab.choose(self.first, lab.Workload((1, 1, 1), byte_budget=1))

    def test_23_read_work_units_are_integers_and_transparent(self):
        n = 2
        frequencies = (2, 3, 5)
        self.assertEqual(lab._read_units(n, (), frequencies), (2*1 + 3*2 + 5*3, 3))
        self.assertEqual(lab._read_units(n, (1,), frequencies), (2 + 0 + 5, 1))
        self.assertEqual(lab._read_units(n, (0, 2), frequencies), (0 + 3 + 0, 1))

    def test_24_full_representation_has_zero_modeled_read_work(self):
        s = self.first
        c = lab.Workload((15, 20, 30))
        full = next(x for x in lab.candidates(s, c) if x.mode == 'full')
        self.assertEqual(full.read_work_units, 0)
        self.assertEqual(full.snapshot_writes, len(s.rounds) + 1)

    def test_25_warm_cache_must_not_ignore_pinned_file_change(self):
        lab.choose(self.first, lab.profiles(self.first)['hot_tail'])
        replaced = dict(lab.PINNED_V025)
        replaced['selective_delta.py'] = '0' * 64
        with patch.object(lab, 'PINNED_V025', replaced):
            with self.assertRaises(lab.CheckpointError):
                lab.choose(self.first, lab.profiles(self.first)['hot_tail'])

    def test_26_brute_force_rank_independent_of_planner_function(self):
        s = self.first
        config = lab.profiles(s)['hot_tail']
        got = lab.choose(s, config)
        # Enumerate separately without calling choose() or its scoring helper.
        entries = []
        for mask in range(1 << (len(s.rounds) + 1)):
            cps = tuple(i for i in range(len(s.rounds) + 1) if mask & (1 << i))
            text = (lab.encode_hybrid(s, cps) if cps else v25.encode(s))
            units = 0
            max_units = 0
            for index, freq in enumerate(config.reads):
                previous = [j for j in cps if j <= index]
                cost = index - previous[-1] if previous else index + 1
                units += freq*cost
                if freq:
                    max_units = max(max_units, cost)
            storage = len(text.encode('utf-8'))
            rank = (storage*config.byte_weight + units*config.replay_weight
                    + len(cps)*config.snapshot_write_weight, storage,
                    units, 'hybrid' if cps else 'selective', cps)
            entries.append(rank)
        full_body = v23.encode(s)
        full_bytes = len(full_body.encode('utf-8'))
        entries.append((full_bytes*config.byte_weight
                        + (len(s.rounds)+1)*config.snapshot_write_weight,
                        full_bytes,0,'full',tuple(range(len(s.rounds)+1))))
        want = min(entries)
        self.assertEqual((got.score, got.byte_size, got.read_work_units,
                          got.mode, got.checkpoints), want)

    def test_27_report_is_reproducible(self):
        self.assertEqual(json.loads(lab.report_text()),
                         json.loads(lab.REPORT_PATH.read_text('utf-8')))

    def test_28_fixture_and_spec_are_reproducible(self):
        self.assertEqual(lab.fixture_text().encode('utf-8'),
                         lab.SAMPLES_PATH.read_bytes())
        self.assertEqual(json.loads(lab.DATA_PATH.read_text('utf-8')),
                         lab.model_spec())

    def test_29_saved_report_uses_only_synthetic_work_units(self):
        data = lab.check()
        self.assertEqual(data['sessions'], 5)
        self.assertEqual(data['rounds'], 8)
        self.assertFalse(data['real_cpu_time_measured'])
        self.assertFalse(data['independent_ai_comprehension_measured'])

    def test_30_all_frozen_state_receipts_are_replayable(self):
        for s in self.sessions:
            all_snapshots = lab.encode_hybrid(s, tuple(range(len(s.rounds)+1)))
            self.assertEqual(lab.expand(all_snapshots), v23.encode(s))
            self.assertEqual(lab.decode(all_snapshots).final_chain_sha256,
                             s.final_chain_sha256)
