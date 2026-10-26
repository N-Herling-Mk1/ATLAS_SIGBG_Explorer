#!/usr/bin/env python
"""
build_site.py  --  turn pipeline results into the static site (GitHub Pages, served from the repo root).

Reads   results/<run>/          one folder per finished kj_sigbg_mk4 run (copy of out_sigbg_mk4_r<N>)
        pipeline/               the script's thresholds and lists, exclude_features.txt, nn_features_mk4.txt
Writes  data/<run>.js           everything the pages show, as window.SIGBG.runs[<run>]
        data/index.js           run list + pipeline metadata
        img/<run>/...           every PDF page rendered to PNG (128-colour, ~60 KB each)
        img/archive/...         every page of every archived run's PDFs (90 dpi), data/archive_plots.js

The page itself (index.html, assets/) is hand-written and never touched by this script.
Re-running is incremental: a PNG is only re-rendered when its PDF is newer.

Usage:  python site_builder/build_site.py [--runs mk4_r1 ...] [--dpi 110] [--force]
"""
import argparse
import ast
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
PIPE = REPO / "pipeline"
DATA_OUT = REPO / "data"
IMG_OUT = REPO / "img"
PIPELINE_SCRIPT = PIPE / "kj_sigbg_mk4.py"
ARCHIVE = RESULTS / "archive"
ARCHIVE_INDEX = ARCHIVE / "archive_index.json"
BKG_SPLIT_RUN = ARCHIVE / "out_sigbg_mk2_r1"     # mk2 run cut on htmissScalar >= 40: below = 0-1 jets, above = 2+ jets
T0 = time.time()

ARCHIVE_GUIDE = [
    ("*SUMMARY.pdf", "Summary PDF: cover, rankings, top-feature pages."),
    ("r1_*_all_features.pdf", "Every feature in this region, one page each, in rank order."),
    ("ks_scores_wide.csv", "KS scores, one row per feature x region (x selection)."),
    ("ks_scores_long.csv", "KS scores, one row per feature x region x comparison."),
    ("selection_report.txt", "The preselection cut, per-file edges of the cut variables, events kept per file and region."),
    ("compare_all_vs_*.csv", "Per feature and region: D with all events vs D after the cut, background counts, background split D."),
    ("bkg_split.csv", "Background below vs at/above the cut, KS D per feature and region."),
    ("duplicates.txt", "Rank-identical column groups; first name kept."),
    ("feature_inventory.txt", "Every column in every file."),
    ("excluded_report.txt", "Columns left out, by reason."),
    ("region_audit.txt", "Region definition and counts."),
    ("unit_tests.txt", "HTmiss-split unit test."),
    ("nn_feature_scores.csv", "NN1/NN2 list features resolved to columns and scored."),
    ("features/*/*.pdf", "Per-feature PDF."),
]

