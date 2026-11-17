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
  rows: [], scrollTop: 0, viewH: 0, viewW: 0, pitch: 0, block: null, // Prozessliste: sortiert, Rollstand, gemessene Größen
  layout: null, memTotal: null, menuCol: null, savedAt: -Infinity, saving: false, // Spalten, %MEM, Menü, layout-Meldung
  drag: null, noClick: false, // laufendes Ziehen; Klick nach dem Umordnen verwerfen
  target: null, opener: null, pending: null, lastTerm: null, alert: null, // Rückfrage, laufendes Beenden, Nachsehen
};
const ui = { labels: [] };
const tiles = new Map(); // Kachel-id -> Elemente
const procRows = new Map(); // "pid:start" -> Zeilenelemente, nur gezeichnete Zeilen
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

/** Diagrammfläche: Beschriftung, Gitter (SVG) und darüber die Canvas der Kurven (zurückgegeben). */
function plot(parent, cls, cap) {
  const box = el("div", cls, parent);
  el("span", "cap", box, cap);
  const c = el("canvas", "", box);
  c.grid = svg(box, "gridlines", null, [""]);
  box.append(c);
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
const BUFFER_ROWS = 6, GUESS_PITCH = 31; // Zeilen über und unter dem Sichtbereich; Zeilenabstand, bis er gemessen ist
const SVG_NS = "http://www.w3.org/2000/svg";
const KIND = { working: "ok", waiting: "idle", busy_noio: "warn", busy_iounknown: "warn", kernel_hang: "bad",
               stopped: "stop", zombie: "dead" }; // Farbe und Symbol je Zustand, wie im Entwurf
const ICONS = { ok: ["M2 6.5l2.5 2.5L10 3.5"], idle: ["M3 6a3 3 0 1 0 6 0a3 3 0 1 0-6 0"], warn: ["M6 1.5l5 9H1z", "M6 5v2.5"],
                bad: ["M3 3l6 6M9 3l-6 6"], stop: ["M4 2.5v7M8 2.5v7"] };
ICONS.dead = ICONS.idle;
const SEVERITY = ["waiting", "working", "zombie", "stopped", "busy_iounknown", "busy_noio", "kernel_hang"]; // absteigend: Auffälliges zuerst
// Grundreihenfolge = layout.COLUMNS (Test), eine Zeile je Spalte. w: Standardbreite in px, off: standardmäßig aus,
// asc: zuerst aufsteigend, cls "r": rechtsbündig, get: Sortierschlüssel, show: Zelltext (sonst String(get)).
// Prozess, Verlauf und Zustand zeichnen eigene Elemente (makeRow).
const COLS = [
  { id: "pid", key: "col.pid", tip: "coltip.pid", w: 64, asc: true, cls: "r", get: (p) => p.pid },
  { id: "process", key: "col.process", tip: "coltip.process", w: 240, asc: true, get: (p) => String(p.name) },
  { id: "user", key: "col.user", tip: "coltip.user", w: 96, asc: true, get: (p) => String(p.user) },
  { id: "cpu", key: "col.cpu", tip: "coltip.cpu", w: 52, cls: "r", get: (p) => p.cpu, show: (p) => withUnit(p.cpu, "%") },
  { id: "last60", key: "col.last60", tip: "coltip.last60", w: 104, get: (p) => p.spark.reduce((a, b) => a + b, 0) },
  { id: "ram", key: "col.ram", tip: "coltip.ram", w: 74, cls: "r", get: (p) => p.rss, show: (p) => withUnit(p.rss, "B") },
  { id: "io", key: "col.io", tip: "coltip.io", w: 80, cls: "r", get: (p) => p.io ?? -1, show: (p) => withUnit(p.io, "B/s") },
  { id: "state", key: "col.state", tip: "coltip.state", w: 200, get: (p) => SEVERITY.indexOf(p.state) },
  { id: "pri", key: "col.pri", tip: "coltip.pri", w: 44, off: true, cls: "r", get: (p) => p.pri },
  { id: "nice", key: "col.nice", tip: "coltip.nice", w: 44, off: true, cls: "r", get: (p) => p.nice },
  { id: "virt", key: "col.virt", tip: "coltip.virt", w: 80, off: true, cls: "r", get: (p) => p.virt, show: (p) => withUnit(p.virt, "B") },
  { id: "shr", key: "col.shr", tip: "coltip.shr", w: 80, off: true, cls: "r", get: (p) => p.shr ?? -1, show: (p) => withUnit(p.shr, "B") },
  { id: "s", key: "col.s", tip: "coltip.s", w: 40, off: true, asc: true, get: (p) => String(p.s) },
  { id: "mem", key: "col.mem", tip: "coltip.mem", w: 64, off: true, cls: "r", get: (p) => p.rss, show: memShare },
  { id: "time", key: "col.time", tip: "coltip.time", w: 84, off: true, cls: "r", get: (p) => p.time, show: (p) => cpuTime(p.time) },
];
const MIN_W = 40, MIN_PROCESS_W = 120, MAX_W = 1200, DEFAULT_SPLIT = 1.55 / 2.55, LAYOUT_GAP_MS = 500;
const FILTERS = { all: () => true, mine: (p) => p.own, flagged: (p) => p.state !== "working" && p.state !== "waiting" };
const RESULTS = ["sent", "gone", "mismatch", "zombie", "kernel", "denied", "nohelper", "error"];

const keyOf = (p) => p.pid + ":" + p.start;
const same = (p, sel) => !!sel && p.pid === sel.pid && p.start === sel.start;
const colOf = (id) => COLS.find((c) => c.id === id);

function withUnit(v, u) {
  return fmt({ v, u }, state.lang);
}

/** %MEM: rss am Gesamtspeicher (aside.of der Kachel mem im selben Takt), eine Nachkommastelle, „%“ wie fmt. */
function memShare(p) {
  const of = state.memTotal;
  return of > 0 ? number(p.rss / of * 100, state.lang, 1, 1, false) + (state.lang === "en" ? "%" : "\u00a0%") : "–";
}

/** CPU-Zeit wie TIME+ in top: „m:ss.hh“, auf ganze Hundertstel gerundet, Minuten ohne Obergrenze, immer „.“. */
function cpuTime(sec) {
  const h = Math.round(sec * 100), s = h % 6000;
  return `${Math.floor(h / 6000)}:${String(Math.floor(s / 100)).padStart(2, "0")}.${String(s % 100).padStart(2, "0")}`;
}

function svg(parent, cls, viewBox, paths) {
  const s = document.createElementNS(SVG_NS, "svg");
  if (viewBox) s.setAttribute("viewBox", viewBox);
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
  ui.list = el("div", "frame list", ui.procs);
  const list = el("div", "in", ui.list);
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
  ui.scroll = el("div", "scroll", list);
  ui.table = label(el("table", "ptable", ui.scroll), "tab.procs", "aria-label");
  ui.colgroup = el("colgroup", "", ui.table);
  const thead = el("thead", "", ui.table);
  ui.headRow = el("tr", "", thead);
  ui.ths = [];
  thead.addEventListener("contextmenu", (e) => {
    const th = e.target.closest("th");
    if (!th) return;
    e.preventDefault();
    openColumnMenu(th, e.clientX, e.clientY);
  });
  thead.addEventListener("keydown", (e) => {
    state.noClick = false; // ein Klick per Taste sortiert immer
    const th = e.target.closest("th");
    if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      e.preventDefault(); // sonst ginge WebKit im Verlauf zurück oder vor
      setWidth(th.dataset.col, colWidth(th) + (e.key === "ArrowLeft" ? -16 : 16));
      saveLayout();
    } else if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
      e.preventDefault();
      const r = th.getBoundingClientRect();
      openColumnMenu(th, r.left, r.bottom);
    }
  });
  thead.addEventListener("pointerdown", (e) => {
    const th = e.target.closest("th"), grip = e.target.closest(".grip");
    if (th) startDrag(e, grip ? "width" : "move", grip || th, th);
    state.noClick = false; // erst danach: endet dabei ein hängender Zug, gilt trotzdem der Klick dieses Drückens
  });
  thead.addEventListener("click", (e) => { // nach dem Umordnen sortiert der Klick des Loslassens nicht
    if (!state.noClick) return;
    state.noClick = false;
    e.stopPropagation();
  }, true);
  thead.addEventListener("dblclick", (e) => { // Griff: Standardbreite, bei Prozess wieder „füllt den Rest“
    const th = e.target.closest(".grip") && e.target.closest("th");
    if (!th) return;
    delete state.layout.widths[th.dataset.col];
    sizeCols();
    saveLayout();
  });
  ui.tbody = el("tbody", "", ui.table);
  ui.pads = []; // Abstandszeilen anstelle der nicht gezeichneten Zeilen
  ui.scroll.addEventListener("scroll", () => {
    state.scrollTop = ui.scroll.scrollTop;
    renderRows();
  }, { passive: true });
  // Nach dem Layout gemessen, erzwingt also kein Layout: Größe des Rollbereichs, Rollstand, Zeilenabstand (Schrift)
  const sizes = new ResizeObserver(() => {
    const viewH = ui.scroll.clientHeight, viewW = ui.scroll.clientWidth, top = ui.scroll.scrollTop, pitch = rowPitch();
    if (!viewH) return;
    if (viewW !== state.viewW) { // Prozess-Spalte füllt die Breite
      state.viewW = viewW;
      sizeCols();
    }
    if (viewH === state.viewH && top === state.scrollTop && !(pitch > 0 && pitch !== state.pitch)) return;
    Object.assign(state, { viewH, scrollTop: top }, pitch > 0 ? { pitch } : {});
    renderRows();
  });
  sizes.observe(ui.scroll);
  sizes.observe(ui.table);
  ui.tbody.addEventListener("click", (e) => pickRow(e.target.closest("tr")));
  ui.tbody.addEventListener("keydown", rowKey);
  ui.tbody.addEventListener("focusin", (e) => {
    state.cursor = e.target.closest("tr").dataset.key;
    rove();
  });

  ui.split = label(el("div", "split", ui.procs), "procs.splitter", "aria-label");
  for (const [k, v] of [["role", "separator"], ["aria-orientation", "vertical"], ["aria-valuemin", "20"], ["aria-valuemax", "80"]]) {
    ui.split.setAttribute(k, v);
  }
  ui.split.tabIndex = 0;
  ui.split.addEventListener("pointerdown", (e) => startDrag(e, "split", ui.split, null));
  ui.split.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    splitTo(ui.list.getBoundingClientRect().width + (e.key === "ArrowLeft" ? -32 : 32));
    saveLayout();
  });
  ui.split.addEventListener("dblclick", () => {
    state.layout.split = DEFAULT_SPLIT;
    showSplit();
    saveLayout();
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
  buildMenu();
  ui.drop = el("div", "drop", ui.procs); // Einfügemarke beim Umordnen
  ui.drop.hidden = true;
  document.addEventListener("pointermove", dragMove);
  document.addEventListener("pointerup", dragEnd);
  document.addEventListener("pointercancel", dragEnd);
  applyLayout(null);
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
  for (const th of ui.ths) {
    if (th.dataset.col === state.sort.col) th.setAttribute("aria-sort", state.sort.desc ? "descending" : "ascending");
    else th.removeAttribute("aria-sort");
  }
}

// ---- Spalten: Layout, Kopf, Breiten, Meldung an Python ----
function defaultLayout() {
  return { order: COLS.map((c) => c.id), hidden: COLS.filter((c) => c.off).map((c) => c.id), widths: {},
           split: DEFAULT_SPLIT };
}

function visibleCols() {
  return state.layout.order.filter((id) => !state.layout.hidden.has(id)).map(colOf);
}

/** Layout übernehmen, aus init (null: Standard) oder nach einer Änderung; sendet nie selbst. */
function applyLayout(l) {
  const d = l || defaultLayout();
  state.layout = { order: [...d.order], hidden: new Set(d.hidden), widths: { ...d.widths }, split: d.split };
  if (state.layout.hidden.has(state.sort.col)) state.sort = { col: "cpu", desc: true };
  const sig = visibleCols().map((c) => c.id).join();
  if (ui.headSig !== sig) {
    ui.headSig = sig;
    buildHead();
  }
  sizeCols();
  showSplit();
  if (!ui.menu.hidden) renderMenu();
  refresh();
}

/** Kopf und col-Elemente der sichtbaren Spalten neu; die gezeichneten Zeilen passen nicht mehr und fallen weg. */
function buildHead() {
  const cols = visibleCols();
  ui.colgroup.replaceChildren(...cols.map(() => el("col")));
  ui.ths = cols.map((c) => {
    const th = el("th", c.cls || "");
    th.scope = "col";
    th.dataset.col = c.id;
    button("", th, () => sortBy(c));
    el("span", "grip", th).setAttribute("aria-hidden", "true");
    return th;
  });
  ui.headRow.replaceChildren(...ui.ths);
  labelHead();
  sortHeads();
  for (const v of procRows.values()) v.tr.remove();
  procRows.clear();
  state.block = null;
  for (const tr of ui.pads) tr.firstChild.colSpan = cols.length;
}

/** Texte direkt aus state.texts, nicht über label(): ui.labels wüchse sonst mit jedem Neuaufbau. */
function labelHead() {
  for (const th of ui.ths) {
    const c = colOf(th.dataset.col), b = th.firstChild;
    setText(b, text(c.key));
    if (b.title !== text(c.tip)) b.title = text(c.tip);
  }
}

/** Breiten per CSSOM; die Prozess-Spalte füllt den Rest des Rollbereichs, ohne eigene Breite des Users schrumpft sie
 * dafür bis MIN_PROCESS_W. Die Tabelle ist so breit wie die Summe. */
function sizeCols() {
  const cols = visibleCols(), w = cols.map((c) => state.layout.widths[c.id] ?? c.w);
  const p = cols.findIndex((c) => c.id === "process"), rest = w.reduce((a, b) => a + b, 0) - w[p];
  if (!state.viewW) state.viewW = ui.scroll.clientWidth; // nur bis zur ersten Messung direkt, danach vom ResizeObserver
  w[p] = Math.max(state.layout.widths.process ?? MIN_PROCESS_W, state.viewW - rest);
  w.forEach((x, i) => { ui.colgroup.children[i].style.width = x + "px"; });
  ui.table.style.width = rest + w[p] + "px";
}

/** Breite in px, begrenzt; die Meldung (saveLayout) kommt vom Aufrufer, beim Ziehen erst am Ende. */
function setWidth(id, px) {
  state.layout.widths[id] = Math.round(Math.min(MAX_W, Math.max(id === "process" ? MIN_PROCESS_W : MIN_W, px)));
  sizeCols();
}

function toggleColumn(id) {
  if (id === "process") return; // fest an
  const hidden = new Set(state.layout.hidden);
  if (!hidden.delete(id)) hidden.add(id);
  applyLayout({ ...state.layout, hidden });
  saveLayout();
}

/** Vor (dir −1) oder hinter (+1) den nächsten sichtbaren Nachbarn; ausgeblendete Spalten bleiben, wo sie sind. */
function moveColumn(id, dir) {
  const vis = visibleCols().map((c) => c.id), i = vis.indexOf(id), next = vis[i + dir];
  if (i >= 0 && next) placeColumn(id, next, dir > 0);
}

/** In der Gesamtreihenfolge vor (after: hinter) die Spalte ref setzen und melden. */
function placeColumn(id, ref, after) {
  const order = state.layout.order.filter((x) => x !== id);
  order.splice(order.indexOf(ref) + (after ? 1 : 0), 0, id);
  applyLayout({ ...state.layout, order });
  saveLayout();
}

/** Anteil der Liste ins Raster (CSSOM-Variablen); CSS hält Liste ≥ 360 px und Detail ≥ 300 px, ohne den Wert zu ändern. */
function showSplit() {
  const s = state.layout.split;
  ui.procs.style.setProperty("--list", s + "fr");
  ui.procs.style.setProperty("--detail", 1 - s + "fr");
  ui.split.setAttribute("aria-valuenow", String(Math.round(s * 100)));
}

/** Liste auf px Breite: begrenzt auf den Vertrag 0,2..0,8 und so, dass Liste ≥ 360 px, Detail ≥ 300 px; Meldung beim
 * Aufrufer. */
function splitTo(px) {
  const total = ui.procs.clientWidth - ui.split.offsetWidth;
  state.layout.split = Math.min(0.8, 1 - 300 / total, Math.max(0.2, 360 / total, px / total));
  showSplit();
}

function restoreLayout() {
  applyLayout(null);
  saveLayout();
}

/** Vertrag „Layout“ als Nachricht; hidden in Spaltenreihenfolge, damit gleicher Stand gleiche Datei heißt. */
function layoutMessage() {
  const l = state.layout;
  return { type: "layout", order: [...l.order], hidden: l.order.filter((id) => l.hidden.has(id)), widths: { ...l.widths },
           split: l.split };
}

/** Höchstens eine Meldung je LAYOUT_GAP_MS; was früher kommt, sendet ein einziger Zeitgeber mit dem neuesten Stand. */
function saveLayout() {
  if (state.saving) return;
  const wait = state.savedAt + LAYOUT_GAP_MS - performance.now();
  if (wait > 0) {
    state.saving = true;
    setTimeout(sendLayout, wait);
  } else {
    sendLayout();
  }
}

function sendLayout() {
  if (state.drag) { // nie mitten im Ziehen: dragEnd sendet dann den neuesten Stand
    state.drag.owe = true;
    return;
  }
  state.saving = false;
  state.savedAt = performance.now();
  post(layoutMessage());
}

// ---- Ziehen: Breite am Griff, Reihenfolge am Kopf, Trenner; Bewegung und Ende am document, gemeldet erst am Ende ----
/** Breite der Spalte, wie sie gezeichnet ist (Prozess also samt aufgefülltem Rest). */
function colWidth(th) {
  return parseFloat(ui.colgroup.children[ui.ths.indexOf(th)].style.width);
}

/** mark bekommt beim Ziehen die Klasse on; th: Kopf (Breite, Umordnen), sonst der Trenner. old: Breiten bzw. Anteil für
 * pointercancel (Umordnen ändert erst beim Ablegen etwas). */
function startDrag(e, kind, mark, th) {
  if (state.drag) dragEnd({ pointerId: state.drag.pointer }); // hängender Zug (Loslassen verloren): endet wie losgelassen
  state.drag = { kind, mark, id: th && th.dataset.col, pointer: e.pointerId, x: e.clientX, moved: false, to: null,
                 owe: false, w: th ? colWidth(th) : ui.list.getBoundingClientRect().width,
                 old: kind === "split" ? state.layout.split : kind === "width" ? { ...state.layout.widths } : null };
  document.body.dataset.drag = kind; // keine Textauswahl, Mauszeiger bleibt
}

function dragMove(e) {
  const d = state.drag, dx = d && e.clientX - d.x;
  if (!d || e.pointerId !== d.pointer) return;
  if (!(e.buttons & 1)) return dragEnd(e); // nur mit der Haupttaste; auch wenn ihr Loslassen verloren ging
  if (!d.moved && Math.abs(dx) < 6) return; // unter 6 px: ein Klick, auch an Griff und Trenner
  d.moved = true;
  d.mark.classList.add("on");
  if (d.kind === "width") setWidth(d.id, d.w + dx);
  else if (d.kind === "split") splitTo(d.w + dx);
  else dropAt(d, e.clientX);
}

/** Einfügemarke an der Grenze zwischen sichtbaren Spalten, die dem Zeiger am nächsten liegt; d.to = Index dahinter. */
function dropAt(d, x) {
  const r = ui.ths.map((t) => t.getBoundingClientRect()), box = ui.scroll.getBoundingClientRect();
  d.to = r.filter((b) => b.left + b.width / 2 < x).length;
  const at = d.to < r.length ? r[d.to].left : r[r.length - 1].right;
  ui.drop.style.left = Math.min(Math.max(at, box.left), box.right) + "px";
  ui.drop.style.top = box.top + "px";
  ui.drop.style.height = box.height + "px";
  ui.drop.hidden = false;
}

/** Breite und Trenner melden; Umordnen legt vor der sichtbaren Spalte an der Marke ab, sonst hinter der letzten.
 * pointercancel nimmt den Zug zurück. Eine im Ziehen zurückgehaltene Meldung geht jetzt, einmal mit dem neuesten Stand. */
function dragEnd(e) {
  const d = state.drag;
  if (!d || e.pointerId !== d.pointer) return;
  state.drag = null;
  delete document.body.dataset.drag;
  d.mark.classList.remove("on");
  ui.drop.hidden = true;
  if (e.type === "pointercancel") {
    if (d.kind === "split") {
      state.layout.split = d.old;
      showSplit();
    } else if (d.kind === "width") {
      state.layout.widths = d.old;
      sizeCols();
    }
  } else if (d.moved && d.kind !== "move") {
    saveLayout();
  } else if (d.moved) {
    state.noClick = true;
    const vis = ui.ths.map((t) => t.dataset.col), i = vis.indexOf(d.id), n = vis.length;
    if (d.to !== i && d.to !== i + 1) placeColumn(d.id, vis[Math.min(d.to, n - 1)], d.to === n);
  }
  if (d.owe) sendLayout(); // state.saving stand noch: saveLayout oben hat nichts gesendet
}

// ---- Spaltenmenü (Rechtsklick, Menütaste oder Umschalt+F10 auf einem Kopf) ----
function buildMenu() {
  ui.menu = el("div", "frame menu", ui.procs);
  ui.menu.hidden = true;
  ui.menuBox = el("div", "in", ui.menu);
  ui.menuBox.setAttribute("role", "menu");
  const item = (role) => {
    const b = el("button");
    b.type = "button";
    b.tabIndex = -1;
    b.setAttribute("role", role);
    return b;
  };
  ui.checks = new Map(COLS.map((c) => {
    const b = item("menuitemcheckbox");
    b.dataset.col = c.id;
    return [c.id, b];
  }));
  ui.checks.get("process").setAttribute("aria-disabled", "true");
  ui.menuSep = el("div", "sep");
  ui.menuSep.setAttribute("role", "separator");
  ui.moves = [item("menuitem"), item("menuitem")]; // nach links, nach rechts
  ui.restore = item("menuitem");
  ui.menuBox.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) pickMenu(b);
  });
  ui.menuBox.addEventListener("keydown", menuKey);
  ui.menuBox.addEventListener("focusin", (e) => { // Roving Tabindex: nur der fokussierte Eintrag im Tab-Ablauf
    for (const b of menuItems()) b.tabIndex = b === e.target ? 0 : -1;
  });
  ui.menu.addEventListener("contextmenu", (e) => e.preventDefault()); // kein Menü von WebKit über dem eigenen
  document.addEventListener("pointerdown", (e) => {
    if (!ui.menu.hidden && !ui.menu.contains(e.target)) closeColumnMenu();
  });
}

