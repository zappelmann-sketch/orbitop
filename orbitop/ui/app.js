// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Oberfläche: Kopfzeile, Lastzeile, Kachelraster und Fußzeile. Alles aus dem Schnappschuss und aus texts kommt per
// textContent ins DOM, nie als HTML. Inline-Stile verbietet die CSP; Farben setzt nur CSSOM (style.setProperty).
"use strict";

const POINTS = 300, THREAD_POINTS = 60, GRID_SECONDS = 30, MAX_MINIS = 8; // Puffergrößen wie im Sampler
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

const state = { lang: "en", texts: {}, tab: "overview", last: null, briefs: [] };
const ui = { labels: [] };
const tiles = new Map(); // Kachel-id -> Elemente
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
  const u = num.u, of = num.of == null ? null : num.of;
  let unit = u, scale = 1;
  if (u === "B" || u === "B/s") {
    const big = Math.max(Math.abs(num.v), Math.abs(of || 0));
    let e = 0;
    while (e < BYTES.length - 1 && big >= 1024 ** (e + 1)) e++;
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

function label(node, key) {
  ui.labels.push([node, key]);
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
  label(el("span", "s", hdr), "strip.tick");
  ui.overview = el("section", "overview", body);
  const strip = el("div", "strip", ui.overview);
  label(el("span", "lbl", strip), "strip.top");
  ui.chips = el("span", "chips", strip);
  label(el("span", "s hint", strip), "strip.hint");
  ui.grid = el("div", "grid", ui.overview);
  ui.procs = el("section", "procs", body); // füllt Task 15
  ui.footer = el("footer", "foot", body);
  showTab("overview");
}

function showTab(name) {
  state.tab = name;
  ui.overview.hidden = name !== "overview";
  ui.procs.hidden = name !== "procs";
  ui.tabs.forEach((b, i) => {
    b.classList.toggle("on", TABS[i] === name);
    b.setAttribute("aria-pressed", String(TABS[i] === name));
  });
}

function select(name, pid, start) {
  showTab(name);
  post({ type: "view", tab: name, pid, start });
  if (name === "overview" && state.last) renderOverview(state.last);
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
      if (p) select("procs", p.pid, p.start); // Auswahl in der Liste vollendet Task 15
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

function plot(parent, cls, cap) {
  const box = el("div", cls, parent);
  el("span", "cap", box, cap);
  return el("canvas", "", box);
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
    canvas: plot(inner, "plot", text(CAPS[t.kind] || "cap.usage")),
    threads: el("div", "", inner), threadEls: [], legend: el("div", "lg", inner), legendSig: null,
    kv: el("div", "kv", inner), dev: el("div", "kv dev", inner),
  };
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
    } else {
      drawArea(v.threadEls[i], [{ fill: true, max: 100, values }],
               { color: v.colors[0], gridSeconds: GRID_SECONDS, points: THREAD_POINTS });
    }
  });
}

function updateTile(v, t) {
  const name = t.name ? shortName(String(t.name)) : "";
  setText(v.kind, text("tile." + t.kind) + (name ? " · " : ""));
  setText(v.name, name);
  v.name.title = t.name ? String(t.name) : "";
  setText(v.main, fmt(t.main, state.lang));
  setText(v.aside, t.aside == null ? "" : show(t.aside));
  drawSegments(v.seg, t.seg);
  drawArea(v.canvas, t.series, { color: v.colors[0], color2: v.colors[1], color3: v.colors[2],
                                 gridSeconds: GRID_SECONDS, points: POINTS });
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
  pairs(v.dev, (t.devices || []).map((d) => [String(d.name),
    d.values.filter((n) => n.v != null).map((n) => fmt(n, state.lang)).join(" · ")]));
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

// ---- Brücke ----
window.orbitop = {
  receive(msg) {
    if (!msg) return;
    if (msg.type === "init") {
      state.lang = msg.lang === "de" ? "de" : "en";
      state.texts = msg.texts || {};
      document.documentElement.lang = state.lang;
      for (const [node, key] of ui.labels) node.textContent = text(key);
    } else if (msg.type === "tick") {
      state.last = msg;
      renderFooter(msg.missing, msg.hints);
      if (state.tab === "overview") renderOverview(msg); // ausgeblendete Kacheln nicht zeichnen
    }
  },
};

build();
post({ type: "ready" });
