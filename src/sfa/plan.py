"""What a query plan reports, and the pairs of layouts it cannot tell apart.

Every engine in scope prints some version of the same three numbers before a
scan runs: bytes to be read, rows to be read, and partitions touched. Spark's
`EXPLAIN FORMATTED` calls them `size`, `numOutputRows` and `PartitionFilters`;
BigQuery's dry run returns `totalBytesProcessed`; Snowflake's profile shows
`Bytes scanned` and `Partitions scanned`.

What none of them reports is the file count, and the ones that do report
something file-shaped report micro-partitions or splits, which are not files and
do not have a one-to-one relationship with them.

`PlanEstimate` holds exactly those three numbers and nothing else. Two layouts
whose estimates compare equal are indistinguishable to anyone reading a plan,
and `scan_cost` can still put an order of magnitude between them. Building the
estimate as its own type, with no reference to the layout it came from, is what
makes that claim checkable rather than rhetorical: there is no field to cheat
with.

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

from sfa.cost import ScanCost, StorageProfile, scan_cost
from sfa.layout import Layout

__all__ = ["PlanEstimate", "Comparison", "estimate", "compare"]


@dataclass(frozen=True, slots=True)
class PlanEstimate:
    """The three numbers a plan prints. Deliberately missing the fourth."""

    bytes_scanned: int
    rows_scanned: int
    partitions_scanned: int

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlanEstimate):
            return NotImplemented
        return (
            self.bytes_scanned == other.bytes_scanned
            and self.rows_scanned == other.rows_scanned
            and self.partitions_scanned == other.partitions_scanned
        )

    def __hash__(self) -> int:
        return hash((self.bytes_scanned, self.rows_scanned, self.partitions_scanned))

    def rendered(self) -> str:
        return (
            f"bytes={self.bytes_scanned} rows={self.rows_scanned} "
            f"partitions={self.partitions_scanned}"
        )


def estimate(layout: Layout) -> PlanEstimate:
    return PlanEstimate(
        bytes_scanned=layout.total_bytes,
        rows_scanned=layout.total_rows,
        partitions_scanned=len(layout.partitions),
    )


@dataclass(frozen=True, slots=True)
class Comparison:
    """Two layouts, their plan estimates and their modelled costs.

    The pairing is the artefact. A reader who wants to disbelieve the argument
    has to disbelieve either the estimates being equal, which is arithmetic, or
    the costs differing, which is a model with its parameters on the page.
    """

    left: ScanCost
    right: ScanCost
    left_estimate: PlanEstimate
    right_estimate: PlanEstimate

    @property
    def plan_sees_a_difference(self) -> bool:
        return self.left_estimate != self.right_estimate

    @property
    def time_ratio(self) -> float:
        return self.left.total_ms / self.right.total_ms

    @property
    def indistinguishable_but_different(self) -> bool:
        """The condition the repository is named after.

        Equal plans, unequal times. The tolerance on "unequal" is one percent,
        which is far below any difference this model produces and exists so the
        property is about a real gap rather than about floating point.
        """
        return not self.plan_sees_a_difference and abs(self.time_ratio - 1.0) > 0.01

    @property
    def file_count_ratio(self) -> float:
        return self.left.file_count / self.right.file_count


def compare(left: Layout, right: Layout, storage: StorageProfile) -> Comparison:
    return Comparison(
        left=scan_cost(left, storage),
        right=scan_cost(right, storage),
        left_estimate=estimate(left),
        right_estimate=estimate(right),
    )
