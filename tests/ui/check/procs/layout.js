// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Spalten-Layout (procs/layout.js): Layout aus init, ausgeblendete Sortierspalte.
import { COLS } from "../../../../orbitop/ui/js/procs/columns.js";
import { applyLayout, toggleColumn } from "../../../../orbitop/ui/js/procs/layout.js";
import { ui } from "../../../../orbitop/ui/js/state.js";
import { $, eq, full, hb, names, ptick, receive, texts, th } from "../kit.js";
import { flush, timers } from "../stubs.js";
import { base, DEFAULT_IDS, detailW, ids, layouts, listW } from "./kit.js";

export function checkLayoutInit() {
  const sep = $(".split");
  // ---- Layout aus init: nie selbst gesendet ----
  flush();
  const sentBefore = layouts().length;
  const order = ["process", "cpu", ...COLS.map((c) => c.id).filter((id) => id !== "process" && id !== "cpu")];
  receive({ type: "init", lang: "de", texts, version: "9.9.9",
            layout: { order, hidden: ["user", "pri"], widths: { cpu: 90 }, split: 0.5 } });
  eq(ids(), order.filter((id) => id !== "user" && id !== "pri").join(), "init: Reihenfolge und Sichtbarkeit aus layout");
  eq(Math.round(th("cpu").getBoundingClientRect().width) + "/" + (layouts().length - sentBefore) + "/" + timers.length,
     "90/0/0", "init: Breite aus layout, nichts gesendet");
  eq(sep.getAttribute("aria-valuenow") + "/" + (Math.abs(listW() - detailW()) <= 1), "50/true", "init: Trenner aus layout");
  receive({ type: "init", lang: "de", texts, version: "9.9.9", layout: null });
  eq(ids() + "/" + hb("pid").title, DEFAULT_IDS + "/Prozessnummer", "init ohne layout: Standard");
  toggleColumn("pri");
  toggleColumn("nice");
  eq(timers.length, 1, "Meldung steht aus");
  receive({ type: "init", lang: "de", texts, version: "9.9.9", layout: null }); // älterer Stand von Python
  flush();
  eq(ids() + "/" + JSON.parse(layouts().at(-1)).hidden.join(), DEFAULT_IDS + ",pri,nice/virt,shr,s,mem,time",
     "init bei ausstehender Meldung: letzte Änderung bleibt und wird gemeldet");
  applyLayout(null);
}

export function checkSortHidden(labelCount) {
  // ---- Sortierspalte ausgeblendet: CPU absteigend; nach CPU sortiert und CPU ausgeblendet: Auswahl bleibt ----
  receive(ptick([...base], full(base[3])));
  toggleColumn("nice");
  hb("nice").click();
  eq(names(), "beta,alpha,chip,Gamma", "nach NI sortiert");
  toggleColumn("nice");
  eq(th("cpu").getAttribute("aria-sort") + "/" + names(), "descending/alpha,Gamma,beta,chip",
     "Sortierspalte ausgeblendet: CPU absteigend");
  const selKey = $(".ptable tr.sel").dataset.key;
  toggleColumn("cpu");
  eq(names() + "/" + $(".ptable tr.sel").dataset.key, "alpha,Gamma,beta,chip/" + selKey,
     "CPU ausgeblendet: weiter nach CPU absteigend, Auswahl bleibt");
  toggleColumn("cpu");
  flush();
  eq(ids() + "/" + ui.labels.length, DEFAULT_IDS + "/" + labelCount, "wieder Standardspalten, ui.labels nicht gewachsen");
}
