// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Fußzeile: fehlende Sensoren und Hinweise zu den Kacheln.
import { el } from "./dom.js";
import { fill, text } from "./format.js";
import { ui } from "./state.js";

export function renderFooter(missing, hints) {
  const lines = (missing && missing.length)
    ? [fill("footer.missing", { list: missing.map((k) => text("missing." + k)).join(" · ") })] : [];
  const all = [...lines, ...(hints || []).map(text)];
  if (ui.footerSig === all.join("\n")) return;
  ui.footerSig = all.join("\n");
  ui.footer.replaceChildren(...all.map((s, i) => el("p", i < lines.length ? "" : "hint", null, s)));
  ui.footer.hidden = !all.length;
}
