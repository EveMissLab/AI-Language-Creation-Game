# AI Language Creation Game (ALCG)

**An open-source, AI-first language-creation playground.** Begin with English-readable concepts and symbols, then grow toward wider semantic coverage and eventually reusable mesoscopic concept/function bundles.

> Status: **v0.2 coverage laboratory (experimental)** — not a finished language, cipher, natural-language translator or semantic proof system.

## What is the game?

ALCG is an incremental experiment in **expressing meaning with readable, composable symbols**. The goal is to gradually cover more concepts while keeping structures inspectable by AI systems and humans. It is intended to become increasingly capable, not remain a toy.

We deliberately **do not** optimize for pronunciation, original writing systems, encryption, code execution, or maximal compression in this initial stage. Public GitHub research documents may eventually use a more mature form of this notation, but a reader should not need to reverse-engineer a secret code: rules and examples remain openly documented.

## Try it (Python 3.10+, standard library only)

```bash
python alcg.py check samples/seed.alcg
python alcg.py parse 'DO(actor=AI, action=CREATE, object=LANGUAGE)'
python alcg.py audit samples/seed.alcg
python -m unittest discover -s tests -v

# v0.2: annotated English-meaning coverage experiments
python coverage_lab.py check
python coverage_lab.py audit
python coverage_lab.py blind --out blind-v0.2.jsonl
```

Minimal examples:

```text
IS(subject=WATER, property=LIQUID)
DO(actor=AI, action=CREATE, object=LANGUAGE)
WANT(agent=PERSON, goal=DO(actor=AI, action=HELP, object=PERSON))
RAW(text="A meaning not yet expressed with structured concepts.")
```

These examples demonstrate a **parser**, not verified meaning or truth. See [syntax sketch](docs/GRAMMAR-v0.1.md) and the [v0.2 coverage protocol](docs/COVERAGE-v0.2.md) for the current limits.

## Roadmap, kept intentionally small

1. **Seed (now):** a readable, recursive text syntax, examples, and a local audit that makes gaps visible.
2. **Coverage experiments (v0.2):** 36 annotated cases across six domains; `candidate`, `partial` and `raw` remain explicitly distinct. Blind reconstruction packets can be exported, but **no independent AI comprehension scores exist yet**.
3. **Stability:** refine relation labels and scope only when test cases expose ambiguity.
4. **Mesoscopic units (later):** explore reusable concept and *functional* compositions; do not force them into the first syntax.

GitHub Actions runs the unit tests, sample syntax check, vocabulary audit, and the v0.2 coverage validator on pushes and pull requests, using standard runners. All checks also work locally without Actions or external APIs. Contributions should include an example meaning, an expression, and a note about ambiguities or failures; not just a shorter spelling.

## 中文簡介

這是 **AI 語言創造遊戲** 的第一個開源試作。優先使用英文概念與現有符號，逐步擴大可表達的語義範圍，並保留 AI 可直接閱讀、依公開規格解析的可能性。目前提供**最小的可解析結構與六領域 36 條覆蓋實驗樣本**，明確區分候選結構、部分表達與原文保留；尚未進行獨立 AI 盲測，不宣稱 AI 已能無歧義理解，不處理發音、加密或中觀字元。後續中觀單元會優先考察實際可用的概念／函數組合。

## License

MIT — see [LICENSE](LICENSE).
