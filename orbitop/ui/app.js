// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Oberfläche: Kopfzeile, Lastzeile, Kachelraster, Fußzeile, Reiter „Prozesse“ und Dialoge. Alles aus dem Schnappschuss
// und aus texts kommt per textContent ins DOM, nie als HTML. Inline-Stile verbietet die CSP; Farben setzt nur CSSOM.
// Ein terminate geht nur aus dem Bestätigungsknopf des Rückfrage-Dialogs an Python (confirmed).
"use strict";

const POINTS = 300, THREAD_POINTS = 60, GRID_SECONDS = 30, MAX_MINIS = 8; // Puffergrößen wie im Sampler, 1 s je Punkt
const AREA = { cpu: "#4fd8ff", gpu: "#c48bff", mem: "#3dffa8", power: "#ffd84f", temp: "#ff5f7a", fan: "#ff7ad9",
               net: "#5b8cff", disk: "#2ff0d0" };
const SECOND = "#ffb347"; // Zweitlinie: Swap, Senden, Schreiben
const GPU_SHADES = [AREA.gpu, "#a17bff", "#dfb5ff", "#8a62dc"]; // weitere Grafikchips
const EXTRA = { mem: [SECOND], temp: [AREA.mem, AREA.gpu], fan: [SECOND, AREA.cpu], net: [SECOND], disk: [SECOND] };
const CAPS = { cpu: "cap.usage", gpu: "cap.usage", mem: "cap.occupancy", power: "cap.watt", temp: "cap.celsius",
               fan: "cap.rpm", net: "cap.rate", disk: "cap.rate" };
const TABS = ["overview", "procs"];
const BYTES = ["B", "KB", "MB", "GB", "TB"];
const DIGITS = { GHz: 1, W: 1 }; // sonst ganze Zahlen; Bytes unter 10 mit einer Nachkommastelle

/** 1024er-Stufe für big; eine Stufe höher, wenn die Rundung 1024 ergäbe (1023,7 B/s -> 1 KB/s). */
function byteStep(big) {
  let e = 0;
  while (e < BYTES.length - 1 && Math.round(big / 1024 ** e) >= 1024) e++;
  return e;
}

const state = {
  lang: "en", texts: {}, version: "", tab: "overview", last: null, n: 0, briefs: [], collator: new Intl.Collator(),
  sel: null, cursor: null, sort: { col: "cpu", desc: true }, filter: "all", query: "", autoPick: false,
  target: null, opener: null, pending: null, lastTerm: null, alert: null, // Rückfrage, laufendes Beenden, Nachsehen
};
const ui = { labels: [] };
const tiles = new Map(); // Kachel-id -> Elemente
const procRows = new Map(); // "pid:start" -> Zeilenelemente, nur angezeigte Zeilen
const formats = new Map();

// ---- Texte und Zahlen ----
function text(key) {
  return Object.hasOwn(state.texts, key) ? state.texts[key] : key;
}

/** Platzhalter wie {list} per reiner Zeichenkettenersetzung, ohne $-Muster von String.replace. */
function fill(key, vars) {
  return text(key).replace(/\{(\w+)\}/g, (m, k) => (Object.hasOwn(vars, k) ? String(vars[k]) : m));
}

function number(v, lang, min, max, group) {
  const key = `${lang}|${min}|${max}|${group}`;
  let f = formats.get(key);
  if (!f) {
    f = new Intl.NumberFormat(lang, { minimumFractionDigits: min, maximumFractionDigits: max, useGrouping: group });
    formats.set(key, f);
  }
  return f.format(v);
}

/** Num -> Text: Bytes in 1024er-Stufen, „v / of Einheit“, Präfix p, Dezimalzeichen nach Sprache, null als „–“. */
function fmt(num, lang) {
  if (!num || num.v == null) return "–";
  const u = num.u, of = num.of;
  let unit = u, scale = 1;
  if (u === "B" || u === "B/s") {
    const e = byteStep(Math.max(Math.abs(num.v), Math.abs(of || 0)));
    scale = 1024 ** e;
    unit = BYTES[e] + u.slice(1);
  } else if (u === "rpm") {
    unit = text("unit.rpm");
  }
  const part = (x) => {
    x /= scale;
    if (scale > 1) return number(x, lang, 0, Math.abs(x) < 10 ? 1 : 0, false);
    const d = DIGITS[u] || 0;
    return number(x, lang, d, d, u === ""); // Tausenderpunkt nur bei Anzahlen (Entwurf: „1.904“, aber „4800 U/min“)
  };
  const sep = u === "" || (u === "%" && lang === "en") ? "" : " ";
  return (num.p ? num.p + " " : "") + part(num.v) + (of == null ? "" : " / " + part(of)) + sep + unit;
}

/** Num | Txt | [Num|Txt] -> Text; Txt.k wird übersetzt, Txt.l bleibt roh. */
function show(x) {
  if (Array.isArray(x)) return x.map(show).join(" · ");
  if (x && "k" in x) return text(x.k);
  if (x && "l" in x) return String(x.l);
  return fmt(x, state.lang);
}

