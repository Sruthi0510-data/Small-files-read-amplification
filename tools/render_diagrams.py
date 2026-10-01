"""Emit the README's diagram as SVG, with every number read from the metrics.

Hand-written SVG rather than Mermaid, for the usual four reasons: Mermaid does
not render in a PDF export, does not render in an editor preview that is not
GitHub, chooses its own layout so a longer label makes it illegible, and cannot
read a number from a metrics file, which leaves every figure in it unguarded.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "docs" / "metrics.json"
OUT = ROOT / "docs" / "img"

SURFACE = "#fcfcfb"
INK = "#1d1d1b"
MUTED = "#6b6b66"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
RULE = "#d9d9d4"
FONT = "font-family=\"-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif\""


def _text(x, y, content, *, size=13, fill=INK, weight="400", anchor="start"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{content}</text>'
    )


def where_the_time_goes(metrics: dict) -> str:
    """One bar, split where the plan's knowledge stops."""
    width, height = 880, 300
    blind = metrics["plan_blind_pct"] / 100.0
    bar_x, bar_w, bar_y, bar_h = 24, 832, 118, 54
    visible_w = bar_w * (1 - blind)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Where a scan's time goes</title>",
        f"<desc id=\"desc\">A single bar representing one modelled scan, split into the "
        f"{metrics['plan_visible_label']} a query plan reports and the "
        f"{metrics['plan_blind_pct']} percent it cannot, which is time spent opening files.</desc>",
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(24, 34, "Where one scan's time goes", size=17, weight="600"),
        _text(
            24,
            58,
            f"{metrics['files']:,} files, {metrics['gib']} GiB, median file {metrics['median_file_kib']} KiB",
            size=12.5,
            fill=MUTED,
        ),
        _text(24, 96, "modelled scan", size=12, fill=MUTED),
        f'<rect x="{bar_x}" y="{bar_y}" width="{visible_w:.1f}" height="{bar_h}" '
        f'rx="4" fill="{BLUE}"/>',
        f'<rect x="{bar_x + visible_w:.1f}" y="{bar_y}" width="{bar_w - visible_w:.1f}" '
        f'height="{bar_h}" rx="4" fill="{ORANGE}"/>',
    ]
    parts.append(
        _text(
            bar_x + visible_w / 2,
            bar_y + bar_h + 24,
            f"reading bytes, {100 - metrics['plan_blind_pct']:.1f}%",
            size=12,
            fill=BLUE,
            weight="600",
            anchor="middle",
        )
    )
    parts.append(
        _text(
            bar_x + visible_w + (bar_w - visible_w) / 2,
            bar_y + bar_h + 24,
            f"opening files, {metrics['plan_blind_pct']}%",
            size=12,
            fill=ORANGE,
            weight="600",
            anchor="middle",
        )
    )
    parts.append(
        f'<line x1="{bar_x + visible_w:.1f}" y1="{bar_y - 14}" '
        f'x2="{bar_x + visible_w:.1f}" y2="{bar_y + bar_h + 32}" stroke="{RULE}" '
        f'stroke-width="1.5" stroke-dasharray="4 4"/>'
    )
    parts.append(
        _text(
            bar_x + visible_w + 8,
            bar_y - 20,
            "everything to the right of this line is invisible to a query plan",
            size=12,
            fill=MUTED,
        )
    )
    parts.append(
        f'<rect x="{bar_x}" y="222" width="{bar_w}" height="48" rx="8" fill="none" '
        f'stroke="{RULE}" stroke-width="1.5"/>'
    )
    parts.append(
        _text(
            bar_x + 20,
            252,
            f"break-even file size {metrics['break_even_mib']} MiB"
            f"   .   this table's median file {metrics['median_file_kib']} KiB"
            f"   .   amplification {metrics['amplification']}x",
            size=13,
        )
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))["metrics"]
    metrics = dict(metrics)
    metrics["plan_visible_label"] = f"{100 - metrics['plan_blind_pct']:.1f} percent"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "where-the-time-goes.svg").write_text(where_the_time_goes(metrics) + "\n", encoding="utf-8")
    print(f"wrote 1 diagram to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
