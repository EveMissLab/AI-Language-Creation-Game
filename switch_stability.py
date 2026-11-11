"""ALCG v0.33 — conservative switching with frozen-prefix evidence.

All streams and performance tracks in this research module are SYNTHETIC.
The Beta posterior is an explicitly assumed IID Bernoulli win model, not a
calibrated statistical guarantee for correlated time windows.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
from math import comb
import json
from pathlib import Path
import sys
from typing import Any

import alcg
import model_selection as v32
import workload_estimator as v30
import adaptive_cache as v29
import forecast_calibration as v31

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'data/switch-stability-policy-v0.33.json'
REPORT = ROOT / 'reports/switch-stability-v0.33.json'
SAMPLES = ROOT / 'samples/switch-decisions-v0.33.alcg'
FORMAT = 'ALCG-v0.33-bounded-switch-stability'
EXPERTS = v32.EXPERTS
SCENARIOS = v32.SCENARIOS
CUTS = v32.CUTS
HORIZON = v32.HORIZON
LOOKBACK = 3
MIN_EVIDENCE = 2
POSTERIOR_THRESHOLD = Fraction(7, 8)
MIN_MARGIN = Fraction(1, 1000)
SWITCH_PENALTY = v32.SWITCH_PENALTY
COOLDOWN = 1


class GuardError(ValueError):
    """Invalid evidence, mismatch, future leak or malformed expression."""


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def digest(obj: Any) -> str:
    return sha256(canonical(obj)).hexdigest()


def exact(value: Fraction | int) -> dict[str, int]:
    f = Fraction(value)
    return {'num': f.numerator, 'den': f.denominator}


def frac(value: Any) -> Fraction:
    if (not isinstance(value, dict) or set(value) != {'num', 'den'}
            or any(type(x) is not int for x in value.values())
            or value['den'] <= 0):
        raise GuardError('expected canonical rational object')
    result = Fraction(value['num'], value['den'])
    if value != exact(result):
        raise GuardError('rational is not in canonical reduced form')
    return result


def expected_config() -> dict[str, Any]:
    return {
        'format': FORMAT,
        'v032_report_sha256': sha256(v32.REPORT_PATH.read_bytes()).hexdigest(),
        'v030_events_sha256': sha256(v30.FIXTURE_PATH.read_bytes()).hexdigest(),
        'v029_timing_source_sha256': sha256(v29.SOURCE_REPORT_PATH.read_bytes()).hexdigest(),
        'expert_names': list(EXPERTS),
        'scenarios': list(SCENARIOS),
        'cuts': list(CUTS),
        'horizon': HORIZON,
        'lookback_closed_windows': LOOKBACK,
        'min_evidence_windows': MIN_EVIDENCE,
        'beta_prior': {'alpha': 1, 'beta': 1},
        'posterior_win_threshold': exact(POSTERIOR_THRESHOLD),
        'switch_penalty': exact(SWITCH_PENALTY),
        'minimum_extra_margin': exact(MIN_MARGIN),
        'cooldown_subsequent_windows': COOLDOWN,
        'stress_tracks': ['alternating', 'sustained_shift', 'single_spike', 'flat'],
        'stress_length': 12,
    }


def config() -> dict[str, Any]:
    stored = json.loads(CONFIG.read_text(encoding='utf-8'))
    if stored != expected_config():
        raise GuardError('v0.33 configuration or frozen source digest mismatch')
    return stored


def beta_tail_probability(wins: int, losses: int) -> Fraction:
    """P(p > 1/2 | Beta(wins+1,losses+1)), exact for integer counts.

    This has an IID Bernoulli likelihood assumption. Dependent windows may
    invalidate that assumption; the score is a heuristic gate, not a CI.
    """
    if type(wins) is not int or type(losses) is not int or min(wins, losses) < 0:
        raise GuardError('win/loss counts must be nonnegative integers')
    n = wins + losses + 1
    return Fraction(sum(comb(n, j) for j in range(wins+1)), 2**n)


def _loss_row(row: dict[str, Any]) -> dict[str, Fraction]:
    if not isinstance(row, dict) or set(row) != set(EXPERTS):
        raise GuardError('loss row must contain all fixed experts')
    if any(not (isinstance(row[name], dict) or type(row[name]) is int
                    or isinstance(row[name], Fraction)) for name in EXPERTS):
        raise GuardError('loss inputs must be exact rational values, never floats')
    values = {name: (frac(row[name]) if isinstance(row[name], dict)
                     else Fraction(row[name])) for name in EXPERTS}
    if any(value < 0 or value > 2 for value in values.values()):
        raise GuardError('bounded combined Brier losses must lie in [0,2]')
    return values


def decision(rows: list[dict[str, Any]], incumbent: str,
             current_index: int, last_switch_index: int | None,
             *, lookback: int = LOOKBACK) -> dict[str, Any]:
    """Use ONLY previously closed loss rows to choose at current_index.

    rows must be a strict past prefix (len(rows) <= current_index), and absent
    past windows are allowed for unsupported expert forecasts. For comparable
    stress tracks len(rows) == current_index.
    """
    if incumbent not in EXPERTS or type(current_index) is not int or current_index < 0:
        raise GuardError('invalid incumbent or decision time')
    if (type(lookback) is not int or lookback < 1 or len(rows) > current_index
            or (last_switch_index is not None and
                (type(last_switch_index) is not int or
                 last_switch_index >= current_index or last_switch_index < 0))):
        raise GuardError('invalid evidence prefix, lookback or prior switch')
    bounded = [_loss_row(row) for row in rows[-lookback:]]
    means = ({m: sum((r[m] for r in bounded), Fraction(0))/len(bounded)
              for m in EXPERTS} if bounded else {})
    alternatives = []
    for expert in EXPERTS:
        if expert == incumbent:
            continue
        wins = sum(r[expert] < r[incumbent] for r in bounded)
        losses = sum(r[expert] > r[incumbent] for r in bounded)
        ties = len(bounded)-wins-losses
        posterior = beta_tail_probability(wins, losses)
        advantage = means[incumbent]-means[expert] if bounded else Fraction(0)
        alternatives.append({
            'expert': expert,
            'wins': wins, 'losses': losses, 'ties': ties,
            'posterior_win_score': exact(posterior),
            'mean_loss_advantage': exact(advantage),
            'qualifies': bool(len(bounded)>=MIN_EVIDENCE
                             and wins>=MIN_EVIDENCE
                             and posterior >= POSTERIOR_THRESHOLD
                             and advantage > SWITCH_PENALTY + MIN_MARGIN),
        })
    qualified = [x for x in alternatives if x['qualifies']]
    cool = (last_switch_index is not None
            and current_index-last_switch_index <= COOLDOWN)
    if len(bounded) < MIN_EVIDENCE:
        selected, reason = incumbent, 'INSUFFICIENT_CLOSED_EVIDENCE'
    elif cool:
        selected, reason = incumbent, 'COOLDOWN_KEEP'
    elif qualified:
        winner = min(qualified, key=lambda x:(means[x['expert']], EXPERTS.index(x['expert'])))
        selected, reason = winner['expert'], 'PERSISTENT_ADVANTAGE_SWITCH'
    else:
        selected, reason = incumbent, 'NO_QUALIFYING_ADVANTAGE'
    return {
        'selected': selected, 'reason': reason,
        'incumbent_before': incumbent,
        'closed_windows_scored': len(bounded),
        'cooldown_active': cool,
        'mean_prior_losses': {m:exact(v) for m,v in means.items()},
        'candidate_evidence': alternatives,
    }


def _rates_and_outcome(full: dict[str, Any], at_tick: int,
                       *, as_of: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if at_tick >= as_of:
        raise GuardError('cannot derive a finished outcome from an unclosed future')
    past = v32.prefix(full, at_tick)
    rates = v32.expert_rates(past, at_tick)
    if rates is None:
        return None, None
    if at_tick + HORIZON > as_of:
        raise GuardError('closed evidence would require future observations')
    outcome = v32.closed_outcome(full['events'][:as_of], at_tick)
    result = {name:exact(frac(v32.loss(rates[name],outcome)['combined_loss']))
              for name in EXPERTS}
    return result, {
        'prior_cut': at_tick,
        'outcome_sha256': digest(outcome),
        'losses': result,
    }


def issue_at(past: dict[str, Any], at_tick: int) -> dict[str, Any]:
    """Only accept the exact visible event prefix, never a full stream."""
    v30.validate_document(past)
    if (type(at_tick) is not int or at_tick not in CUTS
            or len(past['events']) != at_tick or past['label'] not in SCENARIOS
            or past['origin'] != 'synthetic-fixture'):
        raise GuardError('issuance needs the exact supported synthetic past prefix')
    config()
    incumbent, last_switch = 'RAW', None
    prior_windows: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for idx,cut in enumerate(CUTS):
        if cut > at_tick:
            break
        if idx > 0:
            older = CUTS[idx-1]
            if older + HORIZON <= cut:
                losses, receipt = _rates_and_outcome(past, older, as_of=cut)
                if losses is not None and receipt is not None:
                    prior_windows.append(receipt)
        d = decision([x['losses'] for x in prior_windows], incumbent, idx, last_switch)
        if d['selected'] != incumbent:
            last_switch = idx
        incumbent = d['selected']
        if v32.expert_rates(v32.prefix(past,cut),cut) is None:
            d = {**d,'selected':'DEFER','reason':'NO_SUPPORTED_FORECAST'}
        decisions.append(d)
    chosen = decisions[-1]
    current_rates = v32.expert_rates(past, at_tick)
    if current_rates is None:
        chosen = {**chosen, 'selected':'DEFER','reason':'NO_SUPPORTED_FORECAST'}
        route, candidates = 'direct', None
    else:
        candidates = {name:{'read_probability':exact(current_rates[name][0]),
                            'reset_probability':exact(current_rates[name][1])}
                      for name in EXPERTS}
        row = v30.measurement_rows()['selective']
        route = v29.estimate(row,v31.to_profile(current_rates[chosen['selected']]))['selection']
    evidence = [x for x in prior_windows if x['prior_cut'] + HORIZON <= at_tick][-LOOKBACK:]
    body = {
        'format': FORMAT, 'source': 'synthetic-fixture',
        'scenario': past['label'], 'at_tick': at_tick,
        'horizon': HORIZON,
        'source_prefix_sha256': digest(past['events']),
        'source_receipt_sha256': past['receipt_sha256'],
        'v032_report_sha256': config()['v032_report_sha256'],
        'selected': chosen['selected'], 'reason': chosen['reason'],
        'policy_route': route, 'candidates': candidates,
        'decision_evidence': chosen,
        'prior_closed_receipts': evidence,
    }
    return {**body, 'issue_sha256': digest(body)}


def verify_issuance(issued: dict[str, Any], past: dict[str, Any]) -> bool:
    if (not isinstance(issued, dict) or issued.get('issue_sha256') != digest(
            {k:v for k,v in issued.items() if k!='issue_sha256'})):
        raise GuardError('invalid issuance digest')
    if issued != issue_at(past, issued.get('at_tick')):
        raise GuardError('self-rehashed issuance differs from frozen-prefix replay')
    return True


def expression(record: dict[str, Any]) -> str:
    if record['selected'] not in (*EXPERTS,'DEFER'):
        raise GuardError('invalid selected expert')
    node = alcg.Call('GATE_V033', (
        ('scenario',alcg.Name(record['scenario'].upper())),
        ('at',alcg.String(str(record['at_tick']))),
        ('selected',alcg.Name(record['selected'])),
        ('reason',alcg.Name(record['reason'])),
        ('prior',alcg.String(str(len(record['prior_closed_receipts'])))),
        ('policy',alcg.Name(record['policy_route'].upper())),
        ('prefix_sha256',alcg.String(record['source_prefix_sha256'])),
        ('receipt_sha256',alcg.String(record['issue_sha256'])),
    ))
    result = alcg.render(node)
    if alcg.parse(result) != node:
        raise GuardError('ALCG projection failed structural roundtrip')
    return result


def verify_expression(value: str, record: dict[str, Any]) -> bool:
    try:
        if alcg.parse(value) != alcg.parse(expression(record)):
            raise GuardError('ALCG gated decision differs from frozen record')
    except alcg.ParseError as exc:
        raise GuardError('malformed ALCG gated decision') from exc
    return True


def stress_track(name: str) -> list[dict[str, Fraction]]:
    """Independent hand-authored loss regimes, not training or empirical data."""
    if name not in ('alternating','sustained_shift','single_spike','flat'):
        raise GuardError('unknown synthetic stress track')
    out = []
    for t in range(12):
        if name == 'alternating':
            a,b = (Fraction(1,10),Fraction(3,10)) if t%2==0 else (Fraction(3,10),Fraction(1,10))
        elif name == 'sustained_shift':
            a,b = (Fraction(1,20),Fraction(1,3)) if t<6 else (Fraction(3,10),Fraction(1,20))
        elif name == 'single_spike':
            a,b = (Fraction(3,10),Fraction(1,20)) if t==5 else (Fraction(1,20),Fraction(3,10))
        else:
            a,b = Fraction(1,10),Fraction(1,10)
        out.append({'RAW':a,'LAGGED':b,'HEDGE':Fraction(2,5)})
    return out


def stress_evaluate(name: str) -> dict[str, Any]:
    values = stress_track(name)
    incumbent,last_switch='RAW',None
    guarded = []
    naive = []
    for t in range(len(values)):
        d=decision(values[:t],incumbent,t,last_switch)
        if d['selected']!=incumbent:
            last_switch=t
        incumbent=d['selected']
        guarded.append(incumbent)
        if not t:
            naive.append('RAW')
        else:
            prior=values[t-1]
            naive.append(min(EXPERTS,key=lambda x:(prior[x],EXPERTS.index(x))))
    switches=sum(guarded[i]!=guarded[i-1] for i in range(1,len(guarded)))
    n_switches=sum(naive[i]!=naive[i-1] for i in range(1,len(naive)))
    return {
        'name':name,'length':len(values),
        'losses':[ {k:exact(v) for k,v in row.items()} for row in values ],
        'gated_selection':guarded, 'naive_one_window_selection':naive,
        'gated_switches':switches,'naive_switches':n_switches,
        'gated_realized_total_loss':exact(sum((values[i][m] for i,m in enumerate(guarded)),Fraction(0))),
        'naive_realized_total_loss':exact(sum((values[i][m] for i,m in enumerate(naive)),Fraction(0))),
        'gated_minus_naive_total_loss':exact(sum((values[i][guarded[i]]-values[i][naive[i]] for i in range(len(values))),Fraction(0))),
        'post_shift_first_gated_change':next((i for i in range(6,len(guarded)) if guarded[i]!='RAW'), None)
                if name=='sustained_shift' else None,
    }


def report() -> dict[str, Any]:
    cfg = config()
    records=[]
    settlement=[]
    # v0.33 pins the exact v0.32 report bytes in expected_config().
    # v0.32's own unchanged CI replays and validates that historical report.
    # Avoid recomputing its entire costly corpus for each downstream check.
    v32_snapshots = json.loads(v32.REPORT_PATH.read_text(encoding='utf-8'))
    for label in SCENARIOS:
        stream = v32.stream(label)
        for cut in CUTS:
            issue = issue_at(v32.prefix(stream,cut),cut)
            records.append(issue)
            baseline = next(x for x in v32_snapshots['issuances']
                            if x['scenario']==label and x['at_tick']==cut)
            settlement_baseline = next(x for x in v32_snapshots['settlements']
                                       if x['issue_sha256']==baseline['issue_sha256'])
            scored = settlement_baseline['scored_experts']
            settlement.append({
                'issue_sha256':issue['issue_sha256'],
                'outcome_sha256':settlement_baseline['observed']['future_receipt_sha256'],
                'eligible': scored is not None,
                'gated_loss': scored[issue['selected']]['combined_loss'] if scored is not None else None,
                'v032_loss':scored[baseline['selected']]['combined_loss'] if scored is not None else None,
                'always_raw_loss':scored['RAW']['combined_loss'] if scored is not None else None,
            })
    paired=[x for x in settlement if x['eligible']]
    def average(key: str) -> dict[str, int]:
        return exact(sum((frac(x[key]) for x in paired),Fraction(0))/len(paired))
    counts={m:sum(x['selected']==m for x in records) for m in (*EXPERTS,'DEFER')}
    switches={s:sum(records[i]['scenario']==s and records[i]['selected']!=records[i-1]['selected']
                   for i in range(1,len(records)) if records[i]['scenario']==records[i-1]['scenario']
                   and records[i]['selected']!='DEFER' and records[i-1]['selected']!='DEFER')
              for s in SCENARIOS}
    stresses={name:stress_evaluate(name) for name in cfg['stress_tracks']}
    summary = {
        'issued_windows':len(records), 'eligible_scored_windows':len(paired),
        'deferred_windows':counts['DEFER'], 'selected_inventory':counts,
        'switches_by_scenario':switches,
        'total_switches':sum(switches.values()),
        'gated_mean_combined_brier':average('gated_loss'),
        'v032_mean_combined_brier':average('v032_loss'),
        'always_raw_mean_combined_brier':average('always_raw_loss'),
        'stress_gated_vs_naive_switches':{
            k:{'gated':v['gated_switches'],'naive':v['naive_switches']}
            for k,v in stresses.items()},
    }
    body = {
        'format':FORMAT, 'version':'v0.33', 'config':cfg,
        'source_v032_report_sha256':sha256(v32.REPORT_PATH.read_bytes()).hexdigest(),
        'issuances':records,'settlements':settlement,
        'stress':stresses,'summary':summary,
        'limitations':[
            'Only deterministic synthetic streams and hand-authored diagnostic stress tracks.',
            'Beta win score assumes IID Bernoulli comparisons, which correlated windows may violate.',
            'A high posterior win score is not calibrated confidence in real forecast accuracy.',
            'Short lookbacks may miss short genuine regime shifts and may delay useful switching.',
            'No independent AI semantic comprehension, production forecast, or runtime acceleration measured.',
            'Costs and cooldown are authored fixed thresholds, not optimal or learned policies.',
            'Frozen v0.32 report and all historical grammars, model files and dictionaries remain unchanged.',
            'SHA-256 records verify internal consistency, not author identity or external data authenticity.',
        ],
    }
    return {**body,'report_sha256':digest(body)}


def check() -> dict[str, Any]:
    stored=json.loads(REPORT.read_text(encoding='utf-8'))
    fresh=report()
    if stored!=fresh:
        raise GuardError('frozen v0.33 report differs from exact recomputation')
    lines=[x.strip() for x in SAMPLES.read_text(encoding='utf-8').splitlines()
           if x.strip() and not x.lstrip().startswith('#')]
    expected=[expression(row) for row in fresh['issuances']]
    if lines!=expected:
        raise GuardError('v0.33 sample expressions do not match report receipts')
    for line,record in zip(lines,fresh['issuances']):
        verify_expression(line,record)
    return {'status':'PASS','issuances':len(lines),
            'scored':fresh['summary']['eligible_scored_windows'],
            'switches':fresh['summary']['total_switches'],
            'report_sha256':fresh['report_sha256'],
            'warning':'bounded synthetic evidence score, not calibrated real-world confidence'}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description='ALCG v0.33 bounded model switch stability')
    cmds=parser.add_subparsers(dest='command',required=True)
    cmds.add_parser('check');cmds.add_parser('report')
    p=cmds.add_parser('issue');p.add_argument('--case',choices=SCENARIOS,required=True)
    p.add_argument('--at',type=int,choices=CUTS,required=True)
    p=cmds.add_parser('stress');p.add_argument('--case',choices=('alternating','sustained_shift','single_spike','flat'),required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='check':result=check()
        elif args.command=='report':result=report()['summary']
        elif args.command=='stress':result=stress_evaluate(args.case)
        else:
            full=v32.stream(args.case)
            print(expression(issue_at(v32.prefix(full,args.at),args.at)))
            return 0
        print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (GuardError, v32.SelectionError, v30.WorkloadError, v29.AdaptiveError,
            ValueError, OSError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
