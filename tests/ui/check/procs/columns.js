// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Spalten und Formate (procs/columns.js): Standard, Tooltip, TIME+, neue Spalten, Sortieren nach jeder Spalte.
import { COLS, cpuTime } from "../../../../orbitop/ui/js/procs/columns.js";
import { applyLayout, layoutMessage, setWidth } from "../../../../orbitop/ui/js/procs/layout.js";
import { compare } from "../../../../orbitop/ui/js/procs/rows.js";
import { state, ui } from "../../../../orbitop/ui/js/state.js";
import { cell, eq, full, G, hb, plain, ptick, receive, row, rows, th, tick } from "../kit.js";
import { base, DEFAULT_IDS, ids } from "./kit.js";

/** Gibt die Zahl der Texte in ui.labels zurück; checkSortHidden prüft, dass sie nicht wächst. */
export function checkColumns() {
  // ---- Spalten: Standard, Tooltip, TIME+, Formate der neuen Spalten ----
  const labelCount = ui.labels.length;
  eq(ids(), DEFAULT_IDS, "Standardspalten in Grundreihenfolge");
  eq(hb("pid").title, "Prozessnummer", "Tooltip aus coltip.pid");
  eq([cpuTime(0), cpuTime(3.5), cpuTime(59.999), cpuTime(7530.5)].join("|"), "0:00.00|0:03.50|1:00.00|125:30.50",
     "TIME+ als m:ss.hh");
  applyLayout({ ...layoutMessage(), hidden: [] });
  eq(ids(), COLS.map((c) => c.id).join(), "alle Spalten sichtbar");
  const r4242 = row(4242, { name: "neu", user: "<b>u</b>", pri: 20, nice: -5, virt: 3 * G, shr: null, s: "S",
                            time: 7530.5, rss: G, cpu: 3 });
  const memTile = { id: "mem", kind: "mem", aside: { v: G, u: "B", of: 4 * G } };
  const tr4242 = () => rows().find((tr) => cell(tr, "pid").textContent === "4242");
  receive(tick([memTile], { procs: [...base, r4242], detail: full(base[3]) }));
  eq(["pid", "nice", "virt", "shr", "s", "mem", "time"].map((c) => plain(cell(tr4242(), c).textContent)).join("|"),
     "4242|-5|3 GB|–|S|25,0 %|125:30.50", "Formate der neuen Spalten");
  eq(cell(tr4242(), "mem").textContent, "25,0\u00a0%", "%MEM mit geschütztem Leerzeichen wie fmt");
  eq(cell(tr4242(), "user").textContent + "/" + cell(tr4242(), "user").querySelectorAll("b").length, "<b>u</b>/0",
     "Benutzer als Text");
  receive(ptick([...base, { ...r4242, cpu: 4 }], full(base[3])));
  eq(cell(tr4242(), "mem").textContent, "–", "ohne mem-Kachel: %MEM –");

  // ---- Sortieren nach jeder Spalte: aria-sort am Kopf, Zeilen nach c.get in dieser Richtung monoton ----
  receive(tick([memTile], { procs: [...base, r4242], detail: full(base[3]) }));
  const sortedBy = (c) => {
    const s = th(c.id).getAttribute("aria-sort"), dir = s === "ascending" ? 1 : -1;
    const data = rows().map((tr) => state.last.procs.find((p) => String(p.pid) === cell(tr, "pid").textContent));
    return !!s && data.every((p, i) => !i || dir * compare(c.get(data[i - 1]), c.get(p)) <= 0);
  };
  for (const c of COLS) {
    hb(c.id).click();
    eq(sortedBy(c), true, `sortiert nach ${c.id}`);
  }
  const ringInside = (b) => { // Umriss = Knopf plus outline-offset und outline-width, die Zelle schneidet ab
    const r = b.getBoundingClientRect(), t = b.parentNode.getBoundingClientRect(), s = getComputedStyle(b);
    const o = parseFloat(s.outlineOffset) + parseFloat(s.outlineWidth);
    return r.left - o >= t.left - 0.5 && r.right + o <= t.right + 0.5 && r.top - o >= t.top - 0.5;
  };
  hb("mem").click();
  hb("mem").focus();
  eq(hb("mem").matches(":focus-visible") && ringInside(hb("mem")), true, "Fokusring des sortierten Kopfs %MEM ganz sichtbar");
  hb("cpu").click();
  eq(th("cpu").getAttribute("aria-sort"), "descending", "zurück auf CPU absteigend");
  setWidth("cpu", 5);
  setWidth("ram", 5000);
  setWidth("process", 5); // RAM 1200 px: die Füllbreite liegt unter 120 px, die Prozess-Breite wird gespeichert
  eq(JSON.stringify(layoutMessage().widths), '{"cpu":40,"ram":1200,"process":120}', "setWidth begrenzt die Breite");
  return labelCount;
}
