// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Spaltenmenü am Kopf der Tabelle, per Maus und Tastatur. Lagen setzt nur CSSOM.
import { el } from "../dom.js";
import { state, ui } from "../state.js";
import { COLS } from "./columns.js";
import { moveColumn, renderMenu, restoreLayout, toggleColumn } from "./layout.js";

// ---- Spaltenmenü (Rechtsklick, Menütaste oder Umschalt+F10 auf einem Kopf) ----
export function buildMenu() {
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

/** Idempotent: WebKit kann zur Menütaste zusätzlich ein contextmenu schicken. */
export function openColumnMenu(th, x, y) {
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