/** Modellnamen kürzen wie im Entwurf („i7-7600U“ statt „Intel(R) Core(TM) i7-7600U CPU @ 2.80GHz“). */
function shortName(name) {
  return name.replace(/\((R|TM)\)|[®™]/gi, "").replace(/\s+(CPU\s+)?@\s.*$/i, "").replace(/\s+/g, " ").trim();
}

// ---- DOM ----
function el(tag, cls, parent, content) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (content != null) e.textContent = content;
  if (parent) parent.append(e);
  return e;
}

/** Text (oder mit attr ein Attribut) aus texts, neu gesetzt bei jedem init. */
function label(node, key, attr) {
  ui.labels.push([node, key, attr]);
  return node;
}

function setText(node, s) {
  if (node.textContent !== s) node.textContent = s;
}

/** Zweispaltige Liste (Name, Wert) mit wiederverwendeten Elementen. */
function pairs(box, rows) {
  while (box.childElementCount > rows.length * 2) box.lastChild.remove();
  while (box.childElementCount < rows.length * 2) el("span", "", box);
  rows.forEach(([a, b], i) => {
    setText(box.children[2 * i], a);
    setText(box.children[2 * i + 1], b);
  });
  box.hidden = !rows.length;
}

function post(msg) {
  window.webkit?.messageHandlers?.orbitop?.postMessage(msg); // fehlt auf der Testseite
}

function button(cls, parent, onClick) {
  const b = el("button", cls, parent);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

function build() {
  const body = document.body;
  const hdr = el("header", "hdr", body);
  el("span", "brand", hdr, "ORBITOP");
  const nav = el("nav", "tabs", hdr);
  ui.tabs = TABS.map((name) => label(button("tab", nav, () => select(name, null, null)), "tab." + name));
  ui.hdrInfo = el("span", "s", hdr);
  ui.infoBtn = label(button("info", hdr, () => openDialog(ui.about, ui.infoBtn, ui.aboutClose)), "about.title", "aria-label");
  svg(ui.infoBtn, "", "0 0 16 16", ["M2 8a6 6 0 1 0 12 0a6 6 0 1 0-12 0", "M8 7v4.5", "M8 4.3v.4"]);
  ui.overview = el("section", "overview", body);
  const strip = el("div", "strip", ui.overview);
  label(el("span", "lbl", strip), "strip.top");
  ui.chips = el("span", "chips", strip);
  label(el("span", "s hint", strip), "strip.hint");
  ui.grid = el("div", "grid", ui.overview);
  ui.procs = el("section", "procs", body);
  buildProcs();
  ui.footer = el("footer", "foot", body);
  buildDialogs();
  showTab("overview");
}

/** Rechts in der Kopfzeile: Takt in der Übersicht, Prozessanzahl im Reiter „Prozesse“. */
function hdrInfo() {
  const procs = state.tab === "procs" && state.last && state.last.procs;
  setText(ui.hdrInfo, procs ? fill("strip.count", { n: number(procs.length, state.lang, 0, 0, true) }) : text("strip.tick"));
}

function showTab(name) {
  state.tab = name;
  ui.overview.hidden = name !== "overview";
  ui.procs.hidden = name !== "procs";
  ui.footer.classList.toggle("off", name !== "overview"); // Hinweise der Fußzeile betreffen die Kacheln
  ui.tabs.forEach((b, i) => {
    b.classList.toggle("on", TABS[i] === name);
    b.setAttribute("aria-pressed", String(TABS[i] === name));
  });
  hdrInfo();
}

/** Reiter zeigen und Python melden; pid/start (Lastzeile, Tabellenzeile) wählen einen Prozess. Die Auswahl bleibt. */
function select(name, pid, start) {
  if (pid != null) state.sel = { pid, start };
  showTab(name);
  const sel = name === "procs" ? state.sel : null;
  post({ type: "view", tab: name, pid: sel ? sel.pid : null, start: sel ? sel.start : null });
  if (state.last) (name === "overview" ? renderOverview : renderProcs)(state.last);
}

// ---- Lastzeile ----
function renderStrip(top) {
  const cpu = (top && top.cpu) || [];
  const briefs = state.briefs = top && top.mem ? [...cpu, top.mem] : cpu;
  while (ui.chips.childElementCount > briefs.length) ui.chips.lastChild.remove();
  while (ui.chips.childElementCount < briefs.length) {
    const i = ui.chips.childElementCount;
    const b = button("chip", ui.chips, () => {
      const p = state.briefs[i];
      if (p) select("procs", p.pid, p.start);
    });
    el("b", "nm", b);
    el("span", "", b);
  }
  briefs.forEach((p, i) => {
    const chip = ui.chips.children[i];
    setText(chip.firstChild, String(p.name));
    setText(chip.lastChild, " " + (i < cpu.length
      ? fill("strip.cpu", { pct: number(p.cpu, state.lang, 0, 0, false) })
      : fill("strip.ram", { size: fmt({ v: p.rss, u: "B" }, state.lang) })));
  });
}

// ---- Kacheln ----
function colorsOf(t) {
  const gpu = /^gpu(\d+)$/.exec(t.id);
  const first = t.kind === "gpu" ? GPU_SHADES[(gpu ? Number(gpu[1]) : 0) % GPU_SHADES.length] : AREA[t.kind] || AREA.cpu;
  return [first, ...(EXTRA[t.kind] || [])];
}

/** Diagrammfläche: Beschriftung, Gitter-Canvas und darüber die Canvas der Kurven (zurückgegeben). */
function plot(parent, cls, cap) {
  const box = el("div", cls, parent);
  el("span", "cap", box, cap);
  const grid = el("canvas", "grid", box);
  const c = el("canvas", "", box);
  c.grid = grid;
  return c;
}

/** Beschriftung folgt der ersten Kurve: Takt statt Auslastung, Einheit der Skala bei Raten. */
function caption(t) {
  const s = t.series[0];
  const key = s && s.key === "kv.clock" ? "cap.clock" : CAPS[t.kind] || "cap.usage";
  return fill(key, { unit: s && s.u === "B/s" ? BYTES[byteStep(s.max)] + "/s" : "" });
}

function makeTile(t) {
  const root = el("div", "tile");
  const colors = colorsOf(t);
  colors.forEach((c, i) => root.style.setProperty(i ? `--c${i + 1}` : "--c", c)); // CSSOM, von der CSP erlaubt
  const inner = el("div", "in", root);
  const head = el("div", "head", inner);
  const left = el("div", "who", head);
  const title = el("div", "t", left);
  const v = {
    root, colors, kind: el("span", "", title), name: el("span", "nm", title), main: el("div", "v", left),
    aside: el("div", "s aside", head), seg: el("div", "seg", inner),
    canvas: plot(inner, "plot", ""),
    threads: el("div", "", inner), threadEls: [], legend: el("div", "lg", inner), legendSig: null,
    kv: el("div", "kv", inner), dev: el("table", "dev", inner), devShape: null,
  };
  v.cap = v.canvas.parentNode.firstChild;
  v.threads.hidden = true; // nur die CPU-Kachel zeigt Threads
  tiles.set(t.id, v);
  return v;
}

function latest(values) {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] != null) return values[i];
  return null;
}

