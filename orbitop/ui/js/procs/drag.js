// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Ziehen von Spaltenbreite, Spaltenreihenfolge und Trenner. Lagen setzt nur CSSOM.
import { state, ui } from "../state.js";
import { placeColumn, saveLayout, sendLayout, setWidth, showSplit, sizeCols, splitTo } from "./layout.js";

// ---- Ziehen: Breite am Griff, Reihenfolge am Kopf, Trenner; Bewegung und Ende am document, gemeldet erst am Ende ----
/** Breite der Spalte, wie sie gezeichnet ist (Prozess also samt aufgefülltem Rest). */
export function colWidth(th) {
  return parseFloat(ui.colgroup.children[ui.ths.indexOf(th)].style.width);
}

/** mark bekommt beim Ziehen die Klasse on; th: Kopf (Breite, Umordnen), sonst der Trenner. old: Breiten bzw. Anteil für
 * pointercancel (Umordnen ändert erst beim Ablegen etwas). */
export function startDrag(e, kind, mark, th) {
  if (state.drag) dragEnd({ pointerId: state.drag.pointer }); // hängender Zug (Loslassen verloren): endet wie losgelassen
  state.drag = { kind, mark, id: th && th.dataset.col, pointer: e.pointerId, x: e.clientX, moved: false, to: null,
                 owe: false, w: th ? colWidth(th) : ui.list.getBoundingClientRect().width,
                 old: kind === "split" ? state.layout.split : kind === "width" ? { ...state.layout.widths } : null };
  document.body.dataset.drag = kind; // keine Textauswahl, Mauszeiger bleibt
}

export function dragMove(e) {
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
export function dragEnd(e) {
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
