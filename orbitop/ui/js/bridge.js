// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Brücke von Python: window.orbitop.receive verteilt init, tick und die Antworten an die Module der Seite.
import { applyLayout, equal, keyOf, labelHead, refresh, renderDetail, renderProcs } from "./app.js";
import { notify, renderAutostart } from "./dialogs.js";
import { setText } from "./dom.js";
import { fill, text } from "./format.js";
import { renderFooter } from "./footer.js";
import { hdrInfo, renderOverview } from "./page.js";
import { state, ui } from "./state.js";

export function receive(msg) {
  if (!msg) return;
  if (msg.type === "init") {
    state.lang = msg.lang === "de" ? "de" : "en";
    state.texts = msg.texts || {};
    state.version = String(msg.version || "");
    state.collator = new Intl.Collator(state.lang);
    document.documentElement.lang = state.lang;
    for (const [node, key, attr] of ui.labels) {
      if (attr) node.setAttribute(attr, text(key));
      else node.textContent = text(key);
    }
    applyLayout(state.saving ? state.layout : msg.layout); // Meldung steht aus: der neuere Stand der Seite gilt
    labelHead(); // auch ohne Neuaufbau des Kopfes
    setText(ui.version, fill("about.version", { version: state.version }));
    state.autostart = typeof msg.autostart === "boolean" ? msg.autostart : null;
    renderAutostart();
    hdrInfo();
  } else if (msg.type === "tick") {
    const prev = state.last;
    // Python lässt die unveränderte Liste weg: dasselbe Array behalten, equal() endet dann bei a === b
    if (msg.procs_same === true) msg.procs = prev && Array.isArray(prev.procs) ? prev.procs : null;
    state.last = msg;
    state.n++;
    renderFooter(msg.missing, msg.hints);
    if (state.tab === "overview") renderOverview(msg); // ausgeblendete Kacheln nicht zeichnen
    // Prozesse kommen alle 2 s: dazwischen bleiben Tabelle und Detail, nur das Alter im Detail läuft weiter
    else if (Array.isArray(msg.procs) && prev && equal(msg.procs, prev.procs) && equal(msg.detail, prev.detail)) renderDetail(msg);
    else renderProcs(msg);
  } else if (msg.type === "terminate_result") {
    const t = state.pending;
    state.pending = null; // Python nimmt erst jetzt wieder ein terminate an
    notify(msg.result, t && t.pid === msg.pid ? t : null);
    refresh();
  } else if (msg.type === "terminate_check") {
    const t = state.lastTerm;
    if (!t || msg.pid !== t.pid) return;
    if (msg.alive) state.alert = keyOf(t); // „Sofort beenden“ hervorheben
    else notify("gone", t);
    refresh();
  } else if (msg.type === "autostart_state") {
    state.autostart = typeof msg.on === "boolean" ? msg.on : null;
    state.autoBusy = false;
    renderAutostart();
  }
}

// Module legen keine globalen Namen an. Python ruft window.orbitop.receive; es steht vor DOMContentLoaded bereit.
window.orbitop = { receive };
