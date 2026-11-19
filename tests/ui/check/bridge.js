// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Verteilung in bridge.js: procs_same als allererster Tick im Reiter „Prozesse“.
import { $, $$, eq, receive, tick } from "./kit.js";

export function checkFirstProcsSame() {
  // ---- procs_same als allererster Tick im Prozess-Reiter: noch keine Liste, Stand wie bei procs: null ----
  $$(".tab")[1].click();
  const procsState = () => $(".hdr .s").textContent + "|" + $(".ptable").outerHTML; // was eine Liste ändern würde
  const noList = procsState();
  let threw = null;
  try {
    receive(tick([], { procs_same: true }));
  } catch (e) {
    threw = String(e);
  }
  const afterSame = procsState();
  receive(tick([]));
  eq(threw + "/" + (afterSame === noList) + "/" + (procsState() === noList), "null/true/true",
     "procs_same ohne Liste: keine Ausnahme, Stand wie bei procs: null");
  $$(".tab")[0].click();
}
