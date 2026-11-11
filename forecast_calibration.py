"""ALCG v0.31: frozen-prefix forecasts, prequential calibration and retrospective cost audit.

This module measures deterministic SYNTHETIC fixtures from v0.30, never
production traffic or independent AI understanding. It distinguishes issuance,
after-the-fact scoring, and optional calibration trained only on closed windows.
All probability and cost arithmetic is exact Fraction arithmetic.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import adaptive_cache as v29
import alcg
import workload_estimator as v30

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-v0.31-prequential-workload-calibration'
CONFIG_PATH = ROOT / 'data/forecast-calibration-v0.31.json'
REPORT_PATH = ROOT / 'reports/forecast-calibration-v0.31.json'
SAMPLE_PATH = ROOT / 'samples/forecast-audits-v0.31.alcg'
CUTS = (32, 64)
HORIZON = 32
CALIBRATION_WEIGHT = 16
MODES = ('selective', 'hybrid_final', 'full')


class CalibrationError(ValueError):
    """Unsupported forecast, changed fixture, or invalid assessment."""


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(obj: Any) -> str:
    return sha256(canonical(obj)).hexdigest()


def exact(x: Fraction | int) -> dict[str, int]:
    f = Fraction(x)
    return {'num':f.numerator, 'den':f.denominator}


def frac(obj: dict[str, int]) -> Fraction:
    if not isinstance(obj, dict) or set(obj) != {'num', 'den'} or any(
            type(v) is not int for v in obj.values()) or obj['den'] <= 0:
        raise CalibrationError('invalid exact rational')
    return Fraction(obj['num'], obj['den'])


def round_half_up(x: Fraction) -> int:
    if x < 0:
        raise CalibrationError('negative probability or count')
    return (2 * x.numerator + x.denominator) // (2 * x.denominator)


def inputs() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    fixture = v30.read_fixture()
    rows = v30.measurement_rows()
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    wanted = {'format','source_events_sha256','source_timing_sha256','cuts',
              'horizon_opportunities','calibration_strength','modes'}
    if not isinstance(config, dict) or set(config) != wanted or config != {
            'format':FORMAT,
            'source_events_sha256':sha256(v30.FIXTURE_PATH.read_bytes()).hexdigest(),
            'source_timing_sha256':sha256(v29.SOURCE_REPORT_PATH.read_bytes()).hexdigest(),
            'cuts':list(CUTS),'horizon_opportunities':HORIZON,
            'calibration_strength':CALIBRATION_WEIGHT,'modes':list(MODES)}:
        raise CalibrationError('v0.31 pinned configuration or dependency fingerprint mismatch')
    return config, fixture['scenarios'], rows


def issue(stream: dict[str, Any], at_tick: int, *, mode: str = 'selective',
          row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Freeze a forecast without consulting any future event in the stream."""
    # Deliberately construct and validate a PREFIX-ONLY document. A caller may
    # pass only events[:at_tick]; no future event, receipt, or length is needed.
    if not isinstance(stream, dict) or not isinstance(stream.get('events'), list):
        raise CalibrationError('stream must contain an event sequence')
    if at_tick not in CUTS or len(stream['events']) < at_tick:
        raise CalibrationError('not enough past events for requested cut')
    if mode not in MODES:
        raise CalibrationError('unknown timing mode')
    prefix_stream = v30.document(stream.get('label'), stream.get('origin'),
                                 stream['events'][:at_tick])
    row = v30.measurement_rows()[mode] if row is None else row
    predicted = v30.forecast(prefix_stream, at_tick, row=row, horizon=HORIZON)
    body = {
        'format':FORMAT, 'kind':'ISSUE', 'scenario':stream['label'],
        'source_origin':stream['origin'], 'at_tick':at_tick,
        'horizon':HORIZON, 'mode':mode,
        'timing_source_sha256':row['source_sha256'],
        'forecast':predicted,
    }
    return {**body,'issue_sha256':digest(body)}


def ensure_issue(record: dict[str, Any], stream: dict[str, Any],
                 row: dict[str, Any]) -> None:
    if (not isinstance(record, dict) or set(record) != {
            'format','kind','scenario','source_origin','at_tick','horizon','mode',
            'timing_source_sha256','forecast','issue_sha256'}):
        raise CalibrationError('unknown issuance fields')
    if record['issue_sha256'] != digest({k:v for k,v in record.items() if k != 'issue_sha256'}):
        raise CalibrationError('forecast issuance fingerprint mismatch')
    expected = issue(stream, record['at_tick'], mode=record['mode'], row=row)
    if record != expected:
        raise CalibrationError('issued forecast differs from time-cut prefix')


