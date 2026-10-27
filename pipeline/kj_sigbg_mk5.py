#!/usr/bin/env python
"""
kj_sigbg_mk5.py  --  feature study on Prof. Johns' Sep-21-26 drop, in four analysis blocks.
                     mk5 = mk4 analysis unchanged; plot layout changed: every legend sits in its own
                     column beside its row of panels (never on top of the data), and every panel title
                     carries a panel code (1a, 1b, 2a ...) that the site's page map uses.
                     Front end for GAMBIT (Data Gate + block reduction + starting partitions);
                     the unit tests are the data-health gate BASELINE will reuse.

00_common            unit test (HTmiss split by design), inventory, duplicates, exclusions, region audit
A_barrel_vs_endcap   per feature: D in each region, difference, ranks, "separates in" flag, and the
                     barrel-vs-endcap SHAPE of background and of signal.  PDF per feature: shape page +
                     side-by-side separation page.
B_mc_vs_data         per feature and region: each MC mass point vs data, combined MC vs data, data alone
                     (raw | normalized), KS D with noise floor; NN-list table; strong-but-unused list.
C_correlation        background Spearman matrix per region, redundancy blocks (|rho| >= 0.9 with every
                     member), NN1-NN2 cross-correlation of the current lists.
D_prototypes         P0 mk4 as is | P1 minus weak/dead/redundant | P2 P1 + strong unused non-HTmiss features
                     | P3 inclusive P1 (both regions, region flag).  Gradient-boosted surrogate, 5-fold CV:
                     AUC per role (equal weight per mass), worst-mass AUC, dCor/Spearman NN1-NN2 on background.
                     The surrogate nominates; GAMBIT decides (closure and G).
gambit_inputs        unit_tests.json, pool_<region>.txt, blocks.json, drop_suggestions.txt, prototypes/P*.txt

KS D = sup|F_s - F_b| in [0,1] = best single-cut (signal eff - background eff).
Noise floor D_crit = 1.36 sqrt(1/n_s + 1/n_b).  Real data only.  Read-only on the data.
Usage: python kj_sigbg_mk5.py [--data FOLDER] [--block ABCD] [--no-plots] [--top N] [--png] [--round N]
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
SCRIPT_TAG = "kj_sigbg_mk5"
HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.txt"     # copy config_example.txt -> config.txt and set DATA = <your folder>
DATA = None                           # resolved in main(): --data, then config.txt, then $KJ_SIGBG_DATA


def resolve_data(cli_value=None):
    """Data folder, first hit wins: --data, config.txt 'DATA = ...', environment KJ_SIGBG_DATA."""
    import os
    if cli_value:
        return Path(cli_value).expanduser(), "--data"
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            s = line.split("#", 1)[0].strip()
            if s.upper().startswith("DATA") and "=" in s:
                return Path(s.split("=", 1)[1].strip().strip('"').strip("'")).expanduser(), "config.txt"
    if os.environ.get("KJ_SIGBG_DATA"):
        return Path(os.environ["KJ_SIGBG_DATA"]).expanduser(), "environment KJ_SIGBG_DATA"
    sys.exit("No data folder set. Copy config_example.txt to config.txt and set DATA = <folder with the 7 CSVs>,\n"
             "or run with --data <folder>, or set the environment variable KJ_SIGBG_DATA.")
OUT = HERE / "out_sigbg_mk5_r1"      # reset from --round in main()
EXCLUDE_FILE = HERE / "exclude_features.txt"
NN_FEATURES_FILE = HERE / "nn_features_mk4.txt"

BKG_FILE = "DataHTMissLow_train_data24_cleaned.csv"
MASS_FILES = {                       # label -> file   (order = fixed color slot)
    "mH125_mS15":   "HSS_mH125_mS15_ct580_cleaned.csv",
    "mH125_mS55":   "HSS_mH125_mS55_ct5320_cleaned.csv",
    "mH200_mS50":   "HSS_mH200_mS50_ct1255_cleaned.csv",
    "mH400_mS100":  "HSS_mH400_mS100_ct1610_cleaned.csv",
    "mH600_mS150":  "HSS_mH600_mS150_ct3310_cleaned.csv",
    "mH1000_mS275": "HSS_mH1000_mS275_ct2399_cleaned.csv",
}

HT_TEST_VAR = "htmiss_NOSYS"         # unit test: bkg < HT_TEST_GEV, signal >= HT_TEST_GEV
HT_TEST_GEV = 40.0
RANK_BY = "endcap"                   # region whose combined equal-weight D numbers the folders
STRONG_TOP = 15                      # "strong but unused" list length per region

SENTINEL = -999.0
MIN_N = 20
N_BINS = 60
Q_LO, Q_HI = 0.005, 0.995

REGION_MODE = "auto"
REGION_COL = None
BARREL_ETA_MAX = 0.8
ENDCAP_ETA_RANGE = (1.3, 2.5)

HARD_EXCLUDE = [                     # regex, case-insensitive, matched against full name
    r".*score_?nn.*", r".*nn\d?e?_cut.*", r"is_signal", r"sample_label", r"label",
    r"bdt_target", r"ms_gev", r"mh_gev", r".*eventweight.*", r".*weight.*",
    r"runnumber", r"eventnumber", r"mcchannelnumber", r"lumiblock.*",
    r"htmiss_nosys", r"met_met_nosys", r".*_sf_.*", r".*effsf.*",
    r"msvtx_inbarrel_nosys", r"msvtx_inendcaps_nosys",          # region selectors
]

SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BKG_FILL, BKG_EDGE = "#c9c8c2", "#55544f"
INK, INK2, GRID = "#1f1f1d", "#6b6a64", "#e6e5df"
BAND = {"endcap": "#cde2fb", "barrel": "#f9d8c8", "all": "#e6e5df", "overview": "#e6e5df"}
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
    vals = [x for x in vals if len(x)]
    if not vals:
        return None
    v = np.concatenate(vals)
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



# ---------------------------------------------------------------- duplicates
def dedup(num, feats):
    """Collapse columns that are rank-identical: same missing pattern (NaN/-999) in every file and
    the same ordering of valid values across all files (equal up to a monotone transform).
    Such columns give the same KS D in every region and selection."""
    order = list(num)
    finger = {}
    for f in feats:
        x = np.concatenate([num[k][f] for k in order])
        valid = np.isfinite(x) & (x != SENTINEL)
        r = np.unique(x[valid], return_inverse=True)[1] if valid.any() else np.empty(0, int)
        r = np.minimum(r, r.max() - r) if r.size else r          # also catches decreasing transforms
        finger[f] = (valid, r)
    buckets = {}
    for f in feats:
        v, r = finger[f]
        buckets.setdefault(hash(v.tobytes()) ^ hash(r.astype(np.int64).tobytes()), []).append(f)
    groups = []
    for fs in buckets.values():
        while fs:
            head, rest = fs[0], fs[1:]
            same = [g for g in rest if np.array_equal(finger[head][0], finger[g][0])
                    and np.array_equal(finger[head][1], finger[g][1])]
            groups.append([head] + same)
            fs = [g for g in rest if g not in same]

    def pref(name):  # keep: no region tag (content is region-agnostic), then no _raw, shortest, alphabetical
        return (bool(re.search(r"barrel|endcap", name, re.I)), "_raw" in name, len(name), name)

    keep, copies = [], {}
    for g in groups:
        g = sorted(g, key=pref)
        keep.append(g[0])
        if len(g) > 1:
            copies[g[0]] = g[1:]
    return sorted(keep), copies


# ---------------------------------------------------------------- scoring
def score_cell(b, ms):
    """KS scores for one (feature, region, selection) cell. Returns dict, or None if constant."""
    comb = np.concatenate(list(ms.values()))
    pooled = np.concatenate([b, comb])
    if len(pooled) == 0 or np.unique(pooled).size <= 1:
        return None
    cw = np.concatenate([np.full(len(x), 1.0 / len(x)) for x in ms.values() if len(x)]) \
        if len(comb) else np.empty(0)
    ob = np.ones(len(b))
    sc = {m: ks_w(x, np.ones(len(x)), b, ob) for m, x in ms.items()}
    sc["comb_pooled"] = ks_w(comb, np.ones(len(comb)), b, ob)
    sc["comb_equal"] = ks_w(comb, cw, b, ob) if len(comb) else np.nan
    return sc


def rank_order(df):
    d = df.assign(_k=df["D_comb_equal"].fillna(-1.0))
    return d.sort_values(["_k", "feature"], ascending=[False, True], kind="mergesort")["feature"].tolist()


# ---------------------------------------------------------------- plotting
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def banner(fig, feat, line2, line3, kind):
    a = fig.add_axes([0, 0.885, 1, 0.115])
    a.set_xlim(0, 1); a.set_ylim(0, 1); a.axis("off")
    a.add_patch(__import__("matplotlib").patches.Rectangle((0, 0), 1, 1, color=BAND[kind], lw=0))
    a.text(0.012, 0.70, feat, fontsize=19, color=INK, va="center", weight="bold")
    a.text(0.012, 0.36, line2, fontsize=10.5, color=INK, va="center")
    a.text(0.012, 0.12, line3, fontsize=8.5, color=INK2, va="center", family="monospace")


def style(a, title, ylab, xlab, log=False):
    a.set_title(title, fontsize=9.5, color=INK, loc="left")
    a.set_ylabel(ylab, fontsize=8.5, color=INK2)
    a.set_xlabel(xlab, fontsize=8.5, color=INK2)
    a.tick_params(labelsize=7.5, colors=INK2)
    a.grid(True, color=GRID, lw=0.8)
    a.set_axisbelow(True)
    for s in a.spines.values():
        s.set_color(GRID)
    if log:
        a.set_yscale("log")


def _y(h, e, norm):
    s = h.sum()
    return (h / s if s else h) if norm else h            # normalized = fraction of events per bin


def fill_bkg(a, ctr, e, b, norm, label, fill=BKG_FILL, edge=BKG_EDGE):
    y = _y(hist(b, e), e, norm)
    a.fill_between(ctr, y, step="mid", color=fill, lw=0, label=label)
    a.step(ctr, y, where="mid", color=edge, lw=1)


def text_pages(title, lines, rnd, per_page=52, size=7.3, kind=None, feat=None):
    plt = _plt()
    figs = []
    chunks = [lines[i:i + per_page] for i in range(0, max(len(lines), 1), per_page)] or [[]]
    for j, ch in enumerate(chunks, 1):
        fig = plt.figure(figsize=(11, 8.5))
        if feat:
            banner(fig, feat, title, f"page {j}/{len(chunks)}", kind or "overview")
            y0 = 0.86
        else:
            fig.text(0.04, 0.955, title + (f"  ({j}/{len(chunks)})" if len(chunks) > 1 else ""),
                     fontsize=14, color=INK, va="top")
            y0 = 0.905
        fig.text(0.04, y0, "\n".join(ch), fontsize=size, color=INK, va="top", family="monospace",
                 linespacing=1.33)
        fig.text(0.96, 0.015, f"{SCRIPT_TAG} · round {rnd}", fontsize=7, color=INK2, ha="right")
        figs.append(fig)
    return figs



# ---------------------------------------------------------------- unit test
def unit_test_ht(dfs):
    """By design: all background < HT_TEST_GEV and all signal >= HT_TEST_GEV on HT_TEST_VAR.
    Units from the signal median (> 1000 -> MeV). Returns (passed: bool, lines)."""
    var, g = HT_TEST_VAR, HT_TEST_GEV
    L = ["=" * 78, f"UNIT TEST  HTmiss selection:  background {var} < {g:g} GeV,  signal {var} >= {g:g} GeV",
         "=" * 78]
    if any(var not in d.columns for d in dfs.values()):
        L.append(f"FLAG  {var} is missing from at least one file -- test not run")
        return False, L
    sig = np.concatenate([clean(dfs[m][var])[0] for m in MASS_FILES])
    scale = 1000.0 if len(sig) and np.median(sig) > 1000 else 1.0
    L.append(f"units: {'MeV' if scale > 1 else 'GeV'} (signal median {np.median(sig) / scale:,.1f} GeV)")
    L.append(f"  {'file':<13} {'n':>7} {'invalid':>7} {'min GeV':>9} {'max GeV':>9} {'violating':>9}  result")
    ok_all = True
    for k, d in dfs.items():
        raw = pd.to_numeric(d[var], errors="coerce").to_numpy(float)
        x = clean(d[var])[0] / scale
        bad = int(np.sum(x >= g)) if k == "bkg" else int(np.sum(x < g))
        inv = int(len(raw) - len(x))
        ok = bad == 0 and len(x) > 0
        ok_all &= ok
        L.append(f"  {k:<13} {len(raw):>7,} {inv:>7,} {x.min() if len(x) else np.nan:9.2f} "
                 f"{x.max() if len(x) else np.nan:9.2f} {bad:>9,}  {'PASS' if ok else 'FLAG'}")
    L.append("")
    L.append("RESULT: PASS -- background and signal sit on opposite sides of the cut, as designed" if ok_all
             else "RESULT: FLAG -- NOT [all background < cut and all signal >= cut]; check the files")
    return ok_all, L


# ---------------------------------------------------------------- NN feature lists
def read_nn_lists(path):
    """'# NN1 barrel (20)' headers followed by one feature per line -> {block: [names]}."""
    if not path.exists():
        return {}
    blocks, cur = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        m = re.match(r"#\s*(NN\d)\s+(barrel|endcap)\b", s, re.I)
        if m:
            cur = f"{m.group(1).upper()} {m.group(2).lower()}"
            blocks[cur] = []
        elif s and not s.startswith("#") and cur:
            blocks[cur].append(s)
    return blocks


def resolve(name, region, cols):
    """CSV column for a list name: exact, else region tag inserted, else name_raw."""
    if name in cols:
        return name, "exact"
    tok = name.split("_")
    for k in range(1, len(tok)):
        c = "_".join(tok[:k] + [region] + tok[k:])
        if c in cols:
            return c, f"region-tagged ({region})"
    if name + "_raw" in cols:
        return name + "_raw", "_raw"
    return None, "NOT FOUND"


# ---------------------------------------------------------------- plotting
# mk5 layout: two plot columns (raw | normalized, or endcap | barrel) and a third, narrow column per row that
# holds that row's legend, so no legend ever covers data.  Panel codes (1a, 1b, ...) = row number + column letter.
PLOT_GRID = dict(left=0.058, right=0.995, wspace=0.16, width_ratios=[1, 1, 0.72])
LEGEND_FS = 7.2


def legend_col(fig, ss, handles, labels, title=None):
    """A blank axes in the legend column with the row's legend, left-aligned and vertically centred."""
    lax = fig.add_subplot(ss)
    lax.axis("off")
    if handles:
        lg = lax.legend(handles, labels, loc="center left", bbox_to_anchor=(0.0, 0.5), frameon=False,
                        fontsize=LEGEND_FS, labelcolor=INK, handlelength=1.9, borderaxespad=0.0,
                        title=title, title_fontsize=LEGEND_FS + 0.6, alignment="left")
        if title:
            lg.get_title().set_color(INK2)
    return lax