# description for every file a run produces (glob relative to the run folder -> text)
FILE_GUIDE = [
    ("00_common/unit_tests.txt", "Data-health gate. Checks the HTmiss split: background htmiss_NOSYS < 40 GeV, signal >= 40 GeV."),
    ("00_common/feature_inventory.txt", "Every column in every file, and which of the 7 files contain it."),
    ("00_common/duplicates.txt", "Groups of columns that are rank-identical in all files (same KS D everywhere). The first name is kept."),
    ("00_common/excluded_report.txt", "Every column left out, by reason: not in all 7 files, hard-excluded, user-excluded (exclude_features.txt), non-numeric, constant."),
    ("00_common/region_audit.txt", "How barrel and endcap were defined, with event counts per file (barrel / endcap / both / neither)."),
    ("A_barrel_vs_endcap/A_SUMMARY.pdf", "Block A summary: features ranked by max(D_endcap, D_barrel), cross-region table, NN-list features in both regions."),
    ("A_barrel_vs_endcap/barrel_vs_endcap.csv", "Per feature: D and noise floor in each region, difference, ranks, where it separates, barrel-vs-endcap shape D."),
    ("A_barrel_vs_endcap/features/*/*.pdf", "Per feature: barrel-vs-endcap shape page and side-by-side separation page."),
    ("B_mc_vs_data/B_SUMMARY.pdf", "Block B summary: unit test, NN-list scores, strong unused features, top-40 rankings per region."),
    ("B_mc_vs_data/ks_scores_wide.csv", "Main score table: one row per feature x region, D per mass point, combined D (pooled, equal-weight), noise floor, flags."),
    ("B_mc_vs_data/ks_scores_long.csv", "Same scores, one row per feature x region x comparison."),
    ("B_mc_vs_data/nn_feature_scores.csv", "The current NN1/NN2 lists, each name resolved to a CSV column and scored in its own region."),
    ("B_mc_vs_data/features/*/*.pdf", "Per feature: overview page plus one page per region (each mass point vs background, combined, background alone)."),
    ("C_correlation/C_SUMMARY.pdf", "Block C summary: background Spearman heatmaps, redundancy blocks, NN1-NN2 cross-correlation."),
    ("C_correlation/spearman_bkg_*.csv", "Spearman correlation matrix on background, per region."),
    ("D_prototypes/D_SUMMARY.pdf", "Block D summary: prototype feature sets P0-P3 and their surrogate scores."),
    ("D_prototypes/prototype_scores.csv", "Gradient-boosted surrogate, 5-fold CV: AUC per network and mass point, worst-mass AUC, NN1-NN2 dCor on background."),
    ("D_prototypes/P*.txt", "A prototype feature set, in the same format as nn_features_mk4.txt."),
    ("gambit_inputs/unit_tests.json", "Unit-test results for GAMBIT's data gate."),
    ("gambit_inputs/pool_*.txt", "Candidate pool per region: separates, not HTmiss-linked / non-physics / suspicious, one feature per redundancy block."),
    ("gambit_inputs/blocks.json", "Redundancy blocks per region (members, representative, D)."),
    ("gambit_inputs/drop_suggestions.txt", "Features suggested for dropping, with category and reason."),
    ("gambit_inputs/prototypes/P*.txt", "Copies of the prototype sets for GAMBIT."),
    ("E_selection/selection_check.txt", "How the samples were selected: HTmiss edge and background jet-multiplicity structure (tools/selection_check.py)."),
    ("E_selection/selection_check.json", "Same, machine-readable; read by the Findings page."),
]


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def bar(i, n, label=""):
    w = 28
    f = i / max(n, 1)
    sys.stdout.write(f"\r  [{'#' * int(f * w):<{w}}] {i}/{n}  {label[:44]:<44}")
    sys.stdout.flush()
    if i >= n:
        sys.stdout.write("\n")


