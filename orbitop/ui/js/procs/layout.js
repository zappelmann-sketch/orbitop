// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Spalten-Layout (Reihenfolge, Sichtbarkeit, Breiten, Trenner), Kopf mit Sortierung,
// Inhalt des Spaltenmenüs und die Meldung an Python. Breiten und Lagen setzt nur CSSOM.
import { button, el, setText } from "../dom.js";
import { text } from "../format.js";
import { post } from "../post.js";
import { procRows, state, ui } from "../state.js";
import { COLS, colOf, MAX_W, MIN_PROCESS_W, MIN_W, visibleCols } from "./columns.js";
import { refresh } from "./rows.js";

export const DEFAULT_SPLIT = 1.55 / 2.55;
const LAYOUT_GAP_MS = 500;

// ---- Spalten: Layout, Kopf, Breiten, Meldung an Python ----
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

function defaultLayout() {
  return { order: COLS.map((c) => c.id), hidden: COLS.filter((c) => c.off).map((c) => c.id), widths: {},
           split: DEFAULT_SPLIT };
}

/** Layout übernehmen, aus init (null: Standard) oder nach einer Änderung; sendet nie selbst. */
export function applyLayout(l) {
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
export function labelHead() {
  for (const th of ui.ths) {
    const c = colOf(th.dataset.col), b = th.firstChild;
    setText(b, text(c.key));
    if (b.title !== text(c.tip)) b.title = text(c.tip);
  }
}

/** Breiten per CSSOM; die Prozess-Spalte füllt den Rest des Rollbereichs, ohne eigene Breite des Users schrumpft sie
 * dafür bis MIN_PROCESS_W. Die Tabelle ist so breit wie die Summe. */
export function sizeCols() {
  const cols = visibleCols(), w = cols.map((c) => state.layout.widths[c.id] ?? c.w);
  const p = cols.findIndex((c) => c.id === "process"), rest = w.reduce((a, b) => a + b, 0) - w[p];
  if (!state.viewW) state.viewW = ui.scroll.clientWidth; // nur bis zur ersten Messung direkt, danach vom ResizeObserver
  w[p] = Math.max(state.layout.widths.process ?? MIN_PROCESS_W, state.viewW - rest);
  w.forEach((x, i) => { ui.colgroup.children[i].style.width = x + "px"; });
  ui.table.style.width = rest + w[p] + "px";
}

/** Breite in px, begrenzt; die Meldung (saveLayout) kommt vom Aufrufer, beim Ziehen erst am Ende. Prozess bis zur
 * Füllbreite ändert sichtbar nichts und würde nur zur Untergrenze, also füllt sie dann wieder den Rest. */
export function setWidth(id, px) {
  const w = Math.round(Math.min(MAX_W, Math.max(id === "process" ? MIN_PROCESS_W : MIN_W, px)));
  const rest = visibleCols().reduce((a, c) => a + (c.id === "process" ? 0 : state.layout.widths[c.id] ?? c.w), 0);
  if (id === "process" && w <= state.viewW - rest) delete state.layout.widths.process;
  else state.layout.widths[id] = w;
  sizeCols();
}

export function toggleColumn(id) {
  if (id === "process") return; // fest an
  const hidden = new Set(state.layout.hidden);
  if (!hidden.delete(id)) hidden.add(id);
  applyLayout({ ...state.layout, hidden });
  saveLayout();
}

/** Vor (dir −1) oder hinter (+1) den nächsten sichtbaren Nachbarn; ausgeblendete Spalten bleiben, wo sie sind. */
export function moveColumn(id, dir) {
  const vis = visibleCols().map((c) => c.id), i = vis.indexOf(id), next = vis[i + dir];
  if (i >= 0 && next) placeColumn(id, next, dir > 0);
}

/** In der Gesamtreihenfolge vor (after: hinter) die Spalte ref setzen und melden. */
export function placeColumn(id, ref, after) {
  const order = state.layout.order.filter((x) => x !== id);
  order.splice(order.indexOf(ref) + (after ? 1 : 0), 0, id);
  applyLayout({ ...state.layout, order });
  saveLayout();
}

/** Anteil der Liste ins Raster (CSSOM-Variablen); CSS hält Liste ≥ 360 px und Detail ≥ 300 px, ohne den Wert zu ändern. */
export function showSplit() {
  const s = state.layout.split;
  ui.procs.style.setProperty("--list", s + "fr");
  ui.procs.style.setProperty("--detail", 1 - s + "fr");
  ui.split.setAttribute("aria-valuenow", String(Math.round(s * 100)));
}

/** Liste auf px Breite: begrenzt auf den Vertrag 0,2..0,8 und so, dass Liste ≥ 360 px, Detail ≥ 300 px; Meldung beim
 * Aufrufer. */
export function splitTo(px) {
  const total = ui.procs.clientWidth - ui.split.offsetWidth;
  state.layout.split = Math.min(0.8, 1 - 300 / total, Math.max(0.2, 360 / total, px / total));
  showSplit();
}

export function restoreLayout() {
  applyLayout(null);
  saveLayout();
}

/** Vertrag „Layout“ als Nachricht; hidden in Spaltenreihenfolge, damit gleicher Stand gleiche Datei heißt. */
export function layoutMessage() {
  const l = state.layout;
  return { type: "layout", order: [...l.order], hidden: l.order.filter((id) => l.hidden.has(id)), widths: { ...l.widths },
           split: l.split };
}

/** Höchstens eine Meldung je LAYOUT_GAP_MS; was früher kommt, sendet ein einziger Zeitgeber mit dem neuesten Stand. */
export function saveLayout() {
  if (state.saving) return;
  const wait = state.savedAt + LAYOUT_GAP_MS - performance.now();
  if (wait > 0) {
    state.saving = true;
    setTimeout(sendLayout, wait);
  } else {
    sendLayout();
  }
}

export function sendLayout() {
  if (state.drag) { // nie mitten im Ziehen: dragEnd sendet dann den neuesten Stand
    state.drag.owe = true;
    return;
  }
  state.saving = false;
  state.savedAt = performance.now();
  post(layoutMessage());
}

// ---- Inhalt des Spaltenmenüs: hier, weil applyLayout ihn neu zeichnet; Aufbau und Bedienung in menu.js ----
/** Häkchen in der Gesamtreihenfolge, Trennstrich, Verschieben der Spalte des Menüs, Standard; Texte aus texts. */
export function renderMenu() {
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