function updateThreads(v, threads) {
  const n = threads ? threads.length : 0, bars = n > MAX_MINIS;
  if (v.threadEls.length !== n) {
    v.threads.className = bars ? "bars" : "cores";
    v.threads.replaceChildren();
    v.threadEls = (threads || []).map((_, i) => (bars ? el("i", "", v.threads)
      : plot(v.threads, "plot mini", fill("cap.thread", { n: i }))));
    v.threads.hidden = !n;
  }
  (threads || []).forEach((values, i) => {
    if (bars) {
      const x = Math.min(Math.max(latest(values) || 0, 0), 100);
      v.threadEls[i].style.setProperty("--v", String(x));
      v.threadEls[i].classList.toggle("hot", x >= 80);
    } else if ((v.threadEls[i].at ?? -Infinity) <= state.n - 2) { // Mini-Verläufe nur alle 2 s (Spec, Eigenlast)
      v.threadEls[i].at = state.n;
      drawArea(v.threadEls[i], [{ fill: true, max: 100, values }],
               { color: v.colors[0], gridEvery: GRID_SECONDS, points: THREAD_POINTS });
    }
  });
}

/** Geräte als Tabelle: Kopf aus cols (übersetzt), je Gerät eine Zeile, null als „–“. */
function updateDevices(v, devices) {
  const cols = devices ? devices.cols : [], rows = devices ? devices.rows : [];
  const shape = cols.join("\n") + "|" + rows.length;
  if (v.devShape !== shape) {
    v.devShape = shape;
    v.dev.replaceChildren();
    const head = el("tr", "", el("thead", "", v.dev));
    el("th", "", head);
    for (const c of cols) el("th", "", head, text(c)).scope = "col";
    const body = el("tbody", "", v.dev);
    for (let i = 0; i < rows.length; i++) {
      const tr = el("tr", "", body);
      el("th", "nm", tr).scope = "row";
      for (let j = 0; j < cols.length; j++) el("td", "", tr);
    }
    v.dev.hidden = !rows.length;
  }
  rows.forEach((r, i) => {
    const cells = v.dev.tBodies[0].rows[i].cells;
    setText(cells[0], String(r.name));
    for (let j = 0; j < cols.length; j++) setText(cells[j + 1], fmt(r.values[j], state.lang));
  });
}

