"""ALCG v0.32: strictly prefix-only switching between finite forecast experts.

All input streams are SYNTHETIC. Selection uses previously closed holdouts
only, with exact rational Brier scores. It does not learn from real users,
validate language comprehension, or assert causal model truth.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import alcg
import forecast_calibration as v31
import workload_estimator as v30
import adaptive_cache as v29

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'data/model-selection-policy-v0.32.json'
REPORT_PATH = ROOT / 'reports/model-selection-v0.32.json'
SAMPLE_PATH = ROOT / 'samples/model-selections-v0.32.alcg'
FORMAT = 'ALCG-v0.32-prequential-model-selection'
SCENARIOS = ('stable', 'churn', 'sparse', 'drift')
EXPERTS = ('RAW', 'LAGGED', 'HEDGE')
CUTS = (32, 64, 96, 128, 160)
HORIZON = 32
LOOKBACK = 2
SWITCH_PENALTY = Fraction(1, 10000)
HEDGE_FLOOR = Fraction(1, 3)


class SelectionError(ValueError):
    """Incomplete, inconsistent or misordered model selection evidence."""


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def digest(obj: Any) -> str:
    return sha256(canonical(obj)).hexdigest()


def exact(x: Fraction | int) -> dict[str, int]:
    f = Fraction(x)
    return {'num': f.numerator, 'den': f.denominator}


def frac(x: Any) -> Fraction:
    if (not isinstance(x, dict) or set(x) != {'num', 'den'}
            or any(type(n) is not int for n in x.values()) or x['den'] <= 0):
        raise SelectionError('expected a canonical exact rational')
    return Fraction(x['num'], x['den'])


def config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    expected = {
        'format': FORMAT,
        'source_v030_events_sha256': sha256(v30.FIXTURE_PATH.read_bytes()).hexdigest(),
        'source_v031_report_sha256': sha256(v31.REPORT_PATH.read_bytes()).hexdigest(),
        'source_v028_timings_sha256': sha256(v29.SOURCE_REPORT_PATH.read_bytes()).hexdigest(),
        'scenarios': list(SCENARIOS), 'cuts': list(CUTS),
        'horizon': HORIZON, 'history_lookback': LOOKBACK,
        'expert_names': list(EXPERTS),
        'switch_penalty': exact(SWITCH_PENALTY),
        'hedge_reset_floor': exact(HEDGE_FLOOR),
        'extended_events_per_scenario': 192,
    }
    if cfg != expected:
        raise SelectionError('configuration/pinned inputs mismatch')
    return cfg


def stream(label: str, n: int = 192) -> dict[str, Any]:
    if label not in SCENARIOS or n != 192:
        raise SelectionError('unsupported bounded synthetic stream')
    return v30.document(label, 'synthetic-fixture', v30.synthetic_events(label, n))


def prefix(full: dict[str, Any], at_tick: int) -> dict[str, Any]:
    v30.validate_document(full)
    if type(at_tick) is not int or at_tick not in CUTS or len(full['events']) < at_tick:
        raise SelectionError('cut outside available past or fixed cut inventory')
    return v30.document(full['label'], full['origin'], full['events'][:at_tick])


def closed_outcome(events: list[dict[str, Any]], at_tick: int) -> dict[str, Any]:
    """Read ONLY an already completed [at_tick, at_tick + 32) block."""
    if (type(at_tick) is not int or at_tick not in CUTS or
            at_tick + HORIZON > len(events)):
        raise SelectionError('future holdout is not closed yet')
    future = events[at_tick:at_tick+HORIZON]
    reads = [e for e in future if e['kind'] == 'read']
    return {
        'start_tick': at_tick, 'end_tick': at_tick+HORIZON,
        'opportunities': len(future), 'reads': len(reads),
        'read_gaps': max(0, len(reads)-1),
        'revision_changes_internal': sum(int(e['revision_changed']) for e in reads[1:]),
        'future_receipt_sha256': digest(future),
    }


def expert_rates(past: dict[str, Any], at_tick: int,
                 row: dict[str, Any] | None = None) -> dict[str, tuple[Fraction, Fraction]] | None:
    """No event at tick >= at_tick may influence any expert prediction."""
    v30.validate_document(past)
    if at_tick not in CUTS or len(past['events']) != at_tick:
        raise SelectionError('forecast requires exactly the visible prefix')
    row = v30.measurement_rows()['selective'] if row is None else row
    base = v30.forecast(past, at_tick, row=row, horizon=HORIZON)
    raw = v31.baseline_rates(base)
    if raw is None:
        return None
    earlier = closed_outcome(past['events'], at_tick-HORIZON) if at_tick >= 64 else None
    lagged = v31.calibrate(raw, earlier) if earlier is not None else raw
    hedge = (raw[0], max(raw[1], HEDGE_FLOOR))
    return {'RAW': raw, 'LAGGED': lagged, 'HEDGE': hedge}


def loss(rates: tuple[Fraction, Fraction], result: dict[str, Any]) -> dict[str, Any]:
    p, q = rates
    if not (0 <= p <= 1 and 0 <= q <= 1):
        raise SelectionError('prediction is not a probability')
    a = v31.brier(p, result['reads'], result['opportunities'])
    b = v31.brier(q, result['revision_changes_internal'], result['read_gaps'])
    assert a is not None
    return {'read_brier': exact(a), 'reset_brier': exact(b) if b is not None else None,
            'combined_loss': exact(a + (b if b is not None else Fraction(0)))}


def _policy(past_issues: list[dict[str, Any]], events: list[dict[str, Any]],
            at_tick: int) -> tuple[str, str, list[dict[str, Any]], dict[str, Any]]:
    """Compare last LOOKBACK completed, previously frozen expert forecasts."""
    incumbent = next((x['selected'] for x in reversed(past_issues)
                      if x['selected'] in EXPERTS), 'RAW')
    completed = [x for x in past_issues if x['at_tick']+HORIZON <= at_tick
                 and x['candidates'] is not None][-LOOKBACK:]
    evidence = []
    for old in completed:
        outcome = closed_outcome(events, old['at_tick'])
        components = {model:loss((frac(old['candidates'][model]['read_probability']),
                                  frac(old['candidates'][model]['reset_probability'])),outcome)
                      for model in EXPERTS}
        evidence.append({'prior_issue_sha256': old['issue_sha256'],
                         'prior_cut': old['at_tick'], 'outcome': outcome,
                         'losses': components})
    if not evidence:
        return incumbent, 'insufficient_closed_evidence', evidence, {}
    means = {model: sum((frac(e['losses'][model]['combined_loss']) for e in evidence),
                        Fraction(0))/len(evidence) for model in EXPERTS}
    baseline = means[incumbent]
    competitors = sorted((means[m], EXPERTS.index(m), m) for m in EXPERTS if m != incumbent)
    if competitors and competitors[0][0]+SWITCH_PENALTY < baseline:
        selected = competitors[0][2]
        reason = 'switch_after_closed_window_scoring'
    else:
        selected = incumbent
        reason = 'keep_incumbent_under_switch_penalty'
    return selected, reason, evidence, {k:exact(v) for k,v in means.items()}


def issue_at(past: dict[str, Any], at_tick: int,
             row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue a selection from EXACTLY the available prefix (no future allowed)."""
    v30.validate_document(past)
    if type(at_tick) is not int or at_tick not in CUTS or len(past['events']) != at_tick:
        raise SelectionError('a prequential issuance must end at its cut')
    if past['origin'] != 'synthetic-fixture' or past['label'] not in SCENARIOS:
        raise SelectionError('v0.32 supports synthetic fixtures only')
    row = v30.measurement_rows()['selective'] if row is None else row
    history: list[dict[str, Any]] = []
    for older_cut in CUTS:
        if older_cut >= at_tick:
            break
        earlier_prefix = prefix(past, older_cut)
        history.append(_issue_once(earlier_prefix, older_cut, history, row))
    return _issue_once(past, at_tick, history, row)


