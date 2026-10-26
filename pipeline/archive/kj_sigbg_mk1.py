#!/usr/bin/env python
"""
kj_sigbg_mk1.py  --  signal/background separation pass on Prof. Johns' Sep-21-26 drop.

Per feature, per region (barrel / endcap / all):
  graph 1  each mass point vs background            (6 overlays)
  graph 2  combined MC vs background                 (pooled  AND  equal-weight-per-mass)
  graph 3  background alone
each drawn raw (log-y counts) and normalized (unit area).

Output (out_sigbg_r<N>/, N = --round, default 1)
  r<N>_SUMMARY.pdf               cover, then per region: ranking, top-40 table, top feature pages
  r<N>_<region>_all_features.pdf ranking, table, one page per feature in rank order
  ks_scores_long.csv / ks_scores_wide.csv, feature_inventory.txt, excluded_report.txt,
  region_audit.txt.  --png adds one PNG per feature; --no-plots skips the PDFs.

Score: two-sample KS statistic  D = sup_x |F_s(x) - F_b(x)|  (larger = more separation).
       p-values are NOT reported: at N ~ 1e3-1e4 they are ~0 for any real difference.

Feature pool
  * ALL7 only: columns present in background AND all six mass files. Signal-only columns
    are listed in excluded_report.txt and never scored -- their presence alone separates.
  * HARD_EXCLUDE patterns below (labels, NN outputs, weights, event ids, leakage vars).
  * exclude_features.txt next to this script: one name or glob per line, '#' comments.
  * NaN and -999 are removed per feature; their fractions are reported beside D.

Region
  * REGION_MODE = "auto": first a 0/1 column whose name contains "barrel"/"endcap",
    else a vertex |eta| column (BARREL_ETA_MAX / ENDCAP_ETA_RANGE). Choice and all
    candidates are written to region_audit.txt and printed. Override with REGION_COL.

Inventory (terminal + feature_inventory.txt, runs first; --inventory-only stops after it)
  features in each file; common to all 7; common grouped by name (endcap / barrel /
  region-agnostic); not-common features with a per-file presence matrix; exclude-file
  patterns that matched nothing. Excluded features are tagged in the common lists.

Read-only on the data. Real data only. Writes to OUT.
"""
import argparse
import fnmatch
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# =============================== CONFIG =====================================
DATA = Path(r"C:\Users\natha\OneDrive\Desktop\0_mL_ATLAS\0_Sig_BG_09_21_KJ\kj_092126\run3_csv_for_nathan")
HERE = Path(__file__).resolve().parent
OUT = HERE / "out_sigbg_r1"          # reset from --round in main()
EXCLUDE_FILE = HERE / "exclude_features.txt"
SUMMARY_TOP = 15                     # feature pages per region in the summary PDF

BKG_FILE = "DataHTMissLow_train_data24_cleaned.csv"
MASS_FILES = {                       # label -> file   (order = fixed color slot)
    "mH125_mS15":   "HSS_mH125_mS15_ct580_cleaned.csv",
    "mH125_mS55":   "HSS_mH125_mS55_ct5320_cleaned.csv",
    "mH200_mS50":   "HSS_mH200_mS50_ct1255_cleaned.csv",
    "mH400_mS100":  "HSS_mH400_mS100_ct1610_cleaned.csv",
    "mH600_mS150":  "HSS_mH600_mS150_ct3310_cleaned.csv",
    "mH1000_mS275": "HSS_mH1000_mS275_ct2399_cleaned.csv",
}

SENTINEL = -999.0
MIN_N = 20                           # fewer events than this in a cell -> D = NaN
N_BINS = 60
Q_LO, Q_HI = 0.005, 0.995            # binning range from pooled quantiles (edges carry overflow)

REGION_MODE = "auto"                 # "auto" | "flag" | "eta" | "none"
REGION_COL = None                    # e.g. "MS1Vtx_eta"; set to force a column
BARREL_ETA_MAX = 0.8                 # |eta| <  0.8  -> barrel   (confirm with KJ)
ENDCAP_ETA_RANGE = (1.3, 2.5)        # 1.3 <= |eta| < 2.5 -> endcap

