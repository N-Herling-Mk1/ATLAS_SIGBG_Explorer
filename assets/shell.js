/* SIG/BG Feature Explorer shell: left panel + one iframe (app.html). The two talk only through postMessage,
   so it works the same from file:// (opaque origins) and from GitHub Pages. */
(function () {
  "use strict";
  const frame = document.getElementById("view");
  const runSel = document.getElementById("runSelect");
  const themeBtn = document.getElementById("themeBtn");
  const pop = document.getElementById("popOut");
  const I = (window.SIGBG || {}).index;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };
  const send = (msg) => { try { frame.contentWindow.postMessage(Object.assign({ sigbg: 1 }, msg), "*"); } catch (e) { /* not loaded yet */ } };
  const hashNow = () => (location.hash && location.hash.length > 2 ? location.hash : "#/home");
  const theme = () => (document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");

  function highlight(hash) {
    const view = hash.slice(2).split("/")[0] || "home";
    document.querySelectorAll("#sideNav a[data-go]").forEach((a) => a.classList.toggle("on", a.dataset.go === view));
    pop.href = "app.html" + hash;
  }

  // runs (the app owns the data; the shell only offers the choice)
  if (I && I.runs) {
    runSel.innerHTML = I.runs.map((r) => `<option value="${r}">${r}</option>`).join("");
    const saved = store.get("sigbg.run");
    runSel.value = I.runs.includes(saved) ? saved : I.default;
  }
  runSel.addEventListener("change", () => { store.set("sigbg.run", runSel.value); send({ type: "run", value: runSel.value }); });

  // theme
  const themeLabel = () => { themeBtn.textContent = theme() === "light" ? "dark" : "light"; };
  themeLabel();
  themeBtn.addEventListener("click", () => {
    const next = theme() === "light" ? "dark" : "light";
    if (next === "light") document.documentElement.setAttribute("data-theme", "light"); else document.documentElement.removeAttribute("data-theme");
    store.set("sigbg.theme", next);
    themeLabel();
    send({ type: "theme", value: next });
  });

  // navigation: the shell's hash is the address bar; the iframe follows it
  window.addEventListener("hashchange", () => { highlight(hashNow()); send({ type: "go", hash: hashNow() }); closeNav(); });
  window.addEventListener("message", (e) => {
    const m = e.data;
    if (!m || !m.sigbg || e.source !== frame.contentWindow) return;
    if (m.type === "ready") {
      send({ type: "theme", value: theme() });
      if (runSel.value) send({ type: "run", value: runSel.value, quiet: true });
    } else if (m.type === "route" && m.hash) {
      if (m.hash !== location.hash) history.replaceState(null, "", m.hash);
      highlight(m.hash);
      if (m.title) document.title = m.title + " · SIG/BG Feature Explorer";
    }
  });

  // phone: the panel folds into a top bar
  const toggle = document.getElementById("sideToggle");
  function closeNav() { document.body.classList.remove("nav-open"); toggle.setAttribute("aria-expanded", "false"); }
  toggle.addEventListener("click", () => {
    const open = !document.body.classList.contains("nav-open");
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  });

  highlight(hashNow());
  frame.src = "app.html" + hashNow();
})();
