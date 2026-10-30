/* SIG/BG Feature Explorer mk1 — static, no build step, works from file:// and GitHub Pages.
   Data: data/index.js (run list + pipeline metadata) and data/<run>.js (one per result set),
   both written by site_builder/build_site.py. */
(function () {
  "use strict";
  const S = window.SIGBG || { runs: {} };
  const I = S.index;
  const app = document.getElementById("app");
  const tip = document.getElementById("tip");
  const REGIONS = ["endcap", "barrel", "all"];
  let RUN = null;
  const ui = { region: "endcap", sort: "D", asc: false, q: "", hideHM: false, hideNP: false, hideJet: false, onlyNN: false, onlySep: false,
               corrRegion: "endcap", plotTab: {}, excl: null };

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v, d = 3) => (v == null || Number.isNaN(v) ? "–" : Number(v).toFixed(d));
  const int = (v) => (v == null ? "–" : Number(v).toLocaleString("en-US"));
  const kb = (b) => (b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");
  const P = () => (I && I.pipeline) || {};
  const SLOT = () => P().SLOT || ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"];
  const short = (m) => m.replace("mH", "").replace("_mS", "/");
  const fid = (name) => encodeURIComponent(name);
  const store = {
    get(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };
  function tex(s, display) {
    if (window.katex) {
      try { return window.katex.renderToString(s, { displayMode: !!display, throwOnError: false }); } catch (e) { /* fall through */ }
    }
    return `<code>${esc(s)}</code>`;
  }
  function separates(r) {
    if (!r || r.D == null) return false;
    const w = P().WEAK_D != null ? P().WEAK_D : 0.2;
    return r.D >= Math.max(w, 2 * (r.Dcrit || 0));
  }
  function catChip(f) {
    let h = "";
    if (f.category === "htmiss-linked") h += `<span class="chip htmiss" title="D partly set by the by-design HTmiss split">htmiss-linked</span>`;
    if (f.category === "non-physics") h += `<span class="chip nonphys" title="trigger / quality / pileup">non-physics</span>`;
    if (f.suspicious) h += `<span class="chip susp" title="some mass point separated at D >= ${P().SUSPICIOUS_D || 0.99}">suspicious</span>`;
    return h;
  }
  const JET_DEP = 0.2;   // background 0-1 jets vs 2+ jets: D at or above this = depends on jet activity
  function jetDep(f, r) { const b = f.bkg_split && f.bkg_split[r]; return b && b.D != null && b.D >= JET_DEP; }
  function jetChip(f, r) {
    const b = f.bkg_split && f.bkg_split[r];
    return jetDep(f, r) ? `<span class="chip jet" title="background 0-1 jets vs 2+ jets: D ${fmt(b.D)} (mk2 background split)">jet-dep ${fmt(b.D, 2)}</span>` : "";
  }
  function nnChips(f) { return (f.nn_lists || []).map((n) => `<span class="chip nn">${esc(n)}</span>`).join(""); }
  function showTip(e, html) {
    tip.innerHTML = html; tip.hidden = false;
    const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  function lightbox(src, caption, pdf) {
    const lb = document.createElement("div");
    lb.className = "lightbox";
    lb.innerHTML = `<img src="${esc(src)}" alt="${esc(caption)}"><div class="lb-bar"><span>${esc(caption)}</span>` +
      (pdf ? `<a href="${esc(pdf)}" download>PDF</a>` : "") + `<a href="${esc(src)}" download>PNG</a><button type="button">close (Esc)</button></div>`;
    const close = () => { lb.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    lb.addEventListener("click", (e) => { if (e.target === lb || e.target.tagName === "BUTTON") close(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(lb);
  }
  function download(name, text) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function feat(name) { return RUN.features.find((f) => f.name === name); }
  function byRank(region) {
    return RUN.features.filter((f) => f.regions[region]).slice().sort((a, b) => a.regions[region].rank - b.regions[region].rank);
  }

  // ------------------------------------------------------------------ run loading
  function loadRun(name, cb) {
    if (S.runs[name]) { cb(); return; }
    const s = document.createElement("script");
    s.src = `data/${name}.js`;
    s.onload = cb;
    s.onerror = () => { app.innerHTML = `<div class="callout"><h3>Missing data</h3><p>data/${esc(name)}.js did not load. Run <code>python site_builder/build_site.py</code>.</p></div>`; };
    document.head.appendChild(s);
  }
  function initRuns() {
    const sel = document.getElementById("runSelect");
    if (!I) {
      app.innerHTML = `<div class="callout"><h3>No site data yet</h3><p>Run <code>python site_builder/build_site.py</code> from the repo root, then reload.</p></div>`;
      return false;
    }
    sel.innerHTML = I.runs.map((r) => `<option value="${esc(r)}">${esc(r)}</option>`).join("");
    const saved = store.get("sigbg.run");
    sel.value = I.runs.includes(saved) ? saved : I.default;
    sel.addEventListener("change", () => { store.set("sigbg.run", sel.value); start(); });
    document.getElementById("builtStamp").textContent = "site built " + I.built;
    return true;
  }
  function start() {
    const name = document.getElementById("runSelect").value;
    loadRun(name, () => { RUN = S.runs[name]; route(); });
  }

  // ------------------------------------------------------------------ router
  const VIEWS = {};
  function route() {
    if (!RUN) return;
    hideTip();
    const h = (location.hash || "#/").slice(2);
    const [view, ...rest] = h.split("/");
    const arg = rest.length ? decodeURIComponent(rest.join("/")) : "";
    const v = VIEWS[view || "home"] || VIEWS.home;
    document.onkeydown = null;
    document.querySelectorAll("#tabs a").forEach((a) => {
      const t = a.getAttribute("href").slice(2);
      a.classList.toggle("on", t === (view || "") || (t === "" && !view));
    });
    v(arg);
    app.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    const titles = { home: "Home", be: "Features · Barrel–Endcap", sb: "Features · Signal–Background", gbe: "NN groupings · Barrel–Endcap", gsb: "NN groupings · Signal–Background" };
    tellShell({ type: "route", hash: location.hash || "#/home", title: titles[view || "home"] || (view ? view[0].toUpperCase() + view.slice(1) : "Home") });
  }
  window.addEventListener("hashchange", route);

  // ------------------------------------------------------------------ OVERVIEW
  VIEWS.overview = function () {
    const nF = RUN.features.length, ra = RUN.region_audit.rows;
    const bkg = ra.find((r) => r.sample === "bkg") || {};
    const sig = ra.filter((r) => r.sample !== "bkg");
    const nSig = sig.reduce((a, r) => a + r.n, 0);
    const pass = /RESULT:\s*PASS/.test(RUN.unit_test);
    const sb = RUN.selection && RUN.selection.samples && RUN.selection.samples.bkg;
    const zeroJet = sb ? jetFrac(sb) : null;
    const zjTxt = zeroJet ? `, and ${(zeroJet[0] * 100).toFixed(0)}% of the background has no jets at all` : "";
    const clean = byRank("endcap").filter((f) => !f.category && !f.suspicious).slice(0, 10);
    const nDup = Object.values(RUN.duplicates).reduce((a, v) => a + v.length, 0);
    app.innerHTML = `
      <section class="hero">
      <img class="hero-art" src="assets/brand/sigbg_banner_900.png" alt="SIG/BG Feature Explorer: a grey background histogram and a red signal histogram separated by a cut line" width="900" height="900">
      <div>
      <div class="eyebrow">ATLAS Run-3 · MSVtx LLP search · feature study · run ${esc(RUN.name)}</div>
      <h1>Which inputs separate <span class="k">signal</span> from background?</h1>
      <p class="lede">For every column common to the background file and the six signal mass points, this site shows how strongly it
      separates signal from background (two-sample KS distance), in the endcap, the barrel and both together, and how it behaves
      across the two regions, how redundant it is with other columns, and what prototype NN1/NN2 input sets built from it score.
      Every number and plot comes from <code>pipeline/kj_sigbg_mk5.py</code> (run mk4_r1: its predecessor mk4); the code is in this repo so you can rerun it on your own copy of the files.</p>
      </div></section>

      <div class="grid g4" style="margin-top:22px">
        <div class="stat"><div class="v">${nF}</div><div class="l">features scored (after removing duplicates)</div></div>
        <div class="stat"><div class="v">${RUN.n_columns_bkg || "–"}</div><div class="l">columns in the background file</div></div>
        <div class="stat"><div class="v">${nDup}</div><div class="l">duplicate columns folded into ${Object.keys(RUN.duplicates).length} groups</div></div>
        <div class="stat"><div class="v">${RUN.masses.length}</div><div class="l">signal mass points</div></div>
        <div class="stat"><div class="v">${int(bkg.n)}</div><div class="l">background events (data) · ${int(bkg.endcap)} endcap · ${int(bkg.barrel)} barrel</div></div>
        <div class="stat"><div class="v">${int(nSig)}</div><div class="l">signal events (MC), all mass points</div></div>
      </div>

      <div class="callout ${pass ? "warn" : ""}">
        <h3>${pass ? "Read the Findings first" : "Unit test did not pass"}</h3>
        <p>${pass ? `The unit test passes: background has <code>htmiss_NOSYS</code> &lt; 40 GeV and signal has <code>htmiss_NOSYS</code> &ge; 40 GeV, as designed.
        That design means any variable tied to HTmiss or jet activity separates the two files <em>by construction</em>${zjTxt}.
        The ranking flags these features; the <a href="#/findings">Findings</a> page explains which rankings to trust.` :
        `See the unit test on the <a href="#/findings">Findings</a> page before using any ranking.`}</p>
      </div>

      <h2>How it fits <span class="k">together</span></h2>
      <div class="flow">
        <div class="step"><div class="n">1</div><div class="t">Your data</div><p>Background + 6 mass-point CSVs. Never in the repo; point <code>pipeline/config.txt</code> at them.</p></div>
        <div class="step edit"><div class="n">2</div><div class="t">exclude_<wbr>features.txt</div><span class="badge-edit">EDITABLE</span><p>Columns you want left out. Edit by hand or generate it on the <a href="#/exclusions">Exclusions</a> page.</p></div>
        <div class="step"><div class="n">3</div><div class="t">Pipeline</div><p><code>kj_sigbg_mk5.py</code>: unit test, KS scores, barrel vs endcap, correlation, prototypes.</p></div>
        <div class="step"><div class="n">4</div><div class="t">results/&lt;run&gt;</div><p>CSVs, text reports and one PDF per feature. <a href="#/files">Browse every file</a>.</p></div>
        <div class="step"><div class="n">5</div><div class="t">Site builder</div><p><code>build_site.py</code> renders the PDFs to images and writes the data this page reads.</p></div>
        <div class="step"><div class="n">6</div><div class="t">This site</div><p>Static pages. Open <code>index.html</code> locally or serve it with GitHub Pages.</p></div>
      </div>

      <h2>Where to <span class="k">go</span></h2>
      <div class="grid g3">
        ${[
          ["graphs", "Graphs", "Every plot, by split: signal vs background in endcap / barrel / both, barrel vs endcap shapes. One PDF per split."],
          ["findings", "Findings", "How the samples were selected, and what it means for every ranking."],
          ["rankings", "Rankings", "All features by KS D per region, with flags, NN-list membership and filters."],
          ["feature", "Feature view", "One feature: scores, flags, every plot, PDF downloads."],
          ["regions", "Barrel vs endcap", "Where each feature separates; the D_barrel vs D_endcap map."],
          ["correlation", "Correlation", "Background Spearman matrix and redundancy blocks per region."],
          ["prototypes", "Prototypes", "Candidate NN1/NN2 input sets P0–P3 and their surrogate AUCs."],
          ["exclusions", "Exclusions", "What was left out and why; build a new exclude_features.txt."],
          ["methods", "Metrics", "Definitions of every number on this site."],
          ["files", "Files & code", "Download every result file and the code to rerun it."],
          ["plots", "PDF browser", "Every page of every PDF, current and archived, PDF by PDF: browse or search all of them."],
          ["archive", "Archive", "mk1 → mk4: every script version and every run, with what changed."],
        ].map(([h, t, d]) => `<a class="card link" href="#/${h}"><h3>${t} <span class="arrow">→</span></h3><p class="muted small">${d}</p></a>`).join("")}
      </div>

      <h2>Strongest separators <span class="k">without flags</span> · endcap</h2>
      <p class="muted prose">Top ten features in the endcap that are not HTmiss-linked, non-physics or suspicious. See <a href="#/rankings">Rankings</a> for all of them.</p>
      ${rankTable(clean, "endcap", false)}
    `;
    bindRows();
  };

  // ------------------------------------------------------------------ RANKINGS
  function dbar(f, r) {
    const x = f.regions[r];
    if (!x) return "–";
    const cls = f.category === "htmiss-linked" ? "hm" : f.category === "non-physics" ? "np" : "";
    return `<div class="dwrap"><div class="dbar" title="noise floor ${fmt(x.Dcrit)}"><i class="${cls}" style="width:${(x.D || 0) * 100}%"></i>` +
      (x.Dcrit ? `<b style="left:${Math.min(1, x.Dcrit) * 100}%"></b>` : "") + `<span>${fmt(x.D)}</span></div></div>`;
  }
  function strip(f, r) {
    const x = f.regions[r];
    if (!x) return "";
    return `<span class="strip">${x.per_mass.map((d, i) => {
      const a = d == null ? 0 : Math.max(0.06, d);
      return `<i style="background:${SLOT()[i]};opacity:${a}" title="${esc(RUN.masses[i])}: D ${fmt(d)}"></i>`;
    }).join("")}</span>`;
  }
  function rankTable(list, r, full) {
    if (!list.length) return `<p class="muted">No features match.</p>`;
    const th = (k, l, cls = "") => full ? `<th class="sort ${cls} ${ui.sort === k ? "on" + (ui.asc ? " asc" : "") : ""}" data-k="${k}">${l}</th>` : `<th class="${cls}">${l}</th>`;
    return `<div class="tablewrap"><table>
      <thead><tr>${th("rank", "#", "n")}${th("name", "feature")}${th("D", "D equal")}${th("Dmin", "min · max", "n")}<th>per mass</th>${th("flags", "flags")}<th>NN lists</th></tr></thead>
      <tbody>${list.map((f) => {
        const x = f.regions[r];
        const drop = f.drop && f.drop[r] ? `<span class="chip drop" title="${esc(f.drop[r].reason)}">drop: ${esc(f.drop[r].category)}</span>` : "";
        const pool = (f.pool || []).includes(r) ? `<span class="chip pool" title="in GAMBIT candidate pool (${r})">pool</span>` : "";
        return `<tr class="click" data-f="${esc(f.name)}">
          <td class="n">${x.rank}</td>
          <td><a class="fname" href="#/feature/${fid(f.name)}">${esc(f.name)}</a></td>
          <td>${dbar(f, r)}</td>
          <td class="n">${fmt(x.D_min, 2)} · ${fmt(x.D_max, 2)}</td>
          <td>${strip(f, r)}</td>
          <td>${catChip(f)}${jetChip(f, r)}${pool}${drop}</td>
          <td>${nnChips(f)}</td></tr>`;
      }).join("")}</tbody></table></div>`;
  }
  function bindRows() {
    app.querySelectorAll("tr.click").forEach((tr) => tr.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      location.hash = "#/feature/" + fid(tr.dataset.f);
    }));
  }
  VIEWS.rankings = function (arg) {
    if (REGIONS.includes(arg)) ui.region = arg;
    const r = ui.region;
    let list = byRank(r);
    const q = ui.q.trim().toLowerCase();
    if (q) list = list.filter((f) => f.name.toLowerCase().includes(q));
    if (ui.hideHM) list = list.filter((f) => f.category !== "htmiss-linked");
    if (ui.hideNP) list = list.filter((f) => f.category !== "non-physics" && !f.suspicious);
    if (ui.hideJet) list = list.filter((f) => !jetDep(f, r));
    if (ui.onlyNN) list = list.filter((f) => (f.nn_lists || []).length);
    if (ui.onlySep) list = list.filter((f) => separates(f.regions[r]));
    const key = {
      rank: (f) => f.regions[r].rank, name: (f) => f.name.toLowerCase(), D: (f) => f.regions[r].D,
      Dmin: (f) => f.regions[r].D_min, flags: (f) => (f.category || "") + (f.suspicious ? "z" : ""),
    }[ui.sort] || ((f) => f.regions[r].D);
    list.sort((a, b) => { const A = key(a), B = key(b); return (A < B ? -1 : A > B ? 1 : 0) * (ui.asc ? 1 : -1); });
    const rs = RUN.region_audit.rows.find((x) => x.sample === "bkg") || {};
    app.innerHTML = `
      <div class="eyebrow">Block B · signal (MC) vs background (data)</div>
      <h1>Rankings</h1>
      <p class="lede">Combined equal-weight KS distance per feature. The bar is D; the red tick is the noise floor
      ${tex("D_{crit}=1.36\\sqrt{1/n_s+1/n_b}")}. The six squares are the six mass points (darker = larger D). Click a row for the feature view.</p>
      <div class="toolbar">
        <div class="seg" role="tablist">${REGIONS.map((x) => `<button type="button" class="${x === r ? "on " + x : ""}" data-r="${x}">${x}</button>`).join("")}</div>
        <input type="search" id="q" placeholder="search feature name" value="${esc(ui.q)}" aria-label="Search features">
        <label><input type="checkbox" id="hm" ${ui.hideHM ? "checked" : ""}> hide htmiss-linked</label>
        <label><input type="checkbox" id="np" ${ui.hideNP ? "checked" : ""}> hide non-physics / suspicious</label>
        <label><input type="checkbox" id="jd" ${ui.hideJet ? "checked" : ""}> hide jet-dependent</label>
        <label><input type="checkbox" id="nn" ${ui.onlyNN ? "checked" : ""}> only NN-list features</label>
        <label><input type="checkbox" id="sp" ${ui.onlySep ? "checked" : ""}> only "separates"</label>
        <span class="count">${list.length} of ${byRank(r).length} · bkg n = ${int(r === "all" ? rs.n : rs[r])}</span>
      </div>
      <div class="legend" style="margin-bottom:10px">${RUN.masses.map((m, i) => `<span><i style="background:${SLOT()[i]}"></i>${esc(m)}</span>`).join("")}
        <a class="btn sm" style="margin-left:auto" href="#/graphs/sb_${esc(r)}" title="the same filters, as plots">plots for this list →</a>
        <a class="btn sm" href="results/${esc(RUN.name)}/B_mc_vs_data/ks_scores_wide.csv" download>ks_scores_wide.csv</a></div>
      ${rankTable(list, r, true)}
      <p class="muted small" style="margin-top:10px">"separates" = ${tex("D \\ge \\max(" + (P().WEAK_D || 0.2) + ",\\,2D_{crit})")}.
      Flags and drop suggestions come from the pipeline (<code>gambit_inputs/drop_suggestions.txt</code>); see <a href="#/methods">Metrics</a>.
      <span class="chip jet">jet-dep</span> = the feature differs between 0–1-jet and 2+-jet background with D &ge; ${JET_DEP} (background split, <a href="#/findings">Findings §5</a>).</p>`;
    app.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { ui.region = b.dataset.r; location.hash = "#/rankings/" + b.dataset.r; }));
    const q2 = app.querySelector("#q");
    q2.addEventListener("input", () => { ui.q = q2.value; const pos = q2.selectionStart; VIEWS.rankings(); const n = app.querySelector("#q"); n.focus(); n.setSelectionRange(pos, pos); });
    [["hm", "hideHM"], ["np", "hideNP"], ["jd", "hideJet"], ["nn", "onlyNN"], ["sp", "onlySep"]].forEach(([id, k]) =>
      app.querySelector("#" + id).addEventListener("change", (e) => { ui[k] = e.target.checked; VIEWS.rankings(); }));
    app.querySelectorAll("th.sort").forEach((th) => th.addEventListener("click", () => {
      const k = th.dataset.k;
      if (ui.sort === k) ui.asc = !ui.asc; else { ui.sort = k; ui.asc = k === "rank" || k === "name"; }
      VIEWS.rankings();
    }));
    bindRows();
  };

  // ------------------------------------------------------------------ FEATURE
  function massChart(f) {
    const W = 640, H = 230, L = 46, B = 34, T = 14, regs = REGIONS.filter((r) => f.regions[r]);
    const n = RUN.masses.length, gw = (W - L - 10) / n, bw = Math.min(16, (gw - 10) / regs.length);
    const y = (v) => T + (H - T - B) * (1 - v);
    const colors = { endcap: "var(--endcap-ink)", barrel: "var(--barrel-ink)", all: "var(--ink)" };
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="KS D per mass point and region">`;
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => { s += `<line class="gl" x1="${L}" x2="${W - 6}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v.toFixed(2)}</text>`; });
    RUN.masses.forEach((m, i) => {
      const x0 = L + i * gw + (gw - regs.length * bw) / 2;
      regs.forEach((r, j) => {
        const d = f.regions[r].per_mass[i];
        if (d == null) return;
        s += `<rect x="${x0 + j * bw}" y="${y(d)}" width="${bw - 2}" height="${y(0) - y(d)}" fill="${colors[r]}" data-t="${esc(m)} · ${r}: D ${fmt(d)}"/>`;
      });
      s += `<text x="${L + i * gw + gw / 2}" y="${H - 12}" text-anchor="middle">${esc(short(m))}</text>`;
    });
    regs.forEach((r) => {
      const dc = f.regions[r].Dcrit;
      if (dc) s += `<line x1="${L}" x2="${W - 6}" y1="${y(dc)}" y2="${y(dc)}" stroke="${colors[r]}" stroke-dasharray="3 3" opacity=".6"/>`;
    });
    s += `<line class="ax" x1="${L}" x2="${W - 6}" y1="${y(0)}" y2="${y(0)}"/></svg>`;
    return s + `<div class="legend">${regs.map((r) => `<span><i style="background:${colors[r]}"></i>${r}</span>`).join("")}<span class="muted">dashed = noise floor per region · mass labels mH/mS in GeV</span></div>`;
  }
  function plotPanel(f, key, title) {
    const pl = f[key];
    if (!pl) return "";
    const tabKey = f.name + key;
    const i = Math.min(ui.plotTab[tabKey] || (key === "plots_B" ? 1 : 0), pl.pages.length - 1);
    const pg = pl.pages[i];
    const bandCls = REGIONS.includes(pg.label) ? pg.label : "";
    return `<div class="plotpanel" data-key="${key}">
      <div class="plotbar">
        <div class="seg">${pl.pages.map((p, k) => `<button type="button" data-i="${k}" class="${k === i ? "on " + (REGIONS.includes(p.label) ? p.label : "") : ""}">${esc(p.label)}</button>`).join("")}</div>
        <div><span class="plotlabel chip ${bandCls}">${esc(title)} · ${esc(pg.label)}</span>
        <a class="btn sm" href="${esc(pl.pdf)}" download>PDF (all ${pl.pages.length} pages)</a></div>
      </div>
      <img class="plotimg" src="${esc(pg.src)}" alt="${esc(f.name)} · ${esc(title)} · ${esc(pg.label)}" loading="lazy" data-pdf="${esc(pl.pdf)}">
    </div>`;
  }
  VIEWS.feature = function (arg) {
    const list = byRank("endcap");
    const f = feat(arg) || list[0];
    if (!arg) { location.replace("#/feature/" + fid(f.name)); return; }
    const k = list.indexOf(f), prev = list[k - 1], next = list[k + 1];
    const regionCards = REGIONS.filter((r) => f.regions[r]).map((r) => {
      const x = f.regions[r];
      const lo = x.per_mass.indexOf(x.D_min), hi = x.per_mass.indexOf(x.D_max);
      return `<div class="rcard ${r}"><div class="t">${r}</div><div class="big">D ${fmt(x.D)}</div>
        <div class="small">${separates(x) ? "<b>separates</b>" : "does not separate"} · rank ${x.rank} / ${byRank(r).length}</div>
        <dl><dt>pooled D</dt><dd>${fmt(x.D_pooled)}</dd><dt>noise floor</dt><dd>${fmt(x.Dcrit)}</dd>
        <dt>min</dt><dd>${fmt(x.D_min)} (${esc(short(RUN.masses[lo] || ""))})</dd><dt>max</dt><dd>${fmt(x.D_max)} (${esc(short(RUN.masses[hi] || ""))})</dd>
        <dt>n bkg · sig</dt><dd>${int(x.n_bkg)} · ${int(x.n_sig)}</dd><dt>bkg NaN · −999</dt><dd>${fmt(x.bkg_nan, 3)} · ${fmt(x.bkg_m999, 3)}</dd></dl></div>`;
    }).join("");
    const A = f.A || {};
    const rows = [];
    rows.push(["category", catChip(f) || `<span class="muted">none (physics candidate)</span>`]);
    rows.push(["NN lists (mk4)", nnChips(f) || `<span class="muted">not used</span>`]);
    if (f.drop) rows.push(["drop suggestions", Object.entries(f.drop).map(([r, d]) => `<span class="chip ${r}">${r}</span> ${esc(d.category)} — ${esc(d.reason)}`).join("<br>")]);
    if (f.pool) rows.push(["GAMBIT pool", f.pool.map((r) => `<span class="chip pool">${r}</span>`).join("")]);
    if (f.block) rows.push(["redundancy block", Object.entries(f.block).map(([r, b]) => `<span class="chip ${r}">${r}</span> block ${b.id}, rep <code>${esc(b.rep)}</code>` +
      (b.members.length > 1 ? ` · members: ${b.members.map((m) => m === f.name ? `<b>${esc(m)}</b>` : `<a href="#/feature/${fid(m)}">${esc(m)}</a>`).join(", ")}` : " · alone")).join("<br>")]);
    if (f.protos) rows.push(["prototypes", f.protos.map((p) => `<span class="chip">${esc(p)}</span>`).join("")]);
    if (f.copies) rows.push(["identical columns", `<span class="muted">rank-identical in every file, dropped in favour of this name:</span><br>${f.copies.map((c) => `<code>${esc(c)}</code>`).join(" ")}`]);
    if (f.bkg_split) rows.push(["background split", `0–1 jets vs 2+ jets, background only: ` + REGIONS.filter((r) => f.bkg_split[r]).map((r) =>
      `<span class="chip ${r}">${r}</span> D ${fmt(f.bkg_split[r].D)}`).join(" ") + (REGIONS.some((r) => jetDep(f, r)) ? ` <span class="chip jet">jet-dependent</span>` : "") +
      `<div class="small muted">from <a href="#/archive">mk2</a> (cut htmissScalar &ge; 40 GeV)</div>`]);
    if (f.two_jet) rows.push(["vs 2+-jet background", REGIONS.filter((r) => f.two_jet[r]).map((r) =>
      `<span class="chip ${r}">${r}</span> ${fmt(f.two_jet[r].D_all)} → ${fmt(f.two_jet[r].D_cut)}`).join(" ") +
      `<div class="small muted">signal vs all background → signal vs 2+-jet background only (n ${int((f.two_jet.endcap || {}).n_bkg)} endcap). Not the signal region; <a href="#/archive">mk2</a>.</div>`]);
    if (f.A) rows.push(["barrel vs endcap", `separates in <b>${esc(A.separates)}</b> · Δ(barrel − endcap) ${fmt(A.delta_barrel_minus_endcap)} · shape D bkg ${fmt(A.shape_D_bkg)}, signal ${fmt(A.shape_D_sig)}`]);
    app.innerHTML = `
      <div class="fnav">
        <a class="btn sm" href="${prev ? "#/feature/" + fid(prev.name) : "#/feature/" + fid(f.name)}" ${prev ? "" : "aria-disabled=true"}>← ${prev ? esc(prev.name) : "first"}</a>
        <input type="text" id="fpick" list="flist" placeholder="jump to feature… (type to search)" aria-label="Jump to feature">
        <datalist id="flist">${list.map((x) => `<option value="${esc(x.name)}">`).join("")}</datalist>
        <a class="btn sm" href="${next ? "#/feature/" + fid(next.name) : "#/feature/" + fid(f.name)}" ${next ? "" : "aria-disabled=true"}>${next ? esc(next.name) : "last"} →</a>
      </div>
      <div class="fhead">
        <div class="eyebrow">feature · endcap rank ${f.regions.endcap ? f.regions.endcap.rank : "–"} of ${list.length}</div>
        <h1>${esc(f.name)}</h1>
        <div class="meta">${catChip(f)}${nnChips(f)}</div>
      </div>
      <div class="grid g3" style="margin-top:14px">${regionCards}</div>
      <div class="grid g2" style="margin-top:14px">
        <div class="card"><h3>KS D per mass point</h3>${massChart(f)}</div>
        <div class="card"><h3>What the pipeline says</h3><dl class="kv">${rows.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("")}</dl></div>
      </div>
      <h2>Signal vs background <span class="k">plots</span></h2>
      <p class="muted prose">Each region page: every mass point vs background, combined signal vs background (pooled and equal-weight), and background alone, raw and normalized. Click the image to enlarge.</p>
      ${plotPanel(f, "plots_B", "MC vs data")}
      <h2>Barrel vs endcap <span class="k">plots</span></h2>
      <p class="muted prose">Shape page: the same sample in barrel and endcap. Separation page: signal vs background side by side in each region.</p>
      ${plotPanel(f, "plots_A", "barrel vs endcap")}`;
    const pick = app.querySelector("#fpick");
    pick.addEventListener("change", () => { if (feat(pick.value)) location.hash = "#/feature/" + fid(pick.value); });
    app.querySelectorAll(".plotpanel").forEach((pp) => {
      pp.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
        ui.plotTab[f.name + pp.dataset.key] = +b.dataset.i; VIEWS.feature(f.name);
        const again = app.querySelector(`.plotpanel[data-key="${pp.dataset.key}"]`);
        if (again) again.scrollIntoView({ block: "nearest" });
      }));
      const img = pp.querySelector("img");
      img.addEventListener("click", () => lightbox(img.src, img.alt, img.dataset.pdf));
    });
    app.querySelectorAll("svg rect[data-t]").forEach((r) => {
      r.addEventListener("mousemove", (e) => showTip(e, esc(r.dataset.t)));
      r.addEventListener("mouseleave", hideTip);
    });
  };

  // ------------------------------------------------------------------ BARREL VS ENDCAP
  VIEWS.regions = function () {
    const fs = RUN.features.filter((f) => f.A && f.A.D_endcap != null && f.A.D_barrel != null);
    const W = 620, H = 560, L = 50, B = 44, T = 14, R = 14;
    const x = (v) => L + (W - L - R) * v, y = (v) => T + (H - T - B) * (1 - v);
    const col = { both: "var(--ink)", "endcap only": "var(--endcap-ink)", "barrel only": "var(--barrel-ink)", neither: "var(--ink3)" };
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="D barrel versus D endcap per feature">`;
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((v) => {
      s += `<line class="gl" x1="${x(0)}" x2="${x(1)}" y1="${y(v)}" y2="${y(v)}"/><line class="gl" x1="${x(v)}" x2="${x(v)}" y1="${y(0)}" y2="${y(1)}"/>` +
        `<text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v.toFixed(1)}</text><text x="${x(v)}" y="${H - B + 16}" text-anchor="middle">${v.toFixed(1)}</text>`;
    });
    const w = P().WEAK_D || 0.2;
    s += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--rule)" stroke-dasharray="4 4"/>`;
    s += `<line x1="${x(w)}" x2="${x(w)}" y1="${y(0)}" y2="${y(1)}" stroke="var(--accent)" opacity=".35"/><line y1="${y(w)}" y2="${y(w)}" x1="${x(0)}" x2="${x(1)}" stroke="var(--accent)" opacity=".35"/>`;
    s += `<text class="lbl" x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">D ENDCAP</text><text class="lbl" transform="translate(13 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">D BARREL</text>`;
    fs.forEach((f) => {
      const hm = f.category === "htmiss-linked";
      s += `<circle cx="${x(f.A.D_endcap)}" cy="${y(f.A.D_barrel)}" r="${hm ? 5 : 4.2}" fill="${hm ? "var(--bg)" : col[f.A.separates] || "var(--ink3)"}" stroke="${hm ? "var(--accent)" : "var(--bg)"}" stroke-width="${hm ? 2 : 1}" data-f="${esc(f.name)}" style="cursor:pointer"/>`;
    });
    s += `</svg>`;
    const sorted = fs.slice().sort((a, b) => Math.abs(b.A.delta_barrel_minus_endcap) - Math.abs(a.A.delta_barrel_minus_endcap));
    const counts = {}; fs.forEach((f) => { counts[f.A.separates] = (counts[f.A.separates] || 0) + 1; });
    app.innerHTML = `
      <div class="eyebrow">Block A · barrel vs endcap</div>
      <h1>Barrel vs endcap</h1>
      <p class="lede">Each point is a feature: its combined KS D in the endcap (x) and the barrel (y). Points far from the diagonal separate in one region only.
      The barrel has ${int((RUN.region_audit.rows.find((r) => r.sample === "bkg") || {}).barrel)} background events against
      ${int((RUN.region_audit.rows.find((r) => r.sample === "bkg") || {}).endcap)} in the endcap, so its noise floor is higher. Click a point for the feature view.</p>
      <div class="grid g2" style="align-items:start">
        <div class="card">${s}<div class="legend">${Object.keys(col).map((k) => `<span><i style="background:${col[k]}"></i>${k} (${counts[k] || 0})</span>`).join("")}
          <span><i style="background:var(--bg);border:2px solid var(--accent)"></i>htmiss-linked</span><span class="muted">red lines: D = ${w} · ${fs.length} of ${RUN.features.length} features have a D in both regions</span></div></div>
        <div>
          <h3 style="margin-top:0">Largest barrel − endcap differences</h3>
          <div class="tablewrap" style="max-height:600px;overflow:auto"><table><thead><tr><th>feature</th><th class="n">endcap</th><th class="n">barrel</th><th class="n">Δ</th><th>separates</th></tr></thead>
          <tbody>${sorted.map((f) => `<tr class="click" data-f="${esc(f.name)}"><td><a class="fname" href="#/feature/${fid(f.name)}">${esc(f.name)}</a> ${catChip(f)}</td>
            <td class="n">${fmt(f.A.D_endcap)}</td><td class="n">${fmt(f.A.D_barrel)}</td><td class="n">${fmt(f.A.delta_barrel_minus_endcap)}</td><td>${esc(f.A.separates)}</td></tr>`).join("")}</tbody></table></div>
          <p class="small muted" style="margin-top:8px"><a href="results/${esc(RUN.name)}/A_barrel_vs_endcap/barrel_vs_endcap.csv" download>barrel_vs_endcap.csv</a></p>
        </div>
      </div>`;
    app.querySelectorAll("circle[data-f]").forEach((c) => {
      const f = feat(c.dataset.f);
      c.addEventListener("mousemove", (e) => showTip(e, `<b>${esc(f.name)}</b><br>endcap ${fmt(f.A.D_endcap)} · barrel ${fmt(f.A.D_barrel)}<br>${esc(f.A.separates)}${f.category ? " · " + esc(f.category) : ""}`));
      c.addEventListener("mouseleave", hideTip);
      c.addEventListener("click", () => { location.hash = "#/feature/" + fid(f.name); });
    });
    bindRows();
  };

  // ------------------------------------------------------------------ CORRELATION
  VIEWS.correlation = function (arg) {
    if (REGIONS.includes(arg)) ui.corrRegion = arg;
    const regs = Object.keys(RUN.corr);
    if (!regs.length) { app.innerHTML = `<h1>Correlation</h1><p class="muted">No correlation matrices in this run.</p>`; return; }
    if (!regs.includes(ui.corrRegion)) ui.corrRegion = regs[0];
    const r = ui.corrRegion, C = RUN.corr[r], N = C.features.length;
    const blocks = (RUN.blocks[r] || []).filter((b) => b.members.length > 1);
    const thr = P().CORR_BLOCK || 0.9;
    app.innerHTML = `
      <div class="eyebrow">Block C · redundancy on background</div>
      <h1>Correlation</h1>
      <p class="lede">Spearman rank correlation between features, computed on background events only (${esc(r)}, up to ${int(P().CORR_NMAX || 12000)} events).
      Red = positive, blue = negative, stronger colour = larger ${tex("|\\rho|")}. Features are ordered by KS D. A feature joins a redundancy block only if ${tex("|\\rho| \\ge " + thr)} with every member of the block.</p>
      <div class="toolbar"><div class="seg">${regs.map((x) => `<button type="button" class="${x === r ? "on " + x : ""}" data-r="${x}">${x}</button>`).join("")}</div>
        <span class="count">${N} × ${N} · ${blocks.length} blocks with more than one member</span></div>
      <div class="grid g2" style="align-items:start">
        <div class="heat-wrap"><canvas class="heat" id="heat"></canvas>
          <p class="small muted" id="heatSel" style="margin:10px 0 0">Hover a cell to read it; click to pin the pair.</p></div>
        <div>
          <h3 style="margin-top:0">Redundancy blocks · ${esc(r)}</h3>
          <div class="tablewrap" style="max-height:620px;overflow:auto"><table><thead><tr><th class="n">block</th><th>representative (kept)</th><th>other members</th></tr></thead>
          <tbody>${blocks.map((b) => `<tr><td class="n">${b.block}</td><td><a class="fname" href="#/feature/${fid(b.representative)}">${esc(b.representative)}</a>
            <div class="small muted">D ${fmt(b.D_equal[b.representative])}</div></td>
            <td>${b.members.filter((m) => m !== b.representative).map((m) => `<a class="fname" href="#/feature/${fid(m)}">${esc(m)}</a> <span class="small muted">${fmt(b.D_equal[m])}</span>`).join("<br>")}</td></tr>`).join("")}</tbody></table></div>
          <p class="small muted" style="margin-top:8px"><a href="results/${esc(RUN.name)}/C_correlation/spearman_bkg_${esc(r)}.csv" download>spearman_bkg_${esc(r)}.csv</a> ·
          <a href="results/${esc(RUN.name)}/gambit_inputs/blocks.json" download>blocks.json</a></p>
        </div>
      </div>`;
    app.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { location.hash = "#/correlation/" + b.dataset.r; }));
    const cv = app.querySelector("#heat");
    const avail = Math.min(620, app.querySelector(".heat-wrap").clientWidth - 22);
    const cell = Math.max(3, Math.floor(avail / N));
    const dpr = window.devicePixelRatio || 1;
    cv.width = N * cell * dpr; cv.height = N * cell * dpr;
    cv.style.width = N * cell + "px"; cv.style.height = N * cell + "px";
    const g = cv.getContext("2d");
    g.scale(dpr, dpr);
    const cs = getComputedStyle(document.documentElement);
    const hp = cs.getPropertyValue("--heat-pos").trim() || "232,35,10";
    const hn = cs.getPropertyValue("--heat-neg").trim() || "31,95,168";
    const h0 = cs.getPropertyValue("--heat-null").trim() || "#f1f0ec";
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
      const v = C.rho[i][j];
      if (v == null) { g.fillStyle = h0; } else {
        const a = Math.min(1, Math.abs(v));
        g.fillStyle = v >= 0 ? `rgba(${hp},${a})` : `rgba(${hn},${a})`;
      }
      g.fillRect(j * cell, i * cell, cell, cell);
    }
    const sel = app.querySelector("#heatSel");
    const cellAt = (e) => { const b = cv.getBoundingClientRect(); return [Math.floor((e.clientY - b.top) / cell), Math.floor((e.clientX - b.left) / cell)]; };
    cv.addEventListener("mousemove", (e) => {
      const [i, j] = cellAt(e);
      if (i < 0 || j < 0 || i >= N || j >= N) return hideTip();
      showTip(e, `${esc(C.features[i])}<br>${esc(C.features[j])}<br>ρ = ${fmt(C.rho[i][j])}`);
    });
    cv.addEventListener("mouseleave", hideTip);
    cv.addEventListener("click", (e) => {
      const [i, j] = cellAt(e);
      if (i < 0 || j < 0 || i >= N || j >= N) return;
      sel.innerHTML = `ρ = <b class="num">${fmt(C.rho[i][j])}</b> between <a href="#/feature/${fid(C.features[i])}">${esc(C.features[i])}</a> and <a href="#/feature/${fid(C.features[j])}">${esc(C.features[j])}</a>`;
    });
  };

  // ------------------------------------------------------------------ PROTOTYPES
  VIEWS.prototypes = function () {
    const sc = RUN.prototype_scores, protos = RUN.prototypes, names = Object.keys(protos).sort();
    const short2 = (k) => k.replace("AUC_NN1_", "").replace("AUC_NN2_", "");
    const pm = sc.length ? Object.keys(sc[0]).filter((k) => k.startsWith("AUC_NN1_")) : [];
    const pm2 = sc.length ? Object.keys(sc[0]).filter((k) => k.startsWith("AUC_NN2_")) : [];
    const nets = {};
    names.forEach((p) => Object.entries(protos[p].nets).forEach(([n, fs]) => { (nets[n] = nets[n] || new Set()); fs.forEach((x) => nets[n].add(x)); }));
    app.innerHTML = `
      <div class="eyebrow">Block D · candidate input sets</div>
      <h1>Prototypes</h1>
      <p class="lede">Four candidate NN1/NN2 input sets, each scored with a gradient-boosted surrogate (5-fold CV, equal weight per mass point).
      The surrogate only nominates: the real decision is made by GAMBIT with closure and G as referees.</p>
      <div class="grid g4">${names.map((p) => `<div class="card"><h3 style="margin-top:0">${esc(p)}</h3><p class="small">${esc(protos[p].description)}</p>
        <a class="btn sm" href="results/${esc(RUN.name)}/D_prototypes/${esc(p)}.txt" download>${esc(p)}.txt</a></div>`).join("")}</div>
      <h2>Surrogate <span class="k">scores</span></h2>
      <div class="tablewrap"><table><thead><tr><th>set</th><th>trained → evaluated</th><th class="n">n NN1</th><th class="n">n NN2</th>
        <th class="n">AUC NN1</th><th class="n">worst mass</th><th class="n">AUC NN2</th><th class="n">worst mass</th><th class="n" title="distance correlation between NN1 and NN2 surrogate scores on background">dCor bkg</th><th class="n">Spearman bkg</th></tr></thead>
        <tbody>${sc.map((r) => `<tr><td><b>${esc(r.prototype)}</b></td><td>${esc(r.trained_on)} → ${esc(r.evaluated_in)}</td><td class="n">${r.n_NN1}</td><td class="n">${r.n_NN2}</td>
          <td class="n">${fmt(r.AUC_NN1)}</td><td class="n">${fmt(r.AUCmin_NN1)}</td><td class="n">${fmt(r.AUC_NN2)}</td><td class="n">${fmt(r.AUCmin_NN2)}</td><td class="n">${fmt(r.dCor_bkg)}</td><td class="n">${fmt(r.spearman_bkg)}</td></tr>`).join("")}</tbody></table></div>
      <details><summary>AUC per mass point</summary>
        <div class="tablewrap"><table><thead><tr><th>set</th><th>region</th>${pm.map((k) => `<th class="n">NN1 ${esc(short2(k))}</th>`).join("")}${pm2.map((k) => `<th class="n">NN2 ${esc(short2(k))}</th>`).join("")}</tr></thead>
        <tbody>${sc.map((r) => `<tr><td>${esc(r.prototype)}</td><td>${esc(r.evaluated_in)}</td>${pm.map((k) => `<td class="n">${fmt(r[k])}</td>`).join("")}${pm2.map((k) => `<td class="n">${fmt(r[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>
      <h2>Which features are in which <span class="k">set</span></h2>
      ${Object.keys(nets).sort().map((n) => `<h3>${esc(n)}</h3><div class="tablewrap"><table><thead><tr><th>feature</th>${names.map((p) => `<th class="n">${esc(p)}</th>`).join("")}</tr></thead>
        <tbody>${[...nets[n]].map((x) => `<tr><td><a class="fname" href="#/feature/${fid(x)}">${esc(x)}</a> ${feat(x) ? catChip(feat(x)) : ""}</td>${names.map((p) => {
          const has = (protos[p].nets[n] || []).includes(x);
          return `<td class="n">${has ? "<b>●</b>" : protos[p].nets[n] ? '<span class="muted">·</span>' : '<span class="muted">n/a</span>'}</td>`;
        }).join("")}</tr>`).join("")}</tbody></table></div>`).join("")}
      <p class="small muted" style="margin-top:10px"><a href="results/${esc(RUN.name)}/D_prototypes/prototype_scores.csv" download>prototype_scores.csv</a></p>`;
  };

  // ------------------------------------------------------------------ EXCLUSIONS
  function exclState() {
    if (ui.excl && ui.excl.run === RUN.name) return ui.excl;
    const lines = (P().exclude_file || "").split(/\r?\n/).map((l) => l.split("#")[0].trim()).filter(Boolean);
    ui.excl = { run: RUN.name, sel: new Set(lines), extra: "", filter: "" };
    return ui.excl;
  }
  function exclText(st) {
    const by = {}, all = [...st.sel];
    all.forEach((n) => {
      const f = feat(n);
      const g = f ? (f.category || (f.suspicious ? "suspicious" : "physics features")) : "other columns / patterns";
      (by[g] = by[g] || []).push(n);
    });
    let t = `# exclude_features.txt  --  EDITABLE: features you want left out of kj_sigbg_mk5.py\n` +
      `# generated on the Exclusions page of the SIG/BG Feature Explorer, ${new Date().toISOString().slice(0, 10)}, from run ${RUN.name}\n` +
      `# One exact column name or glob per line; '#' starts a comment. Put this file in pipeline/ and rerun.\n` +
      `# Already removed by the script (HARD_EXCLUDE): labels, NN scores, weights, ids, htmiss_NOSYS, met_met_NOSYS, region selectors.\n`;
    Object.keys(by).sort().forEach((g) => { t += `\n# ${g}\n` + by[g].sort().join("\n") + "\n"; });
    const extra = st.extra.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (extra.length) t += `\n# patterns\n` + extra.join("\n") + "\n";
    return t;
  }
  VIEWS.exclusions = function () {
    const st = exclState();
    const ex = RUN.excluded;
    const hard = P().HARD_EXCLUDE || [];
    const pool = [];
    RUN.features.forEach((f) => { pool.push({ n: f.name, f }); (f.copies || []).forEach((c) => pool.push({ n: c, f, copyOf: f.name })); });
    const q = st.filter.toLowerCase();
    const shown = pool.filter((p) => !q || p.n.toLowerCase().includes(q));
    app.innerHTML = `
      <div class="eyebrow">what goes in, what stays out</div>
      <h1>Exclusions <span class="badge-edit">EDITABLE</span></h1>
      <p class="lede"><code>pipeline/exclude_features.txt</code> is the one file you are meant to edit. One column name or glob per line;
      the pipeline leaves those columns out of every block. This page cannot write to your disk: pick features below, check the preview, then
      <b>download</b> the file and drop it into <code>pipeline/</code> before the next run.</p>

      <h2>Left out of run <span class="k">${esc(RUN.name)}</span></h2>
      <div class="grid g4">${Object.entries(ex).map(([k, v]) => `<div class="stat"><div class="v">${v.length}</div><div class="l">${esc({
        not_ALL7: "not in all 7 files (never scored)", hard: "hard-excluded by the script", user: "user-excluded (exclude_features.txt)",
        non_numeric: "non-numeric", constant: "constant in every file" }[k] || k)}</div></div>`).join("")}</div>
      ${Object.entries(ex).map(([k, v]) => `<details><summary>${esc(k)} (${v.length})</summary><p class="mono small">${v.map(esc).join(" · ") || "<span class='muted'>none</span>"}</p></details>`).join("")}
      <details><summary>HARD_EXCLUDE patterns in the script (${hard.length})</summary>
        <p class="small muted">Case-insensitive regular expressions matched against the full column name. Edit <code>HARD_EXCLUDE</code> in <code>kj_sigbg_mk5.py</code> to change them.</p>
        <pre>${hard.map(esc).join("\n")}</pre></details>
      <details><summary>Current pipeline/exclude_features.txt</summary><pre>${esc(P().exclude_file || "(empty)")}</pre></details>

      <h2>Build a new <span class="k">exclude_features.txt</span></h2>
      <div class="toolbar">
        <button class="btn sm" type="button" data-a="hm">+ all htmiss-linked</button>
        <button class="btn sm" type="button" data-a="np">+ all non-physics / suspicious</button>
        <button class="btn sm" type="button" data-a="de">+ endcap drop suggestions</button>
        <button class="btn sm" type="button" data-a="db">+ barrel drop suggestions</button>
        <button class="btn sm" type="button" data-a="cl">clear</button>
        <span class="count">${st.sel.size} selected</span>
      </div>
      <div class="editor">
        <div>
          <input type="search" id="xf" placeholder="filter ${pool.length} columns" value="${esc(st.filter)}" style="width:100%;margin-bottom:8px" aria-label="Filter columns">
          <div class="picklist">${shown.map((p) => {
            const r = p.f.regions.endcap || p.f.regions.all;
            return `<label><input type="checkbox" data-n="${esc(p.n)}" ${st.sel.has(p.n) ? "checked" : ""}>${esc(p.n)} ${p.copyOf ? `<span class="chip">copy of ${esc(p.copyOf)}</span>` : catChip(p.f)}<span class="d">D ${fmt(r && r.D, 2)}</span></label>`;
          }).join("")}</div>
          <h3>Extra patterns (globs)</h3>
          <textarea id="xx" rows="4" style="width:100%" placeholder="e.g.  trigPassed_*   one per line">${esc(st.extra)}</textarea>
        </div>
        <div>
          <textarea class="out" id="xo" readonly aria-label="Preview of exclude_features.txt">${esc(exclText(st))}</textarea>
          <div class="toolbar"><button class="btn primary" type="button" id="xdl">Download exclude_features.txt</button>
            <button class="btn" type="button" id="xcp">Copy</button><span class="small muted" id="xmsg"></span></div>
          <p class="small muted">Then: replace <code>pipeline/exclude_features.txt</code>, run <code>python pipeline/kj_sigbg_mk5.py --round 2</code>,
          copy the new output folder into <code>results/</code> and run the site builder. Check <code>00_common/excluded_report.txt</code> under "user": every line should match at least one column.</p>
        </div>
      </div>`;
    const refreshOut = () => { app.querySelector("#xo").value = exclText(st); app.querySelector(".count").textContent = st.sel.size + " selected"; };
    app.querySelectorAll(".picklist input").forEach((c) => c.addEventListener("change", () => { if (c.checked) st.sel.add(c.dataset.n); else st.sel.delete(c.dataset.n); refreshOut(); }));
    app.querySelector("#xx").addEventListener("input", (e) => { st.extra = e.target.value; refreshOut(); });
    const xf = app.querySelector("#xf");
    xf.addEventListener("input", () => { st.filter = xf.value; const p = xf.selectionStart; VIEWS.exclusions(); const n = app.querySelector("#xf"); n.focus(); n.setSelectionRange(p, p); });
    app.querySelectorAll("[data-a]").forEach((b) => b.addEventListener("click", () => {
      const a = b.dataset.a;
      RUN.features.forEach((f) => {
        if (a === "hm" && f.category === "htmiss-linked") st.sel.add(f.name);
        if (a === "np" && (f.category === "non-physics" || f.suspicious)) st.sel.add(f.name);
        if (a === "de" && f.drop && f.drop.endcap) st.sel.add(f.name);
        if (a === "db" && f.drop && f.drop.barrel) st.sel.add(f.name);
      });
      if (a === "cl") st.sel.clear();
      VIEWS.exclusions();
    }));
    app.querySelector("#xdl").addEventListener("click", () => download("exclude_features.txt", exclText(st)));
    app.querySelector("#xcp").addEventListener("click", () => {
      const ta = app.querySelector("#xo"), msg = app.querySelector("#xmsg");
      const done = () => { msg.textContent = "copied"; setTimeout(() => { msg.textContent = ""; }, 1500); };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(ta.value).then(done, () => { ta.select(); document.execCommand("copy"); done(); });
      else { ta.removeAttribute("readonly"); ta.select(); document.execCommand("copy"); ta.setAttribute("readonly", ""); done(); }
    });
  };

  // ------------------------------------------------------------------ FINDINGS
  function jetFrac(rec) {
    const j = rec.jets && rec.jets.all;
    if (!j) return null;
    if (j.fractions) return [0, 1, 2, 3, 4].map((k) => j.fractions[String(k)] || 0);
    const n = j.n || Object.values(j.counts).reduce((a, b) => a + b, 0);
    return [0, 1, 2, 3, 4].map((k) => (j.counts[String(k)] || 0) / n);
  }
  function jetBars(sel) {
    const order = ["bkg", ...RUN.masses];
    const shades = ["var(--jet0)", "var(--jet1)", "var(--jet2)", "var(--jet3)", "var(--jet4)"];
    const W = 700, rowH = 26, L = 120, H = order.length * rowH + 30;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Jet multiplicity per sample">`;
    order.forEach((k, i) => {
      const rec = sel.samples[k];
      if (!rec) return;
      const fr = jetFrac(rec);
      let x = L;
      const y = 6 + i * rowH;
      s += `<text x="${L - 8}" y="${y + 15}" text-anchor="end" style="${k === "bkg" ? "font-weight:700;fill:var(--ink)" : ""}">${k === "bkg" ? "background" : esc(k)}</text>`;
      fr.forEach((v, j) => {
        const w = v * (W - L - 10);
        if (w > 0) s += `<rect x="${x}" y="${y}" width="${w}" height="${rowH - 6}" fill="${shades[j]}" data-t="${k === "bkg" ? "background" : esc(k)} · ${j === 4 ? "4+" : j} jets: ${(v * 100).toFixed(1)}%"/>`;
        if (w > 34) s += `<text x="${x + w / 2}" y="${y + 14}" text-anchor="middle" style="fill:#fff;stroke:rgba(0,0,0,.65);stroke-width:3px;paint-order:stroke">${(v * 100).toFixed(0)}%</text>`;
        x += w;
      });
    });
    s += `</svg>`;
    return s + `<div class="legend">${["0 jets", "1 jet", "2 jets", "3 jets", "4+ jets"].map((l, j) => `<span><i style="background:${shades[j]}"></i>${l}</span>`).join("")}</div>`;
  }
  function scalarBars(bins) {
    const W = 700, H = 220, L = 60, B = 40, T = 10;
    const mx = Math.max(...bins.map((b) => b.n));
    const bw = (W - L - 10) / bins.length;
    const y = (v) => T + (H - T - B) * (1 - v / mx);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Background htmissScalar distribution">`;
    [0, 0.5, 1].forEach((f) => { s += `<line class="gl" x1="${L}" x2="${W - 6}" y1="${y(mx * f)}" y2="${y(mx * f)}"/><text x="${L - 6}" y="${y(mx * f) + 4}" text-anchor="end">${int(Math.round(mx * f))}</text>`; });
    bins.forEach((b, i) => {
      const lab = b.lo < 0 ? "~0" : `${b.lo}–${b.hi >= 1000 ? "∞" : b.hi}`;
      const empty = b.n === 0;
      s += `<rect x="${L + i * bw + 3}" y="${y(b.n)}" width="${bw - 6}" height="${y(0) - y(b.n)}" fill="${b.lo === 40 ? "var(--accent)" : "var(--ink)"}" data-t="${lab} GeV: ${int(b.n)} events"/>`;
      if (empty) s += `<text x="${L + i * bw + bw / 2}" y="${y(0) - 6}" text-anchor="middle" style="fill:var(--accent)">0</text>`;
      s += `<text x="${L + i * bw + bw / 2}" y="${H - 22}" text-anchor="middle">${lab}</text>`;
    });
    s += `<text class="lbl" x="${(L + W) / 2}" y="${H - 4}" text-anchor="middle">BACKGROUND htmissScalar_NOSYS [GeV]</text></svg>`;
    return s;
  }
  function jetSection() {
    const fs = RUN.features.filter((f) => f.bkg_split && f.bkg_split.endcap).sort((a, b) => b.bkg_split.endcap.D - a.bkg_split.endcap.D);
    if (!fs.length) return "";
    const dep = fs.filter((f) => jetDep(f, "endcap"));
    const unflagged = dep.filter((f) => !f.category);
    const m = RUN.bkg_split_meta || {};
    return `
      <h2>5 · Which features depend on <span class="k">jet activity</span></h2>
      <p class="prose"><b>Measured.</b> Inside the background alone, compare events with 0–1 jets (htmissScalar &lt; 40 GeV) against events with 2+ jets (&ge; 40 GeV).
      A feature that differs between the two populations depends on jet activity, so part of its signal-vs-background separation can come from the jet-count difference
      in section 3. In the endcap, <b>${dep.length}</b> of ${fs.length} features differ with D &ge; ${JET_DEP}; <b>${unflagged.length}</b> of those are <em>not</em> flagged htmiss-linked.</p>
      <div class="tablewrap" style="max-height:520px;overflow:auto"><table><thead><tr><th>feature</th><th class="n">bkg split D endcap</th><th class="n">barrel</th><th class="n">signal vs bkg D endcap</th><th>flags</th><th>NN lists</th></tr></thead>
        <tbody>${dep.map((f) => `<tr class="click" data-f="${esc(f.name)}"><td><a class="fname" href="#/feature/${fid(f.name)}">${esc(f.name)}</a></td>
          <td class="n"><b>${fmt(f.bkg_split.endcap.D)}</b></td><td class="n">${fmt(f.bkg_split.barrel && f.bkg_split.barrel.D)}</td>
          <td class="n">${fmt(f.regions.endcap && f.regions.endcap.D)}</td><td>${catChip(f) || '<span class="chip jet">not flagged</span>'}</td><td>${nnChips(f)}</td></tr>`).join("")}</tbody></table></div>
      <p class="small muted" style="margin-top:8px">Source: <code>${esc(m.source || "")}/bkg_split.csv</code> (${esc(m.cut || "")}; ${esc(m.meaning || "")}). Also on every feature page.</p>`;
  }
  VIEWS.findings = function () {
    const sel = RUN.selection;
    const hl = P().HTMISS_LINKED || [];
    const hlRows = hl.map((n) => feat(n)).filter(Boolean);
    const nnFlag = RUN.features.filter((f) => (f.nn_lists || []).length && f.category);
    const metDphi = feat("MSVtx_MET_dphi_raw");
    let body = `
      <div class="eyebrow">read this before any ranking</div>
      <h1>Findings</h1>
      <p class="lede">How the two samples were selected, measured from the files themselves, and what that does to the separation scores.
      Measured facts and interpretation are kept apart: each section says which is which.</p>

      <h2>1 · The samples are disjoint in <span class="k">HTmiss</span></h2>
      <p class="prose"><b>Measured.</b> Background (data, <code>DataHTMissLow</code>) has <code>htmiss_NOSYS</code> &lt; 40 GeV in every event; every signal event has
      <code>htmiss_NOSYS</code> &ge; 40 GeV. The pipeline's unit test checks this on every run:</p>
      <pre>${esc(RUN.unit_test)}</pre>
      <p class="prose"><b>Consequence.</b> <code>htmiss_NOSYS</code> separates the files perfectly by construction, which is why the script hard-excludes it
      (with <code>met_met_NOSYS</code>). A comparison with both samples above 40 GeV cannot be built from these files: no background would be left.</p>`;
    if (sel) {
      const b = sel.samples.bkg;
      const ct = b.crosstab_jets_x_scalar || {};
      const bands = ["~0", "1-40", ">40"];
      body += `
      <h2>2 · The background is three <span class="k">jet-count</span> populations</h2>
      <p class="prose"><b>Measured.</b> In the background, <code>htmissScalar_NOSYS</code> maps one-to-one onto the number of jets:</p>
      <div class="tablewrap" style="max-width:640px"><table><thead><tr><th>jets</th>${bands.map((x) => `<th class="n">htmissScalar ${x} GeV</th>`).join("")}<th class="n">share</th></tr></thead>
        <tbody>${Object.entries(ct).map(([j, row]) => { const tot = bands.reduce((a, x) => a + (row[x] || 0), 0);
          return `<tr><td class="num">${j === "4" ? "4+" : j}</td>${bands.map((x) => `<td class="n" style="${row[x] ? "font-weight:700" : "color:var(--ink3)"}">${int(row[x] || 0)}</td>`).join("")}<td class="n">${(100 * tot / b.n).toFixed(1)}%</td></tr>`; }).join("")}</tbody></table></div>
      ${b.scalar_bins ? `<div class="card narrow" style="margin-top:14px">${scalarBars(b.scalar_bins)}<p class="small muted">No background event lies between 40 and 50 GeV.</p></div>` : ""}
      <p class="prose" style="margin-top:12px"><b>Interpretation.</b> Zero-jet events sit at ~0. One-jet events have scalar = vector HTmiss, so the &lt; 40 GeV selection caps them.
      Two or more jets above a ~25 GeV threshold already sum past 50 GeV, which leaves the 40–50 GeV gap.</p>
      ${b.bkg_surviving_scalar_cut ? `<details><summary>Background surviving an htmissScalar cut</summary><div class="tablewrap"><table><thead><tr><th class="n">cut [GeV]</th><th class="n">barrel (of ${int((RUN.region_audit.rows[0] || {}).barrel)})</th><th class="n">endcap (of ${int((RUN.region_audit.rows[0] || {}).endcap)})</th></tr></thead>
        <tbody>${b.bkg_surviving_scalar_cut.map((r) => `<tr><td class="n">${r.gev}</td><td class="n">${int(r.barrel)}</td><td class="n">${int(r.endcap)}</td></tr>`).join("")}</tbody></table></div>
        <p class="small muted">Identical counts from 40 to 50 GeV: the survivors are the 2+-jet background, not background in the signal region.</p></details>` : ""}

      <h2>3 · Signal has almost no <span class="k">zero-jet</span> events</h2>
      <p class="prose"><b>Measured.</b> ${((jetFrac(b) || [0])[0] * 100).toFixed(1)}% of background events have no jet; signal has 0–${(Math.max(...RUN.masses.map((m) => (sel.samples[m] ? jetFrac(sel.samples[m])[0] : 0))) * 100).toFixed(1)}%
      depending on mass point, and skews to high jet counts (more so for heavier masses).</p>
      <div class="card narrow">${jetBars(sel)}</div>`;
    }
    body += `
${sel && sel.samples.bkg.met_median != null ? `
      <h2>4 · A second edge: <span class="k">MET</span></h2>
      <p class="prose"><b>Measured.</b> Every signal event has <code>met_met_NOSYS</code> &ge; ${fmt(Math.min(...RUN.masses.map((m) => sel.samples[m].met_min)), 2)} GeV;
      ${fmt(sel.samples.bkg.met_pct_below_20, 1)}% of background is below ${sel.met_cut_gev || 20} GeV (background median ${fmt(sel.samples.bkg.met_median, 1)} GeV).</p>
      <div class="tablewrap narrow"><table><thead><tr><th>sample</th><th class="n">min</th><th class="n">0.1%</th><th class="n">1%</th><th class="n">median</th><th class="n">% below 20</th></tr></thead>
        <tbody>${["bkg", ...RUN.masses].map((k) => { const x = sel.samples[k]; return `<tr><td class="num">${k === "bkg" ? "background" : esc(k)}</td><td class="n">${fmt(x.met_min, 2)}</td><td class="n">${fmt(x.met_q001, 2)}</td><td class="n">${fmt(x.met_q01, 2)}</td><td class="n">${fmt(x.met_median, 2)}</td><td class="n">${fmt(x.met_pct_below_20, 2)}</td></tr>`; }).join("")}</tbody></table></div>
      <p class="prose" style="margin-top:10px"><b>Open.</b> All six minima sit just above 20 GeV, which looks like an explicit MET cut in the signal selection. It may instead follow from HTmiss &ge; 40 GeV. The MET-family features (<code>met_*</code>) are already flagged; the question is for whoever made the files.</p>` : ""}
      ${jetSection()}
      <h2>6 · What this means for the <span class="k">rankings</span></h2>
      <p class="prose"><b>Interpretation.</b> A large KS D for any feature tied to HTmiss or jet activity mostly measures the selection, not the LLP.
      The pipeline flags ${hl.length} such features as <span class="chip htmiss">htmiss-linked</span>, keeps them out of the GAMBIT pool and out of prototype P2:</p>
      <div class="tablewrap" style="max-width:760px"><table><thead><tr><th>htmiss-linked feature</th><th class="n">D endcap</th><th class="n">D barrel</th><th>NN lists</th></tr></thead>
        <tbody>${hlRows.map((f) => `<tr class="click" data-f="${esc(f.name)}"><td><a class="fname" href="#/feature/${fid(f.name)}">${esc(f.name)}</a></td><td class="n">${fmt(f.regions.endcap && f.regions.endcap.D)}</td><td class="n">${fmt(f.regions.barrel && f.regions.barrel.D)}</td><td>${nnChips(f)}</td></tr>`).join("")}</tbody></table></div>
      <ul class="prose" style="margin-top:12px">
        <li>Within a jet-count bin the HTmiss cut is still there (one-jet signal has its jet above ~40 GeV, one-jet background below), so jet-pT features stay selection-driven even after matching jet counts.</li>
        <li>What a jet-count-matched comparison <em>can</em> remove is the separation that comes purely from jet multiplicity, the largest single effect.</li>
        <li>NN-list features that carry a flag: ${nnFlag.length ? nnFlag.map((f) => `<a href="#/feature/${fid(f.name)}">${esc(f.name)}</a>`).join(", ") : "none"}.</li>
        <li>NN-list features that are jet-dependent in the background but carry no flag: ${(() => { const l = RUN.features.filter((f) => (f.nn_lists || []).length && !f.category && REGIONS.some((r) => r !== "all" && jetDep(f, r)));
          return l.length ? l.map((f) => `<a href="#/feature/${fid(f.name)}">${esc(f.name)}</a> (${nnChips(f)})`).join(", ") : "none"; })()}.</li>
      </ul>

      <h2>7 · Open questions <span class="k">for review</span></h2>
      <ul class="prose">
        <li><b>Training region vs signal region.</b> Training on low-HTmiss data and applying the networks in the high-HTmiss signal region is a legitimate design only if the NN inputs do not depend on HTmiss or jet activity. The flags above are the evidence to check that.</li>
        ${metDphi ? `<li><b><code>MSVtx_MET_dphi_raw</code></b> is in the NN2 lists (${nnChips(metDphi) || "–"}) and is <em>not</em> flagged htmiss-linked (D endcap ${fmt(metDphi.regions.endcap && metDphi.regions.endcap.D)}). In a low-HTmiss sample the MET is small and its direction close to random, so part of its separation may also come from the selection.</li>` : ""}
        <li><b>Zero-jet background.</b> Nearly half the training background has no jet, a population with no counterpart in signal. It is a candidate source of multimodal background behaviour and of poor closure in the HTmiss&nbsp;≈&nbsp;0 slice.</li>
      </ul>
      ${sel ? `<p class="small muted" style="margin-top:16px">Source of sections 2–3: <code>${esc(sel.source)}</code> (${esc(sel.written)}).
      Regenerate with <code>python tools/selection_check.py</code> · <a href="results/${esc(RUN.name)}/E_selection/selection_check.txt" download>selection_check.txt</a></p>` : ""}`;
    app.innerHTML = body;
    app.querySelectorAll("svg [data-t]").forEach((r) => { r.addEventListener("mousemove", (e) => showTip(e, esc(r.dataset.t))); r.addEventListener("mouseleave", hideTip); });
    bindRows();
  };



  // ------------------------------------------------------------------ GRAPHS (one split = one page out of every feature PDF)
  // Split definitions come from the builder (RUN.splits, with the pre-built bundle PDF). This copy is the fallback
  // for a run built before splits existed: same pages, no bundles.
  const SPLIT_FALLBACK = [
    { id: "sb_endcap", group: "sig_bkg", short: "endcap", block: "B", label: "endcap", order: "endcap", title: "Signal vs background · endcap" },
    { id: "sb_barrel", group: "sig_bkg", short: "barrel", block: "B", label: "barrel", order: "barrel", title: "Signal vs background · barrel" },
    { id: "sb_all", group: "sig_bkg", short: "all", block: "B", label: "all", order: "all", title: "Signal vs background · barrel + endcap" },
    { id: "sb_side", group: "sig_bkg", short: "endcap | barrel", block: "A", label: "separation", order: "A", title: "Signal vs background · endcap | barrel side by side" },
    { id: "be_shape", group: "bar_end", short: "shape", block: "A", label: "shape", order: "A", title: "Barrel vs endcap · shape of background and of signal" },
  ];
  const SPLIT_GROUPS = [
    ["sig_bkg", "Signal vs background", "MC signal against data background, per region"],
    ["bar_end", "Barrel vs endcap", "the same sample in the two regions"],
  ];
  const SPLIT_TONE = { sb_endcap: "endcap", sb_barrel: "barrel", sb_all: "all", sb_side: "side", be_shape: "shape" };
  const PDFLIB_URL = "https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/dist/pdf-lib.min.js";
  const G_SIZES = { S: 240, M: 380, L: 620 };
  const G_SORTS = [
    ["endcap", "endcap D (rank)"], ["barrel", "barrel D (rank)"], ["all", "barrel + endcap D (rank)"],
    ["delta", "|D barrel − D endcap|"], ["shape_bkg", "shape D · background"], ["shape_sig", "shape D · signal"], ["name", "name"],
  ];
  const splitList = () => (RUN.splits && RUN.splits.length ? RUN.splits : SPLIT_FALLBACK);
  function splitPage(f, sp) {
    const pl = f[sp.block === "B" ? "plots_B" : "plots_A"];
    if (!pl) return null;
    const k = pl.pages.findIndex((p) => p.label === sp.label);
    return k < 0 ? null : { src: pl.pages[k].src, pdf: pl.pdf, k };
  }
  const splitRegions = (sp) => (sp.order === "A" ? ["endcap", "barrel"] : [sp.order]);
  function splitStat(f, sp) {
    if (sp.order !== "A") {
      const x = f.regions[sp.order];
      return x ? `D <b>${fmt(x.D)}</b> · rank ${x.rank}${separates(x) ? "" : ` · <span class="muted">below "separates"</span>`}` : `<span class="muted">not scored</span>`;
    }
    const A = f.A || {};
    return sp.label === "shape" ? `shape D · bkg <b>${fmt(A.shape_D_bkg)}</b> · sig <b>${fmt(A.shape_D_sig)}</b>`
      : `endcap <b>${fmt(A.D_endcap)}</b> · barrel <b>${fmt(A.D_barrel)}</b> · Δ ${fmt(A.delta_barrel_minus_endcap)}`;
  }
  function gSortKey(k) {   // returns value where larger = earlier; null sorts last
    const A = (f) => f.A || {};
    return {
      endcap: (f) => (f.regions.endcap || {}).D, barrel: (f) => (f.regions.barrel || {}).D, all: (f) => (f.regions.all || {}).D,
      delta: (f) => (A(f).delta_barrel_minus_endcap == null ? null : Math.abs(A(f).delta_barrel_minus_endcap)),
      shape_bkg: (f) => A(f).shape_D_bkg, shape_sig: (f) => A(f).shape_D_sig,
    }[k];
  }
  const gDefaultSort = (sp) => (sp.order === "A" ? "delta" : sp.order);
  function loadScript(url) {
    return new Promise((ok, bad) => {
      const s = document.createElement("script");
      s.src = url; s.onload = ok; s.onerror = () => bad(new Error("could not load " + url));
      document.head.appendChild(s);
    });
  }
  function lightboxNav(items, start) {
    let i = start;
    const lb = document.createElement("div");
    lb.className = "lightbox";
    const draw = () => {
      const it = items[i];
      lb.innerHTML = `<img src="${esc(it.src)}" alt="${esc(it.caption)}">
        <div class="lb-bar"><button type="button" data-d="-1" ${i ? "" : "disabled"} aria-label="Previous">←</button>
        <span class="lb-cap">${i + 1} / ${items.length} · ${esc(it.caption)}</span>
        <button type="button" data-d="1" ${i < items.length - 1 ? "" : "disabled"} aria-label="Next">→</button>
        <a href="${esc(it.pdf)}#page=${it.k + 1}" target="_blank" rel="noopener">open PDF p${it.k + 1}</a>
        <a href="${esc(it.pdf)}" download>download PDF</a><a href="${esc(it.src)}" download>PNG</a>
        ${it.feature ? `<a href="#/feature/${fid(it.feature)}" data-go>feature page</a>` : ""}<button type="button" data-x>close (Esc)</button></div>`;
    };
    const step = (d) => { const j = i + d; if (j >= 0 && j < items.length) { i = j; draw(); } };
    const close = () => { lb.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    };
    lb.addEventListener("click", (e) => {
      const t = e.target;
      if (t === lb || t.hasAttribute("data-x") || t.hasAttribute("data-go")) close();
      else if (t.dataset.d) step(+t.dataset.d);
    });
    document.addEventListener("keydown", onKey);
    draw();
    document.body.appendChild(lb);
  }

  VIEWS.graphs = function (arg) {
    const all = splitList();
    const want = (arg || "").split("+").filter((id) => all.some((s) => s.id === id));
    if (want.length) ui.gSplits = want;
    if (!ui.gSplits || !ui.gSplits.length) ui.gSplits = ["sb_endcap", "sb_barrel"];
    const sel = all.filter((s) => ui.gSplits.includes(s.id));
    if (!sel.length) { location.replace("#/graphs/sb_endcap+sb_barrel"); return; }
    ui.gSize = ui.gSize || "M";
    if (ui.gSortAuto !== false || !ui.gSort) ui.gSort = gDefaultSort(sel[0]);
    const regs = [...new Set(sel.flatMap(splitRegions))];

    // filters (shared with Rankings) + search
    let list = RUN.features.slice();
    const q = (ui.gQ || "").trim().toLowerCase();
    if (q) list = list.filter((f) => f.name.toLowerCase().includes(q));
    if (ui.hideHM) list = list.filter((f) => f.category !== "htmiss-linked");
    if (ui.hideNP) list = list.filter((f) => f.category !== "non-physics" && !f.suspicious);
    if (ui.hideJet) list = list.filter((f) => !regs.some((r) => jetDep(f, r)));
    if (ui.onlyNN) list = list.filter((f) => (f.nn_lists || []).length);
    if (ui.onlySep) list = list.filter((f) => regs.some((r) => separates(f.regions[r])));
    list = list.filter((f) => sel.some((sp) => splitPage(f, sp)));
    if (ui.gSort === "name") list.sort((a, b) => a.name.localeCompare(b.name));
    else {
      const key = gSortKey(ui.gSort);
      list.sort((a, b) => { const A = key(a), B = key(b); return (A == null) - (B == null) || (B || 0) - (A || 0) || a.name.localeCompare(b.name); });
    }

    // every image in view order: feature by feature, split by split (same order as the PDF download)
    const items = [];
    list.forEach((f) => sel.forEach((sp) => {
      const pg = splitPage(f, sp);
      if (pg) items.push({ f, sp, ...pg, feature: f.name, caption: `${f.name} · ${sp.title}` });
    }));
    const idx = new Map(items.map((it, n) => [it.f.name + "|" + it.sp.id, n]));
    const nTotal = RUN.features.length;
    const isFile = location.protocol === "file:";

    const tile = (sp) => {
      const on = ui.gSplits.includes(sp.id), b = sp.bundle;
      return `<div class="stile ${SPLIT_TONE[sp.id] || ""} ${on ? "on" : ""}">
        <button type="button" data-s="${esc(sp.id)}" aria-pressed="${on}"><span class="tick" aria-hidden="true"></span>${esc(sp.short)}</button>
        ${b ? `<a href="${esc(b.href)}" download title="every feature's ${esc(sp.label)} page in one PDF, bookmarked per feature">PDF · ${b.pages} p · ${kb(b.bytes)}</a>` : `<span class="muted small">no bundle (rebuild)</span>`}
      </div>`;
    };
    const fig = (f, sp, caption) => {
      const pg = splitPage(f, sp);
      if (!pg) return `<figure class="gfig none"><div class="gnone">no ${esc(sp.label)} page in this feature's PDF<br><span class="muted">the pipeline skipped this region for ${esc(f.name)}</span></div>
        <figcaption><span class="chip ${SPLIT_TONE[sp.id]}">${esc(sp.short)}</span></figcaption></figure>`;
      const n = idx.get(f.name + "|" + sp.id);
      return `<figure class="gfig"><img src="${esc(pg.src)}" alt="${esc(f.name)} · ${esc(sp.title)}" loading="lazy" data-n="${n}">
        <figcaption>${caption}<span class="gstat">${splitStat(f, sp)}</span>
        <a class="gpdf" href="${esc(pg.pdf)}#page=${pg.k + 1}" target="_blank" rel="noopener" title="open the feature PDF at this page">PDF p${pg.k + 1}</a></figcaption></figure>`;
    };
    const jetMulti = (f) => {
      const on = regs.filter((r) => jetDep(f, r));
      return on.length ? `<span class="chip jet" title="background 0-1 jets vs 2+ jets (mk2 background split)">jet-dep ${on.map((r) => `${r} ${fmt(f.bkg_split[r].D, 2)}`).join(" · ")}</span>` : "";
    };
    const flags = (f) => catChip(f) + jetMulti(f) + nnChips(f);
    let body;
    if (!list.length) body = `<p class="muted">No features match the filters.</p>`;
    else if (sel.length === 1) {
      const sp = sel[0];
      body = `<div class="ggrid" style="--gmin:${G_SIZES[ui.gSize]}px">${list.map((f, i) =>
        fig(f, sp, `<span class="gname"><span class="gnum">${i + 1}</span><a class="fname" href="#/feature/${fid(f.name)}">${esc(f.name)}</a></span><span class="gflags">${flags(f)}</span>`)).join("")}</div>`;
    } else {
      body = `<div class="gcolhead" style="--gcols:${sel.length}">${sel.map((sp) => `<div class="${SPLIT_TONE[sp.id]}">${esc(sp.title)}</div>`).join("")}</div>
        ${list.map((f, i) => `<section class="grow">
          <div class="grow-head"><span class="gnum">${i + 1}</span><a class="fname" href="#/feature/${fid(f.name)}">${esc(f.name)}</a><span class="gflags">${flags(f)}</span>
            ${f.plots_B ? `<a class="btn sm" href="${esc(f.plots_B.pdf)}" download title="${esc(f.name)}: signal vs background, every region">PDF · S/B</a>` : ""}
            ${f.plots_A ? `<a class="btn sm" href="${esc(f.plots_A.pdf)}" download title="${esc(f.name)}: barrel vs endcap">PDF · B/E</a>` : ""}</div>
          <div class="gcols" style="--gcols:${sel.length}">${sel.map((sp) => fig(f, sp, `<span class="chip ${SPLIT_TONE[sp.id]}">${esc(sp.short)}</span>`)).join("")}</div>
        </section>`).join("")}`;
    }

    app.innerHTML = `
      <div class="eyebrow">every graph · pick the split</div>
      <h1>Graphs</h1>
      <p class="lede">Choose one or more splits. One split shows that page from every feature's PDF as a grid. Several splits show one row per
      feature with the splits side by side. Click any plot to enlarge it, then use ← → to step through everything on screen.</p>
      <div class="smatrix">${SPLIT_GROUPS.map(([g, t, d]) => `<div class="srow"><div class="slab"><b>${esc(t)}</b><span>${esc(d)}</span></div>
        <div class="stiles">${all.filter((s) => s.group === g).map(tile).join("")}</div></div>`).join("")}</div>
      <div class="toolbar">
        <input type="search" id="gq" placeholder="search feature name" value="${esc(ui.gQ || "")}" aria-label="Search features">
        <label>sort <select id="gsort">${G_SORTS.map(([k, l]) => `<option value="${k}" ${k === ui.gSort ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        ${sel.length === 1 ? `<div class="seg" aria-label="Plot size">${Object.keys(G_SIZES).map((k) => `<button type="button" data-z="${k}" class="${k === ui.gSize ? "on" : ""}">${k}</button>`).join("")}</div>` : ""}
        <span class="count">${list.length} of ${nTotal} features · ${items.length} plots</span>
      </div>
      <div class="toolbar" style="margin-top:-6px">
        <label><input type="checkbox" id="ghm" ${ui.hideHM ? "checked" : ""}> hide htmiss-linked</label>
        <label><input type="checkbox" id="gnp" ${ui.hideNP ? "checked" : ""}> hide non-physics / suspicious</label>
        <label title="jet-dependent in any region shown"><input type="checkbox" id="gjd" ${ui.hideJet ? "checked" : ""}> hide jet-dependent</label>
        <label><input type="checkbox" id="gnn" ${ui.onlyNN ? "checked" : ""}> only NN-list features</label>
        <label title="separates in at least one region shown"><input type="checkbox" id="gsp" ${ui.onlySep ? "checked" : ""}> only "separates"</label>
      </div>
      <div class="gdl">
        <button class="btn primary" type="button" id="gdl" ${items.length && !isFile ? "" : "disabled"}>Download this view as one PDF · ${items.length} pages</button>
        <div class="gprog" id="gprog" hidden><div class="pbar"><i></i></div><span class="small mono"></span></div>
        <span class="small muted">${isFile ? `Opened from a file, so the browser won't let this page read the PDFs. The per-split PDFs above work anyway;
          for a filtered PDF, serve the folder (<code>python -m http.server</code> in the repo, then open <code>localhost:8000</code>) or use GitHub Pages.`
          : "Pages in the order shown, filters applied, built in your browser from the original vector PDFs. The PDF links on the split tiles are the unfiltered versions."}</span>
      </div>
      ${body}`;

    app.querySelectorAll(".stile button[data-s]").forEach((b) => b.addEventListener("click", () => {
      const id = b.dataset.s;
      let next = ui.gSplits.includes(id) ? ui.gSplits.filter((x) => x !== id) : [...ui.gSplits, id];
      if (!next.length) next = [id];
      next = all.map((s) => s.id).filter((x) => next.includes(x));   // keep the matrix order
      ui.gSplits = next;
      location.hash = "#/graphs/" + next.join("+");
    }));
    const rerender = () => { const y = window.scrollY; VIEWS.graphs(); window.scrollTo(0, y); };
    const gq = app.querySelector("#gq");
    gq.addEventListener("input", () => { ui.gQ = gq.value; const p = gq.selectionStart; rerender(); const n = app.querySelector("#gq"); n.focus(); n.setSelectionRange(p, p); });
    app.querySelector("#gsort").addEventListener("change", (e) => { ui.gSort = e.target.value; ui.gSortAuto = false; rerender(); });
    app.querySelectorAll("[data-z]").forEach((b) => b.addEventListener("click", () => { ui.gSize = b.dataset.z; rerender(); }));
    [["ghm", "hideHM"], ["gnp", "hideNP"], ["gjd", "hideJet"], ["gnn", "onlyNN"], ["gsp", "onlySep"]].forEach(([id, k]) =>
      app.querySelector("#" + id).addEventListener("change", (e) => { ui[k] = e.target.checked; rerender(); }));
    app.querySelectorAll("img[data-n]").forEach((img) => img.addEventListener("click", () => lightboxNav(items, +img.dataset.n)));

    const btn = app.querySelector("#gdl");
    btn.addEventListener("click", async () => {
      const prog = app.querySelector("#gprog"), barEl = prog.querySelector("i"), txt = prog.querySelector("span");
      const say = (i, n, label) => { barEl.style.width = (100 * i / Math.max(1, n)).toFixed(1) + "%"; txt.textContent = `${i} / ${n} · ${label}`; };
      btn.disabled = true; prog.hidden = false; say(0, items.length, "loading pdf-lib");
      try {
        if (!window.PDFLib) await loadScript(PDFLIB_URL);
        const { PDFDocument } = window.PDFLib;
        const out = await PDFDocument.create();
        const cache = new Map();
        for (let n = 0; n < items.length; n++) {
          const it = items[n];
          let doc = cache.get(it.pdf);
          if (!doc) {
            const res = await fetch(it.pdf);
            if (!res.ok) throw new Error(`${it.pdf}: HTTP ${res.status}`);
            doc = await PDFDocument.load(await res.arrayBuffer());
            cache.set(it.pdf, doc);
            if (cache.size > 6) cache.delete(cache.keys().next().value);
          }
          const [p] = await out.copyPages(doc, [it.k]);
          out.addPage(p);
          say(n + 1, items.length, `${it.f.name} · ${it.sp.short}`);
        }
        say(items.length, items.length, "writing PDF");
        out.setTitle(`SIG/BG Feature Explorer · ${RUN.name} · ${sel.map((s) => s.title).join(" + ")}`);
        out.setSubject(`${list.length} features, ${items.length} pages, in the order shown on the Graphs page`);
        out.setCreator("SIG/BG Feature Explorer (pdf-lib, in the browser)");
        const bytes = await out.save();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
        a.download = `sigbg_${RUN.name}_${sel.map((s) => s.id).join("+")}_${list.length}features.pdf`;
        document.body.appendChild(a); a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
        txt.textContent = `done · ${items.length} pages · ${kb(bytes.length)}`;
      } catch (err) {
        txt.textContent = "failed: " + err.message;
      }
      btn.disabled = false;
    });
  };

  // ------------------------------------------------------------------ ALL PLOTS (every page of every PDF, current + archive)
  function loadArchivePlots(cb) {
    if (S.archivePlots) { cb(); return; }
    const s = document.createElement("script");
    s.src = "data/archive_plots.js";
    s.onload = cb;
    s.onerror = () => { S.archivePlots = {}; cb(); };
    document.head.appendChild(s);
  }
  function plotSources() {
    const src = [{ id: RUN.name, label: `${RUN.name} · current`, status: "current" }];
    ((I.archive && I.archive.entries) || []).forEach((e) => (e.runs || []).forEach((r) => {
      if (!r.folder.startsWith("..")) src.push({ id: r.folder, label: r.label, status: r.status, note: r.note });
    }));
    return src;
  }
  function currentRunPdfs() {
    const out = RUN.summaries.map((s) => ({ name: s.block + " summary", path: s.pdf.split("/").slice(2).join("/"), href: s.pdf, pages: s.pages }));
    byRank("endcap").forEach((f) => {
      if (f.plots_B) out.push({ name: f.name + " · MC vs data", path: f.plots_B.pdf.split("/").slice(2).join("/"), href: f.plots_B.pdf, pages: f.plots_B.pages.map((p) => ({ label: `${f.name}  ·  ${p.label}`, src: p.src })) });
      if (f.plots_A) out.push({ name: f.name + " · barrel vs endcap", path: f.plots_A.pdf.split("/").slice(2).join("/"), href: f.plots_A.pdf, pages: f.plots_A.pages.map((p) => ({ label: `${f.name}  ·  ${p.label}`, src: p.src })) });
    });
    return out;
  }
  VIEWS.plots = function (arg) {
    loadArchivePlots(() => {
      const [srcId, pdfIdx] = (arg || "").split("|");
      const sources = plotSources();
      const src = sources.find((s) => s.id === srcId) || sources[0];
      const pdfs = src.id === RUN.name ? currentRunPdfs() : (S.archivePlots[src.id] || []);
      const nPages = pdfs.reduce((a, p) => a + p.pages.length, 0);
      const sel = Math.min(Math.max(0, +pdfIdx || 0), Math.max(0, pdfs.length - 1));
      const q = (ui.plotQ || "").trim().toLowerCase();
      let body;
      if (q) {
        const hits = [];
        pdfs.forEach((p) => p.pages.forEach((pg, k) => { if ((pg.label + " " + p.name).toLowerCase().includes(q)) hits.push({ p, pg, k }); }));
        const shown = hits.slice(0, ui.plotMax || 60);
        body = `<p class="muted small">${hits.length} matching pages${hits.length > shown.length ? `, showing ${shown.length}` : ""}.</p>
          <div class="gallery">${shown.map((h) => `<figure><img src="${esc(h.pg.src)}" alt="${esc(h.pg.label)}" loading="lazy" data-pdf="${esc(h.p.href)}"><figcaption>${esc(h.pg.label)}<br><span class="muted">${esc(h.p.path)} · p${h.k + 1}</span></figcaption></figure>`).join("")}</div>
          ${hits.length > shown.length ? `<p style="margin-top:12px"><button class="btn" type="button" id="more">show ${Math.min(60, hits.length - shown.length)} more</button></p>` : ""}`;
      } else if (pdfs.length) {
        const p = pdfs[sel];
        body = `<div class="plotbar" style="border:1px solid var(--grid);border-radius:6px 6px 0 0">
            <div><b class="mono">${esc(p.path)}</b> <span class="muted small">· ${p.pages.length} pages</span></div>
            <div><button class="btn sm" type="button" data-step="-1" ${sel ? "" : "disabled"}>← prev PDF</button>
            <button class="btn sm" type="button" data-step="1" ${sel < pdfs.length - 1 ? "" : "disabled"}>next PDF →</button>
            <a class="btn sm" href="${esc(p.href)}" download>download PDF</a></div></div>
          <div class="pagestack">${p.pages.map((pg, k) => `<figure><figcaption><span class="chip">p${k + 1}</span> ${esc(pg.label)}</figcaption>
            <img class="plotimg" src="${esc(pg.src)}" alt="${esc(pg.label)}" loading="lazy" data-pdf="${esc(p.href)}"></figure>`).join("")}</div>`;
      } else body = `<p class="muted">No plots for this source. Run <code>python site_builder/build_site.py</code>.</p>`;
      app.innerHTML = `
        <div class="eyebrow">every PDF, every version</div>
        <h1>PDF browser</h1>
        <p class="lede">Every page of every PDF the pipeline produced, from the current run and from every archived run, viewable here and downloadable as the original PDF.
        Pick a source, then a PDF, or search page titles (feature names, regions, selections) across the whole source.
        To see one split across all features (e.g. every endcap signal-vs-background page), use <a href="#/graphs">Graphs</a>.</p>
        <div class="toolbar">
          <select id="psrc" aria-label="Source">${sources.map((s) => `<option value="${esc(s.id)}" ${s.id === src.id ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select>
          <select id="ppdf" aria-label="PDF" style="max-width:420px">${pdfs.map((p, i) => `<option value="${i}" ${i === sel ? "selected" : ""}>${esc(p.name)} (${p.pages.length})</option>`).join("")}</select>
          <input type="search" id="pq" placeholder="search page titles in this source" value="${esc(ui.plotQ || "")}" aria-label="Search pages">
          <span class="count">${pdfs.length} PDFs · ${nPages} pages</span>
        </div>
        ${src.status && src.status !== "current" ? `<div class="callout ${src.status === "null result" ? "" : "warn"}" style="margin-top:0"><p><span class="chip">${esc(src.status)}</span> ${esc(src.note || "")}</p></div>` : ""}
        ${body}`;
      app.querySelector("#psrc").addEventListener("change", (e) => { ui.plotQ = ""; ui.plotMax = 60; location.hash = "#/plots/" + encodeURIComponent(e.target.value); });
      app.querySelector("#ppdf") && app.querySelector("#ppdf").addEventListener("change", (e) => { ui.plotQ = ""; location.hash = "#/plots/" + encodeURIComponent(src.id + "|" + e.target.value); });
      app.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => { location.hash = "#/plots/" + encodeURIComponent(src.id + "|" + (sel + +b.dataset.step)); }));
      const pq = app.querySelector("#pq");
      pq.addEventListener("input", () => { ui.plotQ = pq.value; ui.plotMax = 60; const pos = pq.selectionStart; VIEWS.plots(arg); setTimeout(() => { const n = app.querySelector("#pq"); if (n) { n.focus(); n.setSelectionRange(pos, pos); } }, 0); });
      const more = app.querySelector("#more");
      if (more) more.addEventListener("click", () => { ui.plotMax = (ui.plotMax || 60) + 60; VIEWS.plots(arg); });
      app.querySelectorAll("img[data-pdf]").forEach((img) => img.addEventListener("click", () => lightbox(img.src, img.alt, img.dataset.pdf)));
    });
  };

  // ------------------------------------------------------------------ ARCHIVE
  VIEWS.archive = function () {
    const A = I.archive;
    if (!A) { app.innerHTML = `<h1>Archive</h1><p class="muted">No results/archive/archive_index.json.</p>`; return; }
    const badge = (s) => `<span class="chip ${({ current: "pool", "null result": "susp", "kept, relabelled": "drop", superseded: "" })[s] || ""}">${esc(s)}</span>`;
    app.innerHTML = `
      <div class="eyebrow">genealogy · every version, every run, unchanged</div>
      <h1>Archive</h1>
      <p class="lede">${esc(A.about)}</p>
      <div class="timeline">${A.entries.map((e) => `
        <section class="tl-item">
          <div class="tl-ver">${esc(e.version)}</div>
          <div class="tl-body card">
            <div class="tl-head"><h3 style="margin:0">${esc(e.version)} <span class="muted small">· ${esc(e.date)}</span></h3>
              ${e.script ? `<a class="btn sm" href="${esc(e.script)}" download>${esc(e.script.split("/").pop())}${e.script_bytes ? " · " + kb(e.script_bytes) : ""}</a>` : ""}</div>
            <dl class="kv" style="margin-top:10px"><dt>what it does</dt><dd>${esc(e.what)}</dd><dt>changes</dt><dd>${esc(e.changes)}</dd>
              ${e.superseded_by ? `<dt>superseded by</dt><dd>${esc(e.superseded_by)}</dd>` : ""}</dl>
            ${(e.runs || []).map((r) => `
              <div class="tl-run">
                <div class="tl-head"><b class="mono">${esc(r.label)}</b> ${badge(r.status)}
                  <span class="muted small">${r.href_root ? esc(r.href_root) + "/" : ""} · ${r.files.length + r.n_feature_pdfs} files · ${kb(r.bytes || 0)}</span>
                  <a class="btn sm primary" href="#/plots/${encodeURIComponent(r.folder.startsWith("..") ? RUN.name : r.folder)}">view all plots →</a></div>
                <p class="small" style="margin:6px 0 8px">${esc(r.note)}</p>
                ${r.folder.startsWith("..") ? `<p class="small"><a href="#/files">Browse on Files &amp; code →</a></p>` : `
                <details><summary>files (${r.files.length})</summary>
                  <div class="tablewrap"><table class="ftree"><tbody>${r.files.map((f) => `<tr><td>${esc(f.path)}</td><td class="small">${esc(f.desc)}</td><td class="n">${kb(f.bytes)}</td><td><a class="btn sm" href="${esc(f.href)}" ${f.path.endsWith(".pdf") ? 'target="_blank" rel="noopener"' : "download"}>${f.path.endsWith(".pdf") ? "open" : "download"}</a></td></tr>`).join("")}</tbody></table></div></details>
                ${r.feature_pdfs.length ? `<details><summary>per-feature PDFs (${r.feature_pdfs.length})</summary><p class="mono small">${r.feature_pdfs.map((p) => `<a href="${esc(p.href)}" target="_blank" rel="noopener">${esc(p.name)}</a>`).join("<br>")}</p></details>` : ""}`}
              </div>`).join("")}
          </div>
        </section>`).join("")}</div>
      <p class="small muted">Archived scripts are byte-identical to the versions that ran, including their hard-coded data path (edit the <code>DATA = ...</code> line near the top to rerun one).
      <code>pipeline/archive/exclude_features_as_used_mk2-mk4.txt</code> is the exclusion file those runs read (comments only: nothing user-excluded).</p>`;
  };

  // ------------------------------------------------------------------ SUMMARIES
  VIEWS.summaries = function () {
    const titles = { A_barrel_vs_endcap: "A · barrel vs endcap", B_mc_vs_data: "B · MC vs data", C_correlation: "C · correlation", D_prototypes: "D · prototypes" };
    app.innerHTML = `
      <div class="eyebrow">the pipeline's own summary PDFs</div>
      <h1>Summaries</h1>
      <p class="lede">One summary PDF per analysis block, exactly as the pipeline wrote it. Click a page to enlarge; download the PDF for print.</p>
      ${RUN.summaries.map((s) => `<h2>${esc(titles[s.block] || s.block)} <a class="btn sm" style="vertical-align:4px;margin-left:8px" href="${esc(s.pdf)}" download>PDF · ${s.pages.length} pages</a></h2>
        <div class="gallery">${s.pages.map((p, i) => `<figure><img src="${esc(p.src)}" alt="${esc(p.label)}" loading="lazy" data-pdf="${esc(s.pdf)}"><figcaption>${i + 1} · ${esc(p.label)}</figcaption></figure>`).join("")}</div>`).join("")}`;
    app.querySelectorAll(".gallery img").forEach((img) => img.addEventListener("click", () => lightbox(img.src, img.alt, img.dataset.pdf)));
  };

  // ------------------------------------------------------------------ METRICS
  VIEWS.methods = function () {
    const p = P();
    const sec = (t, body) => `<h2>${t}</h2><div class="prose">${body}</div>`;
    app.innerHTML = `
      <div class="eyebrow">definitions</div>
      <h1>Metrics</h1>
      <p class="lede">Every number on this site, defined. Thresholds are read from the pipeline script at build time, so this page always matches the code that produced the run.</p>
      ${sec("KS distance <span class='k'>D</span>", `<p>For one feature, with ${tex("F_s")} and ${tex("F_b")} the empirical CDFs of signal and background (NaN and the sentinel ${tex(String(p.SENTINEL ?? -999))} removed):</p>
        <div class="eq">${tex("D = \\sup_x \\left| F_s(x) - F_b(x) \\right| \\in [0,1]", true)}</div>
        <p>${tex("D")} is the best single cut on that feature: the largest achievable ${tex("\\varepsilon_s - \\varepsilon_b")}. No p-values: with ${tex("n \\sim 10^3\\text{–}10^4")} they are ~0 for any real difference.</p>`)}
      ${sec("Combining the six <span class='k'>mass points</span>", `<p><b>Equal weight</b> (the default ranking) gives each mass point the same say, so small samples count as much as large ones:</p>
        <div class="eq">${tex("F_{eq}(x) = \\frac{1}{M}\\sum_{m=1}^{M} F_m(x), \\qquad D_{equal} = \\sup_x |F_{eq}(x) - F_b(x)|", true)}</div>
        <p><b>Pooled</b> stacks all signal events, so large mass points dominate:</p>
        <div class="eq">${tex("F_{pool}(x) = \\frac{\\sum_m n_m F_m(x)}{\\sum_m n_m}", true)}</div>`)}
      ${sec("Noise <span class='k'>floor</span> and \"separates\"", `<div class="eq">${tex("D_{crit} = 1.36\\,\\sqrt{\\frac{1}{n_s} + \\frac{1}{n_b}}", true)}</div>
        <p>The 95% KS critical value for samples of this size: below it, D is consistent with no difference. A feature <b>separates</b> in a region when</p>
        <div class="eq">${tex("D \\ge \\max(" + (p.WEAK_D ?? 0.2) + ",\\; 2\\,D_{crit})", true)}</div>
        <p>Other thresholds: <b>strong</b> ${tex("D \\ge " + (p.STRONG_D ?? 0.5))} (prototype P2 adds unused features above it);
        <b>suspicious</b> when any single mass point has ${tex("D \\ge " + (p.SUSPICIOUS_D ?? 0.99))} (flagged, never added).</p>`)}
      ${sec("Feature <span class='k'>categories</span>", `<p><span class="chip htmiss">htmiss-linked</span> D partly set by the by-design HTmiss split:</p>
        <pre>${(p.HTMISS_LINKED || []).map(esc).join("\n")}</pre>
        <p><span class="chip nonphys">non-physics</span> trigger, quality and pileup columns (regular expressions, case-insensitive):</p>
        <pre>${(p.NON_PHYSICS || []).map(esc).join("\n")}</pre>`)}
      ${sec("Duplicates and <span class='k'>redundancy</span>", `<p><b>Duplicates</b>: columns with the same missing pattern and the same value ordering in every file have identical KS D everywhere; only the first name is kept.</p>
        <p><b>Redundancy blocks</b>: Spearman ${tex("\\rho_S")} on background events (up to ${int(p.CORR_NMAX || 12000)}, random subsample). A feature joins a block only if
        ${tex("|\\rho_S| \\ge " + (p.CORR_BLOCK ?? 0.9))} with every member; the strongest-D member represents the block.</p>`)}
      ${sec("Prototype <span class='k'>surrogate</span>", `<p>Gradient-boosted trees (scikit-learn <code>HistGradientBoostingClassifier</code>), ${p.CV_FOLDS || 5}-fold stratified cross-validation, seed ${p.SEED ?? 7},
        events weighted so each mass point counts equally. Reported per network: AUC, AUC per mass point, worst-mass AUC. Independence of the two networks on background
        (${int(p.DCOR_N || 3000)} events) by distance correlation:</p>
        <div class="eq">${tex("\\mathrm{dCor}^2(X,Y) = \\frac{\\mathrm{dCov}^2(X,Y)}{\\sqrt{\\mathrm{dVar}^2(X)\\,\\mathrm{dVar}^2(Y)}}", true)}</div>
        <p>plus Spearman between the NN1 and NN2 surrogate scores. The surrogate nominates; GAMBIT decides with closure and G.</p>`)}
      ${sec("Regions and <span class='k'>samples</span>", `<p>${esc(RUN.region_audit.definition)}.</p>
        <div class="tablewrap"><table><thead><tr><th>sample</th><th class="n">n</th><th class="n">barrel</th><th class="n">endcap</th><th class="n">both</th><th class="n">neither</th></tr></thead>
        <tbody>${RUN.region_audit.rows.map((r) => `<tr><td class="num">${esc(r.sample)}</td><td class="n">${int(r.n)}</td><td class="n">${int(r.barrel)}</td><td class="n">${int(r.endcap)}</td><td class="n">${int(r.both)}</td><td class="n">${int(r.neither)}</td></tr>`).join("")}</tbody></table></div>`)}`;
  };

  // ------------------------------------------------------------------ FILES & CODE
  VIEWS.files = function () {
    const files = RUN.files;
    const groups = {};
    files.forEach((f) => {
      const parts = f.path.split("/");
      const top = parts[0].includes(".") ? "(run root)" : parts[0];
      const isFeat = parts[1] === "features";
      const key = isFeat ? top + "/features" : top;
      (groups[key] = groups[key] || []).push(f);
    });
    const code = (P().code_files || []);
    const tot = files.reduce((a, f) => a + f.bytes, 0);
    app.innerHTML = `
      <div class="eyebrow">download everything · rerun it yourself</div>
      <h1>Files &amp; code</h1>
      <h2>Run it <span class="k">yourself</span></h2>
      <div class="prose">
      <p>You need Python 3.10+ and your own copy of the seven CSVs (they are not in this repo).</p>
      <pre>git clone https://github.com/&lt;you&gt;/&lt;this-repo&gt;.git
cd &lt;this-repo&gt;
python -m venv .venv            # Windows: .venv\\Scripts\\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy pipeline\\config_example.txt pipeline\\config.txt     # macOS/Linux: cp pipeline/config_example.txt pipeline/config.txt
#   then set  DATA = &lt;folder with the 7 CSVs&gt;  in pipeline/config.txt

python pipeline/kj_sigbg_mk5.py --round 1      # writes pipeline/out_sigbg_mk5_r1/  (about 5–10 min)
python tools/selection_check.py --out pipeline/out_sigbg_mk5_r1

# publish the new run on the site
#   copy pipeline/out_sigbg_mk5_r1  ->  results/mk5_r1
python site_builder/build_site.py              # renders the PDFs, writes data/*.js
#   open index.html, or commit and push (GitHub Pages: branch main, folder / root)</pre>
      <p>Useful flags: <code>--block BC</code> (only some blocks), <code>--no-plots</code> (tables only, fast), <code>--top 20</code> (feature PDFs for the top 20 only), <code>--data &lt;folder&gt;</code>.</p>
      </div>

      <h2>Code</h2>
      <div class="tablewrap"><table class="ftree"><thead><tr><th>file</th><th>what it does</th><th class="n">size</th><th></th></tr></thead><tbody>
      ${code.map((c) => `<tr><td>${esc(c.path)}</td><td class="small">${esc({
        "pipeline/kj_sigbg_mk5.py": "The analysis: unit test, KS scores, blocks A–D, GAMBIT inputs (mk5: legends in their own column).",
        "pipeline/archive/kj_sigbg_mk4.py": "Archived: produced results/mk4_r1 (legends inside the panels).",
        "pipeline/exclude_features.txt": "EDITABLE — columns to leave out.",
        "pipeline/nn_features_mk4.txt": "The current NN1/NN2 input lists (Prof. Johns, Sep 2026 review) that the pipeline scores.",
        "pipeline/config_example.txt": "Template: copy to config.txt and set your data folder.",
        "tools/selection_check.py": "Measures the HTmiss edge and the background jet-count structure (Findings page).",
        "site_builder/build_site.py": "Turns results/<run> into this site.",
        "pipeline/archive/kj_sigbg_mk1.py": "Archived: first KS pass (see Archive).",
        "pipeline/archive/kj_sigbg_mk2.py": "Archived: two selections + background split (see Archive).",
        "pipeline/archive/kj_sigbg_mk3.py": "Archived: unit test + NN-list table (see Archive).",
        "pipeline/archive/ht_edge_check.py": "Archived: console HTmiss / jet-count checks.",
        "pipeline/archive/exclude_features_as_used_mk2-mk4.txt": "Archived: the exclusion file the runs read.",
      }[c.path] || "")}${c.path.endsWith("exclude_features.txt") ? ' <span class="badge-edit">EDITABLE</span>' : ""}</td>
        <td class="n">${kb(c.bytes)}</td><td><a class="btn sm" href="${esc(c.path)}" download>download</a></td></tr>`).join("")}
      </tbody></table></div>

      <p class="small muted" style="margin-top:8px">Every earlier version and its output: <a href="#/archive">Archive</a>.</p>
      <h2>Results of run <span class="k">${esc(RUN.name)}</span></h2>
      <p class="muted">${files.length} files · ${kb(tot)}. Per-feature PDFs are grouped; each is also on its feature's page.</p>
      <div class="tablewrap"><table class="ftree"><thead><tr><th>file</th><th>what it holds</th><th class="n">size</th><th></th></tr></thead><tbody>
      ${Object.keys(groups).sort().map((g) => {
        const fs = groups[g];
        if (g.endsWith("/features")) {
          return `<tr class="folder"><td colspan="4">${esc(g)}/ · ${fs.length} PDFs</td></tr>
            <tr><td colspan="4"><details><summary>${esc(fs[0].desc)} Show all ${fs.length}.</summary>
            <p class="mono small">${fs.map((f) => `<a href="${esc(f.href)}" download>${esc(f.path.split("/").slice(2).join("/"))}</a>`).join("<br>")}</p></details></td></tr>`;
        }
        return `<tr class="folder"><td colspan="4">${esc(g)}/</td></tr>` + fs.map((f) => `<tr><td>${esc(f.path)}</td><td class="small">${esc(f.desc)}</td><td class="n">${kb(f.bytes)}</td><td><a class="btn sm" href="${esc(f.href)}" download>download</a></td></tr>`).join("");
      }).join("")}
      </tbody></table></div>`;
  };


  // ================================================================== MAIN VIEWS (the shell's four "start here" options)
  // Page geometry: where each panel sits on a pipeline PDF page, as figure fractions [x, y-from-top, w, h],
  // computed from the pipeline's own gridspecs. mk4 = legends inside the panels; mk5 = legends in their own column (L1..L3).
  const PAGE_GEOM = {"mk4": {"region": {"1a": [0.065, 0.155, 0.424, 0.1878], "1b": [0.561, 0.155, 0.424, 0.1878], "2a": [0.065, 0.4461, 0.424, 0.1878], "2b": [0.561, 0.4461, 0.424, 0.1878], "3a": [0.065, 0.7372, 0.424, 0.1878], "3b": [0.561, 0.7372, 0.424, 0.1878]}, "shape": {"1a": [0.065, 0.155, 0.424, 0.3182], "1b": [0.561, 0.155, 0.424, 0.3182], "2a": [0.065, 0.6068, 0.424, 0.3182], "2b": [0.561, 0.6068, 0.424, 0.3182]}, "separation": {"1a": [0.065, 0.155, 0.424, 0.3182], "1b": [0.561, 0.155, 0.424, 0.3182], "2a": [0.065, 0.6068, 0.424, 0.3182], "2b": [0.561, 0.6068, 0.424, 0.3182]}}, "mk5": {"region": {"1a": [0.058, 0.155, 0.3113, 0.1878], "1b": [0.4144, 0.155, 0.3113, 0.1878], "L1": [0.7709, 0.155, 0.2241, 0.1878], "2a": [0.058, 0.4461, 0.3113, 0.1878], "2b": [0.4144, 0.4461, 0.3113, 0.1878], "L2": [0.7709, 0.4461, 0.2241, 0.1878], "3a": [0.058, 0.7372, 0.3113, 0.1878], "3b": [0.4144, 0.7372, 0.3113, 0.1878], "L3": [0.7709, 0.7372, 0.2241, 0.1878]}, "shape": {"1a": [0.058, 0.155, 0.3113, 0.3182], "1b": [0.4144, 0.155, 0.3113, 0.3182], "L1": [0.7709, 0.155, 0.2241, 0.3182], "2a": [0.058, 0.6068, 0.3113, 0.3182], "2b": [0.4144, 0.6068, 0.3113, 0.3182], "L2": [0.7709, 0.6068, 0.2241, 0.3182]}, "separation": {"1a": [0.058, 0.155, 0.3113, 0.3182], "1b": [0.4144, 0.155, 0.3113, 0.3182], "L1": [0.7709, 0.155, 0.2241, 0.3182], "2a": [0.058, 0.6068, 0.3113, 0.3182], "2b": [0.4144, 0.6068, 0.3113, 0.3182], "L2": [0.7709, 0.6068, 0.2241, 0.3182]}}};
  const PAGE_DOC = {
    region: {
      name: "signal vs background page",
      cells: {
        "1a": "each mass point vs background · raw (log y)", "1b": "each mass point vs background · normalized",
        "2a": "combined signal (pooled, and equal weight per mass) vs background · raw", "2b": "combined signal vs background · normalized",
        "3a": "background alone · raw", "3b": "background alone · normalized",
        L1: "legend for row 1: masses, D, n", L2: "legend for row 2: combined signal, D", L3: "legend for row 3: background, NaN / −999",
      },
    },
    shape: {
      name: "barrel vs endcap · shape page",
      cells: {
        "1a": "background (data): barrel vs endcap · raw (log y)", "1b": "background (data): barrel vs endcap · normalized",
        "2a": "combined signal (MC): barrel vs endcap · raw (log y)", "2b": "combined signal (MC): barrel vs endcap · normalized",
        L1: "legend for row 1: n per region, shape D", L2: "legend for row 2: n per region, shape D",
      },
    },
    separation: {
      name: "barrel vs endcap · separation page",
      cells: {
        "1a": "ENDCAP · each mass point vs background (normalized)", "1b": "BARREL · each mass point vs background (normalized)",
        "2a": "ENDCAP · combined signal vs background", "2b": "BARREL · combined signal vs background",
        L1: "legend for row 1: masses, D endcap | barrel", L2: "legend for row 2: combined, D endcap | barrel",
      },
    },
    overview: { name: "overview page", cells: {} },
  };
  const OVERVIEW_NOTE = "Text page: every KS D for this feature (per region and mass point), its noise floor, its rank, and which NN lists use it.";
  function pageType(label) {
    if (REGIONS.includes(label)) return "region";
    if (label === "shape" || label === "separation") return label;
    return "overview";
  }
  const layoutOf = () => (RUN && RUN.layout === "mk5" ? "mk5" : "mk4");
  const REGION_TONE = { endcap: "endcap", barrel: "barrel", all: "all", shape: "be", separation: "be", overview: "all" };

  // ---------------------------------------------------------------- big, bright variable banner
  function vbanner(f, kicker, tone, extra) {
    const e = f.regions.endcap, b = f.regions.barrel;
    const stats = [
      e ? `<span><em>endcap</em> D ${fmt(e.D)} · rank ${e.rank}</span>` : "",
      b ? `<span><em>barrel</em> D ${fmt(b.D)} · rank ${b.rank}</span>` : "",
      f.A && f.A.separates ? `<span><em>separates in</em> ${esc(f.A.separates)}</span>` : "",
    ].join("");
    return `<div class="vbanner tone-${tone}">
      <div class="vb-kicker">${esc(kicker)}</div>
      <div class="vb-name">${esc(f.name)}</div>
      <div class="vb-stats">${stats}</div>
      <div class="vb-chips">${catChip(f)}${REGIONS.filter((r) => r !== "all" && jetDep(f, r)).length ? `<span class="chip jet">jet-dependent</span>` : ""}${nnChips(f)}${extra || ""}</div>
    </div>`;
  }

  // ---------------------------------------------------------------- page map: what is where on the page
  function pageMap(type) {
    const doc = PAGE_DOC[type], geom = (PAGE_GEOM[layoutOf()] || {})[type] || {};
    const W = 220, H = 170;
    let svg = `<svg class="pmap" viewBox="0 0 ${W} ${H}" role="img" aria-label="Layout of this page">
      <rect x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" class="pm-page"/>
      <rect x="0.5" y="0.5" width="${W - 1}" height="${H * 0.115}" class="pm-banner"/>
      <text x="6" y="${H * 0.08}" class="pm-bt">VARIABLE NAME · region · rank</text>`;
    Object.entries(geom).forEach(([code, g]) => {
      const [x, y, w, h] = g;
      const leg = code[0] === "L";
      svg += `<g class="pm-cell ${leg ? "leg" : ""}" data-code="${code}"><rect x="${x * W}" y="${y * H}" width="${w * W}" height="${h * H}"/>
        <text x="${(x + w / 2) * W}" y="${(y + h / 2) * H + 4}" text-anchor="middle">${leg ? "legend" : code}</text></g>`;
    });
    svg += `</svg>`;
    if (type === "overview") {
      return `<div class="pm"><h3>Page map</h3>${svg}<p class="small muted">${OVERVIEW_NOTE}</p></div>`;
    }
    const codes = Object.keys(geom).filter((c) => doc.cells[c]);
    return `<div class="pm"><h3>Page map · ${esc(doc.name)}</h3>${svg}
      <ol class="pm-list">${codes.map((c) => `<li data-code="${c}"><b>${c[0] === "L" ? "legend" : c}</b>${esc(doc.cells[c])}</li>`).join("")}</ol>
      <p class="small muted">Hover a panel or a line to outline it on the plot; click to zoom into it.
      ${layoutOf() === "mk4" ? "This run is mk4: legends sit inside the panels and can cover data. mk5 runs move every legend into its own column." : "a = left column, b = right column."}</p></div>`;
  }
  function panelBox(type, code) {
    const g = ((PAGE_GEOM[layoutOf()] || {})[type] || {})[code];
    if (!g) return null;
    const [x, y, w, h] = g;
    if (code[0] === "L") return [x - 0.005, y - 0.01, w + 0.01, h + 0.02];
    const x0 = Math.max(0, x - 0.05), y0 = Math.max(0, y - 0.035);
    return [x0, y0, Math.min(1, x + w + 0.012) - x0, Math.min(1, y + h + 0.06) - y0];   // + title, axis labels
  }
  function zoomPanel(img, box, caption) {
    const lb = document.createElement("div");
    lb.className = "lightbox";
    const cv = document.createElement("canvas");
    const sw = img.naturalWidth * box[2], sh = img.naturalHeight * box[3];
    const scale = Math.min((window.innerWidth - 40) / sw, (window.innerHeight - 110) / sh, 3);
    cv.width = Math.round(sw * scale); cv.height = Math.round(sh * scale);
    cv.className = "zoomcv";
    const g = cv.getContext("2d");
    g.imageSmoothingQuality = "high";
    g.drawImage(img, img.naturalWidth * box[0], img.naturalHeight * box[1], sw, sh, 0, 0, cv.width, cv.height);
    lb.appendChild(cv);
    const bar = document.createElement("div");
    bar.className = "lb-bar";
    bar.innerHTML = `<span>${esc(caption)}</span><button type="button">close (Esc)</button>`;
    lb.appendChild(bar);
    const close = () => { lb.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    lb.addEventListener("click", (e) => { if (e.target === lb || e.target.tagName === "BUTTON") close(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(lb);
  }

  // ---------------------------------------------------------------- plot viewer: banner + page tabs + plot + page map
  function viewerHTML(f, block, label, kicker) {
    const pl = f[block === "B" ? "plots_B" : "plots_A"];
    if (!pl) return `${vbanner(f, kicker, "all")}<p class="muted">No ${block === "B" ? "signal-vs-background" : "barrel-vs-endcap"} PDF for this feature.</p>`;
    let k = pl.pages.findIndex((p) => p.label === label);
    if (k < 0) k = block === "B" ? Math.min(1, pl.pages.length - 1) : 0;
    const pg = pl.pages[k], type = pageType(pg.label), tone = REGION_TONE[pg.label] || "all";
    const tabName = (l) => (l === "overview" ? "overview (text)" : l === "separation" ? "endcap | barrel separation" : l === "shape" ? "barrel vs endcap shape" : l);
    return `<div class="pv" data-type="${type}">
      ${vbanner(f, kicker, tone)}
      <div class="pv-bar">
        <div class="seg pv-tabs">${pl.pages.map((p, i) => `<button type="button" data-l="${esc(p.label)}" class="${i === k ? "on " + (REGIONS.includes(p.label) ? p.label : "") : ""}">${esc(tabName(p.label))}</button>`).join("")}</div>
        <div class="pv-dl">
          <button class="btn sm" type="button" data-listtoggle title="show or hide the feature list">${ui.mvHide ? "show list" : "hide list"}</button>
          <a class="btn sm" href="${esc(pl.pdf)}#page=${k + 1}" target="_blank" rel="noopener" title="open the original vector PDF at this page">open PDF p${k + 1}</a>
          <a class="btn sm primary" href="${esc(pl.pdf)}" download>download PDF · ${pl.pages.length} p</a>
          <a class="btn sm" href="${esc(pg.src)}" download>PNG</a>
        </div>
      </div>
      <div class="pv-body">
        <div class="pv-imgwrap">
          <div class="pv-tag tone-${tone}"><b>${esc(f.name)}</b><span>${esc(tabName(pg.label))}</span></div>
          <img class="pv-img" src="${esc(pg.src)}" alt="${esc(f.name)} · ${esc(pg.label)}" data-type="${type}">
          <div class="pv-hl" hidden></div>
        </div>
        <aside class="pv-map">${pageMap(type)}</aside>
      </div>
    </div>`;
  }
  function bindViewer(root, f, onTab) {
    const pv = root.querySelector(".pv");
    if (!pv) return;
    pv.querySelectorAll(".pv-tabs button").forEach((b) => b.addEventListener("click", () => onTab(b.dataset.l)));
    const lt = pv.querySelector("[data-listtoggle]"), mv = root.querySelector(".mv");
    if (mv) mv.classList.toggle("nolist", !!ui.mvHide);
    if (lt) { if (!mv) lt.remove(); else lt.addEventListener("click", () => { ui.mvHide = !ui.mvHide; mv.classList.toggle("nolist", ui.mvHide); lt.textContent = ui.mvHide ? "show list" : "hide list"; }); }
    const img = pv.querySelector(".pv-img"), hl = pv.querySelector(".pv-hl"), type = pv.dataset.type;
    if (!img) return;
    const show = (code) => {
      const box = code && panelBox(type, code);
      pv.querySelectorAll("[data-code]").forEach((n) => n.classList.toggle("on", n.dataset.code === code));
      if (!box) { hl.hidden = true; return; }
      hl.hidden = false;
      hl.style.left = box[0] * 100 + "%"; hl.style.top = box[1] * 100 + "%";
      hl.style.width = box[2] * 100 + "%"; hl.style.height = box[3] * 100 + "%";
      hl.dataset.code = code;
    };
    pv.querySelectorAll(".pv-map [data-code]").forEach((n) => {
      n.addEventListener("mouseenter", () => show(n.dataset.code));
      n.addEventListener("mouseleave", () => show(null));
      n.addEventListener("click", () => { const b = panelBox(type, n.dataset.code); if (b && img.complete) zoomPanel(img, b, `${f.name} · panel ${n.dataset.code} · ${PAGE_DOC[type].cells[n.dataset.code] || ""}`); });
    });
    // hovering the plot itself names the panel under the cursor
    img.addEventListener("mousemove", (e) => {
      const r = img.getBoundingClientRect(), fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
      const geom = (PAGE_GEOM[layoutOf()] || {})[type] || {};
      const hit = Object.keys(geom).find((c) => { const b = panelBox(type, c); return b && fx >= b[0] && fx <= b[0] + b[2] && fy >= b[1] && fy <= b[1] + b[3]; });
      if (hit !== hl.dataset.code || hl.hidden) show(hit || null);
      img.style.cursor = hit ? "zoom-in" : "default";
    });
    img.addEventListener("mouseleave", () => show(null));
    img.addEventListener("click", () => {
      const code = hl.hidden ? null : hl.dataset.code, b = code && panelBox(type, code);
      if (b) zoomPanel(img, b, `${f.name} · panel ${code} · ${PAGE_DOC[type].cells[code] || ""}`);
      else lightbox(img.src, img.alt, null);
    });
  }

  // ---------------------------------------------------------------- shared list helpers
  function keyNav(listIds, current, go) {
    document.onkeydown = (e) => {
      if (e.target.closest("input, select, textarea")) return;
      const i = listIds.indexOf(current);
      if (["ArrowDown", "j"].includes(e.key) && i < listIds.length - 1) { e.preventDefault(); go(listIds[i + 1]); }
      if (["ArrowUp", "k"].includes(e.key) && i > 0) { e.preventDefault(); go(listIds[i - 1]); }
    };
  }
  const mbar = (v, cls) => `<i class="mb ${cls}"><b style="width:${Math.max(0, Math.min(1, v || 0)) * 100}%"></b></i>`;
  function splitArg(arg, n) { const p = (arg || "").split("|"); while (p.length < n) p.push(""); return p; }

  // one-click "every feature in one PDF" bar: the pipeline's bundles/<run>/<split>.pdf
  function dlBar(splits, primary, what) {
    const sp = splits.filter((x) => x.bundle).sort((a, b) => (b.id === primary) - (a.id === primary));
    if (!sp.length) return "";
    return `<div class="dlbar"><div class="dlbar-l">Download all ${RUN.features.length} features<span>${esc(what)} · one PDF, one bookmark per feature</span></div>
      ${sp.map((x) => `<a class="dlbtn ${x.id === primary ? "" : "alt"}" href="${esc(x.bundle.href)}" download title="${esc(x.desc || "")}">
        <b>${esc(x.title.replace(/^.*? · /, ""))}</b><span>${x.bundle.pages} p · ${kb(x.bundle.bytes)} · PDF</span></a>`).join("")}</div>`;
  }

  // ---------------------------------------------------------------- HOME
  VIEWS.home = function () {
    const bkg = RUN.region_audit.rows.find((r) => r.sample === "bkg") || {};
    const card = (h, title, sub, desc) => `<a class="homecard" href="#/${h}">
      <span class="hc-title">${title}</span><span class="hc-sub">${sub}</span><span class="hc-desc">${desc}</span>
      <span class="hc-go">open →</span></a>`;
    const row = (n, label, note, cards) => `<div class="hrow">
        <div class="hrow-label"><span class="hrow-n">${n}</span><b>${label}</b><span class="hrow-note">${note}</span></div>
        ${cards}</div>`;
    app.innerHTML = `
      <section class="home">
        <div class="home-intro">
          <div class="eyebrow">ATLAS Run-3 · MSVtx LLP search<br>run ${esc(RUN.name)} · ${RUN.features.length} features</div>
          <h1>Pick a <span class="k">view</span></h1>
          <p class="lede">Every view shows the variable's name in large type above its plots, a page map that says what each panel is,
          and links to the original PDFs.</p>
          <p class="home-n">Background: <b>${int(bkg.n)}</b> data events<br><span>${int(bkg.endcap)} endcap · ${int(bkg.barrel)} barrel</span><br>Signal: <b>six</b> mass points (MC)</p>
          <p class="home-warn">Before trusting any ranking, read <a href="#/findings">Findings</a>: the background is selected at HTmiss &lt; 40 GeV and signal at &ge; 40 GeV, so HTmiss- and jet-related variables separate by construction.</p>
        </div>
        <div class="home-rows">
          ${row("01", "Features", "one variable at a time, every plot", card("be", "Barrel – Endcap", "every feature, region against region", "How each variable's background and signal shapes differ between barrel and endcap, and where it separates signal from background. Two pages per feature: shape, and endcap | barrel separation.") +
            card("sb", "Signal – Background", "every feature, MC signal against data background", "KS separation per region and mass point, with the full plot set: each mass point, combined signal, background alone, raw and normalized."))}
          ${row("02", "NN suggestions", "prototype input sets P0–P3", card("gbe", "Barrel – Endcap", "candidate NN1 / NN2 input sets", "The pipeline's prototype input sets P0–P3, member by member, with each member's barrel-vs-endcap plots.") +
            card("gsb", "Signal – Background", "candidate NN1 / NN2 input sets", "The same prototype sets with each member's signal-vs-background page in the chosen region, the surrogate AUCs, and one-click group PDFs."))}
        </div>
      </section>
      <p class="small muted home-foot">Everything else (rankings, every page of every PDF, correlation, exclusions, the full mk1 → mk5 archive) is in the left panel.</p>`;
  };

  // ---------------------------------------------------------------- FEATURES · BARREL – ENDCAP
  const BE_SORTS = [["delta", "|D barrel − D endcap|"], ["endcap", "D endcap"], ["barrel", "D barrel"], ["shape_bkg", "shape D · background"], ["shape_sig", "shape D · signal"], ["name", "name"]];
  const BE_SEP = ["all", "both", "endcap only", "barrel only", "neither"];
  VIEWS.be = function (arg) {
    const [pageArg, nameArg] = splitArg(arg, 2);
    ui.beSort = ui.beSort || "delta"; ui.beSep = ui.beSep || "all";
    const page = ["shape", "separation"].includes(pageArg) ? pageArg : (ui.bePage || "shape");
    ui.bePage = page;
    let list = RUN.features.filter((f) => f.A);
    const q = (ui.beQ || "").trim().toLowerCase();
    if (q) list = list.filter((f) => f.name.toLowerCase().includes(q));
    if (ui.beSep !== "all") list = list.filter((f) => f.A.separates === ui.beSep);
    if (ui.hideHM) list = list.filter((f) => f.category !== "htmiss-linked");
    if (ui.onlyNN) list = list.filter((f) => (f.nn_lists || []).length);
    const key = {
      delta: (f) => (f.A.delta_barrel_minus_endcap == null ? -1 : Math.abs(f.A.delta_barrel_minus_endcap)), endcap: (f) => f.A.D_endcap ?? -1, barrel: (f) => f.A.D_barrel ?? -1,
      shape_bkg: (f) => f.A.shape_D_bkg ?? -1, shape_sig: (f) => f.A.shape_D_sig ?? -1,
    }[ui.beSort];
    list.sort(ui.beSort === "name" ? (a, b) => a.name.localeCompare(b.name) : (a, b) => key(b) - key(a) || a.name.localeCompare(b.name));
    const f = feat(nameArg) && list.some((x) => x.name === nameArg) ? feat(nameArg) : list[0];
    const go = (name, pg) => { location.hash = "#/be/" + encodeURIComponent((pg || page) + "|" + name); };
    const beSplits = (RUN.splits || []).filter((s) => s.block === "A");
    app.innerHTML = `
      ${dlBar(beSplits, (beSplits.find((s) => s.label === page) || {}).id, "barrel – endcap")}
      <div class="mv">
        <aside class="mv-list">
          <div class="mv-head"><div class="eyebrow">features as</div><h2 class="mv-title">Barrel – Endcap</h2>
            <input type="search" id="beq" placeholder="search ${RUN.features.length} features" value="${esc(ui.beQ || "")}" aria-label="Search features">
            <div class="mv-row"><label>sort <select id="besort">${BE_SORTS.map(([k, l]) => `<option value="${k}" ${k === ui.beSort ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
            <div class="mv-chips">${BE_SEP.map((s) => `<button type="button" data-sep="${s}" class="fchip ${s === ui.beSep ? "on" : ""}">${s === "all" ? "all" : "separates: " + s}</button>`).join("")}</div>
            <div class="mv-row"><label><input type="checkbox" id="behm" ${ui.hideHM ? "checked" : ""}> hide htmiss-linked</label>
              <label><input type="checkbox" id="benn" ${ui.onlyNN ? "checked" : ""}> NN lists only</label></div>
            <div class="mv-count">${list.length} features · ↑ ↓ to step</div>
            <div class="mv-legend"><span><i class="mb e"><b style="width:100%"></b></i> D endcap</span><span><i class="mb b"><b style="width:100%"></b></i> D barrel</span></div>
          </div>
          <ol class="mv-items">${list.map((x) => `<li class="${f && x.name === f.name ? "on" : ""}" data-f="${esc(x.name)}">
            <span class="mv-name">${esc(x.name)}</span>
            <span class="mv-bars">${mbar(x.A.D_endcap, "e")}${mbar(x.A.D_barrel, "b")}</span>
            <span class="mv-meta">${esc(x.A.separates || "")} · Δ ${fmt(x.A.delta_barrel_minus_endcap, 2)}</span></li>`).join("")}</ol>
        </aside>
        <section class="mv-main">${f ? viewerHTML(f, "A", page, "barrel – endcap") +
          `<p class="small muted pv-foot">Every feature's ${page} page in one PDF:
            ${(RUN.splits || []).filter((s) => s.block === "A").map((s) => s.bundle ? `<a href="${esc(s.bundle.href)}" download>${esc(s.title)} · ${s.bundle.pages} p</a>` : "").join(" · ")}</p>`
          : `<p class="muted">No features match.</p>`}</section>
      </div>`;
    app.querySelectorAll(".mv-items li").forEach((li) => li.addEventListener("click", () => go(li.dataset.f)));
    const on = app.querySelector(".mv-items li.on");
    if (on) on.scrollIntoView({ block: "nearest" });
    const rer = () => VIEWS.be(page + "|" + (f ? f.name : ""));
    const bq = app.querySelector("#beq");
    bq.addEventListener("input", () => { ui.beQ = bq.value; const p = bq.selectionStart; rer(); const n = app.querySelector("#beq"); n.focus(); n.setSelectionRange(p, p); });
    app.querySelector("#besort").addEventListener("change", (e) => { ui.beSort = e.target.value; rer(); });
    app.querySelectorAll("[data-sep]").forEach((b) => b.addEventListener("click", () => { ui.beSep = b.dataset.sep; rer(); }));
    app.querySelector("#behm").addEventListener("change", (e) => { ui.hideHM = e.target.checked; rer(); });
    app.querySelector("#benn").addEventListener("change", (e) => { ui.onlyNN = e.target.checked; rer(); });
    if (f) {
      bindViewer(app, f, (l) => go(f.name, l));
      keyNav(list.map((x) => x.name), f.name, (n) => go(n));
    }
  };

  // ---------------------------------------------------------------- FEATURES · SIGNAL – BACKGROUND
  VIEWS.sb = function (arg) {
    const [regArg, nameArg] = splitArg(arg, 2);
    const region = REGIONS.includes(regArg) ? regArg : (ui.sbRegion || "endcap");
    ui.sbRegion = region;
    let list = byRank(region);
    const q = (ui.sbQ || "").trim().toLowerCase();
    if (q) list = list.filter((f) => f.name.toLowerCase().includes(q));
    if (ui.hideHM) list = list.filter((f) => f.category !== "htmiss-linked");
    if (ui.hideNP) list = list.filter((f) => f.category !== "non-physics" && !f.suspicious);
    if (ui.hideJet) list = list.filter((f) => !jetDep(f, region));
    if (ui.onlyNN) list = list.filter((f) => (f.nn_lists || []).length);
    if (ui.onlySep) list = list.filter((f) => separates(f.regions[region]));
    const f = feat(nameArg) && list.some((x) => x.name === nameArg) ? feat(nameArg) : list[0];
    const page = ui.sbPage && ui.sbPage !== "region" ? ui.sbPage : region;
    const go = (name, reg) => { location.hash = "#/sb/" + encodeURIComponent((reg || region) + "|" + name); };
    const bundle = (RUN.splits || []).find((s) => s.id === "sb_" + region);
    const sbSplits = REGIONS.map((r) => (RUN.splits || []).find((s) => s.id === "sb_" + r)).filter(Boolean);
    app.innerHTML = `
      ${dlBar(sbSplits, "sb_" + region, "signal – background")}
      <div class="mv">
        <aside class="mv-list">
          <div class="mv-head"><div class="eyebrow">features as</div><h2 class="mv-title">Signal – Background</h2>
            <div class="seg mv-seg">${REGIONS.map((r) => `<button type="button" data-r="${r}" class="${r === region ? "on " + r : ""}">${r}</button>`).join("")}</div>
            <input type="search" id="sbq" placeholder="search ${RUN.features.length} features" value="${esc(ui.sbQ || "")}" aria-label="Search features">
            <div class="mv-row"><label><input type="checkbox" id="sbhm" ${ui.hideHM ? "checked" : ""}> hide htmiss-linked</label>
              <label><input type="checkbox" id="sbnp" ${ui.hideNP ? "checked" : ""}> hide non-physics</label>
              <label><input type="checkbox" id="sbjd" ${ui.hideJet ? "checked" : ""}> hide jet-dependent</label>
              <label><input type="checkbox" id="sbnn" ${ui.onlyNN ? "checked" : ""}> NN lists only</label>
              <label><input type="checkbox" id="sbsp" ${ui.onlySep ? "checked" : ""}> separates only</label></div>
            <div class="mv-count">${list.length} features · ranked by D in ${region} · ↑ ↓ to step</div>
          </div>
          <ol class="mv-items">${list.map((x) => { const r = x.regions[region];
            return `<li class="${f && x.name === f.name ? "on" : ""}" data-f="${esc(x.name)}">
            <span class="mv-name"><span class="mv-rank">${r.rank}</span>${esc(x.name)}</span>
            <span class="mv-bars">${mbar(r.D, x.category === "htmiss-linked" ? "hm" : region === "barrel" ? "b" : region === "endcap" ? "e" : "a")}<span class="mv-d">${fmt(r.D, 3)}</span></span>
            <span class="mv-meta">${x.category ? esc(x.category) + " · " : ""}${jetDep(x, region) ? "jet-dep · " : ""}${(x.nn_lists || []).join(", ")}</span></li>`; }).join("")}</ol>
        </aside>
        <section class="mv-main">${f ? viewerHTML(f, "B", page, "signal – background") +
          `<p class="small muted pv-foot">${bundle && bundle.bundle ? `Every feature's ${region} page in one PDF: <a href="${esc(bundle.bundle.href)}" download>${esc(bundle.title)} · ${bundle.bundle.pages} p · ${kb(bundle.bundle.bytes)}</a>` : ""}</p>`
          : `<p class="muted">No features match.</p>`}</section>
      </div>`;
    app.querySelectorAll(".mv-items li").forEach((li) => li.addEventListener("click", () => go(li.dataset.f)));
    const on = app.querySelector(".mv-items li.on");
    if (on) on.scrollIntoView({ block: "nearest" });
    const rer = () => VIEWS.sb(region + "|" + (f ? f.name : ""));
    app.querySelectorAll(".mv-seg button").forEach((b) => b.addEventListener("click", () => { ui.sbPage = "region"; go(f ? f.name : "", b.dataset.r); }));
    const sq = app.querySelector("#sbq");
    sq.addEventListener("input", () => { ui.sbQ = sq.value; const p = sq.selectionStart; rer(); const n = app.querySelector("#sbq"); n.focus(); n.setSelectionRange(p, p); });
    [["sbhm", "hideHM"], ["sbnp", "hideNP"], ["sbjd", "hideJet"], ["sbnn", "onlyNN"], ["sbsp", "onlySep"]].forEach(([id, k]) =>
      app.querySelector("#" + id).addEventListener("change", (e) => { ui[k] = e.target.checked; rer(); }));
    if (f) {
      bindViewer(app, f, (l) => { if (REGIONS.includes(l)) { ui.sbPage = "region"; go(f.name, l); } else { ui.sbPage = l; rer(); } });
      keyNav(list.map((x) => x.name), f.name, (n) => go(n));
    }
  };

  // ---------------------------------------------------------------- SUGGESTED NN GROUPINGS (prototype sets P0..P3)
  async function mergePdf(items, filename, title, btn, prog) {
    const barEl = prog.querySelector("i"), txt = prog.querySelector("span");
    const say = (i, n, label) => { barEl.style.width = (100 * i / Math.max(1, n)).toFixed(1) + "%"; txt.textContent = `${i} / ${n} · ${label}`; };
    btn.disabled = true; prog.hidden = false; say(0, items.length, "loading pdf-lib");
    try {
      if (!window.PDFLib) await loadScript(PDFLIB_URL);
      const { PDFDocument } = window.PDFLib;
      const out = await PDFDocument.create();
      const cache = new Map();
      for (let n = 0; n < items.length; n++) {
        const it = items[n];
        let d = cache.get(it.pdf);
        if (!d) {
          const res = await fetch(it.pdf);
          if (!res.ok) throw new Error(`${it.pdf}: HTTP ${res.status}`);
          d = await PDFDocument.load(await res.arrayBuffer());
          cache.set(it.pdf, d);
          if (cache.size > 6) cache.delete(cache.keys().next().value);
        }
        const [p] = await out.copyPages(d, [it.k]);
        out.addPage(p);
        say(n + 1, items.length, it.feature);
      }
      say(items.length, items.length, "writing PDF");
      out.setTitle(title);
      out.setCreator("SIG/BG Feature Explorer (pdf-lib, in the browser)");
      const bytes = await out.save();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
      a.download = filename;
      document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      txt.textContent = `done · ${items.length} pages · ${kb(bytes.length)}`;
    } catch (err) {
      txt.textContent = "failed: " + err.message;
    }
    btn.disabled = false;
  }
  // crop a text-only summary page to its ink, so the printout reads at its native size without a page of white
  function trimPage(img) {
    if (img.dataset.trimmed) return;
    try {
      const W = img.naturalWidth, H = img.naturalHeight, c = document.createElement("canvas");
      c.width = W; c.height = H;
      const g = c.getContext("2d"); g.drawImage(img, 0, 0);
      const d = g.getImageData(0, 0, W, H).data, yStop = Math.floor(H * 0.94);   // ignore the page footer
      let x1 = 0, y1 = 0;
      for (let y = 0; y < yStop; y++) for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4;
        if (d[i] < 200 || d[i + 1] < 200 || d[i + 2] < 200) { if (x > x1) x1 = x; if (y > y1) y1 = y; }
      }
      if (!x1 || !y1) return;
      const cw = Math.min(W, x1 + 40), ch = Math.min(H, y1 + 34);
      const o = document.createElement("canvas"); o.width = cw; o.height = ch;
      o.getContext("2d").drawImage(img, 0, 0, cw, ch, 0, 0, cw, ch);
      img.dataset.trimmed = "1";
      img.style.width = cw + "px";
      img.src = o.toDataURL("image/png");
    } catch (e) { /* tainted canvas (file://): keep the full page */ }
  }
  function groupView(kind, arg) {
    const P = RUN.prototypes || {}, names = Object.keys(P).sort();
    if (!names.length) { app.innerHTML = `<h1>Suggested NN groupings</h1><p class="muted">This run has no prototype sets (block D).</p>`; return; }
    let [p, net, region, page] = splitArg(arg, 4);
    if (!P[p]) p = ui.gP && P[ui.gP] ? ui.gP : (names.includes("P1") ? "P1" : names[0]);
    const nets = Object.keys(P[p].nets);
    const nnOpts = [...new Set(nets.map((n) => n.split(" ")[0]))];
    if (!nnOpts.includes(net)) net = nnOpts.includes(ui.gNet) ? ui.gNet : nnOpts[0];
    const regOpts = [...new Set(nets.filter((n) => n.startsWith(net + " ")).map((n) => n.split(" ")[1]))];
    const inclusive = regOpts.includes("inclusive");
    const plotRegions = inclusive ? ["all", "endcap", "barrel"] : regOpts;
    if (!plotRegions.includes(region)) region = plotRegions.includes(ui.gRegion) ? ui.gRegion : plotRegions[0];
    const netKey = inclusive ? `${net} inclusive` : `${net} ${region}`;
    if (kind === "be" && !["shape", "separation"].includes(page)) page = ui.gPage || "shape";
    Object.assign(ui, { gP: p, gNet: net, gRegion: region, gPage: page });
    const members = (P[p].nets[netKey] || []).map((n) => feat(n) || { name: n, regions: {}, missing: true });
    const scoreReg = region === "all" ? null : region;
    const sc = (RUN.prototype_scores || []).filter((r) => r.prototype === p && (!scoreReg || r.evaluated_in === scoreReg));
    const base = P.P0 && P.P0.nets[netKey] ? new Set(P.P0.nets[netKey]) : null;
    const added = base && p !== "P0" ? members.filter((m) => !base.has(m.name)).map((m) => m.name) : [];
    const dropped = base && p !== "P0" ? [...base].filter((n) => !members.some((m) => m.name === n)) : [];
    const block = kind === "sb" ? "B" : "A", label = kind === "sb" ? region : page;
    const items = [];
    members.forEach((m) => {
      const pl = m[block === "B" ? "plots_B" : "plots_A"];
      if (!pl) return;
      const k = pl.pages.findIndex((x) => x.label === label);
      if (k >= 0) items.push({ src: pl.pages[k].src, pdf: pl.pdf, k, feature: m.name, caption: `${m.name} · ${label}` });
    });
    const href = (pp, nn, rr, pg) => `#/g${kind}/` + encodeURIComponent([pp, nn, rr, pg || ""].join("|"));
    const auc = (r, n) => r[`AUC_${n}`];
    const stat = (m) => {
      if (m.missing) return `<span class="muted">not scored (excluded or dropped)</span>`;
      if (kind === "sb") { const x = m.regions[region]; return x ? `D ${fmt(x.D)} · rank ${x.rank}${separates(x) ? "" : " · <span class='muted'>below “separates”</span>"}` : "–"; }
      return m.A ? `endcap ${fmt(m.A.D_endcap)} · barrel ${fmt(m.A.D_barrel)} · ${esc(m.A.separates || "")}` : "–";
    };
    const isFile = location.protocol === "file:";
    const tone = kind === "sb" ? region : "be";
    // the pipeline's own printout for this set: D_SUMMARY.pdf pages titled "D · <set> · ..."
    const dsum = (RUN.summaries || []).find((x) => /^D_/.test(x.block));
    const prPages = dsum ? dsum.pages.map((pg, i) => ({ ...pg, k: i })).filter((pg) => pg.label.split(" · ")[1] === p) : [];
    const prItems = prPages.map((pg) => ({ src: pg.src, pdf: dsum.pdf, k: pg.k, feature: "", caption: pg.label.trim() }));
    const netHref = (nk) => { const [nn, rr] = nk.split(" "); return href(p, nn, rr === "inclusive" ? region : rr, page); };
    const listTxt = Object.entries(P[p].nets).map(([nk, l]) => `# ${nk} (${l.length})\n${l.join("\n")}`).join("\n\n");
    app.innerHTML = `
      <div class="eyebrow">suggested NN feature groupings · ${kind === "sb" ? "signal – background" : "barrel – endcap"}</div>
      <h1>${esc(p)} · ${esc(net)} · <span class="k">${esc(inclusive ? "inclusive" : region)}</span></h1>
      <div class="gpick">
        <span class="gsel-l">set</span><div class="seg">${names.map((n) => `<a class="segl ${n === p ? "on" : ""}" href="${href(n, net, region, page)}" title="${esc(P[n].description)}">${esc(n)}</a>`).join("")}</div>
        <span class="gsel-l">network</span><div class="seg">${nnOpts.map((n) => `<a class="segl ${n === net ? "on" : ""}" href="${href(p, n, region, page)}">${esc(n)}</a>`).join("")}</div>
        <span class="gsel-l">${inclusive ? "plots from" : "region"}</span><div class="seg">${plotRegions.map((r) => `<a class="segl ${r === region ? "on " + r : ""}" href="${href(p, net, r, page)}">${esc(r)}</a>`).join("")}</div>
        ${kind === "be" ? `<span class="gsel-l">page</span><div class="seg">${["shape", "separation"].map((g) => `<a class="segl ${g === page ? "on" : ""}" href="${href(p, net, region, g)}">${g}</a>`).join("")}</div>` : ""}
      </div>

      <section class="gvars">
        <div class="gvars-head"><h2>${esc(p)} <span class="muted">· ${esc(P[p].description)}</span></h2>
          <button class="btn sm" type="button" id="gvcopy">copy list</button>
          <a class="btn sm" href="results/${esc(RUN.name)}/D_prototypes/${esc(p)}.txt" download>${esc(p)}.txt</a></div>
        <div class="gvars-cols">${Object.entries(P[p].nets).map(([nk, l]) => `<div class="gv-col ${nk === netKey ? "on" : ""}">
          <a class="gv-h" href="${netHref(nk)}">${esc(nk)} <span>${l.length}</span></a>
          <ol>${l.map((n) => `<li>${esc(n)}</li>`).join("")}</ol></div>`).join("")}</div>
      </section>

      <section class="gprint">
        <div class="gvars-head"><h2>Ranking printout <span class="muted">· D_SUMMARY.pdf${prPages.length ? ` p${prPages.map((x) => x.k + 1).join(", ")}` : ""}</span></h2>
          ${dsum ? `<a class="btn sm" href="${esc(dsum.pdf)}#page=${prPages.length ? prPages[0].k + 1 : 1}" target="_blank" rel="noopener">open PDF</a><a class="btn sm" href="${esc(dsum.pdf)}" download>download PDF</a>` : ""}</div>
        ${prPages.length ? prPages.map((pg, i) => `<img src="${esc(pg.src)}" alt="${esc(pg.label)}" loading="lazy" data-pr="${i}">`).join("") : `<p class="muted">No printout page for ${esc(p)} in this run.</p>`}
      </section>

      <h2 class="gmore">Scores, changes and member plots</h2>
      <p class="lede">Candidate input sets from the pipeline's block D, scored by a gradient-boosted surrogate (5-fold CV, equal weight per mass point).
      The surrogate only nominates: the decision belongs to GAMBIT, with closure and G as referees.</p>
      <div class="grid g2" style="margin-top:14px">
        <div class="card"><h3 style="margin-top:0">Surrogate score · ${esc(p)}${scoreReg ? " · evaluated in " + esc(scoreReg) : ""}</h3>
          ${sc.length ? `<div class="tablewrap"><table><thead><tr><th>evaluated in</th><th class="n">n ${esc(net)}</th><th class="n">AUC ${esc(net)}</th><th class="n">worst mass</th><th class="n">dCor NN1–NN2 bkg</th></tr></thead>
            <tbody>${sc.map((r) => { const p0 = (RUN.prototype_scores || []).find((x) => x.prototype === "P0" && x.evaluated_in === r.evaluated_in);
              const d = p0 && p !== "P0" ? auc(r, net) - auc(p0, net) : null;
              return `<tr><td>${esc(r.evaluated_in)}</td><td class="n">${r["n_" + net]}</td><td class="n"><b>${fmt(auc(r, net))}</b>${d != null ? ` <span class="${d >= 0 ? "up" : "down"}">${d >= 0 ? "+" : ""}${fmt(d)}</span>` : ""}</td><td class="n">${fmt(r["AUCmin_" + net])}</td><td class="n">${fmt(r.dCor_bkg)}</td></tr>`; }).join("")}</tbody></table></div>
            <p class="small muted">Change vs P0 in the same region. A large jump deserves a look at which members were added (right) before it is believed.</p>` : `<p class="muted">No score row.</p>`}</div>
        <div class="card"><h3 style="margin-top:0">${esc(netKey)} · ${members.length} members</h3>
          ${p !== "P0" && base ? `<p class="small"><b class="up">added vs P0:</b> ${added.length ? added.map((n) => `<code>${esc(n)}</code>`).join(" ") : "none"}<br>
            <b class="down">dropped vs P0:</b> ${dropped.length ? dropped.map((n) => `<code>${esc(n)}</code>`).join(" ") : "none"}</p>` : `<p class="small muted">P0 is the current mk4 list as it stands.</p>`}
          <a class="btn sm" href="results/${esc(RUN.name)}/D_prototypes/${esc(p)}.txt" download>${esc(p)}.txt</a></div>
      </div>
      <div class="gdl" style="margin-top:14px">
        <button class="btn primary" type="button" id="gpdl" ${items.length && !isFile ? "" : "disabled"}>Download this group as one PDF · ${items.length} pages</button>
        <div class="gprog" id="gpprog" hidden><div class="pbar"><i></i></div><span class="small mono"></span></div>
        <span class="small muted">${isFile ? "Opened from a file: the browser won't let the page read PDFs. Each card's PDF link still works; serve the folder (python -m http.server) or use GitHub Pages for the one-click group PDF." : "Built in your browser from the original vector PDFs, in the order shown."}</span>
      </div>
      <div class="gcards">${members.map((m, i) => {
        const it = items.find((x) => x.feature === m.name);
        const pl = m[block === "B" ? "plots_B" : "plots_A"];
        return `<article class="gcard">
          <a class="gc-banner tone-${tone}" href="#/${kind}/${encodeURIComponent((kind === "sb" ? region : page) + "|" + m.name)}" title="open in the feature view">
            <span class="gc-num">${i + 1}</span><span class="gc-name">${esc(m.name)}</span></a>
          <div class="gc-stat">${stat(m)} ${m.missing ? "" : catChip(m)}${!m.missing && kind === "sb" && jetDep(m, region) ? `<span class="chip jet">jet-dep</span>` : ""}</div>
          ${it ? `<img src="${esc(it.src)}" alt="${esc(it.caption)}" loading="lazy" data-n="${items.indexOf(it)}">` : `<div class="gnone">no ${esc(label)} page for this feature</div>`}
          ${pl ? `<div class="gc-dl"><a href="${esc(pl.pdf)}#page=${(it ? it.k : 0) + 1}" target="_blank" rel="noopener">open PDF p${(it ? it.k : 0) + 1}</a><a href="${esc(pl.pdf)}" download>download PDF</a></div>` : ""}
        </article>`; }).join("")}</div>`;
    app.querySelectorAll(".gcards img[data-n]").forEach((img) => img.addEventListener("click", () => lightboxNav(items, +img.dataset.n)));
    app.querySelectorAll(".gprint img[data-pr]").forEach((img) => {
      img.addEventListener("click", () => lightboxNav(prItems, +img.dataset.pr));
      const trim = () => trimPage(img);
      if (img.complete && img.naturalWidth) trim(); else img.addEventListener("load", trim, { once: true });
    });
    app.querySelector("#gvcopy").addEventListener("click", (e) => {
      const b = e.currentTarget, done = (t) => { b.textContent = t; setTimeout(() => { b.textContent = "copy list"; }, 1400); };
      if (navigator.clipboard) navigator.clipboard.writeText(listTxt).then(() => done("copied"), () => download(`${p}.txt`, listTxt)); else download(`${p}.txt`, listTxt);
    });
    const btn = app.querySelector("#gpdl");
    btn.addEventListener("click", () => mergePdf(items, `sigbg_${RUN.name}_${p}_${netKey.replace(" ", "_")}_${label}.pdf`,
      `SIG/BG Feature Explorer · ${RUN.name} · ${p} ${netKey} · ${label}`, btn, app.querySelector("#gpprog")));
  }
  VIEWS.gsb = (arg) => groupView("sb", arg);
  VIEWS.gbe = (arg) => groupView("be", arg);

  // ---------------------------------------------------------------- shell link (iframe <-> left panel)
  const EMBED = window.parent !== window;
  function tellShell(msg) { if (EMBED) { try { window.parent.postMessage(Object.assign({ sigbg: 1 }, msg), "*"); } catch (e) { /* ignore */ } } }
  window.addEventListener("message", (e) => {
    const m = e.data;
    if (!m || !m.sigbg || e.source !== window.parent) return;
    if (m.type === "go" && m.hash && m.hash !== location.hash) location.hash = m.hash;
    else if (m.type === "theme") {
      if (m.value === "light") document.documentElement.setAttribute("data-theme", "light"); else document.documentElement.removeAttribute("data-theme");
      store.set("sigbg.theme", m.value);
      const tb = document.getElementById("themeBtn"); if (tb) tb.textContent = m.value === "light" ? "dark" : "light";
      if (RUN) route();
    } else if (m.type === "run" && m.value) {
      const sel = document.getElementById("runSelect");
      if (sel && sel.value !== m.value && [...sel.options].some((o) => o.value === m.value)) { sel.value = m.value; store.set("sigbg.run", m.value); start(); }
    }
  });

  // ------------------------------------------------------------------ theme
  function initTheme() {
    const btn = document.getElementById("themeBtn");
    if (!btn) return;
    const label = () => { btn.textContent = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light"; };
    label();
    btn.addEventListener("click", () => {
      const light = document.documentElement.getAttribute("data-theme") !== "light";
      if (light) document.documentElement.setAttribute("data-theme", "light"); else document.documentElement.removeAttribute("data-theme");
      store.set("sigbg.theme", light ? "light" : "dark");
      label();
      route();               // canvas colours are read from the theme at draw time
    });
  }

  // ------------------------------------------------------------------ boot
  const setHdr = () => { const h = document.querySelector("header.top"); if (h) document.documentElement.style.setProperty("--hdr", h.offsetHeight + "px"); };
  setHdr();
  window.addEventListener("resize", setHdr);
  initTheme();
  if (initRuns()) start();
  tellShell({ type: "ready" });
})();
