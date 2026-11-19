// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Aufbau von Suche, Filtern, Tabelle, Trenner, Detail und Meldung; die Ereignisse gehen an
// die übrigen Module unter procs/.
import { button, el, label, svg } from "../dom.js";
import { state, ui } from "../state.js";
import { plot } from "../tiles.js";
import { FILTERS, ICONS } from "./columns.js";
import { colWidth, dragEnd, dragMove, startDrag } from "./drag.js";
import { applyLayout, DEFAULT_SPLIT, saveLayout, setWidth, showSplit, sizeCols, splitTo } from "./layout.js";
import { buildMenu, openColumnMenu } from "./menu.js";
import { pickRow, refresh, renderRows, rove, rowKey, rowPitch } from "./rows.js";

/** ask: Rückfrage vor dem Beenden aus dialogs.js, von page.build hereingereicht (dialogs.js importiert procs/view.js). */
export function buildProcs(ask) {
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
