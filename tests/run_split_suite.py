"""Run each versioned unittest module in its own clean Python process.

This prevents stateful legacy test fixtures from affecting later modules and
emits auditable aggregate totals; it does not skip or reclassify any tests.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = tuple(sorted((ROOT / 'tests').glob('test_*.py')))
PATTERN = re.compile(r'Ran (\d+) tests? in')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='ALCG isolated versioned unittest suites')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end', type=int, default=None)
    args = parser.parse_args(argv)
    ending = len(FILES) if args.end is None else args.end
    if not 0 <= args.start < ending <= len(FILES):
        parser.error(f'range must satisfy 0 <= start < end <= {len(FILES)}')
    total = 0
    for index in range(args.start, ending):
        file = FILES[index]
        cmd = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', file.name, '-q']
        try:
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                 timeout=120, check=False)
        except subprocess.TimeoutExpired:
            print(f'FAIL {file.name}: timeout >120s', file=sys.stderr, flush=True)
            return 1
        output = run.stdout + '\n' + run.stderr
        counted = PATTERN.findall(output)
        if run.returncode != 0 or len(counted) != 1 or not output.strip().endswith('OK'):
            print(f'FAIL {file.name} (exit={run.returncode}):\n{output[-7000:]}',
                  file=sys.stderr, flush=True)
            return 1
        number = int(counted[0])
        if number == 0:
            print(f'FAIL {file.name}: no tests were executed', file=sys.stderr, flush=True)
            return 1
        total += number
        print(f'PASS [{index+1}/{len(FILES)}] {file.name}: {number} tests', flush=True)
    print(f'PASS aggregate: {total} test cases in {ending-args.start} independent modules',
          flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
