#!/usr/bin/env python
"""
kj_sigbg_mk3.py  --  signal/background separation on Prof. Johns' Sep-21-26 drop.
                     One folder and one PDF per feature; NN feature-list table; HTmiss unit test.

Unit test (runs first, never stops the run)
  HTmiss selection by design: every background event htmiss_NOSYS < 40 GeV and every signal
  event htmiss_NOSYS >= 40 GeV. PASS/FLAG per file, written to unit_tests.txt and the SUMMARY cover.

Per feature, features/NNN_<feature>/<feature>.pdf:
  page 1      overview: KS D per region and mass point, noise floor, which NN lists use it
  pages 2-4   one page per region (endcap, barrel, all), banner + 3x2 grid:
                row 1  each mass point vs background      raw | normalized
                row 2  combined signal vs background      raw | normalized
                row 3  background alone                   raw | normalized
  -> 4 pages, 18 panels per feature.  Folders numbered by rank (RANK_BY, default endcap D_equal).

KS score: D = sup_x |F_s(x) - F_b(x)|  in [0, 1].  D is also the best single-cut separation:
  max over thresholds of (signal efficiency - background efficiency).
  Noise floor D_crit = 1.36 * sqrt(1/n_s + 1/n_b)  (95% level for identical distributions;
  n_s for the equal-weight combination is the effective size (sum w)^2 / sum w^2).

NN feature lists: NN_FEATURES_FILE (default nn_features_mk4.txt next to this script).
  Each name is resolved to a CSV column (exact, else region-tagged, else _raw), then through the
  duplicate map. nn_feature_scores.csv + SUMMARY pages give D in that list's region and its rank,
  plus the strongest features that neither NN uses in that region.

Feature pool: common to all 7 files; HARD_EXCLUDE; exclude_features.txt; non-numeric dropped;
  rank-identical columns (same missing pattern, monotone-equivalent values) collapsed to one
  representative (duplicates.txt). Features constant in a region get no page there.

Output: out_sigbg_mk3_r<N>/  SUMMARY.pdf, unit_tests.txt, ks_scores_long.csv, ks_scores_wide.csv,
  nn_feature_scores.csv, duplicates.txt, feature_inventory.txt, excluded_report.txt,
  region_audit.txt, features/.   Read-only on the data. Real data only.
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
OUT = HERE / "out_sigbg_mk3_r1"      # reset from --round in main()
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
        fig.text(0.96, 0.015, f"kj_sigbg_mk3 · round {rnd}", fontsize=7, color=INK2, ha="right")
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
    gs = fig.add_gridspec(3, 2, top=0.845, bottom=0.075, left=0.065, right=0.985, hspace=0.55, wspace=0.17)
    ctr = 0.5 * (e[:-1] + e[1:])
    cw = np.concatenate([np.full(len(x), 1.0 / len(x)) for x in ms.values() if len(x)]) if len(comb) else None
    for col, norm in ((0, False), (1, True)):
        ylab, mode = ("fraction per bin", "normalized") if norm else ("events", "raw")
        a = fig.add_subplot(gs[0, col])
        fill_bkg(a, ctr, e, b, norm, f"background (n={len(b):,})")
        for i, (m, x) in enumerate(ms.items()):
            if len(x):
                a.step(ctr, _y(hist(x, e), e, norm), where="mid", color=SLOT[i], lw=1.8,
                       label=f"{m}  D={sc[m]:.3f}  (n={len(x):,})")
        style(a, f"1 · each mass point vs background · {mode}", ylab, feat, log=not norm)
        a.legend(fontsize=5.8, frameon=False, labelcolor=INK)
        a = fig.add_subplot(gs[1, col])
        fill_bkg(a, ctr, e, b, norm, f"background (n={len(b):,})")
        if len(comb):
            a.step(ctr, _y(hist(comb, e), e, norm), where="mid", color=SLOT[6], lw=1.8,
                   label=f"combined, pooled  D={sc['comb_pooled']:.3f}  (n={len(comb):,})")
            hw = hist(comb, e, cw)
            yw = _y(hw, e, True) if norm else hw * (len(comb) / hw.sum() if hw.sum() else 1)
            a.step(ctr, yw, where="mid", color=SLOT[7], lw=1.8, ls="--",
                   label=f"combined, equal weight per mass  D={sc['comb_equal']:.3f}")
        style(a, f"2 · combined signal vs background · {mode}", ylab, feat, log=not norm)
        a.legend(fontsize=5.8, frameon=False, labelcolor=INK)
        a = fig.add_subplot(gs[2, col])
        fill_bkg(a, ctr, e, b, norm, f"background (n={len(b):,})")
        style(a, f"3 · background alone · {mode} · NaN {fill[0]:.1%}  −999 {fill[1]:.1%}", ylab, feat,
              log=not norm)
    fig.text(0.985, 0.006, "edge bins include under/overflow · NaN and -999 removed", fontsize=6.5,
             color=INK2, ha="right")
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


# ---------------------------------------------------------------- main
def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--regions", default="endcap,barrel,all")
    ap.add_argument("--nn-list", default=str(NN_FEATURES_FILE), help="NN feature list file")
    ap.add_argument("--inventory-only", action="store_true")
    ap.add_argument("--no-plots", action="store_true", help="scores, tables and SUMMARY.pdf only")
    ap.add_argument("--top", type=int, default=0, help="per-feature PDFs for the top N only (0 = all)")
    ap.add_argument("--png", action="store_true", help="also write one PNG per page")
    ap.add_argument("--no-dedup", action="store_true")
    args = ap.parse_args()
    R = args.round
    OUT = HERE / f"out_sigbg_mk3_r{R}"
    OUT.mkdir(exist_ok=True)
    log(f"round {R} -> {OUT}")

    dfs = load()
    pats = read_exclude_file()
    feats, rep, all7 = feature_pool(dfs, pats)
    with open(OUT / "excluded_report.txt", "w", encoding="utf-8") as fh:
        for k, v in rep.items():
            fh.write(f"===== {k} ({len(v)}) =====\n" + "\n".join(v) + "\n\n")
    inventory(dfs, rep, pats)

    ut_pass, ut_lines = unit_test_ht(dfs)
    (OUT / "unit_tests.txt").write_text("\n".join(ut_lines) + "\n", encoding="utf-8")
    print("\n".join(ut_lines), flush=True)
    if args.inventory_only:
        log("--inventory-only: done")
        return

    chosen, audit = find_region(all7, dfs)
    (OUT / "region_audit.txt").write_text(audit, encoding="utf-8")
    rmask = {k: region_masks(df, chosen) for k, df in dfs.items()}
    regions = [r for r in args.regions.split(",") if r in rmask["bkg"]]
    log(f"region: {chosen}")
    for r in regions:
        log(f"  {r:<7} bkg {rmask['bkg'][r].sum():>7,}  " +
            "  ".join(f"{m} {rmask[m][r].sum():,}" for m in MASS_FILES))

    # ---- numeric cache + dedup
    num = {k: df[feats].apply(pd.to_numeric, errors="coerce").to_numpy(float) for k, df in dfs.items()}
    num = {k: {f: v[:, i] for i, f in enumerate(feats)} for k, v in num.items()}
    copies = {}
    if not args.no_dedup:
        feats, copies = dedup(num, feats)
    rep_of = {f: f for f in feats} | {c: k for k, cs in copies.items() for c in cs}
    dup_lines = [f"{len(copies)} groups of rank-identical columns (same missing pattern, same value",
                 "ordering in every file -> same KS D everywhere); kept the first name, dropped the rest", ""]
    for kf, cs in sorted(copies.items()):
        dup_lines += [kf] + [f"    = {c}" for c in cs]
    (OUT / "duplicates.txt").write_text("\n".join(dup_lines) + "\n", encoding="utf-8")
    n_drop = sum(len(v) for v in copies.values())
    log(f"dedup: {n_drop} columns dropped in {len(copies)} groups -> {len(feats)} features")

    def cell(k, f, r):
        return clean(num[k][f][rmask[k][r]])

    # ---- NN lists
    blocks = read_nn_lists(Path(args.nn_list))
    used_in = {}                        # representative feature -> ["NN1 barrel", ...]
    nn_res = []
    for blk, names in blocks.items():
        reg = blk.split()[1]
        for nm in names:
            col, how = resolve(nm, reg, set(all7))
            rp = rep_of.get(col) if col else None
            if col and rp is None:
                how += "; excluded from scoring (see excluded_report.txt)"
            nn_res.append({"block": blk, "region": reg, "list_name": nm, "column": col, "resolved_by": how,
                           "scored_as": rp})
            if rp:
                used_in.setdefault(rp, []).append(blk)
    log(f"NN lists: {len(blocks)} blocks from {args.nn_list}" if blocks else f"NN lists: none ({args.nn_list})")

    # ---- scoring
    long_rows, wide_rows, const, fills = [], [], {}, {}
    for ci, r in enumerate(regions, 1):
        log(f"[{ci}/{len(regions)}] scoring {r}")
        for i, f in enumerate(feats, 1):
            b, bnan, bsen = cell("bkg", f, r)
            fills[(f, r)] = (bnan, bsen)
            ms = {m: cell(m, f, r)[0] for m in MASS_FILES}
            sc = score_cell(b, ms)
            if sc is None:
                const.setdefault(f, []).append(r)
                sc = {m: np.nan for m in MASS_FILES} | {"comb_pooled": np.nan, "comb_equal": np.nan}
            ns = {m: len(x) for m, x in ms.items()}
            n_pool = sum(ns.values())
            inv = [1.0 / n for n in ns.values() if n]
            n_eff = (len(inv) ** 2) / sum(inv) if inv else 0
            for m in MASS_FILES:
                long_rows.append({"round": R, "region": r, "feature": f, "comparison": m, "D": sc[m],
                                  "D_crit": dcrit(ns[m], len(b)), "n_sig": ns[m], "n_bkg": len(b)})
            long_rows.append({"round": R, "region": r, "feature": f, "comparison": "comb_pooled",
                              "D": sc["comb_pooled"], "D_crit": dcrit(n_pool, len(b)), "n_sig": n_pool,
                              "n_bkg": len(b)})
            long_rows.append({"round": R, "region": r, "feature": f, "comparison": "comb_equal",
                              "D": sc["comb_equal"], "D_crit": dcrit(n_eff, len(b)), "n_sig": n_eff,
                              "n_bkg": len(b)})
            md = [sc[m] for m in MASS_FILES]
            fin = np.isfinite(md).any()
            wide_rows.append({"round": R, "region": r, "feature": f, **{f"D_{m}": sc[m] for m in MASS_FILES},
                              "D_comb_pooled": sc["comb_pooled"], "D_comb_equal": sc["comb_equal"],
                              "Dcrit_comb_equal": dcrit(n_eff, len(b)),
                              "D_mass_min": np.nanmin(md) if fin else np.nan,
                              "D_mass_max": np.nanmax(md) if fin else np.nan,
                              "bkg_nan_frac": bnan, "bkg_m999_frac": bsen, "n_bkg": len(b), "n_sig": n_pool,
                              "nn_lists": "; ".join(used_in.get(f, []))})
            bar(i, len(feats), f)
    wide = pd.DataFrame(wide_rows)
    pd.DataFrame(long_rows).to_csv(OUT / "ks_scores_long.csv", index=False)
    wide.to_csv(OUT / "ks_scores_wide.csv", index=False)

    # ---- ranks + NN table
    rank_in = {}
    for r in regions:
        for i, f in enumerate(rank_order(wide[wide.region == r]), 1):
            rank_in[(f, r)] = i
    W = wide.set_index(["feature", "region"])
    nn_rows = []
    for x in nn_res:
        rp, reg = x["scored_as"], x["region"]
        if rp and (rp, reg) in W.index:
            y = W.loc[(rp, reg)]
            nn_rows.append(x | {"D_equal": y.D_comb_equal, "D_crit": y.Dcrit_comb_equal,
                                "D_mass_min": y.D_mass_min, "D_mass_max": y.D_mass_max,
                                "rank_in_region": rank_in[(rp, reg)], "n_features": len(feats)})
        else:
            nn_rows.append(x | {"D_equal": np.nan, "D_crit": np.nan, "D_mass_min": np.nan,
                                "D_mass_max": np.nan, "rank_in_region": np.nan, "n_features": len(feats)})
    nn_df = pd.DataFrame(nn_rows)
    if len(nn_df):
        nn_df.to_csv(OUT / "nn_feature_scores.csv", index=False)
    nn_lines = []
    for blk in blocks:
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
        shared = t.scored_as.dropna()
        if shared.duplicated().any():
            nn_lines.append("  NOTE: list names mapping to the same column: "
                            + ", ".join(sorted(set(t[t.scored_as.duplicated(keep=False)].list_name))))
        nn_lines.append("")
    strong_lines = []
    for r in [x for x in ("endcap", "barrel") if x in regions]:
        inreg = {f for f, bl in used_in.items() if any(b.endswith(r) for b in bl)}
        wr = wide[(wide.region == r) & np.isfinite(wide.D_comb_equal)]
        top = [f for f in rank_order(wr) if f not in inreg][:STRONG_TOP]
        strong_lines += [f"{r.upper()}: top {STRONG_TOP} features used by neither NN1 nor NN2 {r}"]
        for f in top:
            y = W.loc[(f, r)]
            strong_lines.append(f"  {rank_in[(f, r)]:>3}  {f:<40} D_equal {y.D_comb_equal:.3f}  "
                                f"(min {y.D_mass_min:.3f}, max {y.D_mass_max:.3f})")
        strong_lines.append("")
    if blocks:
        print("\n".join(nn_lines + strong_lines), flush=True)

    for r in regions:
        t = wide[wide.region == r]
        t = t.set_index("feature").loc[rank_order(t)].reset_index().head(10)
        log(f"top 10 [{r}]:\n" + t[["feature", "D_comb_equal", "Dcrit_comb_equal", "D_mass_min", "D_mass_max",
                                    "nn_lists"]].to_string(index=False))

    plt = _plt()
    from matplotlib.backends.backend_pdf import PdfPages

    # ---- SUMMARY.pdf
    cover = [
        f"date         {time.strftime('%Y-%m-%d %H:%M')}",
        f"data         {DATA}",
        f"background   {BKG_FILE}  rows {len(dfs['bkg']):,}",
        *[f"signal       {fn}  rows {len(dfs[m]):,}" for m, fn in MASS_FILES.items()],
        f"region       {chosen}",
        f"NN lists     {args.nn_list if blocks else '(none found)'}",
        "",
        f"unit test    HTmiss selection: {'PASS' if ut_pass else 'FLAG'}  (details next page)",
        "",
        f"features common to all 7 files     {len(all7)}",
        f"hard / user excluded               {len(rep['hard'])} / {len(rep['user'])}",
        f"non-numeric / constant overall     {len(rep['non_numeric'])} / {len(rep['constant'])}",
        f"rank-identical duplicates dropped  {n_drop}  (in {len(copies)} groups; duplicates.txt)",
        f"features scored                    {len(feats)}",
        "",
        "KS D = sup|F_s - F_b| in [0, 1] = best single-cut (signal eff - background eff).",
        "noise floor D_crit = 1.36 sqrt(1/n_s + 1/n_b), 95% level for identical distributions.",
        "D_equal weights each mass point 1/N_m (n_s = effective size); D_pooled concatenates them.",
        f"folders: features/NNN_<feature>/, NNN = rank by {RANK_BY} D_equal",
        "",
        "pages: cover, unit test, NN feature table, strong-but-unused features, then per region a",
        "ranking chart (tick = noise floor) and a top-40 table.",
    ]
    with PdfPages(OUT / "SUMMARY.pdf") as pdf:
        for title, lines, kw in [(f"Signal/background separation · mk3 · round {R}", cover, {"size": 8.5}),
                                 ("Unit test", ut_lines, {"size": 7.5}),
                                 ("NN feature lists: KS D in each list's region", nn_lines or ["(no list)"],
                                  {"size": 6.6, "per_page": 60}),
                                 ("Strong features not in the NN lists", strong_lines or ["(no list)"], {})]:
            for fig in text_pages(title, lines, R, **kw):
                pdf.savefig(fig); plt.close(fig)
        for r in regions:
            t = wide[wide.region == r]
            fig = ranking_fig(t, f"Top 40 · region {r.upper()}")
            if fig is not None:
                pdf.savefig(fig); plt.close(fig)
            for fig in text_pages(f"Top 40 table · region {r.upper()}", table_lines(t), R):
                pdf.savefig(fig); plt.close(fig)
        pdf.infodict()["Title"] = f"kj_sigbg_mk3 round {R} summary"
    log("wrote SUMMARY.pdf")
    if args.no_plots:
        log(f"--no-plots: done -> {OUT}")
        return

    # ---- per-feature folders
    rr = RANK_BY if RANK_BY in regions else regions[0]
    order = rank_order(wide[wide.region == rr])
    todo = order[:args.top] if args.top else order
    froot = OUT / "features"
    froot.mkdir(exist_ok=True)
    log(f"writing {len(todo)} feature PDFs ({1 + len(regions)} pages each) -> {froot}")
    for fi, f in enumerate(todo, 1):
        rk = order.index(f) + 1
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f)
        fdir = froot / f"{rk:03d}_{safe}"
        fdir.mkdir(exist_ok=True)
        L = [f"rank {rk} / {len(order)} by {rr} D_equal", ""]
        L.append("used by: " + (", ".join(used_in[f]) if f in used_in else "neither NN list"))
        names = [x["list_name"] for x in nn_res if x["scored_as"] == f and x["list_name"] != f]
        if names:
            L.append("list name(s): " + ", ".join(sorted(set(names))))
        if f in copies:
            L += ["", "rank-identical columns merged into this one:"] + [f"    {c}" for c in copies[f]]
        if f in const:
            L += ["", "constant (no page) in: " + ", ".join(const[f])]
        hdr = f"{'region':<7} {'D_equal':>7} {'noise':>6} {'D_pooled':>8} " + \
              " ".join(f"{m.replace('mH', '').replace('_mS', '/'):>8}" for m in MASS_FILES) + \
              f" {'n_bkg':>7} {'rank':>8}"
        L += ["", hdr, "-" * len(hdr)]
        for r in regions:
            y = W.loc[(f, r)]
            L.append(f"{r:<7} {y.D_comb_equal:7.3f} {y.Dcrit_comb_equal:6.3f} {y.D_comb_pooled:8.3f} "
                     + " ".join(f"{y['D_' + m]:8.3f}" for m in MASS_FILES)
                     + f" {int(y.n_bkg):7,} {str(rank_in[(f, r)]) + '/' + str(len(feats)):>8}")
        L += ["", "pages: one per region -> 1 each mass vs bkg, 2 combined vs bkg, 3 background alone"]
        pages = [("p00_overview", fig) for fig in text_pages(f"overview  ·  rank {rk} / {len(order)}", L, R,
                                                             feat=f, size=8.5, kind="overview")]
        for r in regions:
            if r in const.get(f, []):
                continue
            b = cell("bkg", f, r)[0]
            ms = {m: cell(m, f, r)[0] for m in MASS_FILES}
            e = edges_for([b] + list(ms.values()))
            if e is None:
                continue
            y = W.loc[(f, r)]
            sc = {m: y["D_" + m] for m in MASS_FILES} | {"comb_pooled": y.D_comb_pooled,
                                                         "comb_equal": y.D_comb_equal}
            pages.append((r, region_page(f, r, e, b, ms, sc, y.Dcrit_comb_equal, fills[(f, r)], rk, len(order),
                                         used_in.get(f, []))))
        with PdfPages(fdir / f"{safe}.pdf") as pdf:
            for name, fig in pages:
                pdf.savefig(fig)
                if args.png:
                    (fdir / "png").mkdir(exist_ok=True)
                    fig.savefig(fdir / "png" / f"{name}.png", dpi=110)
                plt.close(fig)
            pdf.infodict()["Title"] = f"{f} - kj_sigbg_mk3 round {R}"
        bar(fi, len(todo), f)
    log(f"DONE -> {OUT}")


if __name__ == "__main__":
    main()
