// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter und Chips (page.js, strip.js) melden die Ansicht an Python.
import { $, $$, cpu, eq, plain, receive, tick } from "./kit.js";
import { posted } from "./stubs.js";

export function checkTabs() {
  // ---- Reiter und Chips melden die Ansicht an Python; verborgene Übersicht zeichnet nicht ----
  receive(tick([cpu([[1]], { main: { v: 12, u: "%" } })]));
  $$(".tab")[1].click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":null,"start":null}', "Reiter Prozesse");
  eq($(".overview").hidden, true, "Übersicht ausgeblendet");
  receive(tick([cpu([[1]], { main: { v: 33, u: "%" } })]));
  eq(plain($(".tile .v").textContent), "12 %", "verborgene Übersicht zeichnet nicht");
  $$(".tab")[0].click();
  eq(posted.at(-1), '{"type":"view","tab":"overview","pid":null,"start":null}', "Reiter Übersicht");
  eq(plain($(".tile .v").textContent), "33 %", "beim Zurückschalten mit dem letzten Tick gezeichnet");
  $(".chip").click();
  eq(posted.at(-1), '{"type":"view","tab":"procs","pid":42,"start":7}', "Chip wählt Prozess");
}
