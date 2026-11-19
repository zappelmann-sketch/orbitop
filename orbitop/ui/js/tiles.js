// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Kachelraster der Übersicht: je Kachel Kopf, Segmente, Verlauf, Threads, Legende, Werte und Geräte.
// Inline-Stile verbietet die CSP; Farben setzt nur CSSOM.
import { drawArea, drawSegments } from "./chart.js";
import { el, pairs, setText, svg } from "./dom.js";
import { BYTES, byteStep, fill, fmt, shortName, show, text } from "./format.js";
import { state, tiles, ui } from "./state.js";

const POINTS = 300, THREAD_POINTS = 60, GRID_SECONDS = 30, MAX_MINIS = 8; // Puffergrößen wie im Sampler, 1 s je Punkt
export const AREA = { cpu: "#4fd8ff", gpu: "#c48bff", mem: "#3dffa8", power: "#ffd84f", temp: "#ff5f7a", fan: "#ff7ad9",
                      net: "#5b8cff", disk: "#2ff0d0" };
const SECOND = "#ffb347"; // Zweitlinie: Swap, Senden, Schreiben
const GPU_SHADES = [AREA.gpu, "#a17bff", "#dfb5ff", "#8a62dc"]; // weitere Grafikchips
const EXTRA = { mem: [SECOND], temp: [AREA.mem, AREA.gpu], fan: [SECOND, AREA.cpu], net: [SECOND], disk: [SECOND] };
const CAPS = { cpu: "cap.usage", gpu: "cap.usage", mem: "cap.occupancy", power: "cap.watt", temp: "cap.celsius",
               fan: "cap.rpm", net: "cap.rate", disk: "cap.rate" };

function colorsOf(t) {
  const gpu = /^gpu(\d+)$/.exec(t.id);
  const first = t.kind === "gpu" ? GPU_SHADES[(gpu ? Number(gpu[1]) : 0) % GPU_SHADES.length] : AREA[t.kind] || AREA.cpu;
  return [first, ...(EXTRA[t.kind] || [])];
}

/** Diagrammfläche: Beschriftung, Gitter (SVG) und darüber die Canvas der Kurven (zurückgegeben). */
export function plot(parent, cls, cap) {
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

export function renderTiles(list) {
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
