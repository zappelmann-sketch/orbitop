// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Spielt die Demodaten in die Oberfläche ein, wie es die App über window.orbitop.receive tut.
// ?threads=16 vervielfacht die CPU-Threads (Balkenreihe), ?long=120 setzt überall unumbrechbare Namen dieser Länge.
// #procs öffnet den Reiter „Prozesse“ und wählt den obersten Prozess (app.js).
"use strict";
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
  window.orbitop.receive(init);
  window.orbitop.receive(tick);
})();
