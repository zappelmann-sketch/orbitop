// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Einstellungen im Dialog „Über“ unter „Beim Anmelden starten“: der Schalter „Messzähler freigeben“ (Spec C1) und
// „Ausgeblendete Hinweise wieder zeigen“ (C3). counters sendet nur stepConfirmed, der Knopf im Schritt nach der
// Erklärung; weder das Laden der Seite noch der Schalter selbst senden. Die Erklärung hilft bei der Bedienung und ist
// kein Schutz (E6): Eine kompromittierte Seite überspringt sie, schützen müssen die Passwortabfrage und ihr Text.
import { button, el, label, setText } from "./dom.js";
import { fill, text } from "./format.js";
import { post } from "./post.js";
import { state, ui } from "./state.js";

const RESULTS = ["cancelled", "denied", "busy", "locked", "nohelper", "error"]; // ok: kein Text, es gilt der Zustand
const PARTS = { perfmon: "settings.part_perfmon", rapl: "settings.part_rapl" };
const MISSING = { perfmon: "settings.state_missing_perfmon", rapl: "settings.state_missing_rapl" };
const STATES = { works: "settings.state_works", broken: "settings.state_broken", manual: "settings.state_manual",
                 none: "settings.state_none" }; // Anzeige nach der Tabelle in B2.5
const LOCKED = { nohelper: "settings.counters_nohelper", nopkexec: "settings.counters_nopkexec" };

export function buildSettings(parent) {
  ui.cnt = label(button("switch counters", parent, openStep), "settings.counters");
  ui.cnt.setAttribute("role", "switch");
  label(el("p", "s", parent), "settings.counters_hint").id = "counters-hint";
  ui.cntLines = el("div", "lines s", parent);
  ui.cntLines.id = "counters-lines";
  ui.cnt.setAttribute("aria-describedby", "counters-hint counters-lines");
  ui.cntStep = el("div", "step", parent);
  ui.cntStep.hidden = true;
  ui.cntStepText = el("p", "", ui.cntStep);
  const btns = el("div", "btns", ui.cntStep);
  ui.cntNo = label(button("btn plain", btns, () => closeStep(true)), "confirm.cancel");
  ui.cntGo = button("btn term", btns, stepConfirmed);
  ui.cntResult = el("p", "s result", parent);
  ui.cntResult.setAttribute("role", "status");
  ui.showHints = label(button("btn plain show", parent, showHints), "settings.show_hints");
  renderCounters();
  renderShowHints();
}

/** Schalter, Zeilen je Teil und Ergebnis. Der Schalter zeigt nur die Merkdatei (unclear: aus); gesperrt ohne
 * nutzbaren Helfer, während des Auftrags und nach „zu oft abgelehnt“ bis zum Neustart. */
export function renderCounters() {
  const c = state.counters && typeof state.counters === "object" ? state.counters : {};
  const usable = c.usable === "yes" || c.usable === "nopkexec" ? c.usable : "nohelper"; // fehlt es: wie ohne Paket
  ui.cnt.setAttribute("aria-checked", String(c.marker === "on"));
  ui.cnt.setAttribute("aria-disabled", String(usable !== "yes" || state.cntBusy || state.cntResult === "locked"));
  const lines = usable === "yes" ? [] : [text(LOCKED[usable])];
  if (c.marker === "unclear") lines.push(text("settings.counters_unclear"));
  for (const p of Array.isArray(c.parts) ? c.parts : []) {
    const known = p && Object.hasOwn(PARTS, p.part); // Object.hasOwn: auch "constructor" ist unbekannt
    const key = known && (p.state === "missing" ? MISSING[p.part] : Object.hasOwn(STATES, p.state) && STATES[p.state]);
    if (key) lines.push(fill("settings.part_line", { part: text(PARTS[p.part]), state: text(key) }));
  }
  if (c.manual_rule === true) lines.push(text("settings.counters_manual_rule")); // B2.9: bleibt auch mit Merkdatei
  ui.cntLines.replaceChildren(...lines.map((s) => el("p", "", null, s)));
  const r = state.cntResult;
  ui.cntResult.hidden = r === null || r === "ok";
  setText(ui.cntResult, ui.cntResult.hidden ? "" : text("counters." + (RESULTS.includes(r) ? r : "error")));
}

/** Erklärung vor der Passwortabfrage: bei „aus“ und „unklar“ der Schritt „Freigeben“, bei „an“ „Sperren“. */
function openStep() {
  if (ui.cnt.getAttribute("aria-disabled") === "true") return;
  state.cntWant = !(state.counters && state.counters.marker === "on");
  setText(ui.cntStepText, text(state.cntWant ? "settings.release_text" : "settings.lock_text"));
  setText(ui.cntGo, text(state.cntWant ? "settings.release" : "settings.lock"));
  ui.cntStep.hidden = false;
  ui.cntNo.focus(); // wie die Rückfrage: „Abbrechen“, nie die Bestätigung
}

/** Schritt zu; dialogs.js ruft es auch beim Schließen des Dialogs (focus false, den Fokus gibt der Dialog zurück). */
export function closeStep(focus) {
  state.cntWant = null;
  ui.cntStep.hidden = true;
  if (focus) ui.cnt.focus();
}

function stepConfirmed() {
  const on = state.cntWant;
  closeStep(true);
  if (on === null) return; // nur aus dem offenen Schritt; während des Auftrags öffnet openStep keinen
  state.cntBusy = true;
  state.cntResult = null;
  post({ type: "counters", on });
  renderCounters();
}

/** „Ausgeblendete Hinweise wieder zeigen“: gesperrt, solange nichts ausgeblendet ist. */
export function renderShowHints() {
  ui.showHints.setAttribute("aria-disabled", String(!state.hidden.length));
}

function showHints() {
  if (ui.showHints.getAttribute("aria-disabled") !== "true") post({ type: "show_hints" });
}