function updateTile(v, t) {
  const name = t.name ? shortName(String(t.name)) : "";
  setText(v.kind, text("tile." + t.kind) + (name ? " · " : ""));
  setText(v.name, name);
  v.name.title = t.name ? String(t.name) : "";
  setText(v.main, fmt(t.main, state.lang));
  setText(v.aside, t.aside == null ? "" : show(t.aside));
  drawSegments(v.seg, t.seg, t.warn);
  setText(v.cap, caption(t));
  drawArea(v.canvas, t.series, { color: v.colors[0], color2: v.colors[1], color3: v.colors[2],
                                 gridEvery: GRID_SECONDS, points: POINTS });
  if (t.kind === "cpu") updateThreads(v, t.threads);
  const names = t.series.length > 1 ? t.series.map((s) => ("key" in s ? text(s.key) : String(s.label))) : [];
  if (v.legendSig !== names.join("\n")) {
    v.legendSig = names.join("\n");
    v.legend.replaceChildren(...names.map((n, i) => {
      const item = el("span", "l" + i);
      el("i", "", item);
      el("span", "", item, n);
      return item;
    }));
    v.legend.hidden = !names.length;
  }
  pairs(v.kv, (t.kv || []).map((r) => ["k" in r ? text(r.k) : String(r.l), show(r.v)]));
  updateDevices(v, t.devices);
}

function renderTiles(list) {
  const views = list.map((t) => tiles.get(t.id) || makeTile(t));
  const ids = new Set(list.map((t) => t.id));
  for (const [id, v] of tiles) {
    if (!ids.has(id)) {
      v.root.remove();
      tiles.delete(id);
    }
  }
  if (views.some((v, i) => ui.grid.children[i] !== v.root)) ui.grid.replaceChildren(...views.map((v) => v.root));
  list.forEach((t, i) => updateTile(views[i], t)); // erst im DOM, sonst hat die Canvas keine Größe
}

// ---- Fußzeile ----
function renderFooter(missing, hints) {
  const lines = (missing && missing.length)
    ? [fill("footer.missing", { list: missing.map((k) => text("missing." + k)).join(" · ") })] : [];
  const all = [...lines, ...(hints || []).map(text)];
  if (ui.footerSig === all.join("\n")) return;
  ui.footerSig = all.join("\n");
  ui.footer.replaceChildren(...all.map((s, i) => el("p", i < lines.length ? "" : "hint", null, s)));
  ui.footer.hidden = !all.length;
}

function renderOverview(msg) {
  renderStrip(msg.top);
  renderTiles(msg.tiles || []);
}

// ---- Prozesse ----
const PROC_POINTS = 150, PROC_GRID = 15, SPARK_POINTS = 30; // 2 s je Punkt: Detail 5 min, Linie alle 30 s; Zeile 60 s
const SVG_NS = "http://www.w3.org/2000/svg";
const KIND = { working: "ok", waiting: "idle", busy_noio: "warn", busy_iounknown: "warn", kernel_hang: "bad",
               stopped: "stop", zombie: "dead" }; // Farbe und Symbol je Zustand, wie im Entwurf
const ICONS = { ok: ["M2 6.5l2.5 2.5L10 3.5"], idle: ["M3 6a3 3 0 1 0 6 0a3 3 0 1 0-6 0"], warn: ["M6 1.5l5 9H1z", "M6 5v2.5"],
                bad: ["M3 3l6 6M9 3l-6 6"], stop: ["M4 2.5v7M8 2.5v7"] };
ICONS.dead = ICONS.idle;
const SEVERITY = ["waiting", "working", "zombie", "stopped", "busy_iounknown", "busy_noio", "kernel_hang"]; // absteigend: Auffälliges zuerst
const COLS = [
  { id: "process", key: "col.process", get: (p) => String(p.name), asc: true },
  { id: "cpu", key: "col.cpu", get: (p) => p.cpu, cls: "r" },
  { id: "last60", key: "col.last60", get: (p) => p.spark.reduce((a, b) => a + b, 0) },
  { id: "ram", key: "col.ram", get: (p) => p.rss, cls: "r" },
  { id: "io", key: "col.io", get: (p) => (p.io == null ? -1 : p.io), cls: "r" },
  { id: "state", key: "col.state", get: (p) => SEVERITY.indexOf(p.state) },
];
const FILTERS = { all: () => true, mine: (p) => p.own, flagged: (p) => p.state !== "working" && p.state !== "waiting" };
const RESULTS = ["sent", "gone", "mismatch", "zombie", "kernel", "denied", "error"];

const keyOf = (p) => p.pid + ":" + p.start;
const same = (p, sel) => !!sel && p.pid === sel.pid && p.start === sel.start;

function svg(parent, cls, viewBox, paths) {
  const s = document.createElementNS(SVG_NS, "svg");
  s.setAttribute("viewBox", viewBox);
  s.setAttribute("aria-hidden", "true");
  if (cls) s.setAttribute("class", cls);
  s.append(...paths.map(pathEl));
  parent.append(s);
  return s;
}

function pathEl(d) {
  const p = document.createElementNS(SVG_NS, "path");
  p.setAttribute("d", d);
  return p;
}

