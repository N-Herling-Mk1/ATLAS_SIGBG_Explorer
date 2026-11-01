"""
build_eda.py -- per-file column lists for the site's EDA page.

Reads   results/<run>/00_common/feature_inventory.txt   (written by the pipeline)
Writes  data/<run>_eda.js   as window.SIGBG.eda[<run>] = {files: {label: [columns]}, order: [labels]}

Everything else the EDA page shows (exclusions, duplicates, region audit, unit tests, NaN / -999
fractions, dead and suspicious features) is already in data/<run>.js. build_site.py calls this
for every run it builds; it can also be run on its own:

    python site_builder/build_eda.py              # every run under results/
    python site_builder/build_eda.py --runs mk5_r1
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
DATA_OUT = REPO / "data"

HEAD = re.compile(r"^FEATURES IN FILE:\s*(\S+)\s+\((\d+)\)\s*$")
ROW = re.compile(r"^\s+\d+\s+(\S+)")


def parse_inventory(txt):
    """Return ({label: [columns]}, [labels in file order]) from feature_inventory.txt."""
    files, order, cur = {}, [], None
    for line in txt.splitlines():
        if line.startswith("="):
            continue
        m = HEAD.match(line.strip())
        if m:
            cur = m.group(1)
            files[cur], expected = [], int(m.group(2))
            files[cur + "__n"] = expected
            order.append(cur)
            continue
        if cur and line.strip() and not line.startswith(" "):
            cur = None                      # any other section header ends the per-file block
            continue
        if cur:
            r = ROW.match(line)
            if r:
                files[cur].append(r.group(1))
    out = {}
    for lab in order:
        cols, n = files[lab], files[lab + "__n"]
        if len(cols) != n:
            print(f"  WARNING {lab}: header says {n} columns, parsed {len(cols)}", flush=True)
        out[lab] = cols
    return out, order


def build(run):
    inv = RESULTS / run / "00_common" / "feature_inventory.txt"
    if not inv.exists():
        print(f"  eda: {run}: no 00_common/feature_inventory.txt, skipped", flush=True)
        return None
    files, order = parse_inventory(inv.read_text(encoding="utf-8", errors="replace"))
    if not files:
        print(f"  eda: {run}: no 'FEATURES IN FILE' sections found, skipped", flush=True)
        return None
    payload = {"files": files, "order": order, "built": time.strftime("%Y-%m-%d %H:%M"),
               "source": f"results/{run}/00_common/feature_inventory.txt"}
    js = ("window.SIGBG = window.SIGBG || {runs: {}};\nwindow.SIGBG.eda = window.SIGBG.eda || {};\n"
          "window.SIGBG.eda[" + json.dumps(run) + "] = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    DATA_OUT.mkdir(exist_ok=True)
    (DATA_OUT / f"{run}_eda.js").write_text(js, encoding="utf-8")
    print(f"  eda: wrote data/{run}_eda.js  ({len(order)} files, "
          + ", ".join(f"{k} {len(files[k])}" for k in order) + ")", flush=True)
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=None, help="run folder names under results/ (default: all)")
    a = ap.parse_args()
    runs = a.runs or sorted(p.name for p in RESULTS.iterdir() if (p / "00_common").is_dir())
    if not runs:
        sys.exit(f"no runs with 00_common/ under {RESULTS}")
    for i, run in enumerate(runs, 1):
        print(f"[{i}/{len(runs)}] {run}", flush=True)
        build(run)
    print("done.", flush=True)


if __name__ == "__main__":
    main()
