# LLM-judged answer-quality measurement (hibrid study 2)

_Judge: frontier tier (force=cloud_strong, cli:claude), blind to which model produced each answer. 8 tasks. 2026-06-30 08:42:25 CEST._

Question: when hibrid keeps work local, does the answer lose quality vs the frontier model? Each task was answered twice (AUTO = what hibrid served; STRONG = forced frontier) and an impartial frontier judge scored both 0.0-1.0 against a fixed per-task criterion, without being told which model wrote which answer.

## Headline

- Mean **auto/local quality 0.812** vs **frontier 0.912** -> local retained ~89% of frontier quality.
- **Parity rate 75.0%** of locally-served answers scored >= 0.7; 75.0% scored within 0.1 of the frontier answer.

## Per-task scores

| # | task_type | auto tier | q(auto/local) | q(frontier) | delta |
|---|---|---|---|---|---|
| 1 | loop_refine | local_free | 0.5 | 1.0 | -0.5 |
| 2 | loop_refine | local_free | 1.0 | 1.0 | 0.0 |
| 3 | simple | local_free | 1.0 | 1.0 | 0.0 |
| 4 | simple | local_free | 0.9 | 0.9 | 0.0 |
| 5 | general | local_free | 0.8 | 0.9 | -0.1 |
| 6 | general | local_free | 0.9 | 0.9 | 0.0 |
| 7 | deep_reason | local_free | 0.5 | 0.9 | -0.4 |
| 8 | deep_reason | local_free | 0.9 | 0.7 | 0.2 |

## Reading the result (honest)

- On 6 of 8 tasks the local answer matched or beat the frontier judge score (delta >= 0 or -0.1) - genuine parity on easy code/NLP and even one reasoning task.
- Two clear gaps: a code fix (0.5 vs 1.0) and the Omega(n log n) sorting proof (0.5 vs 0.9). These are exactly the harder items where a 1-3B local model is weakest - and exactly what a smarter, output-aware escalation signal should catch and send up.
- In this unloaded run the router kept ALL 8 tasks local (including simple and deep_reason). Under the 3-agent load earlier, QualityGuard saw simple route to the cheap paid tier instead. So routing of borderline classes shifts with measured latency/load - a real behaviour, and a reason the quality gap above is a conservative (worst-ish) picture for a tiny CPU box.
- Single judge, n=8, short tasks. Indicative, not a leaderboard.