function menuItems() {
  return [...ui.menuBox.querySelectorAll("button")];
}

/** Häkchen in der Gesamtreihenfolge, Trennstrich, Verschieben der Spalte des Menüs, Standard; Texte aus texts. */
function renderMenu() {
  const l = state.layout, vis = visibleCols().map((c) => c.id), i = vis.indexOf(state.menuCol);
  ui.menuBox.setAttribute("aria-label", text("menu.columns"));
  const checks = l.order.map((id) => {
    const b = ui.checks.get(id);
    setText(b, text(colOf(id).key));
    b.setAttribute("aria-checked", String(!l.hidden.has(id)));
    return b;
  });
  [["menu.move_left", i <= 0], ["menu.move_right", i < 0 || i === vis.length - 1]].forEach(([k, off], j) => {
    setText(ui.moves[j], text(k));
    ui.moves[j].setAttribute("aria-disabled", String(off));
  });
  setText(ui.restore, text("menu.restore"));
  const all = [...checks, ui.menuSep, ...ui.moves, ui.restore];
  if (all.some((x, j) => ui.menuBox.children[j] !== x)) {
    const focused = document.activeElement; // Umhängen nimmt dem Eintrag den Fokus
    ui.menuBox.replaceChildren(...all);
    if (focused && focused !== document.activeElement && focused.isConnected) focused.focus();
  }
}