def _issue_once(past: dict[str, Any], at_tick: int,
                history: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    rates = expert_rates(past, at_tick, row)
    selected, reason, evidence, means = _policy(history, past['events'], at_tick)
    if rates is None:
        selected, reason = 'DEFER', 'insufficient_prefix_for_forecasting'
        candidates, route = None, 'direct'
    else:
        candidates = {m:{'read_probability':exact(rates[m][0]),
                         'reset_probability':exact(rates[m][1])} for m in EXPERTS}
        route = v29.estimate(row, v31.to_profile(rates[selected]))['selection']
    body = {
        'format':FORMAT, 'kind':'ISSUE', 'source':'synthetic-fixture',
        'scenario':past['label'],'at_tick':at_tick, 'horizon':HORIZON,
        'source_prefix_sha256':digest(past['events']),
        'source_receipt_sha256':past['receipt_sha256'],
        'timing_source_sha256':row['source_sha256'],
        'selected':selected, 'reason':reason, 'policy_route':route,
        'candidates':candidates, 'scored_prior_evidence':evidence,
        'mean_prior_losses':means,
    }
    return {**body, 'issue_sha256': digest(body)}


def verify_issuance(record: dict[str, Any], past: dict[str, Any]) -> bool:
    if not isinstance(record, dict) or record.get('issue_sha256') != digest(
            {k:v for k,v in record.items() if k!='issue_sha256'}):
        raise SelectionError('issuance fingerprint mismatch')
    expected = issue_at(past, record['at_tick'])
    if record != expected:
        raise SelectionError('issuance differs from its frozen available prefix')
    return True


def settle(issued: dict[str, Any], complete: dict[str, Any]) -> dict[str, Any]:
    v30.validate_document(complete)
    at = issued['at_tick']
    past = prefix(complete, at)
    verify_issuance(issued, past)
    outcome = closed_outcome(complete['events'], at)
    scored = None
    if issued['candidates'] is not None:
        scored = {model:loss((frac(issued['candidates'][model]['read_probability']),
                              frac(issued['candidates'][model]['reset_probability'])),outcome)
                  for model in EXPERTS}
    body = {'issue_sha256':issued['issue_sha256'],'observed':outcome,
            'scored_experts':scored, 'status':'scored' if scored is not None else 'not_scored'}
    return {**body, 'settlement_sha256':digest(body)}


def expression(issued:dict[str, Any]) -> str:
    """Readable ALCG projection, with replay checked against the exact issuance."""
    def name(s:str) -> alcg.Name:
        return alcg.Name(s.upper())
    def string(x:Any) -> alcg.String:
        return alcg.String(str(x))
    def call(label:str,**values:alcg.Expr) -> alcg.Call:
        return alcg.Call(label, tuple(values.items()))
    e = call('SELECT_V032',
             scenario=name(issued['scenario']),
             at=string(issued['at_tick']),
             selected=name(issued['selected']),
             reason=name(issued['reason']),
             route=name(issued['policy_route']),
             closed=string(len(issued['scored_prior_evidence'])),
             prefix_sha256=string(issued['source_prefix_sha256']),
             issuance_sha256=string(issued['issue_sha256']))
    text=alcg.render(e)
    if alcg.parse(text)!=e:
        raise SelectionError('ALCG model selection roundtrip failed')
    return text


def verify_expression(value:str, issued:dict[str,Any]) -> bool:
    try:
        if alcg.parse(value) != alcg.parse(expression(issued)):
            raise SelectionError('ALCG selection text differs from exact issuance')
    except alcg.ParseError as exc:
        raise SelectionError('malformed ALCG selection text') from exc
    return True


def report() -> dict[str, Any]:
    cfg = config()
    cases = []
    settlements = []
    for label in SCENARIOS:
        full = stream(label)
        for at in CUTS:
            issued=issue_at(prefix(full, at), at)
            cases.append(issued)
            settlements.append(settle(issued, full))
    supported = [r for r in cases if r['selected'] in EXPERTS]
    switches = [r for r in supported if r['reason']=='switch_after_closed_window_scoring']
    paired = [(a, s) for a, s in zip(cases, settlements) if s['scored_experts'] is not None]
    def macro_loss(expert_fn):
        if not paired:
            return None
        return exact(sum((frac(s['scored_experts'][expert_fn(a)]['combined_loss'])
                          for a,s in paired), Fraction(0))/len(paired))
    chosen_total = sum((frac(s['scored_experts'][a['selected']]['combined_loss'])
                        for a,s in paired), Fraction(0))
    raw_total = sum((frac(s['scored_experts']['RAW']['combined_loss'])
                     for a,s in paired), Fraction(0))
    hindsight_total = sum((min(frac(s['scored_experts'][m]['combined_loss']) for m in EXPERTS)
                            for a,s in paired), Fraction(0))
    summary = {
        'selected_macro_combined_brier': macro_loss(lambda a:a['selected']),
        'always_raw_macro_combined_brier': macro_loss(lambda a:'RAW'),
        'always_lagged_macro_combined_brier': macro_loss(lambda a:'LAGGED'),
        'always_hedge_macro_combined_brier': macro_loss(lambda a:'HEDGE'),
        'selected_minus_always_raw_total_loss': exact(chosen_total-raw_total),
        'selected_minus_hindsight_oracle_total_loss': exact(chosen_total-hindsight_total),
        'hindsight_oracle_is_not_a_deployable_policy': True,
        'scenario_count':len(SCENARIOS), 'issued_windows':len(cases),
        'supported_windows':len(supported),
        'unsupported_windows':len(cases)-len(supported),
        'scored_windows':sum(s['status']=='scored' for s in settlements),
        'switches':len(switches),
        'switch_events':[{'scenario':x['scenario'],'at_tick':x['at_tick'],
                          'expert':x['selected']} for x in switches],
        'selected_inventory':{m:sum(r['selected']==m for r in cases) for m in (*EXPERTS,'DEFER')},
    }
    body = {
        'format':FORMAT, 'version':'v0.32',
        'config':cfg,
        'extended_streams_sha256':{label:digest(stream(label)) for label in SCENARIOS},
        'issuances':cases, 'settlements':settlements,
        'summary':summary,
        'limitations':[
            'Only deterministic synthetic event streams; not measured production traffic.',
            'No unseen independent AI readers or English-language comprehension measurement.',
            'Brier comparison is an explicit bounded policy, not a universal optimum.',
            'The expert set and switch threshold are authored before this experiment.',
            'Smoothing may adapt too slowly to abrupt workload regime changes.',
            'A stored receipt is an integrity checksum, not cryptographic authentication.',
            'The v0.29 decisions use pinned v0.28 single-host timing evidence, not live timings.',
            'Future holdouts are accessed only after their cut plus 32 opportunities is closed.',
            'No change to canonical language syntax, published dictionaries or historical data.',
        ],
    }
    return {**body,'report_sha256':digest(body)}


def check() -> dict[str, Any]:
    stored=json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    fresh=report()
    if stored!=fresh:
        raise SelectionError('saved model-selection report differs from source recomputation')
    lines=[x.strip() for x in SAMPLE_PATH.read_text(encoding='utf-8').splitlines()
           if x.strip() and not x.lstrip().startswith('#')]
    expected=[expression(r) for r in fresh['issuances']]
    if lines!=expected:
        raise SelectionError('published ALCG selections do not match frozen issuances')
    for text_, row in zip(lines, fresh['issuances']):
        verify_expression(text_,row)
    return {'status':'PASS','windows':len(expected), 'switches':fresh['summary']['switches'],
            'report_sha256':fresh['report_sha256'],
            'warning':'synthetic prequential model selection, not production accuracy'}


def main(argv:list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(description='ALCG v0.32 synthetic prefix-only expert switching')
    sub=parser.add_subparsers(dest='action', required=True)
    sub.add_parser('check'); sub.add_parser('report')
    p=sub.add_parser('issue'); p.add_argument('--case',choices=SCENARIOS,required=True)
    p.add_argument('--at',type=int,choices=CUTS,default=128)
    p=sub.add_parser('replay'); p.add_argument('--case',choices=SCENARIOS,required=True)
    p.add_argument('--at',type=int,choices=CUTS,default=128)
    args=parser.parse_args(argv)
    try:
        if args.action=='check': result=check()
        elif args.action=='report':
            data=report();result={'summary':data['summary'],'report_sha256':data['report_sha256']}
        else:
            full=stream(args.case)
            issued=issue_at(prefix(full,args.at),args.at)
            if args.action=='issue':
                print(expression(issued)); return 0
            result={'issued':issued,'settled':settle(issued, full)}
        print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        return 0
    except (SelectionError, v30.WorkloadError, v31.CalibrationError, v29.AdaptiveError,
            ValueError, OSError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
