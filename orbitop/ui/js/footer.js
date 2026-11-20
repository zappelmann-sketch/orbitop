// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Fußzeile: fehlende Sensoren und Hinweise zu den Kacheln. Jeder Hinweis hat „Ausblenden“ (Spec C3); hide_hint sendet
// nur dieses Modul, und ausgeblendet ist erst, was Python mit hints_state bestätigt. Ein neuer Schlüssel erscheint
// auch, wenn ein alter ausgeblendet ist. Beim Hinweis hint.igt_missing der Knopf „Installieren“ (C2): nur, wenn init
// install.usable meldet (Intel-Grafik, Paket); sonst und nach failed oder unavailable der Befehl der Distribution.
// install_tool sendet nur install(), ohne Namen; die Vorbedingungen prüft Python.
import { button, el, setText } from "./dom.js";
import { fill, text } from "./format.js";
import { post } from "./post.js";
import { state, ui } from "./state.js";

// Klärung Q4: ohne nutzbaren Schalter (Start ohne Paket, fremdes pkexec) verweisen sie auf die README
const README = { "hint.igt_noperm": "hint.igt_noperm_readme", "hint.rapl_noperm": "hint.rapl_noperm_readme" };
const RESULTS = ["denied", "busy", "locked", "failed", "unavailable", "installed"]; // Unbekanntes gilt als failed
const AGAIN = [null, "denied", "busy"]; // danach ist der Knopf (wieder) da; locked bis zum Neustart, installed einmal

/** Die Fußzeile und neben ihr eine bleibende Statusregion für das Ergebnis von install_tool: renderFooter baut die
 * Fußzeile neu, und eine neu eingefügte Region sagen Bildschirmleser nicht an. tabIndex -1: Ziel des Fokus, wenn nach
 * „Ausblenden“ kein Hinweis mehr da ist. */
export function buildFooter(parent) {
  ui.footer = el("footer", "foot", parent);
  ui.footer.tabIndex = -1;
  ui.instLive = el("p", "live", parent);
  ui.instLive.setAttribute("role", "status");
}

/** Aus dem letzten tick, den ausgeblendeten Hinweisen, counters.usable und dem Stand von install. */
export function renderFooter() {
  const msg = state.last;
  if (!msg) return;
  const lines = (msg.missing && msg.missing.length)
    ? [fill("footer.missing", { list: msg.missing.map((k) => text("missing." + k)).join(" · ") })] : [];
  const readme = !(state.counters && state.counters.usable === "yes");
  const hints = (msg.hints || []).filter((k) => !state.hidden.includes(k))
    .map((k) => [k, text(readme && Object.hasOwn(README, k) ? README[k] : k)]);
  const inst = installView();
  setText(ui.instLive, inst.say); // nur bei neuem Text angesagt; ein neuer Auftrag leert ihn
  const sig = [text("hint.hide"), ...lines, ...hints.flat(), JSON.stringify(inst)].join("\n");
  if (ui.footerSig === sig) return;
  ui.footerSig = sig;
  const active = document.activeElement; // ein Knopf einer Hinweiszeile verschwindet mit dem Neubau
  const line = active && active !== ui.footer && ui.footer.contains(active) ? active.closest(".hint") : null;
  const at = [...ui.footer.querySelectorAll(".hint")].indexOf(line);
  ui.footer.replaceChildren(...lines.map((s) => el("p", "", null, s)), ...hints.map(([k, s]) => hintLine(k, s, inst)));
  ui.footer.hidden = !lines.length && !hints.length;
  if (line) refocus(at, line.dataset.key, active.classList.contains("install"));
}

/** Fokus nach dem Neubau: „Installieren“, wenn er dort war und der Knopf noch da ist; sonst „Ausblenden“ desselben
 * Hinweises, dann der Zeile an derselben Stelle oder der letzten; sonst die Fußzeile, und ist auch sie leer, „Über“
 * mit „Hinweise wieder zeigen“. Nie body. */
function refocus(at, key, install) {
  const lines = [...ui.footer.querySelectorAll(".hint")];
  const same = lines.find((p) => p.dataset.key === key);
  const line = same || lines[Math.min(at, lines.length - 1)];
  const next = (install && same && same.querySelector(".install")) || (line && line.querySelector(".hide"));
  (next || (ui.footer.hidden ? ui.infoBtn : ui.footer)).focus();
}

/** Knopf (null: keiner, sonst ob gesperrt) und Zusatz zum Hinweis hint.igt_missing. */
function installView() {
  const inst = state.install && typeof state.install === "object" ? state.install : {};
  const command = typeof inst.command === "string" ? fill("install.command", { command: inst.command }) : "";
  const r = state.instResult === null || RESULTS.includes(state.instResult) ? state.instResult : "failed";
  const usable = inst.usable === true;
  const note = [r === null ? "" : text("install." + r)];
  if (!usable || r === "failed" || r === "unavailable") note.push(command); // Review Focus 5, Spec C2
  return { button: usable && AGAIN.includes(r) ? state.instBusy : null, note: note.filter(Boolean).join(" "),
           say: note[0] };
}

function hintLine(key, s, inst) {
  const p = el("p", "hint");
  p.dataset.key = key; // für refocus
  const span = el("span", "", p, s);
  if (key === "hint.igt_missing") {
    if (inst.note) el("span", "note", span, inst.note);
    if (inst.button !== null) {
      const b = button("btn term install", p, install);
      b.textContent = text("install.button");
      b.setAttribute("aria-disabled", String(inst.button));
    }
  }
  button("hide", p, () => post({ type: "hide_hint", key })).textContent = text("hint.hide"); // Schlüssel ohne _readme
  return p;
}

function install() {
  if (installView().button !== false) return; // gesperrt während des Auftrags
  state.instBusy = true;
  state.instResult = null;
  post({ type: "install_tool" });
  renderFooter();
}
