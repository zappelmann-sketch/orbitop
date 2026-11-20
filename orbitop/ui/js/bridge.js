// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Brücke von Python: window.orbitop.receive verteilt init, tick und die Antworten an die Module der Seite.
import { applyLayout, keyOf, labelHead, refresh, renderDetail, renderProcs } from "./procs/view.js";
import { notify, renderAutostart } from "./dialogs.js";
import { setText } from "./dom.js";
import { fill, text } from "./format.js";
import { renderFooter } from "./footer.js";
import { hdrInfo } from "./header.js";
import { renderOverview } from "./page.js";
import { renderCounters, renderShowHints } from "./settings.js";
import { state, ui } from "./state.js";

/** Tiefer Vergleich zweier Teile des Schnappschusses (JSON-Werte). */
function equal(a, b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((k) => equal(a[k], b[k]));
}

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
    state.counters = msg.counters || null; // ein laufender Auftrag und sein Ergebnis bleiben über ein neues init
    state.hidden = Array.isArray(msg.hidden_hints) ? msg.hidden_hints : [];
    renderCounters();
    renderShowHints();
    renderFooter();
    hdrInfo();
  } else if (msg.type === "tick") {
    const prev = state.last;
    // Python lässt die unveränderte Liste weg: dasselbe Array behalten, equal() endet dann bei a === b
    if (msg.procs_same === true) msg.procs = prev && Array.isArray(prev.procs) ? prev.procs : null;
    state.last = msg;
    state.n++;
    renderFooter();
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
  } else if (msg.type === "counters_state") { // Antwort auf counters: frischer Zustand und ein festes Wort
    state.counters = msg.counters || null;
    state.cntBusy = false;
    state.cntResult = msg.result;
    renderCounters();
    renderFooter(); // Q4: die Textwahl hängt an usable
  } else if (msg.type === "hints_state") {
    state.hidden = Array.isArray(msg.hidden_hints) ? msg.hidden_hints : [];
    renderShowHints();
    renderFooter();
  }
}

// Module legen keine globalen Namen an. Python ruft window.orbitop.receive; es steht vor DOMContentLoaded bereit.
window.orbitop = { receive };
