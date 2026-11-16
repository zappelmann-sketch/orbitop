// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 zappelmann-sketch
// Spielt die Demodaten in die Oberfläche ein, wie es die App über window.orbitop.receive tut.
"use strict";
(() => {
  const { init, tick } = window.ORBITOP_DEMO;
  const n = Number(new URLSearchParams(location.search).get("threads"));
  const cpu = tick.tiles.find((t) => t.kind === "cpu");
  if (n > 0 && cpu && cpu.threads && cpu.threads.length) {
    cpu.threads = Array.from({ length: n }, (_, i) => cpu.threads[i % cpu.threads.length]);
  }
  window.orbitop.receive(init);
  window.orbitop.receive(tick);
})();
