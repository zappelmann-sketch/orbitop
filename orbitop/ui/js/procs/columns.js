// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Spalten, Zustände und Formate der Zellen; Schlüssel eines Prozesses (pid, start).
import { el, pathEl, setText, svg } from "../dom.js";
import { fmt, number, text } from "../format.js";
import { state } from "../state.js";

export const KIND = { working: "ok", waiting: "idle", busy_noio: "warn", busy_iounknown: "warn", kernel_hang: "bad",
                      stopped: "stop", zombie: "dead" }; // Farbe und Symbol je Zustand, wie im Entwurf
export const ICONS = { ok: ["M2 6.5l2.5 2.5L10 3.5"], idle: ["M3 6a3 3 0 1 0 6 0a3 3 0 1 0-6 0"], warn: ["M6 1.5l5 9H1z", "M6 5v2.5"],
                       bad: ["M3 3l6 6M9 3l-6 6"], stop: ["M4 2.5v7M8 2.5v7"] };
ICONS.dead = ICONS.idle;
const SEVERITY = ["waiting", "working", "zombie", "stopped", "busy_iounknown", "busy_noio", "kernel_hang"]; // absteigend: Auffälliges zuerst
// Grundreihenfolge = layout.COLUMNS (Test), eine Zeile je Spalte. w: Standardbreite in px, off: standardmäßig aus,
// asc: zuerst aufsteigend, cls "r": rechtsbündig, get: Sortierschlüssel, show: Zelltext (sonst String(get)).
// Prozess, Verlauf und Zustand zeichnen eigene Elemente (makeRow).
export const COLS = [
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
export const MIN_W = 40, MIN_PROCESS_W = 120, MAX_W = 1200; // Spaltenbreiten in px
export const FILTERS = { all: () => true, mine: (p) => p.own, flagged: (p) => p.state !== "working" && p.state !== "waiting" };
export const RESULTS = ["sent", "gone", "mismatch", "zombie", "kernel", "denied", "nohelper", "error"];

export const keyOf = (p) => p.pid + ":" + p.start;
export const same = (p, sel) => !!sel && p.pid === sel.pid && p.start === sel.start;
export const colOf = (id) => COLS.find((c) => c.id === id);

export function visibleCols() {
  return state.layout.order.filter((id) => !state.layout.hidden.has(id)).map(colOf);
}

function withUnit(v, u) {
  return fmt({ v, u }, state.lang);
}

/** %MEM: rss am Gesamtspeicher (aside.of der Kachel mem im selben Takt), eine Nachkommastelle, „%“ wie fmt. */
function memShare(p) {
  const of = state.memTotal;
  return of > 0 ? number(p.rss / of * 100, state.lang, 1, 1, false) + (state.lang === "en" ? "%" : "\u00a0%") : "–";
}

/** CPU-Zeit wie TIME+ in top: „m:ss.hh“, auf ganze Hundertstel gerundet, Minuten ohne Obergrenze, immer „.“. */
export function cpuTime(sec) {
  const h = Math.round(sec * 100), s = h % 6000;
  return `${Math.floor(h / 6000)}:${String(Math.floor(s / 100)).padStart(2, "0")}.${String(s % 100).padStart(2, "0")}`;
}

/** Sekunden als „45 s“, „4 Min 12 s“ (unter 10 Min), „38 Min“, „2 Std 5 Min“, „2 T 4 Std“. */
export function duration(sec) {
  const s = Math.max(0, Math.round(sec)), m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  const [min, hr, day] = ["unit.min", "unit.h", "unit.d"].map(text);
  if (s < 60) return `${s} s`;
  if (d) return `${d} ${day} ${h % 24} ${hr}`;
  if (h) return `${h} ${hr} ${m % 60} ${min}`;
  return m < 10 && s % 60 ? `${m} ${min} ${s % 60} s` : `${m} ${min}`;
}

/** Startzeit in Ortszeit; älter als ein Tag mit Datum. */
export function clock(epoch) {
  const opts = { hour: "2-digit", minute: "2-digit" };
  if (Date.now() / 1000 - epoch >= 86400) Object.assign(opts, { day: "2-digit", month: "2-digit" });
  return new Date(epoch * 1000).toLocaleString(state.lang, opts);
}

export function makeBadge(parent) {
  const b = el("span", "st", parent);
  svg(b, "", "0 0 12 12", []);
  el("span", "", b);
  return b;
}

export function setBadge(b, st, label) {
  const kind = KIND[st] || "idle";
  if (b.state !== st) {
    b.state = st;
    b.className = "st " + kind;
    b.firstChild.replaceChildren(...ICONS[kind].map(pathEl));
  }
  setText(b.lastChild, label);
}
