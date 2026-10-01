"""Why partition pruning disappoints, and by how much.

Pruning is the optimisation everybody reaches for and the one whose benefit is
most often overstated, for a reason that follows directly from the cost model.

A plan reports the bytes it will not read. Pruning nine partitions out of ten
drops ninety percent of the bytes, and the plan says so, and that number is
correct. The scan does not get ten times faster, because the per-file term fell
by whatever share of the files lived in the pruned partitions, and in a table
written by a streaming job the recent partitions hold most of the files and
least of the bytes.

So the overstatement is systematic and it points one way. The plan's improvement
is an upper bound on the real one, it is quoted as though it were the real one,
and the gap is widest exactly where the layout is worst.

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
from typing import Sequence

from sfa.cost import ScanCost, StorageProfile, scan_cost
from sfa.layout import Layout, LayoutError

__all__ = ["PruningReport", "prune", "prune_to"]


@dataclass(frozen=True, slots=True)
class PruningReport:
    """One pruning, with what the plan promises beside what the model delivers."""

    full: ScanCost
    pruned: ScanCost
    kept_partitions: tuple[str, ...]
    total_partitions: int

    @property
    def bytes_kept_share(self) -> float:
        return self.pruned.total_bytes / self.full.total_bytes

    @property
    def files_kept_share(self) -> float:
        return self.pruned.file_count / self.full.file_count

    @property
    def plan_promised_speedup(self) -> float:
        """What a reader of the plan would predict from bytes alone."""
        return 1.0 / self.bytes_kept_share

    @property
    def modelled_speedup(self) -> float:
        return self.full.total_ms / self.pruned.total_ms

    @property
    def overstatement(self) -> float:
        """How many times the plan's promise exceeds the modelled result.

        One means the plan was right. Above one means the pruned partitions held
        more bytes per file than the kept ones, which is the normal case for a
        table whose recent data arrives in small increments.
        """
        return self.plan_promised_speedup / self.modelled_speedup


def prune(layout: Layout, keep: Sequence[str], storage: StorageProfile) -> PruningReport:
    """Keep only the named partitions and report what that bought.

    Refuses a partition the layout does not contain rather than silently
    pruning everything, because a typo in a partition filter produces an empty
    result that looks like a correct answer about a quiet day.
    """
    unknown = sorted(set(keep) - set(layout.partitions))
    if unknown:
        raise LayoutError(f"no such partition: {', '.join(unknown)}")
    if not keep:
        raise LayoutError("pruning to no partitions leaves nothing to scan")
    kept_files = tuple(file for file in layout.files if file.partition in set(keep))
    pruned_layout = layout.with_files(kept_files, name=f"{layout.name}-pruned")
    return PruningReport(
        full=scan_cost(layout, storage),
        pruned=scan_cost(pruned_layout, storage),
        kept_partitions=tuple(sorted(keep)),
        total_partitions=len(layout.partitions),
    )


def prune_to(layout: Layout, count: int, storage: StorageProfile) -> PruningReport:
    """Keep the last `count` partitions in sort order, which is what a date filter does."""
    if count < 1:
        raise LayoutError("pruning to no partitions leaves nothing to scan")
    partitions = layout.partitions
    if count > len(partitions):
        raise LayoutError(f"the layout has {len(partitions)} partitions, not {count}")
    return prune(layout, partitions[-count:], storage)
