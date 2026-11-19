// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Gemeinsames der Prüfungen des Reiters „Prozesse“: Messen, Suchen, Tasten, Zeiger, Ziehen, layout-Meldungen und
// die Testzeilen base und moved.
import { sizeCols } from "../../../../orbitop/ui/js/procs/layout.js";
import { state } from "../../../../orbitop/ui/js/state.js";
import { $, $$, names, row, th } from "../kit.js";
import { flush, posted } from "../stubs.js";

export const measure = () => { // wie der ResizeObserver, der in dieser Prüfung nicht läuft
  state.viewW = $(".procs .scroll").clientWidth;
  sizeCols();
};
export const find = (q) => {
  const search = $(".search");
  search.value = q;
  search.dispatchEvent(new Event("input"));
  return names();
};
export const ids = () => [...$$(".ptable th")].map((t) => t.dataset.col).join();
export const layouts = () => posted.filter((m) => JSON.parse(m).type === "layout");
export const key = (node, k, extra) => node.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra }));
export const colW = (id) => parseFloat($$(".ptable col")[[...$$(".ptable th")].indexOf(th(id))].style.width);
export const grip = (id) => th(id).querySelector(".grip"), dblclick = (node) => node.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
export const listW = () => $(".frame.list").getBoundingClientRect().width;
export const detailW = () => $(".frame.detail").getBoundingClientRect().width;
export const pointer = (node, type, x, extra) =>
  node.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, clientX: x, ...extra }));
export let layoutsDuringMove = 0;
/** Drücken, um dx ziehen (during prüft mitten im Ziehen), loslassen; gibt die Zahl der layouts vorher zurück. */
export const drag = (node, dx, during = () => {}) => {
  flush();
  const before = layouts().length, x = node.getBoundingClientRect().left + 1;
  pointer(node, "pointerdown", x);
  pointer(node, "pointermove", x + dx, { buttons: 1 });
  during();
  flush(); // auch ein erst geplantes layout zählt
  layoutsDuringMove = layouts().length - before;
  pointer(node, "pointerup", x + dx);
  return before;
};
export const reported = (fn) => { // layout-Meldungen, die fn auslöst (vorher ausstehende sind schon gesendet)
  flush();
  const n = layouts().length;
  fn();
  flush();
  return layouts().length - n;
};
/** Drücken, um dx ziehen, abbrechen (pointercancel); gibt die Zahl der layout-Meldungen zurück. */
export const cancelled = (node, dx) => reported(() => {
  const x = node.getBoundingClientRect().left + 1;
  pointer(node, "pointerdown", x);
  pointer(node, "pointermove", x + dx, { buttons: 1 });
  pointer(node, "pointercancel", x + dx);
});
export const DEFAULT_IDS = "pid,process,user,cpu,last60,ram,io,state";
export const base = [row(1, { name: "beta", cpu: 5, rss: 300, own: false, io: null, state: "busy_iounknown", since: 200 }),
                     row(2, { name: "alpha", cpu: 50, rss: 100, args: "--needle", state: "working" }),
                     row(3, { name: "Gamma", cpu: 20, rss: 200, state: "zombie" }), row(42, { start: 7, name: "chip", cpu: 1 })];
export const moved = [{ ...base[1], cpu: 1 }, { ...base[0], cpu: 90 }, base[2], base[3]];
