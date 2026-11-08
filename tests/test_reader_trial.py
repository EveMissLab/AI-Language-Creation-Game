"""v0.7 paired AI reading protocol / transparent NON-AI lexical control tests."""
import copy
import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alcg import parse
from coverage_lab import BenchmarkError
import reader_trial as trial


ROOT = Path(__file__).resolve().parents[1]


class ReaderTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates, cls.pairs = trial.load_fixtures()
        cls.packet, cls.key = trial.build_trial()

    def test_36_reconstruction_24_contrast(self):
        self.assertEqual(len(self.candidates),36)
        self.assertEqual(len(self.pairs),24)
        self.assertEqual(Counter(x['task'] for x in self.packet['items']),{'choose':24,'reconstruct':36})
        self.assertEqual(Counter(row['domain'] for row in self.pairs),{x:4 for x in trial.DOMAINS})

    def test_lexical_and_relation_signatures_frozen(self):
        result=trial.sense_report()
        self.assertEqual(result['ambiguous_english_surfaces_reviewed'],8)
        self.assertEqual(result['new_curated_cases'],48)
        self.assertEqual(result['additional_relation_operators_introduced'],0)

    def test_v06_source_pins(self):
        hashes=trial.source_hashes()
        for key,expected in trial.FROZEN_SHA256.items():
            self.assertEqual(hashes[key], expected)

    def test_contrasts_distinct_and_source_referenced(self):
        candidates={row['id']:row for row in self.candidates}
        self.assertEqual(len({row['source_id'] for row in self.pairs}),24)
        for row in self.pairs:
            with self.subTest(row=row['id']):
                self.assertEqual(row['target'],candidates[row['source_id']]['english'])
                self.assertEqual(parse(row['correct']),parse(candidates[row['source_id']]['expression']))
                self.assertNotEqual(parse(row['correct']),parse(row['foil']))

    def test_packet_reconstruction_has_no_source_answers(self):
        gold={r['id']:r for r in self.key['items']}
        for row in self.packet['items']:
            self.assertNotIn('source_id',row)
            self.assertNotIn('english',row)
            self.assertNotIn('correct_option',row)
            self.assertNotIn('gap',row)
            if row['task']=='reconstruct':
                self.assertEqual(set(row),{'id','task','expression'})
                self.assertNotIn(gold[row['id']]['english'],json.dumps(row))
                self.assertNotIn('RAW(',row['expression'])
            else:
                self.assertEqual(set(row),{'id','task','target','options'})
                self.assertEqual(set(row['options']),{'A','B'})

    def test_correct_answer_positions_balanced(self):
        choices=[item for item in self.key['items'] if item['task']=='choose']
        self.assertEqual(Counter(row['correct_option'] for row in choices),{'A':12,'B':12})

    def test_same_seed_reproducible_and_different_seed_changes(self):
        a,k=trial.build_trial(914)
        b,l=trial.build_trial(914)
        c,_=trial.build_trial(915)
        self.assertEqual(a,b)
        self.assertEqual(k,l)
        self.assertNotEqual(a,c)
        trial.verify_trial(a,k)

    def test_two_conditions_are_paired_not_leaked(self):
        assisted,assisted_key=trial.build_trial(condition='glossary')
        trial.verify_trial(assisted,assisted_key)
        main={row['id']:row for row in self.packet['items']}
        for other in assisted['items']:
            stripped={k:v for k,v in other.items() if k!='sense_glossary'}
            self.assertEqual(stripped,main[other['id']])
            self.assertEqual(set(other['sense_glossary']).issubset(trial.SENSE_GLOSSARY),True)
            self.assertNotIn('source_id',other)
            self.assertNotIn('english',other)
        self.assertEqual(sum(bool(row['sense_glossary']) for row in assisted['items']) > 0,True)

    def test_mutated_packet_or_key_rejected(self):
        invalid=copy.deepcopy(self.packet)
        item=next(x for x in invalid['items'] if x['task']=='choose')
        item['options']['A']='RAW(text="leak")'
        with self.assertRaisesRegex(BenchmarkError,'checksum'):
            trial.verify_trial(invalid,self.key)
        invalid_key=copy.deepcopy(self.key)
        invalid_key['source_sha256']['curated_coverage_v0_6']='0'*64
        with self.assertRaisesRegex(BenchmarkError,'sources changed'):
            trial.verify_trial(self.packet,invalid_key)

    def test_tamper_even_if_checksum_recomputed_rejected(self):
        bad=copy.deepcopy(self.packet)
        bad['items'][0]['id']='UNAUTHORIZED'
        key=copy.deepcopy(self.key)
        key['packet_sha256']=trial.sha_bytes(trial.to_json(bad))
        with self.assertRaisesRegex(BenchmarkError,'inconsistent'):
            trial.verify_trial(bad,key)

    def test_deliberate_lexical_baseline_not_ai(self):
        outputs=trial.lexical_baseline(self.packet)
        self.assertEqual(len(outputs),24)
        self.assertTrue(all('NON-AI' in x['rationale'] for x in outputs))
        score=trial.score_trial(self.packet,self.key,outputs)
        self.assertEqual(score['contrast']['selected'],8)
        self.assertEqual(score['contrast']['correct'],8)
        self.assertEqual(score['contrast']['abstained'],16)
        self.assertEqual(score['contrast']['incorrect'],0)
        self.assertEqual(score['reconstruction']['submitted'],0)
        self.assertIsNone(score['reconstruction']['average_on_rated_only'])

    def test_baseline_ignores_glossary(self):
        aided,_=trial.build_trial(condition='glossary')
        self.assertEqual(trial.lexical_baseline(aided),trial.lexical_baseline(self.packet))

    def test_missing_answers_not_treated_as_perfect(self):
        result=trial.score_trial(self.packet,self.key,[])
        self.assertEqual(result['contrast']['missing'],24)
        self.assertIsNone(result['contrast']['accuracy_selected_only'])
        self.assertEqual(result['reconstruction']['missing'],36)

    def test_full_synthetic_answer_coverage_in_test_only(self):
        # Explicitly synthetic oracle: NEVER report as independent AI evidence.
        gold={row['id']:row for row in self.key['items']}
        responses=[]
        for item in self.packet['items']:
            if item['task']=='choose':
                responses.append({'id':item['id'],'choice':gold[item['id']]['correct_option'],'rationale':'synthetic unit-test oracle'})
            else:
                responses.append({'id':item['id'],'reconstruction':'synthetic fixture only','uncertainty':'not an AI reader','abstain':False})
        first=next(x['id'] for x in self.packet['items'] if x['task']=='reconstruct')
        rated=[{'id':first,'rating':2,'notes':'synthetic adjudication fixture for schema test'}]
        result=trial.score_trial(self.packet,self.key,responses,rated)
        self.assertEqual(result['contrast']['correct'],24)
        self.assertEqual(result['reconstruction']['submitted'],36)
        self.assertEqual(result['reconstruction']['rated'],1)
        self.assertEqual(result['reconstruction']['unrated_submissions'],35)
        self.assertFalse(result['independent_reader_identity_verified'])

    def test_abstained_reconstruction_and_ratings_rejected(self):
        recon=next(x for x in self.packet['items'] if x['task']=='reconstruct')
        response={'id':recon['id'],'reconstruction':'','uncertainty':'cannot decode','abstain':True}
        result=trial.score_trial(self.packet,self.key,[response])
        self.assertEqual(result['reconstruction']['abstained'],1)
        with self.assertRaisesRegex(BenchmarkError,'unanswered'):
            trial.score_trial(self.packet,self.key,[response],[{'id':recon['id'],'rating':3,'notes':'unjustified'}])

    def test_duplicate_or_unknown_response_rejected(self):
        row={'id':'C0001','choice':'ABSTAIN','rationale':'cannot tell'}
        with self.assertRaisesRegex(BenchmarkError,'duplicate'):
            trial.score_trial(self.packet,self.key,[row,row])
        with self.assertRaisesRegex(BenchmarkError,'unknown'):
            trial.score_trial(self.packet,self.key,[dict(row,id='NONEXISTENT')])

    def test_invalid_abstain_and_extra_fields_rejected(self):
        rid=next(x['id'] for x in self.packet['items'] if x['task']=='reconstruct')
        with self.assertRaisesRegex(BenchmarkError,'abstain'):
            trial.score_trial(self.packet,self.key,[{'id':rid,'reconstruction':'I decoded it','uncertainty':'','abstain':True}])
        with self.assertRaisesRegex(BenchmarkError,'schema'):
            trial.score_trial(self.packet,self.key,[{'id':'C0001','choice':'A','rationale':'guess','leak':'yes'}])

    def test_invalid_rating_type_rejected(self):
        rid=next(x['id'] for x in self.packet['items'] if x['task']=='reconstruct')
        response={'id':rid,'reconstruction':'some interpretation','uncertainty':'low','abstain':False}
        with self.assertRaisesRegex(BenchmarkError,'rating schema'):
            trial.score_trial(self.packet,self.key,[response],[{'id':rid,'rating':True,'notes':'boolean must not pass'}])

    def test_public_key_location_refused(self):
        with self.assertRaisesRegex(BenchmarkError,'gitignored'):
            trial.protect_private_key(ROOT/'benchmarks/key-v0.7.json')
        trial.protect_private_key(ROOT/'.local/key-v0.7.json')

    def test_report_does_not_claim_reader_understanding(self):
        result=trial.baseline_report()
        self.assertIsNone(result['independent_ai_reader_scores'])
        self.assertIsNone(result['externally_adjudicated_reconstruction_scores'])
        self.assertEqual(result['lexical_overlap_baseline_not_ai']['unaided']['abstained'],16)
        self.assertEqual(result['lexical_overlap_baseline_not_ai']['glossary']['abstained'],16)
        self.assertFalse(result['lexical_overlap_baseline_not_ai']['uses_glossary'])

    def test_cli_roundtrip_prepare_baseline_grade(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)
            packet=folder/'packet.json'
            key=folder/'key.json'
            answers=folder/'lexical.jsonl'
            cmd=[sys.executable,str(ROOT/'reader_trial.py')]
            run=subprocess.run(cmd+['prepare','--condition','unaided','--packet',str(packet),'--key',str(key)],
                               cwd=ROOT,check=True,text=True,capture_output=True)
            self.assertIn('60',run.stdout)
            run=subprocess.run(cmd+['lexical-baseline','--packet',str(packet),'--out',str(answers)],
                               cwd=ROOT,check=True,text=True,capture_output=True)
            self.assertIn('24',run.stdout)
            run=subprocess.run(cmd+['grade','--packet',str(packet),'--key',str(key),'--responses',str(answers)],
                               cwd=ROOT,check=True,text=True,capture_output=True)
            result=json.loads(run.stdout)
            self.assertEqual(result['contrast']['selected'],8)
            self.assertEqual(result['reconstruction']['missing'],36)
            # Refuse blind accidental experiment overwrites.
            rerun=subprocess.run(cmd+['prepare','--condition','unaided','--packet',str(packet),'--key',str(key)],
                                 cwd=ROOT,text=True,capture_output=True)
            self.assertNotEqual(rerun.returncode,0)


if __name__ == '__main__':
    unittest.main()
