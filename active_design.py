"""ALCG v0.19: exact bounded active intervention design over v0.18 mechanisms.

Every 'outcome' is simulated inside assistant-authored Boolean SCMs. The planner
is not an empirical experimenter, causal discovery system or AI comprehension test.
No external packages, API calls, or published symbol/dictionary mutations.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
from itertools import combinations
import json
from math import log2
from pathlib import Path
import sys
from typing import Any, Iterable

import causal_robustness as v17
import mechanism_search as v18
from causal_lab import CausalError, parse_cause

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / 'data' / 'active-design-space-v0.19.json'
REPORT_PATH = ROOT / 'reports' / 'active-design-v0.19.json'
V018_REPORT_SHA256 = '52588b33e3edda771728b6963964c6ebdc6b2d6d0004d0c8816407495b30557e'
V018_SPEC_SHA256 = '99c7ba43e36fad5dfc10f893ff70808c4278b148214bba8c9426cc8674ab465a'
FORMAT = 'ALCG-v0.19-bounded-active-intervention-design'
MASKS = tuple(range(16))
ACTION_COUNT = 8


class DesignError(ValueError):
    """Invalid experiment, stale frozen source, or unsupported hypothesis class."""


def design_spec() -> dict[str, Any]:
    return {
        'format': FORMAT,
        'provenance': 'deterministic synthetic experiment over frozen assistant-authored v0.18 Boolean SCMs',
        'v018_report_sha256': V018_REPORT_SHA256,
        'v018_search_space_sha256': V018_SPEC_SHA256,
        'hypotheses_per_family': 16,
        'families': 7,
        'hypothesis_label': 'H four-bit off-support completion mask, 0..15',
        'background_order': ['U=0,G=0', 'U=0,G=1', 'U=1,G=0', 'U=1,G=1'],
        'observation_equation': 'SIGNAL=U',
        'actions': 'For each context, do(SIGNAL=0) or do(SIGNAL=1), outcome is Boolean Y',
        'cost': 'Every intervention counts as one unit; natural-value interventions are allowed but uninformative',
        'prior': 'uniform over currently compatible masks; conditional reweighting by elimination',
        'objective_exact': 'distinguish all remaining full intervention signatures',
        'objective_anchor': 'decide whether intervention signature equals the original first model',
        'planner': 'exact finite dynamic program, minimize worst-case interventions first, expected interventions second',
        'ties': 'choose lexicographically smallest action ID (context_index*2 + do_signal)',
        'allowed_evidence': 'action id plus observed Boolean Y; reject inconsistent outcomes or impossible observation',
        'claims_scope': ('Exact identification only in the 16-hypothesis class, with specified backgrounds, '
                         'cost and perfect noiseless interventions; no general-world conclusion.'),
        'no_empirical_data': True,
        'no_ai_comprehension_evaluation': True,
        'no_registry_updates': True,
    }


def serialized_spec() -> str:
    return json.dumps(design_spec(), ensure_ascii=False, indent=2) + '\n'


def _read_pinned_report() -> dict:
    v18._guard_inputs()
    for path, expected in ((v18.REPORT_PATH, V018_REPORT_SHA256),
                           (v18.SPEC_PATH, V018_SPEC_SHA256)):
        try:
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise DesignError(f'missing frozen v0.18 input {path.name}') from exc
        if digest != expected:
            raise DesignError(f'frozen v0.18 input modified: {path.name}')
    try:
        spec = SPEC_PATH.read_text(encoding='utf-8')
        report = json.loads(v18.REPORT_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignError(f'cannot read active design inputs: {exc}') from exc
    if spec != serialized_spec():
        raise DesignError('v0.19 search space specification changed')
    if report.get('format') != v18.FORMAT or report.get('summary', {}).get('candidate_models') != 112:
        raise DesignError('incompatible v0.18 reference report')
    return report


def _require_int(value: Any, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise DesignError(f'{label} must be integer in {lower}..{upper}')
    return value


def _bool01(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise DesignError(f'{label} must be Boolean')
    return value


def _family_row(data: dict, family_id: str) -> dict:
    if not isinstance(family_id, str):
        raise DesignError('family must be a string')
    matches = [r for r in data['families'] if r['family_id'] == family_id]
    if len(matches) != 1:
        raise DesignError('unknown or ambiguous family ID')
    row = matches[0]
    if row['completion_count'] != 16 or [c['mask'] for c in row['candidates']] != list(MASKS):
        raise DesignError('expected exactly 16 ordered completion candidates')
    return row


def action_data(action_id: int) -> dict:
    action_id = _require_int(action_id, 0, 7, 'action_id')
    index, forced = divmod(action_id, 2)
    u, g = v18.CONTEXTS[index]
    return {
        'action_id': action_id,
        'context_index': index,
        'background': {'U': u, 'G': g},
        'do_SIGNAL': bool(forced),
        'same_as_natural_SIGNAL': bool(forced) == u,
        'unit_cost': 1,
    }


def informative_actions() -> tuple[int, ...]:
    return tuple(i for i in range(ACTION_COUNT) if not action_data(i)['same_as_natural_SIGNAL'])


def _response(row: dict, mask: int, action_id: int) -> bool:
    _require_int(mask, 0, 15, 'mask')
    action = action_data(action_id)
    pair = row['candidates'][mask]['new_intervention_signature'][action['context_index']]
    if len(pair) != 2 or any(type(x) is not bool for x in pair):
        raise DesignError('invalid recorded Boolean intervention signature')
    return pair[int(action['do_SIGNAL'])]


def _anchor_mask(row: dict, family: v17.Family) -> int:
    source, effect = parse_cause(family.expression)
    first = family.models[0]
    indicator = first.outcomes[effect]
    result = 0
    for i, (u, g) in enumerate(v18.CONTEXTS):
        context = {'U': u, 'G': g}
        natural = first.run(context)[indicator]
        if natural != row['anchor_observations_U_G'][i]:
            raise DesignError('frozen anchor no longer matches recorded observations')
        flipped = first.run(context, intervene={source: not u})[indicator]
        if flipped != natural:
            result |= 1 << i
    if all(_response(row, result, a) == family.models[0].run(
            {'U': v18.CONTEXTS[action_data(a)['context_index']][0],
             'G': v18.CONTEXTS[action_data(a)['context_index']][1]},
            intervene={source: action_data(a)['do_SIGNAL']})[indicator] for a in range(8)):
        return result
    raise DesignError('anchor mechanism not represented by v0.18 completion class')


def _validate_maskset(masks: Iterable[int]) -> tuple[int, ...]:
    values = tuple(masks)
    if not values or len(set(values)) != len(values):
        raise DesignError('mask set must be nonempty and duplicate-free')
    for mask in values:
        _require_int(mask, 0, 15, 'mask')
    return tuple(sorted(values))


def _partition(row: dict, masks: Iterable[int], action_id: int) -> dict[bool, tuple[int, ...]]:
    groups: dict[bool, list[int]] = {False: [], True: []}
    for mask in masks:
        groups[_response(row, mask, action_id)].append(mask)
    return {key: tuple(sorted(value)) for key, value in groups.items() if value}


@dataclass(frozen=True)
class Plan:
    worst: int | None
    expected: Fraction | None
    action: int | None


def _solved(masks: tuple[int, ...], objective: str, anchor_mask: int) -> bool:
    if objective == 'identify':
        return len(masks) == 1
    if objective == 'anchor':
        return anchor_mask not in masks or len(masks) == 1
    raise DesignError('objective must be identify or anchor')


def optimize(row: dict, masks: Iterable[int], objective: str,
             anchor_mask: int, allowed_actions: Iterable[int] = range(8)) -> Plan:
    """Exact minimax decision tree with uniform conditional prior.

    Only binary Boolean outcome actions are considered. A child's candidate
    count must strictly decrease, so recursion is acyclic. Noisy experiments,
    unsupported interventions and model misspecification are out of scope.
    """
    requested = tuple(allowed_actions)
    for action in requested:
        _require_int(action, 0, 7, 'action_id')
    available = tuple(sorted(set(requested)))
    masks = _validate_maskset(masks)
    _require_int(anchor_mask, 0, 15, 'anchor_mask')
    if objective not in ('identify', 'anchor'):
        raise DesignError('objective must be identify or anchor')

    @lru_cache(maxsize=None)
    def solve(state: tuple[int, ...], unused: tuple[int, ...]) -> Plan:
        if _solved(state, objective, anchor_mask):
            return Plan(0, Fraction(0), None)
        possibilities: list[tuple[tuple, Plan]] = []
        for action_id in unused:
            groups = _partition(row, state, action_id)
            if len(groups) < 2:
                continue  # Interventions reproducing observation give no information.
            remainder = tuple(x for x in unused if x != action_id)
            children = [(len(sub), solve(sub, remainder)) for sub in groups.values()]
            if any(child.worst is None or child.expected is None for _, child in children):
                continue
            max_depth = 1 + max(child.worst for _, child in children)
            average = Fraction(1) + sum(
                (Fraction(count, len(state)) * child.expected for count, child in children),
                Fraction(0))
            plan = Plan(max_depth, average, action_id)
            possibilities.append(((max_depth, average, action_id), plan))
        if not possibilities:
            return Plan(None, None, None)
        return min(possibilities, key=lambda item: item[0])[1]

    return solve(masks, available)


def _fraction(value: Fraction | None) -> dict | None:
    if value is None:
        return None
    return {'numerator': value.numerator, 'denominator': value.denominator,
            'decimal': float(value)}


def _entropy(groups: dict[bool, tuple[int, ...]], n: int) -> float:
    return log2(n) - sum(len(sub) / n * log2(len(sub)) for sub in groups.values())


def apply_evidence(row: dict, evidence: list[dict]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if not isinstance(evidence, list) or len(evidence) > 8:
        raise DesignError('evidence must be a list of at most 8 observations')
    remaining = MASKS
    tried: list[int] = []
    for event in evidence:
        if not isinstance(event, dict) or set(event) != {'action_id', 'observed_Y'}:
            raise DesignError('each evidence item must have only action_id and observed_Y')
        action_id = _require_int(event['action_id'], 0, 7, 'action_id')
        truth = _bool01(event['observed_Y'], 'observed_Y')
        if action_id in tried:
            raise DesignError('repeated action in one evidence sequence')
        tried.append(action_id)
        remaining = tuple(mask for mask in remaining if _response(row, mask, action_id) == truth)
        if not remaining:
            raise DesignError('inconsistent observation: no v0.18 hypothesis fits the evidence')
    return remaining, tuple(sorted(tried))


def recommend(row: dict, anchor_mask: int, objective: str = 'identify',
              evidence: list[dict] | None = None, allowed_actions: Iterable[int] = range(8)) -> dict:
    _require_int(anchor_mask, 0, 15, 'anchor_mask')
    if objective not in ('identify', 'anchor'):
        raise DesignError('invalid objective')
    remaining, tried = apply_evidence(row, evidence if evidence is not None else [])
    requested = tuple(allowed_actions)
    for a in requested:
        _require_int(a, 0, 7, 'allowed action')
    allowed = set(requested)
    usable = sorted(allowed.difference(tried))
    plan = optimize(row, remaining, objective, anchor_mask, usable)
    # When exact identification is impossible under access restrictions, offer a
    # best available partial split while explicitly retaining the impossibility.
    suggested = plan.action
    partial_only = False
    if suggested is None and plan.worst is None:
        information = []
        for a in usable:
            partition = _partition(row, remaining, a)
            if len(partition) >= 2:
                information.append((-_entropy(partition, len(remaining)), a))
        if information:
            suggested = min(information)[1]
            partial_only = True
    next_action = action_data(suggested) if suggested is not None else None
    if next_action is not None:
        parts = _partition(row, remaining, suggested)
        next_action = {**next_action,
            'partitions': {str(outcome).lower(): list(masks) for outcome, masks in parts.items()},
            'information_gain_bits_uniform': round(_entropy(parts, len(remaining)), 6),
            'partial_information_only': partial_only,
        }
    return {
        'objective': objective,
        'hypotheses_remaining': list(remaining),
        'count': len(remaining),
        'anchor_mask': anchor_mask,
        'identified': len(remaining) == 1 if objective == 'identify' else _solved(remaining, 'anchor', anchor_mask),
        'decision_if_determined': (remaining[0] if objective == 'identify' and len(remaining) == 1 else
                                   (remaining == (anchor_mask,)) if objective == 'anchor' and _solved(remaining, 'anchor', anchor_mask) else None),
        'next_experiment': next_action,
        'minimum_worst_case_additional_interventions': plan.worst,
        'minimum_expected_additional_interventions_uniform': _fraction(plan.expected),
        'identifiability_under_allowed_actions': plan.worst is not None,
        'used_actions': list(tried),
        'unavailable_or_unselected_actions': sorted(set(range(8)) - allowed),
    }


def _action_signature(row: dict, mask: int, actions: tuple[int, ...]) -> tuple[bool, ...]:
    return tuple(_response(row, mask, action) for action in actions)


def static_budgets(row: dict) -> list[dict]:
    informative = informative_actions()
    rows = []
    for budget in range(5):
        options = list(combinations(informative, budget))
        groups_by_option = [len(set(_action_signature(row, mask, actions) for mask in MASKS)) for actions in options]
        best = max(groups_by_option)
        selected = options[groups_by_option.index(best)]
        rows.append({
            'budget': budget,
            'best_distinguishable_classes': best,
            'largest_indistinguishable_class': 16 // best,
            'best_action_ids': list(selected),
            'example_ambiguity': 16 // best,
        })
    return rows


def simulate(row: dict, family: v17.Family, true_mask: int,
             objective: str = 'identify') -> dict:
    _require_int(true_mask, 0, 15, 'true_mask')
    anchor_mask = _anchor_mask(row, family)
    model = v18.construct(family, true_mask)
    source, effect = parse_cause(family.expression)
    indicator = model.outcomes[effect]
    evidence: list[dict] = []
    steps = []
    for _ in range(9):
        suggestion = recommend(row, anchor_mask, objective, evidence)
        action = suggestion['next_experiment']
        if action is None:
            if not suggestion['identified'] or true_mask not in suggestion['hypotheses_remaining']:
                raise DesignError('unexpected non-identifiability in complete experimental model')
            return {
                'family_id': family.family_id,
                'true_mask': true_mask,
                'anchor_mask': anchor_mask,
                'objective': objective,
                'steps': steps,
                'number_of_interventions': len(steps),
                'compatible_masks_at_end': suggestion['hypotheses_remaining'],
                'final_decision': suggestion['decision_if_determined'],
                'simulated_scm_not_real_experiment': True,
            }
        idx = action['context_index']
        context = {'U': v18.CONTEXTS[idx][0], 'G': v18.CONTEXTS[idx][1]}
        observed = model.run(context, intervene={source: action['do_SIGNAL']})[indicator]
        if observed != _response(row, true_mask, action['action_id']):
            raise DesignError('SCM execution disagrees with saved intervention signature')
        evidence.append({'action_id': action['action_id'], 'observed_Y': observed})
        after = apply_evidence(row, evidence)[0]
        steps.append({
            'step': len(steps) + 1,
            'experiment': {k:v for k,v in action.items() if k != 'partitions'},
            'observed_Y': observed,
            'remaining_masks_after': list(after),
        })
    raise DesignError('planner did not terminate in the bounded action space')


def _cross_check_scm(row: dict, family: v17.Family) -> int:
    """Recompute *every* stored observation from BooleanSCM, not just mask bits."""
    source, effect = parse_cause(family.expression)
    evaluations = 0
    for mask in MASKS:
        model = v18.construct(family, mask)
        indicator = model.outcomes[effect]
        for a in range(8):
            action = action_data(a)
            truth = model.run(action['background'], intervene={source: action['do_SIGNAL']})[indicator]
            if truth != _response(row, mask, a):
                raise DesignError(f'SCM/stored signature mismatch at {family.family_id}, {mask}, {a}')
            evaluations += 1
    return evaluations


def make_report() -> dict:
    previous = _read_pinned_report()
    families = {f.family_id: f for f in v17.load_families()}
    if set(families) != {r['family_id'] for r in previous['families']}:
        raise DesignError('v0.17 family IDs do not match v0.18 report')
    results = []
    evaluations = 0
    for row in previous['families']:
        family = families[row['family_id']]
        anchor_mask = _anchor_mask(row, family)
        evaluations += _cross_check_scm(row, family)
        exact = recommend(row, anchor_mask, 'identify')
        anchor = recommend(row, anchor_mask, 'anchor')
        budgets = static_budgets(row)
        if exact['minimum_worst_case_additional_interventions'] != 4 or exact['minimum_expected_additional_interventions_uniform']['decimal'] != 4.0:
            raise DesignError('unexpected full identification optimum')
        if anchor['minimum_worst_case_additional_interventions'] != 4 or anchor['minimum_expected_additional_interventions_uniform'] != _fraction(Fraction(15,8)):
            raise DesignError('unexpected anchor discrimination optimum')
        if budgets[-1]['best_distinguishable_classes'] != 16 or budgets[3]['best_distinguishable_classes'] != 8:
            raise DesignError('unexpected static discriminability')
        informative = informative_actions()
        if any(len(_partition(row, MASKS, a)) != (1 if a not in informative else 2) for a in range(8)):
            raise DesignError('intervention action partitions do not match declared search class')
        exact_paths = [simulate(row, family, m, 'identify') for m in MASKS]
        anchor_paths = [simulate(row, family, m, 'anchor') for m in MASKS]
        exact_costs = [p['number_of_interventions'] for p in exact_paths]
        anchor_costs = [p['number_of_interventions'] for p in anchor_paths]
        if max(exact_costs) != 4 or sum(exact_costs) != 64:
            raise DesignError('full identification traces do not match optimal DP costs')
        if max(anchor_costs) != 4 or sum(anchor_costs) != 30:
            raise DesignError('anchor agreement traces do not match optimal DP costs')
        demonstrations = {
            'same_as_anchor': anchor_paths[anchor_mask],
            'some_different_from_anchor': anchor_paths[anchor_mask ^ 1],
            'exact_mask_example': exact_paths[anchor_mask ^ 5],
        }
        results.append({
            'family_id': family.family_id,
            'expression': family.expression,
            'anchor_mask': anchor_mask,
            'baseline_observations_U_G': row['anchor_observations_U_G'],
            'natural_value_controls_action_ids': [a for a in range(8) if a not in informative],
            'informative_off_support_actions': [action_data(a) for a in informative],
            'minimum_identification_set': list(informative),
            'static_budget_classes': budgets,
            'optimal_exact_identification': exact,
            'optimal_anchor_agreement_test': anchor,
            'trace_examples': demonstrations,
            'enumerated_exact_identification_costs_per_mask_0_to_15': exact_costs,
            'enumerated_anchor_agreement_costs_per_mask_0_to_15': anchor_costs,
        })
    return {
        'format': FORMAT,
        'versioned_spec_sha256': sha256(SPEC_PATH.read_bytes()).hexdigest(),
        'pinned_v018_report_sha256': V018_REPORT_SHA256,
        'pinned_v018_search_space_sha256': V018_SPEC_SHA256,
        'experiment_model': ('Four Boolean backgrounds U,G; natural SIGNAL=U. For each background '
                             'one off-support do(SIGNAL != U) yields exactly one H bit; '
                             'natural-value interventions reveal none. No noise, unit cost.'),
        'summary': {
            'families': len(results),
            'candidate_models': 16 * len(results),
            'validated_synthetic_intervention_outcomes': evaluations,
            'complete_observational_only_identification_possible': False,
            'natural_value_controls_information_gain_bits': 0,
            'informative_interventions_per_family': 4,
            'minimum_worst_case_exact_identification_interventions': 4,
            'minimum_expected_exact_identification_interventions_uniform': 4.0,
            'minimum_worst_case_anchor_agreement_interventions': 4,
            'minimum_expected_anchor_agreement_interventions_uniform': 1.875,
            'discriminable_classes_by_budget_0_to_4': [1,2,4,8,16],
            'same_prior_across_all_families': True,
            'adaptive_reduces_worst_case_full_identification_vs_static': False,
            'independent_ai_readers': 0,
            'empirical_interventions': 0,
            'actual_world_causal_inference': False,
            'published_registry_changed': False,
        },
        'family_results': results,
    }


def verify_report() -> dict:
    expected = make_report()
    try:
        saved = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesignError(f'missing/invalid v0.19 report: {exc}') from exc
    if saved != expected:
        raise DesignError('v0.19 report diverges from independent recomputation')
    return {
        'ok': True,
        'families_checked': expected['summary']['families'],
        'synthetic_scm_interventions_replayed': expected['summary']['validated_synthetic_intervention_outcomes'],
        'all_costs_and_examples_match': True,
        'no_empirical_or_AI_comprehension_claim': True,
    }


def parse_evidence(values: list[str]) -> list[dict]:
    out = []
    for value in values:
        pieces = value.split('=', 1)
        if len(pieces) != 2 or pieces[1].lower() not in ('true','false','1','0'):
            raise DesignError('evidence must be like 1=true or 4=false (action_id=observed_Y)')
        try:
            index = int(pieces[0])
        except ValueError as exc:
            raise DesignError('invalid evidence action ID') from exc
        out.append({'action_id':index, 'observed_Y':pieces[1].lower() in ('true','1')})
    return out


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('command', choices=('check','report','summary','recommend','simulate','emit-spec'))
    cli.add_argument('--family', default='F17_DIRECT')
    cli.add_argument('--mask', type=int, default=0)
    cli.add_argument('--objective', choices=('identify','anchor'), default='identify')
    cli.add_argument('--evidence', action='append', default=[], metavar='ACTION=BOOL')
    cli.add_argument('--forbid-context', action='append', type=int, default=[], metavar='INDEX')
    args = cli.parse_args(argv)
    try:
        if args.command == 'emit-spec':
            print(serialized_spec(), end='')
            return 0
        if args.command == 'check':
            output = verify_report()
        elif args.command in ('report', 'summary'):
            full = make_report()
            output = full if args.command == 'report' else full['summary']
        else:
            previous = _read_pinned_report()
            row = _family_row(previous, args.family)
            families = {fam.family_id: fam for fam in v17.load_families()}
            family = families[row['family_id']]
            if args.command == 'simulate':
                if args.evidence or args.forbid_context:
                    raise DesignError('simulate does not accept observational evidence or forbidden contexts')
                output = simulate(row, family, args.mask, args.objective)
            else:
                for idx in args.forbid_context:
                    _require_int(idx, 0, 3, 'forbid-context')
                allowed = [i for i in range(8) if action_data(i)['context_index'] not in args.forbid_context]
                output = recommend(row, _anchor_mask(row, family), args.objective,
                                   evidence=parse_evidence(args.evidence), allowed_actions=allowed)
                output['family_id'] = family.family_id
        print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except (DesignError, v18.SearchError, v17.RobustnessError, CausalError, ValueError, OSError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
