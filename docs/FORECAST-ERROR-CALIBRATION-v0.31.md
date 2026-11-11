# ALCG v0.31 — Frozen Forecasts, Delayed Evaluation, and Calibration Feedback

**Status:** experimental, deterministic and reproducible. **Data origin:** the four synthetic workload streams from ALCG v0.30. **Purpose:** evaluate a forecast *after* the events that it predicted have occurred. This is an AI-readable decision/evidence representation experiment, not a live analytics product or evidence of independent AI comprehension.

## 1. Relation to the language project

ALCG v0.22–v0.30 built replayable decision traces and a prefix-only workload observer. ALCG v0.31 separates **prediction issuance**, **future observation**, **error scoring**, **later calibration**, and **retrospective decision costs** into distinguishable artifacts. `AUDIT_V031(...)` is a concrete ALCG expression produced from these artifacts; the expression is parsed and checked against the exact structured record. It is an experimental label with publicly documented roles, **not** a new executable primitive, a new mesoscopic character, or an assertion of factual truth.

## 2. Temporal protocol

- Four pinned streams: `stable`, `churn`, `sparse`, and `drift`; 96 explicitly recorded read/idle *opportunities* each, not wall-clock intervals.
- Predictions are issued at logical cuts **32 and 64**. Every prediction covers the *next* **32** opportunities.
- `issue()` creates a new event document using only `events[:cut]`. It does **not need the future events to exist**. The issuance SHA-256 binds the forecast and the corresponding prefix fingerprint.
- Only after the interval ends may `settle()` see its observations. An issuance for cut 64 can use a correction fitted to the completed interval `[32,64)`; it **cannot** train on `[64,96)`.
- A stream without sufficient observed reads is labeled `insufficient_prefix`; its future is still reported, but no probability score or superiority claim is fabricated.
- Issuance, holdout receipts, and calibration-training receipts are separate. Each receipt checks consistency, not authorship or public trust.

This implements the causal chronology **predict → observe → score → correct future predictions**, without reconstructing an earlier prediction from future data.

## 3. Exact scores

All probabilities, Brier scores and counterfactual costs are calculated using Python `fractions.Fraction` and serialized as `{"num": ..., "den": ...}`. No floating-point rounding is used to decide a result.

For a binary event with predicted probability $p$ and observed outcome $y$:

$$
B(p,y)=(p-y)^2.
$$

For an interval with $n$ opportunities, $k$ positive outcomes and a constant forecast $p$:

$$
B_n=\frac{k(1-p)^2+(n-k)p^2}{n}.
$$

The **read** score is over 32 explicit read/idle opportunities. The **reset** score is over *internal successive read gaps* in that future interval; the first read is deliberately excluded from this gap score. A zero-gap interval has no reset Brier score.

Raw read and reset probabilities come from the unchanged v0.30 smoothed prefix counts. The forecast's rounded read count and parts-per-million reset hazard are used for v0.29 policy selection. The exact, pre-rounded probabilities are used for Brier scores. Those are distinct measurements and must not be conflated.

## 4. One-step delayed correction

Only at cut 64, and only if cut 32 had a scoreable prediction, the previous completed evaluation block is used to adjust the new raw rates. With correction weight $w=16$, old forecast $p$, and previous interval's observed count $k$ out of $n$:

$$
p'=\frac{wp+k}{w+n}.
$$

The same formula is used separately for the read probability and the reset-per-read-gap probability, each with its own observed denominator. It is a **bounded, one-step empirical adjustment** intended to expose behavior, not a guarantee of improved calibration. The adjusted rates yield a separately labeled v0.29 cache/direct decision, leaving the original issuance unchanged.

No correction trained on the present holdout is counted as its prediction. Cut 32 has no calibration. This approach is **prequential** (predict before using the corresponding observation).

## 5. Retrospective regret and what it means

The decision audit calculates a counterfactual on the observed holdout using the *pinned, single-host v0.28 median timings*. It assumes a cold state at the beginning of each interval and prices only the read gaps internal to that interval.

For $N$ future reads, $R$ internal resets, first-admission cost $C$, verified cache-hit cost $H$, and complete verification cost $U$:

$$
D=NU, \qquad K=(1+R)C+(N-1-R)H.
$$

