"""ALCG v0.30: prefix-only workload observations for cache admission.

The pinned timings are v0.28 local measurements. The checked-in event stream is
DETERMINISTIC AND SYNTHETIC; actual event collection requires calling
ObservedCacheReader in a trusted process. No plaintext/source hashes in exports.
No claim of reliable real-world prediction or independent AI understanding.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from threading import RLock
from typing import Any

import adaptive_cache as v29
import checkpoint_planner as v26
import measured_replay as v27
import trusted_cache as v28

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-v0.30-prefix-only-workload-observation'
FIXTURE_PATH = ROOT / 'data/workload-events-v0.30.json'
REPORT_PATH = ROOT / 'reports/workload-estimation-v0.30.json'
WINDOW = 32  # last 32 explicit opportunities, including IDLEs
HORIZON = 64  # forecast next 64 explicit opportunities, NOT wall-clock time
MIN_READS = 8
MIN_GAPS = 7
MAX_EVENTS = 4096
PRIOR_RESET = 1  # explicit synthetic Beta(1,19) prior, not empirically calibrated
PRIOR_TOTAL = 20
MAX_SOURCE_BYTES = v28.MAX_SOURCE_BYTES


class WorkloadError(ValueError):
    """Malformed log, unsupported request, or invalid forecast."""


class WorkloadEnvironmentChanged(WorkloadError):
    """Monitored code/models changed; this reader cannot be reused."""


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _integer(value: Any, name: str, *, start: int, end: int) -> int:
    if type(value) is not int or not start <= value <= end:
        raise WorkloadError(f'{name} must be an integer in [{start}, {end}]')
    return value


def document(label: str, origin: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Export only event flags and logical ticks; no source bytes or IDs."""
    data = {'format': FORMAT, 'label': label, 'origin': origin,
            'opportunity_unit': 'one explicit read-or-idle event (not real time)',
            'events': events}
    data['receipt_sha256'] = _sha(_canonical(data))
    validate_document(data)
    return data


def validate_document(data: Any) -> None:
    if not isinstance(data, dict) or set(data) != {
            'format', 'label', 'origin', 'opportunity_unit', 'events', 'receipt_sha256'}:
        raise WorkloadError('unknown or missing event-log fields')
    if data['format'] != FORMAT or data['origin'] not in {
            'synthetic-fixture', 'instrumented-process'} or data['opportunity_unit'] != (
            'one explicit read-or-idle event (not real time)'):
        raise WorkloadError('unsupported event-log origin or clock basis')
    if type(data['label']) is not str or not data['label'].isascii() or not (
            1 <= len(data['label']) <= 50) or not all(
            c.isalnum() or c in '_-' for c in data['label']):
        raise WorkloadError('label must be a short anonymous ASCII identifier')
    events = data['events']
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise WorkloadError('event log must be bounded')
    seen_read = False
    for index, event in enumerate(events):
        if not isinstance(event, dict) or type(event.get('tick')) is not int or event['tick'] != index:
            raise WorkloadError('logical ticks must be consecutive and unambiguous')
        kind = event.get('kind')
        if kind == 'idle':
            if set(event) != {'tick', 'kind'}:
                raise WorkloadError('idle events cannot carry a source or outcome')
        elif kind == 'read':
            if set(event) != {'tick','kind','revision_changed','route'} or type(
                    event['revision_changed']) is not bool or event['route'] not in (
                    'direct', 'cache', 'not-executed'):
                raise WorkloadError('read events may contain only boolean change and route')
            if not seen_read and event['revision_changed']:
                raise WorkloadError('first observed read has no prior revision to compare')
            seen_read = True
        else:
            raise WorkloadError('unknown event kind')
    receipt = data['receipt_sha256']
    if type(receipt) is not str or receipt != _sha(_canonical(
            {key:value for key,value in data.items() if key != 'receipt_sha256'})):
        raise WorkloadError('log receipt checksum mismatch')


def synthetic_events(kind: str, n: int = 96) -> list[dict[str, Any]]:
    """Deterministic scenarios, NOT records of actual production traffic."""
    if kind not in {'stable', 'churn', 'sparse', 'drift'}:
        raise WorkloadError('unknown synthetic scenario')
    _integer(n, 'n', start=32, end=MAX_EVENTS)
    rows: list[dict[str, Any]] = []
    seen = False
    for tick in range(n):
        read = kind != 'sparse' or tick % 12 == 0
        if kind == 'stable' and tick < 32:
            read = tick % 4 == 0
        if not read:
            rows.append({'tick':tick,'kind':'idle'})
            continue
        changed = seen and (
            kind == 'churn' and tick % 2 == 0 or
            kind == 'drift' and tick >= 64 and tick % 2 == 0)
        rows.append({'tick':tick,'kind':'read','revision_changed':bool(changed),
                     'route':'not-executed'})
        seen = True
    return rows