HARD_EXCLUDE = [                     # regex, case-insensitive, matched against full name
    r".*score_?nn.*", r".*nn\d?e?_cut.*", r"is_signal", r"sample_label", r"label",
    r"bdt_target", r"ms_gev", r"mh_gev", r".*eventweight.*", r".*weight.*",
    r"runnumber", r"eventnumber", r"mcchannelnumber", r"lumiblock.*",
    r"htmiss_nosys", r"met_met_nosys", r".*_sf_.*", r".*effsf.*",
]

# fixed categorical slots (reference palette, light mode); color follows the mass point
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BKG_FILL, BKG_EDGE = "#c9c8c2", "#55544f"
INK, INK2, GRID = "#1f1f1d", "#6b6a64", "#e6e5df"
# ===========================================================================

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def bar(i, n, label="", width=28):
    f = i / max(n, 1)
    sys.stdout.write(f"\r  [{'#' * int(f * width):<{width}}] {i}/{n}  {label[:40]:<40}")
    sys.stdout.flush()
    if i >= n:
        sys.stdout.write("\n")


# ---------------------------------------------------------------- loading
def load():
    log(f"data dir: {DATA}")
    if not DATA.exists():
        sys.exit(f"DATA folder not found: {DATA}")
    files = {"bkg": BKG_FILE, **MASS_FILES}
    dfs = {}
    for i, (k, f) in enumerate(files.items(), 1):
        p = DATA / f
        log(f"[{i}/{len(files)}] {k:<13} {f} ({p.stat().st_size / 1e6:.1f} MB)")
        df = pd.read_csv(p, low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        dfs[k] = df
        log(f"      rows {len(df):,}  cols {df.shape[1]}")
    return dfs


def read_exclude_file():
    if not EXCLUDE_FILE.exists():
        EXCLUDE_FILE.write_text("# one feature name or glob per line; '#' starts a comment\n", encoding="utf-8")
        log(f"created empty {EXCLUDE_FILE.name}")
        return []
    pats = []
    for line in EXCLUDE_FILE.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip()
        if s:
            pats.append(s)
    log(f"{EXCLUDE_FILE.name}: {len(pats)} pattern(s)")
    return pats


def feature_pool(dfs, user_pats):
    sets = {k: set(v.columns) for k, v in dfs.items()}
    all7 = set.intersection(*sets.values())
    union = set.union(*sets.values())
    report = {"not_ALL7": sorted(union - all7), "hard": [], "user": [], "non_numeric": [], "constant": []}
    hard_rx = [re.compile(p, re.I) for p in HARD_EXCLUDE]
    keep = []
    for c in sorted(all7):
        if any(r.fullmatch(c) for r in hard_rx):
            report["hard"].append(c); continue
        if any(fnmatch.fnmatchcase(c, p) or c == p for p in user_pats):
            report["user"].append(c); continue
        if not all(pd.api.types.is_numeric_dtype(dfs[k][c]) or pd.api.types.is_bool_dtype(dfs[k][c]) for k in dfs):
            report["non_numeric"].append(c); continue
        vals = pd.concat([pd.to_numeric(dfs[k][c], errors="coerce") for k in dfs])
        vals = vals[(vals != SENTINEL) & vals.notna()]
        if vals.nunique() <= 1:
            report["constant"].append(c); continue
        keep.append(c)
    return keep, report, sorted(all7)


# ---------------------------------------------------------------- inventory
def name_group(c):
    b, e = bool(re.search(r"barrel", c, re.I)), bool(re.search(r"endcap", c, re.I))
    return "barrel+endcap" if b and e else "barrel" if b else "endcap" if e else "region-agnostic"


def inventory(dfs, rep, user_pats):
    """Terminal + feature_inventory.txt: per-file features, common set, name-grouped common set,
    non-common features with a presence matrix, and exclude-file patterns that matched nothing."""
    files = list(dfs)
    sets = {k: set(v.columns) for k, v in dfs.items()}
    all7 = set.intersection(*sets.values())
    union = set.union(*sets.values())
    hard, user = set(rep["hard"]), set(rep["user"])
    L = []

    def tag(c):
        return "  [hard-excluded]" if c in hard else "  [user-excluded]" if c in user else ""

    def block(title, names, mark=True):
        L.append("")
        L.append("=" * 78)
        L.append(f"{title}  ({len(names)})")
        L.append("=" * 78)
        for i, c in enumerate(sorted(names), 1):
            L.append(f"  {i:4d}  {c}{tag(c) if mark else ''}")

    # 1. features in each file
    for k in files:
        block(f"FEATURES IN FILE: {k}", sets[k], mark=False)

    # 2. common to all files
    block("COMMON TO ALL 7 FILES", all7)

    # 3./4. common, grouped by name
    groups = {}
    for c in all7:
        groups.setdefault(name_group(c), []).append(c)
    for g in ("endcap", "barrel", "barrel+endcap", "region-agnostic"):
        block(f"COMMON TO ALL 7 FILES  --  name contains '{g}'" if g != "region-agnostic"
              else "COMMON TO ALL 7 FILES  --  region-agnostic name (neither 'barrel' nor 'endcap')",
              groups.get(g, []))

    # 5. not common: presence matrix
    nc = sorted(union - all7)
    L.append("")
    L.append("=" * 78)
    L.append(f"NOT COMMON  ({len(nc)})   x = present, . = absent")
    L.append("=" * 78)
    short = {"bkg": "BKG"} | {m: m.replace("mH", "").replace("_mS", "/") for m in MASS_FILES}
    hdr = "  " + " ".join(f"{short[k]:>8}" for k in files) + "   feature"
    L.append(hdr)
    by_pattern = {}
    for c in nc:
        row = "".join("x" if c in sets[k] else "." for k in files)
        by_pattern.setdefault(row, []).append(c)
        L.append("  " + " ".join(f"{('x' if c in sets[k] else '.'):>8}" for k in files) + f"   {c}")
    L.append("")
    L.append("  presence-pattern summary (order: " + ", ".join(short[k] for k in files) + ")")
    for pat, cols in sorted(by_pattern.items(), key=lambda t: -len(t[1])):
        where = "BKG only" if pat == "x" + "." * (len(files) - 1) else \
                "signal only, all 6" if pat == "." + "x" * (len(files) - 1) else \
                f"BKG {'yes' if pat[0] == 'x' else 'no'}, signal {pat[1:].count('x')}/6"
        L.append(f"    {pat}  {len(cols):4d}  {where}")

    # 6. exclude-file patterns that matched nothing
    dead = [p for p in user_pats if not any(fnmatch.fnmatchcase(c, p) or c == p for c in union)]
    L.append("")
    L.append("=" * 78)
    L.append(f"{EXCLUDE_FILE.name}: {len(user_pats)} pattern(s), {len(user)} common feature(s) excluded, "
             f"{len(dead)} pattern(s) matched NO column")
    L.append("=" * 78)
    for p in dead:
        L.append(f"  no match: {p}")

    text = "\n".join(L)
    print(text, flush=True)
    (OUT / "feature_inventory.txt").write_text(text + "\n", encoding="utf-8")
    log("wrote feature_inventory.txt")


# ---------------------------------------------------------------- region
def find_region(all7, dfs):
    lines, chosen = [], None
    flags = [c for c in all7 if re.search(r"barrel|endcap|isbarrel|region", c, re.I)]
    etas = [c for c in all7 if re.search(r"eta", c, re.I) and re.search(r"vtx|vertex|msv", c, re.I)]
    lines.append("flag-like candidates:\n  " + ("\n  ".join(flags) or "(none)"))
    lines.append("vertex-eta candidates:\n  " + ("\n  ".join(etas) or "(none)"))

    def is01(c):
        v = pd.concat([pd.to_numeric(dfs[k][c], errors="coerce") for k in dfs]).dropna()
        return len(v) > 0 and set(np.unique(v)).issubset({0, 1})

    mode = REGION_MODE
    if REGION_COL:
        chosen = (REGION_COL, "flag" if is01(REGION_COL) else "eta", None)
    elif mode in ("auto", "flag"):
        for c in flags:
            if is01(c) and re.search(r"barrel", c, re.I):
                ec = next((x for x in flags if is01(x) and re.search(r"endcap", x, re.I)), None)
                chosen = (c, "flag", ec); break
    if chosen is None and mode in ("auto", "eta") and etas:
        chosen = (etas[0], "eta", None)
    if mode == "none":
        chosen = None
    lines.append(f"CHOSEN: {chosen}")
    if chosen and chosen[1] == "flag":
        lines.append(f"barrel = {chosen[0]} == 1;  endcap = "
                     + (f"{chosen[2]} == 1" if chosen[2] else f"{chosen[0]} == 0 (no endcap flag found)"))
        for k, df in dfs.items():
            b = pd.to_numeric(df[chosen[0]], errors="coerce").to_numpy() == 1
            e = (pd.to_numeric(df[chosen[2]], errors="coerce").to_numpy() == 1) if chosen[2] else ~b
            lines.append(f"  {k:<13} n {len(df):>7,}  barrel {b.sum():>7,}  endcap {e.sum():>7,}  "
                         f"both {(b & e).sum():>5,}  neither {(~b & ~e).sum():>6,}")
    if chosen and chosen[1] == "eta":
        lines.append(f"barrel |eta| < {BARREL_ETA_MAX}; endcap {ENDCAP_ETA_RANGE[0]} <= |eta| < {ENDCAP_ETA_RANGE[1]}")
    return chosen, "\n\n".join(lines)


def region_masks(df, chosen):
    n = len(df)
    allm = np.ones(n, bool)
    if chosen is None:
        return {"all": allm}
    col, kind, ecol = chosen
    v = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
    if kind == "flag":
        b = v == 1
        e = (pd.to_numeric(df[ecol], errors="coerce").to_numpy(float) == 1) if ecol else (v == 0)
    else:
        a = np.abs(v)
        ok = np.isfinite(v) & (v != SENTINEL)
        b = ok & (a < BARREL_ETA_MAX)
        e = ok & (a >= ENDCAP_ETA_RANGE[0]) & (a < ENDCAP_ETA_RANGE[1])
    return {"barrel": b, "endcap": e, "all": allm}


# ---------------------------------------------------------------- stats
def clean(x):
    x = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(float)
    n = len(x)
    nan = ~np.isfinite(x)
    sen = x == SENTINEL
    good = ~(nan | sen)
    return x[good], (nan.sum() / n if n else np.nan), (sen.sum() / n if n else np.nan)


def ks_w(a, wa, b, wb):
    """Weighted two-sample KS statistic. Ties handled by evaluating at the last of each run."""
    if len(a) < MIN_N or len(b) < MIN_N:
        return np.nan
    x = np.concatenate([a, b])
    ua = np.concatenate([wa / wa.sum(), np.zeros(len(b))])
    ub = np.concatenate([np.zeros(len(a)), wb / wb.sum()])
    o = np.argsort(x, kind="mergesort")
    x, ca, cb = x[o], np.cumsum(ua[o]), np.cumsum(ub[o])
    last = np.r_[x[1:] != x[:-1], True]
    return float(np.max(np.abs(ca[last] - cb[last])))


def edges_for(vals):
    v = np.concatenate([x for x in vals if len(x)])
    if len(v) == 0:
        return None
    u = np.unique(v)
    if len(u) <= 40 and np.allclose(u, np.round(u)):
        return np.arange(u.min() - 0.5, u.max() + 1.5, 1.0)
    lo, hi = np.quantile(v, [Q_LO, Q_HI])
    if hi <= lo:
        lo, hi = v.min(), v.max()
    if hi <= lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, N_BINS + 1)