def region_page(feat, region, e, b, ms, sc, dcrit, fill, rank, n_rank, lists):
    plt = _plt()
    fig = plt.figure(figsize=(11, 8.5))
    md = {m: sc[m] for m in MASS_FILES}
    fin = {m: d for m, d in md.items() if np.isfinite(d)}
    mn = min(fin, key=fin.get) if fin else None
    mx = max(fin, key=fin.get) if fin else None
    comb = np.concatenate(list(ms.values()))
    used = f"   ·   in: {', '.join(lists)}" if lists else ""
    banner(fig, feat,
           f"region: {region.upper()}   ·   rank {rank} / {n_rank}{used}",
           f"D_equal {sc['comb_equal']:.3f} (noise {dcrit:.3f})   D_pooled {sc['comb_pooled']:.3f}   "
           + (f"min {fin[mn]:.3f} ({mn})   max {fin[mx]:.3f} ({mx})   " if fin else "")
           + f"bkg n = {len(b):,}   sig n = {len(comb):,}", region)
    gs = fig.add_gridspec(3, 3, top=0.845, bottom=0.075, hspace=0.55, **PLOT_GRID)
    ctr = 0.5 * (e[:-1] + e[1:])
    cw = np.concatenate([np.full(len(x), 1.0 / len(x)) for x in ms.values() if len(x)]) if len(comb) else None
    leg = {}
    for col, norm in ((0, False), (1, True)):
        ylab, mode, c = ("fraction per bin", "normalized", "b") if norm else ("events", "raw", "a")
        a = fig.add_subplot(gs[0, col])
        fill_bkg(a, ctr, e, b, norm, f"background   n {len(b):,}")
        for i, (m, x) in enumerate(ms.items()):
            if len(x):
                a.step(ctr, _y(hist(x, e), e, norm), where="mid", color=SLOT[i], lw=1.8,
                       label=f"{m}   D {sc[m]:.3f}   n {len(x):,}")
        style(a, f"1{c} · each mass point vs background · {mode}", ylab, feat, log=not norm)
        leg.setdefault(0, a.get_legend_handles_labels())
        a = fig.add_subplot(gs[1, col])
        fill_bkg(a, ctr, e, b, norm, f"background   n {len(b):,}")
        if len(comb):
            a.step(ctr, _y(hist(comb, e), e, norm), where="mid", color=SLOT[6], lw=1.8,
                   label=f"combined, pooled   D {sc['comb_pooled']:.3f}   n {len(comb):,}")
            hw = hist(comb, e, cw)
            yw = _y(hw, e, True) if norm else hw * (len(comb) / hw.sum() if hw.sum() else 1)
            a.step(ctr, yw, where="mid", color=SLOT[7], lw=1.8, ls="--",
                   label=f"equal weight per mass   D {sc['comb_equal']:.3f}")
        style(a, f"2{c} · combined signal vs background · {mode}", ylab, feat, log=not norm)
        leg.setdefault(1, a.get_legend_handles_labels())
        a = fig.add_subplot(gs[2, col])
        fill_bkg(a, ctr, e, b, norm, f"background   n {len(b):,}")
        style(a, f"3{c} · background alone · {mode}", ylab, feat, log=not norm)
        leg.setdefault(2, a.get_legend_handles_labels())
    legend_col(fig, gs[0, 2], *leg[0], title="1 · each mass point")
    legend_col(fig, gs[1, 2], *leg[1], title="2 · combined signal")
    legend_col(fig, gs[2, 2], *leg[2], title=f"3 · background alone\nNaN {fill[0]:.1%}   −999 {fill[1]:.1%}")
    fig.text(0.995, 0.006, "a = raw (log y)   b = normalized   ·   edge bins include under/overflow · NaN and -999 removed",
             fontsize=6.5, color=INK2, ha="right")
    return fig