/** Wie fill, aber als Knoten: jeder Wert wird ein eigenes span.nm (unicode-bidi: isolate), lead steht fett davor. */
function fillInto(node, tpl, vars, lead) {
  const sig = [lead, tpl, ...Object.values(vars)].join("\0");
  if (node.sig === sig) return;
  node.sig = sig;
  const parts = tpl.split(/\{(\w+)\}/).map((s, i) => (i % 2 === 0 ? s
    : Object.hasOwn(vars, s) ? el("span", "nm", null, String(vars[s])) : `{${s}}`));
  node.replaceChildren(...(lead ? [el("b", "", null, lead)] : []), ...parts);
}

/** Sekunden als „45 s“, „4 Min 12 s“ (unter 10 Min), „38 Min“, „2 Std 5 Min“, „2 T 4 Std“. */
function duration(sec) {
  const s = Math.max(0, Math.round(sec)), m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  const [min, hr, day] = ["unit.min", "unit.h", "unit.d"].map(text);
  if (s < 60) return `${s} s`;
  if (d) return `${d} ${day} ${h % 24} ${hr}`;
  if (h) return `${h} ${hr} ${m % 60} ${min}`;
  return m < 10 && s % 60 ? `${m} ${min} ${s % 60} s` : `${m} ${min}`;
}

/** Startzeit in Ortszeit; älter als ein Tag mit Datum. */
function clock(epoch) {
  const opts = { hour: "2-digit", minute: "2-digit" };
  if (Date.now() / 1000 - epoch >= 86400) Object.assign(opts, { day: "2-digit", month: "2-digit" });
  return new Date(epoch * 1000).toLocaleString(state.lang, opts);
}

function makeBadge(parent) {
  const b = el("span", "st", parent);
  svg(b, "", "0 0 12 12", []);
  el("span", "", b);
  return b;
}

function setBadge(b, st, label) {
  const kind = KIND[st] || "idle";
  if (b.state !== st) {
    b.state = st;
    b.className = "st " + kind;
    b.firstChild.replaceChildren(...ICONS[kind].map(pathEl));
  }
  setText(b.lastChild, label);
}

function buildProcs() {
  const list = el("div", "in", el("div", "frame list", ui.procs));
  const bar = el("div", "bar2", list);
  ui.search = label(label(el("input", "search", bar), "procs.search", "placeholder"), "procs.search", "aria-label");
  ui.search.type = "search";
  ui.search.addEventListener("input", () => {
    state.query = ui.search.value.trim().toLowerCase();
    refresh();
  });
  const filters = el("div", "filters", bar);
  ui.filters = Object.keys(FILTERS).map((f) => label(button("", filters, () => {
    state.filter = f;
    pressFilters();
    refresh();
  }), "filter." + f));
  const table = label(el("table", "ptable", el("div", "scroll", list)), "tab.procs", "aria-label");
  const head = el("tr", "", el("thead", "", table));
  ui.ths = COLS.map((c) => {
    const th = el("th", c.cls || "", head);
    th.scope = "col";
    label(button("", th, () => sortBy(c)), c.key);
    return th;
  });
  ui.tbody = el("tbody", "", table);
  ui.tbody.addEventListener("click", (e) => pickRow(e.target.closest("tr")));
  ui.tbody.addEventListener("keydown", rowKey);
  ui.tbody.addEventListener("focusin", (e) => {
    state.cursor = e.target.closest("tr").dataset.key;
    rove();
  });

  const det = el("div", "in", el("div", "frame detail", ui.procs));
  label(el("div", "t", det), "detail.selected");
  ui.none = label(el("p", "s", det), "detail.none_selected");
  ui.dbody = el("div", "dbody", det);
  const dh = el("div", "dhead", ui.dbody);
  ui.dname = el("div", "big nm", dh);
  ui.dpid = el("div", "s", dh);
  ui.dcmd = el("div", "s cmd nm", ui.dbody);
  ui.dcanvas = plot(ui.dbody, "plot proc", "");
  label(ui.dcanvas.parentNode.firstChild, "cap.proc_cpu");
  ui.dkv = el("div", "kv", ui.dbody);
  ui.verdict = el("div", "verdict", ui.dbody);
  const btns = el("div", "btns", ui.dbody);
  ui.term = label(button("btn term", btns, () => ask(false, ui.term)), "btn.terminate");
  ui.kill = label(button("btn kill", btns, () => ask(true, ui.kill)), "btn.kill");
  ui.reason = el("p", "s reason", ui.dbody);
  ui.reason.id = "reason";
  for (const b of [ui.term, ui.kill]) b.setAttribute("aria-describedby", "reason");
  label(el("p", "s", ui.dbody), "btn.hint");
  ui.notice = el("div", "notice", det);
  ui.notice.setAttribute("role", "status");
  ui.notice.hidden = true;
  ui.noticeText = el("span", "", ui.notice);
  const x = label(button("x", ui.notice, () => { ui.notice.hidden = true; }), "btn.close", "aria-label");
  svg(x, "", "0 0 12 12", ICONS.bad);
  sortHeads();
  pressFilters();
}

