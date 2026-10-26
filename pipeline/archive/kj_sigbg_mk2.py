#!/usr/bin/env python
"""
kj_sigbg_mk2.py  --  signal/background separation on Prof. Johns' Sep-21-26 drop,
                     two selections side by side, one PDF per feature.

Selections (both run every time)
  all   every event in each file
  <cut> PRESEL cuts (AND-ed), applied to signal AND background before the region split
        (default htmiss_NOSYS >= 40 GeV -> label "ht40"; units auto-detected per variable)
        Output folder carries the label: out_sigbg_mk2_r<N>_<label>/
  Plus a background-only check per region: background below the cut vs at/above it.
  Signal has no events below the cut, so there is no "below" signal-vs-background page.

Per feature, per region (endcap / barrel / all), one PDF in features/NNN_<feature>/:
  page 1            overview: every KS D for this feature, all regions and selections
  per region, 3 pages, each with a banner (feature name, region, selection, rank, D):
    [all]    2x2  each mass vs bkg (raw | normalized), combined vs bkg (raw | normalized)
    [htXX]   2x2  same, after the cut
    [bkg]    1x2  background below vs at/above the cut (raw | normalized)
  -> 10 pages, 30 panels per feature with all three regions.
  All pages of one feature and region share the same x binning, so all vs htXX compare directly.
  Folders are numbered by rank (RANK_BY, default endcap / htXX / combined equal-weight D).

Score: two-sample KS  D = sup_x |F_s(x) - F_b(x)|. Larger = more separation. No p-values.

Feature pool: common to all 7 files; HARD_EXCLUDE; exclude_features.txt; non-numeric dropped;
  rank-identical columns (same missing pattern, monotone-equivalent values) collapsed to one
  representative (duplicates.txt lists the copies);
  features constant inside a region/selection cell get no page there (noted on the overview).

Output: out_sigbg_mk2_r<N>/  SUMMARY.pdf, selection_report.txt, ks_scores_long.csv,
  ks_scores_wide.csv, compare_all_vs_htXX.csv, bkg_split.csv, duplicates.txt,
  feature_inventory.txt, excluded_report.txt, region_audit.txt, features/.

Read-only on the data. Real data only.
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
OUT = HERE / "out_sigbg_mk2_r1"      # reset from --round in main()
EXCLUDE_FILE = HERE / "exclude_features.txt"

BKG_FILE = "DataHTMissLow_train_data24_cleaned.csv"
MASS_FILES = {                       # label -> file   (order = fixed color slot)
    "mH125_mS15":   "HSS_mH125_mS15_ct580_cleaned.csv",
    "mH125_mS55":   "HSS_mH125_mS55_ct5320_cleaned.csv",
    "mH200_mS50":   "HSS_mH200_mS50_ct1255_cleaned.csv",
    "mH400_mS100":  "HSS_mH400_mS100_ct1610_cleaned.csv",
    "mH600_mS150":  "HSS_mH600_mS150_ct3310_cleaned.csv",
    "mH1000_mS275": "HSS_mH1000_mS275_ct2399_cleaned.csv",
}

PRESEL = "htmiss_NOSYS>=40"          # cuts in GeV, AND-ed, comma-separated; --presel overrides
                                     # e.g. "htmiss_NOSYS>=40,met_met_NOSYS>=20"
PRESEL_UNITS = "auto"                # "auto" | "MeV" | "GeV"  (auto: per variable, signal median > 1000 -> MeV)
SHORT = {"htmiss_NOSYS": "ht", "htmissScalar_NOSYS": "htsc", "met_met_NOSYS": "met",
         "jet_pt_max_NOSYS": "jpt"}  # short names for the selection label
EDGE_VARS = ["htmissScalar_NOSYS", "htmiss_NOSYS", "met_met_NOSYS", "jet_pt_max_NOSYS"]
RANK_BY = ("endcap", "ht")           # (region, "all" | "ht") cell whose D_comb_equal orders the folders

SENTINEL = -999.0
MIN_N = 20                           # fewer events than this in a cell -> D = NaN
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
BAND = {"all": "#cde2fb", "ht": "#f9d8c8", "bkg": "#e6e5df"}   # banner tint per page kind
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



# ---------------------------------------------------------------- selection
def parse_presel(spec):
    cuts = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.fullmatch(r"([^<>=\s]+)\s*>=\s*([0-9.]+)", part)
        if not m:
            sys.exit(f"bad --presel term '{part}' (use  var>=GeV, comma-separated)")
        cuts.append((m.group(1), float(m.group(2))))
    label = "_".join(f"{SHORT.get(v, re.sub(r'[^A-Za-z0-9]', '', v))}{g:g}" for v, g in cuts)
    return cuts, label


def presel_setup(dfs, cuts, units):
    """Resolve units per cut variable from the data. Returns ([(var, thr_file_units, scale)], lines)."""
    L, resolved = [], []
    for var, gev in cuts:
        if any(var not in d.columns for d in dfs.values()):
            cand = sorted({c for d in dfs.values() for c in d.columns if re.search(r"htmiss|met_|jet_pt", c, re.I)})
            sys.exit(f"cut variable '{var}' is not in every file. Candidates: {cand}")
        sig = np.concatenate([clean(dfs[m][var])[0] for m in MASS_FILES])
        med = float(np.median(sig)) if len(sig) else np.nan
        u = units if units != "auto" else ("MeV" if med > 1000 else "GeV")
        scale = 1000.0 if u == "MeV" else 1.0
        resolved.append((var, gev * scale, scale))
        L.append(f"cut            {var} >= {gev:g} GeV  =  {gev * scale:g} file units  "
                 f"(units {u}; signal median {med:,.1f} file units)")
    scale0 = resolved[0][2]
    cutvars = {v for v, _ in cuts}
    L += ["", f"per-file edges, in GeV (file units / {scale0:g}):",
          f"  {'file':<13} {'variable':<20} {'min':>9} {'q0.1%':>9} {'q1%':>9} {'median':>9}  {'% < cut':>8}"]
    for v in list(dict.fromkeys(EDGE_VARS + [c for c, _ in cuts])):
        if any(v not in d.columns for d in dfs.values()):
            L.append(f"  (skipped {v}: not in every file)")
            continue
        g = dict(cuts).get(v)
        for k, d in dfs.items():
            x = clean(d[v])[0] / scale0
            if len(x) == 0:
                L.append(f"  {k:<13} {v:<20}  (no valid values)")
                continue
            below = f"{np.mean(x < g):8.2%}" if v in cutvars else ""
            L.append(f"  {k:<13} {v:<20} {x.min():9.2f} {np.quantile(x, .001):9.2f} "
                     f"{np.quantile(x, .01):9.2f} {np.median(x):9.2f}  {below:>8}")
        L.append("")
    return resolved, L


def sel_masks(df, resolved):
    n = len(df)
    ok, ht = np.ones(n, bool), np.ones(n, bool)
    for var, thr, _ in resolved:
        v = pd.to_numeric(df[var], errors="coerce").to_numpy(float)
        good = np.isfinite(v) & (v != SENTINEL)
        ok &= good
        ht &= good & (v >= thr)
    return {"all": np.ones(n, bool), "ht": ht, "lo": ok & ~ht, "ok": ok}


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

    def pref(name):  # keep: no _raw, no region tag, shortest, alphabetical
        return ("_raw" in name, bool(re.search(r"barrel|endcap", name, re.I)), len(name), name)

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


def sig_page(feat, region, sel_label, sel_desc, kind, e, b, ms, sc, rank, n_rank, nsig):
    plt = _plt()
    fig = plt.figure(figsize=(11, 8.5))
    md = {m: sc[m] for m in MASS_FILES}
    fin = {m: d for m, d in md.items() if np.isfinite(d)}
    mn = min(fin, key=fin.get) if fin else None
    mx = max(fin, key=fin.get) if fin else None
    banner(fig, feat,
           f"region: {region.upper()}   ·   selection: {sel_label}  ({sel_desc})   ·   rank {rank} / {n_rank}",
           f"D_equal {sc['comb_equal']:.3f}   D_pooled {sc['comb_pooled']:.3f}   "
           + (f"min {fin[mn]:.3f} ({mn})   max {fin[mx]:.3f} ({mx})   " if fin else "")
           + f"bkg n = {len(b):,}   sig n = {nsig:,}", kind)
    gs = fig.add_gridspec(2, 2, top=0.845, bottom=0.07, left=0.065, right=0.985, hspace=0.38, wspace=0.17)
    ctr = 0.5 * (e[:-1] + e[1:])
    comb = np.concatenate(list(ms.values()))
    cw = np.concatenate([np.full(len(x), 1.0 / len(x)) for x in ms.values() if len(x)]) if len(comb) else None
    for col, norm in ((0, False), (1, True)):
        ylab, mode = ("fraction per bin", "normalized") if norm else ("events", "raw")
        a = fig.add_subplot(gs[0, col])
        fill_bkg(a, ctr, e, b, norm, f"background (n={len(b):,})")
        for i, (m, x) in enumerate(ms.items()):
            if len(x):
                a.step(ctr, _y(hist(x, e), e, norm), where="mid", color=SLOT[i], lw=2,
                       label=f"{m}  D={sc[m]:.3f}  (n={len(x):,})")
        style(a, f"each mass point vs background · {mode}", ylab, feat, log=not norm)
        a.legend(fontsize=6.5, frameon=False, labelcolor=INK)
        a = fig.add_subplot(gs[1, col])
        fill_bkg(a, ctr, e, b, norm, f"background (n={len(b):,})")
        if len(comb):
            a.step(ctr, _y(hist(comb, e), e, norm), where="mid", color=SLOT[6], lw=2,
                   label=f"combined, pooled  D={sc['comb_pooled']:.3f}  (n={len(comb):,})")
            hw = hist(comb, e, cw)
            yw = _y(hw, e, True) if norm else hw * (len(comb) / hw.sum() if hw.sum() else 1)
            a.step(ctr, yw, where="mid", color=SLOT[7], lw=2, ls="--",
                   label=f"combined, equal weight per mass  D={sc['comb_equal']:.3f}")
        style(a, f"combined signal vs background · {mode}", ylab, feat, log=not norm)
        a.legend(fontsize=6.5, frameon=False, labelcolor=INK)
    fig.text(0.985, 0.012, "edge bins include under/overflow · NaN and -999 removed", fontsize=6.5,
             color=INK2, ha="right")
    return fig


def split_page(feat, region, cut_desc, e, lo, hi, d, rank, n_rank):
    plt = _plt()
    fig = plt.figure(figsize=(11, 8.5))
    banner(fig, feat,
           f"region: {region.upper()}   ·   background only: below vs at/above the cut  ({cut_desc})   ·   "
           f"rank {rank} / {n_rank}",
           f"D(below vs above) {d:.3f}   n below = {len(lo):,}   n above = {len(hi):,}   "
           "large D = background shape changes across the cut", "bkg")
    gs = fig.add_gridspec(1, 2, top=0.80, bottom=0.12, left=0.065, right=0.985, wspace=0.17)
    ctr = 0.5 * (e[:-1] + e[1:])
    for col, norm in ((0, False), (1, True)):
        a = fig.add_subplot(gs[0, col])
        if len(lo):
            fill_bkg(a, ctr, e, lo, norm, f"background below cut (n={len(lo):,})")
        if len(hi):
            a.step(ctr, _y(hist(hi, e), e, norm), where="mid", color=INK, lw=2,
                   label=f"background at/above cut (n={len(hi):,})")
        style(a, f"background below vs at/above · {'normalized' if norm else 'raw'}",
              "fraction per bin" if norm else "events", feat, log=not norm)
        a.legend(fontsize=7, frameon=False, labelcolor=INK)
    return fig


def text_pages(title, lines, rnd, per_page=52, size=7.3, kind=None, feat=None):
    plt = _plt()
    figs = []
    chunks = [lines[i:i + per_page] for i in range(0, max(len(lines), 1), per_page)] or [[]]
    for j, ch in enumerate(chunks, 1):
        fig = plt.figure(figsize=(11, 8.5))
        if feat:
            banner(fig, feat, title, f"page {j}/{len(chunks)}", kind or "bkg")
            y0 = 0.86
        else:
            fig.text(0.04, 0.955, title + (f"  ({j}/{len(chunks)})" if len(chunks) > 1 else ""),
                     fontsize=14, color=INK, va="top")
            y0 = 0.905
        fig.text(0.04, y0, "\n".join(ch), fontsize=size, color=INK, va="top", family="monospace",
                 linespacing=1.33)
        fig.text(0.96, 0.015, f"kj_sigbg_mk2 · round {rnd}", fontsize=7, color=INK2, ha="right")
        figs.append(fig)
    return figs


def table_lines(df, top=40):
    d = df.set_index("feature").loc[rank_order(df)].reset_index().head(top)
    if d.empty:
        return ["(no features)"]
    w = max([len("feature")] + [len(f) for f in d["feature"]])
    hdr = f"{'#':>3}  {'feature':<{w}}  {'D_equal':>7}  {'D_pooled':>8}  {'D_min':>6}  {'D_max':>6}  {'n_bkg':>7}"
    out = [hdr, "-" * len(hdr)]
    for i, r in enumerate(d.itertuples(index=False), 1):
        out.append(f"{i:>3}  {r.feature:<{w}}  {r.D_comb_equal:7.3f}  {r.D_comb_pooled:8.3f}  "
                   f"{r.D_mass_min:6.3f}  {r.D_mass_max:6.3f}  {r.n_bkg:7,}")
    return out


def ranking_fig(df, title, top=40):
    plt = _plt()
    d = df.set_index("feature").loc[rank_order(df)].reset_index().head(top)
    d = d[np.isfinite(d["D_comb_equal"])]
    if d.empty:
        return None
    fig, a = plt.subplots(figsize=(11, 8.5), constrained_layout=True)
    a.barh(d["feature"][::-1], d["D_comb_equal"][::-1], color=SLOT[0], height=0.7)
    for y, v in enumerate(d["D_comb_equal"][::-1]):
        a.text(v + 0.005, y, f"{v:.3f}", va="center", fontsize=7, color=INK2)
    a.set_xlabel("KS D, combined signal (equal weight per mass) vs background", fontsize=9, color=INK2)
    a.set_title(title, fontsize=11, color=INK, loc="left")
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
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--regions", default="endcap,barrel,all")
    ap.add_argument("--presel", default=PRESEL, help='e.g. "htmiss_NOSYS>=40,met_met_NOSYS>=20" (GeV)')
    ap.add_argument("--units", default=PRESEL_UNITS, choices=["auto", "MeV", "GeV"])
    ap.add_argument("--inventory-only", action="store_true")
    ap.add_argument("--no-plots", action="store_true", help="scores, reports and SUMMARY.pdf only")
    ap.add_argument("--top", type=int, default=0, help="per-feature PDFs for the top N only (0 = all)")
    ap.add_argument("--png", action="store_true", help="also write one PNG per page")
    ap.add_argument("--no-dedup", action="store_true")
    args = ap.parse_args()
    R = args.round
    cuts, HT = parse_presel(args.presel)
    OUT = HERE / f"out_sigbg_mk2_r{R}_{HT}"
    OUT.mkdir(exist_ok=True)
    SEL = {"all": "all", "ht": HT}
    log(f"round {R} -> {OUT}")

    dfs = load()
    pats = read_exclude_file()
    feats, rep, all7 = feature_pool(dfs, pats)
    with open(OUT / "excluded_report.txt", "w", encoding="utf-8") as fh:
        for k, v in rep.items():
            fh.write(f"===== {k} ({len(v)}) =====\n" + "\n".join(v) + "\n\n")
    inventory(dfs, rep, pats)
    if args.inventory_only:
        log("--inventory-only: done")
        return

    # ---- selection
    resolved, sel_lines = presel_setup(dfs, cuts, args.units)
    cut_desc = " AND ".join(f"{v} >= {g:g} GeV" for v, g in cuts) + ", signal and background"
    cutvars = {v for v, _ in cuts}
    chosen, audit = find_region(all7, dfs)
    (OUT / "region_audit.txt").write_text(audit, encoding="utf-8")
    rmask = {k: region_masks(df, chosen) for k, df in dfs.items()}
    smask = {k: sel_masks(df, resolved) for k, df in dfs.items()}
    regions = [r for r in args.regions.split(",") if r in rmask["bkg"]]
    sel_lines += ["events per file and region, before and after the cut:",
                  f"  {'file':<13} {'region':<7} {'all':>8} {HT:>8} {'kept':>7} {'below':>8} {'invalid':>7}"]
    warn = []
    for k in dfs:
        for r in regions:
            m = rmask[k][r]
            na, nh = int(m.sum()), int((m & smask[k]["ht"]).sum())
            nlo, nbad = int((m & smask[k]["lo"]).sum()), int((m & ~smask[k]["ok"]).sum())
            sel_lines.append(f"  {k:<13} {r:<7} {na:>8,} {nh:>8,} {nh / na if na else 0:7.1%} {nlo:>8,} {nbad:>7,}")
            if k != "bkg" and r == "all" and na and nh / na < 0.99:
                warn.append(f"WARNING: {k} keeps only {nh / na:.1%} after the cut -- signal is not fully above it")
    sel_lines += [""] + (warn or ["all signal files keep >= 99% of events after the cut"])
    (OUT / "selection_report.txt").write_text("\n".join(sel_lines) + "\n", encoding="utf-8")
    print("\n".join(sel_lines), flush=True)
    log(f"region: {chosen}")

    # ---- numeric cache + dedup
    num = {k: df[feats].apply(pd.to_numeric, errors="coerce").to_numpy(float) for k, df in dfs.items()}
    num = {k: {f: v[:, i] for i, f in enumerate(feats)} for k, v in num.items()}
    copies = {}
    if not args.no_dedup:
        feats, copies = dedup(num, feats)
    dup_lines = [f"{len(copies)} groups of rank-identical columns (same missing pattern, same value",
                 "ordering in every file -> same KS D everywhere); kept the first name, dropped the rest", ""]
    for kf, cs in sorted(copies.items()):
        dup_lines.append(f"{kf}")
        dup_lines += [f"    = {c}" for c in cs]
    (OUT / "duplicates.txt").write_text("\n".join(dup_lines) + "\n", encoding="utf-8")
    n_drop = sum(len(v) for v in copies.values())
    log(f"dedup: {n_drop} duplicate columns dropped in {len(copies)} groups -> {len(feats)} features")

    def cell(k, f, r, s):
        return clean(num[k][f][rmask[k][r] & smask[k][s]])

    # ---- scoring
    long_rows, wide_rows, split_rows, const = [], [], [], {}
    cells = [(r, s) for r in regions for s in SEL]
    for ci, (r, s) in enumerate(cells, 1):
        log(f"[{ci}/{len(cells)}] scoring {r} / {SEL[s]}")
        for i, f in enumerate(feats, 1):
            b, bnan, bsen = cell("bkg", f, r, s)
            ms = {m: cell(m, f, r, s)[0] for m in MASS_FILES}
            sc = score_cell(b, ms)
            if sc is None:
                const.setdefault(f, []).append(f"{r}/{SEL[s]}")
                sc = {m: np.nan for m in MASS_FILES} | {"comb_pooled": np.nan, "comb_equal": np.nan}
            for m in MASS_FILES:
                long_rows.append({"round": R, "selection": SEL[s], "region": r, "feature": f, "comparison": m,
                                  "D": sc[m], "n_sig": len(ms[m]), "n_bkg": len(b)})
            for c in ("comb_pooled", "comb_equal"):
                long_rows.append({"round": R, "selection": SEL[s], "region": r, "feature": f, "comparison": c,
                                  "D": sc[c], "n_sig": sum(len(x) for x in ms.values()), "n_bkg": len(b)})
            md = [sc[m] for m in MASS_FILES]
            fin = np.isfinite(md).any()
            wide_rows.append({"round": R, "selection": SEL[s], "region": r, "feature": f,
                              **{f"D_{m}": sc[m] for m in MASS_FILES},
                              "D_comb_pooled": sc["comb_pooled"], "D_comb_equal": sc["comb_equal"],
                              "D_mass_min": np.nanmin(md) if fin else np.nan,
                              "D_mass_max": np.nanmax(md) if fin else np.nan,
                              "bkg_nan_frac": bnan, "bkg_m999_frac": bsen, "n_bkg": len(b),
                              "n_sig": sum(len(x) for x in ms.values())})
            bar(i, len(feats), f)
    for r in regions:
        for f in feats:
            lo = clean(num["bkg"][f][rmask["bkg"][r] & smask["bkg"]["lo"]])[0]
            hi = clean(num["bkg"][f][rmask["bkg"][r] & smask["bkg"]["ht"]])[0]
            d = ks_w(lo, np.ones(len(lo)), hi, np.ones(len(hi))) if np.unique(np.r_[lo, hi]).size > 1 else np.nan
            split_rows.append({"round": R, "region": r, "feature": f, "D_bkg_split": d,
                               "n_bkg_below": len(lo), "n_bkg_above": len(hi)})

    wide = pd.DataFrame(wide_rows)
    split = pd.DataFrame(split_rows)
    pd.DataFrame(long_rows).to_csv(OUT / "ks_scores_long.csv", index=False)
    wide.to_csv(OUT / "ks_scores_wide.csv", index=False)
    split.to_csv(OUT / "bkg_split.csv", index=False)
    a = wide[wide.selection == "all"].set_index(["region", "feature"])
    h = wide[wide.selection == HT].set_index(["region", "feature"])
    cmp_ = pd.DataFrame({"D_all": a["D_comb_equal"], f"D_{HT}": h["D_comb_equal"],
                         "n_bkg_all": a["n_bkg"], f"n_bkg_{HT}": h["n_bkg"]})
    cmp_["delta"] = cmp_[f"D_{HT}"] - cmp_["D_all"]
    cmp_ = cmp_.join(split.set_index(["region", "feature"])[["D_bkg_split"]]).reset_index()
    cmp_ = cmp_.sort_values(["region", "delta"], kind="mergesort")
    cmp_.to_csv(OUT / f"compare_all_vs_{HT}.csv", index=False)
    log(f"wrote ks_scores_long.csv, ks_scores_wide.csv, bkg_split.csv, compare_all_vs_{HT}.csv")

    # ---- ranking that numbers the folders
    rr, rs = RANK_BY
    rr = rr if rr in regions else regions[0]
    order = rank_order(wide[(wide.region == rr) & (wide.selection == SEL[rs])])
    rank = {f: i for i, f in enumerate(order, 1)}
    rank_desc = f"{rr} / {SEL[rs]} / D_equal"

    # ---- console summary
    for r in regions:
        for s in SEL:
            t = wide[(wide.region == r) & (wide.selection == SEL[s])]
            t = t.set_index("feature").loc[rank_order(t)].reset_index().head(10)
            log(f"top 10 [{r} / {SEL[s]}]:\n" + t[["feature", "D_comb_equal", "D_mass_min", "D_mass_max",
                                                  "n_bkg"]].to_string(index=False))
        c = cmp_[cmp_.region == r].head(10)
        log(f"largest drops all -> {HT} [{r}]:\n" + c[["feature", "D_all", f"D_{HT}", "delta",
                                                      "D_bkg_split"]].to_string(index=False))

    plt = _plt()
    from matplotlib.backends.backend_pdf import PdfPages

    # ---- SUMMARY.pdf
    cover = [
        f"date         {time.strftime('%Y-%m-%d %H:%M')}",
        f"data         {DATA}",
        f"background   {BKG_FILE}  rows {len(dfs['bkg']):,}",
        *[f"signal       {fn}  rows {len(dfs[m]):,}" for m, fn in MASS_FILES.items()],
        "",
        f"selections   all  = every event",
        f"             {HT:<4} = {cut_desc}",
        f"region       {chosen}",
        "",
        f"features common to all 7 files   {len(all7)}",
        f"hard / user excluded             {len(rep['hard'])} / {len(rep['user'])}",
        f"non-numeric / constant overall   {len(rep['non_numeric'])} / {len(rep['constant'])}",
        f"rank-identical duplicates dropped {n_drop}  (in {len(copies)} groups; duplicates.txt)",
        f"features scored                  {len(feats)}",
        f"constant in >= 1 cell            {len(const)}  (no page in those cells)",
        "",
        "metric   two-sample KS D, unweighted events, NaN and -999 removed per feature.",
        "         D_equal weights each mass point 1/N_m; D_pooled concatenates them.",
        f"folders  features/NNN_<feature>/, NNN = rank by {rank_desc}",
        "",
        "this PDF: cover, selection report, then per selection and region a ranking chart and",
        f"top-40 table, then per region the 40 largest drops from all to {HT}.",
    ]
    with PdfPages(OUT / "SUMMARY.pdf") as pdf:
        for fig in text_pages(f"Signal/background separation · mk2 · round {R}", cover, R, size=8.5):
            pdf.savefig(fig); plt.close(fig)
        for fig in text_pages("Selection report", sel_lines, R, size=6.8, per_page=62):
            pdf.savefig(fig); plt.close(fig)
        for s in SEL:
            for r in regions:
                t = wide[(wide.region == r) & (wide.selection == SEL[s])]
                fig = ranking_fig(t, f"Top 40 · region {r.upper()} · selection {SEL[s]}")
                if fig is not None:
                    pdf.savefig(fig); plt.close(fig)
                for fig in text_pages(f"Top 40 table · region {r.upper()} · selection {SEL[s]}",
                                      table_lines(t), R):
                    pdf.savefig(fig); plt.close(fig)
        for r in regions:
            c = cmp_[cmp_.region == r].head(40)
            w = max([7] + [len(x) for x in c.feature])
            L = [f"{'feature':<{w}}  {'D_all':>6}  {'D_'+HT:>8}  {'delta':>7}  {'D_split':>7}",
                 "-" * (w + 36)]
            L += [f"{x.feature:<{w}}  {x.D_all:6.3f}  {x[2]:8.3f}  {x.delta:7.3f}  {x.D_bkg_split:7.3f}"
                  for x in c[["feature", "D_all", f"D_{HT}", "delta", "D_bkg_split"]].itertuples(index=False)]
            L += ["", f"delta = D_{HT} - D_all.  Large negative: the separation came from events the cut removes.",
                  "D_split = background below vs at/above the cut (shape change across the cut)."]
            for fig in text_pages(f"Largest drops all -> {HT} · region {r.upper()}", L, R):
                pdf.savefig(fig); plt.close(fig)
        pdf.infodict()["Title"] = f"kj_sigbg_mk2 round {R} summary"
    log("wrote SUMMARY.pdf")
    if args.no_plots:
        log(f"--no-plots: done -> {OUT}")
        return

    # ---- per-feature folders
    todo = order[:args.top] if args.top else order
    froot = OUT / "features"
    froot.mkdir(exist_ok=True)
    W = wide.set_index(["feature", "region", "selection"])
    S = split.set_index(["feature", "region"])
    log(f"writing {len(todo)} feature PDFs (~{1 + 3 * len(regions)} pages each) -> {froot}")
    for fi, f in enumerate(todo, 1):
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f)
        fdir = froot / f"{rank[f]:03d}_{safe}"
        fdir.mkdir(exist_ok=True)
        pages = []
        # overview
        L = [f"rank {rank[f]} / {len(order)}  by {rank_desc}", ""]
        if f in cutvars:
            L += ["NOTE: this is the cut variable; its D in the cut selection is shaped by the cut itself.", ""]
        if f in copies:
            L += ["identical columns dropped in favour of this one:"] + [f"    {c}" for c in copies[f]] + [""]
        if f in const:
            L += ["constant (no page) in: " + ", ".join(const[f]), ""]
        hdr = f"{'region':<7} {'selection':<9} {'D_equal':>7} {'D_pooled':>8} " + \
              " ".join(f"{m.replace('mH', '').replace('_mS', '/'):>8}" for m in MASS_FILES) + f" {'n_bkg':>7}"
        L += [hdr, "-" * len(hdr)]
        for r in regions:
            for s in SEL:
                x = W.loc[(f, r, SEL[s])]
                L.append(f"{r:<7} {SEL[s]:<9} {x.D_comb_equal:7.3f} {x.D_comb_pooled:8.3f} "
                         + " ".join(f"{x['D_' + m]:8.3f}" for m in MASS_FILES) + f" {int(x.n_bkg):7,}")
            y = S.loc[(f, r)]
            L.append(f"{r:<7} {'bkg split':<9} {y.D_bkg_split:7.3f}   below {int(y.n_bkg_below):,} / "
                     f"above {int(y.n_bkg_above):,}")
            L.append("")
        L += [f"selections: all = every event;  {HT} = {cut_desc}",
              "pages: per region -> [all] 2x2, [" + HT + "] 2x2, [background below vs above] 1x2"]
        pages += [("p00_overview", fig) for fig in text_pages(
            f"overview  ·  all regions and selections  ·  rank {rank[f]} / {len(order)}", L, R, feat=f, size=8)]
        for r in regions:
            b_all = cell("bkg", f, r, "all")[0]
            c_all = np.concatenate([cell(m, f, r, "all")[0] for m in MASS_FILES])
            e = edges_for([b_all, c_all])
            if e is None:
                continue
            for s, kind in (("all", "all"), ("ht", "ht")):
                if f"{r}/{SEL[s]}" in const.get(f, []):
                    continue
                b = cell("bkg", f, r, s)[0]
                ms = {m: cell(m, f, r, s)[0] for m in MASS_FILES}
                x = W.loc[(f, r, SEL[s])]
                sc = {m: x["D_" + m] for m in MASS_FILES} | {"comb_pooled": x.D_comb_pooled,
                                                             "comb_equal": x.D_comb_equal}
                desc = "every event" if s == "all" else cut_desc
                pages.append((f"{r}_{SEL[s]}", sig_page(f, r, SEL[s], desc, kind, e, b, ms, sc, rank[f],
                                                       len(order), sum(len(v) for v in ms.values()))))
            lo = clean(num["bkg"][f][rmask["bkg"][r] & smask["bkg"]["lo"]])[0]
            hi = clean(num["bkg"][f][rmask["bkg"][r] & smask["bkg"]["ht"]])[0]
            if len(lo) or len(hi):
                pages.append((f"{r}_bkg_split", split_page(f, r, cut_desc, e, lo, hi,
                                                           S.loc[(f, r)].D_bkg_split, rank[f], len(order))))
        with PdfPages(fdir / f"{safe}.pdf") as pdf:
            for name, fig in pages:
                pdf.savefig(fig)
                if args.png:
                    (fdir / "png").mkdir(exist_ok=True)
                    fig.savefig(fdir / "png" / f"{name}.png", dpi=110)
                plt.close(fig)
            pdf.infodict()["Title"] = f"{f} - kj_sigbg_mk2 round {R}"
        bar(fi, len(todo), f)
    log(f"DONE -> {OUT}")


if __name__ == "__main__":
    main()
