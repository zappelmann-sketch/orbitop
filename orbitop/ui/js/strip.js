// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Lastzeile: Prozesse mit der höchsten Last als Chips; ein Klick wählt den Prozess im Reiter „Prozesse“.
import { button, el, setText } from "./dom.js";
import { fill, fmt, number } from "./format.js";
import { calls, state, ui } from "./state.js";

export function renderStrip(top) {
  const cpu = (top && top.cpu) || [];
  const briefs = state.briefs = top && top.mem ? [...cpu, top.mem] : cpu;
  while (ui.chips.childElementCount > briefs.length) ui.chips.lastChild.remove();
  while (ui.chips.childElementCount < briefs.length) {
    const i = ui.chips.childElementCount;
    const b = button("chip", ui.chips, () => {
      const p = state.briefs[i];
      if (p) calls.select("procs", p.pid, p.start);
    });
    el("b", "nm", b);
    el("span", "", b);
  }
  briefs.forEach((p, i) => {
    const chip = ui.chips.children[i];
    setText(chip.firstChild, String(p.name));
    setText(chip.lastChild, " " + (i < cpu.length
      ? fill("strip.cpu", { pct: number(p.cpu, state.lang, 0, 0, false) })
      : fill("strip.ram", { size: fmt({ v: p.rss, u: "B" }, state.lang) })));
  });
}