/** Idempotent: WebKit kann zur Menütaste zusätzlich ein contextmenu schicken. */
function openColumnMenu(th, x, y) {
  if (!ui.menu.hidden && state.menuCol === th.dataset.col) return;
  state.menuCol = th.dataset.col;
  ui.menu.hidden = false;
  renderMenu();
  const r = ui.menu.getBoundingClientRect(), root = document.documentElement; // im Fenster halten
  ui.menu.style.left = Math.max(0, Math.min(x, root.clientWidth - r.width)) + "px";
  ui.menu.style.top = Math.max(0, Math.min(y, root.clientHeight - r.height)) + "px";
  menuItems()[0].focus();
}

function closeColumnMenu() {
  ui.menu.hidden = true;
}

/** Schließen, Fokus zurück auf den Kopf des Menüs (ist die Spalte inzwischen aus: auf Prozess). */
function leaveMenu() {
  closeColumnMenu();
  const th = ui.ths.find((t) => t.dataset.col === state.menuCol) || ui.ths.find((t) => t.dataset.col === "process");
  th.firstChild.focus();
}

/** Häkchen und Verschieben lassen das Menü offen, „Standard wiederherstellen“ schließt es. */
function pickMenu(b) {
  if (b.getAttribute("aria-disabled") === "true") return;
  if (b === ui.restore) {
    restoreLayout();
    leaveMenu();
  } else if (b.dataset.col) {
    toggleColumn(b.dataset.col);
  } else {
    moveColumn(state.menuCol, b === ui.moves[0] ? -1 : 1);
  }
}

