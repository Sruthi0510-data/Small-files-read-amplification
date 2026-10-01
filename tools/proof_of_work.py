"""Capture this repository's own commands and commit the transcript.

The command list is the README's claims, in the order the README makes them. If
a claim changes, the list changes with it, and the capture fails the build when
a command does not exit the way the README says it does, so all four documented
exit codes are demonstrated rather than asserted.

The captured suite run deselects the two tests that read this transcript back,
and that is not tidying up after an inconvenience. Those two tests assert that
every command in the committed transcript exited as expected, and the suite is
itself one of those commands, so capturing them creates a cycle: a transcript
recording a failing suite makes the transcript tests fail, which makes the suite
fail, which makes the next capture record a failing suite. It happened exactly
once, from a stale figure in the README, and the repository sat in a state that
could not regenerate itself.

Everything else in the suite is captured, the two deselected tests still run in
the full suite and in CI, and the title of the rendered transcript says the run
was narrowed so nobody reads it as the whole suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_terminal import Step, capture  # noqa: E402

PY = sys.executable

SELF_REFERENTIAL = (
    "--deselect",
    "tests/test_tools.py::test_every_captured_command_exited_as_the_readme_claims",
    "--deselect",
    "tests/test_tools.py::test_the_proof_of_work_transcript_covers_all_four_exit_codes",
    "--deselect",
    "tests/test_tools.py::test_the_transcript_shows_both_verdicts_on_the_same_model",
)
"""The tests that read the transcript this run is about to overwrite."""

STEPS = [
    Step(
        label="the suite, with branch coverage",
        argv=[PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--cov=sfa",
              "--cov-branch", "--cov-report=term-missing", "--cov-fail-under=100",
              *SELF_REFERENTIAL],
        max_lines=15,
        tail_lines=4,
    ),
    Step(
        label="one scan, split where the plan's knowledge stops",
        argv=[PY, "-m", "sfa.cli", "scan"],
        expect=3,
        max_lines=22,
    ),
    Step(
        label="the same model on a table that does not need fixing",
        argv=[PY, "-m", "sfa.cli", "scan", "--layout", "uniform-large"],
        expect=0,
        max_lines=8,
        tail_lines=5,
    ),
    Step(
        label="two layouts with identical plans and one order of magnitude between them",
        argv=[PY, "-m", "sfa.cli", "indistinguishable"],
        expect=3,
        max_lines=13,
    ),
    Step(
        label="what partition pruning promises against what it buys",
        argv=[PY, "-m", "sfa.cli", "prune"],
        expect=3,
        max_lines=12,
    ),
    Step(
        label="pricing a quoted performance improvement against this table",
        argv=[PY, "-m", "sfa.cli", "claim", "--improvement", "0.40"],
        expect=0,
        max_lines=13,
    ),
    Step(
        label="the same claim against a table that was already well laid out: a refusal",
        argv=[PY, "-m", "sfa.cli", "claim", "--layout", "uniform-large", "--improvement", "0.9"],
        expect=4,
        max_lines=7,
    ),
    Step(
        label="a partition filter the table cannot satisfy",
        argv=[PY, "-m", "sfa.cli", "prune", "--keep", "999"],
        expect=2,
        max_lines=3,
    ),
    Step(
        label="every published figure re-checked against the prose",
        argv=[PY, "tools/check_numbers.py"],
        max_lines=3,
    ),
]


def main() -> int:
    return capture(
        STEPS,
        title=("small-files-read-amplification: captured by tools/proof_of_work.py, exit codes as "
               "returned. The suite run deselects the three tests that read this transcript."),
        out_svg=ROOT / "docs" / "img" / "proof-of-work.svg",
        out_json=ROOT / "docs" / "proof-of-work.json",
    )


if __name__ == "__main__":
    raise SystemExit(main())
