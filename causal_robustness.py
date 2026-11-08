"""ALCG v0.17: cross-model bounded causal robustness (not empirical inference).

All results are conditional on deliberately authored Boolean SCMs and the explicit
model family; a universal claim *within* that finite family is not a universal
claim about reality, language comprehension or unseen causal structures.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from causal_lab import BooleanSCM, CausalError, parse_cause
from family_fixtures_v017 import serialized_fixture, FORMAT

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'data' / 'causal-families-v0.17.json'
REPORT = ROOT / 'reports' / 'cross-model-invariance-v0.17.json'
LEGACY_FIXTURE = ROOT / 'data' / 'causal-models-v0.16.json'
LEGACY_REPORT = ROOT / 'reports' / 'causal-intervention-v0.16.json'
ACTIVE_PATTERNS = ROOT / 'data' / 'patterns-v0.8.json'
LEGACY_FIXTURE_SHA256 = 'b2128574b01767da0ff2602663372a62c371f6025c3690b4eb13267337f08851'
LEGACY_REPORT_SHA256 = 'ead89c9c4042460027e99ee105a66b4a81065197b0f4798c37f621b200984167'
ACTIVE_PATTERNS_SHA256 = '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6'


class RobustnessError(ValueError):
    """Invalid versioned fixture, incomparability or receipt mismatch."""


def _exact(row: Any, keys: set[str], label: str) -> dict:
    if not isinstance(row, dict) or set(row) != keys:
        raise RobustnessError(f'{label} must have exactly {sorted(keys)}')
    return row


def _guard_inputs() -> None:
    for path, expected in (
        (LEGACY_FIXTURE, LEGACY_FIXTURE_SHA256),
        (LEGACY_REPORT, LEGACY_REPORT_SHA256),
        (ACTIVE_PATTERNS, ACTIVE_PATTERNS_SHA256),
    ):
        try:
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RobustnessError(f'missing frozen source: {path.name}') from exc
        if digest != expected:
            raise RobustnessError(f'frozen v0.16 or active-registry artifact was modified: {path.name}')
    if FIXTURE.read_text(encoding='utf-8') != serialized_fixture():
        raise RobustnessError('v0.17 fixture differs from deterministic declared mechanisms')


@dataclass(frozen=True)
class Family:
    family_id: str
    expression: str
    question: str
    models: tuple[BooleanSCM, ...]


def load_families(path: Path = FIXTURE) -> tuple[Family, ...]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RobustnessError(f'could not read model families: {exc}') from exc
    data = _exact(data, {'format', 'provenance', 'context_alignment', 'families'}, 'fixture')
    if data['format'] != FORMAT or not isinstance(data['provenance'], str) or 'assistant-authored' not in data['provenance']:
        raise RobustnessError('incorrect fixture version or missing synthetic provenance')
    if not isinstance(data['context_alignment'], str) or not data['context_alignment'].strip():
        raise RobustnessError('missing explicit background alignment assumption')
    items = data['families']
    if not isinstance(items, list) or not (1 <= len(items) <= 20):
        raise RobustnessError('family count must be between 1 and 20')
    families: list[Family] = []
    all_ids: set[str] = set()
    for item in items:
        item = _exact(item, {'family_id', 'expression', 'question', 'models'}, 'family')
        ident = item['family_id']
        if not isinstance(ident, str) or not ident.startswith('F17_') or not ident[4:].replace('_','').isalnum():
            raise RobustnessError('invalid family identifier')
        if ident in all_ids:
            raise RobustnessError('duplicate family ID')
        all_ids.add(ident)
        expression = item['expression']
        if not isinstance(expression, str):
            raise RobustnessError('family claim must be a parseable expression')
        try:
            source, effect = parse_cause(expression)
        except CausalError as exc:
            raise RobustnessError(f'bad CAUSE expression for {ident}: {exc}') from exc
        if not isinstance(item['question'], str) or not item['question'].strip():
            raise RobustnessError('missing model-family question')
        model_data = item['models']
        if not isinstance(model_data, list) or not (2 <= len(model_data) <= 4):
            raise RobustnessError('each family must contain 2-4 alternative models')
        try:
            models = tuple(BooleanSCM.from_data(m) for m in model_data)
        except (CausalError, ValueError, TypeError) as exc:
            raise RobustnessError(f'invalid SCM in {ident}: {exc}') from exc
        first = models[0]
        structures: set[str] = set()
        for model in models:
            if model.case_id in all_ids or not model.case_id.startswith(ident+'_M'):
                raise RobustnessError('duplicate/misnamed model ID across families')
            all_ids.add(model.case_id)
            if model.exogenous != first.exogenous:
                raise RobustnessError('models lack aligned ordered background assignments')
            names = {eq.name for eq in model.equations}
            if source not in names or effect not in model.outcomes:
                raise RobustnessError('unmapped intervention source or named outcome')
            if model.outcomes[effect] != first.outcomes[effect]:
                raise RobustnessError('comparison changed outcome indicator identity')
            # Require actual mechanism alternatives, not three copies of one SCM.
            structure = json.dumps([(eq.name,eq.op,eq.args) for eq in model.equations])
            if structure in structures:
                raise RobustnessError('duplicate structural equation system within family')
            structures.add(structure)
        families.append(Family(ident, expression, item['question'], models))
    return tuple(families)


def _direction(low: bool, high: bool) -> str:
    if low == high:
        return 'unchanged'
    return 'positive' if (not low and high) else 'negative'


def _evaluate_family(family: Family) -> dict:
    source, effect = parse_cause(family.expression)
    first = family.models[0]
    contexts = list(first.contexts())
    model_results = []
    for model in family.models:
        indicator = model.outcomes[effect]
        rows = []
        for index, context in enumerate(contexts):
            before = model.run(context)
            low = model.run(context, intervene={source: False})[indicator]
            high = model.run(context, intervene={source: True})[indicator]
            rows.append({
                'context_index': index, 'context': context,
                'observed_source': before[source],
                'observed_indicator': before[indicator],
                'do_false_indicator': low, 'do_true_indicator': high,
                'direction': _direction(low, high),
            })
        exists = any(row['direction'] != 'unchanged' for row in rows)
        # Cross-check against v0.16's independently implemented influence scan.
        oracle = model.influence(family.expression)
        if oracle['influence_in_some_context'] != exists or oracle['contexts_examined'] != len(contexts):
            raise RobustnessError('v0.16 and v0.17 intervention calculations disagree')
        model_results.append({
            'case_id': model.case_id, 'mechanism': model.mechanism,
            'influence_in_some_context': exists,
            'influence_in_all_contexts': all(row['direction'] != 'unchanged' for row in rows),
            'observational': model.observational_association(family.expression),
            'responses': rows,
        })

    agree_sign = []
    agree_values = []
    robust_nonzero = []
    first_sign_witness = None
    first_value_witness = None
    for index, context in enumerate(contexts):
        signatures = [row['responses'][index] for row in model_results]
        directions = [r['direction'] for r in signatures]
        pairs = [(r['do_false_indicator'],r['do_true_indicator']) for r in signatures]
        same_direction = len(set(directions)) == 1
        same_pair = len(set(pairs)) == 1
        if same_direction:
            agree_sign.append({'context_index': index, 'context': context, 'direction': directions[0]})
            if directions[0] != 'unchanged':
                robust_nonzero.append({'context_index': index, 'context': context, 'direction': directions[0]})
        elif first_sign_witness is None:
            first_sign_witness = {'context_index': index, 'context': context,
                                  'models': [{'case_id': m['case_id'], 'direction': r['direction'],
                                              'do_false': r['do_false_indicator'],
                                              'do_true': r['do_true_indicator']}
                                             for m, r in zip(model_results, signatures)]}
        if same_pair:
            agree_values.append({'context_index': index, 'context': context,
                                 'do_false': pairs[0][0], 'do_true': pairs[0][1]})
        elif first_value_witness is None:
            first_value_witness = {'context_index': index, 'context': context,
                                   'models': [{'case_id': m['case_id'],
                                               'do_false': r['do_false_indicator'],
                                               'do_true': r['do_true_indicator']}
                                              for m, r in zip(model_results, signatures)]}
    exact = len(agree_values) == len(contexts)
    directional = len(agree_sign) == len(contexts)
    if exact:
        category = 'exact_intervention_response_invariant'
    elif directional:
        category = 'qualitative_direction_invariant_only'
    elif robust_nonzero:
        category = 'context_limited_direction_invariant'
    else:
        category = 'no_common_nonzero_direction'
    return {
        'family_id': family.family_id, 'expression': family.expression, 'question': family.question,
        'source': source, 'effect': list(effect),
        'mechanisms': len(family.models), 'backgrounds_per_model': len(contexts),
        'classification': category,
        'exact_intervention_response_invariant': exact,
        'qualitative_direction_invariant': directional,
        'existential_influence_agreement': len({m['influence_in_some_context'] for m in model_results}) == 1,
        'every_model_influential_in_some_context': all(m['influence_in_some_context'] for m in model_results),
        'every_model_influential_in_every_context': all(m['influence_in_all_contexts'] for m in model_results),
        'consistent_direction_contexts': agree_sign,
        'identical_intervention_value_contexts': agree_values,
        'robust_nonzero_direction_contexts': robust_nonzero,
        'first_direction_disagreement': first_sign_witness,
        'first_intervention_value_disagreement': first_value_witness,
        'model_results': model_results,
    }


def report() -> dict:
    _guard_inputs()
    families = load_families()
    results = [_evaluate_family(f) for f in families]
    status_counts = Counter(r['classification'] for r in results)
    return {
        'format': FORMAT,
        'source_fixture_sha256': sha256(FIXTURE.read_bytes()).hexdigest(),
        'pinned_v016_fixture_sha256': LEGACY_FIXTURE_SHA256,
        'pinned_v016_report_sha256': LEGACY_REPORT_SHA256,
        'pinned_public_patterns_sha256': ACTIVE_PATTERNS_SHA256,
        'provenance': 'assistant-authored synthetic alternative SCM families; no observational datasets were fitted',
        'scope': ('Finite, explicit, enumerated models only. Identical U,G labels assume aligned backgrounds. '
                  'CAUSE follows v0.16: existence of a do(source=0/1) contrast in some context, '
                  'not proof that a natural-language claim holds in reality.'),
        'summary': {
            'families': len(families),
            'models': sum(len(f.models) for f in families),
            'background_evaluations': sum(len(m['responses']) for r in results for m in r['model_results']),
            'intervention_evaluations': 2 * sum(len(m['responses']) for r in results for m in r['model_results']),
            'classification_counts': dict(sorted(status_counts.items())),
            'robust_nonzero_contexts': sum(len(r['robust_nonzero_direction_contexts']) for r in results),
            'independent_ai_readers': 0,
            'empirical_causal_evidence': None,
            'ai_comprehension_score': None,
            'active_registry_changed': False,
        },
        'results': results,
    }


def replay(family_id: str, context_index: int, *, receipt: dict | None = None) -> dict:
    if not isinstance(context_index, int) or isinstance(context_index, bool):
        raise RobustnessError('context index must be an integer')
    _guard_inputs()
    families = {fam.family_id: fam for fam in load_families()}
    if family_id not in families:
        raise RobustnessError('unknown family identifier')
    fam = families[family_id]
    contexts = list(fam.models[0].contexts())
    if not (0 <= context_index < len(contexts)):
        raise RobustnessError('context index out of range')
    expected = _evaluate_family(fam)
    if receipt is not None:
        if receipt != expected:
            raise RobustnessError('supplied family receipt differs from recomputed interventions')
    context = contexts[context_index]
    return {
        'family_id': family_id, 'context_index': context_index, 'context': context,
        'individual_models': [
            {'case_id': m['case_id'], 'mechanism': m['mechanism'],
             **m['responses'][context_index]}
            for m in expected['model_results']
        ],
        'direction_agreement': next((row['direction'] for row in expected['consistent_direction_contexts']
                                     if row['context_index'] == context_index), None),
        'classification_in_stipulated_family': expected['classification'],
        'causal_truth_in_reality': 'not established',
    }


def verify_report() -> dict:
    fresh = report()
    try:
        saved = json.loads(REPORT.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RobustnessError(f'committed report missing or invalid: {exc}') from exc
    if saved != fresh:
        raise RobustnessError('committed report diverges from canonical finite-family calculations')
    for row in saved['results']:
        for context_idx in range(row['backgrounds_per_model']):
            replay(row['family_id'], context_idx, receipt=row)
    return {
        'ok': True, 'families_verified': len(saved['results']),
        'model_contexts_replayed': saved['summary']['background_evaluations'],
        'frozen_v016_unchanged': True, 'independent_ai_readers': 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check','report','summary','replay'])
    parser.add_argument('--family', default='F17_CONTEXT')
    parser.add_argument('--context-index', type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == 'check':
            result = verify_report()
        elif args.command == 'report':
            result = report()
        elif args.command == 'summary':
            result = report()['summary']
        else:
            result = replay(args.family, args.context_index)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except (RobustnessError, CausalError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
