"""ALCG v0.20: exact Bayesian updates and cost-aware synthetic experiment selection.

A controlled diagnostic over finite, assistant-authored Boolean SCMs.  Neither
noise parameters nor experimental prices are empirical measurements.  This file
never modifies existing grammar, dictionaries, or the v0.19 noiseless oracle.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from fractions import Fraction
from hashlib import sha256
import json
from math import log2
from pathlib import Path
import sys
from typing import Any

import active_design as old

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / 'data' / 'noisy-design-space-v0.20.json'
REPORT_PATH = ROOT / 'reports' / 'noisy-design-v0.20.json'
FORMAT = 'ALCG-v0.20-noisy-cost-aware-active-design'
V019_REPORT_SHA256 = '2d9cddce9204b672465a1d8327ab9348ab84d12f954e7bf25f9c7077bd9ce7a6'
V019_SPEC_SHA256 = '96acd1e374283c8923f003db641c77e607aa5295278b324ea5295083e7439853'
CONTEXT_RATES = (Fraction(1, 16), Fraction(1, 8), Fraction(1, 4), Fraction(1, 8))
CONTEXT_COSTS = (4, 1, 1, 3)
MAX_EVIDENCE = 32


class NoisyDesignError(ValueError):
    """Invalid noisy experiment or changed frozen input."""


def _fraction(value: Fraction) -> dict:
    return {'numerator': value.numerator, 'denominator': value.denominator,
            'decimal': round(float(value), 9)}


def experiment_spec() -> dict[str, Any]:
    return {
        'format': FORMAT,
        'source': 'exact 16-hypothesis truth signatures for each of seven v0.19 synthetic families',
        'v019_report_sha256': V019_REPORT_SHA256,
        'v019_design_spec_sha256': V019_SPEC_SHA256,
        'hypotheses': 'masks 0..15, initially equal probability, exactly as in v0.19',
        'outcomes': 'Boolean SCM result independently flipped with specified probability on each attempt',
        'conditional_independence': 'noise events independent conditional on the true mask and chosen action',
        'experimental_rates_and_costs': [
            {'context_index': i, 'flip_numerator': e.numerator, 'flip_denominator': e.denominator,
             'cost_units': cost} for i, (e, cost) in enumerate(zip(CONTEXT_RATES, CONTEXT_COSTS))],
        'actions': 'eight v0.19 actions, four off-natural informative and four natural noninformative',
        'repetitions': 'allowed, with fresh conditionally independent noise per attempted observation',
        'evidence': 'observed Boolean outcomes with action ID; no deterministic candidate elimination',
        'greedy_objective': 'maximize Shannon information gain divided by integer action cost',
        'exact_budget_objective': 'maximize expected posterior MAP full-mask accuracy under finite cost budget',
        'optimal_budget_scope': 'exact enumeration, budgets 0..4, with repeats and adaptive branches allowed',
        'tie_break': 'prefer lower spent cost, then lower action id; zero-gain action is never chosen',
        'guarantee': 'strictly positive flip rates imply no finite noisy history guarantees exact identification',
        'limitations': 'no real sensor data, no calibrated noise, no intervention price survey, no general optimal policy',
        'no_real_world_causal_inference': True,
        'no_independent_ai_comprehension_claim': True,
        'published_registry_unmodified': True,
    }


def serialized_spec() -> str:
    return json.dumps(experiment_spec(), ensure_ascii=False, indent=2) + '\n'


def _frozen_rows() -> dict[str, dict]:
    for path, expected in ((old.REPORT_PATH, V019_REPORT_SHA256),
                           (old.SPEC_PATH, V019_SPEC_SHA256)):
        try:
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise NoisyDesignError(f'missing pinned v0.19 input: {path.name}') from exc
        if digest != expected:
            raise NoisyDesignError(f'pinned v0.19 input changed: {path.name}')
    if SPEC_PATH.read_text(encoding='utf-8') != serialized_spec():
        raise NoisyDesignError('v0.20 scenario specification is not canonical')
    reference = old._read_pinned_report()
    rows = {r['family_id']: r for r in reference['families']}
    if len(rows) != 7:
        raise NoisyDesignError('v0.19 must have seven distinct families')
    for row in rows.values():
        if row['completion_count'] != 16:
            raise NoisyDesignError('expected 16 hypothesis masks per family')
    return rows


def _int(value: Any, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise NoisyDesignError(f'{name} must be an integer in {lower}..{upper}')
    return value


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise NoisyDesignError(f'{name} must be Boolean')
    return value


def action_rate(action_id: int) -> Fraction:
    action = old.action_data(_int(action_id, 'action_id', 0, 7))
    return CONTEXT_RATES[action['context_index']]


def action_cost(action_id: int) -> int:
    action = old.action_data(_int(action_id, 'action_id', 0, 7))
    return CONTEXT_COSTS[action['context_index']]


def action_profile(action_id: int) -> dict:
    action = old.action_data(_int(action_id, 'action_id', 0, 7))
    return {**{k: v for k, v in action.items() if k != 'unit_cost'},
            'cost_units': action_cost(action_id),
            'flip_probability': _fraction(action_rate(action_id))}


def _normalise(weights: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    if len(weights) != 16 or any(type(w) is not Fraction or w < 0 for w in weights):
        raise NoisyDesignError('posterior must have sixteen nonnegative rational weights')
    total = sum(weights, Fraction(0))
    if total <= 0:
        raise NoisyDesignError('zero-total posterior is invalid')
    return tuple(w / total for w in weights)


def initial_prior() -> tuple[Fraction, ...]:
    return (Fraction(1, 16),) * 16


def likelihood(row: dict, mask: int, action_id: int, observed: bool) -> Fraction:
    _int(mask, 'mask', 0, 15)
    _boolean(observed, 'observed_Y')
    p = action_rate(action_id)
    return (1 - p) if old._response(row, mask, action_id) == observed else p


def evidence_update(row: dict, weights: tuple[Fraction, ...],
                    action_id: int, observed: bool) -> tuple[Fraction, ...]:
    _normalise(weights)
    next_weights = tuple(w * likelihood(row, m, action_id, observed)
                         for m, w in enumerate(weights))
    return _normalise(next_weights)


def posterior(row: dict, evidence: list[dict] | None = None) -> tuple[Fraction, ...]:
    if evidence is None:
        evidence = []
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE:
        raise NoisyDesignError('evidence must be a list of up to 32 observations')
    weights = initial_prior()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {'action_id', 'observed_Y'}:
            raise NoisyDesignError('evidence items must have action_id and observed_Y only')
        weights = evidence_update(row, weights,
                                  _int(item['action_id'], 'action_id', 0, 7),
                                  _boolean(item['observed_Y'], 'observed_Y'))
    return weights


def predictive(row: dict, weights: tuple[Fraction, ...], action_id: int,
               observed: bool) -> Fraction:
    normalized = _normalise(weights)
    return sum((w * likelihood(row, m, action_id, observed) for m, w in enumerate(normalized)),
               Fraction(0))


def binary_entropy(p: Fraction | float) -> float:
    x = float(p)
    if not 0 <= x <= 1:
        raise NoisyDesignError('binary entropy input outside 0..1')
    if x == 0 or x == 1:
        return 0.0
    return -x * log2(x) - (1 - x) * log2(1 - x)


def entropy(weights: tuple[Fraction, ...]) -> float:
    weights = _normalise(weights)
    return -sum(float(p) * log2(float(p)) for p in weights if p)


def information_gain(row: dict, weights: tuple[Fraction, ...], action_id: int) -> float:
    """Exact binary channel probabilities; Shannon information in float bits."""
    q = predictive(row, weights, action_id, True)
    return max(0.0, binary_entropy(q) - binary_entropy(action_rate(action_id)))


def greedy_choice(row: dict, weights: tuple[Fraction, ...], budget: int,
                  *, per_cost: bool = True) -> dict | None:
    _int(budget, 'budget', 0, 100)
    _normalise(weights)
    options = []
    for action_id in old.informative_actions():
        cost = action_cost(action_id)
        if cost > budget:
            continue
        gain = information_gain(row, weights, action_id)
        if gain <= 1e-12:
            continue
        score = gain / cost if per_cost else gain
        options.append((-score, -gain, cost, action_id, gain))
    if not options:
        return None
    _, _, cost, selected, gain = min(options)
    return {**action_profile(selected),
            'expected_information_gain_bits': round(gain, 9),
            'information_bits_per_cost': round(gain / cost, 9),
            'selection_method': 'greedy_gain_per_cost' if per_cost else 'greedy_gain'}


def map_accuracy(weights: tuple[Fraction, ...]) -> Fraction:
    return max(_normalise(weights))


def exact_budget_plan(row: dict, weights: tuple[Fraction, ...], budget: int) -> dict:
    """Global optimum for expected final MAP success in the bounded toy budget.

    An action may be repeated.  The cost budget decreases strictly, so dynamic
    programming over all binary observation branches terminates.  Outcomes are
    integrated under the *current posterior*, not sampled or leaked from truth.
    """
    budget = _int(budget, 'budget', 0, 4)
    weights = _normalise(weights)
    actions = tuple(a for a in old.informative_actions() if action_cost(a) <= budget)

    @lru_cache(maxsize=None)
    def solve(state: tuple[Fraction, ...], remaining: int) -> tuple[Fraction, int | None, int]:
        best = map_accuracy(state)
        decision = None
        spent = 0
        for action_id in actions:
            cost = action_cost(action_id)
            if cost > remaining:
                continue
            outcome_score = Fraction(0)
            for observed in (False, True):
                probability = predictive(row, state, action_id, observed)
                child = evidence_update(row, state, action_id, observed)
                child_score, _, _ = solve(child, remaining - cost)
                outcome_score += probability * child_score
            if outcome_score > best or (outcome_score == best and decision is not None and
                                        (cost, action_id) < (spent, decision)):
                best, decision, spent = outcome_score, action_id, cost
        return best, decision, spent

    optimal, selected, cost = solve(weights, budget)
    return {'budget_cost_units': budget,
            'expected_final_MAP_accuracy': _fraction(optimal),
            'current_MAP_accuracy': _fraction(map_accuracy(weights)),
            'optimal_first_action': action_profile(selected) if selected is not None else None,
            'initial_action_cost': cost if selected is not None else 0,
            'method': 'exact_bounded_dynamic_program_for_MAP_accuracy',
            'objective_note': 'full 16-mask MAP classification, not worst-case guaranteed correctness'}


def _row_report(family_id: str, row: dict) -> dict:
    prior = initial_prior()
    actions = [{**action_profile(action),
                'information_gain_bits_uniform': round(information_gain(row, prior, action), 9),
                'information_bits_per_cost_uniform': round(
                    information_gain(row, prior, action) / action_cost(action), 9)}
               for action in old.informative_actions()]
    greedy = greedy_choice(row, prior, 4)
    one_evidence = [{'action_id': greedy['action_id'],
                     'observed_Y': old._response(row, 0, greedy['action_id'])}]
    updated = posterior(row, one_evidence)
    opposite = {'action_id': greedy['action_id'], 'observed_Y': not one_evidence[0]['observed_Y']}
    balanced = posterior(row, one_evidence + [opposite])
    if balanced != prior:
        raise NoisyDesignError('opposed observations on same independent symmetric sensor should cancel')
    return {
        'family_id': family_id,
        'uniform_prior_entropy_bits': 4,
        'informative_action_cost_noise_tradeoffs': actions,
        'uniform_prior_greedy_per_cost': greedy,
        'greedy_after_one_observation': greedy_choice(row, updated, 1),
        'posterior_after_one_greedy_observation': {
            'evidence': one_evidence,
            'MAP_probability': _fraction(map_accuracy(updated)),
            'entropy_bits': round(entropy(updated), 9),
            'all_16_masks_remain_possible': all(w > 0 for w in updated),
        },
        'two_opposite_readings_cancel_exactly': balanced == prior,
        'exact_MAP_budget_comparisons': [exact_budget_plan(row, prior, b) for b in range(5)],
    }


def make_report() -> dict:
    rows = _frozen_rows()
    results = [_row_report(fid, rows[fid]) for fid in sorted(rows)]
    baseline = results[0]
    if not all(r['exact_MAP_budget_comparisons'] == baseline['exact_MAP_budget_comparisons'] for r in results):
        raise NoisyDesignError('unexpected family-specific design divergence')
    return {
        'format': FORMAT,
        'provenance': 'exact assistant-authored finite channel analysis, no real sampled outcomes',
        'counts': {'families': len(rows), 'hypotheses_per_family': 16,
                   'distinct_contexts': 4, 'interventions_per_family': 8,
                   'informative_off_natural_actions': 4},
        'models': results,
        'limitations': [
            'Noise probabilities and intervention costs are chosen experimental inputs, not estimated.',
            'All 16 masks remain possible after finite noisy evidence: identification is probabilistic.',
            'Greedy information gain per cost and exact finite-budget MAP have different objectives.',
            'The prior is uniform and errors are conditionally independent; correlated/model-specific error is not evaluated.',
            'No empirical intervention, external AI reader, natural language fidelity or general causality claim.',
            'No new language operator, mesoscopic character or published registry change.',
        ],
    }


def serialized_report() -> str:
    return json.dumps(make_report(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def _parse_event(text: str) -> dict:
    if '=' not in text:
        raise NoisyDesignError('expected action_id=0 or action_id=1')
    left, right = text.split('=', 1)
    try:
        action_id = int(left)
    except ValueError as exc:
        raise NoisyDesignError('invalid action id') from exc
    if right not in ('0', '1'):
        raise NoisyDesignError('observed result must be 0 or 1')
    _int(action_id, 'action_id', 0, 7)
    return {'action_id': action_id, 'observed_Y': right == '1'}


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.20 synthetic noisy, cost-sensitive active experiments')
    commands = cli.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='validate pinned inputs and deterministic saved report')
    commands.add_parser('report', help='summarise baseline metrics, not AI reader scores')
    cmd = commands.add_parser('plan', help='posterior, greedy action and exact bounded budget decision')
    cmd.add_argument('--family', default='F17_DIRECT')
    cmd.add_argument('--budget', type=int, default=2)
    cmd.add_argument('--observe', action='append', default=[], metavar='ACTION=0|1',
                     help='may be repeated; e.g. --observe 3=1 --observe 3=0')
    cmd = commands.add_parser('replay', help='show true synthetic SCM result and optional noisy reading')
    cmd.add_argument('--family', default='F17_DIRECT')
    cmd.add_argument('--mask', type=int, required=True)
    cmd.add_argument('--action', type=int, required=True)
    cmd.add_argument('--flip', action='store_true', help='simulate a flipped observation explicitly')
    args = cli.parse_args(argv)
    try:
        rows = _frozen_rows()
        if args.command == 'check':
            if REPORT_PATH.read_text(encoding='utf-8') != serialized_report():
                raise NoisyDesignError('v0.20 saved report differs from deterministic recomputation')
            print(f'OK: {len(rows)} families, 16 hypotheses each, synthetic noisy cost-aware v0.20 report verified')
        elif args.command == 'report':
            report = make_report()
            example = report['models'][0]
            print(json.dumps({'counts': report['counts'], 'sample_family': example['family_id'],
                              'greedy': example['uniform_prior_greedy_per_cost'],
                              'exact_MAP_budgets': example['exact_MAP_budget_comparisons']},
                             indent=2, ensure_ascii=False))
        elif args.command == 'plan':
            if args.family not in rows:
                raise NoisyDesignError('unknown family')
            events = [_parse_event(e) for e in args.observe]
            weights = posterior(rows[args.family], events)
            result = {'family_id': args.family, 'observations': events,
                      'posterior_masks': [_fraction(w) for w in weights],
                      'posterior_entropy_bits': round(entropy(weights), 9),
                      'MAP_probability': _fraction(map_accuracy(weights)),
                      'greedy_next': greedy_choice(rows[args.family], weights, args.budget),
                      'exact_MAP_budget': exact_budget_plan(rows[args.family], weights, args.budget)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if args.family not in rows:
                raise NoisyDesignError('unknown family')
            _int(args.mask, 'mask', 0, 15)
            _int(args.action, 'action_id', 0, 7)
            actual = old._response(rows[args.family], args.mask, args.action)
            observed = actual ^ args.flip
            weights = posterior(rows[args.family], [{'action_id': args.action, 'observed_Y': observed}])
            print(json.dumps({'family_id': args.family, 'true_mask': args.mask,
                              'action': action_profile(args.action), 'true_synthetic_outcome': actual,
                              'explicit_flip': args.flip, 'observed_Y': observed,
                              'posterior_probability_for_true_mask': _fraction(weights[args.mask]),
                              'MAP_probability': _fraction(map_accuracy(weights))},
                             ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, old.DesignError, NoisyDesignError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
