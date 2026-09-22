# Governance — the state machine, the waiver, and what a hash covers

Spec 13 F5 and F6, as built. This is the document to read before trusting an issued pack.

## The state machine

```
   draft ──submit──▶ in_review ──signoff──▶ signed ──issue──▶ issued
                          ▲                    │              (terminal)
                          └──────reopen────────┘
```

`app/issue/states.py` holds this as an explicit `(status, event) → status` table. A pair
absent from the table is illegal — not "undefined behaviour", but a refusal naming what *is*
legal from here. `test_state_machine.py` walks every (Status × Event) combination, so adding
a transition by accident fails the suite.

`signoff` and `issue` are separate edges even though one endpoint performs both. Spec 13 §7
lists no `issue` endpoint, so adding one would be a gratuitous divergence — but keeping the
edge is what lets the suite assert that `issued` is unreachable from `in_review`, which is
the property that actually matters.

## The guards

Both run server-side, in `check_guards`, reached only through `app/service.py`. The UI's
disabled button is a courtesy; the guard is the control, and the tests call the API with the
UI bypassed.

| Guard | Refuses when |
|---|---|
| `sections_unapproved` | any section is not approved |
| `gap_unresolved` | a **required** section has a gap nobody waived |
| `already_issued` | the pack already has an archive |

`check_guards` returns **every** failure, not the first. A reviewer should see the whole list
rather than fix one thing and discover another.

## What makes "all sections approved" true

Editing an approved section **revokes its approval** (`D-012`). Without that rule the guard
could pass over text nobody approved — the one case where the guarantee is load-bearing.

Only `narrative` sections are editable (`D-011`). A table is a deterministic function of
(data, template); editing its cells would break the golden-file contract and reduce the
archive's hash to a claim about nothing. Disagreeing with a table is a *template* change,
which is versioned and re-runnable.

## Waivers

A waiver is how a pack goes out with a known hole, on the record.

- It must name a section that exists **and actually has a gap**. Waiving something that is
  fine is refused.
- It must carry a **reason**. A waiver whose reason is unrecorded is indistinguishable from
  nobody having looked, which is exactly what the mechanism exists to rule out.
- It records the signer and the timestamp, and lands in three places: the `signoffs` row, the
  archive's `MANIFEST.json`, and the issued markdown itself.

The shipped template carries one real, unresolvable gap on purpose, so this flow runs on the
default path rather than only in a test.

## What the hash covers

```
content_hash = SHA-256 over {
    markdown_sha256,       # the document
    pdf_sha256,            # or null — a pack issued without a PDF hashes differently
    data_snapshot_hash,    # the bound data it was built from
    template_ref,          # e.g. monthly_management_pack@v1
}
```

All four together. A hash over the markdown alone would let the data snapshot be swapped
undetected — and the snapshot is the part that says what the numbers were.

`GET /api/archive/{id}/verify` re-computes each component against `MANIFEST.json` and names
which artefact changed. The manifest sits beside the files, so an archive can be verified by
someone holding the directory and not this application.

## Immutability

`archives` is INSERT-only. No UPDATE or DELETE statement against it exists anywhere in
`app/`, and `test_no_update_or_delete_against_archives_anywhere_in_the_app` greps every
module to keep that true. Re-issuing raises before anything is written.

## PDF degrades; it never blocks

If reportlab is missing or a render fails, `render_pdf` returns `None`, the manifest records
`pdf_available: false`, and issuance proceeds. A pack a controller has reviewed, signed and
waived gaps on should not be un-issuable because a typesetting library is absent — the
governance record is the markdown and the hash, not the typography.

## Manual acceptance script

Browser automation was unavailable on the build machine, so the UI path was verified through
the API. To check it by hand:

1. `make dev` → http://localhost:5173
2. **Templates** — the default pack loads. Type `type: nonsense` into a section; the
   validator names the path and the problem. Undo.
3. **Pack run** — assemble a period. Eleven sections; one gap in the panel, marked as
   blocking issuance.
4. **Review** — `j`/`k` to move, `a` to approve, `e` to edit a narrative. Save an edit: the
   word-level diff appears and the section's approval is revoked.
5. **Sign-off** — the sign button is disabled and the checklist says why. Approve
   everything; it stays disabled until the gap has a waiver reason.
6. Sign. The pack issues and the content hash appears.
7. **Archive** — press *Verify now* (intact). Edit `archive/pack-00001/pack.md` by hand and
   press it again: it reports `pack.md has been modified since issuance`.
8. **Month diff** — run a second period and compare: structure identical, numbers changed.