def table_lines(df, top=40):
    d = df.set_index("feature").loc[rank_order(df)].reset_index().head(top)
    if d.empty:
        return ["(no features)"]
    w = max([len("feature")] + [len(f) for f in d["feature"]])
    hdr = f"{'#':>3}  {'feature':<{w}}  {'D_equal':>7}  {'noise':>6}  {'D_pooled':>8}  {'D_min':>6}  {'D_max':>6}  {'n_bkg':>7}"
    out = [hdr, "-" * len(hdr)]
    for i, r in enumerate(d.itertuples(index=False), 1):
        flag = " " if r.D_comb_equal >= r.Dcrit_comb_equal else "*"
        out.append(f"{i:>3}  {r.feature:<{w}}  {r.D_comb_equal:7.3f}{flag} {r.Dcrit_comb_equal:6.3f}  "
                   f"{r.D_comb_pooled:8.3f}  {r.D_mass_min:6.3f}  {r.D_mass_max:6.3f}  {r.n_bkg:7,}")
    out += ["", "* = D_equal below its noise floor (not distinguishable from no separation)"]
    return out


def ranking_fig(df, title, top=40):
    plt = _plt()
    d = df.set_index("feature").loc[rank_order(df)].reset_index().head(top)
    d = d[np.isfinite(d["D_comb_equal"])]
    if d.empty:
        return None
    fig, a = plt.subplots(figsize=(11, 8.5), constrained_layout=True)
    a.barh(d["feature"][::-1], d["D_comb_equal"][::-1], color=SLOT[0], height=0.7)
    for y, (v, c) in enumerate(zip(d["D_comb_equal"][::-1], d["Dcrit_comb_equal"][::-1])):
        a.text(v + 0.005, y, f"{v:.3f}", va="center", fontsize=7, color=INK2)
        a.plot([c, c], [y - 0.35, y + 0.35], color=INK, lw=1.2)
    a.set_xlabel("KS D, combined signal (equal weight per mass) vs background   ·   tick = noise floor",
                 fontsize=9, color=INK2)
    a.set_title(title, fontsize=11, color=INK, loc="left")
    a.set_xlim(0, 1)
    a.tick_params(labelsize=7, colors=INK2)
    a.grid(True, axis="x", color=GRID)
    a.set_axisbelow(True)
    for s in a.spines.values():
        s.set_color(GRID)
    return fig


def dcrit(n_s, n_b):
    return 1.36 * np.sqrt(1.0 / n_s + 1.0 / n_b) if n_s > 0 and n_b > 0 else np.nan


# ---------------------------------------------------------------- mk4: categories and thresholds
HTMISS_LINKED = ["met_significance_NOSYS", "jet_pt_max_NOSYS", "htmissScalar_NOSYS", "htmiss_x_NOSYS",
                 "htmiss_y_NOSYS", "met_sumet_NOSYS", "msvtx_closestJet_pt_NOSYS", "jet_n_NOSYS",
                 "msvtx_jetMinDR_NOSYS"]      # D partly set by the by-design HTmiss split
NON_PHYSICS = [r"trigpassed_.*", r"globaltriggermatch.*", r"isgood.*", r"coreflags", r"hasgoodpv",
               r"iscompleteevent", r".*interactionspercrossing"]   # trigger / quality / pileup
WEAK_D = 0.20          # below this (or below 2x noise floor) a feature "does not separate" in a region
STRONG_D = 0.50        # P2 adds unused features at or above this
SUSPICIOUS_D = 0.99    # any single mass point this separated -> flagged, never added
CORR_BLOCK = 0.90      # |Spearman| on background at/above which features share a redundancy block
CORR_NMAX = 12000      # background events used for the correlation matrix (random subsample)
DCOR_N = 3000          # background events used for dCor between NN1 and NN2 surrogate scores
CV_FOLDS = 5
SEED = 7


def category(f):
    if f in HTMISS_LINKED:
        return "htmiss-linked"
    if any(re.fullmatch(p, f, re.I) for p in NON_PHYSICS):
        return "non-physics"
    return None


def separates(d, dc):
    return bool(np.isfinite(d) and d >= max(WEAK_D, 2 * dc))


def short(m):
    return m.replace("mH", "").replace("_mS", "/")


# ---------------------------------------------------------------- block C helpers
def spearman_bkg(num, rmask, feats, region, rng):
    m = rmask["bkg"][region]
    idx = np.flatnonzero(m)
    if len(idx) > CORR_NMAX:
        idx = np.sort(rng.choice(idx, CORR_NMAX, replace=False))
    cols = {}
    for f in feats:
        x = num["bkg"][f][idx].copy()
        x[(~np.isfinite(x)) | (x == SENTINEL)] = np.nan
        cols[f] = x
    df = pd.DataFrame(cols)
    return df.corr(method="spearman", min_periods=100), len(idx)


def make_blocks(order, rho, thr):
    """Greedy complete linkage: walk features strongest-first; a feature joins a block only if
    |rho| >= thr with EVERY member. First member (strongest) is the representative."""
    a = rho.abs().fillna(0.0)
    left, blocks = list(order), []
    while left:
        head = left.pop(0)
        blk = [head]
        for g in list(left):
            if all(a.at[g, h] >= thr for h in blk):
                blk.append(g)
                left.remove(g)
        blocks.append(blk)
    return blocks


def dcor(x, y):
    x = np.asarray(x, float)[:, None]
    y = np.asarray(y, float)[:, None]
    A = np.abs(x - x.T)
    B = np.abs(y - y.T)
    A = A - A.mean(0) - A.mean(1)[:, None] + A.mean()
    B = B - B.mean(0) - B.mean(1)[:, None] + B.mean()
    v = np.sqrt((A * A).mean() * (B * B).mean())
    return float(np.sqrt(max((A * B).mean(), 0) / v)) if v > 0 else np.nan


