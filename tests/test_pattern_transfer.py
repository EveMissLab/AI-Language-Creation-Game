"""v0.9 cross-condition, no external AI reader, all results protocol-only."""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from alcg import Call, parse, walk
from pattern_lab import load_patterns, expand
from pattern_transfer import (
    CONDITIONS, TASKS, PROBES, REPORT_FORMAT, TransferError, canonical, check_protocol,
    compare_reports, digest, fixture_hashes, fixtures, grade, make_trial,
    response_template, used_patterns, verify_trial,
)
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parents[1]


class PatternTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.probes, _, cls.patterns = fixtures()
        cls.trials = {(task, arm): make_trial(task=task, condition=arm)
                      for task in TASKS for arm in CONDITIONS}

    def test_public_frozen_sources_and_six_domains(self):
        report = check_protocol()
        self.assertEqual(report['patterns'], 16)
        self.assertEqual(report['reconstruction_items'], 24)
        self.assertEqual(report['contrast_items'], 12)
        self.assertEqual(report['condition_task_packets'], 6)
        self.assertEqual(set(report['probe_domain_counts'].values()), {2})
        self.assertIsNone(report['independent_reader_results'])

    def test_different_tasks_keep_paraphrases_out_of_reconstruction(self):
        for arm in CONDITIONS:
            p, k = self.trials['reconstruct', arm]
            self.assertEqual(set(p), {'format', 'task', 'condition', 'seed', 'instructions', 'items'} |
                             ({'glossary', 'glossary_rule'} if arm == 'glossary' else set()))
            self.assertEqual(len(p['items']), 24)
            self.assertTrue(all(set(i) == {'id','expression'} for i in p['items']))
            self.assertTrue(all('english' not in i and 'correct_choice' not in i for i in p['items']))
            packet_text = canonical(p).decode('utf-8').casefold()
            for gold in k['items']:
                self.assertNotIn(gold['english'].casefold(), packet_text)
                self.assertNotIn(gold['source_id'], packet_text)

    def test_contrast_contains_only_choices_not_answer_labels(self):
        for arm in CONDITIONS:
            p, k = self.trials['contrast', arm]
            self.assertEqual(len(p['items']), 12)
            for i, ref in zip(p['items'], k['items']):
                self.assertEqual(set(i), {'id','expression','question','options'})
                self.assertEqual(set(i['options']), {'A','B','C'})
                self.assertEqual(len(set(i['options'].values())), 3)
                self.assertIn(ref['correct_choice'], i['options'])
                self.assertNotIn('correct', i)

    def test_same_sources_ordered_identically_across_all_arms(self):
        for task in TASKS:
            lists = [[r['source_id'] for r in self.trials[task, arm][1]['items']] for arm in CONDITIONS]
            self.assertEqual(lists[0], lists[1])
            self.assertEqual(lists[1], lists[2])

    def test_three_conditions_differ_and_glossary_is_closure_only(self):
        for task in TASKS:
            ua,_=self.trials[task,'unaided']
            glossary,_=self.trials[task,'glossary']
            expanded,_=self.trials[task,'expanded']
            self.assertNotIn('glossary',ua)
            self.assertIn('glossary',glossary)
            self.assertNotIn('glossary',expanded)
            self.assertEqual([i['expression'] for i in ua['items']],
                             [i['expression'] for i in glossary['items']])
            self.assertNotEqual([i['expression'] for i in ua['items']],
                                [i['expression'] for i in expanded['items']])
            expected = set()
            for i in ua['items']:
                expected |= used_patterns(i['expression'], self.patterns)
            self.assertEqual({i['name'] for i in glossary['glossary']}, expected)

    def test_expanded_expression_equivalent_to_reference(self):
        for task in TASKS:
            p,k=self.trials[task,'expanded']
            for item,gold in zip(p['items'],k['items']):
                with self.subTest(item=item['id'],task=task):
                    self.assertEqual(normalize(item['expression']),normalize(gold['reference']))
                    self.assertFalse(any(isinstance(n,Call) and n.name.startswith('P_')
                                         for n in walk(parse(item['expression']))))

    def test_packet_hash_and_canonical_reproducibility(self):
        for task in TASKS:
            for arm in CONDITIONS:
                p,k=self.trials[task,arm]
                self.assertEqual(digest(p),k['packet_hash'])
                verify_trial(p,k)
                p2,k2=make_trial(task=task,condition=arm)
                self.assertEqual(canonical(p),canonical(p2))
                self.assertEqual(k,k2)

    def test_new_seed_permutes_order_and_packet_digest(self):
        a,ka=self.trials['reconstruct','unaided']
        b,kb=make_trial(task='reconstruct',condition='unaided',seed=24680)
        self.assertNotEqual(digest(a),digest(b))
        self.assertNotEqual([g['source_id'] for g in ka['items']], [g['source_id'] for g in kb['items']])
        self.assertEqual({g['source_id'] for g in ka['items']},{g['source_id'] for g in kb['items']})

    def test_packet_and_key_tamper_rejected(self):
        p,k=self.trials['reconstruct','glossary']
        bad=copy.deepcopy(p)
        bad['items'][0]['expression']='IS(subject=UNSAFE, property=TRUE)'
        with self.assertRaises(TransferError):verify_trial(bad,k)
        badkey=copy.deepcopy(k)
        badkey['items'][0]['english']='wrong gold'
        with self.assertRaises(TransferError):verify_trial(p,badkey)

    def test_seed_and_condition_validation(self):
        for params in [{'seed':-1}, {'seed':2**32},{'seed':True},{'task':'unknown'},{'condition':'unknown'}]:
            with self.subTest(params=params), self.assertRaises(TransferError):
                make_trial(**params)

    def test_abstain_template_is_explicitly_not_measured(self):
        for task in TASKS:
            for arm in CONDITIONS:
                p,k=self.trials[task,arm]
                resp=response_template(p,'control-not-a-model')
                result=grade(p,k,resp)
                self.assertEqual(result['abstained'],len(p['items']))
                self.assertEqual(result['answered'],0)
                if task=='reconstruct':
                    self.assertIsNone(result['mean_fidelity_all_0_to_3'])
                    self.assertFalse(result['human_ratings_supplied'])
                    self.assertNotIn('correct',result['by_domain']['daily'])
                else:
                    self.assertEqual(result['correct'],0)
                    self.assertEqual(result['accuracy_all'],0)
                    self.assertIsNone(result['accuracy_answered'])

    def test_perfect_objective_contrast_grades_twelve(self):
        p,k=self.trials['contrast','unaided']
        response=response_template(p,'reader-a')
        answer={item['id']:item['correct_choice'] for item in k['items']}
        for row in response['items']:
            row['choice']=answer[row['id']]
        scored=grade(p,k,response)
        self.assertEqual((scored['correct'], scored['answered'], scored['accuracy_all']),(12,12,1.0))
        self.assertEqual(set(scored['by_domain']),{
            'daily','science','mathematics','computing','society','epistemic'})
        self.assertEqual({r['correct'] for r in scored['by_domain'].values()},{2})

    def test_incorrect_contrast_is_zero(self):
        p,k=self.trials['contrast','glossary']
        r=response_template(p,'control')
        gold={item['id']:item['correct_choice'] for item in k['items']}
        for row in r['items']:
            row['choice']=next(c for c in 'ABC' if c!=gold[row['id']])
        scored=grade(p,k,r)
        self.assertEqual(scored['correct'],0)
        self.assertEqual(scored['accuracy_answered'],0)

    def test_contrast_one_correct_one_wrong_one_abstain(self):
        p,k=self.trials['contrast','expanded']
        r=response_template(p,'reader-3')
        correct=k['items'][0]['correct_choice']
        r['items'][0]['choice']=correct
        wrong=k['items'][1]['correct_choice']
        r['items'][1]['choice']=next(c for c in 'ABC' if c!=wrong)
        scored=grade(p,k,r)
        self.assertEqual(scored['answered'],2)
        self.assertEqual(scored['correct'],1)
        self.assertEqual(scored['abstained'],10)
        self.assertEqual(scored['accuracy_answered'],0.5)
        self.assertAlmostEqual(scored['accuracy_all'],1/12,places=5)

    def test_reconstruction_without_ratings_is_unscored(self):
        p,k=self.trials['reconstruct','unaided']
        r=response_template(p,'reader-a')
        r['items'][0].update(reconstruction='A semantic guess.',abstain=False)
        scored=grade(p,k,r)
        self.assertEqual(scored['answered'],1)
        self.assertIsNone(scored['mean_fidelity_all_0_to_3'])
        self.assertNotIn('correct',scored['by_domain'][k['items'][0]['domain']])

    def test_reconstruction_with_independent_ratings(self):
        p,k=self.trials['reconstruct','expanded']
        r=response_template(p,'reader-1')
        r['items'][0].update(reconstruction='Reader English result one.',abstain=False)
        r['items'][1].update(reconstruction='Reader English result two.',abstain=False)
        ratings={'format':'ALCG-pattern-transfer-rating-v0.9','packet_hash':digest(p),'rater_id':'judge-2',
                 'items':[{'id':r['items'][0]['id'],'fidelity':3,'critical_structure':True,'note':'preserved roles'},
                          {'id':r['items'][1]['id'],'fidelity':1,'critical_structure':False,'note':'scope error'}]}
        report=grade(p,k,r,ratings)
        self.assertEqual(report['mean_fidelity_answered_0_to_3'],2)
        self.assertEqual(report['mean_fidelity_all_0_to_3'],round(4/24,6))
        self.assertEqual(report['critical_structure_rate_all'],round(1/24,6))
        self.assertTrue(report['human_ratings_supplied'])

    def test_reconstruction_missing_or_extraneous_ratings_rejected(self):
        p,k=self.trials['reconstruct','unaided']
        r=response_template(p,'reader-1')
        r['items'][0].update(reconstruction='Some answer',abstain=False)
        no_ratings={'format':'ALCG-pattern-transfer-rating-v0.9','packet_hash':digest(p),
                    'rater_id':'judge-1','items':[]}
        with self.assertRaises(TransferError):grade(p,k,r,no_ratings)
        self_ratings=copy.deepcopy(no_ratings)
        self_ratings['rater_id']='reader-1'
        with self.assertRaisesRegex(TransferError,'self-adjudicate'):
            grade(p,k,r,self_ratings)

    def test_bad_responses_rejected(self):
        p,k=self.trials['reconstruct','unaided']
        for change in ('duplicate','missing','unknown','abstain-mismatch','empty-response','hash'):
            bad=response_template(p,'reader-a')
            if change=='duplicate':bad['items'][1]['id']=bad['items'][0]['id']
            if change=='missing':bad['items'].pop()
            if change=='unknown':bad['items'][0]['id']='R999'
            if change=='abstain-mismatch':bad['items'][0]['reconstruction']='not empty'
            if change=='empty-response':bad['items'][0]['abstain']=False
            if change=='hash':bad['packet_hash']='bad'
            with self.subTest(change=change),self.assertRaises(TransferError):
                grade(p,k,bad)

    def test_compare_requires_distinct_readers_and_equal_fixtures(self):
        reports=[]
        for idx,arm in enumerate(CONDITIONS):
            p,k=self.trials['contrast',arm]
            reports.append(grade(p,k,response_template(p,f'reader-{idx}')))
        summary=compare_reports(reports)
        self.assertEqual(len(summary['arms']),3)
        bad=copy.deepcopy(reports)
        bad[1]['reader_id']=bad[0]['reader_id']
        with self.assertRaises(TransferError):compare_reports(bad)
        bad=copy.deepcopy(reports)
        bad[1]['seed']=222
        with self.assertRaises(TransferError):compare_reports(bad)
        bad=copy.deepcopy(reports)
        bad[1]['condition']=bad[0]['condition']
        with self.assertRaises(TransferError):compare_reports(bad)

    def test_controlled_source_change_detected(self):
        from pattern_transfer import FROZEN
        saved=FROZEN['v0.8_patterns']
        try:
            FROZEN['v0.8_patterns']=(saved[0],'bad-digest')
            with self.assertRaisesRegex(TransferError,'frozen'):
                fixtures()
        finally:
            FROZEN['v0.8_patterns']=saved

    def test_report_matches_checked_in_json(self):
        committed=json.loads((ROOT/'reports/pattern-transfer-v0.9.json').read_text(encoding='utf-8'))
        self.assertEqual(committed,check_protocol())

    def test_cli_check_report(self):
        for args,needle in [(['check'],'6 packet configurations'),(['report'],'"reconstruction_items": 24')]:
            p=subprocess.run([sys.executable,'pattern_transfer.py',*args],cwd=ROOT, capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn(needle,p.stdout)

    def test_cli_prepare_grade_roundtrip_refuses_overwrite(self):
        with TemporaryDirectory() as t:
            root=Path(t)
            packet=root/'read.json';key=root/'private-key.json';response=root/'responses.json'
            cmd=[sys.executable,'pattern_transfer.py','prepare','--task','contrast','--condition','glossary',
                 '--packet',str(packet),'--key',str(key),'--response-template',str(response)]
            first=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            second=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            third=subprocess.run([sys.executable,'pattern_transfer.py','grade','--packet',str(packet),
                                  '--key',str(key),'--responses',str(response)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(third.returncode,0,third.stderr)
            self.assertEqual(json.loads(third.stdout)['abstained'],12)


if __name__=='__main__':
    unittest.main()
