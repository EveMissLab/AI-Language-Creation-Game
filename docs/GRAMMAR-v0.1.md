# ALCG Syntax Sketch v0.1 (Experimental)

This is the **first playable scaffold**, not a standardized language, a translator, or a proven universal semantic representation.

## Design constraints

- Prefer English-readable concept and relation labels, written with ASCII identifiers.
- Compose expressions recursively with **named arguments**; keep role labels visible.
- Allow UTF-8 quoted text when a concept is not yet modeled. This is an explicit fallback, not a semantic success.
- Favor breadth, inspectability and gradual change over short encodings.
- Do not require pronunciation, custom glyphs, cryptography, execution semantics or a compiler.
- Future *mesoscopic characters* may represent reusable functional/conceptual bundles; they are **not specified** here.

## Minimal grammar

```ebnf
line      = expression ;
expression = name | string | call ;
call      = name, "(", [ argument, { ",", argument } ], ")" ;
argument  = name, "=", expression ;
name      = ( ASCII_letter | "_" ), { ASCII_letter | digit | "_" | "-" } ;
string    = JSON_quoted_string ;
```

Each non-blank line in an `.alcg` file is one expression. A line whose first non-space character is `#` is a comment. Inline comments are not supported. Duplicate argument names in the same call are rejected. Names are case-sensitive. `"..."` uses JSON-style escaping, with UTF-8 permitted inside the string.

Examples:

```text
DO(actor=AI, action=CREATE, object=LANGUAGE)
IS(subject=WATER, property=LIQUID)
CAUSE(source=HEAT, effect=CHANGE(subject=WATER, property=TEMPERATURE))
RAW(text="No structured representation for this meaning yet.")
```

`DO`, `IS`, `CAUSE`, and `RAW` are **illustrative English-readable relation labels**, not yet executable functions or a formally complete logic. Argument keys (`actor`, `property`, `effect`, etc.) identify intended roles but are not enforced by a schema in v0.1. The parser checks **structure**, not whether a statement is true, meaningful, or logically valid.

## What the audit measures

`python alcg.py audit samples/seed.alcg` reports:

- **expressions:** lines successfully parsed.
- **structured_without_RAW:** sample expressions not using `RAW(...)`.
- **RAW_nodes:** explicit unmodeled-text fallbacks.
- **named_occurrences:** names (concepts and relation labels) present in the parsed samples. Argument keys are not counted.
- **seed_vocabulary_match_ratio:** the fraction of those name occurrences present in `data/seed-vocabulary.txt`.
- **names_not_in_seed:** names seen in the samples but absent from the small vocabulary.

**Important:** The seed-vocabulary match ratio is **not English concept coverage**, semantic equivalence, factual correctness, or evidence of model comprehension. Unknown names can still be parsed syntactically. `RAW` gives a path to record unmodeled meanings without pretending the language has represented them structurally.

## Future challenge design (not yet implemented)

Test a curated, cross-domain set of English meanings. Record whether each is expressed without `RAW`, whether its relations remain faithful, and whether independent AI readers reconstruct the intended meaning without supplementary hints. Keep structural coverage and reconstruction accuracy separate.
