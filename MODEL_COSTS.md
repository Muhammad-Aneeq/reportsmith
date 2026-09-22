# MODEL_COSTS

Spec 00 D requires a realistic monthly estimate and a "keep it cheap" section. The numbers
below are **measured**, not modelled: the token counts come from the provider's own
`usage_metadata`, captured by `OpenAIComposer` and totalled by `evals/run_fidelity.py`.

An earlier version of this page was an estimate. It was wrong by 2.5× on output tokens,
because it did not account for reasoning tokens. That is the usual failure mode of a cost
page, and it is why the counts are now instrumented rather than guessed.

## Default mode costs nothing, and that is not a trick

The LLM is **mocked by default**. `MockComposer` assembles a factual paragraph from the
section's own figures — no model, no network, no key. Every test run, every CI job and every
screenshot in `docs/` was produced that way.

| Activity | Cost |
|---|---|
| `make dev`, `make demo`, `make month1/2` | **$0.00** |
| `make test` (383 backend + 38 frontend) | **$0.00** |
| `make evals-gate` (all three gates) | **$0.00** |
| `make capture` (14 screenshots, verified) | **$0.00** |
| Every CI run | **$0.00** — no key is configured, and none is needed |

That is a design decision. A portfolio repo that needs a funded API key to demonstrate
anything is a repo most readers will never actually run.

## Live mode — measured

Model: **`gpt-5.6-luna`**, pinned via `REPORTSMITH_MODEL`.
Rate at time of measurement: **$0.20 / 1M input, $1.20 / 1M output**.

Measured over a full run — two periods, three narrative sections each:

```
PASS numeric-fidelity 100.00% (87/87 figures across 6 section(s))
  tokens: 4,547 prompt + 3,920 completion across 6 sections
```

| | prompt | completion | cost |
|---|---:|---:|---:|
| One section (mean of 6) | 758 | 653 | **$0.00093** |
| **One pack** (3 narrative sections) | 2,274 | 1,960 | **$0.0028** |
| Two packs — a full `make demo` | 4,547 | 3,920 | **$0.0056** |

**A full monthly pack costs about a third of a cent.**

The prompt is small because of the architecture, not because of tuning: a narrative section
receives its own figure list and its tone rules, and nothing else. Not the ledger, not the
other sections, not the raw statements. Spec 13 §12 guessed *"tens of cents"*; the measured
figure is roughly a hundredth of that.

**Completion is the larger half of the bill** — 653 output tokens against 758 input, and
output is priced 6× higher. That is reasoning tokens, and it is the line worth watching if
the model is changed.

### Monthly

| Usage | Packs/month | Cost |
|---|---:|---:|
| One entity, monthly close | 1 | **$0.003** |
| Ten entities | 10 | **$0.03** |
| Fifty entities | 50 | **$0.14** |
| Heavy iteration: 200 live runs while tuning prompts | 200 | **$0.56** |

At any realistic volume this is a rounding error. The interesting cost of this product is
the reviewer's time, which is what the design actually optimises.

## The retry is bounded, on purpose

Spec 12 F5 allows exactly **one** re-draft. On a second failure the offending sentence is
dropped rather than re-attempted, so worst-case spend per section is exactly two calls.
`MAX_ATTEMPTS = 2` is a constant in `narrate/graph.py`, not a configurable budget somebody
can raise under deadline pressure.

Observed in practice: **one retry across twelve live drafts.** The first attempt at
`2024-07/performance_commentary` stated a figure the data did not support; the re-draft was
clean. That is the mechanism working, and it cost one extra call.

## Keep it cheap

1. **Leave it in mock mode.** Everything except prose quality is identical and every gate
   passes. Live mode is for checking that the prompt produces readable English.
2. **Do not narrate on every assembly.** `create_pack(narrate=False)` gives tables, KPIs,
   flags and gaps with no model call at all — useful while iterating on a template.
3. **Fewer, larger narrative sections** cost less than many small ones: the system prompt is
   re-sent per section and is most of the input.
4. **Prompt caching** applies to the system prompt, which is identical across sections and
   periods. Not currently exploited; it would cut input cost materially on a large pack, and
   input is the cheaper half, so it has not been worth the complexity.
5. **Pin the model.** `REPORTSMITH_MODEL` is explicit. A silent provider upgrade is how a
   "cheap" project becomes an expensive one with no commit to blame — and how a cost page
   like this one quietly becomes fiction.

## Reproducing these numbers

```bash
cp .env.example .env          # add OPENAI_API_KEY, set REPORTSMITH_LLM=live
make evals                    # prints the token totals above
```

The per-section breakdown lands in `evals/results/fidelity-live-gpt-5.6-luna.json`, committed,
so the claim is checkable rather than asserted.

## What is not costed here

No hosting, no Azure, no vector store, no managed anything. This is a Track-1 project: a
FastAPI process, a SQLite file, a static SPA. It runs on a laptop, and `docker compose up`
runs the whole thing locally with no cloud account.

Sources for the rate: [OpenAI · GPT-5.6](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/) ·
[OpenRouter](https://openrouter.ai/openai/gpt-5.6-luna)
