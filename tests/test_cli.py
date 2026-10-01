"""Tests for the command line and its four exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sfa.cli import AMPLIFIED, BAD_INPUT, OK, UNDETERMINED, main


def test_no_command_is_a_usage_error():
    with pytest.raises(SystemExit):
        main([])


def test_scan_finds_amplification_on_the_shipped_table(capsys):
    assert main(["scan"]) == AMPLIFIED
    out = capsys.readouterr().out
    assert "invisible to a plan" in out and "opening files" in out


def test_scan_separates_what_the_plan_does_and_does_not_report(capsys):
    main(["scan"])
    out = capsys.readouterr().out
    assert "what the plan reports" in out and "what the plan does not report" in out


def test_scan_of_a_well_laid_out_table_exits_zero(capsys):
    assert main(["scan", "--layout", "uniform-large"]) == OK
    assert "which is what the plan reports" in capsys.readouterr().out


def test_scan_accepts_another_profile():
    assert main(["scan", "--profile", "local-nvme"]) == AMPLIFIED


def test_an_unknown_layout_is_rejected_by_the_parser():
    with pytest.raises(SystemExit):
        main(["scan", "--layout", "nope"])


def test_indistinguishable_shows_two_equal_plans_and_two_times(capsys):
    assert main(["indistinguishable"]) == AMPLIFIED
    out = capsys.readouterr().out
    assert "plans are equal     True" in out
    assert "order of magnitude longer" in out


def test_indistinguishable_on_fast_storage_is_still_a_finding():
    assert main(["indistinguishable", "--profile", "local-nvme"]) == AMPLIFIED


def test_prune_reports_the_overstatement(capsys):
    assert main(["prune"]) == AMPLIFIED
    out = capsys.readouterr().out
    assert "plan promises" in out and "overstated by" in out


def test_prune_on_a_uniform_table_is_not_a_finding(capsys):
    assert main(["prune", "--layout", "uniform-large", "--keep", "1"]) == OK
    assert "close to what pruning actually buys" in capsys.readouterr().out


def test_pruning_more_partitions_than_exist_is_a_bad_input(capsys):
    assert main(["prune", "--keep", "999"]) == BAD_INPUT
    assert "partitions, not" in capsys.readouterr().err


def test_compact_sweeps_targets_and_reports_payback(capsys):
    assert main(["compact"]) == AMPLIFIED
    out = capsys.readouterr().out
    assert "payback" in out and "break-even file" in out


def test_compact_on_a_table_that_needs_none_exits_zero(capsys):
    assert main(["compact", "--layout", "uniform-large"]) == OK


def test_compact_shows_never_for_a_rewrite_that_saves_nothing(capsys):
    main(["compact", "--layout", "uniform-large"])
    assert "never" in capsys.readouterr().out


def test_claim_prices_a_quoted_improvement(capsys):
    assert main(["claim"]) == OK
    out = capsys.readouterr().out
    assert "cheapest rewrite" in out and "paid back in" in out


def test_claim_says_when_the_figure_needs_no_real_fix(capsys):
    """The finding that prices an unsourced performance number."""
    main(["claim", "--improvement", "0.40"])
    assert "reachable without fixing the layout" in capsys.readouterr().out


def test_a_claim_no_rewrite_reaches_is_undetermined(capsys):
    assert main(["claim", "--layout", "uniform-large", "--improvement", "0.9"]) == UNDETERMINED
    assert "describes nothing" in capsys.readouterr().out


def test_a_claim_outside_zero_to_one_is_a_bad_input(capsys):
    assert main(["claim", "--improvement", "1.5"]) == BAD_INPUT


def test_a_high_claim_the_shipped_table_does_reach_exits_zero():
    assert main(["claim", "--improvement", "0.80"]) == OK


def test_profiles_lists_every_break_even_size(capsys):
    assert main(["profiles"]) == OK
    out = capsys.readouterr().out
    assert "break-even" in out and "s3-spark" in out


def test_profiles_states_the_counterintuitive_part(capsys):
    main(["profiles"])
    assert "raises the break-even size" in capsys.readouterr().out


def test_json_prints_the_scan(capsys):
    assert main(["json"]) == AMPLIFIED
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_blind_share"] > 0.5


def test_json_of_a_sound_layout_exits_zero(capsys):
    assert main(["json", "--layout", "uniform-large"]) == OK


def test_json_writes_to_a_file(tmp_path: Path, capsys):
    out = tmp_path / "scan.json"
    assert main(["json", "--out", str(out)]) == AMPLIFIED
    assert json.loads(out.read_text())["files"] > 1_000


def test_an_unknown_profile_is_rejected_by_the_parser():
    with pytest.raises(SystemExit):
        main(["scan", "--profile", "hdfs"])


def test_the_four_exit_codes_are_distinct():
    assert len({OK, BAD_INPUT, AMPLIFIED, UNDETERMINED}) == 4


def test_two_layouts_the_plan_can_tell_apart_are_not_a_finding(capsys):
    """The command is useful on any pair, including one the plan does see."""
    code = main(["indistinguishable", "--left", "events", "--right", "uniform-large"])
    assert code == OK
    assert "the plans differ, or the times do not" in capsys.readouterr().out


def test_comparing_a_layout_with_itself_is_not_a_finding():
    assert main(["indistinguishable", "--left", "events", "--right", "events"]) == OK
