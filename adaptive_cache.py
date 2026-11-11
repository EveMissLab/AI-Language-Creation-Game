"""ALCG v0.29: evidence-gated automatic cache admission and invalidation economics.

The policy is intentionally NOT a learned causal law or benchmark of all machines.
It uses a pinned v0.28 single-host timing record and hypothetical workload forecasts.
The reader enforces the stricter v0.28 process-local trust boundary on BOTH paths.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from threading import RLock
from typing import Any

import checkpoint_planner as v26
import measured_replay as v27
import trusted_cache as v28

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-v0.29-evidence-gated-adaptive-cache'
PROFILE_PATH = ROOT / 'data/adaptive-cache-profiles-v0.29.json'
REPORT_PATH = ROOT / 'reports/adaptive-cache-decisions-v0.29.json'
SOURCE_REPORT_PATH = ROOT / 'reports/trusted-cache-v0.28.json'
MAX_READS = 4096
MAX_COST = 10**12
_ALIAS = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')


class AdaptiveError(ValueError):
    """Invalid assumptions, source, evidence or proposed cache use."""


class AdaptiveEnvironmentChanged(AdaptiveError):
    """Dependency changed: fail closed until a new reader is constructed."""


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canon(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _nonnegative_int(value: Any, name: str, *, max_value: int = MAX_COST) -> int:
    if type(value) is not int or not 0 <= value <= max_value:
        raise AdaptiveError(f'{name} must be an integer between 0 and {max_value}')
    return value


def validate_profile(row: Any) -> dict[str, Any]:
    """No floats, booleans or unbounded numbers in the declared forecast."""
    keys = {'expected_reads', 'invalidation_per_million',
            'rebuild_penalty_ns', 'retention_ns_per_read'}
    if not isinstance(row, dict) or set(row) != keys:
        raise AdaptiveError('profile must contain exactly four forecast fields')
    reads = row['expected_reads']
    if type(reads) is not int or not 1 <= reads <= MAX_READS:
        raise AdaptiveError('expected_reads outside 1..4096')
    _nonnegative_int(row['invalidation_per_million'], 'invalidation_per_million', max_value=1_000_000)
    _nonnegative_int(row['rebuild_penalty_ns'], 'rebuild_penalty_ns')
    _nonnegative_int(row['retention_ns_per_read'], 'retention_ns_per_read')
    return row


def read_policy() -> dict[str, Any]:
    try:
        policy = json.loads(PROFILE_PATH.read_text(encoding='utf-8'))
        source_bytes = SOURCE_REPORT_PATH.read_bytes()
    except (OSError, UnicodeError, ValueError) as exc:
        raise AdaptiveError('policy or historical measurements missing or invalid') from exc
    if (not isinstance(policy, dict) or set(policy) != {'format', 'source_report_sha256', 'workloads'}
            or policy['format'] != FORMAT or policy['source_report_sha256'] != _sha(source_bytes)
            or not isinstance(policy['workloads'], dict) or not policy['workloads']
            or len(policy['workloads']) > 16):
        raise AdaptiveError('policy schema or historical measurement fingerprint mismatch')
    for name, row in policy['workloads'].items():
        if type(name) is not str or not _ALIAS.fullmatch(name):
            raise AdaptiveError('invalid workload name')
        validate_profile(row)
    return policy


def measured_evidence() -> dict[str, Any]:
    try:
        evidence = json.loads(SOURCE_REPORT_PATH.read_text(encoding='utf-8'))
        v28.verify_report(evidence)  # audit past arithmetic and pinned live environment
    except (OSError, ValueError, v28.CacheError) as exc:
        raise AdaptiveError('v0.28 measurement record failed verification') from exc
    return evidence


def estimate(row: Any, profile: Any) -> dict[str, Any]:
    """Exact expected-cost comparison, assuming independent per-gap invalidations.

    N reads and N-1 gaps. Each source reset requires a new cold verified
    admission. An unchanged gap permits a hit. This is a workload *forecast*;
    the measured ns medians do not measure reset frequency or CPU time elsewhere.
    """
    validate_profile(profile)
    if not isinstance(row, dict):
        raise AdaptiveError('measurement row must be a mapping')
    u = _nonnegative_int(row.get('uncached_median_ns'), 'uncached_median_ns')
    cold = _nonnegative_int(row.get('cold_admission_ns'), 'cold_admission_ns')
    hit = _nonnegative_int(row.get('cached_median_ns'), 'cached_median_ns')
    if min(u, cold, hit) == 0:
        raise AdaptiveError('nonpositive measured timing')
    n = profile['expected_reads']
    p = Fraction(profile['invalidation_per_million'], 1_000_000)
    admissions = 1 + (n - 1) * p
    hits = (n - 1) * (1 - p)
    resets = (n - 1) * p
    uncached = n * u
    cached = (admissions * cold + hits * hit +
              resets * profile['rebuild_penalty_ns'] +
              n * profile['retention_ns_per_read'])
    # A tie is a bypass: do not pay an entry/memory complexity for no gain.
    selected = 'cache' if cached < uncached else 'direct'
    def exact(f: Fraction | int) -> dict[str, int]:
        v = Fraction(f)
        return {'num': v.numerator, 'den': v.denominator}
    return {
        'selection': selected,
        'expected_reads': n,
        'invalidation_per_million': profile['invalidation_per_million'],
        'expected_cache_admissions': exact(admissions),
        'expected_cache_hits': exact(hits),
        'direct_cost_ns': exact(uncached),
        'cache_cost_ns': exact(cached),
        'expected_savings_ns_if_cached': exact(uncached - cached),
    }


def breakeven(row: dict[str, Any], profile: dict[str, Any]) -> int | None:
    """First total read count where caching wins, within the stated horizon."""
    validate_profile(profile)
    # The difference is linear in N, so scan is simple, independently auditable,
    # and bounded (4096 tests; all Fraction arithmetic).
    for n in range(1, MAX_READS + 1):
        if estimate(row, {**profile, 'expected_reads': n})['selection'] == 'cache':
            return n
    return None


def analyze(evidence: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, dict) or not isinstance(policy, dict):
        raise AdaptiveError('expected evidence and policy objects')
    records = evidence.get('measurements')
    if not isinstance(records, list) or [x.get('mode') for x in records] != [
            'selective', 'hybrid_final', 'full']:
        raise AdaptiveError('wrong historical measurement modes')
    cases = []
    for profile_name, profile in sorted(policy['workloads'].items()):
        validate_profile(profile)
        for row in records:
            selection = estimate(row, profile)
            cases.append({'profile': profile_name, 'mode': row['mode'],
                          'source_sha256': row['source_sha256'],
                          'decision': selection,
                          'break_even_reads_with_same_hazard': breakeven(row, profile)})
    result = {
        'format': FORMAT,
        'evidence': 're-used v0.28 five-sample local medians; not remeasured',
        'source_report_sha256': policy['source_report_sha256'],
        'assumption': 'independent Bernoulli reset per gap, known forecast, no new empirical hazard data',
        'cases': cases,
        'claims_excluded': [
            'no universal performance or accuracy guarantee',
            'no empirical source-change frequency',
            'no authentication of local process or hash receipt',
            'no proof of independent AI semantic comprehension',
            'all cached admissions perform a fresh full validation',
        ],
    }
    result['receipt_sha256'] = _sha(_canon(result))
    return result


def verify_analysis(report: dict[str, Any], evidence: dict[str, Any],
                    policy: dict[str, Any]) -> bool:
    if not isinstance(report, dict):
        raise AdaptiveError('analysis must be an object')
    receipt = report.get('receipt_sha256')
    if type(receipt) is not str or receipt != _sha(_canon({k: v for k, v in report.items()
                                                         if k != 'receipt_sha256'})):
        raise AdaptiveError('analysis receipt corrupted')
    expected = analyze(evidence, policy)
    if report != expected:
        raise AdaptiveError('analysis does not match pinned model and policy')
    return True


class AdaptiveCacheReader:
    """Per-process routing between full verification and v0.28 verified cache.

    `profile` forecasts an epoch; it is not an entitlement to skip verification.
    Source changes through the same alias clear ALL cached entries (conservative).
    Monitored decoder/model/policy changes block this instance permanently.
    Unknown sources always use the full verification path.
    """
    def __init__(self, *, max_entries: int = 4):
        self._lock = RLock()
        self.policy = read_policy()
        self.evidence = measured_evidence()
        self._cache = v28.VerifiedStateCache(max_entries=max_entries)
        session = v27._session(self.evidence['session_id'])
        representations = v27.representations(session)
        self._known = {mode['expression']: row for mode, row in zip(
            representations, self.evidence['measurements'])}
        if any(mode['expression_sha256'] != row['source_sha256']
               for mode, row in zip(representations, self.evidence['measurements'])):
            raise AdaptiveError('measurement source is not identical to known expression')
        self._manifest = self._live_manifest()
        self._blocked = False
        self._aliases: dict[str, str] = {}
        self.direct_reads = self.cached_reads = self.source_invalidations = 0
        self.unknown_direct_reads = 0

    @staticmethod
    def _live_manifest() -> dict[str, str]:
        try:
            original = v28.source_manifest()
            original.update({
                'adaptive_cache.py': _sha((ROOT/'adaptive_cache.py').read_bytes()),
                'data/adaptive-cache-profiles-v0.29.json': _sha(PROFILE_PATH.read_bytes()),
                'reports/trusted-cache-v0.28.json': _sha(SOURCE_REPORT_PATH.read_bytes()),
            })
            return original
        except OSError as exc:
            raise AdaptiveEnvironmentChanged('required model or policy file missing') from exc

    def _check_environment(self) -> None:
        if self._blocked:
            raise AdaptiveEnvironmentChanged('reader blocked after dependency change; restart required')
        try:
            current = self._live_manifest()
        except AdaptiveEnvironmentChanged:
            self._blocked = True
            self._cache.clear()
            raise
        if current != self._manifest:
            self._blocked = True
            self._cache.clear()
            raise AdaptiveEnvironmentChanged('dependency/policy changed; cached or direct read refused')

    def decision(self, source: str, profile: str) -> dict[str, Any]:
        with self._lock:
            self._check_environment()
            v28.VerifiedStateCache._source_key(source)
            if profile not in self.policy['workloads']:
                raise AdaptiveError('unknown workload profile')
            row = self._known.get(source)
            if row is None:
                return {'selection': 'direct', 'reason': 'no pinned timing evidence for this exact source'}
            return {**estimate(row, self.policy['workloads'][profile]),
                    'reason': 'pinned local timing + explicit workload forecast'}

    def read(self, alias: str, source: str, index: int, *, profile: str) -> str:
        with self._lock:
            self._check_environment()
            if type(alias) is not str or not _ALIAS.fullmatch(alias):
                raise AdaptiveError('invalid source alias')
            if type(index) is not int or index < 0:
                raise AdaptiveError('state index must be a nonnegative integer')
            v28.VerifiedStateCache._source_key(source)
            choice = self.decision(source, profile)
            previous = self._aliases.get(alias)
            if previous is not None and previous != source:
                # Changing an alias is a data revision, not a cache hit.
                self._cache.clear()
                self.source_invalidations += 1
            self._aliases[alias] = source
            if choice['selection'] == 'cache':
                output = self._cache.read(source, index)
                self.cached_reads += 1
            else:
                # Full verification on EVERY bypass, including an unknown source.
                try:
                    output = v26.access_state(source, index)
                except (v26.CheckpointError, ValueError, RecursionError) as exc:
                    raise AdaptiveError('direct verification failed: ' + str(exc)) from exc
                self.direct_reads += 1
                if source not in self._known:
                    self.unknown_direct_reads += 1
            self._check_environment()  # refuse a model mutation during processing
            return output

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {'direct_reads': self.direct_reads, 'cached_reads': self.cached_reads,
                    'unknown_direct_reads': self.unknown_direct_reads,
                    'source_invalidations': self.source_invalidations,
                    'blocked': self._blocked, 'underlying_cache': self._cache.stats()}


def check() -> dict[str, Any]:
    policy = read_policy()
    evidence = measured_evidence()
    report = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    verify_analysis(report, evidence, policy)
    session = v27._session(evidence['session_id'])
    source = next(x['expression'] for x in v27.representations(session)
                  if x['mode'] == 'selective')
    expected = v26.access_state(source, len(session.rounds))
    reader = AdaptiveCacheReader()
    direct_profile = 'one_off'
    cache_profile = 'stable_repeat'
    if reader.decision(source, direct_profile)['selection'] != 'direct':
        raise AdaptiveError('expected one-off direct plan')
    if reader.decision(source, cache_profile)['selection'] != 'cache':
        raise AdaptiveError('expected stable-repeat cache plan')
    if (reader.read('demo', source, len(session.rounds), profile=direct_profile) != expected
            or reader.read('demo', source, len(session.rounds), profile=cache_profile) != expected
            or reader.read('demo', source, len(session.rounds), profile=cache_profile) != expected):
        raise AdaptiveError('adaptive reader returned wrong verified result')
    stats = reader.stats()
    if stats['direct_reads'] != 1 or stats['underlying_cache']['verified_admissions'] != 1 or stats['underlying_cache']['hits'] != 1:
        raise AdaptiveError('admission and bypass counters do not match real reader calls')
    return {'status': 'PASS', 'profiles': len(policy['workloads']),
            'cases': len(report['cases']), 'sample_runtime': stats,
            'claim': 'bounded model and pinned historical arithmetic; not measured lifetime speed'}


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.29 policy-gated cache admission')
    sub = cli.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    plan = sub.add_parser('plan')
    plan.add_argument('--profile', required=True)
    plan.add_argument('--mode', choices=('selective','hybrid_final','full'), default='selective')
    run = sub.add_parser('read')
    run.add_argument('--profile', required=True)
    run.add_argument('--mode', choices=('selective','hybrid_final','full'), default='selective')
    run.add_argument('--times', type=int, default=2)
    run.add_argument('--state', type=int, default=2)
    args = cli.parse_args(argv)
    try:
        if args.cmd == 'check':
            value = check()
        else:
            policy = read_policy()
            evidence = measured_evidence()
            if args.profile not in policy['workloads']:
                raise AdaptiveError('unknown workload profile')
            row = next(x for x in evidence['measurements'] if x['mode'] == args.mode)
            if args.cmd == 'plan':
                value = {'profile':args.profile, 'mode':args.mode,
                         'result':estimate(row, policy['workloads'][args.profile]),
                         'break_even_reads':breakeven(row,policy['workloads'][args.profile])}
            else:
                if not 1 <= args.times <= 100 or type(args.times) is not int:
                    raise AdaptiveError('times must be between 1 and 100')
                reader = AdaptiveCacheReader()
                s = v27._session(evidence['session_id'])
                src = next(x['expression'] for x in v27.representations(s)
                           if x['mode'] == args.mode)
                answers = [reader.read('example',src,args.state,profile=args.profile)
                           for _ in range(args.times)]
                value = {'all_equal':len(set(answers))==1,
                         'state_sha256':_sha(answers[-1].encode('utf-8')),
                         'stats':reader.stats()}
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (AdaptiveError, v28.CacheError, v26.CheckpointError,
            ValueError, OSError, StopIteration) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
