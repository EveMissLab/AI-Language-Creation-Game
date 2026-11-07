"""ALCG v0.1: transparent syntax experiments, not a semantic reasoner."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Union


class ParseError(ValueError):
    """Invalid ALCG expression."""


@dataclass(frozen=True)
class Name:
    value: str


@dataclass(frozen=True)
class String:
    value: str


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[tuple[str, "Expr"], ...]


Expr = Union[Name, String, Call]
_TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_-]*|"(?:\\.|[^"\\])*"|[(),=]')
_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')


def tokenize(source: str) -> list[str]:
    tokens = []
    pos = 0
    while pos < len(source):
        if source[pos].isspace():
            pos += 1
            continue
        match = _TOKEN.match(source, pos)
        if match is None:
            raise ParseError(f"unexpected character at offset {pos}: {source[pos:pos + 16]!r}")
        tokens.append(match.group())
        pos = match.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise ParseError(f"expected {expected or 'expression'}, got {token!r}")
        self.pos += 1
        return token

    def expression(self) -> Expr:
        token = self.take()
        if token.startswith('"'):
            try:
                return String(json.loads(token))
            except json.JSONDecodeError as exc:
                raise ParseError(f"invalid quoted string: {exc.msg}") from exc
        if not _NAME.fullmatch(token):
            raise ParseError(f"expected concept name or quoted string, got {token!r}")
        if self.peek() != '(':
            return Name(token)
        self.take('(')
        args: list[tuple[str, Expr]] = []
        seen: set[str] = set()
        if self.peek() != ')':
            while True:
                key = self.take()
                if not _NAME.fullmatch(key):
                    raise ParseError(f"invalid argument name: {key!r}")
                if key in seen:
                    raise ParseError(f"duplicate argument: {key}")
                seen.add(key)
                self.take('=')
                args.append((key, self.expression()))
                if self.peek() != ',':
                    break
                self.take(',')
        self.take(')')
        return Call(token, tuple(args))


def parse(source: str) -> Expr:
    parser = _Parser(tokenize(source))
    result = parser.expression()
    if parser.peek() is not None:
        raise ParseError(f"unexpected trailing token: {parser.peek()!r}")
    return result


def render(expr: Expr) -> str:
    if isinstance(expr, Name):
        return expr.value
    if isinstance(expr, String):
        return json.dumps(expr.value, ensure_ascii=False)
    return f"{expr.name}({', '.join(f'{key}={render(value)}' for key, value in expr.args)})"


def to_data(expr: Expr) -> dict:
    if isinstance(expr, Name):
        return {"type": "name", "value": expr.value}
    if isinstance(expr, String):
        return {"type": "string", "value": expr.value}
    return {"type": "call", "name": expr.name,
            "args": {key: to_data(value) for key, value in expr.args}}


def walk(expr: Expr):
    yield expr
    if isinstance(expr, Call):
        for _, value in expr.args:
            yield from walk(value)


def read_expressions(path: Path) -> list[Expr]:
    expressions = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        try:
            expressions.append(parse(stripped))
        except ParseError as exc:
            raise ParseError(f"{path}:{number}: {exc}") from exc
    return expressions


def audit(expressions: list[Expr], vocabulary: set[str]) -> dict:
    names = Counter()
    raw = 0
    structured = 0
    for expression in expressions:
        nodes = list(walk(expression))
        raw_count = sum(isinstance(node, Call) and node.name == 'RAW' for node in nodes)
        raw += raw_count
        structured += (raw_count == 0)
        for node in nodes:
            if isinstance(node, Name):
                names[node.value] += 1
            elif isinstance(node, Call):
                names[node.name] += 1
    occurrences = sum(names.values())
    matched = sum(count for name, count in names.items() if name in vocabulary)
    return {
        'expressions': len(expressions),
        'structured_without_RAW': structured,
        'RAW_nodes': raw,
        'named_occurrences': occurrences,
        'seed_vocabulary_match_ratio': round(matched / occurrences, 4) if occurrences else None,
        'names_not_in_seed': sorted(name for name in names if name not in vocabulary),
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.1: syntax playground')
    cmds = cli.add_subparsers(dest='command', required=True)
    p = cmds.add_parser('parse', help='parse one expression to JSON AST')
    p.add_argument('expression')
    p = cmds.add_parser('check', help='check sample file syntax')
    p.add_argument('file', type=Path)
    p = cmds.add_parser('audit', help='inspect sample structure and seed-vocabulary usage')
    p.add_argument('file', type=Path)
    p.add_argument('--vocab', type=Path, default=Path('data/seed-vocabulary.txt'))
    args = cli.parse_args(argv)
    try:
        if args.command == 'parse':
            print(json.dumps(to_data(parse(args.expression)), indent=2, ensure_ascii=False))
        elif args.command == 'check':
            examples = read_expressions(args.file)
            print(f'OK: {len(examples)} syntactically valid expressions')
        else:
            examples = read_expressions(args.file)
            vocabulary = {line.strip() for line in args.vocab.read_text(encoding='utf-8').splitlines()
                          if line.strip() and not line.lstrip().startswith('#')}
            print(json.dumps(audit(examples, vocabulary), indent=2, ensure_ascii=False))
    except (ParseError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
