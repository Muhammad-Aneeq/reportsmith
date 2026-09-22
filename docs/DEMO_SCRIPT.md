# Demo script — 80 seconds

The video is the one launch requirement this repo does not contain (spec 00 E). It needs a
person and a screen recorder; everything it needs to *show* is built and reproducible. This
is the shot list, with the exact commands and the exact clicks.

**Setup — one command, then two:**

```bash
make clean && make dev          # API :8000, SPA :5173
# in another terminal:
cd backend && python -m app.cli demo                              # packs 1 and 2, issued
cd backend && python -m app.cli month1 --period 2024-06 --no-signoff   # pack 3, mid-review
```

That is the state every screenshot in `docs/screenshots/` was taken from, so the recording
and the README agree.

---

## 0:00–0:10 · The claim

**Terminal.** Type it live; it takes about four seconds.

```
make month2
```

Let the output land:

```
2024-08  structure 596213ff41816fc3  values 04c58e9eb76c7a91
identical structure : True
changed numbers     : True
```

> "Same template, next month. Identical structure, new numbers. Nobody assembled anything."

---

## 0:10–0:25 · Define it once

**Templates screen.** Scroll the YAML slowly — it is the whole product in one file.

Land on `taboo_phrases` and `rounding`. Then type `type: timeline` into a section and let the
validator reject it inline.

> "Four section types. No fifth. The bindings are a closed grammar — no expressions, so the
> same data and the same template always produce the same tables."

Undo. Do not save.

---

## 0:25–0:40 · Run a period, and see what is missing

**Pack run.** Choose a period, press *Assemble pack*. The per-section binding table fills.

Scroll straight to the **Gaps** panel and rest there.

> "Three sections could not bind. They are not missing from the pack — they are *in* the
> pack, marked, with the reason. A section that quietly disappears from a board pack is the
> failure this whole thing exists to prevent."

---

## 0:40–1:00 · The governance beat — the money shot

**Review**, pack 3, click *Performance commentary*.

Point at, in order:

1. the **6 figures verified** badge,
2. the **Figures this section could cite** chips — "that list is the model's entire numeric
   universe; anything else it writes does not survive",
3. press <kbd>e</kbd>, change a sentence, save.

The word-level diff appears and the **approval badge flips back to Unapproved**.

> "The AI draft is kept beside the edit — green is what a person added. And editing an
> approved section un-approves it, so 'all sections approved' can never be true of text
> nobody approved."

---

## 1:00–1:15 · It refuses

**Sign-off**, pack 3. The button is disabled and the checklist says why: 11 unapproved, three
unresolved gaps.

Approve everything (hold <kbd>a</kbd>/<kbd>j</kbd> through the review list, or click). Come
back. **Still disabled** — the gaps remain.

> "It will not issue. Not because the UI is hiding the button — the guard is server-side and
> the tests call the API with the UI bypassed."

Type a waiver reason into one gap. Then the others. The button lights.

Press it.

---

## 1:15–1:25 · What was issued

**Archive.** The pack is there with its hash. Press **Verify now** → *intact*.

Then, in the terminal, tamper with it:

```bash
echo "a line nobody signed" >> archive/pack-00003/pack.md
```

Press **Verify now** again → *pack.md has been modified since issuance*.

> "The hash covers the markdown, the PDF, the data snapshot and the template version,
> together. Anyone holding the directory can check it — the manifest sits next to the files."

---

## 1:25–1:30 · Close on the diff

**Month diff.** Two tiles: **Structure · Identical**, **Numbers · Changed**.

> "Define the pack once. Review forever after."

---

## Notes for the recording

- **Leave the `mock LLM` badge visible.** It is in the header on every screen and it is the
  honest framing: none of this needed a model to be running. Do not crop it out.
- The synthetic-data banner should stay in frame for the same reason.
- Use the **dark** theme for the recording and flip to light once, briefly, on the Month diff
  screen — both are designed, and a one-second flip proves it without a detour.
- `prefers-reduced-motion` is respected, so if your recorder sets it the transitions will be
  instant. Turn it off for a smoother capture.
- Do not record `make test`. A wall of green dots is not a demo, and the README already
  states the numbers.

## What to say if asked "did an AI write that commentary?"

The honest answer, and the better story: in this recording, **no** — the default composer is a
deterministic mock that assembles the sentence from the figures. The point of the product is
not that a model wrote it. It is that **whatever wrote it, every number is checked against the
bound data before it survives, the draft is preserved, and a human signs.** Swap
`REPORTSMITH_LLM=live` and the same gates apply, unchanged.
