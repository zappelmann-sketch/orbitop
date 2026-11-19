// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Einstieg der Seite: lädt die Brücke für Python (window.orbitop), baut die Oberfläche und meldet ready.
import "./bridge.js";
import { build, select } from "./page.js";
import { post } from "./post.js";
import { state } from "./state.js";

build();
if (location.hash === "#procs") { // Sichtprüfung: demo.html#procs, App mit ORBITOP_TAB=procs
  state.autoPick = true;
  select("procs", null, null);
}
post({ type: "ready" });
