"""The CLI behind the Makefile: `month1`, `month2`, `diff`, `demo`, `verify`."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from app.db import init_db, session_scope
from app.issue.archive import verify_archive
from app.periods import default_period, next_period
from app.service import (
    approve_section,
    create_pack,
    get_pack,
    pack_to_json,
    signoff,
)
from app.settings import settings

WAIVER_REASON = (
    "No segment dimension exists in the current data sources. Reviewed and accepted for "
    "this period; to be revisited when segment reporting is available."
)


def _run_period(period: str, *, auto_signoff: bool) -> dict[str, Any]:
    with session_scope() as db:
        pack = create_pack(db, "monthly_management_pack", period)
        data = pack_to_json(db, pack)
        print(f"\nPack {pack.id} · {period} · {data['template_ref']}")
        for section in data["sections"]:
            mark = "GAP" if section["gaps"] else "ok "
            note = section["gaps"][0]["reason"] if section["gaps"] else section["type"]
            print(f"  {mark} {section['section_key']:24s} {note}")

        if data["gaps"]:
            print(f"\n  {len(data['gaps'])} gap(s); {len(data['blockers'])} blocking issuance")

        if not auto_signoff:
            return data

        for section in data["sections"]:
            approve_section(db, section["id"], "A. Controller")

        waivers = [
            {"section_key": g["section_key"], "reason": WAIVER_REASON}
            for g in data["gaps"]
            if g["required"]
        ]
        pack = signoff(db, pack.id, settings.signer_name, waivers)
        final = pack_to_json(db, pack)
        print(
            f"  signed by {final['signoff']['signer']} · {len(waivers)} waiver(s) · "
            f"status {final['status']}"
        )
        print(f"  archived  {final['archive']['content_hash'][:16]}  {final['archive']['md_ref']}")
        return final


def cmd_month(args: argparse.Namespace) -> int:
    init_db()
    period = args.period or (
        next_period(default_period().id).id if args.which == 2 else default_period().id
    )
    _run_period(period, auto_signoff=not args.no_signoff)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Both periods, end to end — the repeatability demo (spec 13 F7)."""
    init_db()
    first = default_period().id
    second = next_period(first).id
    a = _run_period(first, auto_signoff=True)
    b = _run_period(second, auto_signoff=True)

    print("\n" + "=" * 68)
    print("MONTH-DIFF")
    print(f"  {a['period']}  structure {a['structure_hash'][:16]}  values {a['value_digest'][:16]}")
    print(f"  {b['period']}  structure {b['structure_hash'][:16]}  values {b['value_digest'][:16]}")
    print(f"  identical structure : {a['structure_hash'] == b['structure_hash']}")
    print(f"  changed numbers     : {a['value_digest'] != b['value_digest']}")
    print("=" * 68)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    result = verify_archive(args.pack_id)
    print(f"archive {args.pack_id}: {'OK' if result['ok'] else 'TAMPERED'}")
    for problem in result.get("problems", []):
        print(f"  - {problem}")
    return 0 if result["ok"] else 1


def cmd_show(args: argparse.Namespace) -> int:
    with session_scope() as db:
        print(pack_to_json(db, get_pack(db, args.pack_id))["status"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reportsmith")
    sub = parser.add_subparsers(dest="command", required=True)

    for which in (1, 2):
        p = sub.add_parser(f"month{which}", help=f"run period {which}")
        p.add_argument("--period")
        p.add_argument("--no-signoff", action="store_true")
        p.set_defaults(func=cmd_month, which=which)

    p = sub.add_parser("demo", help="both periods + the month-diff")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("verify", help="verify an issued archive")
    p.add_argument("pack_id", type=int)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("show", help="print a pack's status")
    p.add_argument("pack_id", type=int)
    p.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
