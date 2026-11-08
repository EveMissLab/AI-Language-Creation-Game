"""ALCG v0.18: bounded exhaustive observational-equivalence mechanism search.

This module enumerates 16 Boolean off-observation completions per v0.17 family.
It is *not* empirical causal discovery, universal model search, or AI comprehension.
The structural source SIGNAL is naturally copied from U; only do(SIGNAL=0/1)
exposes values away from the observational support SIGNAL=U.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from causal_lab import BooleanSCM, CausalError, parse_cause
import causal_robustness as v17

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / 'data' / 'mechanism-search-space-v0.18.json'
REPORT_PATH = ROOT / 'reports' / 'mechanism-search-v0.18.json'
FIXTURE_SHA256 = '8e56da78a59fae8a3c7c65940b2a44b2d351d8a155cded02308f75b3173e0589'
REPORT_V17_SHA256 = 'e10073f903a77017ebae9c8571359f02028fa79276f6523f1da25aa6972838b3'
FORMAT = 'ALCG-v0.18-observational-completion-search'
CONTEXTS = ((False, False), (False, True), (True, False), (True, True))  # U, G


class SearchError(ValueError):
    """Invalid search space, mismatched frozen evidence or corrupted witness."""


def search_spec() -> dict[str, Any]:
    """The full, predeclared search class, independent of any results."""
    return {
        'format': FORMAT,
        'provenance': 'deterministic assistant-authored finite Boolean mechanism experiment',
        'original_family_fixture_sha256': FIXTURE_SHA256,
        'original_family_report_sha256': REPORT_V17_SHA256,
        'intervention_source': 'SIGNAL',
        'exogenous_order': ['U', 'G'],
        'natural_source_equation': 'SIGNAL=U',
        'outcome_indicator': 'Y',
        'background_order_U_G': [[u, g] for u, g in CONTEXTS],
        'candidate_masks': list(range(16)),
        'candidate_formula': 'Y=B(U,G) XOR ((SIGNAL XOR U) AND H(U,G))',
        'mask_rule': 'bit i of H is its Boolean value at background_order_U_G[i]',
        'baseline_rule': 'B(U,G) equals the first v0.17 family model observed Y for that context',
        'scope': ('All 16 Boolean off-support completions of the first model observed response '
                  'on the fixed two-bit U,G domain, not all SCMs or real-world causal models.'),
        'selection_rule': ('Enumerate masks ascending. For existing nonvacuous stability claims, select '
                           'the first model that violates the original family invariant.'),
        'no_promotion': True,
        'no_independent_reader_or_empirical_data': True,
    }


def serialized_spec() -> str:
    return json.dumps(search_spec(), ensure_ascii=False, indent=2) + '\n'


def _guard_inputs() -> None:
    v17._guard_inputs()
    for path, digest in ((v17.FIXTURE, FIXTURE_SHA256), (v17.REPORT, REPORT_V17_SHA256)):
        try:
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise SearchError(f'frozen v0.17 artifact modified: {path.name}')
        except OSError as exc:
            raise SearchError(f'cannot read frozen v0.17 artifact {path.name}') from exc
    try:
        if SPEC_PATH.read_text(encoding='utf-8') != serialized_spec():
            raise SearchError('v0.18 search space no longer matches its deterministic specification')
    except OSError as exc:
        raise SearchError('v0.18 search space file unavailable') from exc


def _anchor_observations(family: v17.Family) -> tuple[bool, ...]:
    source, effect = parse_cause(family.expression)
    first = family.models[0]
    if first.exogenous != ('U', 'G') or source != 'SIGNAL' or first.outcomes.get(effect) != 'Y':
        raise SearchError('model family exceeds fixed source, background or indicator assumptions')
    if len(family.models) != 3:
        raise SearchError('v0.18 is pinned to the three v0.17 mechanisms per family')
    observations: list[bool] = []
    for u, g in CONTEXTS:
        context = {'U': u, 'G': g}
        row = first.run(context)
        if row['SIGNAL'] != u:
            raise SearchError('natural observed source is not SIGNAL=U')
        observations.append(row['Y'])
    return tuple(observations)


def _mask_for(values: tuple[bool, ...]) -> int:
    if len(values) != 4 or any(type(v) is not bool for v in values):
        raise SearchError('expected four Boolean responses')
    return sum((1 << i) for i, value in enumerate(values) if value)


def construct(family: v17.Family, mask: int) -> BooleanSCM:
    """Compile an observationally identical but potentially intervention-distinct SCM."""
    if type(mask) is not int or not 0 <= mask < 16:
        raise SearchError('completion mask must be an integer in 0..15')
    base_mask = _mask_for(_anchor_observations(family))
    source, effect = parse_cause(family.expression)
    equations: list[dict] = []

    def add(name: str, op: str, *args: str) -> None:
        equations.append({'name': name, 'op': op, 'args': list(args)})

    add(source, 'copy', 'U')
    add('ZERO', 'xor', 'U', 'U')
    add('NU', 'not', 'U')
    add('NG', 'not', 'G')

    def table(target: str, truth_mask: int) -> None:
        terms = []
        for index, (u, g) in enumerate(CONTEXTS):
            if truth_mask & (1 << index):
                term = f'{target}_T{index}'
                add(term, 'and', 'U' if u else 'NU', 'G' if g else 'NG')
                terms.append(term)
        if not terms:
            add(target, 'copy', 'ZERO')
            return
        acc = terms[0]
        for index, term in enumerate(terms[1:], 1):
            new = f'{target}_OR{index}'
            add(new, 'or', acc, term)
            acc = new
        add(target, 'copy', acc)

    table('BASE', base_mask)
    table('H', mask)
    add('DISCORD', 'xor', source, 'U')
    add('DELTA', 'and', 'DISCORD', 'H')
    add('Y', 'xor', 'BASE', 'DELTA')
    if len(equations) > 24:
        raise SearchError('compiled circuit exceeds bounded BooleanSCM grammar')
    row = {
        'case_id': f'{family.family_id.replace("F17_", "F18_")}_H{mask:02d}',
        'mechanism': f'observational_completion_H{mask:02d}',
        'exogenous': ['U', 'G'],
        'equations': equations,
        'outcomes': [{'subject': effect[0], 'property': effect[1], 'indicator': 'Y'}],
        'note': ('Synthetic circuit; matches the first v0.17 model on SIGNAL=U; '
                 'mask determines four off-support Boolean completions.'),
    }
    model = BooleanSCM.from_data(row)
    for index, (u, g) in enumerate(CONTEXTS):
        context = {'U': u, 'G': g}
        if model.run(context)['Y'] != bool(base_mask & (1 << index)):
            raise SearchError('compiler failed observational equivalence')
    return model


def _responses(model: BooleanSCM, family: v17.Family) -> list[dict]:
    source, effect = parse_cause(family.expression)
    indicator = model.outcomes[effect]
    output = []
    for index, (u, g) in enumerate(CONTEXTS):
        context = {'U': u, 'G': g}
        before = model.run(context)
        low = model.run(context, intervene={source: False})[indicator]
        high = model.run(context, intervene={source: True})[indicator]
        output.append({
            'context_index': index, 'context': context,
            'observed_source': before[source], 'observed_Y': before[indicator],
            'do_false_Y': low, 'do_true_Y': high,
            'direction': v17._direction(low, high),
        })
    return output


def _signature(responses: list[dict]) -> tuple[tuple[bool, bool], ...]:
    return tuple((r['do_false_Y'], r['do_true_Y']) for r in responses)


def _original_signatures(family: v17.Family) -> dict[str, tuple]:
    return {model.case_id: _signature(_responses(model, family)) for model in family.models}


def _classification_witness(before: dict, model_rows: list[dict]) -> tuple[bool, dict | None]:
    """Test *the old* invariant, not the false assertion that all new models agree."""
    cls = before['classification']
    reference = before['model_results']
    if cls == 'no_common_nonzero_direction':
        # A previously absent common direction cannot be refuted by adding members.
        return False, None
    allowed = {r['context_index'] for r in before['robust_nonzero_direction_contexts']}
    for index, candidate in enumerate(model_rows):
        old = [m['responses'][index] for m in reference]
        if cls == 'exact_intervention_response_invariant':
            disagreement = (candidate['do_false_Y'], candidate['do_true_Y']) != (
                old[0]['do_false_indicator'], old[0]['do_true_indicator'])
        elif cls == 'qualitative_direction_invariant_only':
            disagreement = candidate['direction'] != old[0]['direction']
        elif cls == 'context_limited_direction_invariant':
            disagreement = index in allowed and candidate['direction'] != old[0]['direction']
        else:
            raise SearchError(f'unsupported stability category: {cls}')
        if disagreement:
            return True, {
                'context_index': index, 'context': candidate['context'],
                'original_models': [
                    {'case_id': row['case_id'],
                     'do_false_Y': old_row['do_false_indicator'],
                     'do_true_Y': old_row['do_true_indicator'],
                     'direction': old_row['direction']}
                    for row, old_row in zip(reference, old)
                ],
                'candidate': {
                    'do_false_Y': candidate['do_false_Y'],
                    'do_true_Y': candidate['do_true_Y'],
                    'direction': candidate['direction'],
                },
            }
    return False, None


def search_family(family: v17.Family) -> dict:
    old = v17._evaluate_family(family)
    orig_signatures = _original_signatures(family)
    baseline_observations = _anchor_observations(family)
    all_signatures: set[tuple] = set()
    candidates = []
    for mask in range(16):
        candidate = construct(family, mask)
        rows = _responses(candidate, family)
        signature = _signature(rows)
        if signature in all_signatures:
            raise SearchError('duplicate completions in the purported exhaustive class')
        all_signatures.add(signature)
        matches = [r['observed_Y'] == baseline_observations[i] for i, r in enumerate(rows)]
        if not all(matches):
            raise SearchError('candidate changed an observed anchor response')
        broken, witness = _classification_witness(old, rows)
        # This *augmented* classification is relative to the original three plus candidate.
        extended = v17.Family(family.family_id, family.expression, family.question,
                              family.models + (candidate,))
        new = v17._evaluate_family(extended)
        if old['classification'] == 'no_common_nonzero_direction' and new['classification'] != old['classification']:
            raise SearchError('extension fabricated a previously absent invariant')
        if broken:
            if old['classification'] == 'exact_intervention_response_invariant' and new['exact_intervention_response_invariant']:
                raise SearchError('reported counterexample did not weaken exact agreement')
            if old['classification'] == 'qualitative_direction_invariant_only' and new['qualitative_direction_invariant']:
                raise SearchError('reported counterexample did not weaken direction agreement')
            if old['classification'] == 'context_limited_direction_invariant':
                before_idx = {x['context_index'] for x in old['robust_nonzero_direction_contexts']}
                after_idx = {x['context_index'] for x in new['robust_nonzero_direction_contexts']}
                if before_idx <= after_idx:
                    raise SearchError('purported context erosion did not remove an old robust context')
        candidates.append({
            'mask': mask, 'model_id': candidate.case_id,
            'structural_equations': len(candidate.equations),
            'observationally_identical_to_first_model': True,
            'matches_original_intervention_signatures': [
                case_id for case_id, sig in orig_signatures.items() if signature == sig],
            'new_intervention_signature': [list(pair) for pair in signature],
            'refutes_original_nonvacuous_invariant': broken,
            'first_violation': witness,
            'augmented_family_classification': new['classification'],
            'remaining_robust_context_indices': [r['context_index'] for r in new['robust_nonzero_direction_contexts']],
        })
    if len(all_signatures) != 16:
        raise SearchError('incomplete Boolean response completion enumeration')
    first = next((r for r in candidates if r['refutes_original_nonvacuous_invariant']), None)
    anchor_sig = orig_signatures[family.models[0].case_id]
    first_anchor_difference = next((r['mask'] for r in candidates
                                    if tuple(tuple(x) for x in r['new_intervention_signature']) != anchor_sig), None)
    return {
        'family_id': family.family_id, 'expression': family.expression,
        'observational_anchor_id': family.models[0].case_id,
        'anchor_observations_U_G': list(baseline_observations),
        'anchor_baseline_truth_mask': _mask_for(baseline_observations),
        'original_classification': old['classification'],
        'original_robust_context_indices': [x['context_index'] for x in old['robust_nonzero_direction_contexts']],
        'completion_count': len(candidates), 'unique_full_intervention_signatures': len(all_signatures),
        'first_refuting_mask': first['mask'] if first else None,
        'first_refuting_witness': first['first_violation'] if first else None,
        'first_anchor_intervention_difference_mask': first_anchor_difference,
        'counterexample_claim_scope': ('Finite family stability under addition of one '
                                       'observationally anchor-compatible synthetic mechanism.'),
        'candidates': candidates,
    }


def report() -> dict:
    _guard_inputs()
    families = v17.load_families()
    if len(families) != 7 or any(len(f.models) != 3 for f in families):
        raise SearchError('unexpected v0.17 baseline family size')
    results = [search_family(family) for family in families]
    counts = Counter(row['original_classification'] for row in results)
    refuted = [row for row in results if row['first_refuting_mask'] is not None]
    return {
        'format': FORMAT, 'search_space_sha256': sha256(SPEC_PATH.read_bytes()).hexdigest(),
        'pinned_v017_family_fixture_sha256': FIXTURE_SHA256,
        'pinned_v017_family_report_sha256': REPORT_V17_SHA256,
        'provenance': ('Deterministically synthesized finite SCMs from seven earlier, assistant-authored '
                       'families. No empirical observations or independent AI readers.'),
        'scope': ('Only 16 off-observation completions per first-model anchor with Boolean U,G,SIGNAL,Y. '
                  'Observed SIGNAL=U; candidate variables may respond differently to do(SIGNAL=0/1). '
                  'A witness refutes only a previously true finite-family stability property under '
                  'this specified extension, not an actual universal causal theorem.'),
        'summary': {
            'families': len(results), 'original_models': sum(len(f.models) for f in families),
            'candidates_per_family': 16, 'candidate_models': sum(r['completion_count'] for r in results),
            'candidate_observation_evaluations': sum(4 * r['completion_count'] for r in results),
            'candidate_intervention_evaluations': sum(8 * r['completion_count'] for r in results),
            'all_candidates_observationally_match_anchor': True,
            'distinct_intervention_signatures_per_family': 16,
            'original_classification_counts': dict(sorted(counts.items())),
            'families_with_nonvacuous_invariant': sum(r['original_classification'] != 'no_common_nonzero_direction' for r in results),
            'nonvacuous_invariants_refuted_by_a_completion': len(refuted),
            'families_with_preexisting_noninvariance': sum(r['original_classification'] == 'no_common_nonzero_direction' for r in results),
            'universal_causal_theorem_proved_or_refuted': False,
            'independent_ai_readers': 0, 'empirical_causal_evidence': None,
            'ai_comprehension_score': None, 'active_registry_changed': False,
        },
        'families': results,
    }


def replay(family_id: str, mask: int, context_index: int) -> dict:
    _guard_inputs()
    if type(mask) is not int or mask < 0 or mask > 15:
        raise SearchError('mask must be an integer between 0 and 15')
    if type(context_index) is not int or context_index not in range(4):
        raise SearchError('context index must be one of 0,1,2,3')
    families = {f.family_id: f for f in v17.load_families()}
    if family_id not in families:
        raise SearchError('unknown family identifier')
    family = families[family_id]
    generated = construct(family, mask)
    context = {'U': CONTEXTS[context_index][0], 'G': CONTEXTS[context_index][1]}
    originals = [_responses(model, family)[context_index] for model in family.models]
    candidate = _responses(generated, family)[context_index]
    return {
        'family_id': family_id, 'mask': mask, 'context_index': context_index,
        'context': context, 'source': 'SIGNAL',
        'expression': family.expression,
        'generated_scm': {
            'case_id': generated.case_id, 'exogenous': list(generated.exogenous),
            'equations': [dict(name=e.name, op=e.op, args=list(e.args)) for e in generated.equations],
            'outcomes': [{'subject': k[0], 'property': k[1], 'indicator': v} for k,v in generated.outcomes.items()],
        },
        'original_model_responses': [{'case_id': model.case_id, **row} for model, row in zip(family.models, originals)],
        'new_model_response': candidate,
        'observational_equivalence_to_anchor': candidate['observed_Y'] == originals[0]['observed_Y'],
        'reality_claim': 'none',
    }


def check_report() -> dict:
    saved = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    recalculated = report()
    if saved != recalculated:
        raise SearchError('saved v0.18 report diverges from exhaustive deterministic recomputation')
    for family in saved['families']:
        mask = family['first_refuting_mask']
        if mask is None:
            continue
        index = family['first_refuting_witness']['context_index']
        roundtrip = replay(family['family_id'], mask, index)
        if not roundtrip['observational_equivalence_to_anchor']:
            raise SearchError('replayed candidate lost observational equivalence')
        if roundtrip['new_model_response']['do_false_Y'] != family['first_refuting_witness']['candidate']['do_false_Y']:
            raise SearchError('replay failed low intervention receipt')
        if roundtrip['new_model_response']['do_true_Y'] != family['first_refuting_witness']['candidate']['do_true_Y']:
            raise SearchError('replay failed high intervention receipt')
    return {'ok': True, 'families': len(saved['families']),
            'candidate_models_verified': saved['summary']['candidate_models'],
            'all_observations_anchored': True, 'frozen_v017_inputs_unchanged': True,
            'published_patterns_changed': False, 'independent_ai_readers': 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'report', 'summary', 'replay', 'emit-space'))
    parser.add_argument('--family', default='F17_DIRECT')
    parser.add_argument('--mask', type=int, default=0)
    parser.add_argument('--context-index', type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == 'emit-space':
            print(serialized_spec(), end='')
            return 0
        if args.command == 'report':
            result = report()
        elif args.command == 'summary':
            result = report()['summary']
        elif args.command == 'check':
            result = check_report()
        else:
            result = replay(args.family, args.mask, args.context_index)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (SearchError, v17.RobustnessError, CausalError, OSError, ValueError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
