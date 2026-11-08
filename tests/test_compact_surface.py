"""ALCG v0.10 positional surface tests: syntax, registry pinning and semantic caution."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alcg import parse, render
from compact_surface import (
    CompactError, EXAMPLES, LOCKED, PATTERNS, RISKS, check_cases,
    decode, encode, locked_patterns, parse_surface, risk_probes,
    structure_digest, tokenize,
)
from pattern_lab import BENCHMARK, SOURCE, sha256
from semantic_lab import compare, normalize

ROOT = Path(__file__).resolve().parents[1]


class CompactSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping = locked_patterns()
        cls.examples = [json.loads(s) for s in EXAMPLES.read_text(encoding='utf-8').splitlines()]
        cls.original = {r['id']: r for r in (json.loads(l) for l in SOURCE.read_text(encoding='utf-8').splitlines())}
        cls.named = {r['source_id']: r for r in (json.loads(l) for l in BENCHMARK.read_text(encoding='utf-8').splitlines())}

    def test_24_examples_preserve_canonical_expanded_structure(self):
        self.assertEqual(len(self.examples), 24)
        for row in self.examples:
            with self.subTest(sid=row['source_id']):
                full = decode(row['compact'], self.mapping)
                expected = self.original[row['source_id']]['expression']
                self.assertEqual(normalize(full), normalize(expected))
                self.assertEqual(encode(self.named[row['source_id']]['pattern'], self.mapping), row['compact'])

    def test_summary_counts_fixed_and_not_ai_comprehension(self):
        report = check_cases()
        self.assertEqual(report['frozen_cases'], 24)
        self.assertEqual(report['pattern_definitions'], 16)
        self.assertEqual(report['exact_expanded_canonical_roundtrips'], 24)
        self.assertEqual(set(report['domains'].values()), {4})
        self.assertEqual(report['characters'], {'original': 1459, 'named_pattern': 1457, 'compact': 853})
        self.assertEqual(report['registry_transfer_bytes'], 4684)
        self.assertEqual(report['one_batch_payload_plus_registry_bytes'], 5537)
        self.assertEqual(report['repeated_24_case_batches_to_amortize_registry'], 8)
        self.assertIsNone(report['independent_ai_comprehension_results'])
        self.assertEqual(report['new_relation_operators'], 0)
        self.assertEqual(report['new_english_coverage_claims'], 0)

    def test_locked_public_registry_same_sha(self):
        self.assertEqual(sha256(PATTERNS), LOCKED['patterns'][1])
        self.assertTrue(any(row['compact'].startswith('@') for row in self.examples))

    def test_unpinned_registry_refused(self):
        with patch.dict(LOCKED, {'patterns': (PATTERNS, '0'*64)}):
            with self.assertRaisesRegex(CompactError,'changed'):
                locked_patterns()

    def test_alias_simple_event(self):
        self.assertEqual(render(decode('@MAY_ACT2[SERVER|FAIL]', self.mapping)),
                         'MAY(claim=DO(actor=SERVER, action=FAIL))')

    def test_nested_quantifier_and_reference(self):
        shorthand = '@ALL[X|PERSON|@STATE[REF(var=X)|READY]]'
        expected = 'FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY))'
        self.assertEqual(normalize(decode(shorthand, self.mapping)), normalize(expected))

    def test_nested_negation_does_not_disappear(self):
        source = '@NOT[@ALL[X|PERSON|@STATE[REF(var=X)|READY]]]'
        self.assertEqual(normalize(decode(source, self.mapping)), normalize(
            'NOT(claim=FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))'))

    def test_native_alcg_and_compact_nesting(self):
        expr = 'WANT(agent=PERSON, goal=@ACT[AI|HELP|PERSON])'
        expanded = decode(expr, self.mapping)
        self.assertEqual(normalize(expanded), normalize(
            'WANT(agent=PERSON, goal=DO(actor=AI, action=HELP, object=PERSON))'))

    def test_native_named_pattern_still_supported(self):
        named = 'P_STATE(subject=WATER, property=LIQUID)'
        self.assertEqual(normalize(decode(named, self.mapping)),normalize(decode('@STATE[WATER|LIQUID]',self.mapping)))

    def test_named_argument_permutation_does_not_change_structure(self):
        a = 'WANT(goal=@ACT[AI|CREATE|LANGUAGE], agent=PERSON)'
        b = 'WANT(agent=PERSON, goal=@ACT[AI|CREATE|LANGUAGE])'
        self.assertEqual(normalize(decode(a,self.mapping)), normalize(decode(b,self.mapping)))
        self.assertEqual(structure_digest(a,self.mapping), structure_digest(b,self.mapping))

    def test_primitive_cannot_assume_unknown_as_a_registered_pattern(self):
        with self.assertRaisesRegex(CompactError,'unknown positional alias'):
            decode('@UNKNOWN[AI|WATER]',self.mapping)

    def test_wrong_arity_never_silently_fills_fields(self):
        for expr in ('@ACT[PROGRAM|READ]', '@ACT[PROGRAM|READ|FILE|EXTRA]', '@STATE[]', '@STATE[WATER|]'):
            with self.subTest(expr=expr), self.assertRaises(CompactError):
                decode(expr,self.mapping)

    def test_invalid_delimiters_and_trailing_tokens_rejected(self):
        for expr in ('@STATE[WATER|LIQUID', '@STATE[WATER|LIQUID]]', '@STATE[WATER,LIQUID]',
                     '@STATE(WATER|LIQUID)', '@NOT[', '@STATE[WATER|LIQUID] MORE', ''):
            with self.subTest(expr=expr), self.assertRaises(CompactError):
                decode(expr,self.mapping)

    def test_quotes_and_raw_are_explicitly_unsupported(self):
        for expr in ('@STATE["WATER"|LIQUID]', 'RAW(text="original English")'):
            with self.subTest(expr=expr), self.assertRaises(CompactError):
                decode(expr,self.mapping)

    def test_stray_non_ascii_or_bad_symbols_rejected(self):
        for expr in ('@STATE[水|LIQUID]','@STATE[WATER|L!QUID]', '@STATE[WATER|LIQUID]#comment'):
            with self.subTest(expr=expr), self.assertRaises(CompactError):
                tokenize(expr)

    def test_unbound_reference_fails_even_under_partial_semantics(self):
        with self.assertRaisesRegex(CompactError,'unbound variable'):
            decode('@STATE[REF(var=X)|READY]',self.mapping)

    def test_named_duplicate_keys_fails(self):
        with self.assertRaisesRegex(CompactError,'duplicate named role'):
            decode('IS(subject=WATER, subject=EARTH, property=PLANET)',self.mapping)

    def test_quote_and_holed_template_injection_disallowed(self):
        for expr in ('@STATE[HOLE(slot=who)|READY]','@STATE["HELLO"|READY]'):
            with self.subTest(expr=expr), self.assertRaises(CompactError):
                decode(expr,self.mapping)

    def test_parenthesis_and_brackets_have_separate_scopes(self):
        a='@NOT[@STATE[WATER|LIQUID]]'
        b='@NOT[IS(subject=WATER,property=LIQUID)]'
        self.assertEqual(normalize(decode(a,self.mapping)),normalize(decode(b,self.mapping)))

    def test_depth_and_source_budget(self):
        with self.assertRaises(CompactError):
            decode('@NOT[' * 90 + '@STATE[WATER|LIQUID]' + ']' * 90,self.mapping)
        with self.assertRaisesRegex(CompactError,'32768'):
            tokenize(' ' * 32769)

    def test_known_structure_digest_and_modified_role(self):
        original='@ACT[PROGRAM|READ|FILE]'
        wrong='@ACT[FILE|READ|PROGRAM]'
        self.assertEqual(len(structure_digest(original,self.mapping)),64)
        self.assertNotEqual(structure_digest(original,self.mapping),structure_digest(wrong,self.mapping))

    def test_missing_modality_is_not_syntactically_rejected_but_differs(self):
        a='@MAY_ACT2[SERVER|FAIL]'
        b='@ACT2[SERVER|FAIL]'
        self.assertNotEqual(normalize(decode(a,self.mapping)),normalize(decode(b,self.mapping)))

    def test_ten_fixed_risk_probes(self):
        report=risk_probes(self.mapping)
        self.assertEqual(report['risk_cases'],10)
        self.assertEqual(report['malformed_rejected'],4)
        self.assertEqual(report['canonical_drift_detected'],6)
        self.assertEqual(report['finite_world_counterexamples'],2)

    def test_finite_model_counterexamples_are_observed_not_general_proofs(self):
        a=decode('@ALL[X|PERSON|@STATE[REF(var=X)|READY]]',self.mapping)
        b=decode('@SOME[X|PERSON|@STATE[REF(var=X)|READY]]',self.mapping)
        result=compare(render(a), render(b))
        self.assertIsNotNone(result.first_witness)
        self.assertEqual(result.relation, 'distinguishable')

    def test_original_cases_frozen_against_silent_edits(self):
        cases=list(self.examples)
        cases[0]=dict(cases[0],compact='@STATE[WATER|LIQUID]')
        with TemporaryDirectory() as temp:
            p=Path(temp)/'changed.jsonl'
            p.write_text('\n'.join(json.dumps(row) for row in cases)+'\n',encoding='utf8')
            with self.assertRaisesRegex(CompactError,'fixture differs'):
                check_cases(examples=p)

    def test_risk_probes_detect_swapped_expectation(self):
        rows=[json.loads(line) for line in RISKS.read_text(encoding='utf8').splitlines()]
        rows[0]['expected']='structural_drift'
        with TemporaryDirectory() as temp:
            p=Path(temp)/'bad.jsonl'
            p.write_text('\n'.join(json.dumps(row) for row in rows)+'\n',encoding='utf8')
            with self.assertRaises(CompactError):
                risk_probes(self.mapping,path=p)

    def test_cli_check_report_encode_decode_digest(self):
        for args, expected in [
            (['check'],'24 compact roundtrips'),
            (['report'],'"compact": 853'),
            (['encode','P_STATE(subject=WATER,property=LIQUID)'],'@STATE[WATER|LIQUID]'),
            (['decode','@STATE[WATER|LIQUID]'],'IS(subject=WATER, property=LIQUID)'),
        ]:
            with self.subTest(args=args):
                process=subprocess.run([sys.executable,'compact_surface.py',*args], cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(process.returncode,0,process.stderr)
                self.assertIn(expected,process.stdout)

    def test_cli_digest_guard_fails_on_corruption(self):
        s='@STATE[WATER|LIQUID]'
        digest=structure_digest(s,self.mapping)
        pass_cmd=subprocess.run([sys.executable,'compact_surface.py','decode',s,'--expect-sha256',digest],cwd=ROOT,capture_output=True,text=True)
        fail_cmd=subprocess.run([sys.executable,'compact_surface.py','decode','@STATE[EARTH|PLANET]','--expect-sha256',digest],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(pass_cmd.returncode,0,pass_cmd.stderr)
        self.assertEqual(fail_cmd.returncode,1)
        self.assertIn('digest mismatch',fail_cmd.stderr)

    def test_cli_export_does_not_overwrite_and_exports_24(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'expanded.jsonl'
            cmd=[sys.executable,'compact_surface.py','export','--out',str(path)]
            a=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            b=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(a.returncode,0,a.stderr)
            self.assertEqual(b.returncode,1)
            rows=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
            self.assertEqual(len(rows),24)
            self.assertEqual(rows[0]['reference_sha256'],structure_digest(rows[0]['compact'],self.mapping))

    def test_checked_in_report_reproducible(self):
        report=ROOT/'reports/compact-surface-v0.10.json'
        self.assertEqual(json.loads(report.read_text(encoding='utf8')),check_cases())


if __name__=='__main__':
    unittest.main()
