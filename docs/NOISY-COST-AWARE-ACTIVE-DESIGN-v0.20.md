# ALCG v0.20 — Noisy, Cost-Aware Active Intervention Design

**Status:** reproducible, strictly finite synthetic laboratory. Date: 2026-11-09.

## Scope and provenance

Version 0.19 establishes **exact noiseless** identification of 16 observationally compatible Boolean mechanisms per family, with four informative off-natural interventions. Its result is preserved as an earlier conditional theorem. This version changes only the **measurement channel and action costs**; the SCM truth tables, observations, active language syntax, 16 published patterns, and unpromoted proposals remain unchanged.

The prior mechanism family is taken from `reports/active-design-v0.19.json` and its input specification is pinned by SHA-256. An exact mismatch fails closed. There are seven synthetic families and no empirical experimental data.

## New experimental assumptions

Each attempted intervention has a background index `i` in `0..3`, a deterministic Boolean SCM outcome `Y`, and a **new, independent symmetric bit-flip noise variable**. Conditional on the true hypothesis and selected action:

$$
P(O=Y\mid H,a)=1-\epsilon_a,\qquad P(O\ne Y\mid H,a)=\epsilon_a.
$$

The error probability and unit cost are **declared hypothetical parameters**:

| Background index | Flip probability | Cost units | Informative action ID |
| --- | ---: | ---: | ---: |
| 0 | 1/16 | 4 | 1 |
| 1 | 1/8 | 1 | 3 |
| 2 | 1/4 | 1 | 4 |
| 3 | 1/8 | 3 | 6 |

The four natural-value actions (0, 2, 5, 7) still have a cost and a noise rate, but their true SCM result is identical for all hypotheses; they therefore provide **zero information** about the mask. They are not chosen by either planner.

Every hypothesis has equal initial probability `1/16`. No mechanism-dependent noise, channel drift, correlated attempts, unobserved confounding in the noise process, nor operational failure costs are modeled.

## Rational Bayesian update

For history $D = \{(a_t,o_t)\}_{t=1}^n$, posterior weights are computed using Python's exact `fractions.Fraction`. For each mask $H_j$:

$$
P(H_j\mid D)=\frac{P(H_j)\prod_t P(o_t\mid H_j,a_t)}{\sum_k P(H_k)\prod_t P(o_t\mid H_k,a_t)}.
$$

Zero-likelihood elimination from v0.19 is *not* reused. All declared errors are strictly between zero and one-half, hence every hypothesis initially possible remains possible after any finite number of attempted observations.

In particular, for the same action with the same error rate, opposite readings cancel exactly when obtained under the assumed independent and stationary symmetric channel. This is a property of the toy observation model, **not** evidence that real conflicting measurements automatically cancel.

## Two deliberately different experiment planners

1. `greedy_choice`: maximize the expected Shannon information gain **per unit action cost** for the *next attempt*. With current posterior $w$, the information gain is

   $$
   I(H;O\mid D,a)=h_2(P(O=1\mid D,a))-h_2(\epsilon_a).
   $$

   Here $h_2(p)=-p\log_2 p-(1-p)\log_2(1-p)$. This uses floating-point bits **for ranking only**; it does not claim globally optimal final classification under a budget.

2. `exact_budget_plan`: for an **integer available budget of at most four cost units**, maximize expected final **full-mask MAP classification accuracy**, integrating over both possible noisy responses at every step and permitting repeated actions. The dynamic program uses exact rational probabilities:

   $$
   V(w,b)=\max\left\{\max_j w_j,\quad \max_{a:c_a\le b}\sum_{o\in\{0,1\}}P(o\mid w,a)V(w_{a,o},b-c_a)\right\}.
   $$

   The first option means **stop now**. In ties, prefer lower cost and then smaller action ID. Because costs are positive integers and the budget strictly decreases, the dynamic program terminates. The result is exact **only under the specified 16-mask prior, channel model, available actions, objective and budget**.

A policy maximizing information per cost does not necessarily maximize final MAP correctness. The difference is reproducible:

- Uniform prior, cost-budget 4: greedy information-per-cost initially selects action `3`, although the most reliable action `1` has greater *raw* information gain but costs four units.
- After one reading of action `3`, the one-step greedy information-per-cost policy selects action `3` again: new evidence about the same uncertain bit is still informative.
- With that same posterior but just **one additional cost unit**, the exact MAP optimizer instead selects action `4`, because learning a different mechanism bit improves the expected *whole-mask* classification rate more than repeating the first measurement.

Under the uniform prior, exact expected final full-mask MAP success at budgets 0, 1, 2, 3, 4 equals **1/16**, **7/64**, **21/128**, **343/2048**, and **49/256**, respectively. These values are not an empirical model's accuracy and not a guarantee that the realized true mask will be the chosen MAP estimate.

## Reproduction

No pip packages, API credentials, GitHub Actions quota assumptions or access to private data are required. From the repository root:

```bash
python noisy_design.py check
python noisy_design.py report
python noisy_design.py plan --family F17_DIRECT --budget 2
python noisy_design.py plan --family F17_DIRECT --budget 1 --observe 3=1
python noisy_design.py plan --family F17_DIRECT --budget 1 --observe 3=1 --observe 3=0
python noisy_design.py replay --family F17_DIRECT --mask 5 --action 3 --flip
python -m unittest discover -s tests -v
```

`replay --flip` deliberately injects the requested contrary reading; it does not sample a real noisy sensor. The saved JSON report enumerates exact posterior-based decisions for **all seven existing families**, and `check` validates both pinned inputs and the derived report byte for byte.

## Interpretation and limits

- **Noiseless identification (v0.19)**: four informative interventions are necessary and sufficient *with perfect observation*.
- **Noisy finite evidence (v0.20)**: exact certainty is impossible with finite repetitions and strictly positive symmetric flip probabilities; the planner instead optimizes a *probabilistic* decision quality under a defined cost budget.
- **Cost** is an invented integer weight, not a monetary price or real-world resource measurement.
- **Information gain** and **expected MAP accuracy** are different optimization objectives. Neither directly measures comprehension of this language by a new AI.
- Observational equivalence of the candidate SCMs, fidelity to English meaning, and general causal identification are separate research questions.
- The example background index and action IDs are **not** language-production rules. The released ALCG language and published pattern dictionary are unchanged.

### 中文範圍說明

此版本將 v0.19 的無雜訊精確辨識，擴充為「有限候選機制、已知觀測錯誤率、成本不同、允許重複介入」的合成實驗。後驗機率與固定預算的 MAP 成功率使用精確有理數運算；資訊量則使用浮點近似計算。每一項數字都來自事先指定的布林模型與假設性雜訊，不是現實世界測量，也不是跨 AI 語義理解的實測結果。任何有限次數的觀測都不能在此模型中保證 100% 機制辨識；跨領域的因果解釋與中觀函數仍需另外研究。
