"""What compacting a table buys, what it costs, and when it stops paying.

Compaction is the fix and it is not free. Rewriting a table reads every byte and
writes every byte, which is more work than any single scan of it, so the
honest unit is not the speedup but the number of scans it takes to pay the
rewrite back. A table read once a quarter and compacted every night is a table
whose maintenance costs more than its queries.

The second thing this module exists to say is where compaction stops helping.
Below the break-even file size every halving of the file count roughly halves
the scan. Above it the per-file term is already small and further compaction
buys almost nothing, so a job configured to compact to one enormous file is
spending a great deal to move a number that has stopped mattering.

Every property below divides by a modelled time without guarding against zero.
That is deliberate and it is checked by the type invariants rather than at
runtime: a `Layout` must hold at least one file, a `DataFile` must hold at least
one byte, and a `StorageProfile` must have positive throughput, so a cost
produced by `scan_cost` is strictly positive. An earlier version carried the
guards anyway and branch coverage showed every one of them was unreachable,
which is the usual fate of a defensive check written for a state the types have
already ruled out.
"""

from __future__ import annotations

from dataclasses import dataclass

from sfa.cost import ScanCost, StorageProfile, break_even_bytes, scan_cost
from sfa.layout import Layout, LayoutError, rebalanced

__all__ = ["CompactionPlan", "plan_compaction", "sweep_targets", "scans_to_target"]


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    """One proposed rewrite, with its cost on the same page as its benefit."""

    before: ScanCost
    after: ScanCost
    target_bytes: int
    rewrite_ms: float
    break_even_bytes: float

    @property
    def saved_ms(self) -> float:
        return self.before.total_ms - self.after.total_ms

    @property
    def speedup(self) -> float:
        return self.before.total_ms / self.after.total_ms

    @property
    def improvement_share(self) -> float:
        """The figure a performance claim is usually quoted as.

        A forty percent improvement means this is 0.40. It is the saved time
        over the original time, not the speedup, and conflating the two is how a
        2x speedup gets reported as a 200 percent improvement.
        """
        return self.saved_ms / self.before.total_ms

    @property
    def scans_to_pay_back(self) -> float:
        """How many scans of the compacted table repay the rewrite.

        Infinite when the rewrite saves nothing, which is a real outcome for a
        table that is already well laid out and is reported rather than hidden
        behind a large number.
        """
        if self.saved_ms <= 0:
            return float("inf")
        return self.rewrite_ms / self.saved_ms

    @property
    def target_is_above_break_even(self) -> bool:
        return self.target_bytes >= self.break_even_bytes

    @property
    def files_removed(self) -> int:
        return self.before.file_count - self.after.file_count


def plan_compaction(layout: Layout, target_bytes: int, storage: StorageProfile) -> CompactionPlan:
    """Rewrite into files of `target_bytes` and price the result.

    The target is a size, not a count, because that is what every compaction
    knob in every engine takes, and because expressing it as a count hides the
    thing that matters, which is how the target compares with the break-even
    size.

    The rewrite cost is one full read of the old layout plus one full write of
    the new one, with the write modelled at the same throughput as the read.
    That understates it: a write is usually slower than a read and a rewrite
    also pays commit and metadata costs. Understating the cost of the fix is the
    conservative direction for a repository arguing that the fix is worth it.
    """
    if target_bytes <= 0:
        raise LayoutError("a compaction target must be a positive size")
    count = max(1, layout.total_bytes // target_bytes)
    compacted = rebalanced(layout, count, name=f"{layout.name}-at-{target_bytes}")
    read_ms = scan_cost(layout, storage).total_ms
    write_ms = scan_cost(compacted, storage).total_ms
    return CompactionPlan(
        before=scan_cost(layout, storage),
        after=scan_cost(compacted, storage),
        target_bytes=target_bytes,
        rewrite_ms=read_ms + write_ms,
        break_even_bytes=break_even_bytes(storage),
    )


def sweep_targets(
    layout: Layout, targets: tuple[int, ...], storage: StorageProfile
) -> tuple[CompactionPlan, ...]:
    return tuple(plan_compaction(layout, target, storage) for target in targets)


def scans_to_target(
    layout: Layout, storage: StorageProfile, improvement: float
) -> CompactionPlan | None:
    """The smallest rewrite that reaches a claimed improvement, or nothing.

    Exists because performance claims are quoted as a percentage with no layout
    attached, and the only honest way to read one is to ask what rewrite would
    produce it and what that rewrite cost. Returns None when no target in the
    search reaches the figure, which is the answer for a table that was already
    well laid out and the reason a claim needs its starting point quoted
    alongside it.

    The search walks target sizes upward and stops at the first that clears the
    bar, so the plan returned is the cheapest rewrite that gets there rather
    than the most impressive one.
    """
    if not 0 < improvement < 1:
        raise LayoutError("an improvement share must lie strictly between zero and one")
    size = 64 * 1024
    while size <= layout.total_bytes:
        candidate = plan_compaction(layout, size, storage)
        if candidate.improvement_share >= improvement:
            return candidate
        size *= 2
    return None
