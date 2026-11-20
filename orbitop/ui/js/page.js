// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Aufbau der Seite (Kopfzeile, Übersicht, Prozesse, Fußzeile, Dialoge) und Wechsel der Reiter.
import { buildProcs, renderProcs } from "./procs/view.js";
import { ask, buildDialogs, openDialog } from "./dialogs.js";
import { button, el, label, svg } from "./dom.js";
import { buildFooter } from "./footer.js";
import { hdrInfo } from "./header.js";
import { post } from "./post.js";
import { calls, state, ui } from "./state.js";
import { renderStrip } from "./strip.js";
import { renderTiles } from "./tiles.js";

const TABS = ["overview", "procs"];

export function build() {
  const body = document.body;
  const hdr = el("header", "hdr", body);
  el("span", "brand", hdr, "ORBITOP");
  const nav = el("nav", "tabs", hdr);
  ui.tabs = TABS.map((name) => label(button("tab", nav, () => select(name, null, null)), "tab." + name));
  ui.hdrInfo = el("span", "s", hdr);
  ui.infoBtn = label(button("info", hdr, () => openDialog(ui.about, ui.infoBtn, ui.aboutClose)), "about.title", "aria-label");
  svg(ui.infoBtn, "", "0 0 16 16", ["M2 8a6 6 0 1 0 12 0a6 6 0 1 0-12 0", "M8 7v4.5", "M8 4.3v.4"]);
  ui.overview = el("section", "overview", body);
  const strip = el("div", "strip", ui.overview);
  label(el("span", "lbl", strip), "strip.top");
  ui.chips = el("span", "chips", strip);
  label(el("span", "s hint", strip), "strip.hint");
  ui.grid = el("div", "grid", ui.overview);
  ui.procs = el("section", "procs", body);
  buildProcs(ask);
  buildFooter(body);
  buildDialogs();
  showTab("overview");
}

function showTab(name) {
  state.tab = name;
  ui.overview.hidden = name !== "overview";
  ui.procs.hidden = name !== "procs";
  ui.footer.classList.toggle("off", name !== "overview"); // Hinweise der Fußzeile betreffen die Kacheln
  ui.tabs.forEach((b, i) => {
    b.classList.toggle("on", TABS[i] === name);
    b.setAttribute("aria-pressed", String(TABS[i] === name));
  });
  hdrInfo();
}

/** Reiter zeigen und Python melden; pid/start (Lastzeile, Tabellenzeile) wählen einen Prozess. Die Auswahl bleibt. */
export function select(name, pid, start) {
  if (pid != null) state.sel = { pid, start };
  showTab(name);
  const sel = name === "procs" ? state.sel : null;
  post({ type: "view", tab: name, pid: sel ? sel.pid : null, start: sel ? sel.start : null });
  if (state.last) (name === "overview" ? renderOverview : renderProcs)(state.last);
}

export function renderOverview(msg) {
  renderStrip(msg.top);
  renderTiles(msg.tiles || []);
}

calls.select = select; // spät gebunden: select → renderProcs → select (autoPick); strip.js und procs/rows.js wählen darüber