def clean(v):
    """JSON-safe scalar."""
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else round(float(v), 5)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def pipeline_meta():
    """Module-level literal constants of the pipeline script (thresholds, lists)."""
    want = {"HT_TEST_VAR", "HT_TEST_GEV", "RANK_BY", "STRONG_TOP", "SENTINEL", "MIN_N", "N_BINS", "HARD_EXCLUDE",
            "HTMISS_LINKED", "NON_PHYSICS", "WEAK_D", "STRONG_D", "SUSPICIOUS_D", "CORR_BLOCK", "CORR_NMAX",
            "DCOR_N", "CV_FOLDS", "SEED", "BKG_FILE", "MASS_FILES", "SLOT", "BAND"}
    out = {}
    if not PIPELINE_SCRIPT.exists():
        return out
    tree = ast.parse(PIPELINE_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in want:
                try:
                    out[name] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    doc = ast.get_docstring(tree) or ""
    out["DOCSTRING"] = doc
    return out


def read_text(p):
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def parse_sections(txt):
    """'===== name (n) =====' blocks -> {name: [lines]}."""
    out, cur = {}, None
    for line in txt.splitlines():
        m = re.match(r"=====\s*(.+?)\s*\((\d+)\)\s*=====", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and line.strip():
            out[cur].append(line.strip())
    return out


def parse_duplicates(txt):
    """Header paragraph, blank line, then 'keep' lines followed by '    = copy' lines."""
    body = txt.split("\n\n", 1)[1] if "\n\n" in txt else txt
    groups, cur = {}, None
    for line in body.splitlines():
        if line.startswith("    = ") and cur:
            groups[cur].append(line[6:].strip())
        elif line.strip() and not line.startswith(" "):
            cur = line.strip()
            groups[cur] = []
    return {k: v for k, v in groups.items() if v}


def parse_region_audit(txt):
    rows, chosen = [], ""
    for line in txt.splitlines():
        m = re.match(r"\s*(\S+)\s+n\s+([\d,]+)\s+barrel\s+([\d,]+)\s+endcap\s+([\d,]+)\s+both\s+([\d,]+)\s+neither\s+([\d,]+)", line)
        if m:
            g = [int(x.replace(",", "")) for x in m.groups()[1:]]
            rows.append({"sample": m.group(1), "n": g[0], "barrel": g[1], "endcap": g[2], "both": g[3], "neither": g[4]})
        if line.startswith("barrel ="):
            chosen = line.strip()
    return {"rows": rows, "definition": chosen}


def parse_proto(txt):
    nets, cur, desc = {}, None, ""
    for line in txt.splitlines():
        s = line.strip()
        m = re.match(r"#\s*prototype\s+(P\d)\s*--\s*(.+)", s)
        if m:
            desc = m.group(2)
            continue
        m = re.match(r"#\s*(NN\d\s+\w+)\s*\((\d+)\)", s)
        if m:
            cur = m.group(1)
            nets[cur] = []
        elif s and not s.startswith("#") and cur:
            nets[cur].append(s)
    return {"description": desc, "nets": nets}


def parse_nn_lists(txt):
    blocks, cur = {}, None
    for line in txt.splitlines():
        s = line.strip()
        m = re.match(r"#\s*(NN\d)\s+(barrel|endcap)\b", s, re.I)
        if m:
            cur = f"{m.group(1).upper()} {m.group(2).lower()}"
            blocks[cur] = []
        elif s and not s.startswith("#") and cur:
            blocks[cur].append(s)
    return blocks


def page_label(text, kind, k):
    if kind == "S":
        for ln in text.splitlines():
            if re.match(r"^\s*[A-E]\s+·\s+\S", ln):
                return ln.strip()[:90]
        return f"page {k}"
    t = text.upper()
    for r in ("ENDCAP", "BARREL", "ALL"):
        if f"REGION: {r}" in t:
            return r.lower()
    if kind == "B" and "OVERVIEW" in t:
        return "overview"
    if kind == "A":
        if "SEPARATION SIDE BY SIDE" in t:
            return "separation"
        if "SHAPE" in t:
            return "shape"
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), f"page {k}")
    return first[:90]


def render_pdf(pdf, run, dpi, force):
    """Render every page; return [{label, src}] with src relative to the repo root."""
    import pymupdf
    from PIL import Image
    rel = pdf.relative_to(RESULTS / run).with_suffix("")
    base = IMG_OUT / run / rel
    base.parent.mkdir(parents=True, exist_ok=True)
    kind = ("S" if rel.name.endswith("_SUMMARY") else "A" if rel.parts[0].startswith("A_")
            else "B" if rel.parts[0].startswith("B_") else "S")
    pages = []
    doc = pymupdf.open(pdf)
    for k, page in enumerate(doc, 1):
        out = base.parent / f"{base.name}_p{k}.png"
        if force or not out.exists() or out.stat().st_mtime < pdf.stat().st_mtime:
            pix = page.get_pixmap(dpi=dpi)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            im.quantize(128, method=Image.Quantize.FASTOCTREE).save(out, optimize=True)
        pages.append({"label": page_label(page.get_text(), kind, k), "src": out.relative_to(REPO).as_posix()})
    doc.close()
    return pages


def describe(relpath):
    from fnmatch import fnmatch
    for pat, txt in FILE_GUIDE:
        if fnmatch(relpath, pat):
            return txt
    return ""


def archive_describe(rel):
    from fnmatch import fnmatch
    name = rel.split("/", 1)[1] if "/" in rel else rel
    for pat, txt in ARCHIVE_GUIDE:
        if fnmatch(name, pat) or fnmatch(rel.split("/")[-1], pat):
            return txt
    return ""


