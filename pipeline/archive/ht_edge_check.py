#!/usr/bin/env python
"""
ht_edge_check.py -- find the HT(miss) preselection edge in the signal files and
how much background survives it.  Read-only.  Reads 4 columns per file.

Usage:  python ht_edge_check.py
"""
import os
import numpy as np
import pandas as pd

D = r"C:\Users\natha\OneDrive\Desktop\0_mL_ATLAS\0_Sig_BG_09_21_KJ\kj_092126\run3_csv_for_nathan"
FILES = [
    "DataHTMissLow_train_data24_cleaned.csv",
    "HSS_mH125_mS15_ct580_cleaned.csv",
    "HSS_mH125_mS55_ct5320_cleaned.csv",
    "HSS_mH200_mS50_ct1255_cleaned.csv",
    "HSS_mH400_mS100_ct1610_cleaned.csv",
    "HSS_mH600_mS150_ct3310_cleaned.csv",
    "HSS_mH1000_mS275_ct2399_cleaned.csv",
]
VARS = ["htmissScalar_NOSYS", "htmiss_NOSYS", "jet_pt_max_NOSYS"]
COLS = VARS + ["msvtx_inBarrel_NOSYS"]


def main():
    print(f"{'file':40s} {'var':20s} {'min':>9s} {'q0.1%':>9s} {'q1%':>9s} {'median':>9s}   [GeV]")
    bkg = None
    for i, f in enumerate(FILES):
        print(f"  [{i + 1}/{len(FILES)}] reading {f}", flush=True)
        x = pd.read_csv(os.path.join(D, f), usecols=COLS)
        for c in VARS:
            v = x[c].replace(-999, np.nan).dropna() / 1e3
            print(f"{f[:40]:40s} {c:20s} {v.min():9.2f} {v.quantile(.001):9.2f} "
                  f"{v.quantile(.01):9.2f} {v.median():9.2f}")
        if i == 0:
            bkg = x
    print()
    b = bkg["msvtx_inBarrel_NOSYS"] == 1
    for thr in [30, 35, 40, 45, 50]:
        m = bkg["htmissScalar_NOSYS"] / 1e3 >= thr
        j0 = bkg["jet_pt_max_NOSYS"] <= 0
        print(f"bkg surviving htmissScalar >= {thr} GeV:  "
              f"barrel {(m & b).sum():6d} of {b.sum()}   "
              f"endcap {(m & ~b).sum():6d} of {(~b).sum()}   "
              f"jet_pt_max<=0 left {(m & j0).sum()} (of {j0.sum()})")


if __name__ == "__main__":
    main()
