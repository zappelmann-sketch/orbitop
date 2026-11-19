// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Spielt die Demodaten in die Oberfläche ein, wie es die App über window.orbitop.receive tut.
// ?threads=16 vervielfacht die CPU-Threads (Balkenreihe), ?long=120 setzt überall unumbrechbare Namen dieser Länge.
// ?replay=N spielt vorher N Takte ein, deren Verläufe je einen Schritt zurückliegen (links mit dem ältesten Wert
// aufgefüllt): So zeichnen die Diagramme am Ende inkrementell, für den Bildvergleich mit vollem Zeichnen.
// ?cols=all blendet alle Spalten ein (Sichtprüfung, Messung).
// #procs öffnet den Reiter „Prozesse“ und wählt den obersten Prozess (main.js).
import "./demo-data.js";
import { COLS } from "../../orbitop/ui/js/procs/columns.js";
import "../../orbitop/ui/js/main.js";

(() => {
  const { init, tick } = window.ORBITOP_DEMO;
  const params = new URLSearchParams(location.search);
  const n = Number(params.get("threads"));
  const cpu = tick.tiles.find((t) => t.kind === "cpu");
  if (n > 0 && cpu && cpu.threads && cpu.threads.length) {
    cpu.threads = Array.from({ length: n }, (_, i) => cpu.threads[i % cpu.threads.length]);
  }
  const long = Number(params.get("long"));
  if (long > 0) {
    const name = "label_".padEnd(long, "x");
    for (const t of tick.tiles) {
      t.name = name;
      t.aside = { l: name };
      for (const r of t.kv) if ("l" in r) r.l = name;
      t.kv.push({ l: name, v: { l: name } });
      for (const s of t.series) if ("label" in s) s.label = name;
      for (const r of t.devices ? t.devices.rows : []) r.name = name;
    }
    for (const b of tick.top.cpu) b.name = name;
    for (const r of [...(tick.procs || []), tick.detail].filter(Boolean)) Object.assign(r, { name, args: name, user: name });
    if (tick.detail) Object.assign(tick.detail, { cmdline: name, parent: name });
  }
  if (params.get("cols") === "all") init.layout = { order: COLS.map((c) => c.id), hidden: [], widths: {}, split: 1.55 / 2.55 };
  window.orbitop.receive(init);
  const older = (v, k) => (v ? [...Array(Math.min(k, v.length)).fill(v[0]), ...v.slice(0, Math.max(0, v.length - k))] : v);
  for (let k = Number(params.get("replay")) || 0; k > 0; k--) {
    window.orbitop.receive({ ...tick,
      tiles: tick.tiles.map((t) => ({ ...t, threads: t.threads && t.threads.map((v) => older(v, k)),
                                      series: t.series.map((s) => ({ ...s, values: older(s.values, k) })) })),
      detail: tick.detail && { ...tick.detail, history: older(tick.detail.history, k) } });
  }
  window.orbitop.receive(tick);
})();
