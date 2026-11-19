// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Zeilen der Tabelle, gezeichnet nur im Sichtbereich, Auswahl und Tastatur.
// Systemtexte kommen nur per textContent ins DOM, nie als HTML; Höhen setzt nur CSSOM.
import { el, setText, svg } from "../dom.js";
import { text } from "../format.js";
import { hdrInfo } from "../header.js";
import { calls, procRows, state, ui } from "../state.js";
import { colOf, duration, FILTERS, KIND, keyOf, makeBadge, same, setBadge, visibleCols } from "./columns.js";
import { renderButtons, renderDetail } from "./detail.js";

const SPARK_POINTS = 30; // 2 s je Punkt: Zeile 60 s
const BUFFER_ROWS = 6, GUESS_PITCH = 31; // Zeilen über und unter dem Sichtbereich; Zeilenabstand, bis er gemessen ist

export function pickRow(tr) {
  const v = tr && procRows.get(tr.dataset.key);
  if (v) calls.select("procs", v.p.pid, v.p.start);
}

export function rowKey(e) {
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
export function rove() {
  for (const v of procRows.values()) {
    const t = v.key === state.cursor ? 0 : -1;
    if (v.tr.tabIndex !== t) v.tr.tabIndex = t;
  }
}

export function refresh() {
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
export function equal(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((k) => equal(a[k], b[k]));
}

export function compare(a, b) {
  return typeof a === "string" ? state.collator.compare(a, b) : a - b;
}

export function renderProcs(msg) {
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
    return calls.select("procs", list[0].pid, list[0].start);
  }
  state.rows = list;
  renderRows();
  renderDetail(msg);
}

/** Gezeichnet werden nur die Zeilen im Sichtbereich plus Puffer und die Zeile mit dem Tab-Halt (sie behält so auch
 * den Fokus); Abstandszeilen mit der Höhe der übrigen halten jede Zeile an ihrem Platz. */
export function renderRows() {
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
export function rowPitch() {
  const b = state.block;
  return b ? (b[1].getBoundingClientRect().top - b[0].getBoundingClientRect().top) / (b[2] - 1) : 0;
}

function makePad() {
  const tr = el("tr", "pad");
  tr.setAttribute("aria-hidden", "true");
  el("td", "", tr).colSpan = ui.ths.length;
  return tr;
}