def heatmap_fig(rho, feats, blocks, title):
    plt = _plt()
    import matplotlib.colors as mc
    order = [f for b in blocks for f in b if f in feats]
    a = rho.loc[order, order].abs().to_numpy()
    fig, ax = plt.subplots(figsize=(11, 8.5), constrained_layout=True)
    cmap = mc.LinearSegmentedColormap.from_list("seq", ["#ffffff", "#86b6ef", "#2a78d6", "#184f95"])
    im = ax.imshow(a, cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks(range(len(order)), order, rotation=90, fontsize=5.5, color=INK2)
    ax.set_yticks(range(len(order)), order, fontsize=5.5, color=INK2)
    pos = 0
    for b in blocks:
        n = len([f for f in b if f in feats])
        if n > 1:
            ax.add_patch(__import__("matplotlib").patches.Rectangle((pos - .5, pos - .5), n, n, fill=False,
                                                                     ec=INK, lw=1.2))
        pos += n
    fig.colorbar(im, ax=ax, shrink=0.6, label="|Spearman| on background")
    ax.set_title(title, fontsize=11, color=INK, loc="left")
    return fig


# ---------------------------------------------------------------- block D helpers
def sk():
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import StratifiedKFold
        return HistGradientBoostingClassifier, roc_auc_score, StratifiedKFold
    except ImportError:
        return None


def oof_scores(X, y, w, strat, desc):
    HGB, _, SKF = sk()
    s = np.zeros(len(y))
    for k, (tr, te) in enumerate(SKF(CV_FOLDS, shuffle=True, random_state=SEED).split(X, strat), 1):
        clf = HGB(max_iter=300, learning_rate=0.08, early_stopping=True, validation_fraction=0.15,
                  random_state=SEED)
        clf.fit(X[tr], y[tr], sample_weight=w[tr])
        s[te] = clf.predict_proba(X[te])[:, 1]
        bar(k, CV_FOLDS, desc)
    return s


def event_weights(y, mass):
    """Background total 0.5, signal total 0.5 split equally over mass points present."""
    w = np.zeros(len(y))
    nb = (y == 0).sum()
    w[y == 0] = 0.5 / nb if nb else 0
    ms = [m for m in np.unique(mass[y == 1])]
    for m in ms:
        sel = (y == 1) & (mass == m)
        w[sel] = 0.5 / (len(ms) * sel.sum())
    return w * len(y)


def proto_txt(name, desc, nets):
    L = [f"# prototype {name} -- {desc}", f"# written by {SCRIPT_TAG} {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for key, feats in nets.items():
        L.append(f"# {key} ({len(feats)})")
        L += feats
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- block A page builders
def a_shape_page(feat, rank, n_rank, e, bb, be, sb, se, d_bkg, d_sig, de, db, flag):
    plt = _plt()
    fig = plt.figure(figsize=(11, 8.5))
    banner(fig, feat, f"BARREL vs ENDCAP  ·  shape  ·  rank {rank} / {n_rank} by |D_barrel - D_endcap|  ·  {flag}",
           f"shape D(barrel vs endcap): background {d_bkg:.3f}   signal {d_sig:.3f}      "
           f"separation D: endcap {de:.3f}   barrel {db:.3f}", "overview")
    gs = fig.add_gridspec(2, 3, top=0.845, bottom=0.075, hspace=0.42, **PLOT_GRID)
    ctr = 0.5 * (e[:-1] + e[1:])
    for row, (lab, xb, xe, d) in enumerate((("background (data)", bb, be, d_bkg),
                                            ("combined signal (MC, pooled)", sb, se, d_sig))):
        hl = None
        for col, norm in ((0, False), (1, True)):
            a = fig.add_subplot(gs[row, col])
            if len(xe):
                y = _y(hist(xe, e), e, norm)
                a.fill_between(ctr, y, step="mid", color=BAND["endcap"], lw=0, label=f"endcap   n {len(xe):,}")
                a.step(ctr, y, where="mid", color=SLOT[0], lw=1)
            if len(xb):
                a.step(ctr, _y(hist(xb, e), e, norm), where="mid", color=SLOT[1], lw=2,
                       label=f"barrel   n {len(xb):,}")
            style(a, f"{row + 1}{'b' if norm else 'a'} · {lab} · {'normalized' if norm else 'raw'}",
                  "fraction per bin" if norm else "events", feat, log=not norm)
            hl = hl or a.get_legend_handles_labels()
        legend_col(fig, gs[row, 2], *hl, title=f"{row + 1} · {lab}\nshape D = {d:.3f}")
    fig.text(0.995, 0.006, "a = raw (log y)   b = normalized   ·   edge bins include under/overflow · NaN and -999 removed",
             fontsize=6.5, color=INK2, ha="right")
    return fig


def a_sep_page(feat, rank, n_rank, e, data, flag):
    """data[region] = (b, ms, sc). Normalized only: raw counts differ ~30x between regions."""
    plt = _plt()
    fig = plt.figure(figsize=(11, 8.5))
    de, db = data["endcap"][2]["comb_equal"], data["barrel"][2]["comb_equal"]
    banner(fig, feat, f"BARREL vs ENDCAP  ·  separation side by side  ·  rank {rank} / {n_rank}  ·  {flag}",
           f"D_equal  endcap {de:.3f}   barrel {db:.3f}   difference (barrel - endcap) {db - de:+.3f}   "
           "(normalized only: raw counts differ ~30x between regions)", "overview")
    gs = fig.add_gridspec(2, 3, top=0.845, bottom=0.075, hspace=0.42, **PLOT_GRID)
    ctr = 0.5 * (e[:-1] + e[1:])
    h1, h2 = {}, {}
    for col, r in enumerate(("endcap", "barrel")):
        b, ms, sc = data[r]
        c = "ab"[col]
        a = fig.add_subplot(gs[0, col])
        fill_bkg(a, ctr, e, b, True, "background")
        for i, (m, x) in enumerate(ms.items()):
            if len(x):
                a.step(ctr, _y(hist(x, e), e, True), where="mid", color=SLOT[i], lw=1.8, label=m)
        style(a, f"1{c} · {r.upper()} · each mass point vs background", "fraction per bin", feat)
        for hd, lb in zip(*a.get_legend_handles_labels()):
            h1.setdefault(lb, hd)
        a = fig.add_subplot(gs[1, col])
        fill_bkg(a, ctr, e, b, True, "background")
        comb = np.concatenate(list(ms.values()))
        if len(comb):
            cw = np.concatenate([np.full(len(x), 1.0 / len(x)) for x in ms.values() if len(x)])
            a.step(ctr, _y(hist(comb, e, cw), e, True), where="mid", color=SLOT[7], lw=1.8, ls="--",
                   label="combined, equal weight")
        style(a, f"2{c} · {r.upper()} · combined signal vs background", "fraction per bin", feat)
        for hd, lb in zip(*a.get_legend_handles_labels()):
            h2.setdefault(lb, hd)

    def lab1(lb):
        if lb == "background":
            return f"background   n {len(data['endcap'][0]):,} | {len(data['barrel'][0]):,}"
        return f"{lb}   D {data['endcap'][2].get(lb, np.nan):.3f} | {data['barrel'][2].get(lb, np.nan):.3f}"

    legend_col(fig, gs[0, 2], list(h1.values()), [lab1(k) for k in h1], title="1 · each mass point\nD: endcap | barrel")
    legend_col(fig, gs[1, 2], list(h2.values()),
               [lab1(k) if k == "background" else f"{k}   D {de:.3f} | {db:.3f}" for k in h2],
               title="2 · combined signal\nD: endcap | barrel")
    fig.text(0.995, 0.006, "a = endcap   b = barrel   ·   normalized   ·   edge bins include under/overflow · NaN and -999 removed",
             fontsize=6.5, color=INK2, ha="right")
    return fig


def paired_fig(df, title, top=40):
    plt = _plt()
    d = df.assign(_m=np.fmax(df.D_endcap.fillna(0), df.D_barrel.fillna(0))).sort_values(
        ["_m", "feature"], ascending=[False, True]).head(top)
    if d.empty:
        return None
    fig, a = plt.subplots(figsize=(11, 8.5), constrained_layout=True)
    yy = np.arange(len(d))[::-1]
    a.barh(yy + 0.2, d.D_endcap.fillna(0), height=0.38, color=SLOT[0], label="endcap")
    a.barh(yy - 0.2, d.D_barrel.fillna(0), height=0.38, color=SLOT[1], label="barrel")
    a.set_yticks(yy, d.feature, fontsize=6.5, color=INK2)
    a.set_xlim(0, 1)
    a.set_xlabel("KS D, combined signal (equal weight) vs background", fontsize=9, color=INK2)
    a.set_title(title, fontsize=11, color=INK, loc="left")
    a.legend(frameon=False, fontsize=8, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, borderaxespad=0.2)
    a.grid(True, axis="x", color=GRID)
    a.set_axisbelow(True)
    for s in a.spines.values():
        s.set_color(GRID)
    return fig


def save_pdf(path, pages, title, png=False):
    plt = _plt()
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(path) as pdf:
        for name, fig in pages:
            pdf.savefig(fig)
            if png:
                (path.parent / "png").mkdir(exist_ok=True)
                fig.savefig(path.parent / "png" / f"{name}.png", dpi=110)
            plt.close(fig)
        pdf.infodict()["Title"] = title


# ---------------------------------------------------------------- main
def main():
    global OUT, DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="folder holding the background + 6 mass-point CSVs")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--block", default="ABCD", help="any of A B C D, e.g. --block BC")
    ap.add_argument("--nn-list", default=str(NN_FEATURES_FILE))
    ap.add_argument("--no-plots", action="store_true", help="summaries, tables and exports only")
    ap.add_argument("--top", type=int, default=0, help="per-feature PDFs for the top N only (0 = all)")
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    DATA, data_src = resolve_data(args.data)
    log(f"data folder from {data_src}: {DATA}")
    R, BLK = args.round, set(args.block.upper())
    OUT = HERE / f"out_sigbg_mk5_r{R}"
    dirs = {k: OUT / v for k, v in {"0": "00_common", "A": "A_barrel_vs_endcap", "B": "B_mc_vs_data",
                                    "C": "C_correlation", "D": "D_prototypes", "G": "gambit_inputs"}.items()}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    log(f"round {R} -> {OUT}   blocks: {''.join(sorted(BLK))}")

    # ================================================================ 00 common
    dfs = load()
    pats = read_exclude_file()
    feats, rep, all7 = feature_pool(dfs, pats)
    with open(dirs["0"] / "excluded_report.txt", "w", encoding="utf-8") as fh:
        for k, v in rep.items():
            fh.write(f"===== {k} ({len(v)}) =====\n" + "\n".join(v) + "\n\n")
    OUT, _o = dirs["0"], OUT              # inventory() writes into OUT
    inventory(dfs, rep, pats)
    OUT = _o
    ut_pass, ut_lines = unit_test_ht(dfs)
    (dirs["0"] / "unit_tests.txt").write_text("\n".join(ut_lines) + "\n", encoding="utf-8")
    print("\n".join(ut_lines), flush=True)
    chosen, audit = find_region(all7, dfs)
    (dirs["0"] / "region_audit.txt").write_text(audit, encoding="utf-8")
    rmask = {k: region_masks(df, chosen) for k, df in dfs.items()}
    regions = [r for r in ("endcap", "barrel", "all") if r in rmask["bkg"]]
    for r in regions:
        log(f"  {r:<7} bkg {rmask['bkg'][r].sum():>7,}  " +
            "  ".join(f"{m} {rmask[m][r].sum():,}" for m in MASS_FILES))
    num = {k: df[feats].apply(pd.to_numeric, errors="coerce").to_numpy(float) for k, df in dfs.items()}
    num = {k: {f: v[:, i] for i, f in enumerate(feats)} for k, v in num.items()}
    feats, copies = dedup(num, feats)
    rep_of = {f: f for f in feats} | {c: k for k, cs in copies.items() for c in cs}
    dup_lines = [f"{len(copies)} groups of rank-identical columns (same missing pattern, same value",
                 "ordering in every file -> same KS D everywhere); kept the first name, dropped the rest", ""]
    for kf, cs in sorted(copies.items()):
        dup_lines += [kf] + [f"    = {c}" for c in cs]
    (dirs["0"] / "duplicates.txt").write_text("\n".join(dup_lines) + "\n", encoding="utf-8")
    log(f"dedup: {sum(len(v) for v in copies.values())} columns dropped in {len(copies)} groups "
        f"-> {len(feats)} features")

    def cell(k, f, r):
        return clean(num[k][f][rmask[k][r]])

    # NN lists
    blocks_nn = read_nn_lists(Path(args.nn_list))
    used_in, nn_res = {}, []
    for blk, names in blocks_nn.items():
        reg = blk.split()[1]
        for nm in names:
            col, how = resolve(nm, reg, set(all7))
            rp = rep_of.get(col) if col else None
            if col and rp is None:
                how += "; excluded from scoring"
            nn_res.append({"block": blk, "region": reg, "list_name": nm, "column": col, "resolved_by": how,
                           "scored_as": rp})
            if rp:
                used_in.setdefault(rp, []).append(blk)

    # ================================================================ scoring (shared by A-D)
    long_rows, wide_rows, const, fills, cache_sc = [], [], {}, {}, {}
    for ci, r in enumerate(regions, 1):
        log(f"[{ci}/{len(regions)}] KS scoring {r}")
        for i, f in enumerate(feats, 1):
            b, bnan, bsen = cell("bkg", f, r)
            fills[(f, r)] = (bnan, bsen)
            ms = {m: cell(m, f, r)[0] for m in MASS_FILES}
            sc = score_cell(b, ms)
            if sc is None:
                const.setdefault(f, []).append(r)
                sc = {m: np.nan for m in MASS_FILES} | {"comb_pooled": np.nan, "comb_equal": np.nan}
            cache_sc[(f, r)] = sc
            ns = {m: len(x) for m, x in ms.items()}
            n_pool = sum(ns.values())
            inv = [1.0 / n for n in ns.values() if n]
            n_eff = (len(inv) ** 2) / sum(inv) if inv else 0
            for m in MASS_FILES:
                long_rows.append({"round": R, "region": r, "feature": f, "comparison": m, "D": sc[m],
                                  "D_crit": dcrit(ns[m], len(b)), "n_sig": ns[m], "n_bkg": len(b)})
            for c, n in (("comb_pooled", n_pool), ("comb_equal", n_eff)):
                long_rows.append({"round": R, "region": r, "feature": f, "comparison": c, "D": sc[c],
                                  "D_crit": dcrit(n, len(b)), "n_sig": n, "n_bkg": len(b)})
            md = [sc[m] for m in MASS_FILES]
            fin = np.isfinite(md).any()
            wide_rows.append({"round": R, "region": r, "feature": f, **{f"D_{m}": sc[m] for m in MASS_FILES},
                              "D_comb_pooled": sc["comb_pooled"], "D_comb_equal": sc["comb_equal"],
                              "Dcrit_comb_equal": dcrit(n_eff, len(b)),
                              "D_mass_min": np.nanmin(md) if fin else np.nan,
                              "D_mass_max": np.nanmax(md) if fin else np.nan,
                              "bkg_nan_frac": bnan, "bkg_m999_frac": bsen, "n_bkg": len(b), "n_sig": n_pool,
                              "category": category(f) or "",
                              "suspicious": bool(fin and np.nanmax(md) >= SUSPICIOUS_D),
                              "nn_lists": "; ".join(used_in.get(f, []))})
            bar(i, len(feats), f)
    wide = pd.DataFrame(wide_rows)
    W = wide.set_index(["feature", "region"])
    rank_in = {}
    for r in regions:
        for i, f in enumerate(rank_order(wide[wide.region == r]), 1):
            rank_in[(f, r)] = i
    plt = _plt()

    # ================================================================ B: MC vs data
    if "B" in BLK:
        log("block B: MC vs data")
        pd.DataFrame(long_rows).to_csv(dirs["B"] / "ks_scores_long.csv", index=False)
        wide.to_csv(dirs["B"] / "ks_scores_wide.csv", index=False)
        nn_rows = []
        for x in nn_res:
            rp, reg = x["scored_as"], x["region"]
            ok = rp is not None and (rp, reg) in W.index
            y = W.loc[(rp, reg)] if ok else None
            nn_rows.append(x | {"D_equal": y.D_comb_equal if ok else np.nan,
                                "D_crit": y.Dcrit_comb_equal if ok else np.nan,
                                "D_mass_min": y.D_mass_min if ok else np.nan,
                                "D_mass_max": y.D_mass_max if ok else np.nan,
                                "rank_in_region": rank_in[(rp, reg)] if ok else np.nan, "n_features": len(feats)})
        nn_df = pd.DataFrame(nn_rows)
        if len(nn_df):
            nn_df.to_csv(dirs["B"] / "nn_feature_scores.csv", index=False)
        nn_lines = []
        for blk in blocks_nn:
            t = nn_df[nn_df.block == blk]
            w = max([12] + [len(s) for s in t.list_name])
            nn_lines += [f"{blk}  ({len(t)} features, scored in region {blk.split()[1]})",
                         f"  {'list name':<{w}}  {'D_equal':>7}  {'noise':>6}  {'min':>6}  {'max':>6}  {'rank':>8}  scored as",
                         "  " + "-" * (w + 58)]
            for y in t.sort_values("D_equal", ascending=False, na_position="last").itertuples(index=False):
                rk = f"{int(y.rank_in_region)}/{y.n_features}" if np.isfinite(y.rank_in_region) else "--"
                if pd.isna(y.column):
                    sa = "NOT FOUND in the CSV columns"
                elif pd.isna(y.scored_as):
                    sa = f"{y.column}  [{y.resolved_by}]"
                elif y.scored_as == y.list_name:
                    sa = y.scored_as
                else:
                    sa = f"{y.scored_as}  [{y.resolved_by}" + (f": {y.column}]" if y.column != y.scored_as else "]")
                nn_lines.append(f"  {y.list_name:<{w}}  {y.D_equal:7.3f}  {y.D_crit:6.3f}  {y.D_mass_min:6.3f}  "
                                f"{y.D_mass_max:6.3f}  {rk:>8}  {sa}")
            nn_lines.append("")
        strong_lines = []
        for r in ("endcap", "barrel"):
            inreg = {f for f, bl in used_in.items() if any(b.endswith(r) for b in bl)}
            wr = wide[(wide.region == r) & np.isfinite(wide.D_comb_equal)]
            top = [f for f in rank_order(wr) if f not in inreg][:STRONG_TOP]
            strong_lines += [f"{r.upper()}: top {STRONG_TOP} features used by neither NN1 nor NN2 {r}"]
            for f in top:
                y = W.loc[(f, r)]
                tag = f"   [{y.category}]" if y.category else ""
                tag += "   [suspicious: one mass point D>=0.99]" if y.suspicious else ""
                strong_lines.append(f"  {rank_in[(f, r)]:>3}  {f:<40} D_equal {y.D_comb_equal:.3f}  "
                                    f"(min {y.D_mass_min:.3f}, max {y.D_mass_max:.3f}){tag}")
            strong_lines.append("")
        print("\n".join(nn_lines + strong_lines), flush=True)
        pages = []
        cover = [f"date         {time.strftime('%Y-%m-%d %H:%M')}", f"data         {DATA}",
                 f"background   {BKG_FILE}  rows {len(dfs['bkg']):,}",
                 *[f"signal       {fn}  rows {len(dfs[m]):,}" for m, fn in MASS_FILES.items()],
                 f"unit test    HTmiss split: {'PASS' if ut_pass else 'FLAG'}", f"features     {len(feats)}", "",
                 "KS D = sup|F_s - F_b| in [0, 1] = best single-cut (signal eff - background eff).",
                 "noise floor D_crit = 1.36 sqrt(1/n_s + 1/n_b), 95% level for identical distributions.",
                 "Per feature: features/NNN_<feature>/ (NNN = endcap rank) -> overview + endcap, barrel, all,",
                 "each page: 1 each MC mass point vs data, 2 combined MC vs data, 3 data alone (raw | normalized)."]
        for title, lines, kw in [(f"B · MC vs data · round {R}", cover, {"size": 8.5}),
                                 ("B · unit test", ut_lines, {}),
                                 ("B · NN feature lists: KS D in each list's region", nn_lines or ["(no list)"],
                                  {"size": 6.6, "per_page": 60}),
                                 ("B · strong features not in the NN lists", strong_lines, {})]:
            pages += [("t", f) for f in text_pages(title, lines, R, **kw)]
        for r in regions:
            t = wide[wide.region == r]
            fig = ranking_fig(t, f"B · top 40 · region {r.upper()}")
            if fig is not None:
                pages.append(("r", fig))
            pages += [("t", f) for f in text_pages(f"B · top 40 table · {r.upper()}", table_lines(t), R)]
        save_pdf(dirs["B"] / "B_SUMMARY.pdf", pages, f"{SCRIPT_TAG} round {R} B summary")
        if not args.no_plots:
            order = rank_order(wide[wide.region == "endcap"])
            todo = order[:args.top] if args.top else order
            (dirs["B"] / "features").mkdir(exist_ok=True)
            log(f"block B: {len(todo)} feature PDFs")
            for fi, f in enumerate(todo, 1):
                rk = order.index(f) + 1
                safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f)
                fdir = dirs["B"] / "features" / f"{rk:03d}_{safe}"
                fdir.mkdir(exist_ok=True)
                L = [f"rank {rk} / {len(order)} by endcap D_equal", "",
                     "used by: " + (", ".join(used_in[f]) if f in used_in else "neither NN list")]
                if W.loc[(f, "all")].category:
                    L.append(f"category: {W.loc[(f, 'all')].category}")
                if f in copies:
                    L += ["", "rank-identical columns merged into this one:"] + [f"    {c}" for c in copies[f]]
                if f in const:
                    L += ["", "constant (no page) in: " + ", ".join(const[f])]
                hdr = f"{'region':<7} {'D_equal':>7} {'noise':>6} {'D_pooled':>8} " + \
                      " ".join(f"{short(m):>8}" for m in MASS_FILES) + f" {'n_bkg':>7} {'rank':>8}"
                L += ["", hdr, "-" * len(hdr)]
                for r in regions:
                    y = W.loc[(f, r)]
                    L.append(f"{r:<7} {y.D_comb_equal:7.3f} {y.Dcrit_comb_equal:6.3f} {y.D_comb_pooled:8.3f} "
                             + " ".join(f"{y['D_' + m]:8.3f}" for m in MASS_FILES)
                             + f" {int(y.n_bkg):7,} {str(rank_in[(f, r)]) + '/' + str(len(feats)):>8}")
                pg = [("p00_overview", fig) for fig in text_pages(f"MC vs data · overview · rank {rk} / {len(order)}",
                                                                   L, R, feat=f, size=8.5, kind="overview")]
                for r in regions:
                    if r in const.get(f, []):
                        continue
                    b = cell("bkg", f, r)[0]
                    ms = {m: cell(m, f, r)[0] for m in MASS_FILES}
                    e = edges_for([b] + list(ms.values()))
                    if e is None:
                        continue
                    y = W.loc[(f, r)]
                    pg.append((r, region_page(f, r, e, b, ms, cache_sc[(f, r)], y.Dcrit_comb_equal, fills[(f, r)],
                                              rk, len(order), used_in.get(f, []))))
                save_pdf(fdir / f"{safe}.pdf", pg, f"{f} - MC vs data - round {R}", args.png)
                bar(fi, len(todo), f)

    # ================================================================ A: barrel vs endcap
    a_df = None
    if "A" in BLK:
        rows = []
        for f in feats:
            ye, yb = W.loc[(f, "endcap")], W.loc[(f, "barrel")]
            be, bb = cell("bkg", f, "endcap")[0], cell("bkg", f, "barrel")[0]
            se = np.concatenate([cell(m, f, "endcap")[0] for m in MASS_FILES])
            sb = np.concatenate([cell(m, f, "barrel")[0] for m in MASS_FILES])
            ones = np.ones
            d_bkg = ks_w(bb, ones(len(bb)), be, ones(len(be))) if np.unique(np.r_[bb, be]).size > 1 else np.nan
            d_sig = ks_w(sb, ones(len(sb)), se, ones(len(se))) if np.unique(np.r_[sb, se]).size > 1 else np.nan
            s_e, s_b = separates(ye.D_comb_equal, ye.Dcrit_comb_equal), separates(yb.D_comb_equal, yb.Dcrit_comb_equal)
            flag = "both" if s_e and s_b else "endcap only" if s_e else "barrel only" if s_b else "neither"
            rows.append({"feature": f, "D_endcap": ye.D_comb_equal, "Dcrit_endcap": ye.Dcrit_comb_equal,
                         "D_barrel": yb.D_comb_equal, "Dcrit_barrel": yb.Dcrit_comb_equal,
                         "delta_barrel_minus_endcap": yb.D_comb_equal - ye.D_comb_equal,
                         "rank_endcap": rank_in[(f, "endcap")], "rank_barrel": rank_in[(f, "barrel")],
                         "separates": flag, "shape_D_bkg": d_bkg, "shape_D_sig": d_sig,
                         "category": ye.category, "nn_lists": "; ".join(used_in.get(f, []))})
        a_df = pd.DataFrame(rows)
        a_df["_ad"] = a_df.delta_barrel_minus_endcap.abs().fillna(-1)
        a_df = a_df.sort_values(["_ad", "feature"], ascending=[False, True]).drop(columns="_ad")
    if "A" in BLK:
        log("block A: barrel vs endcap")
        a_df.to_csv(dirs["A"] / "barrel_vs_endcap.csv", index=False)
        cnt = a_df.separates.value_counts().to_dict()
        w = max([7] + [len(f) for f in a_df.feature])
        tab = [f"{'feature':<{w}}  {'D_end':>6} {'D_bar':>6} {'delta':>7}  {'rk_e':>4} {'rk_b':>4}  "
               f"{'shapeB':>6} {'shapeS':>6}  separates", "-" * (w + 66)]
        for y in a_df.head(60).itertuples(index=False):
            tab.append(f"{y.feature:<{w}}  {y.D_endcap:6.3f} {y.D_barrel:6.3f} {y.delta_barrel_minus_endcap:+7.3f}  "
                       f"{y.rank_endcap:>4} {y.rank_barrel:>4}  {y.shape_D_bkg:6.3f} {y.shape_D_sig:6.3f}  "
                       f"{y.separates}{'  [' + y.category + ']' if y.category else ''}")
        tab += ["", "separates = D >= max(0.20, 2 x noise floor) in that region",
                "shapeB / shapeS = KS D between barrel and endcap distributions of background / combined signal"]
        mk = []
        for x in nn_res:
            if x["scored_as"] and x["scored_as"] in set(a_df.feature):
                y = a_df.set_index("feature").loc[x["scored_as"]]
                mk.append(f"{x['block']:<11} {x['list_name']:<30} endcap {y.D_endcap:6.3f}  barrel {y.D_barrel:6.3f}  "
                          f"{y.separates}")
        cover = [f"barrel vs endcap · {len(feats)} features", "",
                 *[f"  separates in {k:<12} {v:>4}" for k, v in sorted(cnt.items())], "",
                 "pages: this cover, paired ranking chart, cross-region table (top 60 by |delta|),",
                 "mk4 list features across regions.",
                 "per feature: features/NNN_<feature>/ (NNN = rank by |delta|) -> shape page + separation page"]
        pages = [("t", f) for f in text_pages(f"A · barrel vs endcap · round {R}", cover, R, size=9)]
        fig = paired_fig(a_df, "A · top 40 features by max(D_endcap, D_barrel)")
        if fig is not None:
            pages.append(("r", fig))
        pages += [("t", f) for f in text_pages("A · cross-region table (sorted by |delta|)", tab, R, size=6.5,
                                               per_page=62)]
        pages += [("t", f) for f in text_pages("A · mk4 list features in both regions", mk or ["(no list)"], R,
                                               size=7)]
        save_pdf(dirs["A"] / "A_SUMMARY.pdf", pages, f"{SCRIPT_TAG} round {R} A summary")
        log("block A: separates counts " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
        if not args.no_plots:
            aorder = list(a_df.feature)
            todo = aorder[:args.top] if args.top else aorder
            (dirs["A"] / "features").mkdir(exist_ok=True)
            log(f"block A: {len(todo)} feature PDFs")
            for fi, f in enumerate(todo, 1):
                y = a_df.set_index("feature").loc[f]
                rk = aorder.index(f) + 1
                safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f)
                fdir = dirs["A"] / "features" / f"{rk:03d}_{safe}"
                fdir.mkdir(exist_ok=True)
                data = {r: (cell("bkg", f, r)[0], {m: cell(m, f, r)[0] for m in MASS_FILES}, cache_sc[(f, r)])
                        for r in ("endcap", "barrel")}
                allv = [data[r][0] for r in data] + [x for r in data for x in data[r][1].values()]
                e = edges_for(allv)
                if e is None:
                    continue
                sb = np.concatenate(list(data["barrel"][1].values()))
                se = np.concatenate(list(data["endcap"][1].values()))
                pg = [("shape", a_shape_page(f, rk, len(aorder), e, data["barrel"][0], data["endcap"][0], sb, se,
                                             y.shape_D_bkg, y.shape_D_sig, y.D_endcap, y.D_barrel, y.separates)),
                      ("separation", a_sep_page(f, rk, len(aorder), e, data, y.separates))]
                save_pdf(fdir / f"{safe}.pdf", pg, f"{f} - barrel vs endcap - round {R}", args.png)
                bar(fi, len(todo), f)

    # ================================================================ C: correlation / redundancy
    rho, cblocks, block_of = {}, {}, {}
    if "C" in BLK or "D" in BLK:
        log("block C: background Spearman correlation and redundancy blocks")
        for r in ("endcap", "barrel"):
            live = [f for f in rank_order(wide[(wide.region == r) & np.isfinite(wide.D_comb_equal)])]
            rho[r], n_used = spearman_bkg(num, rmask, live, r, rng)
            cblocks[r] = make_blocks(live, rho[r], CORR_BLOCK)
            for i, blk in enumerate(cblocks[r], 1):
                for f in blk:
                    block_of[(f, r)] = i
            log(f"  {r}: {len(live)} live features -> {len(cblocks[r])} blocks at |rho| >= {CORR_BLOCK} "
                f"({n_used:,} background events)")
    if "C" in BLK:
        pages, jb = [], {}
        for r in ("endcap", "barrel"):
            rho[r].to_csv(dirs["C"] / f"spearman_bkg_{r}.csv")
            top = rank_order(wide[(wide.region == r) & np.isfinite(wide.D_comb_equal)])[:40]
            pages.append(("h", heatmap_fig(rho[r], set(top), cblocks[r],
                                           f"C · {r.upper()} · |Spearman| on background, top 40 by D, boxed = block")))
            L = [f"{len(cblocks[r])} blocks; a feature joins a block only if |rho| >= {CORR_BLOCK} with every member;",
                 "the first member (strongest separator) is the representative.", ""]
            jb[r] = []
            for i, blk in enumerate(cblocks[r], 1):
                rp = blk[0]
                jb[r].append({"block": i, "representative": rp, "members": blk,
                              "D_equal": {f: round(float(W.loc[(f, r)].D_comb_equal), 4) for f in blk}})
                if len(blk) > 1:
                    L.append(f"block {i:>3}  rep {rp}  (D {W.loc[(rp, r)].D_comb_equal:.3f})")
                    L += [f"            {f:<40} D {W.loc[(f, r)].D_comb_equal:.3f}   rho to rep {rho[r].at[f, rp]:+.3f}"
                          for f in blk[1:]]
            L += ["", f"singletons: {sum(len(b) == 1 for b in cblocks[r])}"]
            pages += [("t", f) for f in text_pages(f"C · {r.upper()} · redundancy blocks", L, R, size=6.8,
                                                   per_page=60)]
            nn1 = [x["scored_as"] for x in nn_res if x["block"] == f"NN1 {r}" and x["scored_as"]]
            nn2 = [x["scored_as"] for x in nn_res if x["block"] == f"NN2 {r}" and x["scored_as"]]
            pairs = sorted(((abs(rho[r].at[a, b]), a, b) for a in set(nn1) for b in set(nn2)
                            if a in rho[r].index and b in rho[r].index and np.isfinite(rho[r].at[a, b])),
                           reverse=True)[:20]
            X = [f"mk4 {r}: the 20 most correlated NN1-NN2 feature pairs on background (|Spearman|)", ""]
            X += [f"  {p:.3f}   NN1 {a:<34} NN2 {b}" for p, a, b in pairs] or ["  (no list)"]
            X += ["", "For ABCD the two networks must be independent on background; high pairs here are where",
                  "NN1 and NN2 share information."]
            pages += [("t", f) for f in text_pages(f"C · {r.upper()} · NN1-NN2 cross-correlation (mk4)", X, R)]
        (dirs["G"] / "blocks.json").write_text(__import__("json").dumps(jb, indent=1), encoding="utf-8")
        save_pdf(dirs["C"] / "C_SUMMARY.pdf", pages, f"{SCRIPT_TAG} round {R} C summary")

    # ================================================================ gambit_inputs (always)
    drops, pools = [], {}
    for r in ("endcap", "barrel"):
        pool = []
        for f in rank_order(wide[wide.region == r]):
            y = W.loc[(f, r)]
            if f in [c for c in const if r in const[c]] or not np.isfinite(y.D_comb_equal):
                drops.append((r, f, "dead", "constant or empty in this region"))
                continue
            if y.category:
                drops.append((r, f, y.category, f"D {y.D_comb_equal:.3f}"))
                continue
            if y.suspicious:
                drops.append((r, f, "suspicious", f"max per-mass D {y.D_mass_max:.3f} >= {SUSPICIOUS_D}"))
                continue
            if not separates(y.D_comb_equal, y.Dcrit_comb_equal):
                drops.append((r, f, "weak", f"D {y.D_comb_equal:.3f} < max({WEAK_D}, 2 x {y.Dcrit_comb_equal:.3f})"))
                continue
            if block_of and (f, r) in block_of:
                rp = cblocks[r][block_of[(f, r)] - 1][0]
                if rp != f:
                    drops.append((r, f, "redundant", f"|rho| >= {CORR_BLOCK} with {rp} (block {block_of[(f, r)]})"))
                    continue
            pool.append(f)
        pools[r] = pool
        (dirs["G"] / f"pool_{r}.txt").write_text(
            f"# candidate pool, {r}: separates, not htmiss-linked / non-physics / suspicious, one per block\n"
            + "\n".join(pool) + "\n", encoding="utf-8")
    (dirs["G"] / "drop_suggestions.txt").write_text(
        "# region\tfeature\tcategory\treason\n" + "\n".join("\t".join(x) for x in drops) + "\n", encoding="utf-8")
    import json
    (dirs["G"] / "unit_tests.json").write_text(json.dumps({"htmiss_split": {"result": "PASS" if ut_pass else "FLAG",
                                                                            "lines": ut_lines}}, indent=1),
                                               encoding="utf-8")
    log(f"gambit_inputs: pool endcap {len(pools['endcap'])}, barrel {len(pools['barrel'])}; "
        f"{len(drops)} drop suggestions")

    # ================================================================ D: prototypes
    if "D" in BLK:
        if sk() is None:
            log("block D SKIPPED: scikit-learn not installed  ->  pip install scikit-learn")
        else:
            log("block D: prototype NNs (gradient-boosted surrogate, 5-fold CV)")
            HGB, AUC, _ = sk()
            P = {}
            nets0 = {}
            for r in ("endcap", "barrel"):
                for role in ("NN1", "NN2"):
                    lst = [x["scored_as"] for x in nn_res if x["block"] == f"{role} {r}" and x["scored_as"]]
                    nets0[(role, r)] = list(dict.fromkeys(lst))
            P["P0"] = {k: list(v) for k, v in nets0.items()}
            notes = {"P0": ["mk4 as it stands (list names resolved to scored columns; duplicates collapsed)"],
                     "P1": [], "P2": [], "P3": []}
            P["P1"] = {}
            for (role, r), lst in nets0.items():
                keep, seen = [], {}
                for f in sorted(lst, key=lambda f: -np.nan_to_num(W.loc[(f, r)].D_comb_equal, nan=-1)):
                    y = W.loc[(f, r)]
                    if not separates(y.D_comb_equal, y.Dcrit_comb_equal):
                        notes["P1"].append(f"{role} {r}: drop {f} (D {y.D_comb_equal:.3f}, weak or dead)")
                        continue
                    bk = block_of.get((f, r))
                    if bk in seen:
                        notes["P1"].append(f"{role} {r}: drop {f} (same block as {seen[bk]}, |rho| >= {CORR_BLOCK})")
                        continue
                    seen[bk] = f
                    keep.append(f)
                P["P1"][(role, r)] = keep
            for r in ("endcap", "barrel"):
                shared = {block_of.get((f, r)) for f in P["P1"][("NN1", r)]} & \
                         {block_of.get((f, r)) for f in P["P1"][("NN2", r)]}
                for bk in shared:
                    notes["P1"].append(f"NOTE {r}: block {bk} appears in BOTH nets "
                                       f"({cblocks[r][bk - 1][0]}) -- shared information between NN1 and NN2")
            P["P2"] = {k: list(v) for k, v in P["P1"].items()}
            for r in ("endcap", "barrel"):
                taken = {block_of.get((f, r)) for role in ("NN1", "NN2") for f in P["P1"][(role, r)]}
                for f in pools[r]:
                    y = W.loc[(f, r)]
                    if y.D_comb_equal < STRONG_D or block_of.get((f, r)) in taken:
                        continue
                    c = {role: max([abs(np.nan_to_num(rho[r].at[f, g])) for g in P["P2"][(role, r)]
                                    if g in rho[r].index] or [0]) for role in ("NN1", "NN2")}
                    role = "NN1" if c["NN1"] >= c["NN2"] else "NN2"
                    P["P2"][(role, r)].append(f)
                    taken.add(block_of.get((f, r)))
                    notes["P2"].append(f"{r}: add {f} to {role} (D {y.D_comb_equal:.3f}; max |rho| NN1 {c['NN1']:.2f}, "
                                       f"NN2 {c['NN2']:.2f} -> joins the net it already correlates with)")
            P["P3"] = {}
            for role in ("NN1", "NN2"):
                P["P3"][(role, "inclusive")] = list(dict.fromkeys(P["P1"][(role, "endcap")] + P["P1"][(role, "barrel")]))
            notes["P3"] = ["inclusive: one net per role trained on BOTH regions with a region flag input;",
                           "features = union of P1 endcap and P1 barrel (region-tagged columns are missing outside",
                           "their region; the surrogate handles missing values natively). Scored per region."]
            desc = {"P0": "mk4 as is", "P1": "mk4 minus weak/dead/redundant",
                    "P2": "P1 + strong unused (non-HTmiss) features", "P3": "inclusive P1 with region flag"}
            # event matrix over all files
            files = list(dfs)
            y_all = np.concatenate([np.full(len(dfs[k]), 0 if k == "bkg" else 1) for k in files])
            mass_all = np.concatenate([np.full(len(dfs[k]), k) for k in files])
            regm = {r: np.concatenate([rmask[k][r] for k in files]) for r in regions}
            flag_all = regm["barrel"].astype(float)

            def X_of(fs, extra_flag=False):
                cols = []
                for f in fs:
                    x = np.concatenate([num[k][f] for k in files]).copy()
                    x[(~np.isfinite(x)) | (x == SENTINEL)] = np.nan
                    cols.append(x)
                if extra_flag:
                    cols.append(flag_all)
                return np.column_stack(cols) if cols else np.zeros((len(y_all), 0))

            res_rows, score_store = [], {}
            jobs = [(p, r) for p in ("P0", "P1", "P2") for r in ("endcap", "barrel")] + [("P3", "inclusive")]
            for ji, (p, r) in enumerate(jobs, 1):
                sel = regm["all"] if r == "inclusive" else regm[r]
                for role in ("NN1", "NN2"):
                    fs = P[p][(role, r)]
                    if not fs:
                        continue
                    X = X_of(fs, extra_flag=(r == "inclusive"))[sel]
                    y, mass = y_all[sel], mass_all[sel]
                    wts = event_weights(y, mass)
                    strat = np.where(y == 1, mass, "bkg")
                    log(f"  [{ji}/{len(jobs)}] {p} {r} {role}: {X.shape[1]} features, {len(y):,} events")
                    s = np.full(len(y_all), np.nan)
                    s[sel] = oof_scores(X, y, wts, strat, f"{p} {r} {role}")
                    score_store[(p, r, role)] = s
            for (p, r) in jobs:
                for ev in (["endcap", "barrel"] if r == "inclusive" else [r]):
                    row = {"prototype": p, "trained_on": r, "evaluated_in": ev,
                           "n_NN1": len(P[p].get(("NN1", r), [])), "n_NN2": len(P[p].get(("NN2", r), []))}
                    m = regm[ev]
                    for role in ("NN1", "NN2"):
                        s = score_store.get((p, r, role))
                        if s is None:
                            continue
                        y, mass, sc = y_all[m], mass_all[m], s[m]
                        row[f"AUC_{role}"] = AUC(y, sc, sample_weight=event_weights(y, mass))
                        per = {}
                        for mm in MASS_FILES:
                            k = (mass == mm) | (y == 0)
                            per[mm] = AUC(y[k], sc[k]) if (y[k] == 1).any() else np.nan
                        row[f"AUCmin_{role}"] = np.nanmin(list(per.values()))
                        row |= {f"AUC_{role}_{short(mm)}": v for mm, v in per.items()}
                    s1, s2 = score_store.get((p, r, "NN1")), score_store.get((p, r, "NN2"))
                    if s1 is not None and s2 is not None:
                        bidx = np.flatnonzero(m & (y_all == 0))
                        if len(bidx) > DCOR_N:
                            bidx = rng.choice(bidx, DCOR_N, replace=False)
                        row["dCor_bkg"] = dcor(s1[bidx], s2[bidx])
                        row["spearman_bkg"] = pd.Series(s1[bidx]).corr(pd.Series(s2[bidx]), method="spearman")
                    res_rows.append(row)
            res = pd.DataFrame(res_rows)
            res.to_csv(dirs["D"] / "prototype_scores.csv", index=False)
            for p in P:
                nets = {f"{role} {r}": fs for (role, r), fs in P[p].items()}
                txt = proto_txt(p, desc[p], nets)
                (dirs["D"] / f"{p}.txt").write_text(txt, encoding="utf-8")
                (dirs["G"] / "prototypes").mkdir(exist_ok=True)
                (dirs["G"] / "prototypes" / f"{p}.txt").write_text(txt, encoding="utf-8")
            T = [f"{'proto':<5} {'trained':<9} {'eval':<7} {'nNN1':>4} {'nNN2':>4}  {'AUC1':>6} {'min1':>6}  "
                 f"{'AUC2':>6} {'min2':>6}  {'dCor':>6} {'rho':>6}", "-" * 82]
            for y in res.itertuples(index=False):
                g = lambda k: getattr(y, k, np.nan)
                T.append(f"{y.prototype:<5} {y.trained_on:<9} {y.evaluated_in:<7} {y.n_NN1:>4} {y.n_NN2:>4}  "
                         f"{g('AUC_NN1'):6.3f} {g('AUCmin_NN1'):6.3f}  {g('AUC_NN2'):6.3f} {g('AUCmin_NN2'):6.3f}  "
                         f"{g('dCor_bkg'):6.3f} {g('spearman_bkg'):+6.3f}")
            T += ["", "AUC = cross-validated (5-fold, out-of-fold) AUC of a gradient-boosted surrogate,",
                  "      signal mass points weighted equally; min = worst single mass point vs background.",
                  "dCor / rho = dependence between the NN1 and NN2 surrogate scores on background (0 = independent).",
                  "Barrel-only vs inclusive: compare P1 trained=barrel with P3 trained=inclusive, eval=barrel.",
                  "The surrogate nominates; it does not crown. Final placement is GAMBIT's (closure and G)."]
            print("\n".join(T), flush=True)
            pages = [("t", f) for f in text_pages(f"D · prototype NNs · round {R}", T, R, size=7.2)]
            for p in P:
                L = [f"{p}: {desc[p]}", ""]
                for (role, r), fs in P[p].items():
                    L.append(f"{role} {r}  ({len(fs)})")
                    for f in fs:
                        ev = "endcap" if r == "inclusive" and (f, "endcap") in W.index else r
                        ev = ev if ev != "inclusive" else "all"
                        y = W.loc[(f, ev)]
                        L.append(f"   {f:<40} D_{ev} {y.D_comb_equal:6.3f}   block {block_of.get((f, ev), '-')}")
                    L.append("")
                L += ["changes:"] + [f"  {n}" for n in notes[p]]
                pages += [("t", f) for f in text_pages(f"D · {p} · {desc[p]}", L, R, size=6.8, per_page=60)]
            save_pdf(dirs["D"] / "D_SUMMARY.pdf", pages, f"{SCRIPT_TAG} round {R} D summary")

    log(f"DONE -> {OUT}")


if __name__ == "__main__":
    main()
