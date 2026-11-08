"""ALCG v0.15: bounded witness search for v0.14 generated contrasts.

This is *model-theoretic synthetic testing*, not interpretation of real-world
causation, English truth, or measured comprehension by independent AI readers.
Only BEFORE, EXISTS/FORALL, and NOT/MAY over EQUAL/LESS_THAN/GREATER_THAN
receive model interpretations. CAUSE remains explicitly uninterpreted.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from alcg import Call, Expr, Name, parse, render
from challenge_generator import SUITE, verify as verify_generator
from coverage_lab import jsonl
from finite_probe import FiniteModel, ProbeError, evaluate
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / 'reports' / 'bounded-counterexamples-v0.15.json'
VERSION = 'ALCG-v0.15-bounded-witness'
# Pin the pre-existing v0.14 question corpus independently of this release.
SOURCE_SHA256 = '0d40a9effbf8c3f559269d5a300a6160e5ed3ef251b0bd2b2ad18651c60f8802'
WORLDS = ('actual', 'possible')


class WitnessError(ValueError):
    """Bad model or unverifiable witness fixture; fail closed."""


def _roles(node: Expr, op: str, required: tuple[str, ...]) -> dict[str, Expr]:
    if not isinstance(node, Call) or node.name != op or set(dict(node.args)) != set(required):
        raise WitnessError(f'{op} expected roles {required}')
    return dict(node.args)


def _identifier(node: Expr, label: str) -> str:
    if not isinstance(node, Name):
        raise WitnessError(f'{label} must be a plain name')
    return node.value


def _comparator(node: Expr, *, allow_ref: bool = False) -> tuple[str, str, str]:
    args = _roles(node, 'COMPARE', ('left', 'right', 'by'))
    if allow_ref:
        left = 'REF:' + _identifier(_roles(args['left'], 'REF', ('var',))['var'], 'REF.var')
    else:
        left = _identifier(args['left'], 'COMPARE.left')
    right = _identifier(args['right'], 'COMPARE.right')
    comparator = _identifier(args['by'], 'COMPARE.by')
    if comparator not in ('EQUAL', 'LESS_THAN', 'GREATER_THAN'):
        raise WitnessError('comparison outside bounded finite oracle')
    return left, right, comparator


def _empty_model(*, domains: dict[str, tuple[str, ...]] | None = None,
                 order: dict[str, int] | None = None,
                 before: frozenset[tuple[str, str]] = frozenset()) -> FiniteModel:
    return FiniteModel(
        domains={} if domains is None else domains,
        facts={w: frozenset() for w in WORLDS},
        before={'actual': before, 'possible': frozenset()},
        accessible={'actual': ('actual',), 'possible': ('possible',)},
        order={} if order is None else order,
    )


def _event(node: Expr) -> str:
    args = _roles(node, 'DO', ('action', 'actor', 'object'))
    for role, expr in args.items():
        _identifier(expr, f'DO.{role}')
    return render(Call('DO', tuple((role, args[role]) for role in ('actor', 'action', 'object'))))


def _before_edge(node: Expr) -> tuple[str, str]:
    args = _roles(node, 'BEFORE', ('earlier', 'later'))
    return _event(args['earlier']), _event(args['later'])


def _exists_model(base: Expr, other: Expr) -> FiniteModel:
    a = _roles(base, 'EXISTS', ('claim', 'domain', 'var'))
    comparator = _comparator(a['claim'], allow_ref=True)
    left, right, by = comparator
    if left != 'REF:' + _identifier(a['var'], 'EXISTS.var'):
        raise WitnessError('quantifier binding mismatch')
    domain = _identifier(a['domain'], 'EXISTS.domain')
    # EQUAL has literal identifier equality in this very limited oracle.
    good = right if by == 'EQUAL' else ('V15_LOW' if by == 'LESS_THAN' else 'V15_HIGH')
    bad = 'V15_UNEQUAL' if by == 'EQUAL' else ('V15_HIGH' if by == 'LESS_THAN' else 'V15_LOW')
    if len({good, bad}) != 2 or right in ('V15_LOW', 'V15_HIGH', 'V15_UNEQUAL'):
        raise WitnessError('reserved witness identifiers collide with fixture')
    domains = {domain: (good, bad)}
    if isinstance(other, Call) and other.name == 'EXISTS':
        b = _roles(other, 'EXISTS', ('claim', 'domain', 'var'))
        alternative = _identifier(b['domain'], 'alternate EXISTS.domain')
        if alternative != domain:
            domains[alternative] = (bad,)
    elif not isinstance(other, Call) or other.name != 'FORALL':
        raise WitnessError('unexpected EXISTS counterpart')
    order = {right: 1, 'V15_LOW': 0, 'V15_HIGH': 2}
    return _empty_model(domains=domains, order=order)


def _candidate_models(left: Expr, right: Expr) -> Iterable[FiniteModel]:
    """Deterministic small *pair-directed* models, not an exhaustive universe.

    The pair directs construction, so witness success is not a held-out score.
    Every reported truth value is then recomputed by finite_probe.evaluate.
    """
    if not isinstance(left, Call):
        raise WitnessError('left expression must be a call')
    if left.name == 'BEFORE':
        orig = _before_edge(left)
        if not isinstance(right, Call) or right.name != 'BEFORE':
            raise WitnessError('unexpected BEFORE control')
        alt = _before_edge(right)
        for edges in (frozenset({orig}), frozenset({alt}), frozenset()):
            yield _empty_model(before=edges)
    elif left.name == 'EXISTS':
        yield _exists_model(left, right)
    elif left.name == 'NOT':
        a = _roles(left, 'NOT', ('claim',))
        ls, rs, comp = _comparator(a['claim'])
        if not isinstance(right, Call) or right.name not in ('NOT', 'MAY'):
            raise WitnessError('unexpected NOT control')
        ra = _roles(right, right.name, ('claim',))
        left2, right2, comp2 = _comparator(ra['claim'])
        if comp != comp2 or ls != left2:
            raise WitnessError('unexpected comparator/left drift')
        values = sorted({ls, rs, right2})
        if len(values) > 3:
            raise WitnessError('unexpected value diversity')
        for ranks in product(range(3), repeat=len(values)):
            yield _empty_model(order=dict(zip(values, ranks)))
    else:
        raise WitnessError('operator has no bounded witness strategy')


def model_to_data(model: FiniteModel) -> dict[str, Any]:
    return {
        'domains': {k: list(v) for k, v in sorted(model.domains.items())},
        'facts': {w: [list(p) for p in sorted(model.facts[w])] for w in WORLDS},
        'before': {w: [list(p) for p in sorted(model.before[w])] for w in WORLDS},
        'accessibility': {w: list(model.accessible[w]) for w in WORLDS},
        'order': dict(sorted(model.order.items())),
    }


def model_from_data(data: dict[str, Any]) -> FiniteModel:
    """Strictly reconstruct the executable finite model from a result receipt."""
    if not isinstance(data, dict) or set(data) != {'domains', 'facts', 'before', 'accessibility', 'order'}:
        raise WitnessError('invalid witness model fields')
    for key in ('facts', 'before', 'accessibility'):
        if not isinstance(data[key], dict) or set(data[key]) != set(WORLDS):
            raise WitnessError(f'invalid {key} worlds')
    if not isinstance(data['domains'], dict) or not isinstance(data['order'], dict):
        raise WitnessError('bad domain or rank map')
    domains: dict[str, tuple[str, ...]] = {}
    for k, vals in data['domains'].items():
        if (not isinstance(k, str) or not isinstance(vals, list) or
                not all(isinstance(x, str) and x for x in vals) or len(vals) != len(set(vals))):
            raise WitnessError('bad domain values')
        domains[k] = tuple(vals)
    maps = {}
    for key in ('facts', 'before'):
        part = {}
        for world, pairs in data[key].items():
            if not isinstance(pairs, list) or not all(
                    isinstance(p, list) and len(p) == 2 and all(isinstance(q, str) for q in p)
                    for p in pairs):
                raise WitnessError(f'invalid {key} edge')
            if len(set(map(tuple, pairs))) != len(pairs):
                raise WitnessError('duplicate pair in witness')
            part[world] = frozenset(tuple(p) for p in pairs)
        maps[key] = part
    accesses = {}
    for world, targets in data['accessibility'].items():
        if (not isinstance(targets, list) or len(targets) != len(set(targets)) or
                any(t not in WORLDS for t in targets)):
            raise WitnessError('bad accessibility list')
        accesses[world] = tuple(targets)
    if not all(isinstance(k, str) and type(v) is int for k, v in data['order'].items()):
        raise WitnessError('bad ordered rank')
    model = FiniteModel(domains, maps['facts'], maps['before'], accesses, data['order'])
    if model_to_data(model) != data:
        raise WitnessError('witness model serialization is noncanonical')
    return model


def _find_witness(left: str, right: str) -> tuple[dict[str, Any] | None, int]:
    checked = 0
    for model in _candidate_models(parse(left), parse(right)):
        left_truth = evaluate(left, model)
        right_truth = evaluate(right, model)
        checked += 1
        if left_truth != right_truth:
            receipt = {'world': 'actual', 'model': model_to_data(model),
                       'left': left_truth, 'right': right_truth}
            return receipt, checked
    return None, checked


def audit() -> dict[str, Any]:
    verify_generator()  # Independently verify v0.14 fixtures and prior pinned inputs.
    if sha256(SUITE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise WitnessError('the immutable v0.14 challenge source changed')
    suite = jsonl(SUITE)
    findings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    checked_total = 0
    for row in suite:
        original = row['expression']
        root = row['root']
        for variant in row['variants']:
            text = variant['expression']
            same = normalize(original) == normalize(text)
            if same != variant['canonical_equal']:
                raise WitnessError('v0.14 canonical expectation changed')
            entry: dict[str, Any] = {
                'case_id': row['id'], 'root': root, 'variant': variant['type'],
                'canonical_equal': same, 'status': None, 'models_examined': 0,
                'witness': None,
            }
            if same:
                entry['status'] = 'canonical_equivalent'
                # CAUSE has no truth semantics. Do NOT claim finite confirmation.
                if root != 'CAUSE':
                    # Replay one bounded model as a consistency check; the
                    # stronger equivalence basis is the normalizer, not sampling.
                    base = parse(original)
                    if root == 'BEFORE':
                        model = _empty_model(before=frozenset({_before_edge(base)}))
                    elif root == 'EXISTS':
                        model = _exists_model(base, base)
                    elif root == 'NOT':
                        model = next(iter(_candidate_models(base, parse(text))))
                    else:
                        raise WitnessError('unrecognized equivalence root')
                    entry['models_examined'] = 1
                    if evaluate(original, model) != evaluate(text, model):
                        raise WitnessError('canonical equivalent evaluated differently')
            elif root == 'CAUSE':
                entry['status'] = 'unsupported_causality'
            else:
                witness, examined = _find_witness(original, text)
                checked_total += examined
                entry['models_examined'] = examined
                entry['witness'] = witness
                entry['status'] = ('finite_counterexample' if witness is not None
                                   else 'no_witness_under_bounded_model')
                if examined < 1:
                    raise WitnessError('empty search cannot justify result')
            counts[entry['status']] += 1
            findings.append(entry)
    if len(suite) != 32 or len(findings) != 104:
        raise WitnessError('unexpected fixed-benchmark dimensions')
    return {
        'format': VERSION,
        'source_generated_suite_sha256': SOURCE_SHA256,
        'cases': len(suite), 'variants': len(findings),
        'counts': dict(sorted(counts.items())),
        'witness_models_examined': checked_total,
        'canonical_equivalences_finite_spot_checked': sum(f['status'] == 'canonical_equivalent'
                                                       and f['models_examined'] > 0 for f in findings),
        'cause_canonical_equivalences_structural_only': sum(f['status'] == 'canonical_equivalent'
                                                           and f['models_examined'] == 0 for f in findings),
        'independent_ai_readers': 0,
        'ai_comprehension_score': None,
        'real_world_semantic_accuracy': None,
        'no_active_registry_change': True,
        'caveat': ('Synthetic pair-directed finite witnesses are existential countermodels within the stated '
                   'toy interpretation, NOT evidence of real-world truth or AI understanding. A missing witness '
                   'does not prove semantic equivalence. CAUSE has no executable oracle in this release.'),
        'findings': findings,
    }


def _row_for(report: dict[str, Any], case_id: str, variant: str) -> dict[str, Any]:
    items = [x for x in report['findings'] if x['case_id'] == case_id and x['variant'] == variant]
    if len(items) != 1:
        raise WitnessError('unknown or ambiguous case/variant selection')
    return items[0]


def replay(case_id: str, variant: str, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refuse a fake witness; recompute both values from its serialized model."""
    report = audit() if result is None else result
    entry = _row_for(report, case_id, variant)
    source = next((r for r in jsonl(SUITE) if r['id'] == case_id), None)
    if source is None:
        raise WitnessError('source record missing')
    foil = next((v['expression'] for v in source['variants'] if v['type'] == variant), None)
    if foil is None:
        raise WitnessError('variant expression missing')
    witness = entry['witness']
    if entry['status'] != 'finite_counterexample' or not isinstance(witness, dict):
        raise WitnessError('selected comparison has no finite counterexample to replay')
    if witness.get('world') != 'actual':
        raise WitnessError('unsupported or tampered witness world')
    model = model_from_data(witness['model'])
    left_truth, right_truth = evaluate(source['expression'], model), evaluate(foil, model)
    if (left_truth == right_truth or type(witness['left']) is not bool or
            type(witness['right']) is not bool or
            (left_truth, right_truth) != (witness['left'], witness['right'])):
        raise WitnessError('witness claim does not match re-evaluation')
    return {'case_id': case_id, 'variant': variant, 'left_expression': source['expression'],
            'right_expression': foil, 'world': witness['world'],
            'left_truth': left_truth, 'right_truth': right_truth,
            'finite_model': witness['model'],
            'interpretation': 'stipulated toy world only; not natural-language correctness'}


def verify() -> dict[str, Any]:
    fresh = audit()
    try:
        stored = json.loads(REPORT.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise WitnessError(f'could not load report: {exc}') from exc
    if fresh != stored:
        raise WitnessError('committed finite counterexample report disagrees with regenerated source')
    for f in fresh['findings']:
        if f['status'] == 'finite_counterexample':
            replay(f['case_id'], f['variant'], result=fresh)
    return fresh


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.15: replayable bounded semantic counterexamples')
    cmd = cli.add_subparsers(dest='command', required=True)
    cmd.add_parser('check', help='regenerate all cases and replay all counterexamples')
    cmd.add_parser('report', help='show summary counts; no independent AI score')
    examine = cmd.add_parser('replay', help='replay one selected finite counterexample')
    examine.add_argument('--case', required=True)
    examine.add_argument('--variant', required=True)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            data = verify()
            print(f'OK: {data["variants"]} v0.14 variants, {data["counts"]}; '
                  'all finite witnesses replayed; CAUSE uninterpreted')
        elif args.command == 'report':
            data = audit()
            print(json.dumps({k: v for k, v in data.items() if k != 'findings'},
                             ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(json.dumps(replay(args.case, args.variant),
                             ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (WitnessError, ProbeError, ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
