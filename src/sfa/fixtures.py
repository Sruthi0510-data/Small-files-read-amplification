"""The shipped tables, and why each file in them is the size it is.

Three layouts, built rather than sampled, because every file's size here is
making a point and a sampled table would hide which.

`events` is the one the repository is about: a month of partitions where the
older days have been compacted by a nightly job and the most recent week has
not, so the table holds most of its bytes in a handful of large files and
almost all of its files in the days nobody has got to yet. That shape is not
contrived. It is what a streaming writer plus a nightly maintenance job
produces on any day the maintenance job is behind, and being behind is the
normal state of a maintenance job.

`uniform_small` and `uniform_large` hold identical bytes and identical rows in
different numbers of files. They exist so a comparison can move the file count
and nothing else, which is the only way to attribute a difference in modelled
time to the layout rather than to a different table.
"""

from __future__ import annotations

from sfa.layout import MIB, DataFile, Layout

__all__ = ["events", "uniform_small", "uniform_large", "COMPACTED_DAYS", "RECENT_DAYS"]

COMPACTED_DAYS = 24
"""Days the nightly job has already rewritten into large files."""

RECENT_DAYS = 6
"""Days still as the streaming writer left them."""

_COMPACTED_FILE_BYTES = 128 * MIB
_COMPACTED_FILE_ROWS = 2_000_000
_COMPACTED_FILES_PER_DAY = 2

_STREAMED_FILE_BYTES = 96 * 1024
_STREAMED_FILE_ROWS = 1_500
_STREAMED_FILES_PER_DAY = 2_800
"""One file per micro-batch.

At a thirty-second trigger a day holds 2,880 batches, and a writer that skips
empty batches lands a little under that. The number is the point: nothing is
wrong with any individual file, and there are two thousand eight hundred of
them.
"""


def events() -> Layout:
    """A month of partitions, most of them compacted and the recent ones not."""
    files: list[DataFile] = []
    for day in range(1, COMPACTED_DAYS + RECENT_DAYS + 1):
        partition = f"2026-09-{day:02d}"
        if day <= COMPACTED_DAYS:
            files.extend(
                DataFile(
                    bytes=_COMPACTED_FILE_BYTES,
                    rows=_COMPACTED_FILE_ROWS,
                    partition=partition,
                )
                for _ in range(_COMPACTED_FILES_PER_DAY)
            )
        else:
            files.extend(
                DataFile(
                    bytes=_STREAMED_FILE_BYTES,
                    rows=_STREAMED_FILE_ROWS,
                    partition=partition,
                )
                for _ in range(_STREAMED_FILES_PER_DAY)
            )
    return Layout(files=tuple(files), name="events")


def uniform_small() -> Layout:
    """Four thousand files of 64 KiB, which is 250 MiB."""
    return Layout(
        files=tuple(DataFile(bytes=64 * 1024, rows=1_000) for _ in range(4_000)),
        name="uniform-small",
    )


def uniform_large() -> Layout:
    """The same 250 MiB and the same four million rows, in two files.

    Two rather than one, so that the comparison is between two plausible
    layouts rather than between a table and a degenerate case.
    """
    total_bytes = 4_000 * 64 * 1024
    total_rows = 4_000 * 1_000
    return Layout(
        files=(
            DataFile(bytes=total_bytes // 2, rows=total_rows // 2),
            DataFile(bytes=total_bytes - total_bytes // 2, rows=total_rows - total_rows // 2),
        ),
        name="uniform-large",
    )