def read_fixture() -> dict[str, Any]:
    data = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'format', 'scenarios'} or data['format'] != FORMAT:
        raise WorkloadError('invalid synthetic fixture container')
    scenarios = data['scenarios']
    if not isinstance(scenarios, list) or [s.get('label') for s in scenarios] != [
            'stable', 'churn', 'sparse', 'drift']:
        raise WorkloadError('unrecognized synthetic scenario inventory')
    for x in scenarios:
        validate_document(x)
        if x['origin'] != 'synthetic-fixture' or x['events'] != synthetic_events(x['label']):
            raise WorkloadError('fixture is not the canonical deterministic sequence')
    return data


def measurement_rows() -> dict[str, dict[str, Any]]:
    evidence = v29.measured_evidence()
    return {row['mode']: row for row in evidence['measurements']}


def forecast(data: dict[str, Any], at_tick: int, *, row: dict[str, Any],
             window: int = WINDOW, horizon: int = HORIZON) -> dict[str, Any]:
    """Make an admission decision solely from events before at_tick.

    Fixed Beta(1,19) smoothing on per-READ gaps prevents zero observed resets
    from being interpreted as proof of a zero future change probability.
    Reads per future *opportunity* use smoothed Beta(1,1) read rate.
    """
    validate_document(data)
    _integer(at_tick,'at_tick',start=0,end=len(data['events']))
    _integer(window,'window',start=8,end=MAX_EVENTS)
    _integer(horizon,'horizon',start=1,end=MAX_EVENTS)
    prefix = data['events'][:at_tick]
    recent = prefix[-window:]
    reads = [e for e in recent if e['kind'] == 'read']
    gaps = max(0,len(reads)-1)
    resets = sum(e['revision_changed'] for e in reads[1:])
    observed = {
        'at_tick':at_tick, 'window_opportunities':len(recent),
        'observed_reads':len(reads), 'observed_read_gaps':gaps,
        'observed_revision_changes':resets,
        'prefix_sha256':_sha(_canonical(prefix)),
        'prior':'Beta(1,19) reset-per-read-gap and Beta(1,1) read-per-opportunity',
    }
    if len(recent) < window or len(reads) < MIN_READS or gaps < MIN_GAPS:
        return {**observed, 'selection':'direct',
                'reason':'insufficient fully observed rolling window or read gaps',
                'forecast':None, 'decision':None}
    # Half-up rounding; using only the past window, not upcoming read count.
    estimate_reads = (horizon * (len(reads)+1) * 2 + (window+2)) // (2*(window+2))
    estimate_reads = min(v29.MAX_READS, max(1, estimate_reads))
    invalidations = (1_000_000 * (resets + PRIOR_RESET) * 2 + gaps + PRIOR_TOTAL) // (
        2 * (gaps + PRIOR_TOTAL))
    invalidations = min(1_000_000, invalidations)
    profile = {
        'expected_reads':estimate_reads,
        'invalidation_per_million':invalidations,
        'rebuild_penalty_ns':0,
        'retention_ns_per_read':0,
    }
    calc = v29.estimate(row, profile)
    return {**observed,'selection':calc['selection'],
            'reason':'prefix-only smoothed estimates evaluated with v0.28 pinned timing',
            'forecast':profile, 'decision':calc}


def report() -> dict[str, Any]:
    fixture = read_fixture()
    rows = measurement_rows()
    cases = []
    for case in fixture['scenarios']:
        for at_tick in (16, 32, 64, 96):
            outcome = forecast(case, at_tick, row=rows['selective'])
            cases.append({'case':case['label'], **outcome})
    doc = {
        'format':FORMAT, 'fixture':'deterministic synthetic opportunity event streams',
        'cost_evidence':'pinned v0.28 single-host medians, NOT live remeasurement',
        'window_opportunities':WINDOW, 'forecast_horizon_opportunities':HORIZON,
        'cases':cases,
        'limitations':[
            'one explicitly recorded opportunity per tick, not clock time',
            'synthetic inputs do not establish actual user source-change rates',
            'fixed uncalibrated Bayesian prior and stationary extrapolation may be wrong',
            'no lookahead, no real-world cache speed or AI semantic comprehension score',
            'cold starts and unknown source formats always use full verification',
            'SHA-256 is an integrity check, not authentication',
        ],
    }
    doc['receipt_sha256'] = _sha(_canonical(doc))
    return doc


def verify_report(data: Any) -> bool:
    if not isinstance(data, dict) or data != report():
        raise WorkloadError('the fixed report does not match the pinned fixture and evidence')
    return True


