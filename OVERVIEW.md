# ReportSmith · Overview

*A map of the project: what it does, how it is put together, what is proven, and where to
look. Read this before the code; read [README.md](README.md) if you just want to run it.*

---

## 1 · The one-paragraph version

Every finance team rebuilds the same monthly pack by hand. ReportSmith makes the pack a
**versioned YAML template** instead: sections, data bindings, tone rules, defined once. Each
period it assembles from live data — tables and KPIs computed in code, narratives drafted
from *that section's bound figures only* — and every number the model writes is verified
against those figures before it survives. A human then reviews, edits (tracked), approves
section by section, and signs. Nothing is issued until they do, unresolved gaps block
issuance unless explicitly waived, and issued packs are immutable and hashed.

The demo is `make month2`: same template, next period, **identical structure, changed
numbers**.

---

## 2 · The four claims, and what backs each

| Claim | Mechanism | Evidence |
|---|---|---|
| **Tables and KPIs are deterministic** | zero LLM in `assemble/`; a closed declarative selector grammar; `Decimal` money; total ordering with tiebreaks | committed golden files, byte-compared in CI; `test_golden_assembly.py` |
| **The model cannot invent a number** | `numcheck` checks every numeric token against supplied figures *at the precision the author wrote*; no tolerance parameter | **87/87 figures verified live** against `gpt-5.6-luna`; 100% gate, plus a self-test that proves the gate can fail |
| **The model cannot free-read** | `compose_section(frame, tone_rules, style)` — no parameter exists through which the ledger or other sections could arrive | `test_narrate.py` plants a canary outside the frame and asserts it never reaches the prompt |
| **Nothing is issued without a human** | explicit transition table with named guards, server-side; write-once AI draft; edit revokes approval; waivers require a reason | `test_state_machine.py` walks every (status × event) pair; `test_governance_artifacts.py` |

---

## 3 · How a pack is built

```
  template.yaml ──┐
                  │  (1) BIND          adapters/  →  Bound(frame) | Gap(reason, detail)
                  │      one section per template section, ALWAYS
                  ▼
  ledgerfab ──────┼──▶ (2) ASSEMBLE    assemble/  →  tables · KPIs · flags   [no LLM]
  spendsort ──────┤                                  + figure_refs for narratives
  statementlens ──┘
                  │  (3) NARRATE       narrate/   →  draft → numcheck → retry once
                  │                                  → lint → numcheck re-verify
                  ▼
                     (4) REVIEW        tracked edits · per-section approval
                  │
                  ▼
                     (5) ISSUE         guards → sign-off → md + PDF + snapshot + hash
```

**Step 1 is the one worth understanding.** `resolve_binding` returns a sum type with two arms
and **no exception path** — a bare `except Exception` converts every adapter failure into a
`Gap`. So a section can never silently vanish from a pack. `test_no_silent_omission.py`
drives twelve adversarial adapter behaviours (raises, returns `None`, wrong columns, wrong
types, 5,000 rows, unicode soup) and asserts the section count invariant holds for all of
them. A crash gets noticed; a missing section in a board pack gets *signed*.

---

## 4 · Repository map

```
reportsmith/
├── backend/
│   ├── ledgerfab/          VENDORED engine + statement emitter (zero local changes,
│   │                       drift-checked by a SHA manifest in VENDORED.md)
│   ├── numcheck/           STANDALONE package — zero app imports, own pyproject and tests.
│   │                       Belongs to StatementLens; lives here until its P6. See ORIGIN.md
│   └── app/
│       ├── template/       closed 4-type schema · versioned store · the shipped default pack
│       ├── adapters/       SourceAdapter protocol · closed selector grammar · three sources
│       ├── analysis/       ratios + YAML flag rules, to StatementLens's P4/P5 shapes
│       ├── assemble/       deterministic renderers · structure_hash / value_digest
│       ├── narrate/        LangGraph pipeline · Composer protocol · tone linter
│       ├── issue/          transition table · tracked edits · immutable archive · md/PDF
│       └── service.py      the ONLY path that changes state — guards cannot be bypassed
├── frontend/               Vite + React + aurora; six screens; capture.mjs verifies them
├── evals/                  three gates + committed golden files + live evidence
├── fixtures/               gen_fixtures.py RUNS SpendSort to produce a real export
└── docs/                   template guide · adapter contracts · governance · demo script
```

---

## 5 · What is composed, and what had to be built

The brief said *compose siblings, never rebuild*. What that meant in practice:

