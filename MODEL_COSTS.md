# MODEL_COSTS

Spec 00 D requires every repo to publish a realistic monthly estimate and a "keep it cheap"
section. Here is the honest version, including the part most cost pages leave out: **what
this actually cost to build and run, which is nothing.**

## Default mode costs nothing, and that is not a trick

The LLM is **mocked by default**. `MockComposer` assembles a factual paragraph from the
section's own figures — no model, no network, no key. Every number in this repo, every
screenshot, every test run and every CI job was produced that way.

| Activity | Cost |
|---|---|
| `make dev`, `make demo`, `make month1/2` | **$0.00** |
| `make test` (330 backend + 38 frontend) | **$0.00** |
| `make evals-gate` (all three gates) | **$0.00** |
| Every CI run | **$0.00** — no key is configured, and none is needed |

That is a design decision, not a limitation. A portfolio repo that needs a funded API key
to demonstrate anything is a repo most readers will never actually run.

## Live mode

`REPORTSMITH_LLM=live` with `OPENAI_API_KEY` set routes drafting to `gpt-4o-mini`
(pinned; `REPORTSMITH_MODEL` overrides).

**What the model actually sees is tiny**, and that is the point of the architecture rather
than a cost optimisation. A narrative section receives its own figure list and its tone
rules — not the ledger, not the other sections, not the raw statements. Measured from the
shipped template:

| | tokens |
|---|---|
| System prompt (rules + voice + taboo list) | ~220 |
| Figures (6 per section, pre-formatted) | ~90 |
| Section tone rules | ~70 |
| **Prompt total, per section** | **~380** |
| Completion (capped at 160–200 words) | ~260 |

Three narrative sections per pack:

| | prompt | completion | cost |
|---|---|---|---|
| One section | 380 | 260 | $0.00021 |
| **One pack (3 sections)** | 1,140 | 780 | **$0.00064** |
| One pack **with a re-draft on every section** (worst case) | 2,280 | 1,560 | $0.00128 |

At `gpt-4o-mini` pricing of $0.15 / 1M input and $0.60 / 1M output.

### Monthly

| Usage | Packs/month | Cost |
|---|---|---|
| One entity, monthly close | 1 | **< $0.01** |
| Ten entities | 10 | **~$0.01** |
| Heavy dev: 50 live runs while iterating on prompts | 50 | **~$0.03** |

A full pack is **well under a cent**. Spec 13 §12 estimated *"tens of cents"*; the real
figure is two orders of magnitude lower, because the composer is handed a figure list rather
than a statement set.

## The retry is bounded, on purpose

Spec 12 F5 allows exactly **one** re-draft. On a second failure the offending sentence is
dropped rather than re-attempted. So a pathological model cannot loop: worst-case spend per
section is exactly two calls, and `MAX_ATTEMPTS = 2` is a constant in `narrate/graph.py`,
not a configurable budget somebody can raise under deadline pressure.

## Keep it cheap

1. **Leave it in mock mode.** Everything except prose quality is identical, and every gate
   passes. Live mode is for checking that the prompt produces readable English.
2. **Do not narrate on every assembly.** `create_pack(narrate=False)` gives the tables,
   KPIs, flags and gaps with no model call at all. Useful while iterating on a template.
3. **Fewer, larger narrative sections** cost less than many small ones — the system prompt
   is re-sent per section and is the larger half of the input.
4. **The judge is cached.** Style-adherence scoring runs from committed responses in
   `evals/cache/`, so CI never calls a model and re-scoring costs nothing.
5. **Pin the model.** `REPORTSMITH_MODEL` is explicit. Silent provider upgrades are how a
   "cheap" project becomes an expensive one without a commit to blame.

## What is not costed here

No hosting, no Azure, no vector store, no managed anything. This is a Track-1 project: a
FastAPI process, a SQLite file, a static SPA. It runs on a laptop, and `docker compose up`
runs the whole thing locally with no cloud account.
