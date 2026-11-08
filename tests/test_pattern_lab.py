"""v0.8 transparent composition patterns: syntax, capture safety, frozen corpus."""
import copy
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from alcg import Call, Name, parse, render
from finite_probe import FiniteModel, evaluate
from pattern_lab import PatternError, PATTERNS, BENCHMARK, SOURCE, RELATIONS, check, expand, export, load_patterns, sha256
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parents[1]


class PatternLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_patterns()
        cls.source = {r['id']: r for r in (json.loads(l) for l in SOURCE.read_text(encoding='utf-8').splitlines())}

    def test_24_frozen_roundtrips_six_domains(self):
        report = check(self.patterns)
        self.assertEqual(report['roundtrip_cases'], 24)
        self.assertEqual(report['exact_canonical_roundtrips'], 24)
        self.assertEqual(report['pattern_definitions'], 16)
        self.assertEqual(set(report['domains'].values()), {4})
        self.assertEqual(report['new_relation_operators'], 0)
        self.assertIsNone(report['independent_ai_reader_results'])

    def test_nested_expansions_preserve_original_structures(self):
        for row in (json.loads(l) for l in BENCHMARK.read_text(encoding='utf-8').splitlines()):
            with self.subTest(source_id=row['source_id']):
                result = expand(row['pattern'], self.patterns)
                self.assertEqual(normalize(result), normalize(self.source[row['source_id']]['expression']))
                self.assertNotIn('P_', render(result))
                self.assertNotIn('HOLE(', render(result))

    def test_named_arguments_permutation_preserves_canonical_output(self):
        a = expand('P_STATE(subject=WATER, property=LIQUID)', self.patterns)
        b = expand('P_STATE(property=LIQUID, subject=WATER)', self.patterns)
        self.assertEqual(normalize(a),normalize(b))

    def test_possible_does_not_become_actual(self):
        model = FiniteModel.load(ROOT/'data/finite-world-v0.4.json')
        possible = expand('P_MAY_ACT2(actor=SERVER, action=FAIL)', self.patterns)
        self.assertEqual(render(possible), 'MAY(claim=DO(actor=SERVER, action=FAIL))')
        # The derived syntax retains MAY instead of silently asserting failure.
        self.assertNotEqual(normalize(possible), normalize('NOT(claim=IS(subject=SYSTEM, property=READY))'))

    def test_quantifier_scope_preserved(self):
        source = 'P_NOT(claim=P_ALL(var=X, domain=PERSON, claim=P_STATE(subject=REF(var=X), property=READY)))'
        expected = 'NOT(claim=FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))'
        self.assertEqual(normalize(expand(source, self.patterns)), normalize(expected))

    def test_shadowing_is_explicit_not_hidden(self):
        source = 'P_ALL(var=X, domain=PERSON, claim=P_SOME(var=X, domain=PERSON, claim=P_STATE(subject=REF(var=X), property=READY)))'
        result = expand(source, self.patterns)
        self.assertEqual(normalize(result), normalize('FORALL(var=X, domain=PERSON, claim=EXISTS(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))'))

    def test_free_reference_is_rejected_even_when_nested(self):
        with self.assertRaisesRegex(PatternError,'unbound variable'):
            expand('P_STATE(subject=REF(var=Z), property=READY)', self.patterns)

    def test_binder_requires_explicit_name(self):
        with self.assertRaises(PatternError):
            expand('P_ALL(var=P_STATE(subject=A, property=B), domain=PERSON, claim=P_STATE(subject=A,property=B))', self.patterns)

    def test_hidden_placeholder_as_user_expression_rejected(self):
        for s in ['HOLE(slot=subject)', 'P_STATE(subject=HOLE(slot=subject), property=READY)']:
            with self.subTest(s=s), self.assertRaisesRegex(PatternError,'HOLE is legal only'):
                expand(s, self.patterns)

    def test_unknown_or_missing_pattern_role(self):
        for s in ['P_STATE(subject=WATER)','P_STATE(subject=WATER,property=LIQUID,other=X)']:
            with self.subTest(s=s), self.assertRaisesRegex(PatternError, 'needs exactly'):
                expand(s, self.patterns)

    def test_raw_and_string_leak_rejected(self):
        for s in ['P_NOT(claim=RAW(text="secret"))','P_STATE(subject="plain text",property=TRUE)']:
            with self.subTest(s=s), self.assertRaisesRegex(PatternError, 'structured text'):
                expand(s, self.patterns)

    def test_unknown_relation_rejected(self):
        with self.assertRaisesRegex(PatternError,'unregistered relation'):
            expand('P_NOT(claim=MAGIC(what=ALICE))', self.patterns)

    def test_depth_budget_rejected(self):
        with self.assertRaisesRegex(PatternError,'budget'):
            expand('P_BEFORE_ACTS(actor=PROGRAM,first=CHECK,second=DELETE,object=FILE)', self.patterns,budget=3)

    def test_cycle_in_registry_rejected(self):
        doc = json.loads(PATTERNS.read_text(encoding='utf-8'))
        doc['patterns'].append({'name':'P_CYCLE','slots':['x'], 'template':'P_CYCLE(x=HOLE(slot=x))','gloss':'This entry must fail cyclic validation.'})
        with TemporaryDirectory() as temp:
            path=Path(temp)/'bad.json'
            path.write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaisesRegex(PatternError,'cycle'):
                load_patterns(path)

    def test_undeclared_slot_rejected(self):
        doc=json.loads(PATTERNS.read_text(encoding='utf-8'))
        doc['patterns'][0]['template']='IS(subject=HOLE(slot=missing), property=HOLE(slot=property))'
        with TemporaryDirectory() as temp:
            path=Path(temp)/'bad.json'
            path.write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaisesRegex(PatternError,'undeclared HOLE'):
                load_patterns(path)

    def test_implicit_binder_rejected(self):
        doc=json.loads(PATTERNS.read_text(encoding='utf-8'))
        doc['patterns'][0]['template']='FORALL(var=X, domain=PERSON, claim=IS(subject=HOLE(slot=subject), property=HOLE(slot=property)))'
        with TemporaryDirectory() as temp:
            path=Path(temp)/'bad.json'
            path.write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaisesRegex(PatternError,'caller-supplied HOLE'):
                load_patterns(path)

    def test_hidden_literal_ref_rejected(self):
        doc=json.loads(PATTERNS.read_text(encoding='utf-8'))
        doc['patterns'][0]['template']='IS(subject=REF(var=X), property=HOLE(slot=property))'
        with TemporaryDirectory() as temp:
            path=Path(temp)/'bad.json'
            path.write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaisesRegex(PatternError,'caller-supplied HOLE'):
                load_patterns(path)

    def test_raw_hidden_in_pattern_rejected(self):
        doc=json.loads(PATTERNS.read_text(encoding='utf-8'))
        doc['patterns'][0]['template']='RAW(text=HOLE(slot=subject))'
        with TemporaryDirectory() as temp:
            path=Path(temp)/'bad.json'
            path.write_text(json.dumps(doc),encoding='utf-8')
            with self.assertRaisesRegex(PatternError,'RAW/PARTIAL'):
                load_patterns(path)

    def test_frozen_input_detects_modified_benchmark(self):
        doc=json.loads(BENCHMARK.read_text(encoding='utf-8').splitlines()[0])
        doc['pattern']='P_STATE(subject=WATER, property=LIQUID)'
        lines=BENCHMARK.read_text(encoding='utf-8').splitlines()
        lines[0]=json.dumps(doc)
        with TemporaryDirectory() as temp:
            f=Path(temp)/'modified.jsonl'
            f.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            with self.assertRaisesRegex(PatternError, 'changes the original structure'):
                check(self.patterns, f)

    def test_export_preserves_references_and_nonblind_label(self):
        exported=export(BENCHMARK, self.patterns)
        self.assertEqual(len(exported),24)
        self.assertEqual(set(exported[0]),{'source_id','pattern','expanded','reference'})
        self.assertEqual(normalize(exported[0]['expanded']), normalize(exported[0]['reference']))

    def test_checked_in_report_is_deterministic(self):
        checked=json.loads((ROOT/'reports/pattern-roundtrip-v0.8.json').read_text(encoding='utf-8'))
        self.assertEqual(checked,check(self.patterns))

    def test_cli_check_expand_report(self):
        for args, expected in [(['check'],'OK:'),(['report'],'"roundtrip_cases": 24'),(['expand','P_STATE(subject=WATER,property=LIQUID)'],'IS(subject=WATER, property=LIQUID)')]:
            proc=subprocess.run([sys.executable,'pattern_lab.py',*args],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn(expected,proc.stdout)

    def test_export_refuses_overwrite(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'expanded.jsonl'
            cmd=[sys.executable,'pattern_lab.py','export','--out',str(path)]
            first=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            second=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(second.returncode,1)
            self.assertEqual(len(path.read_text(encoding='utf-8').splitlines()),24)


if __name__=='__main__':
    unittest.main()
