// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Fußzeile: fehlende Sensoren und Hinweise zu den Kacheln. Jeder Hinweis hat „Ausblenden“ (Spec C3); hide_hint sendet
// nur dieses Modul, und ausgeblendet ist erst, was Python mit hints_state bestätigt. Ein neuer Schlüssel erscheint
// auch, wenn ein alter ausgeblendet ist.
import { button, el } from "./dom.js";
import { fill, text } from "./format.js";
import { post } from "./post.js";
import { state, ui } from "./state.js";

// Klärung Q4: ohne nutzbaren Schalter (Start ohne Paket, fremdes pkexec) verweisen sie auf die README
const README = { "hint.igt_noperm": "hint.igt_noperm_readme", "hint.rapl_noperm": "hint.rapl_noperm_readme" };

/** Aus dem letzten tick, den ausgeblendeten Hinweisen und counters.usable. */
export function renderFooter() {
  const msg = state.last;
  if (!msg) return;
  const lines = (msg.missing && msg.missing.length)
    ? [fill("footer.missing", { list: msg.missing.map((k) => text("missing." + k)).join(" · ") })] : [];
  const readme = !(state.counters && state.counters.usable === "yes");
  const hints = (msg.hints || []).filter((k) => !state.hidden.includes(k))
    .map((k) => [k, text(readme && Object.hasOwn(README, k) ? README[k] : k)]);
  const sig = [text("hint.hide"), ...lines, ...hints.flat()].join("\n");
  if (ui.footerSig === sig) return;
  ui.footerSig = sig;
  ui.footer.replaceChildren(...lines.map((s) => el("p", "", null, s)), ...hints.map(([k, s]) => hintLine(k, s)));
  ui.footer.hidden = !lines.length && !hints.length;
}

function hintLine(key, s) {
  const p = el("p", "hint");
  el("span", "", p, s);
  button("hide", p, () => post({ type: "hide_hint", key })).textContent = text("hint.hide"); // Schlüssel ohne _readme
  return p;
}
