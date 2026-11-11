"""ALCG v0.24 reversible delta receipts; no new semantic understanding claim."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from alcg import parse, render
import delta_language as lab
import session_language as full
import trace_language as t22
import correlated_design as policy

ROOT = Path(__file__).resolve().parents[1]


class DeltaSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = lab._sessions()
        cls.texts = [lab.encode(x) for x in cls.sessions]
        cls.two, cls.three, cls.stop, cls.open, cls.other = cls.sessions

    def test_fixed_session_count_and_kinds(self):
        self.assertEqual(len(self.sessions), 5)
        self.assertEqual(sum(len(s.rounds) for s in self.sessions), 8)
        self.assertEqual(sum(s.status == 'STOP' for s in self.sessions), 4)
        self.assertEqual(sum(s.status == 'OPEN' for s in self.sessions), 1)

    def test_all_delta_to_full_exact_bytes(self):
        for session, expr in zip(self.sessions, self.texts):
            with self.subTest(id=session.id):
                self.assertEqual(lab.expand(expr).encode('utf-8'),
                                 full.encode(session).encode('utf-8'))

    def test_full_to_delta_to_full_roundtrip(self):
        for s, expression in zip(self.sessions, self.texts):
            with self.subTest(id=s.id):
                self.assertEqual(lab.pack(full.encode(s)), expression)
                self.assertEqual(lab.decode(expression), s)

    def test_alcg_grammar_without_raw_unchanged(self):
        for line in self.texts:
            self.assertEqual(render(parse(line)), line)
            self.assertNotIn('RAW(', line)
            self.assertIn('DELTA_RUN_V024(', line)
            self.assertNotIn('TRACE_V022(', line)

    def test_replay_receipts_match_existing_v023_chain(self):
        for session, line in zip(self.sessions, self.texts):
            x = lab.decode(line)
            self.assertEqual(x.seed_sha256, session.seed_sha256)
            self.assertEqual(x.final_chain_sha256, session.final_chain_sha256)
            self.assertEqual(x.final_state_sha256, session.final_state_sha256)
            self.assertEqual(x.final_history_sha256, session.final_history_sha256)
            self.assertEqual([r.chain_sha256 for r in x.rounds],
                             [r.chain_sha256 for r in session.rounds])

    def test_policy_actions_and_budgets_are_derived(self):
        for s in self.sessions:
            budget = s.initial.budget
            current = s.initial
            for r in s.rounds:
                self.assertEqual(current.next_action, r.action)
                self.assertEqual(current.decision, 'CONTINUE')
                self.assertEqual(policy.action_cost(r.action), r.cost)
                budget -= r.cost
                self.assertEqual(r.after.budget, budget)
                current = r.after
            self.assertEqual(s.remaining, budget)

    def test_compact_savings_nonempty_and_zero_round(self):
        for s, line in zip(self.sessions, self.texts):
            self.assertLess(len(line.encode('utf-8')),
                            len(full.encode(s).encode('utf-8')))
        self.assertEqual(len(self.stop.rounds), 0)
        self.assertIn('STEPS_V024()', self.texts[2])
        self.assertEqual(lab.decode(self.texts[2]).status, 'STOP')

    def test_report_frozen_and_exact(self):
        observed = lab.check()
        stored = json.loads(lab.REPORT_PATH.read_text(encoding='utf-8'))
        self.assertEqual(stored, observed)
        self.assertEqual(observed['cases'], 5)
        self.assertEqual(observed['rounds'], 8)
        self.assertGreater(observed['saved_utf8_bytes'], 0)
        self.assertEqual(observed['total_full_utf8_bytes'] - observed['total_delta_utf8_bytes'],
                         observed['saved_utf8_bytes'])

    def test_each_per_case_byte_accounting_and_pins(self):
        report = lab.report()
        for row, session in zip(report['per_case'], self.sessions):
            self.assertEqual(row['id'], session.id)
            self.assertEqual(row['saved_utf8_bytes'],
                             row['full_v023_utf8_bytes'] - row['delta_v024_utf8_bytes'])
            self.assertTrue(row['byte_exact_expansion'])
        for name, expected in lab.PINNED_V023.items():
            self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(), expected)

    def test_fixture_file_is_exact_source(self):
        self.assertEqual(lab.SAMPLES_PATH.read_bytes(), lab.fixture_text().encode('utf-8'))
        self.assertEqual(lab.REPORT_PATH.read_bytes(), lab.report_text().encode('utf-8'))

    def test_open_prefix_is_not_a_completed_session(self):
        self.assertEqual(self.open.status, 'OPEN')
        self.assertEqual(lab.decode(self.texts[3]).status, 'OPEN')
        self.assertEqual(self.open.rounds[-1].after.decision, 'CONTINUE')

    def test_append_replays_the_actual_next_policy(self):
        extended = lab.append(self.texts[3], False)
        actual = lab.decode(extended)
        expected = full.build(self.open.id, self.open.initial.family,
                              self.open.initial.budget, self.open.initial.loss,
                              [r.reading for r in self.open.rounds] + [False])
        self.assertEqual(actual, expected)
        self.assertEqual(actual.rounds[0], self.open.rounds[0])
        self.assertEqual(actual.status, expected.status)
        self.assertNotEqual(actual.final_chain_sha256, self.open.final_chain_sha256)

    def test_append_after_stop_is_refused(self):
        for s in (self.stop, self.two):
            with self.assertRaises(lab.DeltaError):
                lab.append(lab.encode(s), True)

    def test_append_requires_boolean(self):
        for not_boolean in (0, 1, 'TRUE', None):
            with self.subTest(value=not_boolean), self.assertRaises(lab.DeltaError):
                lab.append(self.texts[3], not_boolean)

    def test_tamper_observation_is_rejected(self):
        raw = self.texts[0].replace('reading=TRUE', 'reading=FALSE', 1)
        self.assertNotEqual(raw, self.texts[0])
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_action_is_rejected(self):
        raw = self.texts[0].replace('action=NAT(value="3")', 'action=NAT(value="4")', 1)
        self.assertNotEqual(raw, self.texts[0])
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_step_link_is_rejected(self):
        raw = self.texts[0].replace('link_sha256=SHA256(value="',
                                    'link_sha256=SHA256(value="0', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_start_seed_is_rejected(self):
        raw = self.texts[0].replace('seed_sha256=SHA256(value="',
                                    'seed_sha256=SHA256(value="f', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_profile_is_rejected(self):
        raw = self.texts[0].replace('profile_sha256=SHA256(value="',
                                    'profile_sha256=SHA256(value="e', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_final_status_is_rejected(self):
        raw = self.texts[0].replace('status=STOP', 'status=OPEN', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_cost_is_rejected(self):
        raw = self.texts[0].replace('spent=NAT(value="2")',
                                    'spent=NAT(value="1")', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_tamper_final_chain_digest_is_rejected(self):
        raw = self.texts[0].replace('chain_sha256=SHA256(value="',
                                    'chain_sha256=SHA256(value="a', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_missing_step_or_gap_rejected(self):
        raw = self.texts[0].replace('r0002=STEP_V024(', 'r0003=STEP_V024(', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_duplicate_step_name_is_rejected(self):
        raw = self.texts[0].replace('r0002=STEP_V024(', 'r0001=STEP_V024(', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_unknown_field_fails_closed(self):
        raw = self.texts[0].replace('DELTA_RUN_V024(', 'DELTA_RUN_V024(extra=AI, ', 1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_wrong_protocol_or_origin_rejected(self):
        for a,b in [('protocol=V021_CORRELATED', 'protocol=OTHER'),
                    ('origin=SYNTHETIC', 'origin=REAL_WORLD')]:
            with self.subTest(field=a), self.assertRaises(lab.DeltaError):
                lab.decode(self.texts[0].replace(a,b,1))

    def test_noncanonical_nat_rejected(self):
        raw = self.texts[0].replace('budget=NAT(value="2")',
                                    'budget=NAT(value="02")',1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_wrong_reading_rejected(self):
        with self.assertRaises(lab.DeltaError):
            lab.decode(self.texts[0].replace('reading=TRUE','reading=MAYBE',1))

    def test_delta_cannot_claim_unsupported_family(self):
        raw = self.texts[0].replace('family=F17_DIRECT','family=F17_NOT_SUPPORTED',1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)

    def test_wrong_id_and_too_many_rounds_rejected(self):
        raw = self.texts[0].replace('id=R23_TWO_ROUNDS','id=OTHER',1)
        with self.assertRaises(lab.DeltaError):
            lab.decode(raw)
        with self.assertRaises(full.SessionError):
            full.build('R23_TOO_MANY','F17_DIRECT',2,64,[True]*5)

    def test_empty_trailing_garbage_and_oversize_rejected(self):
        for item in ('', self.texts[0] + 'garbage', 'X' * (lab.MAX_SOURCE_CHARS + 1)):
            with self.subTest(size=len(item)), self.assertRaises(lab.DeltaError):
                lab.decode(item)

    def test_changed_pins_are_rejected_before_replay(self):
        with patch.object(lab, 'PINNED_V023', {**lab.PINNED_V023,
                                              'session_language.py':'0'*64}):
            with self.assertRaises(lab.DeltaError):
                lab.decode(self.texts[0])

    def test_byte_equality_is_stronger_than_posteriors(self):
        self.assertNotEqual(self.three.initial.history_sha256,
                            self.three.final_history_sha256)
        self.assertEqual(lab.expand(self.texts[1]), full.encode(self.three))

    def test_rebuilt_entire_history_can_be_valid_not_authenticated(self):
        a = full.build('R23_SYNTHETIC_REWRITE','F17_DIRECT',2,64,[True,False])
        b = full.build('R23_SYNTHETIC_REWRITE','F17_DIRECT',2,64,[False,True])
        self.assertNotEqual(a.final_chain_sha256,b.final_chain_sha256)
        self.assertEqual(lab.decode(lab.encode(a)),a)
        self.assertEqual(lab.decode(lab.encode(b)),b)

    def test_cli_checks_are_repeatable(self):
        run = subprocess.run([sys.executable, 'delta_language.py', 'check'],
                             cwd=ROOT, text=True, capture_output=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('OK v0.24:', run.stdout)

    def test_cli_decode_and_expand_one_file(self):
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / 'case.alcg'
            path.write_text(self.texts[0] + '\n', encoding='utf-8')
            run = subprocess.run([sys.executable, 'delta_language.py', 'expand', str(path)],
                                 cwd=ROOT, text=True, capture_output=True, timeout=90)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(run.stdout.strip(),full.encode(self.two))


if __name__ == '__main__':
    unittest.main()
