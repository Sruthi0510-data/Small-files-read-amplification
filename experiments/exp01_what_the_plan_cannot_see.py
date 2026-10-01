"""Everything the plan reports, everything it does not, and the gap between them.

Five measurements, all on the shipped layouts, all from the same cost model with
its parameters on the page.

One: how much of a scan of the shipped table is invisible to a plan.
Two: two layouts a plan cannot tell apart, and the ratio between their times.
Three: what partition pruning promises against what it delivers.
Four: where compaction earns its cost and where it stops.
Five: what a quoted performance improvement would have taken to produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sfa.compaction import plan_compaction, scans_to_target  # noqa: E402
from sfa.cost import PROFILES, break_even_bytes, profile, scan_cost  # noqa: E402
from sfa.fixtures import RECENT_DAYS, events, uniform_large, uniform_small  # noqa: E402
from sfa.layout import MIB  # noqa: E402
from sfa.plan import compare  # noqa: E402
from sfa.pruning import prune_to  # noqa: E402

TARGETS = (64 * 1024, 1 * MIB, 8 * MIB, 32 * MIB, 128 * MIB, 512 * MIB)
CLAIM = 0.40


def main() -> dict[str, object]:
    storage = profile("s3-spark")
    table = events()
    cost = scan_cost(table, storage)

    pair = compare(uniform_small(), uniform_large(), storage)
    pruning = prune_to(table, RECENT_DAYS, storage)
    sweep = [plan_compaction(table, target, storage) for target in TARGETS]
    claim = scans_to_target(table, storage, CLAIM)

    profiles = []
    for name in sorted(PROFILES):
        entry = PROFILES[name]
        profiles.append(
            {
                "profile": name,
                "per_file_ms": entry.per_file_ms,
                "throughput_mib_per_s": entry.throughput_mib_per_s,
                "break_even_mib": break_even_bytes(entry) / MIB,
                "blind_share": scan_cost(table, entry).plan_blind_share,
            }
        )

    best = max(sweep, key=lambda item: item.improvement_share)
    at_break_even = plan_compaction(table, int(break_even_bytes(storage)), storage)

    return {
        "files": cost.file_count,
        "bytes": cost.total_bytes,
        "rows": cost.total_rows,
        "partitions": len(table.partitions),
        "median_file_kib": table.median_file_bytes / 1024,
        "mean_file_kib": table.mean_file_bytes / 1024,
        "small_file_share": table.small_file_share(1 * MIB),
        "bytes_in_small_files_share": table.bytes_in_small_files(1 * MIB) / table.total_bytes,
        "total_ms": cost.total_ms,
        "plan_visible_ms": cost.plan_visible_ms,
        "plan_blind_ms": cost.plan_blind_ms,
        "plan_blind_share": cost.plan_blind_share,
        "amplification": cost.amplification,
        "break_even_mib": break_even_bytes(storage) / MIB,
        "pair_plans_equal": not pair.plan_sees_a_difference,
        "pair_time_ratio": pair.time_ratio,
        "pair_file_ratio": pair.file_count_ratio,
        "prune_bytes_kept": pruning.bytes_kept_share,
        "prune_files_kept": pruning.files_kept_share,
        "prune_promised": pruning.plan_promised_speedup,
        "prune_delivered": pruning.modelled_speedup,
        "prune_overstatement": pruning.overstatement,
        "compaction": [
            {
                "target_kib": item.target_bytes // 1024,
                "files": item.after.file_count,
                "scan_ms": item.after.total_ms,
                "improvement": item.improvement_share,
                "payback_scans": None if item.scans_to_pay_back == float("inf") else item.scans_to_pay_back,
                "above_break_even": item.target_is_above_break_even,
            }
            for item in sweep
        ],
        "best_improvement": best.improvement_share,
        "best_target_mib": best.target_bytes / MIB,
        "improvement_at_break_even": at_break_even.improvement_share,
        "payback_at_break_even": at_break_even.scans_to_pay_back,
        "claim": CLAIM,
        "claim_target_kib": claim.target_bytes // 1024,
        "claim_improvement": claim.improvement_share,
        "claim_payback_scans": claim.scans_to_pay_back,
        "claim_files_after": claim.after.file_count,
        "claim_above_break_even": claim.target_is_above_break_even,
        "profiles": profiles,
    }


if __name__ == "__main__":
    payload = main()
    (ROOT / "docs" / "experiments").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "experiments" / "exp01.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in payload.items() if not isinstance(v, list)}, indent=2))
