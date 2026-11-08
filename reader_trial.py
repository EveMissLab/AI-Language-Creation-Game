"""ALCG v0.7: paired blind-reading packets, counterfactual contrasts and a non-AI baseline.

Public, curated benchmarks are NOT securely held out. This tool only validates the
protocol and records externally supplied reading evidence; it does not call any AI.
Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from typing import Any

from alcg import Call, Name, String, parse, walk
from coverage_lab import BenchmarkError, DOMAINS, inspect_calls, jsonl, load_benchmark, relations
from sense_coverage import NEW, REGISTRY, SENSES, report as sense_report, validate_senses

ROOT = Path(__file__).resolve().parent
CONTRASTS = ROOT / 'benchmarks' / 'reader-contrast-v0.7.jsonl'
FORMAT = 'ALCG-reader-v0.7'
CONDITIONS = {'unaided', 'glossary'}
CONTRAST_FIELDS = {'id', 'source_id', 'domain', 'target', 'correct', 'foil', 'contrast_type', 'note'}
SENSE_GLOSSARY = {s['sense_id']: s['gloss'] for s in validate_senses()}
ID_FORMAT = re.compile(r'V7[0-9]{2}\Z')
# Frozen v0.6 assets: intentionally pin the original bytes instead of just
# checking their shape, so an accidental benchmark rewrite fails closed.
FROZEN_SHA256 = {
    'curated_coverage_v0_6': '1555814a6ec16a4083c198cf8e72fe8e6de28cd19c87e76c8c3e6b59ccfd9ea9',
    'relation_registry_v0_4': '8ea3fbb5ceba073eac2904ada7469809be2556f319a4a627f705a7db4e08f34e',
    'sense_registry_v0_6': '97ee83d87a5e5c971f559498ee265f6b599a121e8fa7e27cf107d0723ec8c9ab',
}


def sha_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def to_json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def source_hashes() -> dict[str, str]:
    return {
        'curated_coverage_v0_6': sha_bytes(NEW.read_bytes()),
        'relation_registry_v0_4': sha_bytes(REGISTRY.read_bytes()),
        'sense_registry_v0_6': sha_bytes(SENSES.read_bytes()),
        'reader_contrasts_v0_7': sha_bytes(CONTRASTS.read_bytes()),
    }


def load_fixtures() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Ensures pinned v0.4 assets and unmodified v0.6 source discipline.
    if any(source_hashes()[name] != expected for name, expected in FROZEN_SHA256.items()):
        raise BenchmarkError('v0.6 baseline changed; v0.7 requires frozen source bytes')
    previous = sense_report()
    coverage = load_benchmark(NEW, REGISTRY)
    candidates = [c for c in coverage if c['hypothesis'] == 'candidate']
    if previous['new_curated_cases'] != 48 or len(candidates) != 36:
        raise BenchmarkError('expected unmodified v0.6 candidate set')
    by_id = {c['id']: c for c in candidates}
    pairs = jsonl(CONTRASTS)
    if len(pairs) != 24:
        raise BenchmarkError('v0.7 requires exactly 24 contrast pairs')
    seen: set[str] = set()
    sources: set[str] = set()
    domains: Counter[str] = Counter()
    registry = relations(REGISTRY)
    ambiguity = {item['surface'].upper() for item in validate_senses()}
    for item in pairs:
        if set(item) != CONTRAST_FIELDS:
            raise BenchmarkError('contrast row has incorrect fields')
        cid, sid, domain = item['id'], item['source_id'], item['domain']
        if not isinstance(cid, str) or not ID_FORMAT.fullmatch(cid) or cid in seen:
            raise BenchmarkError(f'invalid/duplicate v0.7 pair ID: {cid!r}')
        if not isinstance(sid, str) or sid not in by_id or sid in sources:
            raise BenchmarkError(f'{cid}: missing/duplicate candidate source')
        if domain != by_id[sid]['domain'] or domain not in DOMAINS:
            raise BenchmarkError(f'{cid}: domain mismatch')
        if not all(isinstance(item[k], str) and item[k].strip()
                   for k in ('target', 'correct', 'foil', 'contrast_type', 'note')):
            raise BenchmarkError(f'{cid}: invalid contrast text')
        if item['target'] != by_id[sid]['english'] or parse(item['correct']) != parse(by_id[sid]['expression']):
            raise BenchmarkError(f'{cid}: correct side does not match frozen English/source expression')
        if len(item['note'].strip()) < 25:
            raise BenchmarkError(f'{cid}: missing explanation of changed meaning')
        left, right = parse(item['correct']), parse(item['foil'])
        if left == right:
            raise BenchmarkError(f'{cid}: foil does not change the expression')
        for expr in (left, right):
            inspect_calls(expr, registry)
            if any(isinstance(n, String) or (isinstance(n, Call) and n.name in {'RAW','PARTIAL'})
                   for n in walk(expr)):
                raise BenchmarkError(f'{cid}: raw/partial information leak')
            if any(isinstance(n, Name) and n.value in ambiguity for n in walk(expr)):
                raise BenchmarkError(f'{cid}: unqualified polysemous label')
        seen.add(cid)
        sources.add(sid)
        domains[domain] += 1
    if set(seen) != {f'V7{idx:02}' for idx in range(1,25)} or any(domains[d] != 4 for d in DOMAINS):
        raise BenchmarkError('IDs must be V701..V724, with four pairs per domain')
    return candidates, pairs


def used_glossary(*expressions: str) -> dict[str, str]:
    labels: set[str] = set()
    for expression in expressions:
        labels.update(n.value for n in walk(parse(expression)) if isinstance(n, Name))
    return {k: SENSE_GLOSSARY[k] for k in sorted(labels & SENSE_GLOSSARY.keys())}


def build_trial(seed: int = 20261108, condition: str = 'unaided') -> tuple[dict, dict]:
    if condition not in CONDITIONS:
        raise BenchmarkError('unknown reader condition')
    candidates, pairs = load_fixtures()
    rng = random.Random(seed)
    rng.shuffle(candidates)
    rng.shuffle(pairs)
    sides = ['A'] * 12 + ['B'] * 12
    rng.shuffle(sides)
    items: list[dict] = []
    gold: list[dict] = []
    for i, row in enumerate(candidates, 1):
        task_id = f'R{i:04}'
        task = {'id': task_id, 'task': 'reconstruct', 'expression': row['expression']}
        if condition == 'glossary':
            task['sense_glossary'] = used_glossary(row['expression'])
        items.append(task)
        gold.append({'id': task_id, 'task': 'reconstruct', 'source_id': row['id'],
                     'domain': row['domain'], 'english': row['english']})
    for i, (row, correct_side) in enumerate(zip(pairs, sides), 1):
        task_id = f'C{i:04}'
        options = ({'A': row['correct'], 'B': row['foil']}
                   if correct_side == 'A' else {'A': row['foil'], 'B': row['correct']})
        task = {'id': task_id, 'task': 'choose', 'target': row['target'], 'options': options}
        if condition == 'glossary':
            task['sense_glossary'] = used_glossary(*options.values())
        items.append(task)
        gold.append({'id': task_id, 'task': 'choose', 'source_id': row['source_id'],
                     'domain': row['domain'], 'correct_option': correct_side,
                     'contrast_type': row['contrast_type'], 'note': row['note']})
    rng.shuffle(items)
    packet = {
        'schema': FORMAT + '-packet', 'condition': condition,
        'instructions': {
            'reconstruct': 'Write the meaning in ordinary English. If unsure, abstain explicitly.',
            'choose': 'Choose A, B or ABSTAIN to match the visible English target. Explain uncertainty.',
            'format': 'Return one JSON object per ID; see docs/READER-TRANSFER-v0.7.md.',
        },
        'items': items,
    }
    key = {
        'schema': FORMAT + '-key', 'seed': seed, 'condition': condition,
        'packet_sha256': sha_bytes(to_json(packet)),
        'source_sha256': source_hashes(),
        'items': gold,
        'notice': 'Never share the key with a reader; this public source dataset is not a secure holdout.',
    }
    if any(any(k in entry for k in ('english', 'source_id', 'correct_option', 'gap')) for entry in packet['items']):
        raise AssertionError('blinded packet contains key-only fields')
    return packet, key


def verify_trial(packet: dict, key: dict) -> None:
    if not isinstance(packet, dict) or not isinstance(key, dict):
        raise BenchmarkError('packet/key must both be JSON objects')
    if packet.get('schema') != FORMAT + '-packet' or key.get('schema') != FORMAT + '-key':
        raise BenchmarkError('unsupported packet/key schema')
    if packet.get('condition') != key.get('condition') or key.get('condition') not in CONDITIONS:
        raise BenchmarkError('packet/key condition mismatch')
    if sha_bytes(to_json(packet)) != key.get('packet_sha256'):
        raise BenchmarkError('packet checksum mismatch')
    if key.get('source_sha256') != source_hashes():
        raise BenchmarkError('benchmark sources changed since packet creation')
    if type(key.get('seed')) is not int:
        raise BenchmarkError('invalid seed')
    expected_packet, expected_key = build_trial(key['seed'], key['condition'])
    if packet != expected_packet or key != expected_key:
        raise BenchmarkError('packet/key inconsistent with deterministic trial construction')


def validate_response(packet: dict, responses: list[dict]) -> dict[str, dict]:
    tasks = {case['id']: case for case in packet['items']}
    result: dict[str, dict] = {}
    for response in responses:
        rid = response.get('id')
        if not isinstance(rid, str) or rid not in tasks or rid in result:
            raise BenchmarkError(f'unknown/duplicate response ID {rid!r}')
        task = tasks[rid]['task']
        if task == 'reconstruct':
            if set(response) != {'id', 'reconstruction', 'uncertainty', 'abstain'}:
                raise BenchmarkError(f'{rid}: reconstruction schema mismatch')
            if (not isinstance(response['reconstruction'], str)
                    or not isinstance(response['uncertainty'], str)
                    or type(response['abstain']) is not bool):
                raise BenchmarkError(f'{rid}: invalid reconstruction response values')
            if response['abstain'] == bool(response['reconstruction'].strip()):
                raise BenchmarkError(f'{rid}: abstain must correspond to empty reconstruction')
        else:
            if set(response) != {'id', 'choice', 'rationale'}:
                raise BenchmarkError(f'{rid}: choice schema mismatch')
            if response['choice'] not in ('A', 'B', 'ABSTAIN') or not isinstance(response['rationale'], str):
                raise BenchmarkError(f'{rid}: invalid choice response values')
        result[rid] = response
    return result


def validate_ratings(gold: list[dict], responses: dict[str, dict], ratings: list[dict]) -> dict[str, dict]:
    reconstruct_ids = {i['id'] for i in gold if i['task'] == 'reconstruct'}
    rated: dict[str, dict] = {}
    for row in ratings:
        rid = row.get('id')
        if (not isinstance(rid, str) or rid not in reconstruct_ids or rid in rated
                or rid not in responses or responses[rid]['abstain']):
            raise BenchmarkError(f'invalid/duplicate/unanswered reconstruction rating {rid!r}')
        if set(row) != {'id','rating','notes'} or type(row['rating']) is not int or row['rating'] not in (0,1,2,3):
            raise BenchmarkError(f'{rid}: rating schema mismatch or rating outside 0..3')
        if not isinstance(row['notes'], str) or not row['notes'].strip():
            raise BenchmarkError(f'{rid}: adjudication notes required')
        rated[rid] = row
    return rated


def score_trial(packet: dict, key: dict, responses: list[dict], ratings: list[dict] | None = None) -> dict:
    verify_trial(packet, key)
    supplied = validate_response(packet, responses)
    gold = key['items']
    grades = validate_ratings(gold, supplied, ratings or [])
    choose = [g for g in gold if g['task']=='choose']
    recon = [g for g in gold if g['task']=='reconstruct']
    selected = [g for g in choose if g['id'] in supplied and supplied[g['id']]['choice'] in ('A', 'B')]
    abstained = sum(g['id'] in supplied and supplied[g['id']]['choice'] == 'ABSTAIN' for g in choose)
    correct = sum(supplied[g['id']]['choice'] == g['correct_option'] for g in selected)
    recon_submitted = [g for g in recon if g['id'] in supplied and not supplied[g['id']]['abstain']]
    recon_abstained = sum(g['id'] in supplied and supplied[g['id']]['abstain'] for g in recon)
    distributions = Counter(row['rating'] for row in grades.values())
    by_domain = {}
    for domain in sorted(DOMAINS):
        local = [g for g in choose if g['domain'] == domain]
        by_domain[domain] = {
            'assigned': len(local),
            'correct': sum(g in selected and supplied[g['id']]['choice'] == g['correct_option'] for g in local),
            'abstained': sum(g['id'] in supplied and supplied[g['id']]['choice'] == 'ABSTAIN' for g in local),
        }
    return {
        'schema': FORMAT + '-score', 'condition': packet['condition'],
        'assigned': {'reconstruction':len(recon), 'contrast':len(choose)},
        'contrast': {
            'selected':len(selected), 'correct':correct, 'incorrect':len(selected)-correct,
            'abstained':abstained, 'missing':len(choose)-len(selected)-abstained,
            'accuracy_all_assigned':round(correct/len(choose),4) if choose else None,
            'accuracy_selected_only':round(correct/len(selected),4) if selected else None,
            'always_A_expected_accuracy':round(sum(g['correct_option']=='A' for g in choose)/len(choose),4) if choose else None,
            'by_domain':by_domain,
        },
        'reconstruction': {
            'submitted':len(recon_submitted), 'abstained':recon_abstained,
            'missing':len(recon)-len(recon_submitted)-recon_abstained,
            'rated':len(grades), 'unrated_submissions':len(recon_submitted)-len(grades),
            'rating_distribution':{str(k):distributions[k] for k in (0,1,2,3)},
            'average_on_rated_only':round(sum(k*v for k,v in distributions.items())/len(grades),4) if grades else None,
        },
        'independent_reader_identity_verified':False,
        'limits': 'A forced-choice result is not open-ended understanding. Ratings require external adjudication. The public benchmark is not a secure holdout.',
    }


STOPWORDS = frozenset('the a an of in on to for that is are was were has have had by with their this it its at from as when how than and or some one every'.split())


def lexical_tokens(text: str) -> set[str]:
    words = re.findall(r'[A-Za-z]+', text.lower())
    return {w for w in words if w not in STOPWORDS}


def expression_tokens(source: str) -> set[str]:
    labels = []
    for item in walk(parse(source)):
        if isinstance(item, Name):
            labels.append(item.value)
        elif isinstance(item, Call):
            labels.append(item.name)
    return lexical_tokens(' '.join(labels).replace('_',' '))


def lexical_baseline(packet: dict) -> list[dict]:
    """Deliberately weak, hand-coded, non-AI overlap rule. No access to gold or glossary."""
    out = []
    for item in packet['items']:
        if item['task'] != 'choose':
            continue
        target = lexical_tokens(item['target'])
        overlaps = {side:len(target & expression_tokens(expr)) for side,expr in item['options'].items()}
        if overlaps['A'] == overlaps['B']:
            choice='ABSTAIN'
        else:
            choice='A' if overlaps['A'] > overlaps['B'] else 'B'
        out.append({'id':item['id'],'choice':choice,'rationale':f'NON-AI lexical overlap A={overlaps["A"]}, B={overlaps["B"]}; ties abstain.'})
    return out


def baseline_report(seed: int = 20261108) -> dict:
    unaided,key = build_trial(seed,'unaided')
    assisted,_ = build_trial(seed,'glossary')
    unaided_score = score_trial(unaided,key,lexical_baseline(unaided))
    assisted_key = build_trial(seed,'glossary')[1]
    assisted_score = score_trial(assisted,assisted_key,lexical_baseline(assisted))
    return {
        'schema':FORMAT+'-development-report',
        'seed':seed,
        'public_curated_source_cases':48,
        'reconstruction_tasks':36,
        'contrast_tasks':24,
        'contrast_types':dict(sorted(Counter(c['contrast_type'] for c in load_fixtures()[1]).items())),
        'conditions':['unaided','glossary'],
        'lexical_overlap_baseline_not_ai':{
            'unaided':unaided_score['contrast'],
            'glossary':assisted_score['contrast'],
            'uses_glossary':False,
            'reconstruction_cases_answered':0,
        },
        'independent_ai_reader_scores':None,
        'externally_adjudicated_reconstruction_scores':None,
        'public_source_generalization_claim':None,
        'warning':'Mechanical coverage, balanced keys and a lexical non-AI baseline do not measure AI comprehension. The public gold source is not a secure unseen test.',
    }


def write_new(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as handle:
        handle.write(blob)


def protect_private_key(path: Path) -> None:
    try:
        relative=path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return
    if not relative.parts or relative.parts[0] not in {'.local','private','.runs'}:
        raise BenchmarkError('local gold keys in this public repository must be stored under .local/, private/ or .runs/ (gitignored)')


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description='ALCG v0.7 blind-reader trials; does not call an AI service')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('check')
    sub.add_parser('baseline-report')
    prep=sub.add_parser('prepare')
    prep.add_argument('--condition',choices=sorted(CONDITIONS),required=True)
    prep.add_argument('--seed',type=int,default=20261108)
    prep.add_argument('--packet',type=Path,required=True)
    prep.add_argument('--key',type=Path,required=True)
    base=sub.add_parser('lexical-baseline')
    base.add_argument('--packet',type=Path,required=True)
    base.add_argument('--out',type=Path,required=True)
    grade=sub.add_parser('grade')
    grade.add_argument('--packet',type=Path,required=True)
    grade.add_argument('--key',type=Path,required=True)
    grade.add_argument('--responses',type=Path,required=True)
    grade.add_argument('--ratings',type=Path)
    args=p.parse_args(argv)
    try:
        if args.command == 'check':
            c,pairs=load_fixtures()
            for cond in sorted(CONDITIONS):
                packet,key=build_trial(condition=cond)
                verify_trial(packet,key)
                if len(packet['items'])!=60:
                    raise BenchmarkError('unexpected challenge size')
            print(f'OK: {len(c)} reconstruction candidates, {len(pairs)} distinct contrast pairs; no independent reader scores')
        elif args.command=='baseline-report':
            print(json.dumps(baseline_report(),indent=2,ensure_ascii=False))
        elif args.command=='prepare':
            if args.packet.resolve()==args.key.resolve() or args.packet.exists() or args.key.exists():
                raise BenchmarkError('packet/key must have distinct unused output paths')
            protect_private_key(args.key)
            packet,key=build_trial(args.seed,args.condition)
            write_new(args.packet,to_json(packet))
            write_new(args.key,to_json(key))
            print(f'Wrote {len(packet["items"])} {args.condition} reader tasks: {args.packet}. Keep {args.key} private.')
        elif args.command=='lexical-baseline':
            if args.out.exists():
                raise BenchmarkError('baseline output already exists')
            packet=json.loads(args.packet.read_text(encoding='utf-8'))
            if not isinstance(packet,dict) or packet.get('schema')!=FORMAT+'-packet':
                raise BenchmarkError('invalid reader packet')
            responses=lexical_baseline(packet)
            write_new(args.out,(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in responses)).encode('utf-8'))
            print(f'Wrote {len(responses)} non-AI lexical contrast guesses; reconstruct tasks intentionally unanswered.')
        else:
            packet=json.loads(args.packet.read_text(encoding='utf-8'))
            key=json.loads(args.key.read_text(encoding='utf-8'))
            responses=jsonl(args.responses)
            ratings=jsonl(args.ratings) if args.ratings else None
            print(json.dumps(score_trial(packet,key,responses,ratings),indent=2,ensure_ascii=False))
    except (BenchmarkError,OSError,ValueError,KeyError,TypeError,RecursionError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