When $N=0$ both costs are defined to be zero. The hindsight oracle chooses the cheaper of these two **modeled** costs. Regret is the chosen modeled cost minus the oracle cost. The oracle uses the future and is **never** an admissible online prediction. This is **not measured production latency**, and cannot establish how much a new live cache policy would save.

## 6. Fixed experiment outcomes

| Quantity | Deterministic result |
|---|---:|
| Scenario/cut pairs | 8 |
| Windows with enough prefix evidence to score | 6 |
| Windows marked insufficient evidence | 2 (`sparse` at both cuts) |
| Next-block calibration evaluations | 3 (`stable`, `churn`, `drift` at cut 64) |
| Separate mode-specific retrospective audits | 24 entries, of which 18 have decisions |

For the three evaluated calibrated holdouts, the macro-average **read** Brier score changes from about **0.000865** to **0.000096**, while the macro-average **reset** Brier changes from about **0.248118** to **0.243532**. These are three deliberately chosen synthetic cases, not statistical generalization. In `drift` at cut 64, the reset Brier score **worsens** (approximately 0.465280 → 0.477456), despite improvements elsewhere. A calibrated `selective` route switches from `direct` to `cache` under this drift and incurs positive hindsight cost regret. Under `stable`, the same change is retrospectively beneficial. Both outcomes are published, with no cherry-picking.

The `stable` scenario also documents a cold-regime miss: at cut 32, only eight of the previous 32 opportunities were reads, but all of the next 32 opportunities are reads. Its prospective probability is much too low. This failure is not erased by the later adaptation.

## 7. ALCG text projection

The file `samples/forecast-audits-v0.31.alcg` contains eight explicit, post-hoc `AUDIT_V031(...)` expressions. Every expression has separate roles:

- `issuance=ISSUE_V031(...)` with a frozen prediction receipt and route;
- `observation=OBSERVED_V031(...)` with realized read and reset counts and a holdout receipt;
- `feedback=FEEDBACK_V031(...)` with status, exact rational scores, and optional adjusted route.

The evaluator verifies that the expression parses and exactly matches the corresponding pinned report record. It **does not** infer the real-world truth of a synthetic statement, prove a new relation primitive, or establish independent AI-reader semantics. The JSON report remains canonical for score reproduction, while `.alcg` supplies a readable language projection.

## 8. Running the experiment

From repository root with Python 3.10+ and no third-party packages:

```bash
python forecast_calibration.py check
python forecast_calibration.py report
python forecast_calibration.py score --case drift --at 64
python forecast_calibration.py emit --case stable --at 64
python alcg.py check samples/forecast-audits-v0.31.alcg
python -m unittest discover -s tests -p test_forecast_calibration.py -v
python tests/run_split_suite.py
```

`check` recomputes the report from pinned sources, verifies both SHA-256 references and checks every `.alcg` sample. CI never requires a live model, network API, or volatile timing threshold. Previous versions' source code, dictionaries, and fixture records are unchanged.

## 9. Limitations and evidence boundary

1. Every source stream is **synthetic**. No actual production cache hit rate, prediction quality, or source-change distribution was measured.
2. Only two forecast cuts, three calibrated holdouts, and four intentionally structured scenarios are studied. They are not a representative population.
3. The previous interval is partly overlapping information relative to v0.30's rolling context; the correction is a decision experiment, **not** a separately trained deployment model.
4. Raw probabilities are intentionally simple and may be poorly calibrated during regime changes. Calibration can make both scores and subsequent decisions worse.
5. Brier score improvement does not guarantee lower realized cost, better hardware performance, or independent AI understanding.
6. SHA-256 receipts are consistency evidence only. Hostile provenance, identity, and signature verification are outside the model.
7. The regret comparison uses a hypothetical cold-start per window and pinned historical timing medians, not live measured savings.

### 中文研究結論

v0.31 將 ALCG 的運算紀錄進一步分成**當下已發布的預測、未來完成的觀測、事後評分、前一窗口的校準與決策損失**。這讓「觀測 → 預測 → 決策 → 結果 → 修正」有了具備時間順序、防後見之明與可重播性的表徵基礎。最重要的反例是：局部校準雖可能改善平均機率分數，卻不能保證在環境突變時產生更好的快取決策。所有結果只代表這個開源合成基準，未聲稱 AI 已獨立理解或掌握現實因果。
