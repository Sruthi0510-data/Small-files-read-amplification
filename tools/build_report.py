"""Build the standalone HTML report from the experiment JSON.

One file, no assets, no network. Every number comes from running the code, so
the report cannot disagree with the README even when only one was regenerated.

The verdict badge carries an explicit colour rather than inheriting one, and the
screenshot tool reads the computed style back, because a badge rendered in its
own background colour passes every test in the suite and is invisible.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs" / "experiments" / "exp01.json"
OUT = ROOT / "docs" / "report.html"

STYLE = """
:root { --surface:#fcfcfb; --ink:#1d1d1b; --muted:#6b6b66; --rule:#d9d9d4;
        --blue:#2a78d6; --orange:#eb6834; --green:#1baf7a; }
* { box-sizing: border-box; }
body { margin:0 auto; padding:48px 24px 96px; max-width:920px; background:var(--surface);
       color:var(--ink); line-height:1.55;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; }
h1 { font-size:30px; margin:0 0 8px; letter-spacing:-0.01em; }
h2 { font-size:20px; margin:48px 0 12px; padding-top:18px; border-top:1px solid var(--rule); }
p { margin:0 0 14px; }
.lede { color:var(--muted); font-size:15px; margin-bottom:28px; }
.verdict { display:inline-block; padding:6px 14px; border-radius:999px; font-weight:600;
           font-size:13px; color:#ffffff; background:var(--orange); }
.figures { display:flex; flex-wrap:wrap; gap:16px; margin:24px 0 8px; }
.figure { flex:1 1 190px; border:1px solid var(--rule); border-radius:10px; padding:16px 18px;
          background:#ffffff; }
.figure .value { font-size:28px; font-weight:600; letter-spacing:-0.02em; }
.figure .label { font-size:12px; color:var(--muted); margin-top:4px; }
table { border-collapse:collapse; width:100%; margin:16px 0; font-size:14px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--rule); }
th { font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:0.04em;
     color:var(--muted); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }
.note { font-size:13px; color:var(--muted); }
.split { display:flex; height:40px; border-radius:6px; overflow:hidden; margin:12px 0 6px; }
.split .visible { background:var(--blue); }
.split .blind { background:var(--orange); }
"""


def _figure(value: str, label: str) -> str:
    return f'<div class="figure"><div class="value">{value}</div><div class="label">{label}</div></div>'


def build() -> str:
    payload = json.loads(EXPERIMENT.read_text())
    blind = 100 * payload["plan_blind_share"]
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Read amplification report</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>How much of this scan can the plan account for?</h1>",
        '<p class="lede">One modelled table on object storage, read by Spark. Every figure '
        "below is produced by running the code in this repository against the shipped "
        "layout.</p>",
        '<p><span class="verdict">most of it, no</span></p>',
        '<h2 id="summary">Summary</h2>',
        '<div class="figures">',
        _figure(f"{blind:.1f}%", "of modelled time no plan reports"),
        _figure(f"{payload['amplification']:.1f}x", "longer than the bytes suggest"),
        _figure(f"{payload['files']:,}", "files holding "
                f"{payload['bytes'] / 1024 ** 3:.1f} GiB"),
        _figure(f"{payload['break_even_mib']:.1f} MiB", "break-even file size"),
        "</div>",
        f'<div class="split"><div class="visible" style="width:{100 - blind:.1f}%"></div>'
        f'<div class="blind" style="width:{blind:.1f}%"></div></div>',
        f'<p class="note">Blue is reading bytes, which every plan reports. Orange is opening '
        f"files, which none does. The median file in this table is "
        f"{payload['median_file_kib']:.0f} KiB against a break-even size of "
        f"{payload['break_even_mib']:.1f} MiB.</p>",
        '<h2 id="indistinguishable">Two layouts a plan cannot separate</h2>',
        "<p>Same bytes, same rows, same partitions, and "
        f"{payload['pair_file_ratio']:,.0f} times the file count. The modelled times differ by "
        f"{payload['pair_time_ratio']:.0f} times, and no field in any plan output separates "
        "them.</p>",
        '<h2 id="pruning">What pruning promises against what it buys</h2>',
        "<table><thead><tr><th>quantity</th><th>value</th></tr></thead><tbody>"
        f"<tr><td>bytes kept</td><td class=\"num\">{100 * payload['prune_bytes_kept']:.1f}%</td></tr>"
        f"<tr><td>files kept</td><td class=\"num\">{100 * payload['prune_files_kept']:.1f}%</td></tr>"
        f"<tr><td>speedup the plan promises</td><td class=\"num\">{payload['prune_promised']:.1f}x</td></tr>"
        f"<tr><td>speedup the model delivers</td><td class=\"num\">{payload['prune_delivered']:.2f}x</td></tr>"
        f"<tr><td>overstatement</td><td class=\"num\">{payload['prune_overstatement']:.1f}x</td></tr>"
        "</tbody></table>",
        '<p class="note">Pruning removed the cheap half of the cost and left the expensive '
        "one, because the recent partitions hold almost all of the files and the fewest "
        "bytes.</p>",
        '<h2 id="compaction">What compaction buys, and what it costs</h2>',
        "<table><thead><tr><th>target</th><th>files after</th><th>scan</th>"
        "<th>improvement</th><th>pays back after</th></tr></thead><tbody>",
    ]
    for row in payload["compaction"]:
        payback = "never" if row["payback_scans"] is None else f"{row['payback_scans']:.1f} scans"
        parts.append(
            f"<tr><td>{row['target_kib']:,} KiB</td>"
            f"<td class=\"num\">{row['files']:,}</td>"
            f"<td class=\"num\">{row['scan_ms']:,.0f} ms</td>"
            f"<td class=\"num\">{100 * row['improvement']:.1f}%</td>"
            f"<td class=\"num\">{payback}</td></tr>"
        )
    parts += [
        "</tbody></table>",
        f'<p class="note">A rewrite reads every byte and writes every byte, so the honest '
        f"unit is the number of scans it takes to pay that back. The break-even target "
        f"reaches {100 * payload['improvement_at_break_even']:.1f}% and repays itself in "
        f"{payload['payback_at_break_even']:.1f} scans; everything above it is a long tail "
        "bought at full rewrite price.</p>",
        '<h2 id="claim">Pricing a performance claim</h2>',
        f"<p>A claim of a {100 * payload['claim']:.0f}% improvement, priced against this "
        f"table: the cheapest rewrite that reaches it targets "
        f"{payload['claim_target_kib']:,} KiB files, delivers "
        f"{100 * payload['claim_improvement']:.1f}%, and leaves "
        f"{payload['claim_files_after']:,} files behind, every one of them below the "
        "break-even size.</p>",
        '<p class="note">So the figure is reachable without fixing the layout. A performance '
        "claim without its starting layout is not a weak claim; it is not a claim.</p>",
        "</body></html>",
    ]
    return "\n".join(parts)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build() + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
