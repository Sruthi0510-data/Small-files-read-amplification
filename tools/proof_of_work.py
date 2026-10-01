"""Capture this repository's own commands and commit the transcript.

The command list is the README's claims, in the order the README makes them. If
a claim changes, the list changes with it, and the capture fails the build when
a command does not exit the way the README says it does, so all four documented
exit codes are demonstrated rather than asserted.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_terminal import Step, capture  # noqa: E402

PY = sys.executable

STEPS = [
    Step(
        label="the suite, with branch coverage",
        argv=[PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--cov=sfa",
              "--cov-branch", "--cov-report=term-missing", "--cov-fail-under=100"],
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
        title="small-files-read-amplification: captured by tools/proof_of_work.py, exit codes as returned",
        out_svg=ROOT / "docs" / "img" / "proof-of-work.svg",
        out_json=ROOT / "docs" / "proof-of-work.json",
    )


if __name__ == "__main__":
    raise SystemExit(main())
