# ALCG v0.14 — Deterministic Metamorphic Challenge Generation

**Status:** executable, version-pinned, synthetic structural challenge generator. This is not a natural-language semantics benchmark, autonomous LLM invention, proof of English concept coverage, or an independent AI-reader test.

## Research question

Can the existing ALCG candidate patterns generate new *structural* problems, together with controlled transformations that reveal when a matcher is conflating (a) textual variation, (b) canonical structure, and (c) intended meaning?

The prior v0.13 experiment showed that all three matches to the historical nontraining contrasts were wrong-answer foils. It therefore would be misleading to count pattern compatibility alone as semantic transfer. v0.14 constructs and validates metamorphic cases rather than inventing an unverifiable semantic success score.

## Inputs and provenance

- The 4 **review-only** motifs discovered in v0.12; the public v0.8 16-pattern registry is SHA-256 pinned and **never changed**.
- `data/generator-lexicon-v0.14.json`: hand-curated English-readable *slot label banks*. Names are synthetic experimental material, not observed English utterances or truth-annotated scientific claims.
- A deterministic SHA-256 selector (`seed=1409`) chooses combinations. This is combinatorial program generation, **not AI training or unconstrained natural-language generation**.
- Canonical ASTs from the v0.12 actual discovery inputs, the earlier contrast datasets, and v0.13 diagnostics are checked for exact overlap. All 32 new positives are outside that frozen list. This does **not** make the source distribution statistically independent.
- Every pattern, case, and transformation is openly documented. No hidden key, pronunciation specification, encryption or specialized glyph is introduced.

## Generated task types

For each of the four candidate patterns (`BEFORE`, `CAUSE`, `EXISTS`, `NOT`), generate 8 new positives, for 32 total. Each new positive has three metamorphic controls; the existential cases have a fourth.

| Generated control | Expected canonical relation | Candidate matcher result | What this establishes |
|---|---|---|---|
| Named-argument reordering (32) | Identical | Match | Named argument order is not an extra semantic role |
| Lexical-slot substitution (32) | Different | Still matches | Pattern shape does **not** imply identical canonical content |
| Operator/coreference perturbation (32) | Different | Reject | Some changed operator or shared-role constraints are caught |
| Bound-variable alpha-renaming (8) | Identical | Match | Renaming the bound variable and corresponding `REF` preserves canonical structure |

In total: **32 newly generated expressions and 104 controlled variants**. The complete set is committed as `benchmarks/generated-challenges-v0.14.jsonl`, with an identical reproducible report in `reports/generated-challenges-v0.14.json`.

### Concrete example

A generated candidate may take the form:

```text
BEFORE(earlier=DO(action=LOAD, actor=RESEARCH_ASSISTANT, object=PACKAGE_RECORD), later=DO(action=ANALYZE, actor=RESEARCH_ASSISTANT, object=RESULT_REPORT))
```

Swapping the order of the `earlier` and `later` *arguments in the textual call* preserves the same canonical structure. By contrast, replacing the later actor `RESEARCH_ASSISTANT` with `OTHER_RESEARCH_ASSISTANT` violates the discovered pattern's shared-actor constraint; the matcher rejects it. Replacing `RESULT_REPORT` with `DELIVERY_ORDER` is another canonical structure and still matches the same pattern. No claim is made that any of these propositions is true in the real world.

## Reproduce (standard-library Python 3.10+)

```bash
python challenge_generator.py check
python challenge_generator.py report
python challenge_generator.py generate --out /tmp/alcg-v014-generated.jsonl
python -m unittest discover -s tests -v
```

On Windows, the last command works unchanged; choose an appropriate writable path for `--out` (e.g. `..\generated-v014.jsonl` (a directory above the repository)). The `generate` command refuses to change existing repository artifacts other than rewriting the identical committed challenge file, and refuses to overwrite an external file whose content differs. Nothing automatically promotes a candidate into the official pattern dictionary.

`check` regenerates the challenges from frozen inputs, validates all metamorphic classifications, and compares bytes parsed from the committed fixture plus the machine-readable report. An external participant can try their own lexical bank or seed in code, but must not treat this batch as independent evidence of natural-language comprehension.

## Verified outcomes / boundaries

- **32/32** generated positives match and expand losslessly to the canonical full ALCG structure.
- **40/40** equivalence controls (32 named-argument permutations + 8 alpha-renamings) preserve the canonical structure.
- **32/32** lexical substitution controls change the canonical structure but remain pattern matches; this is a known blind spot if the matcher is incorrectly treated as a semantic judge.
- **32/32** role/operator controls change the structure and fail their candidate's structural constraint.
- All retained/generated positive expressions and non-equivalent transformations are disjoint from the frozen prior AST corpus used in these checks.

These are **deterministic structural properties, not predictive accuracy**. In particular, `different canonical AST` does not entail `different truth value in every possible model`, and the synthetic lexical labels are neither proof of plausible natural-language meaning nor evidence of expanded English coverage. The candidate patterns remain pending review; the independent-reader count stays zero.

## Why this remains a game

This is an iterative and falsifiable experimental move: create new examples, manufacture controlled challenges, check which invariants survive, log failures, and improve the representation. More meaningful AI language evolution requires future independent readers, meaning-grounded test annotations, and typed executable-function composition; **none of those achievements are claimed here**.

## 中文摘要

v0.14 開始讓程式依現有概念樣板**自行組合新的測試表達式與對照變體**，而不是每輪只靠手寫正反例。總共 32 條新表達式、104 條變體；分辨具名參數換序、量詞綁定變數改名、詞彙替換與算子／共用角色改動。所有可判定結論都停留在「標準化結構是否相同」與「候選樣板是否匹配」的層次，不宣稱已具備真正的語義判定、英語概念覆蓋增益或獨立 AI 理解測試結果。這一輪也沒有修改原本的 16 個正式樣板。