def build_archive():
    """archive_index.json + file listings of every archived run folder."""
    if not ARCHIVE_INDEX.exists():
        return None
    idx = json.loads(read_text(ARCHIVE_INDEX))
    for e in idx.get("entries", []):
        sp = REPO / e["script"] if e.get("script") else None
        e["script_bytes"] = sp.stat().st_size if sp and sp.exists() else None
        for r in e.get("runs", []):
            folder = (ARCHIVE / r["folder"]).resolve()
            r["href_root"] = folder.relative_to(REPO).as_posix() if folder.exists() else None
            files, n_pdf, tot = [], 0, 0
            if folder.exists():
                for p in sorted(folder.rglob("*")):
                    if p.is_file():
                        rel = p.relative_to(folder).as_posix()
                        tot += p.stat().st_size
                        if p.suffix == ".pdf" and "/features/" in "/" + rel:
                            n_pdf += 1
                            continue
                        files.append({"path": rel, "href": p.relative_to(REPO).as_posix(), "bytes": p.stat().st_size,
                                      "desc": archive_describe(rel)})
            r["files"], r["n_feature_pdfs"], r["bytes"] = files, n_pdf, tot
            fe = folder / "features"
            r["feature_pdfs"] = ([{"name": q.parent.name, "href": q.relative_to(REPO).as_posix()}
                                  for q in sorted(fe.glob("*/*.pdf"))] if fe.exists() else [])
    log(f"archive: {len(idx.get('entries', []))} versions, "
        f"{sum(len(e.get('runs', [])) for e in idx.get('entries', []))} runs")
    return idx


def archive_label(text, k):
    L = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(L):
        if "region:" in ln:
            segs = [x.strip() for x in ln.split("·") if x.strip()][:3]
            if ln.lstrip().lower().startswith("region") and i > 0:
                segs = [L[i - 1]] + segs
            return "  ·  ".join(segs)[:140]
    for ln in L[:6]:
        if "·" in ln or (len(ln) > 6 and not re.fullmatch(r"[-+0-9.,e ]+", ln)):
            return ln[:140]
    return f"page {k}"


def render_archive_plots(dpi, force):
    """Render every page of every archived PDF -> img/archive/<folder>/...; return {folder: [pdf entries]}."""
    import pymupdf
    from PIL import Image
    if not ARCHIVE.exists():
        return {}
    out = {}
    pdfs = sorted(ARCHIVE.rglob("*.pdf"))
    log(f"archive: rendering {len(pdfs)} PDFs at {dpi} dpi (incremental)")
    for i, pdf in enumerate(pdfs, 1):
        rel = pdf.relative_to(ARCHIVE)
        folder = rel.parts[0]
        base = IMG_OUT / "archive" / rel.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open(pdf)
        pages = []
        for k, page in enumerate(doc, 1):
            png = base.parent / f"{base.name}_p{k}.png"
            if force or not png.exists() or png.stat().st_mtime < pdf.stat().st_mtime:
                pix = page.get_pixmap(dpi=dpi)
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                im.quantize(128, method=Image.Quantize.FASTOCTREE).save(png, optimize=True)
            pages.append({"label": archive_label(page.get_text(), k), "src": png.relative_to(REPO).as_posix()})
        doc.close()
        sub = Path(*rel.parts[1:]).as_posix()
        name = rel.parent.name if "features" in rel.parts else pdf.stem
        out.setdefault(folder, []).append({"name": name, "path": sub, "href": pdf.relative_to(REPO).as_posix(), "pages": pages})
        bar(i, len(pdfs), f"{folder}/{pdf.name}")
    for folder, lst in out.items():   # summaries first, then region PDFs, then per-feature folders in rank order
        lst.sort(key=lambda e: (0 if "SUMMARY" in e["path"] else 1 if "/" not in e["path"] else 2, e["path"]))
    return out