def hist(x, e, w=None):
    xc = np.clip(x, e[0], e[-1] - 1e-12 * max(1.0, abs(e[-1])))
    h, _ = np.histogram(xc, bins=e, weights=w)
    return h


# ---------------------------------------------------------------- plotting
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def feature_fig(feat, region, e, bkg, masses, comb, comb_w, scores, rank, n_rank, rnd):
    plt = _plt()
    fig, ax = plt.subplots(3, 2, figsize=(11, 8.5), constrained_layout=True)   # US letter landscape
    ctr = 0.5 * (e[:-1] + e[1:])
    nb = len(bkg)

    def style(a, title, ylab, log=False):
        a.set_title(title, fontsize=10, color=INK, loc="left")
        a.set_ylabel(ylab, fontsize=9, color=INK2)
        a.tick_params(labelsize=8, colors=INK2)
        a.grid(True, color=GRID, lw=0.8)
        a.set_axisbelow(True)
        for s in a.spines.values():
            s.set_color(GRID)
        if log:
            a.set_yscale("log")

    def bkg_fill(a, norm):
        h = hist(bkg, e)
        y = h / (h.sum() * np.diff(e)) if norm else h
        a.fill_between(ctr, y, step="mid", color=BKG_FILL, lw=0, label=f"background (n={nb:,})")
        a.step(ctr, y, where="mid", color=BKG_EDGE, lw=1)

    for col, norm in ((0, False), (1, True)):
        ylab = "density" if norm else "events"
        # graph 1
        a = ax[0, col]
        bkg_fill(a, norm)
        for i, (m, x) in enumerate(masses.items()):
            if len(x) == 0:
                continue
            h = hist(x, e)
            y = h / (h.sum() * np.diff(e)) if norm else h
            d = scores.get(m, np.nan)
            a.step(ctr, y, where="mid", color=SLOT[i], lw=2, label=f"{m}  D={d:.3f}  (n={len(x):,})")
        style(a, f"1 · each mass point vs background · {'normalized' if norm else 'raw'}", ylab, log=not norm)
        a.legend(fontsize=7, frameon=False, labelcolor=INK)
        # graph 2
        a = ax[1, col]
        bkg_fill(a, norm)
        if len(comb):
            h = hist(comb, e)
            y = h / (h.sum() * np.diff(e)) if norm else h
            a.step(ctr, y, where="mid", color=SLOT[6], lw=2,
                   label=f"combined, pooled  D={scores.get('comb_pooled', np.nan):.3f}  (n={len(comb):,})")
            hw = hist(comb, e, comb_w)
            if norm:
                yw = hw / (hw.sum() * np.diff(e))
            else:
                yw = hw * (len(comb) / hw.sum())     # same total as pooled, shape from equal weighting
            a.step(ctr, yw, where="mid", color=SLOT[7], lw=2, ls="--",
                   label=f"combined, equal-weight/mass  D={scores.get('comb_equal', np.nan):.3f}")
        style(a, f"2 · combined MC vs background · {'normalized' if norm else 'raw'}", ylab, log=not norm)
        a.legend(fontsize=7, frameon=False, labelcolor=INK)
        # graph 3
        a = ax[2, col]
        bkg_fill(a, norm)
        fr = scores.get("bkg_fill", (np.nan, np.nan))
        style(a, f"3 · background alone · {'normalized' if norm else 'raw'} · NaN {fr[0]:.1%}  −999 {fr[1]:.1%}",
              ylab, log=not norm)
        a.set_xlabel(feat, fontsize=9, color=INK2)

    fig.suptitle(f"{feat}   ·   region: {region}   ·   rank {rank}/{n_rank} by combined equal-weight D"
                 f"   ·   round {rnd}   ·   edge bins include under/overflow",
                 fontsize=10, color=INK, x=0.01, ha="left")
    return fig


