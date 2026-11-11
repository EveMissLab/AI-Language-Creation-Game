"""ALCG v0.23 multi-step receipt tests, including adversarial trace edits."""
import dataclasses
from hashlib import sha256
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from alcg import Call, parse, render
import correlated_design as model
import session_language as lab
import trace_language as v22

ROOT = Path(__file__).resolve().parents[1]


class LinkedSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = lab._cases()
        cls.records = [lab._build_case(c) for c in cls.cases]
        cls.lines = [line for line in lab.fixture_text().splitlines() if line and not line.startswith('#')]
        cls.two, cls.three, cls.stop, cls.open, cls.other = cls.records

    def test_sample_count_and_report(self):
        report = lab.check()
        self.assertEqual((report['sessions'], report['rounds']), (5, 8))
        self.assertEqual((report['terminal_stops'], report['open_prefixes']), (4,1))
        self.assertEqual(report['spent_units'], 8)

    def test_all_roundtrip_byte_exact(self):
        for line in self.lines:
            with self.subTest(line=line[:30]):
                self.assertEqual(lab.encode(lab.decode(line)), line)

    def test_existing_alcg_parser_and_no_raw(self):
        self.assertTrue(all(render(parse(x)) == x for x in self.lines))
        self.assertTrue(all('RAW(' not in x for x in self.lines))
        self.assertTrue(all('RUN_V023(' in x and 'TRACE_V022(' in x for x in self.lines))

    def test_fixture_bytes_canonical(self):
        self.assertEqual(lab.SAMPLES_PATH.read_bytes(), lab.fixture_text().encode('utf-8'))
        self.assertEqual(lab.REPORT_PATH.read_bytes(), lab.report_text().encode('utf-8'))

    def test_v022_artifacts_are_pinned(self):
        for path,digest in ((v22.SAMPLES_PATH, lab.PINNED_V022_SAMPLE_SHA256),
                            (v22.REPORT_PATH, lab.PINNED_V022_REPORT_SHA256),
                            (v22.CASES_PATH, lab.PINNED_V022_CASES_SHA256)):
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), digest)

    def test_replay_true_actions_for_two_rounds(self):
        self.assertEqual([r.action for r in self.two.rounds], [3,4])
        self.assertEqual(self.two.initial.decision, 'CONTINUE')
        self.assertEqual(self.two.remaining, 0)
        self.assertEqual(self.two.status, 'STOP')
        self.assertEqual([r.cost for r in self.two.rounds],[1,1])

    def test_replay_three_rounds(self):
        self.assertEqual([r.action for r in self.three.rounds], [3,3,4])
        self.assertEqual([r.reading for r in self.three.rounds], [False,True,False])
        self.assertEqual(self.three.remaining,0)
        self.assertEqual(self.three.total_spent,3)

    def test_budget_conservation_every_prefix(self):
        for session in self.records:
            remaining = session.initial.budget
            total = 0
            for rnd in session.rounds:
                self.assertEqual(rnd.cost, model.action_cost(rnd.action))
                total += rnd.cost
                remaining -= rnd.cost
                self.assertEqual(rnd.after.budget, remaining)
            self.assertEqual((session.total_spent,session.remaining), (total,remaining))

    def test_prior_policy_action_is_followed(self):
        for session in self.records:
            current = session.initial
            for rnd in session.rounds:
                self.assertEqual(current.decision, 'CONTINUE')
                self.assertEqual(current.next_action, rnd.action)
                current = rnd.after

    def test_each_round_matches_full_v022_replay(self):
        for session in self.records:
            history=[]
            for rnd in session.rounds:
                history.append({'action_id':rnd.action,'observed_Y':rnd.reading})
                expected=v22.build(session.initial.family,history,rnd.after.budget,session.initial.loss)
                self.assertEqual(rnd.after,expected)

    def test_history_is_cumulative_and_ordered(self):
        h=[]
        for rnd in self.three.rounds:
            h.append((rnd.action,rnd.reading))
            self.assertEqual(list(rnd.after.observations),h)

    def test_stop_zero_rounds_is_real_stop(self):
        self.assertEqual(self.stop.initial.decision,'STOP')
        self.assertEqual(self.stop.rounds,())
        self.assertEqual(self.stop.total_spent,0)
        self.assertEqual(self.stop.status,'STOP')

    def test_open_is_not_stopped(self):
        self.assertEqual(self.open.status,'OPEN')
        self.assertEqual(self.open.rounds[-1].after.decision,'CONTINUE')
        self.assertGreater(self.open.remaining,0)
        more=lab.build('R23_OPEN_PREFIX','F17_DIRECT',3,64,[True,False])
        self.assertEqual(len(more.rounds),2)
        self.assertEqual(more.rounds[0],self.open.rounds[0])
        self.assertNotEqual(more.final_chain_sha256,self.open.final_chain_sha256)

    def test_cannot_append_after_stop(self):
        with self.assertRaises(lab.SessionError):
            lab.build('R23_START_STOP','F17_DIRECT',2,8,[True])
        with self.assertRaises(lab.SessionError):
            lab.build('R23_TWO_ROUNDS','F17_DIRECT',2,64,[True,False,True])

    def test_truncation_undetected_if_only_valid_prefix_explicitly_open(self):
        prefix=lab.build('R23_TWO_ROUNDS','F17_DIRECT',2,64,[True])
        self.assertEqual(prefix.status,'OPEN')
        self.assertNotEqual(prefix.final_chain_sha256,self.two.final_chain_sha256)
        self.assertEqual(lab.decode(lab.encode(prefix)),prefix)

    def test_chain_is_bound_to_id(self):
        a=lab.build('R23_A','F17_DIRECT',2,64,[True,False])
        b=lab.build('R23_B','F17_DIRECT',2,64,[True,False])
        self.assertEqual(a.rounds[-1].after,b.rounds[-1].after)
        self.assertNotEqual(a.seed_sha256,b.seed_sha256)
        self.assertNotEqual(a.final_chain_sha256,b.final_chain_sha256)

    def test_chain_is_order_sensitive(self):
        a=lab.build('R23_ORDER','F17_DIRECT',2,64,[True,False])
        b=lab.build('R23_ORDER','F17_DIRECT',2,64,[False,True])
        self.assertNotEqual(a.final_chain_sha256,b.final_chain_sha256)
        self.assertNotEqual(a.final_history_sha256,b.final_history_sha256)

    def test_chain_recomputes_from_previous_digest(self):
        current=lab._seed(self.three.id,self.three.initial)
        before=self.three.initial
        for round in self.three.rounds:
            current=lab._link(self.three.id,current,before,round.index,
                              round.action,round.reading,round.cost,round.after)
            self.assertEqual(current,round.chain_sha256)
            self.assertEqual(round.before_trace_sha256, lab._trace_hash(before))
            before=round.after
        self.assertEqual(current,self.three.final_chain_sha256)

    def test_tamper_action_rejected(self):
        orig=self.lines[0]
        bad=orig.replace('action=NAT(value="3")','action=NAT(value="4")',1)
        self.assertNotEqual(orig,bad)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_observation_rejected(self):
        bad=self.lines[0].replace('reading=TRUE','reading=FALSE',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_cost_rejected(self):
        bad=self.lines[0].replace('cost=NAT(value="1")','cost=NAT(value="2")',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_intermediate_history_rejected(self):
        bad=self.lines[0].replace('history_sha256=SHA256(value="',
                                  'history_sha256=SHA256(value="f',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_intermediate_policy_rejected(self):
        bad=self.lines[0].replace('decision=CONTINUE','decision=STOP',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_end_state_rejected(self):
        bad=self.lines[0].replace('status=STOP','status=OPEN',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_end_cumulative_spent_rejected(self):
        bad=self.lines[0].replace('spent=NAT(value="2")','spent=NAT(value="1")',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_tamper_chain_rejected(self):
        bad=self.lines[0].replace('chain_sha256=SHA256(value="',
                                  'chain_sha256=SHA256(value="0',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_duplicate_or_gapped_rounds_rejected(self):
        orig=self.lines[0]
        bad=orig.replace('r0002=ROUND_V023(', 'r0003=ROUND_V023(', 1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)
        bad=orig.replace('r0002=ROUND_V023(', 'r0001=ROUND_V023(', 1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_schema_rejects_unknown_field(self):
        bad=self.lines[0].replace('RUN_V023(', 'RUN_V023(extra=AI, ',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_unknown_origin_or_protocol_is_rejected(self):
        bad=self.lines[0].replace('origin=SYNTHETIC','origin=REAL_WORLD',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_reading_type_rejected(self):
        bad=self.lines[0].replace('reading=TRUE','reading=MAYBE',1)
        with self.assertRaises(lab.SessionError): lab.decode(bad)

    def test_invalid_limits_and_int_boolean(self):
        cases=[('foo','F17_DIRECT',2,64,[]),
               ('R23_B','F17_DIRECT',-1,64,[]),
               ('R23_B','F17_DIRECT',2,64,[1]),
               ('R23_B','F17_DIRECT',2,64,'101'),
               ('R23_B','F17_DIRECT',2,64,[True]*5)]
        for case in cases:
            with self.subTest(case=str(case)[:45]), self.assertRaises(lab.SessionError):
                lab.build(*case)

    def test_invalid_text_or_recursive_parse_fails_closed(self):
        for x in ['', 'RUN_V023(', 'X'* (lab.MAX_CHARS+1)]:
            with self.subTest(inp=x[:20]), self.assertRaises(lab.SessionError):
                lab.decode(x)

    def test_field_order_not_significant(self):
        ast=parse(self.lines[0])
        self.assertIsInstance(ast,Call)
        reord=render(Call(ast.name,tuple(reversed(ast.args))))
        self.assertEqual(lab.decode(reord),self.two)

    def test_forged_dataclass_cannot_be_encoded(self):
        altered=dataclasses.replace(self.two,total_spent=400)
        with self.assertRaises(lab.SessionError): lab.encode(altered)

    def test_v022_pin_tamper_fails_even_after_cache(self):
        lab.build('R23_PIN','F17_DIRECT',2,64,[])
        with tempfile.TemporaryDirectory() as temp:
            bogus=Path(temp)/'trace-language-v0.22.json'
            bogus.write_text('{}',encoding='utf-8')
            with patch.object(v22,'REPORT_PATH',bogus):
                with self.assertRaises(lab.SessionError):
                    lab.build('R23_PIN','F17_DIRECT',2,64,[])

    def test_cli_replay_and_check(self):
        result=subprocess.run([sys.executable,'session_language.py','check'],cwd=ROOT,
                              capture_output=True,text=True,timeout=35)
        self.assertEqual(result.returncode,0,result.stderr)
        x=subprocess.run([sys.executable,'session_language.py','replay', '--id','R23_TWO_ROUNDS'],
                         cwd=ROOT,capture_output=True,text=True,timeout=35)
        self.assertEqual(x.returncode,0,x.stderr)
        self.assertEqual(json.loads(x.stdout)['rounds'][0]['action'],3)


if __name__ == '__main__':
    unittest.main()
