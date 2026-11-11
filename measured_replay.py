"""ALCG v0.27: empirical timing of the CURRENT fully verified v0.26 reader.

Latency results are observational and environment-dependent. No lazy-checkpoint
speedup is implied: v0.26 access_state always verifies/replays the entire run.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time
from typing import Any, Callable

import checkpoint_planner as v26
import selective_delta as v25
import session_language as v23
import trace_language as v22

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-v0.27-measured-verified-replay'
REPORT_PATH = ROOT / 'reports' / 'measured-replay-v0.27.json'
DOC_PATH = ROOT / 'docs' / 'MEASURED-REPLAY-v0.27.md'
MAX_REPEATS = 25
PROFILES = ('cold_archive', 'hot_tail', 'mixed_reads', 'storage_limited', 'bounded_latency')


class MeasurementError(ValueError):
    """Invalid measured-replay fixture, receipt or benchmark configuration."""


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _source_hashes() -> dict[str, str]:
    v26._check_pins()
    return {name: _sha((ROOT / name).read_bytes()) for name in (
        'alcg.py', 'trace_language.py', 'session_language.py', 'delta_language.py',
        'selective_delta.py', 'checkpoint_planner.py',
        'data/linked-sessions-v0.23.json',
        'data/checkpoint-profiles-v0.26.json',
    )}


def _session(run_id: str) -> v23.Session:
    try:
        return next(s for s in v26._sessions() if s.id == run_id)
    except StopIteration as exc:
        raise MeasurementError('unknown fixed synthetic session') from exc


def representations(s: v23.Session) -> list[dict[str, Any]]:
    """Compare the *exact same verified state* across three frozen encodings."""
    n = len(s.rounds)
    choices = [
        ('selective', [], v25.encode(s)),
        ('hybrid_final', [n], v26.encode_hybrid(s, (n,))),
        ('full', list(range(n + 1)), v23.encode(s)),
    ]
    return [{'mode': mode, 'checkpoints': locations, 'expression': expr,
             'utf8_bytes': len(expr.encode('utf-8')),
             'expression_sha256': _sha(expr.encode('utf-8'))}
            for mode, locations, expr in choices]


def _check_nonnegative(value: Any, label: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise MeasurementError(label + ' must be a ' + ('positive' if positive else 'nonnegative') + ' integer')
    return value


def _profile_reads(s: v23.Session, profile: str) -> tuple[int, ...]:
    if profile not in PROFILES:
        raise MeasurementError('unsupported profile')
    return v26.profiles(s)[profile].reads


def evaluate_choices(rows: list[dict[str, Any]], reads: tuple[int, ...],
                     byte_price_ns: int) -> dict[str, Any]:
    """Minimize measured-time proxy + explicitly assumed storage byte price.

    The price is NOT a calibrated real storage monetary cost; it merely sets a
    sensitivity scenario expressed in nanosecond-equivalent score units.
    """
    _check_nonnegative(byte_price_ns, 'byte_price_ns')
    if not isinstance(reads, tuple) or not reads or any(type(x) is not int or x < 0 for x in reads):
        raise MeasurementError('reads must be nonnegative integer tuple')
    scored = []
    for row in rows:
        medians = row['median_ns_by_state']
        if len(medians) != len(reads):
            raise MeasurementError('workload has wrong number of states')
        timing = sum(a * b for a, b in zip(reads, medians))
        storage = row['utf8_bytes'] * byte_price_ns
        scored.append({'mode': row['mode'], 'utf8_bytes': row['utf8_bytes'],
                       'weighted_latency_ns': timing,
                       'storage_charge_ns_equivalent': storage,
                       'score_ns_equivalent': timing + storage})
    sorted_rows = sorted(scored, key=lambda x:(x['score_ns_equivalent'], x['utf8_bytes'], x['mode']))
    return {'reads_per_state': list(reads), 'byte_price_ns_equivalent': byte_price_ns,
            'evaluated': sorted_rows, 'selected_mode': sorted_rows[0]['mode']}


def measure(run_id: str = 'R23_TWO_ROUNDS', *, repetitions: int = 3,
            warmups: int = 1, profile: str = 'hot_tail',
            byte_price_ns: int = 1000, seed: int = 27027,
            clock: Callable[[], int] = time.perf_counter_ns,
            reader: Callable[[str, int], str] = v26.access_state) -> dict[str, Any]:
    """Measure warm-process, fully verified access_state; NO performance assertions.

    All encodings access identical states. Balanced shuffled blocks mitigate,
    but cannot remove, CPU frequency, OS load and Python-cache interference.
    """
    _check_nonnegative(repetitions, 'repetitions', positive=True)
    if repetitions > MAX_REPEATS:
        raise MeasurementError('repetitions exceed bounded limit')
    _check_nonnegative(warmups, 'warmups')
    if warmups > MAX_REPEATS:
        raise MeasurementError('warmups exceed bounded limit')
    _check_nonnegative(byte_price_ns, 'byte_price_ns')
    _check_nonnegative(seed, 'seed')
    s = _session(run_id)
    reads = _profile_reads(s, profile)
    choices = representations(s)
    names = [choice['mode'] for choice in choices]
    if len(set(names)) != 3:
        raise MeasurementError('duplicate representation mode')
    reference = [v22.encode(v26._state(s, i)) for i in range(len(s.rounds) + 1)]
    # A timed call must be a real fully verified read, *not* a direct checkpoint peek.
    for c in choices:
        if v26.decode(c['expression']) != s:
            raise MeasurementError('candidate failed verified full-session decode')
    trial_keys = [(m, i) for m in range(len(choices)) for i in range(len(reference))]
    samples: list[list[list[int]]] = [
        [[] for _ in reference] for _ in choices
    ]
    rng = random.Random(seed)
    for trial in range(warmups + repetitions):
        indices = list(trial_keys)
        rng.shuffle(indices)
        for mode_id, state_id in indices:
            source = choices[mode_id]['expression']
            start = clock()
            result = reader(source, state_id)
            end = clock()
            if result != reference[state_id]:
                raise MeasurementError('verified state differs from canonical trace')
            dt = end - start
            if type(dt) is not int or dt <= 0:
                raise MeasurementError('nonpositive or invalid monotonic timer delta')
            if trial >= warmups:
                samples[mode_id][state_id].append(dt)
    rows: list[dict[str, Any]] = []
    for i,c in enumerate(choices):
        by_state = samples[i]
        medians = [statistics.median_low(times) for times in by_state]
        rows.append({'mode':c['mode'], 'checkpoints':c['checkpoints'],
                     'utf8_bytes':c['utf8_bytes'],
                     'expression_sha256':c['expression_sha256'],
                     'sample_ns_by_state':by_state,
                     'median_ns_by_state':medians})
    decision = evaluate_choices(rows, reads, byte_price_ns)
    v26_modeled = v26.choose(s, v26.profiles(s)[profile])
    report: dict[str, Any] = {
        'format':FORMAT,
        'kind':'environment-specific experimental timing; not a universal benchmark',
        'clock':'time.perf_counter_ns; elapsed ns per fully verified state access',
        'reader':'checkpoint_planner.access_state (decode and validate whole history on EVERY read)',
        'session_id':s.id, 'rounds':len(s.rounds), 'profile':profile,
        'source_v023_sha256':_sha(v23.encode(s).encode('utf-8')),
        'source_fingerprints':_source_hashes(),
        'python_version':platform.python_version(),
        'os':platform.system(), 'machine':platform.machine(),
        'repetitions':repetitions, 'warmup_blocks':warmups, 'shuffle_seed':seed,
        'measurement_start_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'results':rows, 'observed_scenario':decision,
        'v026_abstract_planner':{'mode':v26_modeled.mode, 'checkpoints':list(v26_modeled.checkpoints),
                                 'modeled_replay_units':v26_modeled.read_work_units},
        'notes':['All candidates use complete full-chain verification per timed access.',
                 'Saved checkpoints currently do not enable lazy state retrieval.',
                 'The assumed byte-price is not a real market cost or CPU time.',
                 'No-independent-AI-semantic-reader and no physical sensor are involved.',
                 'Small fixture and process-local caches limit generalizability.'],
    }
    report['receipt_sha256']=_sha(_canonical(report))
    return report


def verify_report(record: dict[str, Any], *, enforce_source_pins: bool=True) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise MeasurementError('expected a JSON object')
    receipt = record.get('receipt_sha256')
    if type(receipt) is not str or len(receipt)!=64:
        raise MeasurementError('missing report digest')
    payload=dict(record)
    del payload['receipt_sha256']
    if receipt != _sha(_canonical(payload)):
        raise MeasurementError('report content changed since receipt was computed')
    if record.get('format') != FORMAT or record.get('reader') != 'checkpoint_planner.access_state (decode and validate whole history on EVERY read)':
        raise MeasurementError('unsupported format / reader semantics')
    s=_session(record.get('session_id'))
    if record.get('rounds') != len(s.rounds) or record.get('source_v023_sha256') != _sha(v23.encode(s).encode('utf-8')):
        raise MeasurementError('source session mismatch')
    if enforce_source_pins and record.get('source_fingerprints') != _source_hashes():
        raise MeasurementError('source fingerprints do not match installed code')
    count=_check_nonnegative(record.get('repetitions'), 'repetitions', positive=True)
    if count>MAX_REPEATS:
        raise MeasurementError('too many repetitions')
    _check_nonnegative(record.get('warmup_blocks'),'warmup_blocks')
    _check_nonnegative(record.get('shuffle_seed'),'shuffle_seed')
    profile=record.get('profile')
    reads=_profile_reads(s,profile)
    reference=representations(s)
    rows=record.get('results')
    if not isinstance(rows,list) or len(rows)!=len(reference):
        raise MeasurementError('missing benchmark alternatives')
    for row,source in zip(rows,reference):
        for key in ('mode','checkpoints','utf8_bytes','expression_sha256'):
            if row.get(key)!=source[key]:
                raise MeasurementError('candidate identity or storage bytes changed: '+key)
        samples=row.get('sample_ns_by_state')
        medians=row.get('median_ns_by_state')
        if not isinstance(samples,list) or len(samples)!=len(reads):
            raise MeasurementError('wrong number of states')
        if not isinstance(medians,list) or len(medians)!=len(reads):
            raise MeasurementError('missing medians')
        for times,median in zip(samples,medians):
            if not isinstance(times,list) or len(times)!=count or any(type(t) is not int or t<=0 for t in times):
                raise MeasurementError('malformed timing observations')
            if median != statistics.median_low(times):
                raise MeasurementError('median does not match raw observations')
    scenario=record.get('observed_scenario')
    if not isinstance(scenario,dict):
        raise MeasurementError('missing scenario')
    byte_price=_check_nonnegative(scenario.get('byte_price_ns_equivalent'),'byte_price_ns_equivalent')
    if scenario != evaluate_choices(rows, reads,byte_price):
        raise MeasurementError('measured cost comparison inconsistent')
    baseline=v26.choose(s,v26.profiles(s)[profile])
    if record.get('v026_abstract_planner')!={'mode':baseline.mode,
           'checkpoints':list(baseline.checkpoints),
           'modeled_replay_units':baseline.read_work_units}:
        raise MeasurementError('old-model baseline does not match')
    return {'checked':True,'session_id':s.id,'modes':len(rows),'states':len(reads),
            'repetitions':count,'measured_selected_mode':scenario['selected_mode'],
            'old_model_selected_mode':baseline.mode,
            'claim':'report integrity, not timing reproducibility or authentication'}


def load_verified(path: Path) -> dict[str, Any]:
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        verify_report(data)
        return data
    except (OSError, json.JSONDecodeError, v26.CheckpointError,
            v25.SelectionError,v23.SessionError,ValueError) as exc:
        raise MeasurementError(str(exc)) from exc


def check() -> dict[str, Any]:
    return verify_report(json.loads(REPORT_PATH.read_text(encoding='utf-8')))


def main(argv: list[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description='ALCG v0.27 real-clock replay laboratory')
    cmd=parser.add_subparsers(dest='command',required=True)
    bench=cmd.add_parser('bench',help='measure LOCAL CPU time (not run in CI)')
    bench.add_argument('--session',default='R23_TWO_ROUNDS',choices=[s.id for s in v26._sessions()])
    bench.add_argument('--profile',default='hot_tail',choices=PROFILES)
    bench.add_argument('--repeats',default=3,type=int)
    bench.add_argument('--warmups',default=1,type=int)
    bench.add_argument('--byte-price-ns',default=1000,type=int)
    bench.add_argument('--seed',default=27027,type=int)
    bench.add_argument('--output',type=Path,help='optional UTF-8 JSON report location')
    cmd.add_parser('check',help='audit committed measured sample WITHOUT expecting the same ns')
    rec=cmd.add_parser('recommend',help='re-score recorded samples under another declared workload')
    rec.add_argument('report',nargs='?',type=Path,default=REPORT_PATH)
    rec.add_argument('--profile',default='mixed_reads',choices=PROFILES)
    rec.add_argument('--byte-price-ns',default=1000,type=int)
    args=parser.parse_args(argv)
    try:
        if args.command=='bench':
            record=measure(args.session,repetitions=args.repeats,warmups=args.warmups,
                           profile=args.profile,byte_price_ns=args.byte_price_ns,
                           seed=args.seed)
            verify_report(record)
            output=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
            if args.output:
                # Generated runtime timing is deliberately not allowed to overwrite
                # committed source, fixtures, dictionaries or prior research.
                safe_dir = (ROOT / '.local').resolve()
                dest = args.output.resolve()
                if safe_dir not in dest.parents:
                    raise MeasurementError('benchmark output must be inside .local/')
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(output,encoding='utf-8')
                print('Wrote locally measured timing report:',args.output)
            else:
                print(output,end='')
        elif args.command=='check':
            print(json.dumps(check(),ensure_ascii=False,indent=2,sort_keys=True))
        else:
            record=load_verified(args.report)
            s=_session(record['session_id'])
            choice=evaluate_choices(record['results'], _profile_reads(s,args.profile),args.byte_price_ns)
            print(json.dumps({'basis':'observed per-state warm-process timings + explicit byte price',
                              'session':s.id,'profile':args.profile,'scenario':choice},
                             indent=2,sort_keys=True))
        return 0
    except (MeasurementError, v26.CheckpointError, OSError,ValueError) as exc:
        print('ERROR:',str(exc),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
