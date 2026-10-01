"""Tests for the cost model, the break-even size and the indistinguishability claim."""

from __future__ import annotations

import pytest

from sfa.cost import (
    PROFILES,
    ScanCost,
    StorageProfile,
    UnknownProfileError,
    break_even_bytes,
    profile,
    scan_cost,
)
from sfa.fixtures import uniform_large, uniform_small
from sfa.layout import MIB, DataFile, Layout, uniform
from sfa.plan import PlanEstimate, compare, estimate


def tiny(**overrides) -> StorageProfile:
    base = {
        "name": "tiny",
        "open_ms": 10.0,
        "footer_bytes": 0,
        "parse_ms": 0.0,
        "throughput_mib_per_s": 1.0,
        "readers": 1,
        "note": "a profile with round numbers, for tests that do arithmetic by hand",
    }
    base.update(overrides)
    return StorageProfile(**base)


def test_a_negative_open_cost_is_refused():
    with pytest.raises(ValueError, match="cannot be negative"):
        tiny(open_ms=-1)


def test_a_negative_parse_cost_is_refused():
    with pytest.raises(ValueError, match="cannot be negative"):
        tiny(parse_ms=-1)


def test_a_negative_footer_is_refused():
    with pytest.raises(ValueError, match="footer"):
        tiny(footer_bytes=-1)


def test_zero_throughput_is_refused():
    with pytest.raises(ValueError, match="throughput"):
        tiny(throughput_mib_per_s=0)


def test_zero_readers_are_refused():
    with pytest.raises(ValueError, match="at least one reader"):
        tiny(readers=0)


def test_the_per_file_cost_adds_open_parse_and_footer():
    storage = tiny(open_ms=10, parse_ms=5, footer_bytes=1024, throughput_mib_per_s=1.0)
    assert storage.per_file_ms == pytest.approx(15 + 1024 / (MIB / 1000))


def test_every_shipped_profile_carries_a_note():
    assert all(entry.note.strip() for entry in PROFILES.values())


def test_every_shipped_profile_is_keyed_by_its_own_name():
    assert all(name == entry.name for name, entry in PROFILES.items())


def test_looking_up_a_profile_works():
    assert profile("s3-spark").name == "s3-spark"


def test_an_unknown_profile_lists_the_known_ones():
    with pytest.raises(UnknownProfileError, match="available: adls-databricks"):
        profile("hdfs")


def test_the_break_even_size_is_the_per_file_cost_times_throughput():
    storage = tiny()
    assert break_even_bytes(storage) == pytest.approx(storage.per_file_ms * storage.throughput_bytes_per_ms)


def test_a_file_at_the_break_even_size_splits_the_cost_evenly():
    storage = tiny()
    size = int(break_even_bytes(storage))
    cost = scan_cost(Layout(files=(DataFile(bytes=size, rows=1),)), storage)
    assert cost.plan_blind_share == pytest.approx(0.5, abs=0.001)


def test_faster_storage_raises_the_break_even_size():
    """Counterintuitive, and the reason a laptop benchmark says the layout is fine."""
    assert break_even_bytes(profile("local-nvme")) > break_even_bytes(profile("s3-spark"))


def test_the_two_cost_terms_sum_to_the_total():
    cost = scan_cost(uniform(10, 1_000), tiny())
    assert cost.total_ms == pytest.approx(cost.plan_visible_ms + cost.plan_blind_ms)


def test_readers_divide_both_terms():
    layout = uniform(16, 1_000)
    one = scan_cost(layout, tiny(readers=1))
    four = scan_cost(layout, tiny(readers=4))
    assert one.total_ms == pytest.approx(4 * four.total_ms)


def test_more_files_at_the_same_bytes_cost_more():
    small = scan_cost(uniform_small(), profile("s3-spark"))
    large = scan_cost(uniform_large(), profile("s3-spark"))
    assert small.total_bytes == large.total_bytes
    assert small.total_ms > 10 * large.total_ms


def test_amplification_is_the_total_over_the_bytes_term():
    cost = scan_cost(uniform(100, 1_000), tiny())
    assert cost.amplification == pytest.approx(cost.total_ms / cost.plan_visible_ms)


def test_a_scan_with_no_per_file_cost_has_an_amplification_of_one():
    cost = scan_cost(uniform(10, 1_000), tiny(open_ms=0, parse_ms=0, footer_bytes=0))
    assert cost.amplification == pytest.approx(1.0)
    assert cost.plan_blind_share == 0.0


def test_a_scan_cost_of_nothing_reports_zero_rather_than_dividing():
    empty = ScanCost(
        layout="x", profile="y", file_count=0, total_bytes=0, total_rows=0,
        per_file_ms=0.0, bytes_ms=0.0, readers=1,
    )
    assert empty.plan_blind_share == 0.0 and empty.amplification == 0.0


def test_a_plan_estimate_holds_three_numbers_and_not_the_file_count():
    plan = estimate(uniform_small())
    assert not hasattr(plan, "file_count")
    assert not hasattr(plan, "files")


def test_two_layouts_with_the_same_bytes_and_rows_have_equal_estimates():
    assert estimate(uniform_small()) == estimate(uniform_large())


def test_an_estimate_does_not_compare_equal_to_another_type():
    assert estimate(uniform_small()) != "bytes=1"


def test_estimates_are_hashable_so_they_can_be_grouped():
    assert len({estimate(uniform_small()), estimate(uniform_large())}) == 1


def test_an_estimate_renders_its_three_numbers():
    rendered = PlanEstimate(bytes_scanned=1, rows_scanned=2, partitions_scanned=3).rendered()
    assert rendered == "bytes=1 rows=2 partitions=3"


def test_the_headline_claim_holds_on_the_shipped_layouts():
    """Equal plans, and one takes an order of magnitude longer."""
    result = compare(uniform_small(), uniform_large(), profile("s3-spark"))
    assert not result.plan_sees_a_difference
    assert result.indistinguishable_but_different
    assert result.time_ratio > 10


def test_the_file_count_ratio_is_reported():
    result = compare(uniform_small(), uniform_large(), profile("s3-spark"))
    assert result.file_count_ratio == 2_000


def test_two_identical_layouts_are_not_a_finding():
    result = compare(uniform_small(), uniform_small(), profile("s3-spark"))
    assert not result.plan_sees_a_difference
    assert not result.indistinguishable_but_different


def test_two_layouts_with_different_bytes_are_visible_to_the_plan():
    result = compare(uniform(10, 1_000), uniform(10, 2_000), profile("s3-spark"))
    assert result.plan_sees_a_difference


def test_a_comparison_against_a_free_scan_reports_zero_rather_than_dividing():
    free = tiny(open_ms=0, parse_ms=0, footer_bytes=0, throughput_mib_per_s=10**9)
    result = compare(uniform(1, 1), uniform(1, 1), free)
    assert result.time_ratio in (0.0, pytest.approx(1.0))
