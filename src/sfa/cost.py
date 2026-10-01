"""What a scan costs, split into the part a plan reports and the part it cannot.

A query plan reports bytes scanned and rows scanned. Both are properties of the
data, which is why a plan can know them: they come from the table's own
metadata, and the planner reads that metadata to decide what to do.

The cost that dominates a badly laid out table is none of those. It is paid once
per file, for finding the object, opening it, reading its footer, parsing its
schema and building a reader. On object storage the first of those is a network
round trip, and a round trip costs the same for a 64 KiB file as for a 512 MiB
one. The planner cannot report it because it is not a property of the data; it
is a property of the reader, the storage system and the day.

So the model has two terms and the plan can see one of them:

    time = per_file_cost * file_count  +  total_bytes / throughput
           \\_____ invisible to the plan ____/   \\_ what the plan reports _/

Dividing one by the other gives the number this repository exists for: the
break-even file size, below which a scan spends more time opening files than
reading them. It is `per_file_cost * throughput`, it depends on nothing about
the table, and it is usually larger than people expect.
"""

from __future__ import annotations

from dataclasses import dataclass

from sfa.layout import MIB, Layout

__all__ = [
    "StorageProfile",
    "ScanCost",
    "PROFILES",
    "profile",
    "UnknownProfileError",
    "scan_cost",
    "break_even_bytes",
]


class UnknownProfileError(KeyError):
    """Raised when a caller names a storage profile this repository does not model."""


@dataclass(frozen=True, slots=True)
class StorageProfile:
    """One storage and engine combination, as the four numbers that decide a scan.

    `note` records where the numbers come from and what they are not. They are
    order-of-magnitude figures for a cold read on a typical deployment, and no
    test can check them against anybody's cluster. A reader whose numbers differ
    should change them; the argument does not depend on the particular values,
    only on the per-file cost being nonzero, which it always is.
    """

    name: str
    open_ms: float
    footer_bytes: int
    parse_ms: float
    throughput_mib_per_s: float
    readers: int
    note: str

    def __post_init__(self) -> None:
        if self.open_ms < 0 or self.parse_ms < 0:
            raise ValueError("a cost cannot be negative")
        if self.throughput_mib_per_s <= 0:
            raise ValueError("throughput must be positive")
        if self.readers < 1:
            raise ValueError("a scan needs at least one reader")
        if self.footer_bytes < 0:
            raise ValueError("a footer cannot be negative")

    @property
    def throughput_bytes_per_ms(self) -> float:
        return self.throughput_mib_per_s * MIB / 1000.0

    @property
    def per_file_ms(self) -> float:
        """Everything a scan pays once per file, regardless of the file's size.

        The footer read is included at full throughput cost rather than as a
        second round trip. That understates it on object storage, where the
        footer is usually its own request, and understating the invisible term
        is the conservative direction for this repository's argument.
        """
        return self.open_ms + self.parse_ms + self.footer_bytes / self.throughput_bytes_per_ms


PROFILES: dict[str, StorageProfile] = {
    "s3-spark": StorageProfile(
        name="s3-spark",
        open_ms=28.0,
        footer_bytes=64 * 1024,
        parse_ms=3.0,
        throughput_mib_per_s=90.0,
        readers=32,
        note="object storage over the network: first-byte latency dominates the open, "
             "and the Parquet footer is a second request in practice",
    ),
    "adls-databricks": StorageProfile(
        name="adls-databricks",
        open_ms=22.0,
        footer_bytes=64 * 1024,
        parse_ms=2.5,
        throughput_mib_per_s=120.0,
        readers=48,
        note="similar shape to S3 with a faster path to storage and more readers per "
             "cluster, which raises the break-even size rather than lowering it",
    ),
    "gcs-bigquery-external": StorageProfile(
        name="gcs-bigquery-external",
        open_ms=35.0,
        footer_bytes=64 * 1024,
        parse_ms=4.0,
        throughput_mib_per_s=140.0,
        readers=64,
        note="an external table pays the per-object cost on every query because "
             "nothing is cached between them",
    ),
    "local-nvme": StorageProfile(
        name="local-nvme",
        open_ms=0.25,
        footer_bytes=64 * 1024,
        parse_ms=1.5,
        throughput_mib_per_s=2_000.0,
        readers=16,
        note="the profile that makes small files look harmless in absolute terms "
             "and worse in relative ones: opens get cheaper than object storage "
             "by two orders of magnitude and bytes get cheaper by three, so the "
             "break-even file size is higher here than on S3",
    ),
}


