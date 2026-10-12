"""Re-measure every published figure and write docs/metrics.json.

Nothing is typed by hand. The test count and the coverage come from pytest's
machine readable reports, and every other figure comes from the experiment,
which is produced by running the experiment.

Anchors pair each value with two or three words of its context, because a
checker that searches for digits passes happily while the sentence around them
has gone stale.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_tables import table_values  # noqa: E402

DOCS = ROOT / "docs"
EXPERIMENT = ROOT / "experiments" / "exp01_what_the_plan_cannot_see.py"
EXPERIMENT_OUTPUT = DOCS / "experiments" / "exp01.json"
JUNIT = ROOT / "junit.xml"
COVERAGE_JSON = ROOT / "coverage.json"
METRICS_PATH = DOCS / "metrics.json"


def checked_documents() -> list[str]:
    """Every prose document in the repository, found rather than listed.

    An earlier version carried a hardcoded list, and deleting a document from
    the repository then failed the build with "listed as a checked document and
    not present". Removing a document is an ordinary editorial act, and a
    receipts mechanism that treats it as a build failure is a mechanism people
    learn to edit around.

    Discovery makes the set self-maintaining in both directions: a document
    added to docs/ is checked from the moment it exists, and a document deleted
    stops being checked without anyone having to remember a second place.

    Sorted so the output is stable, and relative so the committed metrics file
    does not record the path this happened to be built at.
    """
    found = [ROOT / "README.md"] if (ROOT / "README.md").exists() else []
    found += sorted(p for p in (ROOT / "docs").rglob("*.md") if p.is_file())
    return [str(p.relative_to(ROOT)) for p in found]


ANCHORS: dict[str, list[str]] = {
    "tests_total": ["{} tests,"],
    "coverage_line_pct": ["{}% line"],
    "coverage_branch_pct": ["{}% branch"],
    "files": ["holds {} files"],
    "partitions": ["across {} partitions"],
    "gib": ["{} GiB"],
    "median_file_kib": ["median file is {} KiB"],
    "mean_file_kib": ["mean is {} KiB"],
    "small_file_share_pct": ["{}% of the files"],
    "bytes_in_small_files_pct": ["hold {}% of the bytes"],
    "plan_blind_pct": ["{}% of the modelled"],
    "amplification": ["{} times longer"],
    "break_even_mib": ["break-even file size is {} MiB"],
    "pair_time_ratio": ["one takes {} times"],
    "pair_file_ratio": ["{} times as many files"],
    "prune_promised": ["promises a {} times"],
    "prune_delivered": ["delivers {} times"],
    "prune_overstatement": ["overstates it by {}"],
    "best_improvement_pct": ["caps out at {}%"],
    "improvement_at_break_even_pct": ["break-even target reaches {}%"],
    "payback_at_break_even": ["pays for itself in {} scans"],
    "claim_pct": ["{}% performance improvement", "clears {}%", "so {}% is reachable", "a {}% improvement on a table"],
    "claim_improvement_pct": ["actually delivers {}%"],
    "claim_target_kib": ["files of {} KiB"],
    "claim_payback_scans": ["back in {} scans"],
    "claim_files_after": ["still leaves {} files"],
}


def run_tests() -> bool:
    """Run pytest with machine readable reports. Returns whether it was green.

    Deliberately does not raise on a red suite, and that is a fix rather than a
    looseness. The suite contains a test that runs the number checker, the
    number checker compares the documents against the figures this script
    writes, and this script is how a stale figure gets corrected. Refusing to
    measure until the suite is green therefore made a stale figure unfixable:
    the only tool that could repair it declined to run until it had already been
    repaired.

    pytest writes its junit and coverage reports whether it passes or fails, so
    the measurement is available either way. A red suite is a fact to print
    loudly, not a reason to refuse to measure.
    """
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--cov=sfa", f"--cov-report=json:{COVERAGE_JSON}", f"--junitxml={JUNIT}",
        ],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        print(
            "  the suite is red; measuring anyway so a stale figure can be "
            "corrected, then run it again"
        )
    return result.returncode == 0


def read_test_count() -> int:
    root = ET.parse(JUNIT).getroot()
    suite = root if root.tag == "testsuite" else root[0]
    return int(suite.get("tests", 0))


def read_coverage() -> tuple[float, float]:
    totals = json.loads(COVERAGE_JSON.read_text())["totals"]
    line = round(float(totals["percent_covered"]), 1)
    covered, total = totals.get("covered_branches", 0), totals.get("num_branches", 0)
    return line, (round(100.0 * covered / total, 1) if total else 100.0)


def build_metrics(skip_tests: bool) -> dict[str, Any]:
    green = True
    if not skip_tests:
        green = run_tests()
    line_pct, branch_pct = read_coverage()
    subprocess.run([sys.executable, str(EXPERIMENT)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    payload = json.loads(EXPERIMENT_OUTPUT.read_text())

    metrics = {
        "tests_total": read_test_count(),
        "coverage_line_pct": line_pct,
        "coverage_branch_pct": branch_pct,
        "files": payload["files"],
        "partitions": payload["partitions"],
        "gib": round(payload["bytes"] / 1024 ** 3, 1),
        "median_file_kib": round(payload["median_file_kib"]),
        "mean_file_kib": round(payload["mean_file_kib"]),
        "small_file_share_pct": round(100 * payload["small_file_share"], 1),
        "bytes_in_small_files_pct": round(100 * payload["bytes_in_small_files_share"], 1),
        "plan_blind_pct": round(100 * payload["plan_blind_share"], 1),
        "amplification": round(payload["amplification"], 1),
        "break_even_mib": round(payload["break_even_mib"], 1),
        "pair_time_ratio": round(payload["pair_time_ratio"]),
        "pair_file_ratio": round(payload["pair_file_ratio"]),
        "prune_promised": round(payload["prune_promised"], 1),
        "prune_delivered": round(payload["prune_delivered"], 2),
        "prune_overstatement": round(payload["prune_overstatement"], 1),
        "best_improvement_pct": round(100 * payload["best_improvement"], 1),
        "improvement_at_break_even_pct": round(100 * payload["improvement_at_break_even"], 1),
        "payback_at_break_even": round(payload["payback_at_break_even"], 1),
        "claim_pct": round(100 * payload["claim"]),
        "claim_improvement_pct": round(100 * payload["claim_improvement"], 1),
        "claim_target_kib": payload["claim_target_kib"],
        "claim_payback_scans": round(payload["claim_payback_scans"], 1),
        "claim_files_after": payload["claim_files_after"],
    }
    return {
        "metrics": metrics,
        "table_values": table_values(),
        "anchors": ANCHORS,
        "checked_documents": checked_documents(),
        "measured_despite_a_red_suite": not green,
        "note": (
            "every value here is produced by running the suite and the experiment; "
            "tools/check_numbers.py fails the build when a document quotes a figure the code "
            "no longer produces"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="re-measure every published figure")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    payload = build_metrics(skip_tests=args.skip_tests)
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {METRICS_PATH.relative_to(ROOT)} with {len(payload['metrics'])} metrics")
    for name, value in sorted(payload["metrics"].items()):
        print(f"  {name:<28} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
