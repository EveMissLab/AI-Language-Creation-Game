"""ALCG v0.2 coverage laboratory: transparent, *unverified* representation trials.

Syntax and role signatures are machine-checked. Meaning preservation requires
independent reconstruction and human adjudication; no automatic semantic claim.
Standard library only, Python >=3.10.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

from alcg import Call, Name, ParseError, String, parse, render, walk

ROOT = Path(__file__).resolve().parent
DEFAULT_BENCHMARK = ROOT / "benchmarks" / "coverage-v0.2.jsonl"
DEFAULT_RELATIONS = ROOT / "data" / "relations-v0.2.json"
DOMAINS = frozenset({"daily", "science", "mathematics", "computing", "society", "epistemic"})
HYPOTHESES = frozenset({"candidate", "partial", "raw"})
ID_PATTERN = re.compile(r"^[A-Z][0-9]{2,4}$")


class BenchmarkError(ValueError):
    """Invalid benchmark, relation profile, or external rating."""


def jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(obj, dict):
            raise BenchmarkError(f"{path}:{line_no}: expected a JSON object")
        result.append(obj)
    return result


def relations(path: Path = DEFAULT_RELATIONS) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        mapping = document["relations"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BenchmarkError(f"invalid relation registry: {path}") from exc
    if not isinstance(mapping, dict) or not mapping:
        raise BenchmarkError("relation registry must contain a non-empty object")
    for name, spec in mapping.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("required"), list) or not isinstance(spec.get("optional"), list):
            raise BenchmarkError(f"invalid relation signature: {name}")
        keys = spec["required"] + spec["optional"]
        if len(set(keys)) != len(keys):
            raise BenchmarkError(f"overlapping or duplicate roles in relation: {name}")
    return mapping


def inspect_calls(expr: Name | String | Call, registry: dict[str, dict[str, Any]]) -> None:
    for node in walk(expr):
        if isinstance(node, Call):
            spec = registry.get(node.name)
            if spec is None:
                raise BenchmarkError(f"unregistered relation operator: {node.name}")
            roles = {key for key, _ in node.args}
            required = set(spec["required"])
            allowed = required | set(spec["optional"])
            if not required.issubset(roles) or not roles.issubset(allowed):
                raise BenchmarkError(f"invalid roles for {node.name}: got {sorted(roles)}, required {sorted(required)}")
            if node.name == "RAW" and not isinstance(dict(node.args)["text"], String):
                raise BenchmarkError("RAW(text=...) requires a quoted string")
        elif isinstance(node, String):
            # A plain quoted string is permitted by the syntax, but not by
            # this structured-coverage benchmark unless it is RAW's text.
            pass


def validate_row(row: dict[str, Any], registry: dict[str, dict[str, Any]]) -> tuple[str, str, str, Name | String | Call]:
    expected = {"id", "domain", "english", "expression", "hypothesis", "gap"}
    if set(row) != expected:
        raise BenchmarkError(f"case fields mismatch: {sorted(set(row) ^ expected)}")
    identifier, domain, hypothesis = row["id"], row["domain"], row["hypothesis"]
    if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
        raise BenchmarkError(f"invalid case ID: {identifier!r}")
    if not isinstance(domain, str) or not isinstance(hypothesis, str) or domain not in DOMAINS or hypothesis not in HYPOTHESES:
        raise BenchmarkError(f"{identifier}: invalid domain or hypothesis")
    if not isinstance(row["english"], str) or not row["english"].strip():
        raise BenchmarkError(f"{identifier}: missing source English")
    if not isinstance(row["expression"], str) or not row["expression"].strip():
        raise BenchmarkError(f"{identifier}: missing expression")
    if not isinstance(row["gap"], str):
        raise BenchmarkError(f"{identifier}: gap must be text")
    try:
        expr = parse(row["expression"])
    except ParseError as exc:
        raise BenchmarkError(f"{identifier}: invalid syntax: {exc}") from exc
    if parse(render(expr)) != expr:
        raise BenchmarkError(f"{identifier}: parser round-trip mismatch")
    inspect_calls(expr, registry)
    if hypothesis == "candidate":
        if row["gap"].strip():
            raise BenchmarkError(f"{identifier}: candidate must not claim a known gap")
        if any(isinstance(x, String) or (isinstance(x, Call) and x.name in {"RAW", "PARTIAL"}) for x in walk(expr)):
            raise BenchmarkError(f"{identifier}: candidate contains an escape or partial marker")
    elif hypothesis == "raw":
        if not isinstance(expr, Call) or expr.name != "RAW":
            raise BenchmarkError(f"{identifier}: raw case must be a top-level RAW call")
        if not row["gap"].strip():
            raise BenchmarkError(f"{identifier}: raw case must describe the gap")
    else:
        if not isinstance(expr, Call) or expr.name != "PARTIAL":
            raise BenchmarkError(f"{identifier}: partial case must use top-level PARTIAL")
        args = dict(expr.args)
        missing = args["missing"]
        core = args["core"]
        if not isinstance(missing, Call) or missing.name != "RAW":
            raise BenchmarkError(f"{identifier}: missing part must be RAW(text=...)")
        if any(isinstance(x, String) or (isinstance(x, Call) and x.name in {"RAW", "PARTIAL"}) for x in walk(core)):
            raise BenchmarkError(f"{identifier}: partial core must contain only structure")
        if not row["gap"].strip():
            raise BenchmarkError(f"{identifier}: partial case must describe the gap")
    return identifier, domain, hypothesis, expr


def load_benchmark(path: Path = DEFAULT_BENCHMARK, registry_path: Path = DEFAULT_RELATIONS) -> list[dict[str, Any]]:
    registry = relations(registry_path)
    rows = jsonl(path)
    if not rows:
        raise BenchmarkError("benchmark must contain at least one case")
    ids: set[str] = set()
    for row in rows:
        identifier, _, _, _ = validate_row(row, registry)
        if identifier in ids:
            raise BenchmarkError(f"duplicate case ID: {identifier}")
        ids.add(identifier)
    return rows


def summarize(rows: list[dict[str, Any]], registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["hypothesis"] for r in rows)
    by_domain: dict[str, Counter[str]] = defaultdict(Counter)
    symbols: set[str] = set()
    used_relations: set[str] = set()
    for r in rows:
        by_domain[r["domain"]][r["hypothesis"]] += 1
        for node in walk(parse(r["expression"])):
            if isinstance(node, Name):
                symbols.add(node.value)
            elif isinstance(node, Call):
                used_relations.add(node.name)
    return {
        "benchmark_cases": len(rows),
        "candidate_not_yet_verified": counts["candidate"],
        "partial_with_explicit_gap": counts["partial"],
        "raw_unrepresented": counts["raw"],
        "candidate_share_of_this_curated_set": round(counts["candidate"] / len(rows), 4),
        "independent_reconstruction_scores": None,
        "unique_english_concept_labels_not_semantically_validated": len(symbols),
        "relation_operators_used": len(used_relations),
        "registered_relation_operators": len(registry),
        "by_domain": {d: {"total": sum(c.values()), **{status: c[status] for status in sorted(HYPOTHESES)}} for d, c in sorted(by_domain.items())},
        "warning": "Author hypotheses are NOT independent semantic coverage or AI comprehension scores. The corpus was curated, not sampled from English use."
    }


def blind_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Only id and expression. The target English and hints are NEVER sent."""
    return [{"id": row["id"], "expression": row["expression"]} for row in rows]