function pressFilters() {
  Object.keys(FILTERS).forEach((f, i) => ui.filters[i].setAttribute("aria-pressed", String(f === state.filter)));
}

function sortBy(c) {
  const s = state.sort;
  state.sort = { col: c.id, desc: s.col === c.id ? !s.desc : !c.asc };
  sortHeads();
  refresh();
}

function sortHeads() {
  ui.ths.forEach((th, i) => {
    if (COLS[i].id === state.sort.col) th.setAttribute("aria-sort", state.sort.desc ? "descending" : "ascending");
    else th.removeAttribute("aria-sort");
  });
}

function pickRow(tr) {
  const v = tr && procRows.get(tr.dataset.key);
  if (v) select("procs", v.p.pid, v.p.start);
}

function rowKey(e) {
  const tr = e.target.closest("tr");
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    pickRow(tr);
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
    if (next) {
      e.preventDefault();
      next.focus();
    }
  }
}

/** Nur eine Zeile steht im Tab-Ablauf (die zuletzt fokussierte, sonst die gewählte oder die erste); Pfeile wandern. */
function rove() {
  for (const v of procRows.values()) {
    const t = v.key === state.cursor ? 0 : -1;
    if (v.tr.tabIndex !== t) v.tr.tabIndex = t;
  }
}

function refresh() {
  if (state.tab === "procs" && state.last) renderProcs(state.last);
}

function makeRow(key) {
  const tr = el("tr");
  tr.dataset.key = key;
  tr.tabIndex = -1; // ohne das Attribut meldet tabIndex zwar -1, die Zeile ist aber nicht fokussierbar
  const name = el("td", "name", tr);
  const v = { tr, key, name: el("b", "nm", name), args: el("span", "s nm", name), cpu: el("td", "r", tr) };
  v.spark = svg(el("td", "", tr), "spark", "0 0 90 18", ["", ""]);
  v.ram = el("td", "r", tr);
  v.io = el("td", "r", tr);
  v.badge = makeBadge(el("td", "", tr));
  procRows.set(key, v);
  return v;
}

function updateRow(v, p) {
  const lang = state.lang, kind = KIND[p.state] || "idle", sel = same(p, state.sel);
  v.p = p;
  setText(v.name, String(p.name));
  setText(v.args, String(p.args || ""));
  setText(v.cpu, fmt({ v: p.cpu, u: "%" }, lang));
  const vals = p.spark.slice(-SPARK_POINTS), step = 90 / (SPARK_POINTS - 1), off = SPARK_POINTS - vals.length;
  const pts = vals.map((y, i) => `${((off + i) * step).toFixed(1)} ${(17 - Math.min(Math.max(y, 0), 100) * 0.15).toFixed(1)}`);
  const line = pts.length ? "M" + pts.join(" L") : "";
  if (v.line !== line) {
    v.line = line;
    v.spark.firstChild.setAttribute("d", line && `M${(off * step).toFixed(1)} 18 L${pts.join(" L")} L90 18Z`);
    v.spark.lastChild.setAttribute("d", line);
  }
  if (v.kind !== kind) {
    v.kind = kind;
    v.spark.setAttribute("class", "spark " + kind);
  }
  setText(v.ram, fmt({ v: p.rss, u: "B" }, lang));
  setText(v.io, fmt({ v: p.io, u: "B/s" }, lang));
  setBadge(v.badge, p.state, text("state." + p.state) + (p.state === "kernel_hang" ? " · " + duration(p.since) : ""));
  if (v.sel !== sel) {
    v.sel = sel;
    v.tr.classList.toggle("sel", sel);
    v.tr.setAttribute("aria-selected", String(sel));
  }
}

function compare(a, b) {
  return typeof a === "string" ? state.collator.compare(a, b) : a - b;
}

function renderProcs(msg) {
  if (!Array.isArray(msg.procs)) { // Python füllt procs erst nach der view-Meldung
    if (ui.d && !same(ui.d, state.sel)) { // andere Auswahl (Chip): das alte Detail verschwindet, bis ihre Daten kommen
      ui.d = ui.shown = null;
      ui.dbody.hidden = true;
    }
    renderButtons(); // auch „läuft …“ gleich nach dem Bestätigen
    return;
  }
  hdrInfo();
  const col = COLS.find((c) => c.id === state.sort.col), dir = state.sort.desc ? -1 : 1, q = state.query;
  const list = msg.procs.filter((p) => FILTERS[state.filter](p) && (!q || `${p.name}\n${p.args}`.toLowerCase().includes(q)));
  list.sort((a, b) => dir * compare(col.get(a), col.get(b)) || a.pid - b.pid); // pid: Gleichstand springt nicht
  if (state.autoPick && !state.sel && list.length) { // nur Sichtprüfung (#procs): obersten Prozess wählen
    state.autoPick = false;
    return select("procs", list[0].pid, list[0].start);
  }
  const views = list.map((p) => {
    const v = procRows.get(keyOf(p)) || makeRow(keyOf(p));
    updateRow(v, p);
    return v;
  });
  const shown = new Set(views);
  for (const [k, v] of procRows) {
    if (!shown.has(v)) {
      v.tr.remove();
      procRows.delete(k);
    }
  }
  if (views.some((v, i) => ui.tbody.children[i] !== v.tr)) {
    const focused = document.activeElement; // Umhängen nimmt der Zeile den Fokus
    ui.tbody.replaceChildren(...views.map((v) => v.tr));
    if (focused && focused !== document.activeElement && focused.isConnected) focused.focus({ preventScroll: true });
  }
  if (!procRows.has(state.cursor)) {
    const sk = state.sel && keyOf(state.sel);
    state.cursor = procRows.has(sk) ? sk : views.length ? views[0].key : null;
  }
  rove();
  renderDetail(msg);
}

