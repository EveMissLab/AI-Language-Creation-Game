"""ALCG v0.28: validated-once, process-local immutable state cache.

Trust boundary: one non-hostile Python process, exact source bytes and monitored
model/decoder source files. A hash is an integrity identifier, NOT authentication.
No disk persistence, remote cache import, or full-verification bypass on misses.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import platform
import statistics
import sys
from threading import RLock
from time import perf_counter_ns
from typing import Any

import checkpoint_planner as v26
import measured_replay as v27
import session_language as v23
import trace_language as v22

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-v0.28-verified-in-process-cache'
POLICY_PATH = ROOT / 'data/trusted-cache-policy-v0.28.json'
REPORT_PATH = ROOT / 'reports/trusted-cache-v0.28.json'
MAX_SOURCE_BYTES = 128_000
MAX_BENCH_REPEATS = 20
# Watch *bytes* of the live model, its historical rule code, and its scenario
# inputs. A changed file refuses further use of this reader until restart.
WATCH_FILES = (
    'alcg.py', 'trace_language.py', 'session_language.py',
    'delta_language.py', 'selective_delta.py', 'checkpoint_planner.py',
    'correlated_design.py', 'noisy_design.py', 'active_design.py',
    'data/linked-sessions-v0.23.json',
    'data/trace-cases-v0.22.json',
    'data/correlated-design-space-v0.21.json',
    'data/checkpoint-profiles-v0.26.json',
    'data/selective-profile-v0.25.json',
    'data/active-design-space-v0.19.json',
    'data/noisy-design-space-v0.20.json',
    'data/trusted-cache-policy-v0.28.json',
)


class CacheError(ValueError):
    """Invalid source, stale dependency, incorrect access, or corrupt cache."""


class CacheEnvironmentChanged(CacheError):
    """The loaded model/decoder environment changed; do not reuse cache."""


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def source_manifest() -> dict[str, str]:
    """Read monitored files on EVERY access, not just at cache admission."""
    try:
        return {name: _sha((ROOT / name).read_bytes()) for name in WATCH_FILES}
    except OSError as exc:
        raise CacheEnvironmentChanged('monitored model file unavailable') from exc


def _policy() -> dict[str, Any]:
    try:
        data = json.loads(POLICY_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CacheError('invalid cache policy file') from exc
    if (not isinstance(data, dict) or set(data) !=
            {'format','max_entries','max_source_bytes','persistence','source_check','trust_domain'}
            or data.get('format') != FORMAT
            or type(data.get('max_entries')) is not int or not 1 <= data['max_entries'] <= 16
            or data.get('max_source_bytes') != MAX_SOURCE_BYTES
            or data.get('persistence') != 'process-only'
            or data.get('source_check') != 'hash source and monitored model files on each read'
            or data.get('trust_domain') != 'non-hostile single process'):
        raise CacheError('unsupported cache policy')
    return data


@dataclass(frozen=True)
class _Entry:
    source: str
    source_sha256: str
    states: tuple[str, ...]
    states_sha256: tuple[str, ...]
    full_session: str
    full_sha256: str
    final_chain_sha256: str


class VerifiedStateCache:
    """Bounded LRU with verification once per *exact* canonical expression.

    A cache hit checks input bytes, dependency bytes, and returned snapshot bytes.
    It does NOT re-evaluate the model. It is safe only while this process, code,
    and dependencies remain in the assumed trusted execution boundary.
    """
    def __init__(self, max_entries: int | None = None):
        policy = _policy()
        limit = policy['max_entries'] if max_entries is None else max_entries
        if type(limit) is not int or not 1 <= limit <= 16:
            raise CacheError('max_entries must be an integer between 1 and 16')
        v26._check_pins()
        self.max_entries = limit
        self._lock = RLock()
        self._manifest = source_manifest()
        self._environment = _sha(_json_bytes(self._manifest))
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._hits = self._misses = self._admissions = 0
        self._evictions = self._invalidations = 0

    @property
    def environment_sha256(self) -> str:
        return self._environment

    def _check_environment(self) -> None:
        if source_manifest() != self._manifest:
            self._entries.clear()
            self._invalidations += 1
            raise CacheEnvironmentChanged('dependency bytes changed: cache invalidated; restart required')

    @staticmethod
    def _source_key(source: str) -> tuple[str, bytes]:
        if type(source) is not str or not source or len(source) > v26.MAX_CHARS:
            raise CacheError('source must be a nonempty bounded canonical ALCG string')
        try:
            raw = source.encode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise CacheError('source is not valid UTF-8') from exc
        if len(raw) > MAX_SOURCE_BYTES:
            raise CacheError('source exceeds byte-size limit')
        return _sha(raw), raw

    @staticmethod
    def _entry(source: str, key: str) -> _Entry:
        # Never trust the caller's claimed SHA-256 or previously serialized states.
        try:
            session = v26.decode(source)
            states = tuple(v22.encode(v26._state(session, i))
                           for i in range(len(session.rounds) + 1))
            full = v23.encode(session)
        except (v26.CheckpointError, v22.TraceError, v23.SessionError,
                ValueError, OSError, RecursionError) as exc:
            raise CacheError('fresh full verification failed: ' + str(exc)) from exc
        return _Entry(source, key, states,
                      tuple(_sha(s.encode('utf-8')) for s in states),
                      full, _sha(full.encode('utf-8')), session.final_chain_sha256)

    def _get(self, source: str) -> _Entry:
        key, _ = self._source_key(source)
        self._check_environment()
        hit = self._entries.get(key)
        if hit is not None:
            # A digest collision MUST NOT produce a silent incorrect cache hit.
            if hit.source != source or hit.source_sha256 != key:
                self._entries.clear()
                self._invalidations += 1
                raise CacheError('cache key/source identity collision')
            self._entries.move_to_end(key)
            self._hits += 1
            return hit
        self._misses += 1
        entry = self._entry(source, key)
        # Fail closed if model/source files changed during the full replay.
        self._check_environment()
        self._entries[key] = entry
        self._admissions += 1
        if len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
            self._evictions += 1
        return entry

    def read(self, source: str, index: int) -> str:
        """Return exact canonical v0.22 snapshot, once fully admitted."""
        if type(index) is not int or index < 0:
            raise CacheError('state index must be a nonnegative integer')
        with self._lock:
            entry = self._get(source)
            if index >= len(entry.states):
                raise CacheError('state index out of range')
            output = entry.states[index]
            if _sha(output.encode('utf-8')) != entry.states_sha256[index]:
                self._entries.clear()
                self._invalidations += 1
                raise CacheError('cached snapshot changed: cache invalidated')
            return output

    def expand(self, source: str) -> str:
        """Expand to byte-identical v0.23 RUN after initial verified admission."""
        with self._lock:
            entry = self._get(source)
            if _sha(entry.full_session.encode('utf-8')) != entry.full_sha256:
                self._entries.clear()
                self._invalidations += 1
                raise CacheError('cached canonical session changed')
            return entry.full_session

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._invalidations += 1

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {'hits':self._hits,'misses':self._misses,
                    'verified_admissions':self._admissions,
                    'evictions':self._evictions,'invalidations':self._invalidations,
                    'live_entries':len(self._entries)}


def benchmark(*, repeats: int = 5, session_id: str = 'R23_TWO_ROUNDS') -> dict[str, Any]:
    """Capture genuine warm-process time, never impose a fragile speed threshold."""
    if type(repeats) is not int or not 1 <= repeats <= MAX_BENCH_REPEATS:
        raise CacheError('repeats out of supported range')
    session = v27._session(session_id)
    end_index = len(session.rounds)
    expected = v22.encode(v26._state(session, end_index))
    measurements = []
    for row in v27.representations(session):
        src = row['expression']
        baseline = []
        for _ in range(repeats):
            t0 = perf_counter_ns()
            result = v26.access_state(src, end_index)
            t1 = perf_counter_ns()
            if result != expected:
                raise CacheError('uncached read returned wrong state')
            baseline.append(max(1, t1-t0))
        cache = VerifiedStateCache(max_entries=3)
        t0 = perf_counter_ns()
        result = cache.read(src, end_index)
        first_ns = max(1, perf_counter_ns()-t0)
        if result != expected:
            raise CacheError('first cached read returned wrong state')
        hits = []
        for _ in range(repeats):
            t0 = perf_counter_ns()
            result = cache.read(src, end_index)
            hits.append(max(1, perf_counter_ns()-t0))
            if result != expected:
                raise CacheError('cache hit returned wrong state')
        if cache.stats()['verified_admissions'] != 1 or cache.stats()['hits'] != repeats:
            raise CacheError('cache did not actually reuse one verified admission')
        measurements.append({
            'mode': row['mode'], 'utf8_bytes': row['utf8_bytes'],
            'source_sha256': row['expression_sha256'],
            'uncached_samples_ns': baseline,
            'uncached_median_ns': statistics.median_low(baseline),
            'cold_admission_ns': first_ns,
            'cached_samples_ns': hits,
            'cached_median_ns': statistics.median_low(hits),
            'verified_admissions': 1, 'cache_hits': repeats,
        })
    document = {
        'format': FORMAT, 'measurement':'time.perf_counter_ns, single local process',
        'session_id':session_id, 'rounds':end_index,
        'python_version':platform.python_version(), 'os':platform.system(),
        'mode_sequence':['selective','hybrid_final','full'],
        'repeats':repeats, 'model_environment_sha256': VerifiedStateCache().environment_sha256,
        'measurements':measurements,
        'limitations':['synthetic short histories, environment-specific timings',
                       'no cryptographic authenticity or cross-process trust',
                       'cached reads still hash source, snapshots and dependency files',
                       'non-hostile process assumption; no hostile concurrent file mutation guarantee',
                       'first access must fully validate all history'],
    }
    document['receipt_sha256'] = _sha(_json_bytes(document))
    return document


def verify_report(doc: dict[str, Any]) -> dict[str, Any]:
    """Verify recorded arithmetic and identity, not truth of timer measurements."""
    if not isinstance(doc, dict):
        raise CacheError('report is not an object')
    payload = {k:v for k,v in doc.items() if k!='receipt_sha256'}
    if doc.get('receipt_sha256') != _sha(_json_bytes(payload)):
        raise CacheError('report receipt mismatch')
    if doc.get('format') != FORMAT or doc.get('mode_sequence') != ['selective','hybrid_final','full']:
        raise CacheError('report schema mismatch')
    reps = doc.get('repeats')
    if type(reps) is not int or not 1 <= reps <= MAX_BENCH_REPEATS:
        raise CacheError('invalid repeat count')
    session = v27._session(doc.get('session_id'))
    if doc.get('rounds') != len(session.rounds):
        raise CacheError('round count mismatch')
    if doc.get('model_environment_sha256') != VerifiedStateCache().environment_sha256:
        raise CacheError('report belongs to different model environment')
    references = v27.representations(session)
    rows = doc.get('measurements')
    if not isinstance(rows, list) or len(rows) != len(references):
        raise CacheError('wrong number of report modes')
    for row, ref in zip(rows, references):
        for key, name in (('mode','mode'),('utf8_bytes','utf8_bytes'),
                          ('source_sha256','expression_sha256')):
            if row.get(key) != ref[name]:
                raise CacheError('recorded input identity mismatch')
        if row.get('verified_admissions') != 1 or row.get('cache_hits') != reps:
            raise CacheError('recorded cache counts inconsistent')
        for k, median_key in (('uncached_samples_ns','uncached_median_ns'),
                              ('cached_samples_ns','cached_median_ns')):
            times = row.get(k)
            if not isinstance(times,list) or len(times)!=reps or any(type(t) is not int or t<=0 for t in times):
                raise CacheError('malformed timing samples')
            if row.get(median_key)!=statistics.median_low(times):
                raise CacheError('medians do not match raw samples')
        if type(row.get('cold_admission_ns')) is not int or row['cold_admission_ns']<=0:
            raise CacheError('invalid first admission duration')
    return {'verified':True,'modes':len(rows),'repeats':reps,
            'claim':'recomputed report identity and arithmetic; timer values not independently attested'}


def check() -> dict[str, Any]:
    document = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    verified = verify_report(document)
    # Functional validation with real source replays; avoids volatile time budgets.
    session = v27._session(document['session_id'])
    cache = VerifiedStateCache()
    for row in v27.representations(session):
        for index in range(len(session.rounds)+1):
            expected = v22.encode(v26._state(session,index))
            if cache.read(row['expression'],index) != expected:
                raise CacheError('verified repeated read differs from canonical state')
            if cache.read(row['expression'],index) != expected:
                raise CacheError('repeated read differs from canonical state')
    return {**verified, 'cached_accesses':cache.stats(),
            'sample_note':'saved timing sample checked for internal consistency only'}


def _safe_destination(filename: str) -> Path:
    p = (Path.cwd()/filename).resolve()
    if p.suffix != '.json' or p == REPORT_PATH.resolve():
        raise CacheError('benchmark output must be JSON outside frozen report')
    project = ROOT.resolve()
    if project == p or project in p.parents:
        scratch = (project/'.local').resolve()
        if scratch not in p.parents:
            raise CacheError('write only under .local when inside repository')
    return p


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.28 verified-once state cache')
    sub = cli.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    p = sub.add_parser('bench')
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--session', default='R23_TWO_ROUNDS')
    p.add_argument('--output', default='.local/cache-benchmark-v0.28.json')
    p = sub.add_parser('read')
    p.add_argument('--session', default='R23_TWO_ROUNDS')
    p.add_argument('--mode', choices=('selective','hybrid_final','full'), default='selective')
    p.add_argument('--state', type=int, default=2)
    p.add_argument('--times', type=int, default=2)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            answer = check()
        elif args.command == 'bench':
            doc = benchmark(repeats=args.repeats,session_id=args.session)
            pth = _safe_destination(args.output)
            pth.parent.mkdir(parents=True,exist_ok=True)
            pth.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
            answer = {'output':str(pth),'verified':verify_report(doc)}
        else:
            if type(args.times) is not int or not 1 <= args.times <= 100:
                raise CacheError('times out of range')
            session = v27._session(args.session)
            expression = next(x['expression'] for x in v27.representations(session)
                              if x['mode']==args.mode)
            cache = VerifiedStateCache()
            results = [cache.read(expression,args.state) for _ in range(args.times)]
            answer = {'state_sha256':_sha(results[-1].encode('utf-8')),
                      'all_equal':len(set(results))==1,'cache':cache.stats()}
        print(json.dumps(answer,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (CacheError,v26.CheckpointError,OSError,ValueError,StopIteration) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
