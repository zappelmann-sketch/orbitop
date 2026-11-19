// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Diagrammfläche für die Kacheln der Übersicht und das Detail im Reiter „Prozesse“, dazu die Grundfarbe je Art.
import { el, svg } from "./dom.js";

export const AREA = { cpu: "#4fd8ff", gpu: "#c48bff", mem: "#3dffa8", power: "#ffd84f", temp: "#ff5f7a", fan: "#ff7ad9",
                      net: "#5b8cff", disk: "#2ff0d0" };

/** Diagrammfläche: Beschriftung, Gitter (SVG) und darüber die Canvas der Kurven (zurückgegeben). */
export function plot(parent, cls, cap) {
  const box = el("div", cls, parent);
  el("span", "cap", box, cap);
  const c = el("canvas", "", box);
  c.grid = svg(box, "gridlines", null, [""]);
  box.append(c);
  return c;
}
