"""Tests for the fix and for the optimisation that disappoints."""

from __future__ import annotations

import pytest

from sfa.compaction import plan_compaction, scans_to_target, sweep_targets
from sfa.cost import break_even_bytes, profile
from sfa.fixtures import COMPACTED_DAYS, RECENT_DAYS, events, uniform_small
from sfa.layout import MIB, DataFile, Layout, LayoutError, uniform
from sfa.pruning import prune, prune_to

S3 = profile("s3-spark")


def test_compaction_preserves_bytes_and_rows():
    layout = uniform_small()
    plan = plan_compaction(layout, 8 * MIB, S3)
    assert plan.after.total_bytes == layout.total_bytes
    assert plan.after.total_rows == layout.total_rows


def test_compaction_reduces_the_file_count():
    plan = plan_compaction(uniform_small(), 8 * MIB, S3)
    assert plan.files_removed > 0


def test_a_zero_target_is_refused():
    with pytest.raises(LayoutError, match="positive size"):
        plan_compaction(uniform_small(), 0, S3)


def test_a_target_larger_than_the_table_gives_one_file():
    plan = plan_compaction(uniform_small(), 10**12, S3)
    assert plan.after.file_count == 1


def test_the_improvement_share_is_saved_over_original():
    plan = plan_compaction(uniform_small(), 8 * MIB, S3)
    assert plan.improvement_share == pytest.approx(plan.saved_ms / plan.before.total_ms)


def test_the_speedup_and_the_improvement_are_different_numbers():
    """Conflating them is how a 2x speedup gets reported as 200 percent."""
    plan = plan_compaction(uniform_small(), 8 * MIB, S3)
    assert plan.speedup > 2
    assert plan.improvement_share < 1


def test_compacting_an_already_large_table_saves_nothing_and_never_pays_back():
    layout = uniform(2, 256 * MIB, name="already-fine")
    plan = plan_compaction(layout, 256 * MIB, S3)
    assert plan.saved_ms <= 0
    assert plan.scans_to_pay_back == float("inf")


def test_a_rewrite_costs_more_than_a_scan():
    plan = plan_compaction(uniform_small(), 8 * MIB, S3)
    assert plan.rewrite_ms > plan.before.total_ms


def test_the_payback_is_the_rewrite_over_the_saving():
    plan = plan_compaction(uniform_small(), 8 * MIB, S3)
    assert plan.scans_to_pay_back == pytest.approx(plan.rewrite_ms / plan.saved_ms)


def test_a_target_above_the_break_even_size_says_so():
    plan = plan_compaction(uniform_small(), 128 * MIB, S3)
    assert plan.target_is_above_break_even


def test_a_target_below_the_break_even_size_says_so():
    plan = plan_compaction(uniform_small(), 64 * 1024, S3)
    assert not plan.target_is_above_break_even


def test_the_gain_is_concentrated_below_the_break_even_size():
    """Where compaction earns its cost, stated as a comparison rather than a feeling.

    Going from a quarter of the break-even size up to it gains more than
    multiplying the target by sixty-four above it does. A job configured to
    compact everything into enormous files is paying a great deal to move a
    number that has stopped mattering.
    """
    break_even = int(break_even_bytes(S3))
    layout = events()
    quarter = plan_compaction(layout, break_even // 4, S3)
    at = plan_compaction(layout, break_even, S3)
    far_above = plan_compaction(layout, 64 * break_even, S3)
    gain_below = at.improvement_share - quarter.improvement_share
    gain_above = far_above.improvement_share - at.improvement_share
    assert gain_below > gain_above


def test_a_sweep_returns_one_plan_per_target():
    targets = (1 * MIB, 8 * MIB, 64 * MIB)
    assert len(sweep_targets(uniform_small(), targets, S3)) == 3


def test_the_search_finds_the_cheapest_rewrite_reaching_a_claim():
    found = scans_to_target(events(), S3, 0.40)
    assert found is not None and found.improvement_share >= 0.40


def test_the_search_returns_the_cheapest_not_the_most_impressive():
    found = scans_to_target(events(), S3, 0.40)
    smaller = plan_compaction(events(), found.target_bytes // 2, S3)
    assert smaller.improvement_share < 0.40


def test_an_unreachable_claim_returns_nothing():
    """The answer for a table that was already well laid out."""
    assert scans_to_target(uniform(2, 256 * MIB), S3, 0.9) is None


def test_a_claim_outside_zero_to_one_is_refused():
    for value in (0.0, 1.0, 1.5, -0.2):
        with pytest.raises(LayoutError, match="strictly between"):
            scans_to_target(uniform_small(), S3, value)


def test_the_shipped_table_reaches_forty_percent_below_break_even():
    """The finding that prices an unsourced performance claim."""
    found = scans_to_target(events(), S3, 0.40)
    assert found is not None and not found.target_is_above_break_even


def test_the_shipped_table_has_the_shape_the_fixture_claims():
    layout = events()
    assert len(layout.partitions) == COMPACTED_DAYS + RECENT_DAYS
    assert layout.small_file_share(1 * MIB) > 0.99
    assert layout.bytes_in_small_files(1 * MIB) / layout.total_bytes < 0.25


def test_pruning_keeps_only_the_named_partitions():
    report = prune(events(), ["2026-09-01"], S3)
    assert report.pruned.file_count == 2


def test_pruning_to_an_unknown_partition_is_refused():
    with pytest.raises(LayoutError, match="no such partition"):
        prune(events(), ["2026-10-01"], S3)


def test_pruning_to_nothing_is_refused():
    with pytest.raises(LayoutError, match="leaves nothing"):
        prune(events(), [], S3)


def test_pruning_to_zero_partitions_is_refused():
    with pytest.raises(LayoutError, match="leaves nothing"):
        prune_to(events(), 0, S3)


def test_pruning_to_more_partitions_than_exist_is_refused():
    with pytest.raises(LayoutError, match="partitions, not"):
        prune_to(events(), 999, S3)


def test_pruning_to_the_recent_days_drops_bytes_and_keeps_files():
    """The mechanism: the recent partitions hold most files and least bytes."""
    report = prune_to(events(), RECENT_DAYS, S3)
    assert report.bytes_kept_share < 0.3
    assert report.files_kept_share > 0.99


def test_the_plan_overstates_what_pruning_buys():
    report = prune_to(events(), RECENT_DAYS, S3)
    assert report.plan_promised_speedup > 3
    assert report.modelled_speedup < 1.3
    assert report.overstatement > 3


def test_pruning_a_uniform_table_is_not_overstated():
    """The plan is right when every partition has the same bytes per file."""
    files = tuple(
        DataFile(bytes=8 * MIB, rows=1_000, partition=f"p{index % 4}") for index in range(80)
    )
    report = prune_to(Layout(files=files, name="even"), 1, S3)
    assert report.overstatement == pytest.approx(1.0, abs=0.05)


def test_pruning_keeps_the_partitions_it_reports():
    report = prune_to(events(), 2, S3)
    assert len(report.kept_partitions) == 2
    assert report.total_partitions == COMPACTED_DAYS + RECENT_DAYS
