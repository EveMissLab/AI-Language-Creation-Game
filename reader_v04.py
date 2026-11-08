"""ALCG v0.4 packet generation: reuse the v0.3 reader protocol on new data.

No remote AI is invoked by this module. It prepares offline experiments only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from coverage_lab import BenchmarkError
from reconstruction_lab import (
    evaluate, json_bytes, jsonl_bytes, prepare, validate_sources, write_new,
)

ROOT = Path(__file__).resolve().parent
COVERAGE = ROOT / 'benchmarks/coverage-v0.4.jsonl'
CONTRAST = ROOT / 'benchmarks/contrast-v0.4.jsonl'
RELATIONS = ROOT / 'data/relations-v0.4.json'


def build(seed: int = 20261108):
    return prepare(coverage_path=COVERAGE, contrast_path=CONTRAST,
                   registry_path=RELATIONS, seed=seed)


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.4 offline reader-protocol extension')
    subs = cli.add_subparsers(dest='command', required=True)
    subs.add_parser('check')
    prepared = subs.add_parser('prepare')
    prepared.add_argument('--out', type=Path, required=True)
    prepared.add_argument('--key', type=Path, required=True)
    prepared.add_argument('--seed', type=int, default=20261108)
    graded = subs.add_parser('grade')
    graded.add_argument('--packet', type=Path, required=True)
    graded.add_argument('--key', type=Path, required=True)
    graded.add_argument('--responses', type=Path, required=True)
    graded.add_argument('--ratings', type=Path)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            candidates, contrasts = validate_sources(COVERAGE, CONTRAST, RELATIONS)
            print(f'OK: {len(candidates)} authored reconstruct candidates, {len(contrasts)} contrasts; no model readers invoked')
        elif args.command == 'prepare':
            if args.out.resolve() == args.key.resolve() or args.out.exists() or args.key.exists():
                raise BenchmarkError('packet and key must be distinct new files')
            packet, key = build(seed=args.seed)
            write_new(args.out, jsonl_bytes(packet))
            write_new(args.key, json_bytes(key))
            print(f'Wrote {len(packet)} cases: {args.out}. Keep key private: {args.key}')
        else:
            print(json.dumps(evaluate(args.packet, args.key, args.responses, args.ratings),
                             indent=2, ensure_ascii=False))
    except (BenchmarkError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