def text_page(title, lines, rnd, mono=True, size=7.5):
    plt = _plt()
    fig = plt.figure(figsize=(11, 8.5))
    fig.text(0.04, 0.95, title, fontsize=14, color=INK, va="top")
    fig.text(0.04, 0.905, "\n".join(lines), fontsize=size, color=INK, va="top",
             family="monospace" if mono else None, linespacing=1.35)
    fig.text(0.96, 0.02, f"kj_sigbg_mk1 · round {rnd}", fontsize=7, color=INK2, ha="right")
    return fig


def rank_order(df):
    """Single deterministic ranking: D_comb_equal descending, NaN last, ties broken by name."""
    d = df.assign(_k=df["D_comb_equal"].fillna(-1.0))
    return d.sort_values(["_k", "feature"], ascending=[False, True], kind="mergesort")["feature"].tolist()


def table_lines(df, top=40):
    d = df.set_index("feature").loc[rank_order(df)].reset_index().head(top)
    w = max([len("feature")] + [len(f) for f in d["feature"]])
    hdr = f"{'#':>3}  {'feature':<{w}}  {'D_equal':>7}  {'D_pooled':>8}  {'D_min':>6}  {'D_max':>6}  " \
          f"{'bkgNaN':>6}  {'bkg-999':>7}"
    out = [hdr, "-" * len(hdr)]
    for i, r in enumerate(d.itertuples(index=False), 1):
        out.append(f"{i:>3}  {r.feature:<{w}}  {r.D_comb_equal:7.3f}  {r.D_comb_pooled:8.3f}  "
                   f"{r.D_mass_min:6.3f}  {r.D_mass_max:6.3f}  {r.bkg_nan_frac:6.1%}  {r.bkg_m999_frac:7.1%}")
    return out


