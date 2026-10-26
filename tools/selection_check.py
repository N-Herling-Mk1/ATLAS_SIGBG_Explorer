#!/usr/bin/env python
"""
selection_check.py  --  how the background and signal samples were selected, measured from the files.

Answers three questions the KS rankings depend on:
  1. Where is the HTmiss edge?  (signal min / background max of htmiss_NOSYS and htmissScalar_NOSYS)
  2. How is the background built?  (jet multiplicity x htmissScalar band)
  3. How do signal and background jet multiplicities compare, per region?
  4. Is there a MET edge too?  (met_met_NOSYS minimum in signal, fraction of background below 20 GeV)

Writes  <out>/E_selection/selection_check.txt  and  selection_check.json  (read by the site builder).
Read-only on the data.  Real data only.

Usage:  python tools/selection_check.py [--data FOLDER] [--out results/mk4_r1]
        data folder: --data, else pipeline/config.txt 'DATA = ...', else $KJ_SIGBG_DATA
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BKG_FILE = "DataHTMissLow_train_data24_cleaned.csv"
MASS_FILES = {
    "mH125_mS15":   "HSS_mH125_mS15_ct580_cleaned.csv",
    "mH125_mS55":   "HSS_mH125_mS55_ct5320_cleaned.csv",
    "mH200_mS50":   "HSS_mH200_mS50_ct1255_cleaned.csv",
    "mH400_mS100":  "HSS_mH400_mS100_ct1610_cleaned.csv",
    "mH600_mS150":  "HSS_mH600_mS150_ct3310_cleaned.csv",
    "mH1000_mS275": "HSS_mH1000_mS275_ct2399_cleaned.csv",
}
COLS = ["htmiss_NOSYS", "htmissScalar_NOSYS", "met_met_NOSYS", "jet_n_NOSYS", "jet_pt_max_NOSYS",
        "msvtx_inBarrel_NOSYS", "msvtx_inEndcaps_NOSYS"]
SCALAR_BANDS = [(-1e9, 1.0, "~0"), (1.0, 40.0, "1-40"), (40.0, 1e9, ">40")]   # GeV
MET_CUT_GEV = 20.0                                                             # signal edge seen in mk2
JET_BINS = [0, 1, 2, 3, 4]                                                     # 4 = 4 or more
SENTINEL = -999.0
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def resolve_data(cli):
    if cli:
        return Path(cli).expanduser(), "--data"
    for cfg in (REPO / "pipeline" / "config.txt", HERE / "config.txt"):
        if cfg.exists():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                s = line.split("#", 1)[0].strip()
                if s.upper().startswith("DATA") and "=" in s:
                    return Path(s.split("=", 1)[1].strip().strip('"').strip("'")).expanduser(), str(cfg.name)
    if os.environ.get("KJ_SIGBG_DATA"):
        return Path(os.environ["KJ_SIGBG_DATA"]).expanduser(), "KJ_SIGBG_DATA"
    sys.exit("No data folder: use --data, pipeline/config.txt (DATA = ...), or $KJ_SIGBG_DATA.")


def gev(s):
    v = pd.to_numeric(s, errors="coerce").replace(SENTINEL, np.nan)
    return v / 1e3


def jet_hist(jn):
    jn = pd.to_numeric(jn, errors="coerce").dropna().clip(upper=4).astype(int)
    n = len(jn)
    return {str(k): int((jn == k).sum()) for k in JET_BINS}, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default=str(REPO / "results" / "mk4_r1"))
    args = ap.parse_args()
    data, src = resolve_data(args.data)
    out = Path(args.out) / "E_selection"
    out.mkdir(parents=True, exist_ok=True)
    log(f"data folder from {src}: {data}")

    files = {"bkg": BKG_FILE, **MASS_FILES}
    samples, lines = {}, []
    for i, (k, f) in enumerate(files.items(), 1):
        p = data / f
        if not p.exists():
            sys.exit(f"missing {p}")
        log(f"[{i}/{len(files)}] {k:<13} {f}")
        x = pd.read_csv(p, usecols=lambda c: c.strip() in COLS, low_memory=False)
        x.columns = [c.strip() for c in x.columns]
        ht, hs = gev(x["htmiss_NOSYS"]), gev(x["htmissScalar_NOSYS"])
        jp = gev(x["jet_pt_max_NOSYS"])
        mt = gev(x["met_met_NOSYS"])
        reg = {"barrel": x["msvtx_inBarrel_NOSYS"] == 1, "endcap": x["msvtx_inEndcaps_NOSYS"] == 1,
               "all": pd.Series(True, index=x.index)}
        rec = {"file": f, "n": int(len(x)),
               "htmiss_min": float(ht.min()), "htmiss_max": float(ht.max()),
               "htmissScalar_min": float(hs.min()), "htmissScalar_max": float(hs.max()),
               "jet_pt_max_min": float(jp.min()), "jet_pt_max_q01": float(jp.quantile(0.01)),
               "met_min": float(mt.min()), "met_q001": float(mt.quantile(0.001)), "met_q01": float(mt.quantile(0.01)),
               "met_median": float(mt.median()), "met_pct_below_20": float(100 * (mt < MET_CUT_GEV).mean()),
               "jets": {}}
        for r, m in reg.items():
            h, n = jet_hist(x.loc[m, "jet_n_NOSYS"])
            rec["jets"][r] = {"n": n, "counts": h}
        if k == "bkg":
            band = pd.cut(hs, [b[0] for b in SCALAR_BANDS] + [SCALAR_BANDS[-1][1]],
                          labels=[b[2] for b in SCALAR_BANDS], right=False)
            jn = pd.to_numeric(x["jet_n_NOSYS"], errors="coerce").clip(upper=4)
            ct = pd.crosstab(jn, band)
            rec["crosstab_jets_x_scalar"] = {str(int(j)): {str(c): int(ct.loc[j, c]) for c in ct.columns}
                                              for j in ct.index}
            edges = [-1, 1, 10, 20, 30, 40, 50, 60, 100, 1e9]
            cnt = pd.cut(hs, edges).value_counts().sort_index()
            rec["scalar_bins"] = [{"lo": float(iv.left), "hi": float(iv.right), "n": int(v)}
                                  for iv, v in cnt.items()]
        samples[k] = rec

    b = samples["bkg"]
    sig_min = min(samples[m]["htmiss_min"] for m in MASS_FILES)
    disjoint = b["htmiss_max"] <= sig_min
    lines += ["SELECTION CHECK", "=" * 78,
              f"background htmiss_NOSYS max   {b['htmiss_max']:8.2f} GeV",
              f"signal     htmiss_NOSYS min   {sig_min:8.2f} GeV   (over 6 mass points)",
              f"samples disjoint in htmiss_NOSYS: {'YES' if disjoint else 'NO'}", "",
              f"met_met_NOSYS: background median {b['met_median']:.2f} GeV, {b['met_pct_below_20']:.2f}% below {MET_CUT_GEV:g} GeV;"
              f" signal minimum {min(samples[m]['met_min'] for m in MASS_FILES):.2f} GeV", "",
              "jet multiplicity (fraction), region all:"]
    hdr = f"  {'sample':<13}" + "".join(f"{('4+' if j == 4 else j):>8}" for j in JET_BINS) + f"{'n':>9}"
    lines.append(hdr)
    for k, rec in samples.items():
        js = rec["jets"]["all"]
        lines.append(f"  {k:<13}" + "".join(f"{js['counts'][str(j)] / max(js['n'], 1):8.3f}" for j in JET_BINS)
                     + f"{js['n']:9,}")
    lines += ["", "background: jet_n x htmissScalar band (GeV):"]
    for j, row in b["crosstab_jets_x_scalar"].items():
        lines.append(f"  jets {('4+' if j == '4' else j):<3} " + "  ".join(f"{c}:{v:>7,}" for c, v in row.items()))
    txt = "\n".join(lines) + "\n"
    (out / "selection_check.txt").write_text(txt, encoding="utf-8")
    payload = {"source": "tools/selection_check.py", "written": time.strftime("%Y-%m-%d %H:%M"),
               "data_folder_name": data.name, "disjoint_in_htmiss": bool(disjoint),
               "bkg_htmiss_max": b["htmiss_max"], "sig_htmiss_min": sig_min, "met_cut_gev": MET_CUT_GEV,
               "samples": samples}
    (out / "selection_check.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(txt)
    log(f"wrote {out / 'selection_check.txt'} and selection_check.json")


if __name__ == "__main__":
    main()
