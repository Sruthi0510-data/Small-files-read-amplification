"""A table as the files it is actually made of.

The unit here is the file, not the partition and not the row group, because the
file is where the cost this repository is about is paid. A partition with one
file and a partition with four hundred files hold the same rows and cost
different amounts to read, and nothing in a partition-level description can say
which one you have.

Sizes are in bytes and counts are exact. No averages: a layout whose files are
described by a mean file size hides the long tail, and the long tail is where
the small files live. Two layouts with the same mean can differ by a factor of
several in scan time, and `Layout` is built to make that representable.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Iterator, Sequence

__all__ = ["DataFile", "Layout", "LayoutError", "MIB", "uniform", "rebalanced"]

MIB = 1024 * 1024


class LayoutError(ValueError):
    """Raised when a layout cannot describe a table anyone could have."""


@dataclass(frozen=True, slots=True)
class DataFile:
    """One file on object storage.

    `partition` is carried because pruning operates on it and because a layout
    that cannot say which partition a file belongs to cannot model the thing
    that makes pruning disappointing.
    """

    bytes: int
    rows: int
    partition: str = "all"

    def __post_init__(self) -> None:
        if self.bytes <= 0:
            raise LayoutError("a file with no bytes is not a file")
        if self.rows < 0:
            raise LayoutError("a file cannot hold a negative number of rows")

    @property
    def bytes_per_row(self) -> float:
        """Average row width, or zero for an empty file.

        Zero rather than a division error, because an empty data file is a real
        thing that real pipelines emit, usually one per empty micro-batch, and
        refusing to describe it would exclude the layout that motivates this
        repository.
        """
        if self.rows == 0:
            return 0.0
        return self.bytes / self.rows


@dataclass(frozen=True, slots=True)
class Layout:
    """A table, as a list of files.

    Frozen and explicit. Everything derived is a property, so a layout cannot
    drift out of agreement with its own summary, which is the failure this
    repository is about happening to the repository itself.
    """

    files: tuple[DataFile, ...]
    name: str = "layout"

    def __post_init__(self) -> None:
        if not self.files:
            raise LayoutError("a layout with no files describes no table")

    def __len__(self) -> int:
        return len(self.files)

    def __iter__(self) -> Iterator[DataFile]:
        return iter(self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(file.bytes for file in self.files)

    @property
    def total_rows(self) -> int:
        return sum(file.rows for file in self.files)

    @property
    def mean_file_bytes(self) -> float:
        return self.total_bytes / self.file_count

    @property
    def median_file_bytes(self) -> float:
        """The number that tells you about the tail, which the mean does not.

        A table with one 1 GiB file and four hundred 64 KiB files has a mean
        file size of several megabytes and a median of 64 KiB. The mean says the
        layout is fine. The median says it is not, and the scan time agrees with
        the median.
        """
        return float(median(file.bytes for file in self.files))

    @property
    def partitions(self) -> tuple[str, ...]:
        return tuple(sorted({file.partition for file in self.files}))

    def files_in(self, partition: str) -> tuple[DataFile, ...]:
        return tuple(file for file in self.files if file.partition == partition)

    def small_files(self, threshold_bytes: int) -> tuple[DataFile, ...]:
        """Files below a threshold, strictly.

        Strictly below rather than at or below, so a layout compacted to exactly
        the threshold reports zero small files rather than all of them, which is
        the arithmetic a compaction planner's own success check runs on.
        """
        return tuple(file for file in self.files if file.bytes < threshold_bytes)

    def small_file_share(self, threshold_bytes: int) -> float:
        return len(self.small_files(threshold_bytes)) / self.file_count

    def bytes_in_small_files(self, threshold_bytes: int) -> int:
        return sum(file.bytes for file in self.small_files(threshold_bytes))

    def with_files(self, files: Iterable[DataFile], *, name: str | None = None) -> "Layout":
        return Layout(files=tuple(files), name=name or self.name)


def uniform(count: int, file_bytes: int, *, rows_per_file: int = 10_000, name: str = "uniform") -> Layout:
    """A layout of identical files, for the comparisons that need one variable.

    Used by the experiments to hold bytes and rows fixed while file count moves,
    which is the only way to attribute a change in modelled time to the file
    count rather than to a different table.
    """
    if count <= 0:
        raise LayoutError("a layout needs at least one file")
    return Layout(
        files=tuple(DataFile(bytes=file_bytes, rows=rows_per_file) for _ in range(count)),
        name=name,
    )


def rebalanced(layout: Layout, count: int, *, name: str | None = None) -> Layout:
    """The same bytes and rows redistributed into `count` files of equal size.

    This is what a compaction produces in the best case, and it is the layout
    the plan cannot distinguish from the original. Remainders go to the last
    file rather than being spread, because that is what a writer flushing a
    buffer does and because spreading them would quietly change the file count.
    """
    if count <= 0:
        raise LayoutError("a layout needs at least one file")
    total_bytes, total_rows = layout.total_bytes, layout.total_rows
    if count > total_bytes:
        raise LayoutError(
            f"cannot split {total_bytes} bytes into {count} files of at least one byte"
        )
    share_bytes, share_rows = total_bytes // count, total_rows // count
    files = [DataFile(bytes=share_bytes, rows=share_rows) for _ in range(count - 1)]
    files.append(
        DataFile(
            bytes=total_bytes - share_bytes * (count - 1),
            rows=total_rows - share_rows * (count - 1),
        )
    )
    return Layout(files=tuple(files), name=name or f"{layout.name}-compacted")