function menuKey(e) {
  const list = menuItems(), n = list.length, i = list.indexOf(e.target);
  const to = { ArrowDown: (i + 1) % n, ArrowUp: (i - 1 + n) % n, Home: 0, End: n - 1 };
  if (Object.hasOwn(to, e.key)) {
    e.preventDefault();
    list[to[e.key]].focus();
  } else if (e.key === "Enter" || e.key === " ") {
    e.preventDefault(); // sonst klickte der Knopf zusätzlich selbst
    pickMenu(e.target);
  } else if (e.key === "Escape") {
    e.preventDefault();
    leaveMenu();
  } else if (e.key === "Tab") {
    leaveMenu(); // ohne preventDefault: Tab geht vom Kopf aus weiter
  }
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
    const i = state.rows.findIndex((p) => keyOf(p) === tr.dataset.key);
    const next = i < 0 ? null : state.rows[i + (e.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      e.preventDefault();
      const key = (state.cursor = keyOf(next)); // lokal: renderRows gibt den Fokus zurück, focusin setzt cursor
      renderRows(); // die Zeile kommt in den DOM, falls sie fehlte
      procRows.get(key).tr.focus(); // und rollt ins Bild
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

/** Zellen in der Reihenfolge der sichtbaren Spalten; Systemtexte (Name, Argumente, Benutzer) nur als Text. */
function makeRow(key) {
  const tr = el("tr");
  tr.dataset.key = key;
  tr.tabIndex = -1; // ohne das Attribut meldet tabIndex zwar -1, die Zeile ist aber nicht fokussierbar
  const v = { tr, key, cells: [] };
  for (const c of visibleCols()) {
    const td = el("td", c.cls || "", tr);
    if (c.id === "process") {
      td.className = "name";
      v.name = el("b", "nm", td);
      v.args = el("span", "s nm", td);
    } else if (c.id === "last60") {
      v.spark = svg(td, "spark", "0 0 90 18", ["", ""]);
    } else if (c.id === "state") {
      v.badge = makeBadge(td);
    } else {
      v.cells.push([td, c]);
    }
  }
  procRows.set(key, v);
  return v;
}

function updateRow(v, p) {
  const sel = same(p, state.sel);
  v.p = p;
  for (const [td, c] of v.cells) setText(td, c.show ? c.show(p) : String(c.get(p)));
  if (v.name) {
    setText(v.name, String(p.name));
    setText(v.args, String(p.args || ""));
  }
  if (v.spark) updateSpark(v, p);
  if (v.badge) setBadge(v.badge, p.state, text("state." + p.state) + (p.state === "kernel_hang" ? " · " + duration(p.since) : ""));
  if (v.sel !== sel) {
    v.sel = sel;
    v.tr.classList.toggle("sel", sel);
    v.tr.setAttribute("aria-selected", String(sel));
  }
}

/** Mini-Verlauf der letzten 60 s, Farbe nach Zustand. */
function updateSpark(v, p) {
  const kind = KIND[p.state] || "idle";
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
}

/** Tiefer Vergleich zweier Teile des Schnappschusses (JSON-Werte). */
function equal(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((k) => equal(a[k], b[k]));
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
  const mem = (msg.tiles || []).find((t) => t.id === "mem");
  state.memTotal = mem && mem.aside ? mem.aside.of : null; // für %MEM
  const col = colOf(state.sort.col), dir = state.sort.desc ? -1 : 1, q = state.query;
  const list = msg.procs.filter((p) => FILTERS[state.filter](p) && (!q || `${p.name}\n${p.args}`.toLowerCase().includes(q)));
  list.sort((a, b) => dir * compare(col.get(a), col.get(b)) || a.pid - b.pid); // pid: Gleichstand springt nicht
  if (state.autoPick && !state.sel && list.length) { // nur Sichtprüfung (#procs): obersten Prozess wählen
    state.autoPick = false;
    return select("procs", list[0].pid, list[0].start);
  }
  state.rows = list;
  renderRows();
  renderDetail(msg);
}

/** Gezeichnet werden nur die Zeilen im Sichtbereich plus Puffer und die Zeile mit dem Tab-Halt (sie behält so auch
 * den Fokus); Abstandszeilen mit der Höhe der übrigen halten jede Zeile an ihrem Platz. */
function renderRows() {
  if (!state.viewH) state.viewH = ui.scroll.clientHeight; // nur beim ersten Mal direkt, danach vom ResizeObserver
  const list = state.rows, n = list.length, pitch = state.pitch || GUESS_PITCH, viewH = state.viewH || innerHeight;
  const top = Math.min(state.scrollTop, Math.max(0, n * pitch - viewH)); // nach dem Kürzen der Liste rollt der Browser hoch
  const a = Math.min(n, Math.max(0, Math.floor(top / pitch) - BUFFER_ROWS));
  const b = Math.min(n, Math.ceil((top + viewH) / pitch) + BUFFER_ROWS);
  let c = list.findIndex((p) => keyOf(p) === state.cursor);
  if (c < 0) { // Tab-Halt: die gewählte, sonst die erste Zeile
    const sk = state.sel && keyOf(state.sel);
    c = Math.max(0, list.findIndex((p) => keyOf(p) === sk));
    state.cursor = n ? keyOf(list[c]) : null;
  }
  const idx = Array.from({ length: b - a }, (_, i) => a + i);
  if (n && c < a) idx.unshift(c);
  if (c >= b && c < n) idx.push(c);
  const kids = [], keep = new Set();
  let next = 0, pads = 0;
  const pad = (rowsLeft) => {
    const tr = ui.pads[pads++] || (ui.pads[pads - 1] = makePad());
    const h = rowsLeft * pitch - 1 + "px"; // ohne die untere Linie, die die Zelle selbst zeichnet
    if (tr.firstChild.style.height !== h) tr.firstChild.style.height = h;
    kids.push(tr);
  };
  for (const i of idx) {
    if (i > next) pad(i - next);
    const p = list[i], key = keyOf(p), v = procRows.get(key) || makeRow(key);
    updateRow(v, p);
    if (v.index !== i) v.tr.setAttribute("aria-rowindex", String((v.index = i) + 2)); // Kopfzeile ist 1
    keep.add(key);
    kids.push(v.tr);
    next = i + 1;
  }
  if (n > next) pad(n - next);
  for (const [k, v] of procRows) {
    if (!keep.has(k)) {
      v.tr.remove();
      procRows.delete(k);
    }
  }
  if (kids.length !== ui.tbody.childElementCount || kids.some((tr, i) => ui.tbody.children[i] !== tr)) {
    const focused = document.activeElement; // Umhängen nimmt der Zeile den Fokus
    ui.tbody.replaceChildren(...kids);
    if (focused && focused !== document.activeElement && focused.isConnected) focused.focus({ preventScroll: true });
  }
  if (ui.table.getAttribute("aria-rowcount") !== String(n + 1)) ui.table.setAttribute("aria-rowcount", String(n + 1));
  state.block = b - a > 1 ? [procRows.get(keyOf(list[a])).tr, procRows.get(keyOf(list[b - 1])).tr, b - a] : null;
  rove();
  if (!state.pitch && rowPitch() > 0) { // einmalig: Zeilenabstand noch unbekannt, jetzt messen und richtig setzen
    state.pitch = rowPitch();
    renderRows();
  }
}

/** Abstand zweier Zeilen aus dem zusammenhängend gezeichneten Block, 0 wenn unbekannt oder ausgeblendet. */
function rowPitch() {
  const b = state.block;
  return b ? (b[1].getBoundingClientRect().top - b[0].getBoundingClientRect().top) / (b[2] - 1) : 0;
}

function makePad() {
  const tr = el("tr", "pad");
  tr.setAttribute("aria-hidden", "true");
  el("td", "", tr).colSpan = ui.ths.length;
  return tr;
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
      applyLayout(state.saving ? state.layout : msg.layout); // Meldung steht aus: der neuere Stand der Seite gilt
      labelHead(); // auch ohne Neuaufbau des Kopfes
      setText(ui.version, fill("about.version", { version: state.version }));
      hdrInfo();
    } else if (msg.type === "tick") {
      const prev = state.last;
      // Python lässt die unveränderte Liste weg: dasselbe Array behalten, equal() endet dann bei a === b
      if (msg.procs_same === true) msg.procs = prev && Array.isArray(prev.procs) ? prev.procs : null;
      state.last = msg;
      state.n++;
      renderFooter(msg.missing, msg.hints);
      if (state.tab === "overview") renderOverview(msg); // ausgeblendete Kacheln nicht zeichnen
      // Prozesse kommen alle 2 s: dazwischen bleiben Tabelle und Detail, nur das Alter im Detail läuft weiter
      else if (Array.isArray(msg.procs) && prev && equal(msg.procs, prev.procs) && equal(msg.detail, prev.detail)) renderDetail(msg);
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