function ioText(d) {
  if (d.io == null) return d.own ? "–" : text("detail.io_hidden");
  const rate = fmt({ v: d.io, u: "B/s" }, state.lang);
  // Dauerlast ohne E/A heißt: seit since kein Byte gelesen oder geschrieben
  return d.state === "busy_noio" ? fill("detail.io_since", { rate, since: duration(d.since) }) : rate;
}

/** Gewählter Prozess: volles detail von Python, bis dahin (gleich nach dem Klick) die Tabellenzeile. */
function renderDetail(msg) {
  const sel = state.sel, lang = state.lang;
  const full = msg.detail && same(msg.detail, sel) ? msg.detail : null;
  const d = full || (sel && msg.procs.find((p) => same(p, sel))) || null;
  ui.shown = full;
  ui.d = d;
  ui.none.hidden = !!d;
  ui.dbody.hidden = !d;
  renderButtons();
  if (!d) return;
  setText(ui.dname, String(d.name));
  ui.dname.title = String(d.name);
  fillInto(ui.dpid, text("detail.pid_user"), { pid: d.pid, user: String(d.user) });
  setText(ui.dcmd, full ? String(full.cmdline) : "");
  const hist = full ? full.history : [];
  drawArea(ui.dcanvas, [{ fill: true, max: Math.max(100, Math.ceil(Math.max(0, ...hist) / 100) * 100), values: hist }],
           { color: AREA.cpu, gridEvery: PROC_GRID, points: PROC_POINTS });
  const num = (x) => number(x, lang, 0, x < 10 ? 1 : 0, false);
  pairs(ui.dkv, [
    [text("detail.cpu"), d.cpu >= 90 && d.cpu <= 105 ? fill("detail.cpu_one_core", { pct: num(d.cpu) }) : fmt({ v: d.cpu, u: "%" }, lang)],
    [text("detail.ram"), fmt({ v: d.rss, u: "B" }, lang)],
    [text("detail.io"), ioText(d)],
    [text("detail.threads"), fmt({ v: d.threads, u: "" }, lang)], // Zeile ohne threads: „–“
    [text("detail.ctx"), full ? fill("detail.ctx_value", { vol: num(full.vctx), invol: num(full.nvctx) }) : "–"],
    [text("detail.started"), full ? fill("detail.started_value",
      { time: clock(full.started), age: duration(Date.now() / 1000 - full.started) }) : "–"],
  ]);
  const tpl = text("verdict." + d.state), cut = tpl.indexOf(". ") + 1; // erster Satz fett
  ui.verdict.className = "verdict " + (KIND[d.state] || "idle");
  const parent = !full ? "–" : full.parent ? String(full.parent) : fill("detail.parent_pid", { pid: full.ppid });
  fillInto(ui.verdict, tpl.slice(cut), { since: duration(d.since), parent }, tpl.slice(0, cut));
}

/** Knöpfe frei nur mit vollem Detail der Auswahl, ohne Sperrgrund und ohne laufendes Beenden. */
function renderButtons() {
  const d = ui.d, full = ui.shown;
  const why = !d ? null : d.state === "zombie" ? "result.zombie" : full && full.kernel === true ? "result.kernel"
    : state.pending ? "btn.busy" : null;
  const off = String(!full || !!why); // aria-disabled statt disabled: der Knopf behält den Fokus und nennt den Grund
  for (const b of [ui.term, ui.kill]) if (b.getAttribute("aria-disabled") !== off) b.setAttribute("aria-disabled", off);
  setText(ui.reason, why ? text(why) : "");
  ui.kill.classList.toggle("alert", !!full && state.alert === keyOf(full));
}

// ---- Dialoge ----
function makeDialog(cls, titleId) {
  const d = el("dialog", cls, document.body);
  d.setAttribute("aria-modal", "true");
  d.setAttribute("aria-labelledby", titleId);
  d.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closeDialog(d);
    }
  });
  d.addEventListener("close", () => { // falls die Seite ohne uns schließt; kommt nach unserem Schließen erst später
    if (!d.open) closeDialog(d);
  });
  return el("div", "in", el("div", "frame", d));
}