def profile(name: str) -> StorageProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        available = ", ".join(sorted(PROFILES))
        raise UnknownProfileError(f"no such profile: {name}; available: {available}") from exc


@dataclass(frozen=True, slots=True)
class ScanCost:
    """One modelled scan, with the two terms kept apart.

    They are kept apart because collapsing them produces a single number that
    looks like a measurement and answers no question. The whole argument is the
    ratio between them.
    """

    layout: str
    profile: str
    file_count: int
    total_bytes: int
    total_rows: int
    per_file_ms: float
    bytes_ms: float
    readers: int

    @property
    def total_ms(self) -> float:
        return self.per_file_ms + self.bytes_ms

    @property
    def plan_visible_ms(self) -> float:
        """The part a plan could predict from what it reports."""
        return self.bytes_ms

    @property
    def plan_blind_ms(self) -> float:
        return self.per_file_ms

    @property
    def plan_blind_share(self) -> float:
        """The share of modelled time the plan cannot account for.

        The headline. At zero the plan is a complete predictor of relative cost;
        at one the plan is reporting a quantity that has nothing to do with how
        long the query takes.
        """
        if self.total_ms == 0:
            return 0.0
        return self.plan_blind_ms / self.total_ms

    @property
    def amplification(self) -> float:
        """How many times longer the scan takes than its bytes alone would suggest."""
        if self.bytes_ms == 0:
            return 0.0
        return self.total_ms / self.bytes_ms


def scan_cost(layout: Layout, storage: StorageProfile) -> ScanCost:
    """Model one scan.

    Work is divided across readers as a flat split of both terms rather than by
    assigning whole files, which is what a scheduler with a work queue
    approaches and what every engine here does when file counts exceed reader
    counts. ADR-002 records the case this is wrong about, which is a handful of
    enormous files on many readers, and why the repository does not go there.
    """
    per_file = storage.per_file_ms * layout.file_count / storage.readers
    bytes_ms = layout.total_bytes / storage.throughput_bytes_per_ms / storage.readers
    return ScanCost(
        layout=layout.name,
        profile=storage.name,
        file_count=layout.file_count,
        total_bytes=layout.total_bytes,
        total_rows=layout.total_rows,
        per_file_ms=per_file,
        bytes_ms=bytes_ms,
        readers=storage.readers,
    )


def break_even_bytes(storage: StorageProfile) -> float:
    """The file size at which opening a file costs as much as reading it.

    `per_file_ms * throughput_bytes_per_ms`, and nothing about the table appears
    in it. Below this size a scan spends more time opening files than reading
    them, and no amount of column pruning, predicate pushdown or compression
    changes that, because all three reduce bytes and none of them reduces the
    file count.

    On the profiles modelled here it lands at a few megabytes. That is far above
    what a streaming writer emits per micro-batch, which is the layout this
    repository is about, and far below the target file size the table formats
    default to, which is why those defaults are conservative and correct.

    The counterintuitive part is that faster storage raises it. Local NVMe has a
    per-file cost two orders of magnitude below object storage and a throughput
    three orders above, so bytes get cheap faster than opens do and the
    break-even size goes up rather than down. Fast storage does not make small
    files less of a problem in relative terms; it makes the absolute number
    small enough that nobody looks.
    """
    return storage.per_file_ms * storage.throughput_bytes_per_ms