def ranking_fig(df, region, top=40):
    plt = _plt()
    d = df.set_index("feature").loc[rank_order(df)].reset_index().head(top)
    if d.empty:
        return None
    fig, a = plt.subplots(figsize=(11, 8.5), constrained_layout=True)
    a.barh(d["feature"][::-1], d["D_comb_equal"][::-1], color=SLOT[0], height=0.7)
    for y, v in enumerate(d["D_comb_equal"][::-1]):
        a.text(v + 0.005, y, f"{v:.3f}", va="center", fontsize=7, color=INK2)
    a.set_xlabel("KS D, combined MC (equal weight per mass) vs background", fontsize=9, color=INK2)
    a.set_title(f"Top {len(d)} features by separation · {region}", fontsize=10, color=INK, loc="left")
    a.tick_params(labelsize=7, colors=INK2)
    a.grid(True, axis="x", color=GRID)
    a.set_axisbelow(True)
    for s in a.spines.values():
        s.set_color(GRID)
    return fig


# ---------------------------------------------------------------- main
def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=1, help="round number; output goes to out_sigbg_r<N>")
    ap.add_argument("--regions", default="barrel,endcap,all")
    ap.add_argument("--inventory-only", action="store_true",
                    help="print/write the feature inventory and exclusion report, then stop")
    ap.add_argument("--no-plots", action="store_true", help="scores, inventory and text only; no PDFs")
    ap.add_argument("--png", action="store_true", help="also write one PNG per feature per region")
    ap.add_argument("--summary-only", action="store_true",
                    help="score + write r<N>_SUMMARY.pdf only; skip the per-region all-features PDFs")
    args = ap.parse_args()
    R = args.round
    OUT = HERE / f"out_sigbg_r{R}"
    OUT.mkdir(exist_ok=True)
    log(f"round {R} -> {OUT}")

    dfs = load()
    pats = read_exclude_file()
    feats, rep, all7 = feature_pool(dfs, pats)
    log(f"ALL7 columns {len(all7)} | scored features {len(feats)} | hard-excluded {len(rep['hard'])} | "
        f"user-excluded {len(rep['user'])} | non-numeric {len(rep['non_numeric'])} | constant {len(rep['constant'])} | "
        f"not-ALL7 {len(rep['not_ALL7'])}")
    with open(OUT / "excluded_report.txt", "w", encoding="utf-8") as fh:
        for k, v in rep.items():
            fh.write(f"===== {k} ({len(v)}) =====\n" + "\n".join(v) + "\n\n")
    inventory(dfs, rep, pats)
    if args.inventory_only:
        log(f"--inventory-only: stopping after inventory -> {OUT}")
        return

    chosen, audit = find_region(all7, dfs)
    (OUT / "region_audit.txt").write_text(audit, encoding="utf-8")
    log(f"region: {chosen}")
    masks = {k: region_masks(df, chosen) for k, df in dfs.items()}
    regions = [r for r in args.regions.split(",") if r in masks["bkg"]]
    if chosen is None:
        log("WARNING: no region column found -> 'all' only. See region_audit.txt and set REGION_COL.")
    count_lines = []
    for r in regions:
        ln = f"  {r:<7} bkg {masks['bkg'][r].sum():>7,}  " + \
             "  ".join(f"{m} {masks[m][r].sum():,}" for m in MASS_FILES)
        count_lines.append(ln)
        log(ln)

    from matplotlib.backends.backend_pdf import PdfPages
    plt = _plt()
    long_rows, wide_rows, top_cache = [], [], {}
    for r in regions:
        log(f"region {r}: scoring {len(feats)} features")
        cache = {}
        for i, f in enumerate(feats, 1):
            b, bnan, bsen = clean(dfs["bkg"].loc[masks["bkg"][r], f])
            ms, fills = {}, {}
            for m in MASS_FILES:
                x, n_, s_ = clean(dfs[m].loc[masks[m][r], f])
                ms[m], fills[m] = x, (n_, s_)
            comb = np.concatenate(list(ms.values()))
            cw = np.concatenate([np.full(len(x), 1.0 / len(x)) if len(x) else np.empty(0) for x in ms.values()])
            sc = {"bkg_fill": (bnan, bsen)}
            ones_b = np.ones(len(b))
            for m, x in ms.items():
                sc[m] = ks_w(x, np.ones(len(x)), b, ones_b)
                long_rows.append({"round": R, "region": r, "feature": f, "comparison": m, "D": sc[m],
                                  "n_sig": len(x), "n_bkg": len(b), "sig_nan_frac": fills[m][0],
                                  "sig_m999_frac": fills[m][1], "bkg_nan_frac": bnan, "bkg_m999_frac": bsen})
            sc["comb_pooled"] = ks_w(comb, np.ones(len(comb)), b, ones_b)
            sc["comb_equal"] = ks_w(comb, cw, b, ones_b) if len(comb) else np.nan
            for k in ("comb_pooled", "comb_equal"):
                long_rows.append({"round": R, "region": r, "feature": f, "comparison": k, "D": sc[k],
                                  "n_sig": len(comb), "n_bkg": len(b), "sig_nan_frac": np.nan,
                                  "sig_m999_frac": np.nan, "bkg_nan_frac": bnan, "bkg_m999_frac": bsen})
            md = [sc[m] for m in MASS_FILES]
            wide_rows.append({"round": R, "region": r, "feature": f, **{f"D_{m}": sc[m] for m in MASS_FILES},
                              "D_comb_pooled": sc["comb_pooled"], "D_comb_equal": sc["comb_equal"],
                              "D_mass_min": np.nanmin(md) if np.isfinite(md).any() else np.nan,
                              "D_mass_max": np.nanmax(md) if np.isfinite(md).any() else np.nan,
                              "bkg_nan_frac": bnan, "bkg_m999_frac": bsen, "n_bkg": len(b)})
            cache[f] = (b, ms, comb, cw, sc)
            bar(i, len(feats), f)

        wide_r = pd.DataFrame([w for w in wide_rows if w["region"] == r])
        if not args.no_plots and not wide_r.empty:
            order = rank_order(wide_r)
            top_cache[r] = (order, {f: cache[f] for f in order[:SUMMARY_TOP]})
            if args.summary_only:
                del cache
                continue
            pdf_path = OUT / f"r{R}_{r}_all_features.pdf"
            pdir = OUT / "png" / r
            if args.png:
                pdir.mkdir(parents=True, exist_ok=True)
            log(f"region {r}: writing {len(order)} feature pages -> {pdf_path.name}")
            with PdfPages(pdf_path) as pdf:
                fig = ranking_fig(wide_r, r)
                if fig is not None:
                    pdf.savefig(fig); plt.close(fig)
                fig = text_page(f"Round {R} · {r} · top 40 by combined equal-weight KS D",
                                table_lines(wide_r), R)
                pdf.savefig(fig); plt.close(fig)
                for rank, f in enumerate(order, 1):
                    b, ms, comb, cw, sc = cache[f]
                    e = edges_for([b, comb])
                    if e is not None:
                        fig = feature_fig(f, r, e, b, ms, comb, cw, sc, rank, len(order), R)
                        pdf.savefig(fig)
                        if args.png:
                            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f)
                            fig.savefig(pdir / f"{rank:03d}_{safe}.png", dpi=110)
                        plt.close(fig)
                    bar(rank, len(order), f)
                d = pdf.infodict()
                d["Title"] = f"kj_sigbg_mk1 round {R} - {r} - all features"
        del cache

    pd.DataFrame(long_rows).to_csv(OUT / "ks_scores_long.csv", index=False)
    wide = pd.DataFrame(wide_rows).sort_values(["region", "D_comb_equal"], ascending=[True, False])
    wide.to_csv(OUT / "ks_scores_wide.csv", index=False)
    log("wrote ks_scores_long.csv (one row per feature x region x comparison), ks_scores_wide.csv")

    if not args.no_plots:
        spath = OUT / f"r{R}_SUMMARY.pdf"
        log(f"writing summary -> {spath.name}")
        cover = [
            f"date        {time.strftime('%Y-%m-%d %H:%M')}",
            f"data        {DATA}",
            f"background  {BKG_FILE}  rows {len(dfs['bkg']):,}",
            *[f"signal      {f}  rows {len(dfs[m]):,}" for m, f in MASS_FILES.items()],
            "",
            f"columns common to all 7 files (ALL7)   {len(all7)}",
            f"features scored                        {len(feats)}",
            f"hard-excluded                          {len(rep['hard'])}",
            f"user-excluded ({EXCLUDE_FILE.name})   {len(rep['user'])}",
            f"non-numeric / constant                 {len(rep['non_numeric'])} / {len(rep['constant'])}",
            f"not common to all 7 (never scored)     {len(rep['not_ALL7'])}",
            "",
            f"region column   {chosen}",
            *(f"                barrel |eta| < {BARREL_ETA_MAX}; endcap {ENDCAP_ETA_RANGE[0]} <= |eta| < "
              f"{ENDCAP_ETA_RANGE[1]}" for _ in [0] if chosen and chosen[1] == "eta"),
            "events per region (after region selection):",
            *count_lines,
            "",
            "metric   two-sample KS D = sup|F_s - F_b|, unweighted events; NaN and -999 removed per feature.",
            "         'equal' weights each mass point 1/N_m so small points count as much as large ones.",
            "         p-values not reported (N ~ 1e3-1e4 makes them ~0 for any real difference).",
            "",
            f"this summary: per region -> ranking, top-40 table, top {SUMMARY_TOP} feature pages.",
            f"all features: r{R}_<region>_all_features.pdf",
        ]
        with PdfPages(spath) as pdf:
            fig = text_page(f"Signal/background separation · round {R}", cover, R, size=8.5)
            pdf.savefig(fig); plt.close(fig)
            for r in regions:
                wide_r = wide[wide.region == r]
                fig = ranking_fig(wide_r, r)
                if fig is not None:
                    pdf.savefig(fig); plt.close(fig)
                fig = text_page(f"Round {R} · {r} · top 40 by combined equal-weight KS D", table_lines(wide_r), R)
                pdf.savefig(fig); plt.close(fig)
                order, cached = top_cache[r]
                for rank, f in enumerate(order[:SUMMARY_TOP], 1):
                    b, ms, comb, cw, sc = cached[f]
                    e = edges_for([b, comb])
                    if e is not None:
                        fig = feature_fig(f, r, e, b, ms, comb, cw, sc, rank, len(order), R)
                        pdf.savefig(fig); plt.close(fig)
            pdf.infodict()["Title"] = f"kj_sigbg_mk1 round {R} - summary"

    for r in regions:
        top = wide[wide.region == r].head(10)
        log(f"top 10 [{r}] by D_comb_equal:\n" +
            top[["feature", "D_comb_equal", "D_mass_min", "D_mass_max"]].to_string(index=False))
    log(f"DONE -> {OUT}")


if __name__ == "__main__":
    main()
