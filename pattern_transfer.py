"""ALCG v0.9: three-condition pattern-reading trials, WITHOUT any AI calls.

Two tasks are kept in separate packets so multiple-choice paraphrases cannot
leak answers to free reconstruction. Benchmarks are PUBLIC and therefore not a
secure held-out evaluation. Reader and adjudicator evidence must be recorded
externally. Python >= 3.10; standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any

from alcg import Call, parse, render, walk
from coverage_lab import DOMAINS, BenchmarkError, jsonl
from pattern_lab import BENCHMARK, PATTERNS, SOURCE, Pattern, PatternError, check, expand, load_patterns, sha256
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parent
PROBES = ROOT / 'benchmarks/pattern-probes-v0.9.jsonl'
PACKET_FORMAT = 'ALCG-pattern-transfer-packet-v0.9'
KEY_FORMAT = 'ALCG-pattern-transfer-key-v0.9'
RESPONSE_FORMAT = 'ALCG-pattern-transfer-response-v0.9'
RATING_FORMAT = 'ALCG-pattern-transfer-rating-v0.9'
REPORT_FORMAT = 'ALCG-pattern-transfer-report-v0.9'
TASKS = ('reconstruct', 'contrast')
CONDITIONS = ('unaided', 'glossary', 'expanded')
FROZEN = {
    'v0.8_patterns': ('data/patterns-v0.8.json', '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6'),
    'v0.8_examples': ('benchmarks/pattern-roundtrips-v0.8.jsonl', 'b18682f859e2000bbc97dcc82d8520eef9b9ed9a5ee363106a89d86f4a315130'),
    'v0.6_source': ('benchmarks/coverage-v0.6.jsonl', '1555814a6ec16a4083c198cf8e72fe8e6de28cd19c87e76c8c3e6b59ccfd9ea9'),
}


class TransferError(ValueError):
    """Invalid public fixtures or trial metadata."""


def canonical(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def fixture_hashes() -> dict[str, str]:
    return {name: sha256(ROOT / path) for name, (path, _) in FROZEN.items()} | {'v0.9_probes': sha256(PROBES)}


def fixtures() -> tuple[list[dict], list[dict], dict[str, dict], dict[str, Pattern]]:
    hashes = fixture_hashes()
    if any(hashes[name] != expected for name, (_, expected) in FROZEN.items()):
        raise TransferError('frozen v0.8 benchmark or source changed; refusing to rewrite test history')
    mapping = load_patterns()
    report = check(mapping)
    if report['exact_canonical_roundtrips'] != 24 or report['pattern_definitions'] != 16:
        raise TransferError('v0.8 baseline is not the expected 24 cases / 16 patterns')
    case_rows = jsonl(BENCHMARK)
    source = {r['id']: r for r in jsonl(SOURCE)}
    if len(case_rows) != 24 or len({r['source_id'] for r in case_rows}) != 24:
        raise TransferError('expected exactly 24 distinct v0.8 cases')
    cases = []
    for case in case_rows:
        row = source[case['source_id']]
        if row['hypothesis'] != 'candidate' or row['domain'] not in DOMAINS:
            raise TransferError('reader fixtures must not contain RAW or partial hypotheses')
        if normalize(expand(case['pattern'], mapping)) != normalize(row['expression']):
            raise TransferError('pattern expansion does not preserve the original structure')
        cases.append({'source_id': row['id'], 'domain': row['domain'], 'english': row['english'],
                      'pattern': case['pattern'], 'reference': row['expression']})
    probes = jsonl(PROBES)
    case_ids = {c['source_id'] for c in cases}
    seen: set[str] = set()
    domain_counts: Counter[str] = Counter()
    if len(probes) != 12:
        raise TransferError('requires exactly 12 probes')
    for row in probes:
        if set(row) != {'source_id', 'question', 'options', 'correct', 'distinction', 'note'}:
            raise TransferError('invalid probe field set')
        sid = row['source_id']
        if not isinstance(sid, str) or sid not in case_ids or sid in seen:
            raise TransferError('probe source_id missing, repeated or not in pattern cases')
        if not isinstance(row['question'], str) or not row['question'].strip():
            raise TransferError('probe question cannot be empty')
        options = row['options']
        if (not isinstance(options, list) or len(options) != 3 or
                any(not isinstance(opt, str) or not opt.strip() for opt in options) or
                len({opt.casefold().strip() for opt in options}) != 3):
            raise TransferError('each probe needs three distinct substantive choices')
        if type(row['correct']) is not int or row['correct'] not in (0, 1, 2):
            raise TransferError('invalid correct answer index')
        if any(not isinstance(row[k], str) or len(row[k].strip()) < (12 if k == 'note' else 5) for k in ('note', 'distinction')):
            raise TransferError('probe needs distinction and detailed editorial rationale')
        seen.add(sid)
        domain_counts[source[sid]['domain']] += 1
    if any(domain_counts[d] != 2 for d in DOMAINS):
        raise TransferError('requires two contrast probes per domain')
    return cases, probes, source, mapping


def used_patterns(expression: str, mapping: dict[str, Pattern]) -> set[str]:
    used = {n.name for n in walk(parse(expression)) if isinstance(n, Call) and n.name in mapping}
    todo = list(used)
    while todo:
        name = todo.pop()
        for node in walk(mapping[name].template):
            if isinstance(node, Call) and node.name in mapping and node.name not in used:
                used.add(node.name)
                todo.append(node.name)
    return used


def _id(n: int, task: str) -> str:
    return ('R' if task == 'reconstruct' else 'Q') + f'{n:02d}'


def _shuffle(seed: int, domain: str) -> random.Random:
    payload = f'{seed}|{domain}|ALCG-v0.9'.encode('utf-8')
    return random.Random(int.from_bytes(hashlib.sha256(payload).digest()[:8], 'big'))


def make_trial(*, task: str = 'reconstruct', condition: str = 'unaided', seed: int = 20261108) -> tuple[dict, dict]:
    if task not in TASKS or condition not in CONDITIONS:
        raise TransferError('unknown task or condition')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise TransferError('seed must be a 32-bit nonnegative integer')
    cases, probes, _, mapping = fixtures()
    by_id = {row['source_id']: row for row in cases}
    selected = list(cases) if task == 'reconstruct' else [by_id[r['source_id']] for r in probes]
    _shuffle(seed, task).shuffle(selected)  # The same order for all three conditions.
    p_by_id = {r['source_id']: r for r in probes}
    items = []
    key_items = []
    for idx, row in enumerate(selected, 1):
        question_id = _id(idx, task)
        expression = row['pattern'] if condition != 'expanded' else render(expand(row['pattern'], mapping))
        item: dict[str, Any] = {'id': question_id, 'expression': expression}
        key_item: dict[str, Any] = {
            'id': question_id, 'source_id': row['source_id'], 'domain': row['domain'],
            'english': row['english'], 'reference': row['reference'],
        }
        if task == 'contrast':
            probe = p_by_id[row['source_id']]
            indexes = [0, 1, 2]
            _shuffle(seed + idx, row['source_id']).shuffle(indexes)
            item['question'] = probe['question']
            item['options'] = {chr(65 + i): probe['options'][n] for i, n in enumerate(indexes)}
            key_item['correct_choice'] = chr(65 + indexes.index(probe['correct']))
            key_item['distinction'] = probe['distinction']
            key_item['note'] = probe['note']
        items.append(item)
        key_items.append(key_item)
    packet: dict[str, Any] = {
        'format': PACKET_FORMAT,
        'task': task,
        'condition': condition,
        'seed': seed,
        'instructions': (
            'Explain the meaning of each expression in ordinary English, preserving roles, '
            'time order, scope, negation and possibility. If uncertain, abstain.' if task == 'reconstruct' else
            'Select A, B or C for the most faithful description; abstain rather than guess.'
        ),
        'items': items,
    }
    if condition == 'glossary':
        needed = set()
        for c in selected:
            needed |= used_patterns(c['pattern'], mapping)
        packet['glossary'] = [
            {'name': p.name, 'slots': list(p.slots), 'template': render(p.template), 'gloss': p.gloss}
            for p in (mapping[name] for name in sorted(needed))
        ]
        packet['glossary_rule'] = 'HOLE(slot=name) means substitute the caller argument of that slot name.'
    packet_hash = digest(packet)
    key = {'format': KEY_FORMAT, 'packet_hash': packet_hash, 'source_hashes': fixture_hashes(),
           'task': task, 'condition': condition, 'seed': seed, 'items': key_items}
    # A reconstruction packet must not contain a reference English sentence, even indirectly.
    if task == 'reconstruct':
        packet_text = json.dumps(packet, ensure_ascii=False).casefold()
        if any(row['english'].casefold() in packet_text for row in selected):
            raise TransferError('reconstruction packet leaks an English source answer')
    return packet, key


def response_template(packet: dict, reader_id: str) -> dict:
    if not reader_id or not reader_id.strip() or len(reader_id) > 96:
        raise TransferError('reader_id must be a nonempty pseudonym at most 96 characters')
    task = packet['task']
    return {'format': RESPONSE_FORMAT, 'packet_hash': digest(packet), 'reader_id': reader_id,
            'items': [({'id': row['id'], 'reconstruction': '', 'abstain': True}
                       if task == 'reconstruct' else {'id': row['id'], 'choice': None})
                      for row in packet['items']]}


def verify_trial(packet: dict, key: dict) -> None:
    if not isinstance(packet, dict) or not isinstance(key, dict):
        raise TransferError('trial must contain JSON objects')
    if (packet.get('format') != PACKET_FORMAT or key.get('format') != KEY_FORMAT or
            packet.get('task') not in TASKS or packet.get('condition') not in CONDITIONS or
            key.get('packet_hash') != digest(packet)):
        raise TransferError('packet/key format or digest mismatch')
    candidate_packet, candidate_key = make_trial(
        task=packet['task'], condition=packet['condition'], seed=packet['seed'])
    if packet != candidate_packet or key != candidate_key:
        raise TransferError('packet/key do not match frozen generation rules or source hashes')


def _response_map(packet: dict, response: dict) -> dict[str, dict]:
    if (not isinstance(response, dict) or set(response) != {'format', 'packet_hash', 'reader_id', 'items'} or
            response['format'] != RESPONSE_FORMAT or response['packet_hash'] != digest(packet) or
            not isinstance(response['reader_id'], str) or not response['reader_id'].strip() or
            len(response['reader_id']) > 96 or not isinstance(response['items'], list)):
        raise TransferError('response metadata mismatched or malformed')
    ids = {row['id'] for row in packet['items']}
    mapping: dict[str, dict] = {}
    for row in response['items']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            raise TransferError('invalid response item')
        ident = row['id']
        if ident in mapping or ident not in ids:
            raise TransferError('duplicate or unknown response ID')
        if packet['task'] == 'reconstruct':
            if set(row) != {'id', 'reconstruction', 'abstain'} or type(row['abstain']) is not bool or not isinstance(row['reconstruction'], str):
                raise TransferError('reconstruction row needs id, reconstruction, abstain')
            if (row['abstain'] and row['reconstruction'].strip()) or (not row['abstain'] and not row['reconstruction'].strip()):
                raise TransferError('abstain and nonempty reconstruction must agree')
            if len(row['reconstruction']) > 4000:
                raise TransferError('reconstruction exceeds length limit')
        elif set(row) != {'id', 'choice'} or row['choice'] not in (None, 'A', 'B', 'C'):
            raise TransferError('contrast choice must be A, B, C or null (abstain)')
        mapping[ident] = row
    if set(mapping) != ids:
        raise TransferError('response must include every item exactly once')
    return mapping


def _ratings_map(packet: dict, response: dict, ratings: dict | None) -> dict[str, dict] | None:
    if ratings is None:
        return None
    if (not isinstance(ratings, dict) or set(ratings) != {'format', 'packet_hash', 'rater_id', 'items'} or
            ratings['format'] != RATING_FORMAT or ratings['packet_hash'] != digest(packet) or
            not isinstance(ratings['rater_id'], str) or not ratings['rater_id'].strip() or
            not isinstance(ratings['items'], list)):
        raise TransferError('rating format or packet reference invalid')
    if ratings['rater_id'] == response['reader_id']:
        raise TransferError('reader should not self-adjudicate')
    mapping = {}
    for row in ratings['items']:
        if (not isinstance(row, dict) or set(row) != {'id', 'fidelity', 'critical_structure', 'note'} or
                not isinstance(row['id'], str) or row['id'] in mapping or
                type(row['fidelity']) is not int or row['fidelity'] not in (0, 1, 2, 3) or
                type(row['critical_structure']) is not bool or not isinstance(row['note'], str)):
            raise TransferError('invalid or duplicate rating')
        mapping[row['id']] = row
    return mapping


def grade(packet: dict, key: dict, response: dict, ratings: dict | None = None) -> dict:
    verify_trial(packet, key)
    rmap = _response_map(packet, response)
    ratings_map = _ratings_map(packet, response, ratings)
    if packet['task'] == 'contrast' and ratings is not None:
        raise TransferError('human ratings are only used for free reconstruction')
    if packet['task'] == 'reconstruct':
        answered_ids = {i for i, row in rmap.items() if not row['abstain']}
        if ratings_map is not None and set(ratings_map) != answered_ids:
            raise TransferError('all and only non-abstained reconstructions require independent ratings')
    by_domain: dict[str, dict[str, int]] = {}
    correct = 0
    answered = 0
    fidelity_sum = 0
    structure_kept = 0
    for item in key['items']:
        ident, domain = item['id'], item['domain']
        local = by_domain.setdefault(domain, {'items': 0, 'answered': 0})
        local['items'] += 1
        row = rmap[ident]
        is_answered = (not row['abstain']) if packet['task'] == 'reconstruct' else (row['choice'] is not None)
        answered += int(is_answered)
        local['answered'] += int(is_answered)
        if packet['task'] == 'contrast':
            is_correct = row['choice'] == item['correct_choice']
            correct += int(is_correct)
            local['correct'] = local.get('correct', 0) + int(is_correct)
        elif ratings_map and is_answered:
            fidelity_sum += ratings_map[ident]['fidelity']
            structure_kept += int(ratings_map[ident]['critical_structure'])
    total = len(key['items'])
    report: dict[str, Any] = {
        'format': REPORT_FORMAT, 'task': packet['task'], 'condition': packet['condition'],
        'reader_id': response['reader_id'], 'packet_hash': key['packet_hash'],
        'source_hashes': key['source_hashes'], 'seed': packet['seed'],
        'total_items': total, 'answered': answered, 'abstained': total - answered,
        'by_domain': dict(sorted(by_domain.items())),
        'independent_ai_reader_result': 'external_response_supplied_unverified',
        'note': 'Public benchmarks are not held out; report records externally supplied responses, not verified model identity or independence.'
    }
    if packet['task'] == 'contrast':
        report.update(correct=correct, accuracy_all=round(correct / total, 6),
                      accuracy_answered=round(correct / answered, 6) if answered else None)
    else:
        report['human_ratings_supplied'] = ratings_map is not None
        if ratings_map is not None:
            report['rater_id'] = ratings['rater_id']
            report['mean_fidelity_answered_0_to_3'] = round(fidelity_sum / answered, 6) if answered else None
            report['mean_fidelity_all_0_to_3'] = round(fidelity_sum / total, 6)
            report['critical_structure_rate_all'] = round(structure_kept / total, 6)
        else:
            report['mean_fidelity_all_0_to_3'] = None
            report['critical_structure_rate_all'] = None
    return report


def compare_reports(reports: list[dict]) -> dict:
    if len(reports) < 2 or any(not isinstance(r, dict) or r.get('format') != REPORT_FORMAT for r in reports):
        raise TransferError('compare needs at least two v0.9 grading reports')
    if len({r['condition'] for r in reports}) != len(reports):
        raise TransferError('conditions must be different across comparison reports')
    if len({r['reader_id'] for r in reports}) != len(reports):
        raise TransferError('avoid repeated reader exposure across conditions')
    if len({r['task'] for r in reports}) != 1 or len({r['total_items'] for r in reports}) != 1 or len({r['seed'] for r in reports}) != 1 or len({digest(r['source_hashes']) for r in reports}) != 1:
        raise TransferError('only comparable tasks and unchanged benchmark sources may be compared')
    return {
        'format': 'ALCG-transfer-comparison-v0.9', 'task': reports[0]['task'],
        'arms': [{'condition': r['condition'], 'reader_id': r['reader_id'],
                  'answered': r['answered'], 'total': r['total_items'],
                  'score': r.get('accuracy_all') if r['task'] == 'contrast' else r.get('mean_fidelity_all_0_to_3')}
                 for r in sorted(reports, key=lambda r: r['condition'])],
        'note': 'Descriptive cross-reader comparison only; no random assignment, model identity verification, or causal significance.'
    }


def check_protocol() -> dict:
    cases, probes, _, mapping = fixtures()
    checks = 0
    for task in TASKS:
        per_task: dict[str, list[str]] = {}
        for condition in CONDITIONS:
            packet, key = make_trial(task=task, condition=condition)
            verify_trial(packet, key)
            identifiers = [i['source_id'] for i in key['items']]
            per_task[condition] = identifiers
            assert len(identifiers) == (24 if task == 'reconstruct' else 12)
            if condition == 'glossary':
                assert len(packet['glossary']) > 0
            else:
                assert 'glossary' not in packet
            template = response_template(packet, 'synthetic-abstain-control')
            report = grade(packet, key, template)
            assert report['answered'] == 0
            checks += 1
        if not all(ids == per_task['unaided'] for ids in per_task.values()):
            raise TransferError('item order drift between trial conditions')
    return {'version': '0.9', 'tasks': list(TASKS), 'conditions': list(CONDITIONS),
            'reconstruction_items': len(cases), 'contrast_items': len(probes),
            'condition_task_packets': checks, 'patterns': len(mapping),
            'probe_domain_counts': dict(sorted(Counter(c['domain'] for c in cases if c['source_id'] in {p['source_id'] for p in probes}).items())),
            'frozen_source_hashes': fixture_hashes(),
            'independent_reader_results': None,
            'note': 'Deterministic protocol validation only. Zero external model calls; no independent comprehension score.'}


def new_file(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + '\n')


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.9 three-condition pattern-transfer trials (no model calls)')
    sub = cli.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('report')
    prep = sub.add_parser('prepare')
    prep.add_argument('--task', choices=TASKS, required=True)
    prep.add_argument('--condition', choices=CONDITIONS, required=True)
    prep.add_argument('--seed', type=int, default=20261108)
    prep.add_argument('--packet', type=Path, required=True)
    prep.add_argument('--key', type=Path, required=True)
    prep.add_argument('--response-template', type=Path)
    prep.add_argument('--reader-id', default='external-reader-001')
    scoring = sub.add_parser('grade')
    scoring.add_argument('--packet', type=Path, required=True)
    scoring.add_argument('--key', type=Path, required=True)
    scoring.add_argument('--responses', type=Path, required=True)
    scoring.add_argument('--ratings', type=Path)
    scoring.add_argument('--out', type=Path)
    cmp = sub.add_parser('compare')
    cmp.add_argument('reports', type=Path, nargs='+')
    args = cli.parse_args(argv)
    try:
        if args.command in ('check', 'report'):
            r = check_protocol()
            print(f"OK: {r['condition_task_packets']} packet configurations, {r['reconstruction_items']} reconstruction and {r['contrast_items']} contrast sources" if args.command == 'check' else json.dumps(r, ensure_ascii=False, indent=2))
        elif args.command == 'prepare':
            packet, key = make_trial(task=args.task, condition=args.condition, seed=args.seed)
            filenames = [args.packet, args.key] + ([args.response_template] if args.response_template else [])
            if len({p.resolve() for p in filenames}) != len(filenames) or any(p.exists() for p in filenames):
                raise TransferError('output paths must differ and must not already exist')
            new_file(args.packet, packet)
            new_file(args.key, key)
            if args.response_template:
                new_file(args.response_template, response_template(packet, args.reader_id))
            print(f"Wrote {len(packet['items'])} {args.task} tasks for {args.condition}; keep key private from reader")
        elif args.command == 'grade':
            packet = json.loads(args.packet.read_text(encoding='utf-8'))
            key = json.loads(args.key.read_text(encoding='utf-8'))
            response = json.loads(args.responses.read_text(encoding='utf-8'))
            ratings = json.loads(args.ratings.read_text(encoding='utf-8')) if args.ratings else None
            result = grade(packet, key, response, ratings)
            if args.out:
                new_file(args.out, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            result = compare_reports([json.loads(f.read_text(encoding='utf-8')) for f in args.reports])
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (TransferError, PatternError, BenchmarkError, OSError, ValueError, KeyError, TypeError, RecursionError, AssertionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