def score_rows(rows: list[dict[str, Any]], judgments: list[dict[str, Any]]) -> dict[str, Any]:
    known = {r["id"]: r for r in rows}
    seen: set[str] = set()
    distribution: Counter[int] = Counter()
    by_domain: dict[str, Counter[int]] = defaultdict(Counter)
    for judgment in judgments:
        if set(judgment) != {"id", "rating", "notes"}:
            raise BenchmarkError("judgments require exactly: id, rating, notes")
        identifier, rating, notes = judgment["id"], judgment["rating"], judgment["notes"]
        if identifier not in known or identifier in seen:
            raise BenchmarkError(f"unknown or duplicate judgment ID: {identifier!r}")
        if type(rating) is not int or rating not in (0, 1, 2, 3):
            raise BenchmarkError(f"{identifier}: rating must be an integer from 0 through 3")
        if not isinstance(notes, str) or not notes.strip():
            raise BenchmarkError(f"{identifier}: adjudication notes must explain the rating")
        seen.add(identifier)
        distribution[rating] += 1
        by_domain[known[identifier]["domain"]][rating] += 1
    return {
        "rated_cases": len(seen),
        "unrated_cases": len(rows) - len(seen),
        "ratings_distribution": {str(i): distribution[i] for i in range(4)},
        "average_rating_over_rated_cases_only": round(sum(k * v for k, v in distribution.items()) / len(seen), 4) if seen else None,
        "faithful_rating_3_over_rated_cases_only": round(distribution[3] / len(seen), 4) if seen else None,
        "by_domain": {domain: {str(i): c[i] for i in range(4)} for domain, c in sorted(by_domain.items())},
        "warning": "All ratings are externally adjudicated. Do not generalize from curated samples or ungraded cases."
    }


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="ALCG v0.2: coverage and reconstruction laboratory")
    cli.add_argument("command", choices=["check", "audit", "blind", "score"])
    cli.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    cli.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS)
    cli.add_argument("--out", type=Path, help="For blind: destination JSONL file; otherwise print to stdout")
    cli.add_argument("--judgments", type=Path, help="For score: independently adjudicated JSONL ratings")
    args = cli.parse_args(argv)
    try:
        rows = load_benchmark(args.benchmark, args.relations)
        if args.command == "check":
            print(f"OK: {len(rows)} annotated cases are structurally valid; meaning is not verified")
        elif args.command == "audit":
            print(json.dumps(summarize(rows, relations(args.relations)), indent=2, ensure_ascii=False))
        elif args.command == "blind":
            packet = blind_rows(rows)
            if args.out:
                write_jsonl(args.out, packet)
                print(f"Wrote {len(packet)} blind cases to {args.out}")
            else:
                print("\n".join(json.dumps(item, ensure_ascii=False) for item in packet))
        else:
            if args.judgments is None:
                raise BenchmarkError("score requires --judgments PATH; scores are never invented")
            print(json.dumps(score_rows(rows, jsonl(args.judgments)), indent=2, ensure_ascii=False))
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
