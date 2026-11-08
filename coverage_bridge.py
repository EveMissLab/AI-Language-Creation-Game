"""ALCG v0.4: fixed-English benchmark comparison, *not* reader scoring."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from coverage_lab import BenchmarkError, load_benchmark

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'benchmarks/coverage-v0.2.jsonl'
NEW = ROOT / 'benchmarks/coverage-v0.4.jsonl'
OLD_RELATIONS = ROOT / 'data/relations-v0.2.json'
NEW_RELATIONS = ROOT / 'data/relations-v0.4.json'
EXPECTED_PROMOTIONS = frozenset({'D05', 'S05', 'M06', 'C05'})


def report() -> dict:
    old = {r['id']: r for r in load_benchmark(OLD, OLD_RELATIONS)}
    new = {r['id']: r for r in load_benchmark(NEW, NEW_RELATIONS)}
    if set(old) != set(new) or len(old) != 36:
        raise BenchmarkError('v0.4 must retain the same 36 case IDs from v0.2')
    for identifier in old:
        for field in ('id', 'english', 'domain'):
            if old[identifier][field] != new[identifier][field]:
                raise BenchmarkError(f'{identifier}: original meaning or domain was changed')
    old_count = Counter(x['hypothesis'] for x in old.values())
    new_count = Counter(x['hypothesis'] for x in new.values())
    promotions = sorted(identifier for identifier in old
                        if old[identifier]['hypothesis'] != 'candidate' and new[identifier]['hypothesis'] == 'candidate')
    altered = sorted(identifier for identifier in old if old[identifier] != new[identifier])
    if set(promotions) != EXPECTED_PROMOTIONS or altered != promotions:
        raise BenchmarkError(f'v0.4 delta must affect only four specified cases; got changed={altered}, promotions={promotions}')
    if (old_count['candidate'], old_count['partial'], old_count['raw']) != (24, 6, 6):
        raise BenchmarkError('v0.2 original labels changed unexpectedly')
    if (new_count['candidate'], new_count['partial'], new_count['raw']) != (28, 3, 5):
        raise BenchmarkError('v0.4 proposed labels changed unexpectedly')
    return {
        'version': '0.4',
        'fixed_english_cases': len(old),
        'original_v0_2_sha256': hashlib.sha256(OLD.read_bytes()).hexdigest(),
        'proposal_v0_4_sha256': hashlib.sha256(NEW.read_bytes()).hexdigest(),
        'v0_2': {'candidate': 24, 'partial': 6, 'raw': 6},
        'v0_4': {'candidate': 28, 'partial': 3, 'raw': 5},
        'changed_cases': promotions,
        'unverified_proposal_delta': 4,
        'independent_reader_scores': None,
        'interpretation': 'This is an authored structural-proposal change on a frozen curated dataset, not a measured increase in English-language coverage or independent AI comprehension.'
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='Compare ALCG v0.2 to v0.4 on fixed authored meanings')
    cli.add_argument('command', choices=['check', 'report'])
    args = cli.parse_args(argv)
    try:
        value = report()
        if args.command == 'check':
            print('OK: 36 original meanings frozen, 4 proposed candidate promotions, no independent comprehension claims')
        else:
            print(json.dumps(value, indent=2, ensure_ascii=False))
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
