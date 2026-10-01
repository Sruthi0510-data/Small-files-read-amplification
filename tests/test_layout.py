"""Tests for the layout model, which exists because the file is where the cost is paid."""

from __future__ import annotations

import pytest

from sfa.layout import MIB, DataFile, Layout, LayoutError, rebalanced, uniform


def test_a_file_with_no_bytes_is_refused():
    with pytest.raises(LayoutError, match="no bytes"):
        DataFile(bytes=0, rows=1)


def test_a_file_with_negative_rows_is_refused():
    with pytest.raises(LayoutError, match="negative"):
        DataFile(bytes=1, rows=-1)


def test_an_empty_file_has_no_row_width():
    """Real pipelines emit one of these per empty micro-batch."""
    assert DataFile(bytes=512, rows=0).bytes_per_row == 0.0


def test_row_width_is_bytes_over_rows():
    assert DataFile(bytes=1_000, rows=100).bytes_per_row == 10.0


def test_a_layout_with_no_files_is_refused():
    with pytest.raises(LayoutError, match="no files"):
        Layout(files=())


def test_a_layout_reports_its_totals():
    layout = Layout(files=(DataFile(bytes=10, rows=1), DataFile(bytes=20, rows=2)))
    assert (layout.file_count, layout.total_bytes, layout.total_rows) == (2, 30, 3)


def test_iterating_a_layout_yields_its_files():
    files = (DataFile(bytes=10, rows=1),)
    assert tuple(Layout(files=files)) == files


def test_a_layout_has_a_length():
    assert len(Layout(files=(DataFile(bytes=1, rows=0),))) == 1


def test_the_mean_hides_the_tail_and_the_median_does_not():
    """The property the median exists for, as a worked example."""
    files = (DataFile(bytes=1 * MIB * 1024, rows=1),) + tuple(
        DataFile(bytes=64 * 1024, rows=1) for _ in range(400)
    )
    layout = Layout(files=files)
    assert layout.mean_file_bytes > 2 * MIB
    assert layout.median_file_bytes == 64 * 1024


def test_partitions_come_out_sorted_and_unique():
    layout = Layout(
        files=(
            DataFile(bytes=1, rows=0, partition="b"),
            DataFile(bytes=1, rows=0, partition="a"),
            DataFile(bytes=1, rows=0, partition="b"),
        )
    )
    assert layout.partitions == ("a", "b")


def test_files_in_a_partition_are_found():
    layout = Layout(
        files=(
            DataFile(bytes=1, rows=0, partition="a"),
            DataFile(bytes=2, rows=0, partition="b"),
        )
    )
    assert len(layout.files_in("a")) == 1


def test_files_in_an_absent_partition_are_none():
    assert Layout(files=(DataFile(bytes=1, rows=0),)).files_in("nope") == ()


def test_small_files_are_strictly_below_the_threshold():
    """A table compacted to exactly the threshold reports zero small files."""
    layout = Layout(files=(DataFile(bytes=100, rows=0), DataFile(bytes=99, rows=0)))
    assert len(layout.small_files(100)) == 1


def test_the_small_file_share_is_over_the_file_count():
    layout = Layout(files=tuple(DataFile(bytes=n, rows=0) for n in (1, 2, 300, 400)))
    assert layout.small_file_share(100) == 0.5


def test_the_bytes_in_small_files_can_be_a_tiny_share_of_the_table():
    """The shape that makes a table look fine by bytes and read badly."""
    layout = Layout(
        files=(DataFile(bytes=1_000_000, rows=0),) + tuple(DataFile(bytes=10, rows=0) for _ in range(99))
    )
    assert layout.small_file_share(1_000) == 0.99
    assert layout.bytes_in_small_files(1_000) / layout.total_bytes < 0.01


def test_a_layout_can_be_rebuilt_with_new_files():
    layout = Layout(files=(DataFile(bytes=1, rows=0),), name="x")
    rebuilt = layout.with_files((DataFile(bytes=2, rows=0),))
    assert rebuilt.total_bytes == 2 and rebuilt.name == "x"


def test_rebuilding_can_rename():
    layout = Layout(files=(DataFile(bytes=1, rows=0),), name="x")
    assert layout.with_files(layout.files, name="y").name == "y"


def test_uniform_builds_identical_files():
    layout = uniform(4, 1_000)
    assert layout.file_count == 4 and layout.median_file_bytes == 1_000


def test_uniform_refuses_a_zero_count():
    with pytest.raises(LayoutError, match="at least one file"):
        uniform(0, 1_000)


def test_rebalancing_preserves_bytes_and_rows():
    layout = uniform(400, 1_000, rows_per_file=7)
    for count in (1, 2, 7, 399, 400):
        rebuilt = rebalanced(layout, count)
        assert rebuilt.total_bytes == layout.total_bytes
        assert rebuilt.total_rows == layout.total_rows


def test_rebalancing_produces_the_requested_count():
    assert rebalanced(uniform(400, 1_000), 13).file_count == 13


def test_rebalancing_puts_the_remainder_in_the_last_file():
    layout = Layout(files=(DataFile(bytes=10, rows=3),))
    rebuilt = rebalanced(layout, 3)
    assert [file.bytes for file in rebuilt] == [3, 3, 4]


def test_rebalancing_refuses_a_zero_count():
    with pytest.raises(LayoutError, match="at least one file"):
        rebalanced(uniform(4, 10), 0)


def test_rebalancing_refuses_more_files_than_bytes():
    with pytest.raises(LayoutError, match="cannot split"):
        rebalanced(Layout(files=(DataFile(bytes=3, rows=0),)), 4)


def test_rebalancing_names_the_result():
    assert rebalanced(uniform(4, 10), 2).name.endswith("-compacted")


def test_rebalancing_accepts_an_explicit_name():
    assert rebalanced(uniform(4, 10), 2, name="chosen").name == "chosen"
