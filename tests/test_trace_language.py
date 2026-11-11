"""v0.22 strict typed decision-trace schema and replay adversarial tests."""
import dataclasses
from fractions import Fraction
from pathlib import Path
import re
import subprocess
import sys
import unittest

from alcg import Call, Name, parse, render
import correlated_design as source
import trace_language as lab


ROOT = Path(__file__).resolve().parents[1]


class TraceLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = lab._cases()
        cls.lines = lab.fixture_lines()
        cls.records = [lab.decode(s) for s in cls.lines]
        cls.initial_stop = cls.lines[0]
        cls.initial_continue = cls.lines[1]
        cls.single = cls.lines[2]
        cls.contradictory = cls.lines[3]

    def test_all_fixture_records_roundtrip(self):
        self.assertEqual(len(self.lines), 8)
        self.assertEqual([lab.encode(lab.decode(x)) for x in self.lines], self.lines)

    def test_all_examples_use_existing_parser(self):
        for line in self.lines:
            with self.subTest(line=line[:40]):
                self.assertEqual(render(parse(line)), line)

    def test_no_RAW_or_opaque_english_fallback(self):
        self.assertFalse(any('RAW(' in line for line in self.lines))
        self.assertFalse(any('ORIGINAL_ENGLISH' in line for line in self.lines))

    def test_no_new_published_operators_and_known_narrow_profile(self):
        self.assertTrue(all(isinstance(parse(line), Call) and parse(line).name == 'TRACE_V022'
                            for line in self.lines))
        self.assertIn('protocol=V021_CORRELATED', self.initial_continue)

    def test_fixture_bytes_and_report_recompute(self):
        self.assertEqual(lab.SAMPLES_PATH.read_bytes(), lab.fixture_text().encode('utf-8'))
        self.assertEqual(lab.REPORT_PATH.read_bytes(), lab.report_text().encode('utf-8'))
        self.assertEqual(lab.check()['case_count'], 8)

    def test_report_is_explicitly_synthetic(self):
        report = lab.report()
        self.assertTrue(report['no_empirical_evidence'])
        self.assertTrue(report['no_independent_ai_comprehension_scores'])
        self.assertTrue(report['published_language_dictionary_unchanged'])
        self.assertEqual(report['decision_counts'], {'STOP': 2, 'CONTINUE': 6})

    def test_stop_and_continue_are_both_represented(self):
        a, b = self.records[:2]
        self.assertEqual((a.decision,a.next_action), ('STOP',None))
        self.assertEqual((b.decision,b.next_action), ('CONTINUE',3))
        self.assertEqual(a.stop_risk, a.optimal_risk)
        self.assertLess(b.optimal_risk, b.stop_risk)

    def test_exact_fraction_receipts_match_v21_joint_posterior(self):
        r = self.records[3]
        row = source.pinned_rows()[r.family]
        observations = r.as_json()['observations']
        joint = source.posterior(row, observations)
        self.assertEqual(r.max_mask_probability, max(source.mask_posterior(joint)))
        self.assertEqual(r.session_fault_probability, source.fault_posterior(joint))
        self.assertEqual(r.stop_risk, source.stop_loss(joint, r.loss))
        self.assertEqual(r.state_sha256, lab._state_sha(joint))

    def test_receipt_is_exact_normalized_rational(self):
        for record in self.records:
            self.assertEqual(record.stop_risk.denominator > 0, True)
            self.assertEqual(record.optimal_risk.denominator > 0, True)
            self.assertEqual(Fraction(record.max_mask_probability), record.max_mask_probability)

    def test_ordered_observation_history_has_own_digest(self):
        a = self.records[3]
        reverse = lab.build(a.family,
                            [{'action_id': v, 'observed_Y': y} for v, y in reversed(a.observations)],
                            a.budget, a.loss)
        self.assertEqual(reverse.state_sha256, a.state_sha256)
        self.assertNotEqual(reverse.history_sha256, a.history_sha256)

    def test_schema_field_order_can_be_reordered_without_changing_meaning(self):
        source_text = self.initial_continue
        self.assertIn('scenario=SCENARIO(', source_text)
        self.assertIn('evidence=OBSERVATIONS()', source_text)
        # Named arguments are independent of presentation order.
        expr = parse(source_text)
        assert isinstance(expr, Call)
        reshuffled = Call(expr.name, tuple(reversed(expr.args)))
        self.assertEqual(lab.decode(render(reshuffled)), self.records[1])
        self.assertEqual(lab.encode(lab.decode(render(reshuffled))), source_text)

    def test_whitespace_variants_canonicalize(self):
        self.assertEqual(lab.decode('  ' + self.initial_continue + '  '), self.records[1])

    def test_tamper_observation_reading_rejected(self):
        changed = self.single.replace('reading=TRUE', 'reading=FALSE', 1)
        self.assertNotEqual(changed, self.single)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_observation_action_rejected(self):
        changed = self.single.replace('action=NAT(value="3")', 'action=NAT(value="4")', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_history_receipt_rejected(self):
        changed = self.contradictory.replace('history_sha256=SHA256(value="',
                                              'history_sha256=SHA256(value="0', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_state_digest_rejected(self):
        changed = self.single.replace('state_sha256=SHA256(value="',
                                      'state_sha256=SHA256(value="f', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_profile_fingerprint_rejected(self):
        changed = self.initial_continue.replace('spec_sha256=SHA256(value="',
                                                'spec_sha256=SHA256(value="0', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_decision_rejected(self):
        changed = self.initial_continue.replace('decision=CONTINUE', 'decision=STOP', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_next_action_rejected(self):
        changed = self.initial_continue.replace('next=NAT(value="3")', 'next=NONE', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_tamper_numerical_risk_rejected(self):
        changed = re.sub(r'(optimal_risk=RAT\(n=")([0-9]+)',
                         lambda m: m.group(1) + str(int(m.group(2)) + 1),
                         self.initial_continue, count=1)
        self.assertNotEqual(changed, self.initial_continue)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_unknown_field_rejected(self):
        changed = self.initial_continue.replace('scenario=SCENARIO(',
                                                'unused=AI, scenario=SCENARIO(', 1)
        with self.assertRaises(lab.TraceError): lab.decode(changed)

    def test_wrong_top_level_operator_rejected(self):
        with self.assertRaises(lab.TraceError):
            lab.decode(self.initial_continue.replace('TRACE_V022(', 'RAW(', 1))

    def test_wrong_origin_and_protocol_rejected(self):
        for what, change in [('origin=SYNTHETIC','origin=REAL_WORLD'),
                             ('protocol=V021_CORRELATED','protocol=V020_NOISE')]:
            with self.subTest(change=change), self.assertRaises(lab.TraceError):
                lab.decode(self.initial_continue.replace(what,change,1))

    def test_duplicate_or_gap_observation_indices_rejected(self):
        x = self.contradictory.replace('e0002=OBS(', 'e0003=OBS(', 1)
        with self.assertRaises(lab.TraceError): lab.decode(x)
        x = self.contradictory.replace('e0002=OBS(', 'e0001=OBS(', 1)
        with self.assertRaises(lab.TraceError): lab.decode(x)

    def test_negative_noncanonical_and_out_of_range_nat_rejected(self):
        for value in ('-1','03','8','99999999999'):
            altered = self.single.replace('action=NAT(value="3")', f'action=NAT(value="{value}")',1)
            with self.subTest(value=value), self.assertRaises(lab.TraceError):
                lab.decode(altered)

    def test_budget_and_loss_bounds(self):
        for budget, loss in [(-1,64),(5,64),(2,-1),(2,10001),(True,1)]:
            with self.subTest(budget=budget, loss=loss), self.assertRaises(lab.TraceError):
                lab.build('F17_DIRECT', [], budget, loss)

    def test_unknown_family(self):
        with self.assertRaises(lab.TraceError):
            lab.build('F17_NOT_DEFINED',[],2,64)

    def test_invalid_observations_fail_closed(self):
        for observations in ([{'action_id':0,'observed_Y':1}],
                             [{'action_id':True,'observed_Y':False}],
                             [{'action_id':2,'observed_Y':False,'unused':'X'}],
                             'not-a-history',
                             [{'action_id':0,'observed_Y':False}]*33):
            with self.subTest(sample=str(observations)[:40]), self.assertRaises(lab.TraceError):
                lab.build('F17_DIRECT',observations,2,64)

    def test_32_observation_bound_is_supported(self):
        events = [{'action_id':3,'observed_Y':True}]*32
        record = lab.build('F17_DIRECT',events,0,8)
        self.assertEqual(lab.decode(lab.encode(record)),record)

    def test_invalid_syntax_and_oversized_payload_fail(self):
        for source_text in ['', 'garbage', 'TRACE_V022(', 'X' * (lab.MAX_EXPRESSION_CHARS+1)]:
            with self.subTest(source_text=source_text[:30]), self.assertRaises(lab.TraceError):
                lab.decode(source_text)

    def test_self_forged_record_rejected_by_encoder(self):
        original = self.records[1]
        forged = dataclasses.replace(original, decision='STOP', next_action=None)
        with self.assertRaises(lab.TraceError): lab.encode(forged)

    def test_cli_check_and_build(self):
        check = subprocess.run([sys.executable, 'trace_language.py', 'check'],
                               cwd=ROOT, text=True, capture_output=True,timeout=25)
        self.assertEqual(check.returncode,0,check.stderr)
        built = subprocess.run([sys.executable, 'trace_language.py', 'build', '--budget','2','--loss','64'],
                               cwd=ROOT,text=True,capture_output=True,timeout=25)
        self.assertEqual(built.returncode,0,built.stderr)
        self.assertEqual(lab.decode(built.stdout.strip()),self.records[1])


if __name__ == '__main__':
    unittest.main()