def truth(stream: dict[str, Any], at_tick: int) -> dict[str, Any]:
    """Holdout is consulted only at settlement, never at issuance."""
    v30.validate_document(stream)
    end = at_tick + HORIZON
    if at_tick not in CUTS or end > len(stream['events']):
        raise CalibrationError('holdout interval not available')
    future = stream['events'][at_tick:end]
    reads = [e for e in future if e['kind'] == 'read']
    # v0.30 reset rate is defined on successive READ pairs inside a window.
    # Excluding the first future read keeps the numerator/denominator aligned.
    resets = sum(e['revision_changed'] for e in reads[1:])
    return {'start_tick':at_tick,'end_tick':end, 'opportunities':len(future),
            'reads':len(reads),'read_gaps':max(0,len(reads)-1),
            'revision_changes_internal':resets, 'future_receipt_sha256':digest(future)}


def baseline_rates(forecast: dict[str, Any]) -> tuple[Fraction, Fraction] | None:
    if forecast['forecast'] is None:
        return None
    n = forecast['observed_reads']
    w = forecast['window_opportunities']
    gaps = forecast['observed_read_gaps']
    resets = forecast['observed_revision_changes']
    return Fraction(n+1, w+2), Fraction(resets+v30.PRIOR_RESET, gaps+v30.PRIOR_TOTAL)


def brier(p: Fraction, ones: int, trials: int) -> Fraction | None:
    if not 0 <= p <= 1 or type(ones) is not int or type(trials) is not int or not 0 <= ones <= trials:
        raise CalibrationError('invalid Brier score input')
    if not trials:
        return None
    return (ones*(1-p)**2 + (trials-ones)*p**2)/trials


def calibrate(raw: tuple[Fraction, Fraction], prior: dict[str, Any]) -> tuple[Fraction, Fraction]:
    """Bounded shrinkage toward ONE earlier completed evaluation interval.

    This is a transparent demonstration of lagged correction, not a trained
    production calibrator nor a promise of improved future Brier scores.
    """
    if not isinstance(prior, dict) or not all(k in prior for k in ('reads','opportunities','read_gaps','revision_changes_internal')):
        raise CalibrationError('incomplete earlier realization')
    k = CALIBRATION_WEIGHT
    return (
        Fraction(k*raw[0]+prior['reads'], k+prior['opportunities']),
        Fraction(k*raw[1]+prior['revision_changes_internal'], k+prior['read_gaps']),
    )


def to_profile(rates: tuple[Fraction, Fraction]) -> dict[str, int]:
    p,q = rates
    if not (0 <= p <= 1 and 0 <= q <= 1):
        raise CalibrationError('invalid calibrated rates')
    return {'expected_reads':min(v29.MAX_READS,max(1,round_half_up(HORIZON*p))),
            'invalidation_per_million':min(1_000_000,round_half_up(1_000_000*q)),
            'rebuild_penalty_ns':0,'retention_ns_per_read':0}


