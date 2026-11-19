// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Reiter „Prozesse“: Detail des gewählten Prozesses und die Knöpfe zum Beenden.
// Systemtexte kommen nur per textContent ins DOM, nie als HTML.
import { drawArea } from "../chart.js";
import { fillInto, pairs, setText } from "../dom.js";
import { fill, fmt, number, text } from "../format.js";
import { state, ui } from "../state.js";
import { AREA } from "../tiles.js";
import { clock, duration, KIND, keyOf, same } from "./columns.js";

const PROC_POINTS = 150, PROC_GRID = 15; // 2 s je Punkt: Detail 5 min, Linie alle 30 s

function ioText(d) {
  if (d.io == null) return d.own ? "–" : text("detail.io_hidden");
  const rate = fmt({ v: d.io, u: "B/s" }, state.lang);
  // Dauerlast ohne E/A heißt: seit since kein Byte gelesen oder geschrieben
  return d.state === "busy_noio" ? fill("detail.io_since", { rate, since: duration(d.since) }) : rate;
}

/** Gewählter Prozess: volles detail von Python, bis dahin (gleich nach dem Klick) die Tabellenzeile. */
export function renderDetail(msg) {
  const sel = state.sel, lang = state.lang;
  const full = msg.detail && same(msg.detail, sel) ? msg.detail : null;
  const d = full || (sel && msg.procs.find((p) => same(p, sel))) || null;
  ui.shown = full;
  ui.d = d;
  ui.none.hidden = !!d;
  ui.dbody.hidden = !d;
  renderButtons();
  if (!d) return;
  setText(ui.dname, String(d.name));
  ui.dname.title = String(d.name);
  fillInto(ui.dpid, text("detail.pid_user"), { pid: d.pid, user: String(d.user) });
  setText(ui.dcmd, full ? String(full.cmdline) : "");
  const hist = full ? full.history : [];
  drawArea(ui.dcanvas, [{ fill: true, max: Math.max(100, Math.ceil(Math.max(0, ...hist) / 100) * 100), values: hist }],
           { color: AREA.cpu, gridEvery: PROC_GRID, points: PROC_POINTS });
  const num = (x) => number(x, lang, 0, x < 10 ? 1 : 0, false);
  pairs(ui.dkv, [
    [text("detail.cpu"), d.cpu >= 90 && d.cpu <= 105 ? fill("detail.cpu_one_core", { pct: num(d.cpu) }) : fmt({ v: d.cpu, u: "%" }, lang)],
    [text("detail.ram"), fmt({ v: d.rss, u: "B" }, lang)],
    [text("detail.io"), ioText(d)],
    [text("detail.threads"), fmt({ v: d.threads, u: "" }, lang)], // Zeile ohne threads: „–“
    [text("detail.ctx"), full ? fill("detail.ctx_value", { vol: num(full.vctx), invol: num(full.nvctx) }) : "–"],
    [text("detail.started"), full ? fill("detail.started_value",
      { time: clock(full.started), age: duration(Date.now() / 1000 - full.started) }) : "–"],
  ]);
  const tpl = text("verdict." + d.state), cut = tpl.indexOf(". ") + 1; // erster Satz fett
  ui.verdict.className = "verdict " + (KIND[d.state] || "idle");
  const parent = !full ? "–" : full.parent ? String(full.parent) : fill("detail.parent_pid", { pid: full.ppid });
  fillInto(ui.verdict, tpl.slice(cut), { since: duration(d.since), parent }, tpl.slice(0, cut));
}

/** Knöpfe frei nur mit vollem Detail der Auswahl, ohne Sperrgrund und ohne laufendes Beenden. */
export function renderButtons() {
  const d = ui.d, full = ui.shown;
  const why = !d ? null : d.state === "zombie" ? "result.zombie" : full && full.kernel === true ? "result.kernel"
    : state.pending ? "btn.busy" : null;
  const off = String(!full || !!why); // aria-disabled statt disabled: der Knopf behält den Fokus und nennt den Grund
  for (const b of [ui.term, ui.kill]) if (b.getAttribute("aria-disabled") !== off) b.setAttribute("aria-disabled", off);
  setText(ui.reason, why ? text(why) : "");
  ui.kill.classList.toggle("alert", !!full && state.alert === keyOf(full));
}