| | Status | What was done |
|---|---|---|
| `ledgerfab` engine | built, elsewhere | **vendored**, byte-identical, provenance recorded |
| `ledgerfab.statements` emitter | built in StatementLens | **vendored** with the engine — this is what gives the pack real P&L, balance sheet and cash flow |
| SpendSort export | complete, runnable | adapter against its **real** 15-column schema; fixtures generated by *running it* |
| StatementLens ratios/flags | **not built upstream** (P3 of P11) | computed in-repo **to upstream's own P4/P5 shapes**, so the swap is one reader change |
| `numcheck` | **not built upstream** (its P6) | **originates here**, standalone, verified liftable into an empty directory |

Nothing imports across a sibling path at runtime — reuse means vendored code plus committed
fixtures, never a path dependency that would make the repo unclonable.

---

## 6 · Running it

```bash
make install
make dev                  # API :8000, SPA :5173 — no API key needed, mock is the default
make demo                 # both periods end to end, then the month diff
make test                 # 383 backend + 38 frontend
make evals-gate           # the three CI gates + the self-test that proves one can fail
make capture              # screenshot AND verify all six screens, both themes
```

For the live model: copy `.env.example` to `.env`, add `OPENAI_API_KEY`, set
`REPORTSMITH_LLM=live`. A pack costs about **$0.003**.

---

## 7 · Current state

| | |
|---|---|
| Backend tests | **383** passing (169 are the vendored engine's own, run here) |
| Frontend tests | **38** passing |
| Lint / types | ruff clean · mypy `strict` clean |
| Eval gates | fidelity 100% · gate self-test · state machine · E2E · golden files |
| Live model | **87/87 figures verified** against `gpt-5.6-luna`, one retry in twelve drafts |
| Cost to build | **$0.00** mock · **$0.0056** for the one live two-period run |
| Not done | the demo **video** (footage recordable via `node frontend/record-demo.mjs`; shot list in `docs/DEMO_SCRIPT.md`) |

---

## 8 · The five decisions that shaped it

1. **A closed selector grammar, not an expression language** (D-008). Determinism, safety and
   a schema-validatable editor, all from one fence. A template is user input; `eval` in user
   input is a remote-code-execution hole.
2. **A deliberately faulty mock** (D-014). A 100% fidelity gate is satisfiable by writing no
   numbers, and a gate never seen red proves nothing. CI runs the broken composer and
   *requires* the check to fire.
3. **The default pack ships a real, unresolvable gap** (D-006). `segment_performance` binds to
   a dataset that genuinely does not exist, and is `required` — so the gaps panel, the
   blocking guard and the waiver flow run on the default path, not in a fixture.
4. **Two hashes over disjoint inputs** (D-016). One hash can only say "different". Two make
   *"identical structure, changed numbers"* a claim a test can falsify.
5. **Editing an approved section revokes approval** (D-012). Otherwise "all sections
   approved" can be true of text nobody approved — the one case where it matters.

---

## 9 · Two mistakes worth reading

Both are written up in full — they are the most useful part of the history.

**The stale directory read** (BLOCKERS B0). Phase 0 concluded from a directory listing that
two sibling projects were spec-only. They were not. It cost a day of planning aimed at the
wrong constraints and produced a worse design — the pack avoided revenue entirely while a
working statement emitter sat in the sibling. The tell: Phase 0 verified the data engine by
**running** it, and that finding held. The two that were wrong were the two taken from a
listing.

**The unverified screens** (BLOCKERS B6). Screenshots were going to be taken and shipped. The
capture script asserts instead, and immediately found a duplicate React key that collapsed
three sign-off blockers into one, an absolute filesystem path leaking into the *issued
document*, and a month-diff comparing the wrong column so every row read "ok → ok".

Same lesson twice: **run it, look at it, and assert on what you see.**

---

## 10 · Where to look next

| Question | File |
|---|---|
| How do I write a template? | [docs/TEMPLATE_GUIDE.md](docs/TEMPLATE_GUIDE.md) |
| What does each adapter publish? | [docs/ADAPTER_CONTRACTS.md](docs/ADAPTER_CONTRACTS.md) |
| What exactly does sign-off guarantee? | [docs/GOVERNANCE.md](docs/GOVERNANCE.md) |
| What would this cost? | [MODEL_COSTS.md](MODEL_COSTS.md) — measured, not estimated |
| What is unfinished, and why? | [BLOCKERS.md](BLOCKERS.md) |
| What should the siblings fix? | [FINAL_REPORT.md](FINAL_REPORT.md) → SIBLING_NOTES |
| How was it built? | [PLAN.md](PLAN.md) · [PROGRESS.md](PROGRESS.md) |