def attach_bkg_split(feats):
    """D(background 0-1 jets vs 2+ jets) and D(signal vs 2+-jet background) from the mk2 htmissScalar run."""
    bs, cmp_ = BKG_SPLIT_RUN / "bkg_split.csv", None
    cands = sorted(BKG_SPLIT_RUN.glob("compare_all_vs_*.csv"))
    if cands:
        cmp_ = cands[0]
    if not bs.exists():
        return None
    b = pd.read_csv(bs)
    c = pd.read_csv(cmp_) if cmp_ else None
    look = {}
    for f in feats.values():
        for n in [f["name"]] + f.get("copies", []):
            look.setdefault(n, f["name"])
    hit = set()
    for r in b.to_dict("records"):
        tgt = look.get(r["feature"])
        if tgt and pd.notna(r["D_bkg_split"]):
            d = feats[tgt].setdefault("bkg_split", {})
            if r["region"] not in d:
                d[r["region"]] = {"D": clean(r["D_bkg_split"]), "n_lo": clean(r["n_bkg_below"]), "n_hi": clean(r["n_bkg_above"])}
                hit.add(tgt)
    if c is not None:
        dcol = [k for k in c.columns if k.startswith("D_") and k not in ("D_all", "D_bkg_split")][0]
        ncol = [k for k in c.columns if k.startswith("n_bkg_") and k != "n_bkg_all"][0]
        for r in c.to_dict("records"):
            tgt = look.get(r["feature"])
            if tgt:
                d = feats[tgt].setdefault("two_jet", {})
                if r["region"] not in d:
                    d[r["region"]] = {"D_all": clean(r["D_all"]), "D_cut": clean(r[dcol]), "n_bkg": clean(r[ncol])}
    log(f"  background split attached to {len(hit)} features (source {BKG_SPLIT_RUN.name})")
    return {"source": BKG_SPLIT_RUN.relative_to(REPO).as_posix(), "cut": "htmissScalar_NOSYS >= 40 GeV",
            "meaning": "below = background with 0 or 1 jets, above = background with 2+ jets"}


