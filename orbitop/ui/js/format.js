// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Texte aus texts und Zahlen als Text: Einheiten, Dezimalzeichen nach Sprache, Bytes in 1024er-Stufen.
import { formats, state } from "./state.js";

export const BYTES = ["B", "KB", "MB", "GB", "TB"];
const DIGITS = { GHz: 1, W: 1 }; // sonst ganze Zahlen; Bytes unter 10 mit einer Nachkommastelle

/** 1024er-Stufe für big; eine Stufe höher, wenn die Rundung 1024 ergäbe (1023,7 B/s -> 1 KB/s). */
export function byteStep(big) {
  let e = 0;
  while (e < BYTES.length - 1 && Math.round(big / 1024 ** e) >= 1024) e++;
  return e;
}

export function text(key) {
  return Object.hasOwn(state.texts, key) ? state.texts[key] : key;
}

/** Platzhalter wie {list} per reiner Zeichenkettenersetzung, ohne $-Muster von String.replace. */
export function fill(key, vars) {
  return text(key).replace(/\{(\w+)\}/g, (m, k) => (Object.hasOwn(vars, k) ? String(vars[k]) : m));
}

export function number(v, lang, min, max, group) {
  const key = `${lang}|${min}|${max}|${group}`;
  let f = formats.get(key);
  if (!f) {
    f = new Intl.NumberFormat(lang, { minimumFractionDigits: min, maximumFractionDigits: max, useGrouping: group });
    formats.set(key, f);
  }
  return f.format(v);
}

/** Num -> Text: Bytes in 1024er-Stufen, „v / of Einheit“, Präfix p, Dezimalzeichen nach Sprache, null als „–“. */
export function fmt(num, lang) {
  if (!num || num.v == null) return "–";
  const u = num.u, of = num.of;
  let unit = u, scale = 1;
  if (u === "B" || u === "B/s") {
    const e = byteStep(Math.max(Math.abs(num.v), Math.abs(of || 0)));
    scale = 1024 ** e;
    unit = BYTES[e] + u.slice(1);
  } else if (u === "rpm") {
    unit = text("unit.rpm");
  }
  const part = (x) => {
    x /= scale;
    if (scale > 1) return number(x, lang, 0, Math.abs(x) < 10 ? 1 : 0, false);
    const d = DIGITS[u] || 0;
    return number(x, lang, d, d, u === ""); // Tausenderpunkt nur bei Anzahlen (Entwurf: „1.904“, aber „4800 U/min“)
  };
  const sep = u === "" || (u === "%" && lang === "en") ? "" : " ";
  return (num.p ? num.p + " " : "") + part(num.v) + (of == null ? "" : " / " + part(of)) + sep + unit;
}

/** Num | Txt | [Num|Txt] -> Text; Txt.k wird übersetzt, Txt.l bleibt roh. */
export function show(x) {
  if (Array.isArray(x)) return x.map(show).join(" · ");
  if (x && "k" in x) return text(x.k);
  if (x && "l" in x) return String(x.l);
  return fmt(x, state.lang);
}

/** Modellnamen kürzen wie im Entwurf („i7-7600U“ statt „Intel(R) Core(TM) i7-7600U CPU @ 2.80GHz“). */
export function shortName(name) {
  return name.replace(/\((R|TM)\)|[®™]/gi, "").replace(/\s+(CPU\s+)?@\s.*$/i, "").replace(/\s+/g, " ").trim();
}