class ObservedCacheReader:
    """Opt-in in-process instrumentation and conservative dynamic admission.

    One source stream: source revisions are exact source-text changes, and IDLE
    opportunities must be provided explicitly. Outputs never contain the source
    text or a source fingerprint. This does not authenticate callers or logs.
    """
    def __init__(self, *, label: str = 'local', max_entries: int = 2):
        self._lock = RLock()
        self._events: list[dict[str, Any]] = []
        self._label = label
        self._last_source: str | None = None
        self._cache = v28.VerifiedStateCache(max_entries=max_entries)
        self._known = {}
        evidence = v29.measured_evidence()
        session = v27._session(evidence['session_id'])
        for representation, timing in zip(v27.representations(session), evidence['measurements']):
            if representation['expression_sha256'] != timing['source_sha256']:
                raise WorkloadError('historical timing case does not match source')
            self._known[representation['expression']] = timing
        self._dependencies = self._manifest()
        self._blocked = False
        self.cached_reads = self.direct_reads = self.source_invalidations = 0
        document(label, 'instrumented-process', [])  # Validate label on construction.

    @staticmethod
    def _manifest() -> dict[str, str]:
        try:
            result = v28.source_manifest()
            for p in ('adaptive_cache.py', 'workload_estimator.py',
                      'reports/trusted-cache-v0.28.json'):
                result[p] = _sha((ROOT/p).read_bytes())
            return result
        except OSError as exc:
            raise WorkloadEnvironmentChanged('required dependency disappeared') from exc

    def _check_environment(self) -> None:
        if self._blocked:
            raise WorkloadEnvironmentChanged('this reader was invalidated; construct another')
        try:
            current = self._manifest()
        except WorkloadEnvironmentChanged:
            self._blocked = True
            self._cache.clear()
            raise
        if self._dependencies != current:
            self._blocked = True
            self._cache.clear()
            raise WorkloadEnvironmentChanged('model or policy files changed, refusing access')

    def idle(self) -> None:
        with self._lock:
            self._check_environment()
            if len(self._events) >= MAX_EVENTS:
                raise WorkloadError('event capacity exceeded')
            self._events.append({'tick':len(self._events),'kind':'idle'})

    def read(self, source: str, index: int) -> str:
        with self._lock:
            self._check_environment()
            if len(self._events) >= MAX_EVENTS:
                raise WorkloadError('event capacity exceeded')
            v28.VerifiedStateCache._source_key(source)
            if type(index) is not int or index < 0:
                raise WorkloadError('state index must be a nonnegative integer')
            changed = self._last_source is not None and self._last_source != source
            if changed:
                # Conservative cache purge before attempting the new revision.
                self._cache.clear()
            row = self._known.get(source)
            past = self.export()
            choice = (forecast(past, len(self._events), row=row) if row is not None
                      else {'selection':'direct', 'reason':'unknown exact source'})
            if choice['selection'] == 'cache':
                output = self._cache.read(source, index)
                route = 'cache'
            else:
                try:
                    output = v26.access_state(source,index)
                except (v26.CheckpointError,ValueError,OSError,RecursionError) as exc:
                    raise WorkloadError('fresh direct verification failed: '+str(exc)) from exc
                route = 'direct'
            self._check_environment()  # fail closed if changed during the read
            self._last_source = source
            if changed:
                self.source_invalidations += 1
            self._events.append({'tick':len(self._events),'kind':'read',
                                 'revision_changed':bool(changed), 'route':route})
            if route == 'cache':
                self.cached_reads += 1
            else:
                self.direct_reads += 1
            return output

    def export(self) -> dict[str, Any]:
        with self._lock:
            return document(self._label, 'instrumented-process',
                            [dict(event) for event in self._events])

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {'direct_reads':self.direct_reads,'cached_reads':self.cached_reads,
                    'source_invalidations':self.source_invalidations,
                    'observed_opportunities':len(self._events),
                    'cache':self._cache.stats()}


def check() -> dict[str, Any]:
    saved = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    verify_report(saved)
    rows = measurement_rows()
    fixture = read_fixture()
    stable = next(d for d in fixture['scenarios'] if d['label']=='stable')
    drift = next(d for d in fixture['scenarios'] if d['label']=='drift')
    s = forecast(stable, 96, row=rows['selective'])
    d = forecast(drift, 96, row=rows['selective'])
    if s['selection'] != 'cache' or d['selection'] != 'direct':
        raise WorkloadError('expected stable/cache and drift/direct demo contrast')
    return {'status':'PASS', 'case_count':len(saved['cases']),
            'stable_latest_route':s['selection'],'drift_latest_route':d['selection'],
            'warning':'synthetic fixture, not observed production workload'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='ALCG v0.30 bounded prefix-only workload observation')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('check')
    sub.add_parser('report')
    plan = sub.add_parser('predict')
    plan.add_argument('--case', choices=('stable','churn','sparse','drift'),required=True)
    plan.add_argument('--at', type=int, choices=(16,32,64,96),default=96)
    plan.add_argument('--mode', choices=('selective','hybrid_final','full'),default='selective')
    args = parser.parse_args(argv)
    try:
        if args.action == 'check':
            value = check()
        elif args.action == 'report':
            value = report()
        else:
            fixture = read_fixture()
            stream = next(x for x in fixture['scenarios'] if x['label']==args.case)
            value = forecast(stream,args.at,row=measurement_rows()[args.mode])
        print(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True))
        return 0
    except (WorkloadError, v28.CacheError, v29.AdaptiveError, OSError, ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
