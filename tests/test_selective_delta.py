"""v0.25 exact selective transport and adversarial tests; all examples synthetic."""
import json
from pathlib import Path
from dataclasses import replace
import unittest

from alcg import parse, render
import selective_delta as lab
import delta_language as v24
import session_language as v23

ROOT = Path(__file__).resolve().parents[1]


class SelectiveDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = v24._sessions()
        cls.lean = [lab.encode(s) for s in cls.sessions]

    def test_original_five_cases_and_rounds(self):
        self.assertEqual(len(self.sessions), 5)
        self.assertEqual(sum(len(s.rounds) for s in self.sessions), 8)
        self.assertEqual([len(s.rounds) for s in self.sessions], [2, 3, 0, 1, 2])

    def test_readings_are_irreducible_and_retained(self):
        for s, source in zip(self.sessions, self.lean):
            self.assertEqual(source.count('reading='), len(s.rounds))
            self.assertEqual([r.reading for r in lab.decode(source).rounds],
                             [r.reading for r in s.rounds])

    def test_lean_omits_only_derived_step_fields(self):
        for source in self.lean:
            self.assertNotIn('link_sha256=', source)
            self.assertNotIn('action=', source)
            self.assertIn('chain_sha256=', source)
            self.assertIn('seed_sha256=', source)
            self.assertIn('profile_sha256=', source)

    def test_full_reconstruction_for_every_profile(self):
        for s in self.sessions:
            for name, gap, ma in lab._profiles(s):
                with self.subTest(id=s.id, profile=name):
                    value = lab.encode(s, gap, ma)
                    self.assertEqual(lab.decode(value), s)
                    self.assertEqual(lab.expand(value).encode('utf-8'),
                                     v23.encode(s).encode('utf-8'))
                    self.assertEqual(lab.pack(v23.encode(s), gap, ma), value)

    def test_preserves_open_and_stop(self):
        for s, source in zip(self.sessions, self.lean):
            self.assertEqual(lab.decode(source).status, s.status)
        self.assertEqual(self.sessions[3].status, 'OPEN')
        self.assertEqual(self.sessions[2].status, 'STOP')

    def test_mandatory_terminal_hash_and_initial_pins(self):
        for s, src in zip(self.sessions, self.lean):
            self.assertIn(s.final_chain_sha256, src)
            self.assertIn(s.seed_sha256, src)
            self.assertIn(s.initial.spec_sha256, src)

    def test_best_size_is_true_minimum_for_bounded_mask_family(self):
        # Independent brute force length enumeration, not just a claim in prose.
        for s in self.sessions:
            n = len(s.rounds)
            for gap in (1, 2, lab.MAX_GAP):
                for min_actions in (0, min(1, n), n):
                    with self.subTest(id=s.id, gap=gap, minimum=min_actions):
                        candidate = lab.encode(s, gap, min_actions)
                        sizes = []
                        for a in range(1 << n):
                            for h in range(1 << n):
                                anchors = [0] + [i+1 for i in range(n-1) if h & (1 << i)] + [n]
                                if n and (h & (1 << (n-1))):
                                    continue
                                if a.bit_count() < min_actions:
                                    continue
                                if any(b - x > gap for x,b in zip(anchors, anchors[1:])):
                                    continue
                                sizes.append(len(render(lab._tree(s,gap,min_actions,a,h)).encode('utf-8')))
                        self.assertTrue(sizes)
                        self.assertEqual(len(candidate.encode('utf-8')), min(sizes))

    def test_gap_one_forces_internal_receipts(self):
        s=self.sessions[1]  # 3 rounds, final receipt already at 3.
        a,h,_=lab._best(s,1,0)
        self.assertEqual(a,0)
        self.assertEqual(h,0b011)

    def test_at_least_one_visible_action(self):
        for s in self.sessions:
            if not s.rounds:
                continue
            for gap in (1,2):
                a,h,_=lab._best(s,gap,1)
                self.assertGreaterEqual(a.bit_count(),1)
                self.assertEqual(lab.decode(lab.encode(s,gap,1)),s)

    def test_zero_round_receipt_is_larger_not_fake_savings(self):
        session=self.sessions[2]
        self.assertGreater(len(lab.encode(session)),len(v24.encode(session)))
        self.assertIn('STEPS_V025()',lab.encode(session))

    def test_constraints_reject_bool_negative_or_overflow(self):
        s=self.sessions[0]
        for gap,ma in [(0,0),(lab.MAX_GAP+1,0),(True,0),(1,-1),(1,3),(1,False)]:
            with self.subTest(gap=gap,ma=ma), self.assertRaises(lab.SelectionError):
                lab.encode(s,gap,ma)

    def test_byte_budget_success_at_threshold_and_failure_below(self):
        s=self.sessions[0]; value=lab.encode(s,2,1)
        self.assertEqual(lab.encode(s,2,1,len(value.encode('utf-8'))),value)
        with self.assertRaises(lab.SelectionError):
            lab.encode(s,2,1,len(value.encode('utf-8'))-1)
        for invalid in (True, -1, 1.5):
            with self.subTest(budget=invalid),self.assertRaises(lab.SelectionError):
                lab.encode(s,2,1,invalid)

    def test_syntax_roundtrip(self):
        for s in self.sessions:
            for name,gap,ma in lab._profiles(s):
                src=lab.encode(s,gap,ma)
                self.assertEqual(render(parse(src)),src)
                self.assertNotIn('TRACE_V022(',src)
                self.assertNotIn('RAW(',src)

    def test_tampered_observation_fails(self):
        src=self.lean[0]
        altered=src.replace('reading=TRUE','reading=FALSE',1)
        self.assertNotEqual(src,altered)
        with self.assertRaises(lab.SelectionError):lab.decode(altered)

    def test_tampered_final_receipt_fails(self):
        src=self.lean[0]
        altered=src.replace('chain_sha256=SHA256(value="',
                            'chain_sha256=SHA256(value="1',1)
        with self.assertRaises(lab.SelectionError):lab.decode(altered)

    def test_tampered_visible_action_fails(self):
        s=self.sessions[0];src=lab.encode(s,2,2)
        self.assertIn('action=NAT(value="',src)
        mutated=src.replace('action=NAT(value="','action=NAT(value="99',1)
        with self.assertRaises(lab.SelectionError):lab.decode(mutated)

    def test_tampered_intermediate_chain_receipt_fails(self):
        s=self.sessions[1];src=lab.encode(s,1,0)
        self.assertIn('link_sha256=SHA256(value="',src)
        mutated=src.replace('link_sha256=SHA256(value="',
                            'link_sha256=SHA256(value="0',1)
        with self.assertRaises(lab.SelectionError):lab.decode(mutated)

    def test_tampered_stored_audit_contract_fails(self):
        src=lab.encode(self.sessions[1],1,2)
        mutated=src.replace('max_gap=NAT(value="1")','max_gap=NAT(value="2")',1)
        with self.assertRaises(lab.SelectionError):lab.decode(mutated)

    def test_forged_model_version_rejected(self):
        src=self.lean[0]
        bad=src.replace('profile_sha256=SHA256(value="',
                        'profile_sha256=SHA256(value="bad',1)
        with self.assertRaises(lab.SelectionError):lab.decode(bad)

    def test_unknown_fields_and_missing_reading_rejected(self):
        src=self.lean[0]
        for bad in (src.replace('SELECTIVE_RUN_V025(', 'SELECTIVE_RUN_V025(extra=AI, ',1),
                    src.replace('reading=TRUE','not_reading=TRUE',1),
                    src.replace('r0002=STEP_V025(', 'r0003=STEP_V025(',1)):
            with self.subTest(snippet=bad[:80]), self.assertRaises(lab.SelectionError):
                lab.decode(bad)

    def test_noncanonical_overstorage_rejected(self):
        src=self.lean[0]
        # Adding a semantically correct but unnecessary field violates canonical selection.
        action=self.sessions[0].rounds[0].action
        bad=src.replace('reading=TRUE',
                        'reading=TRUE, action=NAT(value="'+str(action)+'")',1)
        with self.assertRaises(lab.SelectionError):lab.decode(bad)

    def test_source_bound_and_garbage(self):
        for bad in ('', 'X'* (lab.MAX_SOURCE_CHARS+1), self.lean[0]+'garbage'):
            with self.assertRaises(lab.SelectionError):lab.decode(bad)

    def test_modified_session_not_encodable(self):
        bad=replace(self.sessions[0],total_spent=self.sessions[0].total_spent+1)
        with self.assertRaises(lab.SelectionError): lab.encode(bad)

    def test_open_append_keeps_initial_pins_and_prefix(self):
        s=self.sessions[3]
        src=lab.encode(s,2,1)
        extended=lab.append(src,False)
        rebuilt=lab.decode(extended)
        self.assertEqual(rebuilt.seed_sha256,s.seed_sha256)
        self.assertEqual(rebuilt.rounds[:len(s.rounds)],s.rounds)
        self.assertEqual(rebuilt, v23.build(s.id,s.initial.family,s.initial.budget,
                                            s.initial.loss,[True,False]))
        self.assertIn('min_actions=NAT(value="1")', extended)

    def test_stop_append_rejected(self):
        with self.assertRaises(lab.SelectionError):lab.append(self.lean[0],True)
        with self.assertRaises(lab.SelectionError):lab.append(self.lean[2],False)

    def test_nonboolean_append_rejected(self):
        for y in (0,1,'TRUE',None):
            with self.subTest(y=y), self.assertRaises(lab.SelectionError):
                lab.append(self.lean[3],y)

    def test_frozen_fixture_and_report_byte_exact(self):
        self.assertEqual(lab.SAMPLE_PATH.read_bytes(),lab.fixture_text().encode('utf-8'))
        self.assertEqual(lab.REPORT_PATH.read_bytes(),lab.report_text().encode('utf-8'))
        self.assertEqual(lab.check(),lab.report())

    def test_report_does_not_call_byte_reduction_semantic_comprehension(self):
        r=lab.report()
        self.assertFalse(r['real_world_or_independent_ai_test'])
        self.assertFalse(r['measured_replay_time'])
        self.assertFalse(r['fully_self_contained_without_public_rules'])
        self.assertEqual(r['cases'],5)
        self.assertEqual(r['rounds'],8)
        self.assertEqual(r['legacy_v024_bytes'],4962)
        self.assertGreater(r['profile_savings_vs_v024']['lean'],0)
        self.assertGreater(r['profile_totals']['audit'], r['profile_totals']['lean'])


if __name__=='__main__':
    unittest.main()