/** Schließen und den Fokus sofort an den öffnenden Knopf zurückgeben (das close-Ereignis käme erst später). */
function closeDialog(d) {
  d.close();
  const o = state.opener;
  state.opener = state.target = null;
  if (o) o.focus();
}

function openDialog(d, opener, first) {
  state.opener = opener;
  d.showModal();
  first.focus(); // Rückfrage: „Abbrechen“, nie die Bestätigung
}

function buildDialogs() {
  const c = makeDialog("confirm", "confirm-title");
  ui.confirm = c.parentNode.parentNode;
  ui.cTitle = el("h2", "t", c);
  ui.cTitle.id = "confirm-title";
  ui.cText = el("p", "", c);
  const cb = el("div", "btns", c);
  ui.cNo = label(button("btn plain", cb, () => closeDialog(ui.confirm)), "confirm.cancel");
  ui.cYes = button("btn term", cb, confirmed);

  const a = makeDialog("about", "about-title");
  ui.about = a.parentNode.parentNode;
  el("h2", "brand", a, "ORBITOP").id = "about-title";
  ui.version = el("p", "", a);
  for (const k of ["about.license", "about.copyright", "about.fonts"]) label(el("p", "s", a), k);
  label(el("h3", "t", a), "legend.title");
  const leg = el("div", "legend", a);
  for (const s of Object.keys(KIND)) {
    const b = makeBadge(el("div", "", leg));
    setBadge(b, s, "");
    label(b.lastChild, "state." + s);
    label(el("p", "", leg), "legend." + s);
  }
  const ab = el("div", "btns", a);
  ui.aboutClose = label(button("btn plain", ab, () => closeDialog(ui.about)), "btn.close");
  label(button("btn term", ab, () => post({ type: "quit" })), "about.quit");
}

/** Rückfrage öffnen; das Ziel (pid, start) wird jetzt festgehalten, nicht erst beim Bestätigen. */
function ask(force, opener) {
  const d = ui.shown;
  if (!d || !same(d, state.sel) || opener.getAttribute("aria-disabled") === "true") return;
  state.target = { pid: d.pid, start: d.start, force, name: String(d.name) };
  ui.confirm.classList.toggle("kill", force);
  setText(ui.cTitle, text(force ? "confirm.title_kill" : "confirm.title"));
  fillInto(ui.cText, text(force ? "confirm.kill_text" : "confirm.terminate_text"), { name: String(d.name), pid: d.pid });
  setText(ui.cYes, text(force ? "confirm.yes_kill" : "confirm.yes"));
  ui.cYes.className = "btn " + (force ? "kill" : "term");
  openDialog(ui.confirm, opener, ui.cNo);
}

function confirmed() {
  const t = state.target;
  closeDialog(ui.confirm);
  if (!t || state.pending) return; // Python verwirft ein zweites terminate ohnehin still
  state.pending = state.lastTerm = t;
  state.alert = null;
  post({ type: "terminate", pid: t.pid, start: t.start, force: t.force });
  refresh();
}

/** Ergebnis als Meldung; t (Ziel der Rückfrage) nennt den Prozess, denn die Auswahl kann inzwischen eine andere sein. */
function notify(code, t) {
  const msg = text("result." + (RESULTS.includes(code) ? code : "error"));
  fillInto(ui.noticeText, t ? text("notice.for") : msg, t ? { name: t.name, pid: t.pid, text: msg } : {});
  ui.notice.hidden = false;
}

// ---- Brücke ----
window.orbitop = {
  receive(msg) {
    if (!msg) return;
    if (msg.type === "init") {
      state.lang = msg.lang === "de" ? "de" : "en";
      state.texts = msg.texts || {};
      state.version = String(msg.version || "");
      state.collator = new Intl.Collator(state.lang);
      document.documentElement.lang = state.lang;
      for (const [node, key, attr] of ui.labels) {
        if (attr) node.setAttribute(attr, text(key));
        else node.textContent = text(key);
      }
      setText(ui.version, fill("about.version", { version: state.version }));
      hdrInfo();
    } else if (msg.type === "tick") {
      state.last = msg;
      state.n++;
      renderFooter(msg.missing, msg.hints);
      if (state.tab === "overview") renderOverview(msg); // ausgeblendete Kacheln nicht zeichnen
      else renderProcs(msg);
    } else if (msg.type === "terminate_result") {
      const t = state.pending;
      state.pending = null; // Python nimmt erst jetzt wieder ein terminate an
      notify(msg.result, t && t.pid === msg.pid ? t : null);
      refresh();
    } else if (msg.type === "terminate_check") {
      const t = state.lastTerm;
      if (!t || msg.pid !== t.pid) return;
      if (msg.alive) state.alert = keyOf(t); // „Sofort beenden“ hervorheben
      else notify("gone", t);
      refresh();
    }
  },
};

build();
if (location.hash === "#procs") { // Sichtprüfung: demo.html#procs, App mit ORBITOP_TAB=procs
  state.autoPick = true;
  select("procs", null, null);
}
post({ type: "ready" });
