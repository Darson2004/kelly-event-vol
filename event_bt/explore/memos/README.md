# Meta-research memos (2026-08-31)

Three parallel deep-research threads on "how to research better" commissioned
before the top-decile signal exploration. Full memo texts are not published; the key operational content is distilled
into ../PROTOCOL.md.

1. **hyperresearch (Jordan Gibbs)** — github.com/jordan-gibbs/hyperresearch
   dissected (repo read for verbatim prompts). Stolen mechanics:
   committed-position + calibration block (confidence bucket, boundary
   conditions, "what would flip this"), corpus-critic pre-verdict question
   ("what test, if run, would overturn this?" -> run it), vault/registry with
   dedup-before-create, loci scoring (Importance/Uncertainty/Disagreement/
   Decision-Impact) for compute allocation, tool-locked critic (Read-only),
   coverage matrix with refuse-closure-while-uncovered. Its 16-step
   report-shaped pipeline does NOT port; exploration loops don't terminate in
   prose. Best files: tests/fixtures/golden_prompts/agents/
   depth_investigator_agent.md, dialectic_critic_agent.md.

2. **Exploratory agent landscape** — Anthropic multi-agent research blog
   (orchestrator-worker, effort quotas, token-breadth), STORM (perspective-
   conditioned question generation = cheapest coverage-widener), AI-Scientist
   (documented self-modification/unfair-baseline failures; BadScientist: LLM
   reviewers accept fabrications at up to 82% -> never rely on LLM judging
   alone), Google Co-Scientist (generate/debate/evolve, Elo tournament,
   Reflection verdict buckets), FunSearch/AlphaEvolve (PRE-COMMITTED automated
   evaluator is THE hallucination guard; ~80% honest nulls), AIDE/MLE-bench
   (tree search over experiments beats linear chat ~4x; monitor the TRACE for
   cheating, not just the report). 12 design principles distilled into
   PROTOCOL.md section 2.

3. **Honest signal mining statistics** — HLZ t>=3 hurdle / minimum Bayes factor
   exp(-t^2/2); BH-FDR q=0.10 with the FULL tested family as m; deflated
   Sharpe (DSR >= 0.95, N = ALL logged trials incl. agent exploration);
   PBO/CSCV with whole-earnings-season blocks; season-cluster bootstrap-t
   (24 clusters -> noisy SEs -> only large effects claimable); POWER LIMITS:
   n=193 liquid trades can only detect tail-rate doubling or rank-IC >= 0.25;
   subtle effects only findable in the ~3,700-event small-cap panel; rank/sign
   tests ONLY (never means on tail-driven P&L); cross-universe transfer =
   recognized practice (Jensen-Kelly-Pedersen replication logic) but treat as
   SIGN test with expected ~35%+ attenuation (McLean-Pontiff); the historical
   liquid cell is ALREADY-CONTAMINATED discovery data (we've seen aggregates);
   descriptive work is free ONLY on discovery data with registry-before-
   validation discipline (Dwork et al. reusable-holdout logic).