def realized_costs(timing: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    """Counterfactual costs using PINNED historical local timing medians.

    This does NOT measure live elapsed time, production costs, or the actual
    v0.30 execution routes. Cold start at each evaluation interval.
    """
    n=outcome['reads']
    resets=outcome['revision_changes_internal']
    gaps=outcome['read_gaps']
    u=timing['uncached_median_ns'];cold=timing['cold_admission_ns'];hit=timing['cached_median_ns']
    if n==0:
        direct=cache=0
    else:
        direct=n*u
        cache=(1+resets)*cold+(gaps-resets)*hit
    oracle='cache' if cache<direct else 'direct'
    return {'direct_cost_ns':direct,'cache_cost_ns':cache,'oracle':oracle}


def settle(issued: dict[str, Any], stream: dict[str, Any], row: dict[str, Any],
           training: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score one frozen issuance. Training, if present, must be earlier and closed."""
    ensure_issue(issued,stream,row)
    actual=truth(stream,issued['at_tick'])
    calc = issued['forecast']
    raw=baseline_rates(calc)
    if training is not None:
        if (issued['at_tick'] != 64 or training.get('at_tick') != 32 or
                training.get('end_tick') != 64 or training.get('scenario') != stream['label'] or
                training.get('realization') != truth(stream,32) or
                training.get('issue_sha256') != issue(stream,32,mode=issued['mode'],row=row)['issue_sha256']):
            raise CalibrationError('calibration training is not a certified closed prior window')
    if raw is None:
        if training is not None:
            raise CalibrationError('cannot calibrate unsupported issuance')
        return {'issue':issued,'realization':actual,'status':'insufficient_prefix',
                'raw_scores':None,'calibrated_scores':None,'decision_audit':None,
                'calibration_training':None}

    def scores(rates: tuple[Fraction,Fraction]) -> dict[str,Any]:
        p,q=rates
        x=brier(p,actual['reads'],actual['opportunities'])
        y=brier(q,actual['revision_changes_internal'],actual['read_gaps'])
        return {'predicted_read_probability':exact(p),
                'predicted_reset_probability_per_read_gap':exact(q),
                'read_brier':exact(x), 'reset_brier':exact(y) if y is not None else None,
                'realized_read_frequency':exact(Fraction(actual['reads'],actual['opportunities'])),
                'realized_reset_frequency_per_gap':exact(Fraction(actual['revision_changes_internal'],actual['read_gaps'])) if actual['read_gaps'] else None}

    calibrated = calibrate(raw,training['realization']) if training is not None else None
    costs=realized_costs(row,actual)
    raw_route=calc['selection']
    cal_route=v29.estimate(row,to_profile(calibrated))['selection'] if calibrated is not None else None
    def regret(route:str)->int:
        chosen=costs['cache_cost_ns'] if route=='cache' else costs['direct_cost_ns']
        oracle=min(costs['cache_cost_ns'],costs['direct_cost_ns'])
        return chosen-oracle
    decision={'forecast_route':raw_route,'calibrated_route':cal_route,
              'realized_costs_pinned_ns':costs,
              'raw_regret_ns':regret(raw_route),
              'calibrated_regret_ns':regret(cal_route) if cal_route is not None else None}
    return {'issue':issued,'realization':actual,'status':'scored',
            'raw_scores':scores(raw),'calibrated_scores':scores(calibrated) if calibrated is not None else None,
            'decision_audit':decision,
            'calibration_training':{
                'issue_sha256':training['issue_sha256'],
                'realization_receipt_sha256':digest(training['realization'])
            } if training is not None else None}


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [r for r in records if r['status']=='scored']
    calibration = [r for r in scores if r['calibrated_scores'] is not None]
    def macro(rows:list[dict[str,Any]],name:str,which:str)->dict[str,int] | None:
        seq=[frac(r[which][name]) for r in rows if r[which] is not None and r[which][name] is not None]
        return exact(sum(seq,Fraction(0))/len(seq)) if seq else None
    return {
        'total_issued_scenario_windows':len(records),
        'scored_windows':len(scores),
        'insufficient_prefix_windows':len(records)-len(scores),
        'calibrated_holdouts':len(calibration),
        'raw_read_brier_macro':macro(scores,'read_brier','raw_scores'),
        'raw_reset_brier_macro':macro(scores,'reset_brier','raw_scores'),
        'holdout_raw_read_brier_macro':macro(calibration,'read_brier','raw_scores'),
        'holdout_calibrated_read_brier_macro':macro(calibration,'read_brier','calibrated_scores'),
        'holdout_raw_reset_brier_macro':macro(calibration,'reset_brier','raw_scores'),
        'holdout_calibrated_reset_brier_macro':macro(calibration,'reset_brier','calibrated_scores'),
    }


def report() -> dict[str, Any]:
    config,streams,rows=inputs()
    records=[];decision_rows=[]
    for stream in streams:
        for cut in CUTS:
            base=issue(stream,cut,row=rows['selective'])
            preceding=None
            if cut==64:
                prior=issue(stream,32,row=rows['selective'])
                if prior['forecast']['forecast'] is not None:
                    preceding={'scenario':stream['label'],'at_tick':32,'end_tick':64,
                               'issue_sha256':prior['issue_sha256'],'realization':truth(stream,32)}
            record=settle(base,stream,rows['selective'],training=preceding)
            records.append(record)
            for mode in MODES:
                issued=issue(stream,cut,mode=mode,row=rows[mode])
                training=None
                if cut==64 and preceding is not None:
                    prior=issue(stream,32,mode=mode,row=rows[mode])
                    training={**preceding,'issue_sha256':prior['issue_sha256']}
                audit=settle(issued,stream,rows[mode],training=training)
                decision_rows.append({'scenario':stream['label'],'cut':cut,'mode':mode,
                                      'decision':audit['decision_audit']})
    doc={'format':FORMAT,'source':'v0.30 four deterministic synthetic event streams',
         'source_report_timing':'v0.28 single-host pinned medians; counterfactual only',
         'method':'frozen prefix at 32/64, score next 32; lagged calibration from closed previous block',
         'config':config,'records':records,'mode_decisions':decision_rows,
         'summary':_summary(records),
         'limitations':[
             'Synthetic event streams are not real production traffic or AI comprehension.',
             'All forecasts issued before their next 32 events; holdouts never influence their own issuance.',
             'No data outside the completed [32,64) window calibrates the forecast at cut 64.',
             'The first read within each holdout is excluded from read-gap reset scoring.',
             'A Brier score evaluates declared predictive probabilities, not causal truth.',
             'Costs are counterfactual from one host\'s pinned v0.28 medians, not measured future latency.',
             'Previous future outcomes are legally available only after the earlier block closes.',
             'Calibration may worsen subsequent forecasts; do not equate tuning with improvement.',
             'Receipts are SHA-256 consistency checks, not origin authentication or signatures.',
         ]}
    doc['report_sha256']=digest(doc)
    return doc


def audit_expression(record: dict[str, Any]) -> str:
    """Render one POST-HOC evaluation as ordinary parseable ALCG syntax.

    This is a readable structure with explicit roles, not an executable new
    language operator or a claim of semantic comprehension by other models.
    """
    def name(v:str)->alcg.Name:
        return alcg.Name(v.upper().replace('-','_'))
    def string(v:Any)->alcg.String:
        return alcg.String(str(v))
    def call(n:str,**kwargs:alcg.Expr)->alcg.Call:
        return alcg.Call(n,tuple(kwargs.items()))
    issue_row=record['issue'];out=record['realization']
    pred=issue_row['forecast']['forecast']
    rs=record['raw_scores'];cs=record['calibrated_scores'];audit=record['decision_audit']
    def rv(x:dict[str,int]|None)->str:
        return 'NA' if x is None else f"{x['num']}/{x['den']}"
    node=call('AUDIT_V031',
        source=name('synthetic'), scenario=name(issue_row['scenario']),
        cut=string(issue_row['at_tick']),
        issuance=call('ISSUE_V031', receipt=string(issue_row['issue_sha256']),
                      route=name(issue_row['forecast']['selection']),
                      expected_reads=string(pred['expected_reads'] if pred else 'NA')),
        observation=call('OBSERVED_V031',reads=string(out['reads']),
                         resets=string(out['revision_changes_internal']),
                         horizon=string(out['opportunities']),receipt=string(out['future_receipt_sha256'])),
        feedback=call('FEEDBACK_V031',status=name(record['status']),
                      read_brier=string(rv(rs['read_brier']) if rs else 'NA'),
                      reset_brier=string(rv(rs['reset_brier']) if rs else 'NA'),
                      adjusted_reset_brier=string(rv(cs['reset_brier']) if cs else 'NA'),
                      adjusted_route=name(audit['calibrated_route']) if audit and audit['calibrated_route'] else name('not_applicable')))
    rendered=alcg.render(node)
    if alcg.parse(rendered)!=node:
        raise CalibrationError('ALCG post-hoc audit roundtrip failed')
    return rendered


def verify_audit_expression(expression:str,record:dict[str,Any])->bool:
    try:
        parsed=alcg.parse(expression)
        expected=alcg.parse(audit_expression(record))
        if parsed!=expected:
            raise CalibrationError('ALCG audit does not match the exact scored record')
    except alcg.ParseError as exc:
        raise CalibrationError('malformed ALCG audit expression') from exc
    return True


def check()->dict[str,Any]:
    stored=json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    live=report()
    if not isinstance(stored,dict) or stored!=live:
        raise CalibrationError('saved scoring report differs from deterministic, pinned recomputation')
    expected=[audit_expression(r) for r in live['records']]
    actual=[alcg.render(e) for e in alcg.read_expressions(SAMPLE_PATH)]
    if actual != expected:
        raise CalibrationError('ALCG post-hoc sample differs from pinned scored evidence')
    for line,record in zip(actual,live['records']):
        verify_audit_expression(line,record)
    s=live['summary']
    if s['total_issued_scenario_windows']!=8 or s['scored_windows']!=6 or s['calibrated_holdouts']!=3:
        raise CalibrationError('unexpected calibration trial coverage')
    return {'status':'PASS','issued':8,'scored':6,'calibrated':3,
            'report_sha256':live['report_sha256'],
            'warning':'synthetic retrospective scoring, not production accuracy'}


def main(argv: list[str]|None=None)->int:
    cli=argparse.ArgumentParser(description='ALCG v0.31 synthetic out-of-sample calibration and feedback')
    sub=cli.add_subparsers(dest='action',required=True)
    sub.add_parser('check');sub.add_parser('report')
    emit=sub.add_parser('emit');emit.add_argument('--case',choices=('stable','churn','sparse','drift'),required=True)
    emit.add_argument('--at',type=int,choices=CUTS,default=64)
    p=sub.add_parser('score');p.add_argument('--case',choices=('stable','churn','sparse','drift'),required=True)
    p.add_argument('--at',type=int,choices=CUTS,default=64)
    args=cli.parse_args(argv)
    try:
        if args.action=='check': out=check()
        else:
            doc=report()
            if args.action=='report': out={'summary':doc['summary'],'report_sha256':doc['report_sha256']}
            else: out=next(x for x in doc['records'] if x['issue']['scenario']==args.case and x['issue']['at_tick']==args.at)
        if args.action=='emit':print(audit_expression(out))
        else: print(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (CalibrationError,v30.WorkloadError,v29.AdaptiveError,OSError,ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':
    raise SystemExit(main())
