// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Einstieg der Seite: setzt die Brücke für Python, baut die Oberfläche und meldet ready.
import { build, post, receive, select, state } from "./app.js";

// Module legen keine globalen Namen an. Python ruft window.orbitop.receive; es steht vor DOMContentLoaded bereit.
window.orbitop = { receive };
build();
if (location.hash === "#procs") { // Sichtprüfung: demo.html#procs, App mit ORBITOP_TAB=procs
  state.autoPick = true;
  select("procs", null, null);
}
post({ type: "ready" });