def build_run(run, dpi, force):
    root = RESULTS / run
    log(f"run {run}: {root}")
    R = {"name": run, "built": time.strftime("%Y-%m-%d %H:%M")}

    # ---------------------------------------------------------------- 00 common
    c0 = root / "00_common"
    R["unit_test"] = read_text(c0 / "unit_tests.txt")
    R["excluded"] = parse_sections(read_text(c0 / "excluded_report.txt"))
    R["duplicates"] = parse_duplicates(read_text(c0 / "duplicates.txt"))
    R["region_audit"] = parse_region_audit(read_text(c0 / "region_audit.txt"))
    inv = read_text(c0 / "feature_inventory.txt")
    m = re.search(r"FEATURES IN FILE: bkg\s+\((\d+)\)", inv)
    R["n_columns_bkg"] = int(m.group(1)) if m else None
    log(f"  00_common: {len(R['duplicates'])} duplicate groups, "
        f"{sum(len(v) for v in R['excluded'].values())} columns excluded")

    # ---------------------------------------------------------------- B scores
    wide = pd.read_csv(root / "B_mc_vs_data" / "ks_scores_wide.csv")
    masses = [c[2:] for c in wide.columns if c.startswith("D_mH")]
    R["masses"] = masses
    R["regions"] = [r for r in ("endcap", "barrel", "all") if r in set(wide.region)]
    feats = {}
    for region, g in wide.groupby("region", sort=False):
        g = g.sort_values("D_comb_equal", ascending=False).reset_index(drop=True)
        for i, row in g.iterrows():
            f = row["feature"]
            rec = feats.setdefault(f, {"name": f, "regions": {}})
            rec["category"] = clean(row.get("category")) if isinstance(row.get("category"), str) else None
            rec["nn_lists"] = [s.strip() for s in str(row.get("nn_lists", "")).split(";")
                               if s.strip() and s.strip() != "nan"]
            rec["regions"][region] = {
                "rank": i + 1, "D": clean(row["D_comb_equal"]), "D_pooled": clean(row["D_comb_pooled"]),
                "Dcrit": clean(row.get("Dcrit_comb_equal")), "D_min": clean(row["D_mass_min"]),
                "D_max": clean(row["D_mass_max"]), "per_mass": [clean(row[f"D_{m}"]) for m in masses],
                "n_bkg": clean(row.get("n_bkg")), "n_sig": clean(row.get("n_sig")),
                "bkg_nan": clean(row.get("bkg_nan_frac")), "bkg_m999": clean(row.get("bkg_m999_frac")),
                "suspicious": bool(row.get("suspicious")) if pd.notna(row.get("suspicious")) else False,
            }
            if rec["regions"][region]["suspicious"]:
                rec["suspicious"] = True
    log(f"  B: {len(feats)} features x {len(R['regions'])} regions, {len(masses)} mass points")

    # nn list resolution
    nnp = root / "B_mc_vs_data" / "nn_feature_scores.csv"
    R["nn_resolution"] = []
    if nnp.exists():
        nn = pd.read_csv(nnp)
        R["nn_resolution"] = [{k: clean(v) for k, v in r.items()} for r in nn.to_dict("records")]

    # ---------------------------------------------------------------- A
    ap_ = root / "A_barrel_vs_endcap" / "barrel_vs_endcap.csv"
    if ap_.exists():
        a = pd.read_csv(ap_)
        for r in a.to_dict("records"):
            if r["feature"] in feats:
                feats[r["feature"]]["A"] = {k: clean(r[k]) if not isinstance(r[k], str) else r[k]
                                            for k in ("D_endcap", "Dcrit_endcap", "D_barrel", "Dcrit_barrel",
                                                      "delta_barrel_minus_endcap", "rank_endcap", "rank_barrel",
                                                      "separates", "shape_D_bkg", "shape_D_sig")}

    # ---------------------------------------------------------------- gambit inputs
    g = root / "gambit_inputs"
    for line in read_text(g / "drop_suggestions.txt").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 4 and parts[1] in feats:
            feats[parts[1]].setdefault("drop", {})[parts[0]] = {"category": parts[2], "reason": parts[3]}
    R["pools"] = {}
    for p in sorted(g.glob("pool_*.txt")):
        reg = p.stem.split("_", 1)[1]
        names = [s.strip() for s in read_text(p).splitlines() if s.strip() and not s.startswith("#")]
        R["pools"][reg] = names
        for n in names:
            if n in feats:
                feats[n].setdefault("pool", []).append(reg)
    R["blocks"] = {}
    bj = g / "blocks.json"
    if bj.exists():
        blocks = json.loads(read_text(bj))
        R["blocks"] = blocks
        for reg, lst in blocks.items():
            for b in lst:
                for mbr in b["members"]:
                    if mbr in feats:
                        feats[mbr].setdefault("block", {})[reg] = {
                            "id": b["block"], "rep": b["representative"],
                            "members": b["members"]}

    # ---------------------------------------------------------------- C correlation
    R["corr"] = {}
    for p in sorted((root / "C_correlation").glob("spearman_bkg_*.csv")):
        reg = p.stem.rsplit("_", 1)[1]
        c = pd.read_csv(p, index_col=0)
        R["corr"][reg] = {"features": list(c.columns),
                          "rho": [[None if not np.isfinite(x) else round(float(x), 3) for x in row]
                                  for row in c.to_numpy(float)]}
    log(f"  C: correlation matrices for {', '.join(R['corr']) or 'none'}")

    # ---------------------------------------------------------------- D prototypes
    R["prototypes"] = {}
    dd = root / "D_prototypes"
    for p in sorted(dd.glob("P*.txt")):
        R["prototypes"][p.stem] = parse_proto(read_text(p))
        for net, names in R["prototypes"][p.stem]["nets"].items():
            for n in names:
                if n in feats:
                    feats[n].setdefault("protos", []).append(f"{p.stem} {net}")
    ps = dd / "prototype_scores.csv"
    R["prototype_scores"] = ([{k: clean(v) for k, v in r.items()} for r in pd.read_csv(ps).to_dict("records")]
                             if ps.exists() else [])

    # duplicates onto features
    for keep, copies in R["duplicates"].items():
        if keep in feats:
            feats[keep]["copies"] = copies

    R["bkg_split_meta"] = attach_bkg_split(feats)

    # ---------------------------------------------------------------- E selection
    sj = root / "E_selection" / "selection_check.json"
    R["selection"] = json.loads(read_text(sj)) if sj.exists() else None

    # ---------------------------------------------------------------- images
    pdfs = sorted(root.rglob("*.pdf"))
    log(f"  rendering {len(pdfs)} PDFs at {dpi} dpi (incremental)")
    rendered = {}
    for i, pdf in enumerate(pdfs, 1):
        rendered[pdf.relative_to(root).as_posix()] = render_pdf(pdf, run, dpi, force)
        bar(i, len(pdfs), pdf.name)
    R["summaries"] = []
    for rel, pages in rendered.items():
        parts = rel.split("/")
        if len(parts) == 4 and parts[1] == "features":
            folder = parts[2]
            num = int(folder.split("_", 1)[0])
            fname_pdf = parts[3][:-4]
            # map back to the feature name (folder names replace '/' with '_')
            target = next((f for f in feats if f.replace("/", "_") == fname_pdf), None)
            if target:
                key = "plots_B" if parts[0].startswith("B_") else "plots_A"
                feats[target][key] = {"pdf": f"results/{run}/{rel}", "pages": pages, "folder_rank": num}
        elif rel.endswith("_SUMMARY.pdf"):
            R["summaries"].append({"block": parts[0], "pdf": f"results/{run}/{rel}", "pages": pages})

    # ---------------------------------------------------------------- file guide
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            files.append({"path": rel, "href": f"results/{run}/{rel}", "bytes": p.stat().st_size,
                          "desc": describe(rel)})
    R["files"] = files
    R["features"] = sorted(feats.values(), key=lambda f: (f["regions"].get("endcap", {}).get("rank", 999), f["name"]))
    log(f"  {len(files)} files catalogued")
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=None, help="run folder names under results/ (default: all)")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--force", action="store_true", help="re-render every PNG")
    ap.add_argument("--archive-dpi", type=int, default=90, help="render resolution for archived runs")
    ap.add_argument("--skip-archive-plots", action="store_true", help="do not render archived PDFs")
    args = ap.parse_args()
    try:
        import pymupdf  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("needs pymupdf and pillow:  pip install pymupdf pillow")
    runs = args.runs or sorted(p.name for p in RESULTS.iterdir() if (p / "B_mc_vs_data").is_dir())
    if not runs:
        sys.exit(f"no runs under {RESULTS} (expected folders containing B_mc_vs_data/)")
    DATA_OUT.mkdir(exist_ok=True)
    log(f"runs: {', '.join(runs)}")
    for i, run in enumerate(runs, 1):
        log(f"[{i}/{len(runs)}] building {run}")
        R = build_run(run, args.dpi, args.force)
        js = "window.SIGBG = window.SIGBG || {runs: {}};\nwindow.SIGBG.runs[" + json.dumps(run) + "] = " + \
             json.dumps(R, separators=(",", ":")) + ";\n"
        (DATA_OUT / f"{run}.js").write_text(js, encoding="utf-8")
        log(f"  wrote data/{run}.js ({len(js) / 1e6:.2f} MB)")
    meta = pipeline_meta()
    meta["exclude_file"] = read_text(PIPE / "exclude_features.txt")
    meta["nn_file"] = read_text(PIPE / "nn_features_mk4.txt")
    meta["nn_lists"] = parse_nn_lists(meta["nn_file"])
    code = []
    for sub in ("pipeline", "tools", "site_builder", "pipeline/archive"):
        for p in sorted((REPO / sub).glob("*")):
            if p.is_file() and p.suffix in (".py", ".txt") and p.name != "config.txt":
                code.append({"path": f"{sub}/{p.name}", "bytes": p.stat().st_size})
    meta["code_files"] = code
    idx = ("window.SIGBG = window.SIGBG || {runs: {}};\nwindow.SIGBG.index = " +
           json.dumps({"runs": runs, "default": runs[-1], "built": time.strftime("%Y-%m-%d %H:%M"),
                       "pipeline": meta, "archive": build_archive()}, separators=(",", ":")) + ";\n")
    (DATA_OUT / "index.js").write_text(idx, encoding="utf-8")
    if not args.skip_archive_plots:
        ap_ = render_archive_plots(args.archive_dpi, args.force)
        js = ("window.SIGBG = window.SIGBG || {runs: {}};\nwindow.SIGBG.archivePlots = " +
              json.dumps(ap_, separators=(",", ":")) + ";\n")
        (DATA_OUT / "archive_plots.js").write_text(js, encoding="utf-8")
        log(f"wrote data/archive_plots.js ({len(js) / 1e6:.2f} MB, "
            f"{sum(len(p['pages']) for v in ap_.values() for p in v)} pages)")
    log("wrote data/index.js")
    log("done. Open index.html in a browser, or push and enable GitHub Pages (branch main, folder / root).")


if __name__ == "__main__":
    main()
