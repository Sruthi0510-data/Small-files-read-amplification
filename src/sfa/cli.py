"""The command line, whose exit codes carry the argument.

  0  the layout is sound: the per-file term is a minority of modelled time
  2  the tool was handed something it cannot work with
  3  read amplification was found: the plan cannot see most of the cost
  4  the question cannot be answered from what was supplied

Three is a finding. Four is a refusal. A claim of a particular improvement that
no rewrite in the search reaches is a four, not a three, because the honest
answer is that the figure does not describe this table rather than that the
table is fine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from sfa.compaction import plan_compaction, scans_to_target, sweep_targets
from sfa.cost import PROFILES, UnknownProfileError, break_even_bytes, profile, scan_cost
from sfa.fixtures import events, uniform_large, uniform_small
from sfa.layout import MIB, Layout, LayoutError
from sfa.plan import compare, estimate
from sfa.pruning import prune_to

__all__ = ["main", "OK", "BAD_INPUT", "AMPLIFIED", "UNDETERMINED"]

OK = 0
BAD_INPUT = 2
AMPLIFIED = 3
UNDETERMINED = 4

BLIND_THRESHOLD = 0.5
"""The share of modelled time above which the plan is reporting the wrong thing.

Half. Not a statistical threshold, a statement: above it, more of the scan is
spent on work the plan cannot see than on work it can, so a reader optimising
from the plan is optimising the minority of their runtime.
"""

LAYOUTS = {"events": events, "uniform-small": uniform_small, "uniform-large": uniform_large}
TARGETS = (64 * 1024, 1 * MIB, 8 * MIB, 32 * MIB, 128 * MIB, 512 * MIB)


def _layout(name: str) -> Layout:
    """Build a named layout.

    No guard on the name. Argparse validates it against the same mapping through
    `choices`, so a check here would be unreachable, and branch coverage said so
    before this docstring did.
    """
    return LAYOUTS[name]()


def _mib(value: float) -> str:
    return f"{value / MIB:,.1f} MiB"


def _cmd_scan(args: argparse.Namespace) -> int:
    layout, storage = _layout(args.layout), profile(args.profile)
    cost = scan_cost(layout, storage)
    plan = estimate(layout)
    print(f"layout                {layout.name}")
    print(f"profile               {storage.name}")
    print()
    print("what the plan reports")
    print(f"  bytes scanned       {plan.bytes_scanned:,}")
    print(f"  rows scanned        {plan.rows_scanned:,}")
    print(f"  partitions scanned  {plan.partitions_scanned}")
    print()
    print("what the plan does not report")
    print(f"  files               {cost.file_count:,}")
    print(f"  median file         {_mib(layout.median_file_bytes)}")
    print(f"  break-even file     {_mib(break_even_bytes(storage))}")
    print()
    print(f"modelled scan         {cost.total_ms:,.0f} ms")
    print(f"  reading bytes       {cost.plan_visible_ms:,.0f} ms")
    print(f"  opening files       {cost.plan_blind_ms:,.0f} ms")
    print(f"  invisible to a plan {cost.plan_blind_share:.1%}")
    print(f"  amplification       {cost.amplification:.1f}x")
    if cost.plan_blind_share <= BLIND_THRESHOLD:
        print()
        print("most of this scan is reading data, which is what the plan reports")
        return OK
    print()
    print("most of this scan is opening files, which no plan reports")
    return AMPLIFIED


def _cmd_indistinguishable(args: argparse.Namespace) -> int:
    storage = profile(args.profile)
    result = compare(_layout(args.left), _layout(args.right), storage)
    print(f"profile               {storage.name}")
    print()
    print(f"  small layout plan   {result.left_estimate.rendered()}")
    print(f"  large layout plan   {result.right_estimate.rendered()}")
    print(f"  plans are equal     {not result.plan_sees_a_difference}")
    print()
    print(f"  small layout files  {result.left.file_count:,}")
    print(f"  large layout files  {result.right.file_count:,}")
    print(f"  modelled times      {result.left.total_ms:,.0f} ms and {result.right.total_ms:,.0f} ms")
    print(f"  ratio               {result.time_ratio:.1f}x")
    if not result.indistinguishable_but_different:
        print()
        print("the plans differ, or the times do not")
        return OK
    print()
    print("identical plans, and one takes an order of magnitude longer")
    return AMPLIFIED


def _cmd_prune(args: argparse.Namespace) -> int:
    layout, storage = _layout(args.layout), profile(args.profile)
    report = prune_to(layout, args.keep, storage)
    print(f"layout                {layout.name}")
    print(f"kept partitions       {len(report.kept_partitions)} of {report.total_partitions}")
    print()
    print(f"  bytes kept          {report.bytes_kept_share:.1%}")
    print(f"  files kept          {report.files_kept_share:.1%}")
    print()
    print(f"  plan promises       {report.plan_promised_speedup:.1f}x faster")
    print(f"  model delivers      {report.modelled_speedup:.2f}x faster")
    print(f"  overstated by       {report.overstatement:.1f}x")
    if report.overstatement <= 1.1:
        print()
        print("the plan's promise is close to what pruning actually buys here")
        return OK
    print()
    print("pruning dropped the bytes and left the files, so the plan overstates the gain")
    return AMPLIFIED


def _cmd_compact(args: argparse.Namespace) -> int:
    layout, storage = _layout(args.layout), profile(args.profile)
    plans = sweep_targets(layout, TARGETS, storage)
    print(f"layout                {layout.name}")
    print(f"break-even file       {_mib(break_even_bytes(storage))}")
    print()
    print(f"{'target':>12}  {'files':>8}  {'scan ms':>9}  {'improvement':>11}  {'payback':>8}")
    print("-" * 56)
    for item in plans:
        payback = "never" if item.scans_to_pay_back == float("inf") else f"{item.scans_to_pay_back:.1f}"
        print(
            f"{_mib(item.target_bytes):>12}  {item.after.file_count:>8,}  "
            f"{item.after.total_ms:>9,.0f}  {item.improvement_share:>10.1%}  {payback:>8}"
        )
    best = max(plans, key=lambda item: item.improvement_share)
    print()
    print(f"best target           {_mib(best.target_bytes)} at {best.improvement_share:.1%}")
    return OK if best.improvement_share < 0.1 else AMPLIFIED


def _cmd_claim(args: argparse.Namespace) -> int:
    layout, storage = _layout(args.layout), profile(args.profile)
    found = scans_to_target(layout, storage, args.improvement)
    print(f"layout                {layout.name}")
    print(f"claimed improvement   {args.improvement:.0%}")
    if found is None:
        print()
        print("no rewrite in the search reaches that figure on this table")
        print("a performance claim without its starting layout describes nothing")
        return UNDETERMINED
    print()
    print(f"  cheapest rewrite    files of {_mib(found.target_bytes)}")
    print(f"  file count          {found.before.file_count:,} becomes {found.after.file_count:,}")
    print(f"  improvement         {found.improvement_share:.1%}")
    print(f"  rewrite cost        {found.rewrite_ms:,.0f} ms, paid back in "
          f"{found.scans_to_pay_back:.1f} scans")
    print(f"  above break-even    {found.target_is_above_break_even}")
    print()
    if not found.target_is_above_break_even:
        print("the cheapest rewrite reaching this figure leaves the table below the")
        print("break-even file size, so the figure is reachable without fixing the layout")
    return OK


def _cmd_profiles(args: argparse.Namespace) -> int:
    print(f"{'profile':>24}  {'per file':>9}  {'throughput':>12}  {'break-even':>12}")
    print("-" * 64)
    for name in sorted(PROFILES):
        storage = PROFILES[name]
        print(
            f"{name:>24}  {storage.per_file_ms:>7.1f}ms  "
            f"{storage.throughput_mib_per_s:>8,.0f} MiB/s  {_mib(break_even_bytes(storage)):>12}"
        )
    print()
    print("faster storage raises the break-even size: bytes get cheap faster than opens do")
    return OK


def _cmd_json(args: argparse.Namespace) -> int:
    layout, storage = _layout(args.layout), profile(args.profile)
    cost = scan_cost(layout, storage)
    payload = {
        "layout": layout.name,
        "profile": storage.name,
        "files": cost.file_count,
        "bytes": cost.total_bytes,
        "rows": cost.total_rows,
        "total_ms": cost.total_ms,
        "plan_visible_ms": cost.plan_visible_ms,
        "plan_blind_ms": cost.plan_blind_ms,
        "plan_blind_share": cost.plan_blind_share,
        "amplification": cost.amplification,
        "break_even_bytes": break_even_bytes(storage),
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return AMPLIFIED if cost.plan_blind_share > BLIND_THRESHOLD else OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sfa",
        description="Measure the part of a scan's cost a query plan cannot report.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def with_common(node, *, layout_default="events"):
        node.add_argument("--layout", default=layout_default, choices=sorted(LAYOUTS))
        node.add_argument("--profile", default="s3-spark", choices=sorted(PROFILES))
        return node

    with_common(sub.add_parser("scan", help="model one scan and split its cost")).set_defaults(
        handler=_cmd_scan
    )
    node = sub.add_parser("indistinguishable", help="two layouts one plan cannot tell apart")
    node.add_argument("--left", default="uniform-small", choices=sorted(LAYOUTS))
    node.add_argument("--right", default="uniform-large", choices=sorted(LAYOUTS))
    node.add_argument("--profile", default="s3-spark", choices=sorted(PROFILES))
    node.set_defaults(handler=_cmd_indistinguishable)
    node = with_common(sub.add_parser("prune", help="what partition pruning actually buys"))
    node.add_argument("--keep", type=int, default=6, help="partitions to keep")
    node.set_defaults(handler=_cmd_prune)
    with_common(sub.add_parser("compact", help="sweep compaction targets")).set_defaults(
        handler=_cmd_compact
    )
    node = with_common(sub.add_parser("claim", help="price a quoted performance improvement"))
    node.add_argument("--improvement", type=float, default=0.40)
    node.set_defaults(handler=_cmd_claim)
    sub.add_parser("profiles", help="the storage profiles and their break-even sizes").set_defaults(
        handler=_cmd_profiles
    )
    node = with_common(sub.add_parser("json", help="one scan as JSON"))
    node.add_argument("--out", type=Path, default=None)
    node.set_defaults(handler=_cmd_json)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (LayoutError, UnknownProfileError) as exc:
        print(str(exc).strip('"'), file=sys.stderr)
        return BAD_INPUT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
