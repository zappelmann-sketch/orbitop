// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Bausteine für das DOM: Elemente, Knöpfe, SVG-Pfade. Texte kommen nur per textContent hinein, nie als HTML.
import { ui } from "./state.js";

const SVG_NS = "http://www.w3.org/2000/svg";

export function el(tag, cls, parent, content) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (content != null) e.textContent = content;
  if (parent) parent.append(e);
  return e;
}

/** Text (oder mit attr ein Attribut) aus texts, neu gesetzt bei jedem init. */
export function label(node, key, attr) {
  ui.labels.push([node, key, attr]);
  return node;
}

export function setText(node, s) {
  if (node.textContent !== s) node.textContent = s;
}

/** Zweispaltige Liste (Name, Wert) mit wiederverwendeten Elementen. */
export function pairs(box, rows) {
  while (box.childElementCount > rows.length * 2) box.lastChild.remove();
  while (box.childElementCount < rows.length * 2) el("span", "", box);
  rows.forEach(([a, b], i) => {
    setText(box.children[2 * i], a);
    setText(box.children[2 * i + 1], b);
  });
  box.hidden = !rows.length;
}

export function button(cls, parent, onClick) {
  const b = el("button", cls, parent);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

export function svg(parent, cls, viewBox, paths) {
  const s = document.createElementNS(SVG_NS, "svg");
  if (viewBox) s.setAttribute("viewBox", viewBox);
  s.setAttribute("aria-hidden", "true");
  if (cls) s.setAttribute("class", cls);
  s.append(...paths.map(pathEl));
  parent.append(s);
  return s;
}

export function pathEl(d) {
  const p = document.createElementNS(SVG_NS, "path");
  p.setAttribute("d", d);
  return p;
}

/** Wie fill, aber als Knoten: jeder Wert wird ein eigenes span.nm (unicode-bidi: isolate), lead steht fett davor. */
export function fillInto(node, tpl, vars, lead) {
  const sig = [lead, tpl, ...Object.values(vars)].join("\0");
  if (node.sig === sig) return;
  node.sig = sig;
  const parts = tpl.split(/\{(\w+)\}/).map((s, i) => (i % 2 === 0 ? s
    : Object.hasOwn(vars, s) ? el("span", "nm", null, String(vars[s])) : `{${s}}`));
  node.replaceChildren(...(lead ? [el("b", "", null, lead)] : []), ...parts);
}
