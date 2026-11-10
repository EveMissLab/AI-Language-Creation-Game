"""ALCG v0.21: synthetic asymmetric and session-correlated sensing.

Exact Bayesian inference over 16 frozen mechanism masks and one persistent
binary session-fault variable.  Rates, costs, and SCMs are intentionally
assistant-authored; there are NO empirical experiments or AI reader trials.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import active_design as design
import noisy_design as baseline

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / 'data' / 'correlated-design-space-v0.21.json'
REPORT_PATH = ROOT / 'reports' / 'correlated-design-v0.21.json'
FORMAT = 'ALCG-v0.21-asymmetric-session-correlated-stop-decisions'
PINNED_V020_SPEC_SHA256 = 'c93375d04d1c4b45110d00ca2f961e23c58711575654eb0dc41668519b27837e'
PINNED_V020_REPORT_SHA256 = '5375a1f49e81eae095cad6041f8829010a4583eb4ec7573420922aa93bf73e90'
FALSE_POSITIVE = (Fraction(1, 32), Fraction(1, 16), Fraction(3, 16), Fraction(1, 8))
FALSE_NEGATIVE = (Fraction(1, 16), Fraction(3, 16), Fraction(1, 8), Fraction(1, 4))
SESSION_FAULT_PRIOR = Fraction(1, 8)
COSTS = baseline.CONTEXT_COSTS
MAX_EVENTS = 32
MAX_PLANNING_BUDGET = 4


class ChannelError(ValueError):
    """Invalid finite channel, evidence, or changed pinned input."""


def _rat(x: Fraction) -> dict:
    return {'numerator': x.numerator, 'denominator': x.denominator,
            'decimal': round(float(x), 9)}


def experiment_spec() -> dict[str, Any]:
    return {
        'format': FORMAT,
        'source': 'frozen v0.19 sixteen-mask SCMs and frozen v0.20 independent-noise comparison',
        'pinned_v020_spec_sha256': PINNED_V020_SPEC_SHA256,
        'pinned_v020_report_sha256': PINNED_V020_REPORT_SHA256,
        'hypotheses': 'sixteen mechanisms m=0..15 and persistent session fault Z=0/1',
        'joint_prior': 'P(M=m)=1/16, P(Z=1)=1/8 independent at session start',
        'per_context_false_positive': [_rat(x) for x in FALSE_POSITIVE],
        'per_context_false_negative': [_rat(x) for x in FALSE_NEGATIVE],
        'costs': list(COSTS),
        'channel': ('A fresh base reading B has P(B=1|trueY=0)=FPR, '
                    'P(B=0|trueY=1)=FNR; actual observed Y=B XOR persistent Z.'),
        'correlation': 'Z is drawn once for the full session; base sensor errors are independent given M,Z,actions',
        'independent_control': 'Z is instead redrawn independently per observation (for analytic contrast only)',
        'allowed_actions': 'all eight v0.19 interventions, including natural-output calibration probes',
        'loss': 'L*(1-max_m P(M=m|history)), for a chosen unit-cost misclassification penalty L',
        'stop_policy': 'exact finite-horizon dynamic program: minimum expected future measurement cost plus stop loss',
        'stop_tie_break': 'stop on equality; otherwise lowest action id among exact ties',
        'planning_budget_max': MAX_PLANNING_BUDGET,
        'limitations': [
            'Synthetic Boolean SCMs and arbitrary assumed noise and costs; not measured sensors.',
            'Session fault is only a toy shared latent flip, not a general correlated noise model.',
            'The maximum four-unit plan is optimal only inside the stated bounded action/model class.',
            'Positive noise allows no finite-history certainty; loss must be supplied by the decision maker.',
            'No experimental causal inference, external AI reader results or published language change.',
        ],
        'no_empirical_causality': True,
        'no_independent_ai_comprehension': True,
        'published_language_dictionary_unmodified': True,
    }


def serialized_spec() -> str:
    return json.dumps(experiment_spec(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def pinned_rows() -> dict[str, dict]:
    for path, expected in ((baseline.SPEC_PATH, PINNED_V020_SPEC_SHA256),
                           (baseline.REPORT_PATH, PINNED_V020_REPORT_SHA256)):
        try:
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError as ex:
            raise ChannelError(f'missing pinned v0.20 artifact: {path.name}') from ex
        if digest != expected:
            raise ChannelError(f'v0.20 artifact modified: {path.name}')
    if SPEC_PATH.read_text(encoding='utf-8') != serialized_spec():
        raise ChannelError('v0.21 scenario spec is not canonical')
    return baseline._frozen_rows()


def _check_bool(v: Any, label: str) -> bool:
    if type(v) is not bool:
        raise ChannelError(f'{label} must be Boolean')
    return v


def _check_int(v: Any, label: str, low: int, high: int) -> int:
    if type(v) is not int or not low <= v <= high:
        raise ChannelError(f'{label} must be integer in {low}..{high}')
    return v


def _fault_prior(q: Fraction) -> Fraction:
    if type(q) is not Fraction or not Fraction(0) <= q <= Fraction(1, 2):
        raise ChannelError('session fault prior must be rational in [0, 1/2]')
    return q


def initial_joint(q: Fraction = SESSION_FAULT_PRIOR) -> tuple[Fraction, ...]:
    q = _fault_prior(q)
    return tuple([Fraction(1, 16) * (1-q)] * 16 + [Fraction(1, 16) * q] * 16)


def normalized_joint(weights: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    if (not isinstance(weights, tuple) or len(weights) != 32
        or any(type(w) is not Fraction or w < 0 for w in weights)):
        raise ChannelError('joint posterior requires 32 nonnegative rational cells')
    total = sum(weights, Fraction(0))
    if not total:
        raise ChannelError('zero probability joint posterior')
    return tuple(w / total for w in weights)


def likelihood(row: dict, mask: int, fault: bool, action: int, observed: bool) -> Fraction:
    _check_int(mask, 'mask', 0, 15)
    _check_bool(fault, 'fault')
    _check_bool(observed, 'observed_Y')
    ctx = design.action_data(_check_int(action, 'action_id', 0, 7))['context_index']
    truth = design._response(row, mask, action)
    p_base_true = 1 - FALSE_NEGATIVE[ctx] if truth else FALSE_POSITIVE[ctx]
    base_target_true = observed ^ fault
    return p_base_true if base_target_true else (1 - p_base_true)


def update(row: dict, state: tuple[Fraction, ...], action: int,
           observed: bool) -> tuple[Fraction, ...]:
    state = normalized_joint(state)
    return normalized_joint(tuple(w * likelihood(row, idx % 16, bool(idx//16), action, observed)
                                  for idx, w in enumerate(state)))


def posterior(row: dict, observations: list[dict] | None = None,
              q: Fraction = SESSION_FAULT_PRIOR) -> tuple[Fraction, ...]:
    if observations is None:
        observations = []
    if not isinstance(observations, list) or len(observations) > MAX_EVENTS:
        raise ChannelError('evidence must be a list of at most 32 observations')
    state = initial_joint(q)
    for event in observations:
        if not isinstance(event, dict) or set(event) != {'action_id', 'observed_Y'}:
            raise ChannelError('evidence must contain action_id and observed_Y only')
        state = update(row, state,
                       _check_int(event['action_id'], 'action_id', 0, 7),
                       _check_bool(event['observed_Y'], 'observed_Y'))
    return state


def mask_posterior(state: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    state = normalized_joint(state)
    return tuple(state[i] + state[16+i] for i in range(16))


def fault_posterior(state: tuple[Fraction, ...]) -> Fraction:
    state = normalized_joint(state)
    return sum(state[16:], Fraction(0))


def predictive(row: dict, state: tuple[Fraction, ...], action: int,
               observed: bool) -> Fraction:
    state = normalized_joint(state)
    return sum((w * likelihood(row, idx % 16, bool(idx//16), action, observed)
                for idx, w in enumerate(state)), Fraction(0))


def redraw_fault_posterior(row: dict, observations: list[dict],
                           q: Fraction = SESSION_FAULT_PRIOR) -> tuple[Fraction, ...]:
    """Control: same marginal error rates, but fault is redrawn each trial."""
    q = _fault_prior(q)
    if not isinstance(observations, list) or len(observations) > MAX_EVENTS:
        raise ChannelError('evidence must be list of <=32 observations')
    weights = [Fraction(1,16)] * 16
    for event in observations:
        if not isinstance(event, dict) or set(event) != {'action_id', 'observed_Y'}:
            raise ChannelError('invalid evidence item')
        act = _check_int(event['action_id'], 'action_id', 0, 7)
        y = _check_bool(event['observed_Y'], 'observed_Y')
        for m in range(16):
            a = likelihood(row, m, False, act, y)
            b = likelihood(row, m, True, act, y)
            weights[m] *= (1-q)*a + q*b
    total = sum(weights, Fraction(0))
    return tuple(x/total for x in weights)


def action_cost(action: int) -> int:
    ctx = design.action_data(_check_int(action, 'action_id', 0, 7))['context_index']
    return COSTS[ctx]


def stop_loss(state: tuple[Fraction, ...], penalty: int) -> Fraction:
    _check_int(penalty, 'penalty', 0, 10000)
    return penalty * (1 - max(mask_posterior(state)))


def plan(row: dict, state: tuple[Fraction, ...], budget: int,
         penalty: int, allowed_actions: tuple[int, ...] = tuple(range(8))) -> dict:
    """Exact budget-bounded Bayes risk DP with STOP option at every node.

    Costs are paid per chosen action, terminal loss is MAP classification loss;
    all sensor responses and persistent session faults are marginalized exactly.
    Best value includes *future* costs only, so earlier costs are sunk.
    """
    _check_int(budget, 'budget', 0, MAX_PLANNING_BUDGET)
    _check_int(penalty, 'penalty', 0, 10000)
    state = normalized_joint(state)
    if not isinstance(allowed_actions, tuple):
        raise ChannelError('allowed_actions must be tuple')
    for act in allowed_actions:
        _check_int(act, 'allowed action', 0, 7)
    choices = tuple(sorted(set(allowed_actions)))

    @lru_cache(maxsize=None)
    def solve(s: tuple[Fraction, ...], b: int) -> tuple[Fraction, int | None]:
        best_value = stop_loss(s, penalty)
        selected: int | None = None
        for act in choices:
            cost = action_cost(act)
            if cost > b:
                continue
            expectation = Fraction(cost)
            for y in (False, True):
                py = predictive(row, s, act, y)
                if py:
                    child = update(row, s, act, y)
                    child_value, _ = solve(child, b - cost)
                    expectation += py * child_value
            if expectation < best_value or (expectation == best_value and selected is not None and act < selected):
                best_value, selected = expectation, act
        return best_value, selected

    best_risk, best_action = solve(state, budget)
    return {
        'budget_cost_units': budget,
        'misclassification_penalty_units': penalty,
        'stop_now_expected_loss': _rat(stop_loss(state, penalty)),
        'optimal_expected_future_total_loss': _rat(best_risk),
        'optimal_first_action': best_action,
        'decision': 'STOP' if best_action is None else 'CONTINUE',
        'method': 'exact_joint_bayes_risk_dp_with_stop_and_session_latent',
        'budget_only_bounded': True,
    }


def _preview(row: dict) -> dict:
    prior = initial_joint()
    action = 3
    natural = 2
    natural_truth = design._response(row, 0, natural)
    synthetic_trace = [{'action_id': action, 'observed_Y': True},
                       {'action_id': natural, 'observed_Y': natural_truth},
                       {'action_id': action, 'observed_Y': True}]
    repeated = [{'action_id': action, 'observed_Y': True}] * 3
    correlated_m = mask_posterior(posterior(row, repeated))
    redraw_m = redraw_fault_posterior(row, repeated)
    return {
        'example_family_id': row['family_id'],
        'uniform_mask_prior': '16 mechanisms at 1/16, session fault prior 1/8',
        'sensor_asymmetry_at_action_3': {
            'P_false_positive': _rat(FALSE_POSITIVE[1]),
            'P_false_negative': _rat(FALSE_NEGATIVE[1]),
        },
        'synthetic_trace': synthetic_trace,
        'trace_posterior_fault': _rat(fault_posterior(posterior(row, synthetic_trace))),
        'trace_posterior_max_mask': _rat(max(mask_posterior(posterior(row, synthetic_trace)))),
        'repeat_count': len(repeated),
        'max_mask_probability_persistent_fault': _rat(max(correlated_m)),
        'max_mask_probability_redrawn_fault': _rat(max(redraw_m)),
        'persistent_and_redrawn_mask_posteriors_differ': correlated_m != redraw_m,
        'initial_risk_policies_loss32': [plan(row, prior, b, 32) for b in range(5)],
        'initial_risk_policies_loss64': [plan(row, prior, b, 64) for b in range(5)],
        'after_first_reading_loss64': [plan(row, posterior(row, [synthetic_trace[0]]), b, 64)
                                       for b in range(3)],
    }


def make_report() -> dict:
    rows = pinned_rows()
    r = _preview(rows['F17_DIRECT'])
    return {
        'format': FORMAT,
        'provenance': 'exact enumerated synthetic Bayesian inference; no sampled or real observations',
        'counts': {'families_frozen': len(rows), 'hypotheses_masks': 16,
                   'joint_fault_mask_states': 32, 'context_sensor_profiles': 4},
        'preview': r,
        'warnings': experiment_spec()['limitations'],
        'legacy_v020_unchanged': True,
    }


def serialized_report() -> str:
    return json.dumps(make_report(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def _args_observations(texts: list[str]) -> list[dict]:
    try:
        return [baseline._parse_event(text) for text in texts]
    except baseline.NoisyDesignError as ex:
        raise ChannelError(str(ex)) from ex


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.21 bounded asymmetric correlated sensor laboratory')
    commands = cli.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='recompute and validate saved exact synthetic report')
    commands.add_parser('summary', help='print small synthetic risk comparison')
    p = commands.add_parser('plan', help='exact Bayesian posterior and stop/continue plan')
    p.add_argument('--family', default='F17_DIRECT')
    p.add_argument('--budget', type=int, default=2)
    p.add_argument('--loss', type=int, default=64)
    p.add_argument('--observe', action='append', default=[], metavar='ACTION=0|1')
    p = commands.add_parser('replay', help='show exact observation distribution given one hypothesis')
    p.add_argument('--family', default='F17_DIRECT')
    p.add_argument('--mask', type=int, required=True)
    p.add_argument('--fault', type=int, choices=[0,1], required=True)
    p.add_argument('--action', type=int, required=True)
    args = cli.parse_args(argv)
    try:
        rows = pinned_rows()
        if args.command == 'check':
            if REPORT_PATH.read_text(encoding='utf-8') != serialized_report():
                raise ChannelError('v0.21 report differs from recomputed canonical result')
            print(f'OK v0.21: {len(rows)} families, 32 joint states, cost-aware correlated-channel receipt verified')
        elif args.command == 'summary':
            report = make_report()
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == 'plan':
            if args.family not in rows:
                raise ChannelError('unknown family')
            events = _args_observations(args.observe)
            state = posterior(rows[args.family], events)
            print(json.dumps({
                'family_id': args.family, 'evidence': events,
                'mask_MAP_probability': _rat(max(mask_posterior(state))),
                'session_fault_posterior': _rat(fault_posterior(state)),
                'plan': plan(rows[args.family], state, args.budget, args.loss),
            }, ensure_ascii=False, indent=2))
        elif args.command == 'replay':
            if args.family not in rows:
                raise ChannelError('unknown family')
            _check_int(args.mask, 'mask', 0, 15)
            _check_int(args.action, 'action_id', 0, 7)
            result = {
                'family_id': args.family, 'mask': args.mask,
                'session_fault': bool(args.fault), 'action_id': args.action,
                'deterministic_SCM_result': design._response(rows[args.family], args.mask, args.action),
                'P_observed_false': _rat(likelihood(rows[args.family], args.mask, bool(args.fault), args.action, False)),
                'P_observed_true': _rat(likelihood(rows[args.family], args.mask, bool(args.fault), args.action, True)),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ChannelError, baseline.NoisyDesignError, design.DesignError, OSError, json.JSONDecodeError) as ex:
        print('ERROR:', ex, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
