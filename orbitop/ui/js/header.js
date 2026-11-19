// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Kopfzeile rechts: Takt in der Übersicht, Prozessanzahl im Reiter „Prozesse“.
import { setText } from "./dom.js";
import { fill, number, text } from "./format.js";
import { state, ui } from "./state.js";

/** Rechts in der Kopfzeile: Takt in der Übersicht, Prozessanzahl im Reiter „Prozesse“. */
export function hdrInfo() {
  const procs = state.tab === "procs" && state.last && state.last.procs;
  setText(ui.hdrInfo, procs ? fill("strip.count", { n: number(procs.length, state.lang, 0, 0, true) }) : text("strip.tick"));
}
